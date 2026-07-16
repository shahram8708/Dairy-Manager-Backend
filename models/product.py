from datetime import datetime
from . import db


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    pack_size = db.Column(db.String(50), nullable=True)
    outer_unit = db.Column(db.String(50), default='Crate')
    pieces_per_unit = db.Column(db.Integer, nullable=True)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    prices = db.relationship('ProductPrice', backref='product', lazy='dynamic', order_by='ProductPrice.effective_from.desc()')

    def get_current_price(self):
        from .product_price import ProductPrice
        price = ProductPrice.query.filter_by(product_id=self.id, effective_to=None).first()
        return price

    def to_dict(self, include_price=True):
        result = {
            'id': self.id,
            'name': self.name,
            'pack_size': self.pack_size,
            'outer_unit': self.outer_unit,
            'pieces_per_unit': self.pieces_per_unit,
            'display_order': self.display_order,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else None
        }
        if include_price:
            current_price = self.get_current_price()
            result['current_price'] = float(current_price.price_per_unit) if current_price else None
            result['price_id'] = current_price.id if current_price else None
        return result
