"""
Delivery management routes for the Dairy Distribution Management System.
Handles delivery entry CRUD, finalization, and unlocking.
"""

from flask import Blueprint, request, jsonify
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_

from models import db
from models.delivery import DeliveryEntry, DeliveryLineItem
from models.dealer import Dealer
from models.product import Product
from utils.auth import admin_required, login_required_any, get_current_user
from utils.audit import log_audit
from utils.billing import recalculate_dealer_balance, get_active_price, calculate_line_amount
from utils.validators import validate_required, sanitize_string

deliveries_bp = Blueprint('deliveries', __name__)


# ---------------------------------------------------------------------------
# GET /  –  Delivery grid for a given agency + date
# ---------------------------------------------------------------------------
@deliveries_bp.route('/', methods=['GET'])
@admin_required
def get_delivery_grid():
    """
    Return the delivery grid for a specific agency and date.
    Builds a dealer × product matrix with quantities, amounts, and totals.
    """
    try:
        # ------ Validate required query params ------
        agency_id = request.args.get('agency_id')
        date_str = request.args.get('date')

        if not agency_id or not date_str:
            return jsonify({'error': 'agency_id and date are required'}), 400

        try:
            agency_id = int(agency_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid agency_id'}), 400

        try:
            delivery_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        # ------ Fetch core data ------
        entry = DeliveryEntry.query.filter_by(
            agency_id=agency_id,
            delivery_date=delivery_date
        ).first()

        # All active dealers for this agency, ordered by name
        dealers = (
            Dealer.query
            .filter_by(agency_id=agency_id, is_active=True)
            .order_by(Dealer.name)
            .all()
        )

        # All active products ordered by display_order
        products = (
            Product.query
            .filter_by(is_active=True)
            .order_by(Product.display_order)
            .all()
        )

        # Build lookup for existing line items: (dealer_id, product_id) -> item
        line_item_map = {}
        if entry:
            line_items = DeliveryLineItem.query.filter_by(
                delivery_entry_id=entry.id
            ).all()
            for item in line_items:
                line_item_map[(item.dealer_id, item.product_id)] = item

        # ------ Build the grid ------
        dealer_rows = []
        product_totals = {p.id: Decimal('0') for p in products}
        bill_total = Decimal('0')

        for dealer in dealers:
            items = []
            day_total = Decimal('0')

            for product in products:
                key = (dealer.id, product.id)
                li = line_item_map.get(key)

                if li:
                    quantity = float(li.quantity) if li.quantity is not None else 0
                    unit_price = float(li.unit_price) if li.unit_price is not None else 0
                    line_amount = float(li.line_amount) if li.line_amount is not None else 0
                    is_non_billable = li.is_non_billable or False
                    remark = li.remark or ''

                    product_totals[product.id] += (li.quantity or Decimal('0'))
                    if not is_non_billable:
                        day_total += (li.line_amount or Decimal('0'))
                else:
                    quantity = 0
                    unit_price = 0
                    line_amount = 0
                    is_non_billable = False
                    remark = ''

                items.append({
                    'product_id': product.id,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'line_amount': line_amount,
                    'is_non_billable': is_non_billable,
                    'remark': remark
                })

            bill_total += day_total
            dealer_rows.append({
                'id': dealer.id,
                'name': dealer.name,
                'items': items,
                'day_total': float(day_total)
            })

        # ------ Build product list for response ------
        product_list = []
        for p in products:
            current_price_obj = p.get_current_price()
            current_price = float(current_price_obj.price_per_unit) if current_price_obj else None
            product_list.append({
                'id': p.id,
                'name': p.name,
                'pack_size': p.pack_size,
                'outer_unit': p.outer_unit,
                'current_price': current_price
            })

        # ------ Totals row ------
        totals = {
            'products': {str(pid): float(qty) for pid, qty in product_totals.items()},
            'bill_total': float(bill_total)
        }

        return jsonify({
            'entry': entry.to_dict() if entry else None,
            'dealers': dealer_rows,
            'products': product_list,
            'totals': totals
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch delivery grid: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# POST /  –  Create a new delivery entry
# ---------------------------------------------------------------------------
@deliveries_bp.route('/', methods=['POST'])
@admin_required
def create_delivery_entry():
    """
    Create a new delivery entry with line items.
    Snapshots current product prices and recalculates dealer balances.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # ------ Validate inputs ------
        agency_id = data.get('agency_id')
        date_str = data.get('delivery_date')
        line_items_data = data.get('line_items', [])

        if not agency_id:
            return jsonify({'error': 'agency_id is required'}), 400
        if not date_str:
            return jsonify({'error': 'delivery_date is required'}), 400

        try:
            agency_id = int(agency_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid agency_id'}), 400

        try:
            delivery_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid delivery_date format. Use YYYY-MM-DD'}), 400

        # ------ Prevent duplicate entries ------
        existing = DeliveryEntry.query.filter_by(
            agency_id=agency_id,
            delivery_date=delivery_date
        ).first()
        if existing:
            return jsonify({
                'error': 'A delivery entry already exists for this agency and date',
                'existing_entry_id': existing.id
            }), 409

        # ------ Create entry ------
        current_user = get_current_user()
        entry = DeliveryEntry(
            agency_id=agency_id,
            delivery_date=delivery_date,
            status='open',
            created_by=current_user.id
        )
        db.session.add(entry)
        db.session.flush()  # Get entry.id before adding line items

        # ------ Create line items ------
        affected_dealer_ids = set()
        delivery_date_dt = delivery_date

        for item_data in line_items_data:
            quantity_raw = item_data.get('quantity', 0)

            try:
                quantity = Decimal(str(quantity_raw))
            except (InvalidOperation, TypeError):
                return jsonify({'error': f'Invalid quantity value: {quantity_raw}'}), 400

            if quantity <= 0:
                continue  # Skip zero/negative quantities

            product_id = item_data.get('product_id')
            dealer_id = item_data.get('dealer_id')
            is_non_billable = bool(item_data.get('is_non_billable', False))
            remark = sanitize_string(item_data.get('remark', ''))

            if not product_id or not dealer_id:
                return jsonify({'error': 'Each line item requires product_id and dealer_id'}), 400

            # Get active price at the delivery date
            price = get_active_price(product_id, delivery_date_dt)
            if not price:
                product = Product.query.get(product_id)
                product_name = product.name if product else f'ID {product_id}'
                return jsonify({
                    'error': f'No active price found for product "{product_name}" on {date_str}'
                }), 400

            unit_price = price.price_per_unit
            line_amount = calculate_line_amount(quantity, unit_price)

            if is_non_billable:
                line_amount = Decimal('0')

            line_item = DeliveryLineItem(
                delivery_entry_id=entry.id,
                dealer_id=dealer_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
                line_amount=line_amount,
                is_non_billable=is_non_billable,
                remark=remark
            )
            db.session.add(line_item)
            affected_dealer_ids.add(dealer_id)

        db.session.commit()

        # ------ Recalculate balances for affected dealers ------
        for dealer_id in affected_dealer_ids:
            recalculate_dealer_balance(dealer_id)

        # ------ Audit log ------
        log_audit(
            current_user.id,
            'create',
            'delivery_entry',
            entry.id,
            after_value={
                'agency_id': agency_id,
                'delivery_date': date_str,
                'line_item_count': len(affected_dealer_ids),
                'status': 'open'
            }
        )

        return jsonify({
            'entry': entry.to_dict(),
            'message': 'Delivery entry saved'
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to create delivery entry: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# PUT /<id>  –  Update an existing delivery entry
# ---------------------------------------------------------------------------
@deliveries_bp.route('/<int:entry_id>', methods=['PUT'])
@admin_required
def update_delivery_entry(entry_id):
    """
    Update an existing delivery entry by replacing all line items.
    Only allowed if entry is not finalized.
    """
    try:
        # ------ Find entry ------
        entry = DeliveryEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Delivery entry not found'}), 404

        if entry.status == 'finalized':
            return jsonify({'error': 'Entry is finalized'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        line_items_data = data.get('line_items', [])

        # ------ Capture old line items for audit ------
        old_line_items = DeliveryLineItem.query.filter_by(
            delivery_entry_id=entry.id
        ).all()

        old_dealer_ids = {li.dealer_id for li in old_line_items}
        old_audit_data = [
            {
                'dealer_id': li.dealer_id,
                'product_id': li.product_id,
                'quantity': float(li.quantity) if li.quantity else 0,
                'unit_price': float(li.unit_price) if li.unit_price else 0,
                'line_amount': float(li.line_amount) if li.line_amount else 0,
                'is_non_billable': li.is_non_billable
            }
            for li in old_line_items
        ]

        # ------ Delete existing line items ------
        DeliveryLineItem.query.filter_by(delivery_entry_id=entry.id).delete()

        # ------ Re-create line items with new data ------
        new_dealer_ids = set()
        delivery_date_dt = entry.delivery_date
        new_audit_data = []

        for item_data in line_items_data:
            quantity_raw = item_data.get('quantity', 0)

            try:
                quantity = Decimal(str(quantity_raw))
            except (InvalidOperation, TypeError):
                db.session.rollback()
                return jsonify({'error': f'Invalid quantity value: {quantity_raw}'}), 400

            if quantity <= 0:
                continue

            product_id = item_data.get('product_id')
            dealer_id = item_data.get('dealer_id')
            is_non_billable = bool(item_data.get('is_non_billable', False))
            remark = sanitize_string(item_data.get('remark', ''))

            if not product_id or not dealer_id:
                db.session.rollback()
                return jsonify({'error': 'Each line item requires product_id and dealer_id'}), 400

            # Get active price at the delivery date
            price = get_active_price(product_id, delivery_date_dt)
            if not price:
                db.session.rollback()
                product = Product.query.get(product_id)
                product_name = product.name if product else f'ID {product_id}'
                return jsonify({
                    'error': f'No active price found for product "{product_name}" on {entry.delivery_date.isoformat()}'
                }), 400

            unit_price = price.price_per_unit
            line_amount = calculate_line_amount(quantity, unit_price)

            if is_non_billable:
                line_amount = Decimal('0')

            line_item = DeliveryLineItem(
                delivery_entry_id=entry.id,
                dealer_id=dealer_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
                line_amount=line_amount,
                is_non_billable=is_non_billable,
                remark=remark
            )
            db.session.add(line_item)
            new_dealer_ids.add(dealer_id)
            new_audit_data.append({
                'dealer_id': dealer_id,
                'product_id': product_id,
                'quantity': float(quantity),
                'unit_price': float(unit_price),
                'line_amount': float(line_amount),
                'is_non_billable': is_non_billable
            })

        # Update the entry's updated_at timestamp
        entry.updated_at = datetime.utcnow()
        db.session.commit()

        # ------ Recalculate balances for ALL affected dealers (old + new) ------
        all_affected_dealers = old_dealer_ids | new_dealer_ids
        for dealer_id in all_affected_dealers:
            recalculate_dealer_balance(dealer_id)

        # ------ Audit log ------
        current_user = get_current_user()
        log_audit(
            current_user.id,
            'update',
            'delivery_entry',
            entry.id,
            before_value={
                'agency_id': entry.agency_id,
                'delivery_date': entry.delivery_date.isoformat(),
                'before': old_audit_data,
                'after': new_audit_data
            }
        )

        return jsonify({
            'entry': entry.to_dict(),
            'message': 'Delivery entry updated'
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to update delivery entry: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# POST /<id>/finalize  –  Lock an entry
# ---------------------------------------------------------------------------
@deliveries_bp.route('/<int:entry_id>/finalize', methods=['POST'])
@admin_required
def finalize_delivery_entry(entry_id):
    """Finalize (lock) a delivery entry to prevent further edits."""
    try:
        entry = DeliveryEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Delivery entry not found'}), 404

        if entry.status == 'finalized':
            return jsonify({'error': 'Entry is already finalized'}), 400

        entry.status = 'finalized'
        entry.updated_at = datetime.utcnow()
        db.session.commit()

        current_user = get_current_user()
        log_audit(
            current_user.id,
            'update',
            'delivery_entry',
            entry.id,
            after_value={
                'agency_id': entry.agency_id,
                'delivery_date': entry.delivery_date.isoformat(),
                'status': 'finalized'
            }
        )

        return jsonify({'entry': entry.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to finalize delivery entry: {str(e)}'}), 500


# ---------------------------------------------------------------------------
# POST /<id>/unlock  –  Re-open a finalized entry
# ---------------------------------------------------------------------------
@deliveries_bp.route('/<int:entry_id>/unlock', methods=['POST'])
@admin_required
def unlock_delivery_entry(entry_id):
    """Unlock a finalized delivery entry to allow edits."""
    try:
        entry = DeliveryEntry.query.get(entry_id)
        if not entry:
            return jsonify({'error': 'Delivery entry not found'}), 404

        if entry.status == 'open':
            return jsonify({'error': 'Entry is already open'}), 400

        entry.status = 'open'
        entry.updated_at = datetime.utcnow()
        db.session.commit()

        current_user = get_current_user()
        log_audit(
            current_user.id,
            'update',
            'delivery_entry',
            entry.id,
            after_value={
                'agency_id': entry.agency_id,
                'delivery_date': entry.delivery_date.isoformat(),
                'status': 'open'
            }
        )

        return jsonify({'entry': entry.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to unlock delivery entry: {str(e)}'}), 500
