from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity
)
from datetime import datetime, timezone, timedelta
from models import db
from models.user import User
from utils.auth import login_required_any, get_current_user
from utils.audit import log_audit
import threading

auth_bp = Blueprint('auth', __name__)

# ---------------------------------------------------------------------------
# Rate limiting state (per-process; suitable for single-instance deployment)
# ---------------------------------------------------------------------------
_failed_attempts = {}  # ip -> list of datetime objects
_rate_lock = threading.Lock()

RATE_LIMIT_WINDOW = timedelta(minutes=15)
RATE_LIMIT_MAX = 5


def _is_rate_limited(ip: str) -> bool:
    """Return True if *ip* has exceeded the failure threshold."""
    now = datetime.now(timezone.utc)
    with _rate_lock:
        attempts = _failed_attempts.get(ip, [])
        # Prune old entries
        attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
        _failed_attempts[ip] = attempts
        return len(attempts) >= RATE_LIMIT_MAX


def _record_failure(ip: str) -> None:
    now = datetime.now(timezone.utc)
    with _rate_lock:
        _failed_attempts.setdefault(ip, []).append(now)


def _clear_failures(ip: str) -> None:
    with _rate_lock:
        _failed_attempts.pop(ip, None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user and return JWT tokens."""
    try:
        client_ip = request.remote_addr or 'unknown'

        # Rate-limit check
        if _is_rate_limited(client_ip):
            return jsonify({
                'error': 'Too many failed login attempts. Please try again later.'
            }), 429

        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''

        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            _record_failure(client_ip)
            return jsonify({'error': 'Invalid username or password'}), 401

        if not user.is_active:
            _record_failure(client_ip)
            return jsonify({'error': 'Account is deactivated. Contact an administrator.'}), 403

        # Successful login - clear rate-limit counter
        _clear_failures(client_ip)

        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'role': user.role,
                'username': user.username,
                'full_name': user.full_name or user.username,
                'agency_id': user.agency_id,
                'agency_name': user.agency.name if user.agency else None
            }
        )
        refresh_token = create_refresh_token(identity=str(user.id))

        return jsonify({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'user': user.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Login failed', 'detail': str(e)}), 500


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Issue a new access token using a valid refresh token."""
    try:
        identity = get_jwt_identity()
        access_token = create_access_token(identity=str(identity))
        return jsonify({'access_token': access_token}), 200
    except Exception as e:
        return jsonify({'error': 'Token refresh failed', 'detail': str(e)}), 500


@auth_bp.route('/change-password', methods=['POST'])
@login_required_any
def change_password():
    """Change the current user's password."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        data = request.get_json(silent=True) or {}
        current_password = data.get('current_password') or ''
        new_password = data.get('new_password') or ''

        if not current_password or not new_password:
            return jsonify({'error': 'Current password and new password are required'}), 400

        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters'}), 400

        if not user.check_password(current_password):
            return jsonify({'error': 'Current password is incorrect'}), 401

        user.set_password(new_password)
        db.session.commit()

        log_audit(
            user.id,
            'update',
            'user',
            user.id,
            after={'action': 'password_changed'}
        )

        return jsonify({'message': 'Password changed successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Password change failed', 'detail': str(e)}), 500


@auth_bp.route('/logout', methods=['POST'])
@login_required_any
def logout():
    """Log out the current user (client should discard tokens)."""
    try:
        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        return jsonify({'error': 'Logout failed', 'detail': str(e)}), 500


@auth_bp.route('/me', methods=['GET'])
@login_required_any
def me():
    """Return the current authenticated user's profile."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'user': user.to_dict()}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch user profile', 'detail': str(e)}), 500
