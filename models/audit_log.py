from datetime import datetime
from . import db


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(20), nullable=False)  # 'create', 'update', 'delete'
    entity_type = db.Column(db.String(50), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    before_value = db.Column(db.Text, nullable=True)
    after_value = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_name': (self.user.full_name or self.user.username) if self.user else 'System',
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'before_value': self.before_value,
            'after_value': self.after_value,
            'ip_address': self.ip_address,
            'timestamp': self.timestamp.strftime('%d/%m/%Y %H:%M:%S') if self.timestamp else None
        }
