"""
Payment management routes for the Dairy Distribution Management System.
Handles payment CRUD with duplicate prevention, balance recalculation,
and comprehensive audit logging.
"""

from flask import Blueprint, request, jsonify
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_

from models import db
from models.payment import Payment
from models.dealer import Dealer
from utils.auth import admin_required, login_required_any, get_current_user
from utils.audit import log_audit
from utils.billing import recalculate_dealer_balance
from utils.validators import validate_required, sanitize_string

payments_bp = Blueprint('payments', __name__)

# Valid payment modes
VALID_PAYMENT_MODES = ['Cash', 'Online/UPI', 'Bank Transfer', 'Cheque']

# Duplicate prevention window (seconds)
DUPLICATE_WINDOW_SECONDS = 60


# ---------------------------------------------------------------------------
# GET /  –  Paginated payment listing with filters
# ---------------------------------------------------------------------------
@payments_bp.route('/', methods=['GET'])
@login_required_any
def get_payments():
    """
    Return a paginated, filtered list of payments.
    Supports filtering by dealer, agency, date range, mode, and collector.
    """
    try:
        # ------ Pagination params ------
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        per_page = min(per_page, 100)  # Cap at 100

        # ------ Build base query (exclude soft-deleted) ------
        query = Payment.query.filter(
            Payment.is_deleted == False  # noqa: E712
        )

        # ------ Apply filters ------
        dealer_id = request.args.get('dealer_id', type=int)
        agency_id = request.args.get('agency_id', type=int)
        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')
        payment_mode = request.args.get('payment_mode')
        collected_by = request.args.get('collected_by', type=int)

        if dealer_id:
            query = query.filter(Payment.dealer_id == dealer_id)

        if agency_id:
            # Join with Dealer to filter by agency
            query = query.join(Dealer, Payment.dealer_id == Dealer.id).filter(
                Dealer.agency_id == agency_id
            )

        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
                query = query.filter(Payment.payment_date >= from_date)
            except ValueError:
                return jsonify({'error': 'Invalid from_date format. Use YYYY-MM-DD'}), 400

        if to_date_str:
            try:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
                # Include the entire to_date day
                to_date_end = to_date + timedelta(days=1)
                query = query.filter(Payment.payment_date < to_date_end)
            except ValueError:
                return jsonify({'error': 'Invalid to_date format. Use YYYY-MM-DD'}), 400

        if payment_mode:
            query = query.filter(Payment.payment_mode == payment_mode)

        if collected_by:
            query = query.filter(Payment.collected_by == collected_by)

        # ------ Order and paginate ------
        query = query.order_by(Payment.payment_date.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        payments = [p.to_dict() for p in pagination.items]

        return jsonify({
            'payments': payments,
            'total': pagination.total,
            'page': pagination.page,
            'pages': pagination.pages
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch payments: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# POST /  –  Record a new payment
# ---------------------------------------------------------------------------
@payments_bp.route('/', methods=['POST'])
@login_required_any
def create_payment():
    """
    Record a new payment. Available to both admin and collector roles.
    Implements duplicate prevention within a 60-second window.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # ------ Validate required fields ------
        dealer_id = data.get('dealer_id')
        amount_raw = data.get('amount')
        payment_mode = data.get('payment_mode')
        remark = sanitize_string(data.get('remark', ''))
        payment_date_str = data.get('payment_date')

        if not dealer_id:
            return jsonify({'error': 'dealer_id is required'}), 400
        if amount_raw is None:
            return jsonify({'error': 'amount is required'}), 400
        if not payment_mode:
            return jsonify({'error': 'payment_mode is required'}), 400

        # Validate amount
        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, TypeError):
            return jsonify({'error': 'Invalid amount value'}), 400

        if amount <= 0:
            return jsonify({'error': 'Amount must be greater than 0'}), 400

        # Validate payment mode
        if payment_mode not in VALID_PAYMENT_MODES:
            return jsonify({
                'error': f'Invalid payment_mode. Must be one of: {", ".join(VALID_PAYMENT_MODES)}'
            }), 400

        # Validate dealer exists and is active
        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404
        if not dealer.is_active:
            return jsonify({'error': 'Dealer is not active'}), 400

        # Parse payment date (default to now)
        if payment_date_str:
            try:
                payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d')
            except ValueError:
                try:
                    payment_date = datetime.strptime(payment_date_str, '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    return jsonify({'error': 'Invalid payment_date format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS'}), 400
        else:
            payment_date = datetime.utcnow()

        # ------ Duplicate prevention ------
        duplicate_cutoff = datetime.utcnow() - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
        duplicate = Payment.query.filter(
            and_(
                Payment.dealer_id == dealer_id,
                Payment.amount == amount,
                Payment.payment_date == payment_date,
                Payment.created_at >= duplicate_cutoff,
                Payment.is_deleted == False  # noqa: E712
            )
        ).first()

        if duplicate:
            return jsonify({
                'error': 'Duplicate payment detected. A payment with the same dealer, amount, and date was recorded within the last 60 seconds.',
                'existing_payment_id': duplicate.id
            }), 409

        # ------ Create payment ------
        current_user = get_current_user()
        payment = Payment(
            dealer_id=dealer_id,
            amount=amount,
            payment_date=payment_date,
            payment_mode=payment_mode,
            collected_by=current_user.id,
            remark=remark,
            is_deleted=False
        )
        db.session.add(payment)
        db.session.commit()

        # ------ Recalculate dealer balance immediately ------
        recalculate_dealer_balance(dealer_id)

        # Refresh dealer to get updated pending_balance
        db.session.refresh(dealer)

        # ------ Audit log ------
        log_audit(
            current_user.id,
            'create',
            'payment',
            payment.id,
            after_value={
                'dealer_id': dealer_id,
                'amount': float(amount),
                'payment_mode': payment_mode,
                'payment_date': payment_date.isoformat(),
                'collected_by': current_user.id
            }
        )

        return jsonify({
            'payment': payment.to_dict(),
            'dealer': dealer.to_dict(),
            'message': 'Payment recorded'
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create payment: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# PUT /<id>  –  Update an existing payment (admin only)
# ---------------------------------------------------------------------------
@payments_bp.route('/<int:payment_id>', methods=['PUT'])
@admin_required
def update_payment(payment_id):
    """
    Update an existing payment. Admin only.
    Only amount, payment_mode, and remark can be modified.
    """
    try:
        # ------ Find payment (not deleted) ------
        payment = Payment.query.filter_by(
            id=payment_id,
            is_deleted=False
        ).first()

        if not payment:
            return jsonify({'error': 'Payment not found'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # ------ Store old values for audit ------
        old_values = {
            'amount': float(payment.amount) if payment.amount else 0,
            'payment_mode': payment.payment_mode,
            'remark': payment.remark
        }

        # ------ Update fields ------
        if 'amount' in data:
            try:
                new_amount = Decimal(str(data['amount']))
            except (InvalidOperation, TypeError):
                return jsonify({'error': 'Invalid amount value'}), 400

            if new_amount <= 0:
                return jsonify({'error': 'Amount must be greater than 0'}), 400
            payment.amount = new_amount

        if 'payment_mode' in data:
            if data['payment_mode'] not in VALID_PAYMENT_MODES:
                return jsonify({
                    'error': f'Invalid payment_mode. Must be one of: {", ".join(VALID_PAYMENT_MODES)}'
                }), 400
            payment.payment_mode = data['payment_mode']

        if 'remark' in data:
            payment.remark = sanitize_string(data['remark'])

        db.session.commit()

        # ------ Recalculate dealer balance ------
        recalculate_dealer_balance(payment.dealer_id)

        # Refresh dealer to get updated balance
        dealer = Dealer.query.get(payment.dealer_id)
        db.session.refresh(dealer)

        # ------ Capture new values for audit ------
        new_values = {
            'amount': float(payment.amount) if payment.amount else 0,
            'payment_mode': payment.payment_mode,
            'remark': payment.remark
        }

        log_audit(
            current_user.id,
            'update',
            'payment',
            payment.id,
            before_value={
                'dealer_id': payment.dealer_id,
                'before': old_values,
                'after': new_values
            }
        )

        return jsonify({
            'payment': payment.to_dict(),
            'dealer': dealer.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update payment: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# DELETE /<id>  –  Soft-delete a payment (admin only)
# ---------------------------------------------------------------------------
@payments_bp.route('/<int:payment_id>', methods=['DELETE'])
@admin_required
def delete_payment(payment_id):
    """Soft-delete a payment by setting is_deleted=True. Admin only."""
    try:
        payment = Payment.query.get(payment_id)
        if not payment:
            return jsonify({'error': 'Payment not found'}), 404

        if payment.is_deleted:
            return jsonify({'error': 'Payment is already deleted'}), 400

        # ------ Soft delete ------
        payment.is_deleted = True
        db.session.commit()

        # ------ Recalculate dealer balance ------
        recalculate_dealer_balance(payment.dealer_id)

        # ------ Audit log ------
        log_audit(
            current_user.id,
            'delete',
            'payment',
            payment.id,
            before_value={
                'dealer_id': payment.dealer_id,
                'amount': float(payment.amount) if payment.amount else 0,
                'payment_mode': payment.payment_mode,
                'payment_date': payment.payment_date.isoformat() if payment.payment_date else None
            }
        )

        return jsonify({'message': 'Payment deleted'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to delete payment: {str(e)}'}), 500
