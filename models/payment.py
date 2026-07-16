from datetime import datetime
from decimal import Decimal
from . import db


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    dealer_id = db.Column(db.Integer, db.ForeignKey('dealers.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    payment_mode = db.Column(db.String(30), nullable=False)  # Cash, Online/UPI, Bank Transfer, Cheque
    collected_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    remark = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)

    collector = db.relationship('User', foreign_keys=[collected_by])

    def to_dict(self):
        return {
            'id': self.id,
            'dealer_id': self.dealer_id,
            'dealer_name': self.dealer.name if self.dealer else None,
            'amount': float(self.amount),
            'payment_date': self.payment_date.strftime('%d/%m/%Y %H:%M') if self.payment_date else None,
            'payment_date_iso': self.payment_date.isoformat() if self.payment_date else None,
            'payment_mode': self.payment_mode,
            'collected_by': self.collected_by,
            'collected_by_name': (self.collector.full_name or self.collector.username) if self.collector else None,
            'remark': self.remark,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else None
        }
