from datetime import datetime
from . import db


class Agency(db.Model):
    __tablename__ = 'agencies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    shift_label = db.Column(db.String(20), nullable=True)
    contact_person = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    dealers = db.relationship('Dealer', backref='agency', lazy='dynamic')
    delivery_entries = db.relationship('DeliveryEntry', backref='agency', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'shift_label': self.shift_label,
            'contact_person': self.contact_person,
            'phone': self.phone,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M') if self.created_at else None,
            'dealer_count': self.dealers.filter_by(is_active=True).count() if self.dealers else 0
        }
