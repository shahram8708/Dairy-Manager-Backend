from datetime import datetime
from decimal import Decimal
from . import db


class Dealer(db.Model):
    __tablename__ = 'dealers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    agency_id = db.Column(db.Integer, db.ForeignKey('agencies.id'), nullable=False)
    route_area = db.Column(db.String(100), nullable=True)
    credit_limit = db.Column(db.Numeric(12, 2), nullable=True)
    opening_balance = db.Column(db.Numeric(12, 2), default=Decimal('0.00'), nullable=False)
    pending_balance = db.Column(db.Numeric(12, 2), default=Decimal('0.00'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    line_items = db.relationship('DeliveryLineItem', backref='dealer', lazy='dynamic')
    payments = db.relationship('Payment', backref='dealer', lazy='dynamic', order_by='Payment.payment_date.desc()')

    def to_dict(self):
        result = {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'address': self.address,
            'agency_id': self.agency_id,
            'agency_name': self.agency.name if self.agency else None,
            'route_area': self.route_area,
            'credit_limit': float(self.credit_limit) if self.credit_limit is not None else None,
            'opening_balance': float(self.opening_balance) if self.opening_balance else 0,
            'pending_balance': float(self.pending_balance) if self.pending_balance else 0,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else None
        }
        if self.credit_limit is not None and self.pending_balance is not None:
            result['over_credit_limit'] = float(self.pending_balance) > float(self.credit_limit)
        else:
            result['over_credit_limit'] = False
        return result
