from datetime import datetime
from . import db


class BusinessSettings(db.Model):
    __tablename__ = 'business_settings'
    id = db.Column(db.Integer, primary_key=True)
    business_name = db.Column(db.String(200), default='Dairy Distribution Business')
    address = db.Column(db.Text, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
