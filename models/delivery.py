from datetime import datetime, date
from decimal import Decimal
from . import db


class DeliveryEntry(db.Model):
    __tablename__ = 'delivery_entries'
    id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, db.ForeignKey('agencies.id'), nullable=False)
    delivery_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='open', nullable=False)  # 'open' or 'finalized'
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    line_items = db.relationship('DeliveryLineItem', backref='delivery_entry', lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (db.UniqueConstraint('agency_id', 'delivery_date', name='uq_agency_date'),)

    def to_dict(self):
        return {
            'id': self.id,
            'agency_id': self.agency_id,
            'agency_name': self.agency.name if self.agency else None,
            'delivery_date': self.delivery_date.strftime('%d/%m/%Y') if self.delivery_date else None,
            'delivery_date_iso': self.delivery_date.isoformat() if self.delivery_date else None,
            'status': self.status,
            'created_by': self.created_by,
            'created_by_name': (self.creator.full_name or self.creator.username) if self.creator else None,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%d/%m/%Y %H:%M') if self.updated_at else None
        }


class DeliveryLineItem(db.Model):
    __tablename__ = 'delivery_line_items'
    id = db.Column(db.Integer, primary_key=True)
    delivery_entry_id = db.Column(db.Integer, db.ForeignKey('delivery_entries.id'), nullable=False)
    dealer_id = db.Column(db.Integer, db.ForeignKey('dealers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Numeric(10, 3), default=Decimal('0.000'), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    line_amount = db.Column(db.Numeric(12, 2), default=Decimal('0.00'), nullable=False)
    is_non_billable = db.Column(db.Boolean, default=False, nullable=False)
    remark = db.Column(db.String(255), nullable=True)

    product = db.relationship('Product', foreign_keys=[product_id])

    def to_dict(self):
        return {
            'id': self.id,
            'delivery_entry_id': self.delivery_entry_id,
            'dealer_id': self.dealer_id,
            'dealer_name': self.dealer.name if self.dealer else None,
            'product_id': self.product_id,
            'product_name': self.product.name if self.product else None,
            'quantity': float(self.quantity),
            'unit_price': float(self.unit_price),
            'line_amount': float(self.line_amount),
            'is_non_billable': self.is_non_billable,
            'remark': self.remark
        }
