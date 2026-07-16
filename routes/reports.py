"""
Reporting routes for the Dairy Distribution Management System.
Provides dashboard statistics, daily sheets, dealer statements,
outstanding reports, product sales analytics, payment collection
summaries, and export functionality (PDF / Excel).
"""

from flask import Blueprint, request, jsonify, send_file
from decimal import Decimal
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_

from models import db
from models.agency import Agency
from models.dealer import Dealer
from models.product import Product
from models.delivery import DeliveryEntry, DeliveryLineItem
from models.payment import Payment
from utils.auth import login_required_any
from utils.export import generate_pdf, generate_excel

reports_bp = Blueprint('reports', __name__)


# ===========================================================================
# Helper: safe decimal
# ===========================================================================
def _safe_decimal(value):
    """Convert a value to Decimal, defaulting to 0 if None."""
    if value is None:
        return Decimal('0')
    return Decimal(str(value))


def _parse_date(date_str, param_name='date'):
    """Parse a YYYY-MM-DD string to a date object, or raise ValueError."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'Invalid {param_name} format. Use YYYY-MM-DD')


# ===========================================================================
# GET /dashboard  –  Dashboard statistics
# ===========================================================================
@reports_bp.route('/dashboard', methods=['GET'])
@login_required_any
def get_dashboard():
    """Return comprehensive dashboard statistics."""
    try:
        today = date.today()
        month_start = today.replace(day=1)

        today_start_dt = datetime.combine(today, datetime.min.time())
        today_end_dt = datetime.combine(today + timedelta(days=1), datetime.min.time())
        month_start_dt = datetime.combine(month_start, datetime.min.time())

        # ------ Today's billed amount ------
        today_billed = db.session.query(
            func.sum(DeliveryLineItem.line_amount)
        ).join(
            DeliveryEntry, DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
        ).filter(
            and_(
                DeliveryEntry.delivery_date == today,
                DeliveryLineItem.is_non_billable == False  # noqa: E712
            )
        ).scalar()
        today_billed = _safe_decimal(today_billed)

        # ------ Today's collected amount ------
        today_collected = db.session.query(
            func.sum(Payment.amount)
        ).filter(
            and_(
                Payment.payment_date >= today_start_dt,
                Payment.payment_date < today_end_dt,
                Payment.is_deleted == False  # noqa: E712
            )
        ).scalar()
        today_collected = _safe_decimal(today_collected)

        today_pending = today_billed - today_collected

        # ------ Month billed ------
        month_billed = db.session.query(
            func.sum(DeliveryLineItem.line_amount)
        ).join(
            DeliveryEntry, DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
        ).filter(
            and_(
                DeliveryEntry.delivery_date >= month_start,
                DeliveryEntry.delivery_date <= today,
                DeliveryLineItem.is_non_billable == False  # noqa: E712
            )
        ).scalar()
        month_billed = _safe_decimal(month_billed)

        # ------ Month collected ------
        month_collected = db.session.query(
            func.sum(Payment.amount)
        ).filter(
            and_(
                Payment.payment_date >= month_start_dt,
                Payment.payment_date < today_end_dt,
                Payment.is_deleted == False  # noqa: E712
            )
        ).scalar()
        month_collected = _safe_decimal(month_collected)

        month_pending = month_billed - month_collected

        # ------ Total outstanding (sum of all active dealer balances) ------
        total_outstanding = db.session.query(
            func.sum(Dealer.pending_balance)
        ).filter(
            Dealer.is_active == True  # noqa: E712
        ).scalar()
        total_outstanding = _safe_decimal(total_outstanding)

        # ------ Per-agency breakdown ------
        agencies = Agency.query.filter_by(is_active=True).all()
        per_agency = []

        for agency in agencies:
            agency_dealer_ids = [
                d.id for d in
                Dealer.query.filter_by(agency_id=agency.id, is_active=True).all()
            ]

            if agency_dealer_ids:
                ag_today_billed = db.session.query(
                    func.sum(DeliveryLineItem.line_amount)
                ).join(
                    DeliveryEntry,
                    DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
                ).filter(
                    and_(
                        DeliveryEntry.delivery_date == today,
                        DeliveryLineItem.is_non_billable == False,  # noqa: E712
                        DeliveryLineItem.dealer_id.in_(agency_dealer_ids)
                    )
                ).scalar()
                ag_today_billed = _safe_decimal(ag_today_billed)

                ag_today_collected = db.session.query(
                    func.sum(Payment.amount)
                ).filter(
                    and_(
                        Payment.payment_date >= today_start_dt,
                        Payment.payment_date < today_end_dt,
                        Payment.is_deleted == False,  # noqa: E712
                        Payment.dealer_id.in_(agency_dealer_ids)
                    )
                ).scalar()
                ag_today_collected = _safe_decimal(ag_today_collected)
            else:
                ag_today_billed = Decimal('0')
                ag_today_collected = Decimal('0')

            per_agency.append({
                'id': agency.id,
                'name': agency.name,
                'today_billed': float(ag_today_billed),
                'today_collected': float(ag_today_collected),
                'dealer_count': len(agency_dealer_ids)
            })

        # ------ Top 10 pending dealers ------
        top_pending_dealers_q = (
            Dealer.query
            .filter(
                and_(
                    Dealer.is_active == True,  # noqa: E712
                    Dealer.pending_balance > 0
                )
            )
            .order_by(Dealer.pending_balance.desc())
            .limit(10)
            .all()
        )
        top_pending_dealers = []
        for d in top_pending_dealers_q:
            agency_name = d.agency.name if d.agency else 'N/A'
            top_pending_dealers.append({
                'id': d.id,
                'name': d.name,
                'agency_name': agency_name,
                'pending_balance': float(d.pending_balance or 0)
            })

        # ------ Counts ------
        total_dealers = Dealer.query.filter_by(is_active=True).count()
        total_products = Product.query.filter_by(is_active=True).count()

        return jsonify({
            'dashboard': {
                'today_billed': float(today_billed),
                'today_collected': float(today_collected),
                'today_pending': float(today_pending),
                'month_billed': float(month_billed),
                'month_collected': float(month_collected),
                'month_pending': float(month_pending),
                'total_outstanding': float(total_outstanding),
                'per_agency': per_agency,
                'top_pending_dealers': top_pending_dealers,
                'total_dealers': total_dealers,
                'total_products': total_products
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch dashboard: {str(e)}'}), 500


# ===========================================================================
# GET /daily-sheet  –  Paper ledger reproduction
# ===========================================================================
@reports_bp.route('/daily-sheet', methods=['GET'])
@login_required_any
def get_daily_sheet():
    """
    Reproduce the exact paper ledger grid for an agency on a given date.
    Includes ALL active dealers even if they have no deliveries that day.
    """
    try:
        agency_id = request.args.get('agency_id', type=int)
        date_str = request.args.get('date')

        if not agency_id or not date_str:
            return jsonify({'error': 'agency_id and date are required'}), 400

        try:
            report_date = _parse_date(date_str, 'date')
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400

        # Fetch agency
        agency = Agency.query.get(agency_id)
        if not agency:
            return jsonify({'error': 'Agency not found'}), 404

        # All active dealers for this agency
        dealers = (
            Dealer.query
            .filter_by(agency_id=agency_id, is_active=True)
            .order_by(Dealer.name)
            .all()
        )

        # All active products
        products = (
            Product.query
            .filter_by(is_active=True)
            .order_by(Product.display_order)
            .all()
        )

        # Find delivery entry
        entry = DeliveryEntry.query.filter_by(
            agency_id=agency_id,
            delivery_date=report_date
        ).first()

        # Build line item lookup
        line_item_map = {}
        if entry:
            items = DeliveryLineItem.query.filter_by(
                delivery_entry_id=entry.id
            ).all()
            for item in items:
                line_item_map[(item.dealer_id, item.product_id)] = item

        # Build grid
        dealer_rows = []
        product_totals = {p.id: Decimal('0') for p in products}
        bill_total = Decimal('0')
        paid_total = Decimal('0')
        pending_total = Decimal('0')

        for dealer in dealers:
            product_data = {}
            day_bill = Decimal('0')

            for product in products:
                key = (dealer.id, product.id)
                li = line_item_map.get(key)

                if li:
                    qty = _safe_decimal(li.quantity)
                    amt = _safe_decimal(li.line_amount) if not li.is_non_billable else Decimal('0')
                    product_totals[product.id] += qty
                    day_bill += amt if not li.is_non_billable else Decimal('0')
                else:
                    qty = Decimal('0')
                    amt = Decimal('0')

                product_data[str(product.id)] = {
                    'qty': float(qty),
                    'amount': float(amt)
                }

            # All-time total paid for this dealer
            total_paid_q = db.session.query(
                func.sum(Payment.amount)
            ).filter(
                and_(
                    Payment.dealer_id == dealer.id,
                    Payment.is_deleted == False  # noqa: E712
                )
            ).scalar()
            total_paid = _safe_decimal(total_paid_q)

            pending_balance = _safe_decimal(dealer.pending_balance)

            bill_total += day_bill
            paid_total += total_paid
            pending_total += pending_balance

            dealer_rows.append({
                'id': dealer.id,
                'name': dealer.name,
                'products': product_data,
                'day_bill': float(day_bill),
                'total_paid': float(total_paid),
                'pending_balance': float(pending_balance)
            })

        # Product list for the response
        product_list = []
        for p in products:
            current_price_obj = p.get_current_price()
            product_list.append({
                'id': p.id,
                'name': p.name,
                'pack_size': p.pack_size,
                'current_price': float(current_price_obj.price_per_unit) if current_price_obj else None
            })

        totals = {
            'products': {str(pid): float(qty) for pid, qty in product_totals.items()},
            'bill_total': float(bill_total),
            'paid_total': float(paid_total),
            'pending_total': float(pending_total)
        }

        return jsonify({
            'date': report_date.isoformat(),
            'agency': {'id': agency.id, 'name': agency.name},
            'dealers': dealer_rows,
            'products': product_list,
            'totals': totals
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch daily sheet: {str(e)}'}), 500


# ===========================================================================
# GET /dealer-statement  –  Chronological ledger statement
# ===========================================================================
@reports_bp.route('/dealer-statement', methods=['GET'])
@login_required_any
def get_dealer_statement():
    """
    Return a chronological statement for a dealer with running balance.
    Merges deliveries and payments, sorted by date.
    """
    try:
        dealer_id = request.args.get('dealer_id', type=int)
        if not dealer_id:
            return jsonify({'error': 'dealer_id is required'}), 400

        dealer = Dealer.query.get(dealer_id)
        if not dealer:
            return jsonify({'error': 'Dealer not found'}), 404

        # Date range
        try:
            from_date = _parse_date(request.args.get('from_date'), 'from_date')
            to_date = _parse_date(request.args.get('to_date'), 'to_date')
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400

        # ------ Get deliveries in range ------
        delivery_query = db.session.query(
            DeliveryEntry.delivery_date,
            func.sum(DeliveryLineItem.line_amount).label('total_billed')
        ).join(
            DeliveryLineItem,
            DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
        ).filter(
            and_(
                DeliveryLineItem.dealer_id == dealer_id,
                DeliveryLineItem.is_non_billable == False  # noqa: E712
            )
        )

        if from_date:
            delivery_query = delivery_query.filter(DeliveryEntry.delivery_date >= from_date)
        if to_date:
            delivery_query = delivery_query.filter(DeliveryEntry.delivery_date <= to_date)

        delivery_rows = delivery_query.group_by(
            DeliveryEntry.delivery_date
        ).order_by(
            DeliveryEntry.delivery_date
        ).all()

        # ------ Get payments in range ------
        payment_query = Payment.query.filter(
            and_(
                Payment.dealer_id == dealer_id,
                Payment.is_deleted == False  # noqa: E712
            )
        )

        if from_date:
            from_date_dt = datetime.combine(from_date, datetime.min.time())
            payment_query = payment_query.filter(Payment.payment_date >= from_date_dt)
        if to_date:
            to_date_dt = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
            payment_query = payment_query.filter(Payment.payment_date < to_date_dt)

        payment_rows = payment_query.order_by(Payment.payment_date).all()

        # ------ Merge and sort chronologically ------
        entries = []

        for row in delivery_rows:
            entries.append({
                'date': row.delivery_date.isoformat(),
                'sort_key': datetime.combine(row.delivery_date, datetime.min.time()),
                'type': 'delivery',
                'description': f'Delivery on {row.delivery_date.strftime("%d %b %Y")}',
                'debit': float(_safe_decimal(row.total_billed)),
                'credit': 0.0
            })

        for payment in payment_rows:
            payment_dt = payment.payment_date
            entries.append({
                'date': payment_dt.strftime('%Y-%m-%d'),
                'sort_key': payment_dt,
                'type': 'payment',
                'description': f'Payment ({payment.payment_mode}){" - " + payment.remark if payment.remark else ""}',
                'debit': 0.0,
                'credit': float(_safe_decimal(payment.amount))
            })

        # Sort chronologically
        entries.sort(key=lambda x: x['sort_key'])

        # ------ Calculate running balance ------
        opening_balance = _safe_decimal(dealer.opening_balance)
        running_balance = float(opening_balance)
        total_billed = 0.0
        total_paid = 0.0

        statement = []
        for entry in entries:
            running_balance += entry['debit'] - entry['credit']
            total_billed += entry['debit']
            total_paid += entry['credit']

            statement.append({
                'date': entry['date'],
                'type': entry['type'],
                'description': entry['description'],
                'debit': entry['debit'],
                'credit': entry['credit'],
                'balance': round(running_balance, 2)
            })

        closing_balance = round(running_balance, 2)

        return jsonify({
            'dealer': dealer.to_dict(),
            'statement': statement,
            'summary': {
                'opening_balance': float(opening_balance),
                'total_billed': round(total_billed, 2),
                'total_paid': round(total_paid, 2),
                'closing_balance': closing_balance
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch dealer statement: {str(e)}'}), 500


# ===========================================================================
# GET /outstanding  –  Dealers with pending balances
# ===========================================================================
@reports_bp.route('/outstanding', methods=['GET'])
@login_required_any
def get_outstanding():
    """Return all dealers with positive pending balance, sorted descending."""
    try:
        agency_id = request.args.get('agency_id', type=int)
        min_amount_str = request.args.get('min_amount')

        min_amount = Decimal('0')
        if min_amount_str:
            try:
                min_amount = Decimal(str(min_amount_str))
            except Exception:
                return jsonify({'error': 'Invalid min_amount value'}), 400

        query = Dealer.query.filter(
            and_(
                Dealer.is_active == True,  # noqa: E712
                Dealer.pending_balance > min_amount
            )
        )

        if agency_id:
            query = query.filter(Dealer.agency_id == agency_id)

        query = query.order_by(Dealer.pending_balance.desc())
        dealers = query.all()

        total_outstanding = Decimal('0')
        dealer_list = []

        for d in dealers:
            balance = _safe_decimal(d.pending_balance)
            total_outstanding += balance

            # Determine if over credit limit
            credit_limit = _safe_decimal(getattr(d, 'credit_limit', None) or 0)
            over_credit = bool(credit_limit > 0 and balance > credit_limit)

            agency_name = d.agency.name if d.agency else 'N/A'
            phone = getattr(d, 'phone', '') or ''

            dealer_list.append({
                'id': d.id,
                'name': d.name,
                'agency_name': agency_name,
                'phone': phone,
                'pending_balance': float(balance),
                'credit_limit': float(credit_limit),
                'over_credit_limit': over_credit
            })

        return jsonify({
            'dealers': dealer_list,
            'total_outstanding': float(total_outstanding)
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch outstanding report: {str(e)}'}), 500


# ===========================================================================
# GET /product-sales  –  Product sales analytics
# ===========================================================================
@reports_bp.route('/product-sales', methods=['GET'])
@login_required_any
def get_product_sales():
    """
    Sum total quantity and revenue for each active product in a date range.
    """
    try:
        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')

        if not from_date_str or not to_date_str:
            return jsonify({'error': 'from_date and to_date are required'}), 400

        try:
            from_date = _parse_date(from_date_str, 'from_date')
            to_date = _parse_date(to_date_str, 'to_date')
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400

        # Number of days in period
        days_in_period = max((to_date - from_date).days + 1, 1)

        products = Product.query.filter_by(is_active=True).order_by(Product.display_order).all()

        product_list = []
        for product in products:
            # Sum quantity and revenue for this product in the date range
            result = db.session.query(
                func.sum(DeliveryLineItem.quantity).label('total_qty'),
                func.sum(DeliveryLineItem.line_amount).label('total_revenue')
            ).join(
                DeliveryEntry,
                DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
            ).filter(
                and_(
                    DeliveryLineItem.product_id == product.id,
                    DeliveryEntry.delivery_date >= from_date,
                    DeliveryEntry.delivery_date <= to_date
                )
            ).first()

            total_qty = _safe_decimal(result.total_qty if result else None)
            total_revenue = _safe_decimal(result.total_revenue if result else None)
            avg_daily = total_qty / Decimal(str(days_in_period))

            product_list.append({
                'id': product.id,
                'name': product.name,
                'pack_size': product.pack_size,
                'total_quantity': float(total_qty),
                'total_revenue': float(total_revenue),
                'avg_daily_quantity': float(avg_daily.quantize(Decimal('0.001')))
            })

        return jsonify({
            'products': product_list,
            'period': {
                'from': from_date.isoformat(),
                'to': to_date.isoformat(),
                'days': days_in_period
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch product sales: {str(e)}'}), 500


# ===========================================================================
# GET /payment-collection  –  Payment collection summary
# ===========================================================================
@reports_bp.route('/payment-collection', methods=['GET'])
@login_required_any
def get_payment_collection():
    """Return filtered payment list with summary breakdown by mode."""
    try:
        # Build query
        query = Payment.query.filter(Payment.is_deleted == False)  # noqa: E712

        from_date_str = request.args.get('from_date')
        to_date_str = request.args.get('to_date')
        agency_id = request.args.get('agency_id', type=int)
        dealer_id = request.args.get('dealer_id', type=int)
        collected_by = request.args.get('collected_by', type=int)

        if from_date_str:
            try:
                from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
                query = query.filter(Payment.payment_date >= from_date)
            except ValueError:
                return jsonify({'error': 'Invalid from_date format. Use YYYY-MM-DD'}), 400

        if to_date_str:
            try:
                to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
                to_date_end = to_date + timedelta(days=1)
                query = query.filter(Payment.payment_date < to_date_end)
            except ValueError:
                return jsonify({'error': 'Invalid to_date format. Use YYYY-MM-DD'}), 400

        if agency_id:
            query = query.join(Dealer, Payment.dealer_id == Dealer.id).filter(
                Dealer.agency_id == agency_id
            )

        if dealer_id:
            query = query.filter(Payment.dealer_id == dealer_id)

        if collected_by:
            query = query.filter(Payment.collected_by == collected_by)

        query = query.order_by(Payment.payment_date.desc())
        payments = query.all()

        # Build summary
        total_amount = Decimal('0')
        by_mode = {}

        for p in payments:
            amt = _safe_decimal(p.amount)
            total_amount += amt
            mode = p.payment_mode or 'Unknown'
            by_mode[mode] = float(_safe_decimal(by_mode.get(mode)) + amt)

        return jsonify({
            'payments': [p.to_dict() for p in payments],
            'summary': {
                'total_amount': float(total_amount),
                'count': len(payments),
                'by_mode': by_mode
            }
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to fetch payment collection: {str(e)}'}), 500


# ===========================================================================
# GET /export/<report_type>  –  Export reports as PDF or Excel
# ===========================================================================
@reports_bp.route('/export/<report_type>', methods=['GET'])
@login_required_any
def export_report(report_type):
    """
    Export any report as PDF or Excel.
    Supported: daily-sheet, dealer-statement, outstanding, product-sales, payment-collection.
    """
    try:
        export_format = request.args.get('format', 'pdf').lower()
        if export_format not in ('pdf', 'excel'):
            return jsonify({'error': 'format must be "pdf" or "excel"'}), 400

        # Dispatch to the correct builder
        builders = {
            'daily-sheet': _build_daily_sheet_export,
            'dealer-statement': _build_dealer_statement_export,
            'outstanding': _build_outstanding_export,
            'product-sales': _build_product_sales_export,
            'payment-collection': _build_payment_collection_export,
        }

        builder = builders.get(report_type)
        if not builder:
            return jsonify({
                'error': f'Unknown report type: {report_type}. '
                         f'Supported: {", ".join(builders.keys())}'
            }), 400

        title, headers, rows, filename = builder(request.args)

        # Generate the file
        if export_format == 'pdf':
            file_io = generate_pdf(title, headers, rows, filename)
            mimetype = 'application/pdf'
            download_name = f'{filename}.pdf'
        else:
            file_io = generate_excel(title, headers, rows, filename)
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            download_name = f'{filename}.xlsx'

        file_io.seek(0)
        return send_file(
            file_io,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to export report: {str(e)}'}), 500


# ===========================================================================
# Export builders – Each returns (title, headers, rows, filename)
# ===========================================================================

def _build_daily_sheet_export(args):
    """Build export data for the daily sheet report."""
    agency_id = args.get('agency_id', type=int)
    date_str = args.get('date')

    if not agency_id or not date_str:
        raise ValueError('agency_id and date are required')

    report_date = _parse_date(date_str, 'date')
    agency = Agency.query.get(agency_id)
    if not agency:
        raise ValueError('Agency not found')

    dealers = (
        Dealer.query
        .filter_by(agency_id=agency_id, is_active=True)
        .order_by(Dealer.name)
        .all()
    )
    products = (
        Product.query
        .filter_by(is_active=True)
        .order_by(Product.display_order)
        .all()
    )

    entry = DeliveryEntry.query.filter_by(
        agency_id=agency_id,
        delivery_date=report_date
    ).first()

    line_item_map = {}
    if entry:
        for item in DeliveryLineItem.query.filter_by(delivery_entry_id=entry.id).all():
            line_item_map[(item.dealer_id, item.product_id)] = item

    # Build headers
    headers = ['Dealer'] + [p.name for p in products] + ['Day Bill', 'Total Paid', 'Balance']

    # Build rows
    rows = []
    product_totals = {p.id: Decimal('0') for p in products}
    bill_total = Decimal('0')
    paid_total = Decimal('0')
    pending_total = Decimal('0')

    for dealer in dealers:
        row = [dealer.name]
        day_bill = Decimal('0')

        for product in products:
            li = line_item_map.get((dealer.id, product.id))
            qty = _safe_decimal(li.quantity) if li else Decimal('0')
            row.append(float(qty))
            product_totals[product.id] += qty
            if li and not li.is_non_billable:
                day_bill += _safe_decimal(li.line_amount)

        total_paid_q = db.session.query(
            func.sum(Payment.amount)
        ).filter(
            and_(
                Payment.dealer_id == dealer.id,
                Payment.is_deleted == False  # noqa: E712
            )
        ).scalar()
        total_paid = _safe_decimal(total_paid_q)
        pending_balance = _safe_decimal(dealer.pending_balance)

        bill_total += day_bill
        paid_total += total_paid
        pending_total += pending_balance

        row.extend([float(day_bill), float(total_paid), float(pending_balance)])
        rows.append(row)

    # Totals row
    totals_row = ['TOTAL'] + [float(product_totals[p.id]) for p in products] + [float(bill_total), float(paid_total), float(pending_total)]
    rows.append(totals_row)

    title = f'Daily Sheet - {agency.name} - {report_date.strftime("%d %b %Y")}'
    filename = f'daily_sheet_{agency.name.replace(" ", "_")}_{date_str}'

    return title, headers, rows, filename


def _build_dealer_statement_export(args):
    """Build export data for the dealer statement report."""
    dealer_id = args.get('dealer_id', type=int)
    if not dealer_id:
        raise ValueError('dealer_id is required')

    dealer = Dealer.query.get(dealer_id)
    if not dealer:
        raise ValueError('Dealer not found')

    from_date = _parse_date(args.get('from_date'), 'from_date')
    to_date = _parse_date(args.get('to_date'), 'to_date')

    # Deliveries
    delivery_query = db.session.query(
        DeliveryEntry.delivery_date,
        func.sum(DeliveryLineItem.line_amount).label('total_billed')
    ).join(
        DeliveryLineItem,
        DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
    ).filter(
        and_(
            DeliveryLineItem.dealer_id == dealer_id,
            DeliveryLineItem.is_non_billable == False  # noqa: E712
        )
    )
    if from_date:
        delivery_query = delivery_query.filter(DeliveryEntry.delivery_date >= from_date)
    if to_date:
        delivery_query = delivery_query.filter(DeliveryEntry.delivery_date <= to_date)
    delivery_rows = delivery_query.group_by(DeliveryEntry.delivery_date).all()

    # Payments
    payment_query = Payment.query.filter(
        and_(
            Payment.dealer_id == dealer_id,
            Payment.is_deleted == False  # noqa: E712
        )
    )
    if from_date:
        payment_query = payment_query.filter(
            Payment.payment_date >= datetime.combine(from_date, datetime.min.time())
        )
    if to_date:
        payment_query = payment_query.filter(
            Payment.payment_date < datetime.combine(to_date + timedelta(days=1), datetime.min.time())
        )
    payment_rows = payment_query.order_by(Payment.payment_date).all()

    # Merge
    entries = []
    for row in delivery_rows:
        entries.append({
            'sort_key': datetime.combine(row.delivery_date, datetime.min.time()),
            'date': row.delivery_date.strftime('%d %b %Y'),
            'type': 'Delivery',
            'description': f'Delivery',
            'debit': float(_safe_decimal(row.total_billed)),
            'credit': 0.0
        })
    for p in payment_rows:
        entries.append({
            'sort_key': p.payment_date,
            'date': p.payment_date.strftime('%d %b %Y'),
            'type': 'Payment',
            'description': f'{p.payment_mode}{" - " + p.remark if p.remark else ""}',
            'debit': 0.0,
            'credit': float(_safe_decimal(p.amount))
        })

    entries.sort(key=lambda x: x['sort_key'])

    headers = ['Date', 'Type', 'Description', 'Debit', 'Credit', 'Balance']

    opening = float(_safe_decimal(dealer.opening_balance))
    balance = opening
    rows = [['', '', 'Opening Balance', '', '', opening]]

    total_billed = 0.0
    total_paid = 0.0

    for e in entries:
        balance += e['debit'] - e['credit']
        total_billed += e['debit']
        total_paid += e['credit']
        rows.append([e['date'], e['type'], e['description'], e['debit'], e['credit'], round(balance, 2)])

    rows.append(['', '', 'TOTAL', round(total_billed, 2), round(total_paid, 2), round(balance, 2)])

    date_range = ''
    if from_date:
        date_range += f' from {from_date.strftime("%d %b %Y")}'
    if to_date:
        date_range += f' to {to_date.strftime("%d %b %Y")}'

    title = f'Statement - {dealer.name}{date_range}'
    filename = f'statement_{dealer.name.replace(" ", "_")}'

    return title, headers, rows, filename


def _build_outstanding_export(args):
    """Build export data for the outstanding report."""
    agency_id = args.get('agency_id', type=int)
    min_amount_str = args.get('min_amount')

    min_amount = Decimal('0')
    if min_amount_str:
        min_amount = Decimal(str(min_amount_str))

    query = Dealer.query.filter(
        and_(
            Dealer.is_active == True,  # noqa: E712
            Dealer.pending_balance > min_amount
        )
    )
    if agency_id:
        query = query.filter(Dealer.agency_id == agency_id)

    dealers = query.order_by(Dealer.pending_balance.desc()).all()

    headers = ['#', 'Dealer', 'Agency', 'Phone', 'Pending Balance', 'Credit Limit']

    rows = []
    total = Decimal('0')
    for idx, d in enumerate(dealers, 1):
        balance = _safe_decimal(d.pending_balance)
        total += balance
        credit_limit = _safe_decimal(getattr(d, 'credit_limit', None) or 0)
        agency_name = d.agency.name if d.agency else 'N/A'
        phone = getattr(d, 'phone', '') or ''
        rows.append([idx, d.name, agency_name, phone, float(balance), float(credit_limit)])

    rows.append(['', 'TOTAL', '', '', float(total), ''])

    title = 'Outstanding Balance Report'
    filename = 'outstanding_report'

    return title, headers, rows, filename


def _build_product_sales_export(args):
    """Build export data for the product sales report."""
    from_date_str = args.get('from_date')
    to_date_str = args.get('to_date')

    if not from_date_str or not to_date_str:
        raise ValueError('from_date and to_date are required')

    from_date = _parse_date(from_date_str, 'from_date')
    to_date = _parse_date(to_date_str, 'to_date')
    days_in_period = max((to_date - from_date).days + 1, 1)

    products = Product.query.filter_by(is_active=True).order_by(Product.display_order).all()

    headers = ['Product', 'Pack Size', 'Total Quantity', 'Total Revenue', 'Avg Daily Qty']

    rows = []
    for product in products:
        result = db.session.query(
            func.sum(DeliveryLineItem.quantity).label('total_qty'),
            func.sum(DeliveryLineItem.line_amount).label('total_revenue')
        ).join(
            DeliveryEntry,
            DeliveryLineItem.delivery_entry_id == DeliveryEntry.id
        ).filter(
            and_(
                DeliveryLineItem.product_id == product.id,
                DeliveryEntry.delivery_date >= from_date,
                DeliveryEntry.delivery_date <= to_date
            )
        ).first()

        total_qty = _safe_decimal(result.total_qty if result else None)
        total_revenue = _safe_decimal(result.total_revenue if result else None)
        avg_daily = float((total_qty / Decimal(str(days_in_period))).quantize(Decimal('0.001')))

        rows.append([product.name, product.pack_size, float(total_qty), float(total_revenue), avg_daily])

    title = f'Product Sales Report ({from_date.strftime("%d %b %Y")} - {to_date.strftime("%d %b %Y")})'
    filename = f'product_sales_{from_date_str}_to_{to_date_str}'

    return title, headers, rows, filename


def _build_payment_collection_export(args):
    """Build export data for the payment collection report."""
    query = Payment.query.filter(Payment.is_deleted == False)  # noqa: E712

    from_date_str = args.get('from_date')
    to_date_str = args.get('to_date')
    agency_id = args.get('agency_id', type=int)
    dealer_id = args.get('dealer_id', type=int)
    collected_by = args.get('collected_by', type=int)

    if from_date_str:
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        query = query.filter(Payment.payment_date >= from_date)
    if to_date_str:
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
        query = query.filter(Payment.payment_date < to_date + timedelta(days=1))
    if agency_id:
        query = query.join(Dealer, Payment.dealer_id == Dealer.id).filter(
            Dealer.agency_id == agency_id
        )
    if dealer_id:
        query = query.filter(Payment.dealer_id == dealer_id)
    if collected_by:
        query = query.filter(Payment.collected_by == collected_by)

    payments = query.order_by(Payment.payment_date.desc()).all()

    headers = ['Date', 'Dealer', 'Amount', 'Mode', 'Collected By', 'Remark']

    rows = []
    total = Decimal('0')
    for p in payments:
        dealer = Dealer.query.get(p.dealer_id)
        dealer_name = dealer.name if dealer else 'Unknown'
        collector_name = ''
        if p.collector:
            collector_name = p.collector.username if hasattr(p.collector, 'username') else str(p.collector)

        amt = _safe_decimal(p.amount)
        total += amt
        rows.append([
            p.payment_date.strftime('%d %b %Y %H:%M') if p.payment_date else '',
            dealer_name,
            float(amt),
            p.payment_mode or '',
            collector_name,
            p.remark or ''
        ])

    rows.append(['', 'TOTAL', float(total), '', '', ''])

    date_range_parts = []
    if from_date_str:
        date_range_parts.append(f'from {from_date_str}')
    if to_date_str:
        date_range_parts.append(f'to {to_date_str}')
    date_range = ' '.join(date_range_parts) if date_range_parts else 'All Time'

    title = f'Payment Collection Report - {date_range}'
    filename = f'payment_collection_{from_date_str or "start"}_to_{to_date_str or "end"}'

    return title, headers, rows, filename
