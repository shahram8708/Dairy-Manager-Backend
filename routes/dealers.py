from flask import Blueprint, request, jsonify
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import func, and_
from models import db
from models.dealer import Dealer
from models.agency import Agency
from models.delivery import DeliveryEntry, DeliveryLineItem
from models.payment import Payment
from models.product import Product
from utils.auth import admin_required, login_required_any, get_current_user
from utils.audit import log_audit
from utils.billing import recalculate_dealer_balance
from utils.validators import validate_required, sanitize_string

dealers_bp = Blueprint('dealers', __name__)


@dealers_bp.route('', methods=['GET'])
@login_required_any
def list_dealers():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        per_page = min(per_page, 100)

        current_user = get_current_user()
        query = Dealer.query
        if current_user.role == 'delivery':
            query = query.filter_by(agency_id=current_user.agency_id)

        agency_id = request.args.get('agency_id', type=int)
        if agency_id and current_user.role == 'admin':
            query = query.filter_by(agency_id=agency_id)

        route_area = request.args.get('route_area')
        if route_area:
            query = query.filter(Dealer.route_area.ilike(f'%{route_area}%'))

        search = request.args.get('search')
        if search:
            query = query.filter(Dealer.name.ilike(f'%{search}%'))

        is_active = request.args.get('is_active')
        if is_active is not None:
            query = query.filter_by(is_active=is_active.lower() == 'true')

        query = query.order_by(Dealer.name)
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'dealers': [d.to_dict() for d in paginated.items],
            'total': paginated.total,
            'page': paginated.page,
            'pages': paginated.pages,
            'per_page': per_page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _parse_date(date_str, param_name='date'):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'Invalid {param_name} format. Use YYYY-MM-DD')


@dealers_bp.route('/<int:dealer_id>/deliveries', methods=['GET'])
@login_required_any
def get_dealer_deliveries(dealer_id):
    try:
        current_user = get_current_user()
        if current_user.role == 'collector':
            return jsonify({'error': 'Access denied'}), 403
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404
        if current_user.role == 'delivery' and dealer.agency_id != current_user.agency_id:
            return jsonify({'error': 'Access denied'}), 403

        from_date = _parse_date(request.args.get('from_date'), 'from_date')
        to_date = _parse_date(request.args.get('to_date'), 'to_date')

        delivery_query = db.session.query(
            DeliveryEntry.id,
            DeliveryEntry.delivery_date,
            Agency.name.label('agency_name'),
            func.sum(DeliveryLineItem.line_amount).label('amount')
        ).join(
            DeliveryLineItem,
            DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
        ).join(
            Agency,
            DeliveryEntry.agency_id == Agency.id
        ).filter(
            DeliveryLineItem.dealer_id == dealer_id,
            DeliveryLineItem.is_non_billable == False  # noqa: E712
        )

        if from_date:
            delivery_query = delivery_query.filter(DeliveryEntry.delivery_date >= from_date)
        if to_date:
            delivery_query = delivery_query.filter(DeliveryEntry.delivery_date <= to_date)

        delivery_rows = delivery_query.group_by(
            DeliveryEntry.id,
            DeliveryEntry.delivery_date,
            Agency.name
        ).order_by(DeliveryEntry.delivery_date.desc()).all()

        entry_ids = [row.id for row in delivery_rows]
        line_map = {}
        if entry_ids:
            item_rows = db.session.query(
                DeliveryLineItem.delivery_entry_id,
                Product.name.label('product_name'),
                Product.pack_size,
                Product.outer_unit,
                Product.pieces_per_unit,
                DeliveryLineItem.quantity,
                DeliveryLineItem.unit_price,
                DeliveryLineItem.line_amount,
                DeliveryLineItem.remark,
                DeliveryLineItem.is_non_billable
            ).join(
                Product,
                DeliveryLineItem.product_id == Product.id
            ).filter(
                DeliveryLineItem.dealer_id == dealer_id,
                DeliveryLineItem.delivery_entry_id.in_(entry_ids)
            ).order_by(
                DeliveryLineItem.delivery_entry_id,
                DeliveryLineItem.id
            ).all()

            for item in item_rows:
                line_map.setdefault(item.delivery_entry_id, []).append({
                    'product_name': item.product_name,
                    'pack_size': item.pack_size,
                    'outer_unit': item.outer_unit,
                    'pieces_per_unit': item.pieces_per_unit,
                    'quantity': float(item.quantity or 0),
                    'unit_price': float(item.unit_price or 0),
                    'line_amount': float(item.line_amount or 0),
                    'remark': item.remark,
                    'is_non_billable': item.is_non_billable
                })

        deliveries = []
        for row in delivery_rows:
            const_items = line_map.get(row.id, [])
            deliveries.append({
                'delivery_date': row.delivery_date.isoformat(),
                'agency_name': row.agency_name,
                'products': ', '.join(sorted({item['product_name'] for item in const_items})) if const_items else '-',
                'amount': float(row.amount or 0),
                'line_items': const_items
            })

        return jsonify({'deliveries': deliveries}), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dealers_bp.route('/<int:dealer_id>', methods=['GET'])
