from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from sqlalchemy import func
from models import db
from models.dealer import Dealer
from models.delivery import DeliveryLineItem
from models.payment import Payment
from models.product_price import ProductPrice


def get_active_price(product_id, as_of_date=None):
    if as_of_date is None:
        as_of_date = datetime.utcnow()
    elif not isinstance(as_of_date, datetime):
        as_of_date = datetime.combine(as_of_date, datetime.max.time())

    price = ProductPrice.query.filter(
        ProductPrice.product_id == product_id,
        ProductPrice.effective_from <= as_of_date,
        db.or_(
            ProductPrice.effective_to.is_(None),
            ProductPrice.effective_to >= as_of_date
        )
    ).order_by(ProductPrice.effective_from.desc()).first()
    return price


def calculate_line_amount(quantity, unit_price):
    if not isinstance(quantity, Decimal):
        quantity = Decimal(str(quantity))
    if not isinstance(unit_price, Decimal):
        unit_price = Decimal(str(unit_price))
    result = quantity * unit_price
    return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def recalculate_dealer_balance(dealer_id):
    dealer = Dealer.query.get(dealer_id)
    if not dealer:
        return None

    total_billed = db.session.query(
        func.coalesce(func.sum(DeliveryLineItem.line_amount), Decimal('0.00'))
    ).filter(
        DeliveryLineItem.dealer_id == dealer_id,
        DeliveryLineItem.is_non_billable == False
    ).scalar()

    total_paid = db.session.query(
        func.coalesce(func.sum(Payment.amount), Decimal('0.00'))
    ).filter(
        Payment.dealer_id == dealer_id,
        Payment.is_deleted == False
    ).scalar()

    if not isinstance(total_billed, Decimal):
        total_billed = Decimal(str(total_billed)) if total_billed else Decimal('0.00')
    if not isinstance(total_paid, Decimal):
        total_paid = Decimal(str(total_paid)) if total_paid else Decimal('0.00')

    opening = dealer.opening_balance if dealer.opening_balance else Decimal('0.00')
    if not isinstance(opening, Decimal):
        opening = Decimal(str(opening))

    dealer.pending_balance = opening + total_billed - total_paid
    db.session.add(dealer)
    db.session.commit()
    return dealer
