from flask import Blueprint, request, jsonify
from datetime import datetime
from models import db
from models.user import User
from utils.auth import admin_required, get_current_user
from utils.audit import log_audit
from utils.validators import validate_required, sanitize_string

users_bp = Blueprint('users', __name__)


@users_bp.route('', methods=['GET'])
@admin_required
def list_users():
    try:
        users = User.query.order_by(User.created_at.desc()).all()
        return jsonify({'users': [u.to_dict() for u in users]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@users_bp.route('', methods=['POST'])
@admin_required
def create_user():
    try:
        data = request.get_json()
        errors = validate_required(data, ['username', 'password', 'role'])
        if errors:
            return jsonify({'error': errors[0]}), 400

        role = data.get('role')
        if role not in ('admin', 'collector'):
            return jsonify({'error': 'Role must be admin or collector'}), 400

        username = sanitize_string(data.get('username'))
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400

        password = data.get('password', '').strip()
        if len(password) < 4:
            return jsonify({'error': 'Password must be at least 4 characters'}), 400

        current = get_current_user()
        user = User(
            username=username,
            role=role,
            full_name=sanitize_string(data.get('full_name')),
            is_active=True,
            created_at=datetime.utcnow(),
            created_by=current.id
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        log_audit(current.id, 'create', 'user', user.id, after=user.to_dict())
        db.session.commit()
        return jsonify({'user': user.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@users_bp.route('/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        current = get_current_user()
        data = request.get_json()
        before = user.to_dict()

        if 'is_active' in data and not data['is_active'] and user.id == current.id:
            return jsonify({'error': 'Cannot deactivate your own account'}), 400

        if 'role' in data:
            if data['role'] not in ('admin', 'collector'):
                return jsonify({'error': 'Role must be admin or collector'}), 400
            user.role = data['role']
        if 'full_name' in data:
            user.full_name = sanitize_string(data.get('full_name'))
        if 'is_active' in data:
            user.is_active = data['is_active']

        log_audit(current.id, 'update', 'user', user.id, before=before, after=user.to_dict())
        db.session.commit()
        return jsonify({'user': user.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@users_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_password(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json()
        new_password = data.get('new_password', '').strip()
        if len(new_password) < 4:
            return jsonify({'error': 'Password must be at least 4 characters'}), 400

        user.set_password(new_password)

        current = get_current_user()
        log_audit(current.id, 'update', 'user_password', user.id,
                  after={'action': 'password_reset'})
        db.session.commit()
        return jsonify({'message': 'Password reset successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
