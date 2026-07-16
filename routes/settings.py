from flask import Blueprint, request, jsonify, send_file
from datetime import datetime
import os
import io
from models import db
from models.settings import BusinessSettings
from models.audit_log import AuditLog
from utils.auth import admin_required, login_required_any, get_current_user
from utils.validators import sanitize_string

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('', methods=['GET'])
@login_required_any
def get_settings():
    try:
        s = BusinessSettings.query.first()
        if not s:
            s = BusinessSettings(business_name='Dairy Distribution Business')
            db.session.add(s)
            db.session.commit()
        return jsonify({'settings': {
            'id': s.id,
            'business_name': s.business_name,
            'address': s.address,
            'phone': s.phone,
            'email': s.email,
            'updated_at': s.updated_at.strftime('%d/%m/%Y %H:%M') if s.updated_at else None
        }})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('', methods=['PUT'])
@admin_required
def update_settings():
    try:
        data = request.get_json()
        s = BusinessSettings.query.first()
        if not s:
            s = BusinessSettings()
            db.session.add(s)

        if 'business_name' in data:
            s.business_name = sanitize_string(data['business_name']) or 'Dairy Distribution Business'
        if 'address' in data:
            s.address = sanitize_string(data.get('address'))
        if 'phone' in data:
            s.phone = sanitize_string(data.get('phone'))
        if 'email' in data:
            s.email = sanitize_string(data.get('email'))

        user = get_current_user()
        s.updated_by = user.id
        s.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({'settings': {
            'id': s.id,
            'business_name': s.business_name,
            'address': s.address,
            'phone': s.phone,
            'email': s.email,
            'updated_at': s.updated_at.strftime('%d/%m/%Y %H:%M') if s.updated_at else None
        }})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/audit-log', methods=['GET'])
@admin_required
def get_audit_log():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        per_page = min(per_page, 100)

        query = AuditLog.query

        entity_type = request.args.get('entity_type')
        if entity_type:
            query = query.filter_by(entity_type=entity_type)

        action = request.args.get('action')
        if action:
            query = query.filter_by(action=action)

        user_id = request.args.get('user_id', type=int)
        if user_id:
            query = query.filter_by(user_id=user_id)

        from_date = request.args.get('from_date')
        if from_date:
            query = query.filter(AuditLog.timestamp >= datetime.strptime(from_date, '%Y-%m-%d'))

        to_date = request.args.get('to_date')
        if to_date:
            to_dt = datetime.strptime(to_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(AuditLog.timestamp <= to_dt)

        query = query.order_by(AuditLog.timestamp.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        return jsonify({
            'logs': [l.to_dict() for l in paginated.items],
            'total': paginated.total,
            'page': paginated.page,
            'pages': paginated.pages
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/backup', methods=['GET', 'POST'])
@admin_required
def create_backup():
    try:
        db_uri = db.engine.url.database
        if not db_uri or not os.path.exists(db_uri):
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'instance', 'dairy.db')
            if not os.path.exists(db_path):
                db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dairy.db')
            if not os.path.exists(db_path):
                return jsonify({'error': 'Database file not found'}), 404
            db_uri = db_path

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return send_file(
            db_uri,
            as_attachment=True,
            download_name=f'dairy_backup_{timestamp}.db',
            mimetype='application/x-sqlite3'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
