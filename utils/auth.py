from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from models.user import User


def get_current_user():
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        pass
    return User.query.get(user_id)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = get_current_user()
        if not user or not user.is_active:
            return jsonify({'error': 'Account inactive or not found'}), 403
        if user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return fn(*args, **kwargs)
    return wrapper


def login_required_any(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user = get_current_user()
        if not user or not user.is_active:
            return jsonify({'error': 'Account inactive or not found'}), 403
        return fn(*args, **kwargs)
    return wrapper