@login_required_any
def get_dealer(dealer_id):
    try:
        current_user = get_current_user()
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404
        if current_user.role == 'delivery' and dealer.agency_id != current_user.agency_id:
            return jsonify({'error': 'Access denied'}), 403
        return jsonify({'dealer': dealer.to_dict()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dealers_bp.route('', methods=['POST'])
@admin_required
def create_dealer():
    try:
        data = request.get_json()
        errors = validate_required(data, ['name', 'agency_id'])
        if errors:
            return jsonify({'error': errors[0]}), 400

        agency = Agency.query.get(data['agency_id'])
        if not agency:
            return jsonify({'error': 'Agency not found'}), 404

        opening = Decimal(str(data.get('opening_balance', 0) or 0))
        credit_limit = None
        if data.get('credit_limit') is not None and data.get('credit_limit') != '':
            credit_limit = Decimal(str(data['credit_limit']))

        dealer = Dealer(
            name=sanitize_string(data.get('name')),
            phone=sanitize_string(data.get('phone')),
            address=sanitize_string(data.get('address')),
            agency_id=data['agency_id'],
            route_area=sanitize_string(data.get('route_area')),
            credit_limit=credit_limit,
            opening_balance=opening,
            pending_balance=opening,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(dealer)
        db.session.flush()

        user = get_current_user()
        log_audit(user.id, 'create', 'dealer', dealer.id, after=dealer.to_dict())
        db.session.commit()
        return jsonify({'dealer': dealer.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@dealers_bp.route('/<int:dealer_id>', methods=['PUT'])
@admin_required
def update_dealer(dealer_id):
    try:
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404

        data = request.get_json()
        before = dealer.to_dict()
        old_opening = dealer.opening_balance

        if 'name' in data and data['name']:
            dealer.name = sanitize_string(data['name'])
        if 'phone' in data:
            dealer.phone = sanitize_string(data.get('phone'))
        if 'address' in data:
            dealer.address = sanitize_string(data.get('address'))
        if 'agency_id' in data:
            agency = Agency.query.get(data['agency_id'])
            if not agency:
                return jsonify({'error': 'Agency not found'}), 404
            dealer.agency_id = data['agency_id']
        if 'route_area' in data:
            dealer.route_area = sanitize_string(data.get('route_area'))
        if 'credit_limit' in data:
            if data['credit_limit'] is not None and data['credit_limit'] != '':
                dealer.credit_limit = Decimal(str(data['credit_limit']))
            else:
                dealer.credit_limit = None
        if 'opening_balance' in data:
            dealer.opening_balance = Decimal(str(data.get('opening_balance', 0) or 0))
        if 'is_active' in data:
            dealer.is_active = data.get('is_active')

        user = get_current_user()
        log_audit(user.id, 'update', 'dealer', dealer.id, before=before, after=dealer.to_dict())
        db.session.commit()

        if dealer.opening_balance != old_opening:
            recalculate_dealer_balance(dealer_id)
            dealer = Dealer.query.get(dealer_id)

        return jsonify({'dealer': dealer.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@dealers_bp.route('/<int:dealer_id>', methods=['DELETE'])
@admin_required
def delete_dealer(dealer_id):
    try:
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404

        before = dealer.to_dict()
        dealer.is_active = False

        user = get_current_user()
        log_audit(user.id, 'delete', 'dealer', dealer.id, before=before)
        db.session.commit()
        return jsonify({'message': 'Dealer deactivated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@dealers_bp.route('/<int:dealer_id>/statement', methods=['GET'])
@login_required_any
def get_statement(dealer_id):
    try:
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404

        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')

        from_date = None
        to_date = None
        if from_date_str:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        if to_date_str:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()

        delivery_query = db.session.query(
            DeliveryEntry.delivery_date,
            func.sum(DeliveryLineItem.line_amount).label('total_amount')
        ).join(
            DeliveryLineItem, DeliveryEntry.id == DeliveryLineItem.delivery_entry_id
        ).filter(
            DeliveryLineItem.dealer_id == dealer_id,
            DeliveryLineItem.is_non_billable == False
        )

        if from_date:
            delivery_query = delivery_query.filter(DeliveryEntry.delivery_date >= from_date)
        if to_date:
            delivery_query = delivery_query.filter(DeliveryEntry.delivery_date <= to_date)

        delivery_query = delivery_query.group_by(DeliveryEntry.delivery_date)
        delivery_results = delivery_query.all()

        payment_query = Payment.query.filter_by(dealer_id=dealer_id, is_deleted=False)
        if from_date:
            payment_query = payment_query.filter(Payment.payment_date >= datetime.combine(from_date, datetime.min.time()))
        if to_date:
            payment_query = payment_query.filter(Payment.payment_date <= datetime.combine(to_date, datetime.max.time()))
        payments = payment_query.order_by(Payment.payment_date).all()

        entries = []
        for del_date, total_amt in delivery_results:
            amt = float(total_amt) if total_amt else 0
            entries.append({
                'date': del_date.strftime('%d/%m/%Y'),
                'date_sort': del_date.isoformat(),
                'type': 'delivery',
                'description': f'Delivery on {del_date.strftime("%d/%m/%Y")}',
                'debit': amt,
                'credit': 0,
                'balance': 0
            })

        for payment in payments:
            pdate = payment.payment_date.date() if isinstance(payment.payment_date, datetime) else payment.payment_date
            entries.append({
                'date': pdate.strftime('%d/%m/%Y'),
                'date_sort': pdate.isoformat(),
                'type': 'payment',
                'description': f'Payment ({payment.payment_mode}){" - " + payment.remark if payment.remark else ""}',
                'debit': 0,
                'credit': float(payment.amount),
                'balance': 0
            })

        entries.sort(key=lambda x: x['date_sort'])

        opening = float(dealer.opening_balance) if dealer.opening_balance else 0
        running = opening
        total_billed = 0
        total_paid = 0

        for entry in entries:
            if entry['type'] == 'delivery':
                running += entry['debit']
                total_billed += entry['debit']
            else:
                running -= entry['credit']
                total_paid += entry['credit']
            entry['balance'] = round(running, 2)

        summary = {
            'opening_balance': opening,
            'total_billed': round(total_billed, 2),
            'total_paid': round(total_paid, 2),
            'closing_balance': round(running, 2)
        }

        return jsonify({
            'dealer': dealer.to_dict(),
            'statement': entries,
            'summary': summary
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dealers_bp.route('/<int:dealer_id>/recalculate', methods=['POST'])
@admin_required
def recalculate_balance(dealer_id):
    try:
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404

        before_balance = float(dealer.pending_balance) if dealer.pending_balance else 0
        dealer = recalculate_dealer_balance(dealer_id)

        user = get_current_user()
        log_audit(user.id, 'update', 'dealer_balance', dealer_id,
                  before={'pending_balance': before_balance},
                  after={'pending_balance': float(dealer.pending_balance)})

        return jsonify({
            'dealer': dealer.to_dict(),
            'message': 'Balance recalculated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@dealers_bp.route('/<int:dealer_id>/adjustment', methods=['POST'])
@admin_required
def create_adjustment(dealer_id):
    try:
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404

        data = request.get_json()
        errors = validate_required(data, ['amount', 'type', 'remark'])
        if errors:
            return jsonify({'error': errors[0]}), 400

        adj_type = data.get('type')
        if adj_type not in ('credit', 'debit'):
            return jsonify({'error': 'Type must be credit or debit'}), 400

        try:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                return jsonify({'error': 'Amount must be positive'}), 400
        except Exception:
            return jsonify({'error': 'Invalid amount'}), 400

        user = get_current_user()
        remark = sanitize_string(data.get('remark')) or 'Manual adjustment'

        if adj_type == 'credit':
            payment = Payment(
                dealer_id=dealer_id,
                amount=amount,
                payment_date=datetime.utcnow(),
                payment_mode='Cash',
                collected_by=user.id,
                remark=f'[ADJUSTMENT - Credit] {remark}',
                created_at=datetime.utcnow(),
                is_deleted=False
            )
            db.session.add(payment)
        else:
            payment = Payment(
                dealer_id=dealer_id,
                amount=-amount,
                payment_date=datetime.utcnow(),
                payment_mode='Cash',
                collected_by=user.id,
                remark=f'[ADJUSTMENT - Debit] {remark}',
                created_at=datetime.utcnow(),
                is_deleted=False
            )
            db.session.add(payment)

        db.session.flush()

        log_audit(user.id, 'create', 'adjustment', dealer_id,
                  after={'type': adj_type, 'amount': float(amount), 'remark': remark})
        db.session.commit()

        dealer = recalculate_dealer_balance(dealer_id)

        return jsonify({
            'message': f'Adjustment ({adj_type}) of ₹{float(amount)} applied',
            'dealer': dealer.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
