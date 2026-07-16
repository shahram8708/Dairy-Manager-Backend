from datetime import datetime
from decimal import Decimal
from . import db


class ProductPrice(db.Model):
    __tablename__ = 'product_prices'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    price_per_unit = db.Column(db.Numeric(10, 2), nullable=False)
    effective_from = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    effective_to = db.Column(db.DateTime, nullable=True)  # null = currently active
    set_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    setter = db.relationship('User', foreign_keys=[set_by])

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'price_per_unit': float(self.price_per_unit),
            'effective_from': self.effective_from.strftime('%d/%m/%Y %H:%M') if self.effective_from else None,
            'effective_to': self.effective_to.strftime('%d/%m/%Y %H:%M') if self.effective_to else None,
            'set_by': self.set_by,
            'set_by_name': self.setter.full_name or self.setter.username if self.setter else None,
            'is_current': self.effective_to is None,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else None
        }
