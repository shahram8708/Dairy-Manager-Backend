from flask import Blueprint, request, jsonify
from models import db
from models.agency import Agency
from utils.auth import admin_required, login_required_any, get_current_user
from utils.audit import log_audit
from utils.validators import validate_required, sanitize_string
import json

agencies_bp = Blueprint('agencies', __name__)


@agencies_bp.route('/', methods=['GET'])
@login_required_any
def list_agencies():
    """List all agencies with optional is_active filter."""
    try:
        current_user = get_current_user()
        query = Agency.query

        if current_user.role == 'delivery':
            query = query.filter_by(id=current_user.agency_id)

        is_active = request.args.get('is_active')
        if is_active is not None:
            query = query.filter_by(is_active=is_active.lower() == 'true')

        agencies = query.order_by(Agency.name).all()
        return jsonify({'agencies': [a.to_dict() for a in agencies]}), 200

    except Exception as e:
        return jsonify({'error': 'Failed to fetch agencies', 'detail': str(e)}), 500


@agencies_bp.route('/<int:id>', methods=['GET'])
@login_required_any
def get_agency(id):
    """Get a single agency by ID."""
    try:
        current_user = get_current_user()
        agency = Agency.query.get(id)
        if not agency:
            return jsonify({'error': 'Agency not found'}), 404
        if current_user.role == 'delivery' and agency.id != current_user.agency_id:
            return jsonify({'error': 'Access denied'}), 403
        return jsonify({'agency': agency.to_dict()}), 200
    except Exception as e:
        return jsonify({'error': 'Failed to fetch agency', 'detail': str(e)}), 500


@agencies_bp.route('/', methods=['POST'])
@admin_required
def create_agency():
    """Create a new agency."""
    try:
        data = request.get_json(silent=True) or {}

        # Validate required fields
        name = sanitize_string(data.get('name', ''))
        if not name:
            return jsonify({'error': 'Agency name is required'}), 400

        # Check for duplicate name
        existing = Agency.query.filter(
            db.func.lower(Agency.name) == name.lower()
        ).first()
        if existing:
            return jsonify({'error': 'An agency with this name already exists'}), 400

        agency = Agency(
            name=name,
            shift_label=sanitize_string(data.get('shift_label', '')),
            contact_person=sanitize_string(data.get('contact_person', '')),
            phone=sanitize_string(data.get('phone', '')),
            is_active=True
        )
        db.session.add(agency)
        db.session.commit()

        current_user = get_current_user()
        log_audit(
            user_id=current_user.id,
            action='create',
            entity_type='agency',
            entity_id=agency.id,
            after=agency.to_dict()
        )

        return jsonify({'agency': agency.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create agency', 'detail': str(e)}), 500


@agencies_bp.route('/<int:id>', methods=['PUT'])
@admin_required
def update_agency(id):
    """Update an existing agency."""
    try:
        agency = Agency.query.get(id)
        if not agency:
            return jsonify({'error': 'Agency not found'}), 404

        data = request.get_json(silent=True) or {}
        before = json.dumps(agency.to_dict())

        if 'name' in data:
            new_name = sanitize_string(data['name'])
            if not new_name:
                return jsonify({'error': 'Agency name cannot be empty'}), 400
            # Check duplicate (exclude self)
            existing = Agency.query.filter(
                db.func.lower(Agency.name) == new_name.lower(),
                Agency.id != id
            ).first()
            if existing:
                return jsonify({'error': 'An agency with this name already exists'}), 400
            agency.name = new_name

        if 'shift_label' in data:
            agency.shift_label = sanitize_string(data['shift_label'])
        if 'contact_person' in data:
            agency.contact_person = sanitize_string(data['contact_person'])
        if 'phone' in data:
            agency.phone = sanitize_string(data['phone'])
        if 'is_active' in data:
            agency.is_active = bool(data['is_active'])

        db.session.commit()

        current_user = get_current_user()
        log_audit(
            user_id=current_user.id,
            action='update',
            entity_type='agency',
            entity_id=agency.id,
            before=before,
            after=agency.to_dict()
        )

        return jsonify({'agency': agency.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update agency', 'detail': str(e)}), 500


@agencies_bp.route('/<int:id>', methods=['DELETE'])
@admin_required
def delete_agency(id):
    """Soft-delete (deactivate) an agency."""
    try:
        agency = Agency.query.get(id)
        if not agency:
            return jsonify({'error': 'Agency not found'}), 404

        if not agency.is_active:
            return jsonify({'error': 'Agency is already deactivated'}), 400

        agency.is_active = False
        db.session.commit()

        current_user = get_current_user()
        log_audit(
            user_id=current_user.id,
            action='deactivate',
            entity_type='agency',
            entity_id=agency.id,
            after={'id': agency.id, 'name': agency.name, 'is_active': False}
        )

        return jsonify({'message': 'Agency deactivated'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to deactivate agency', 'detail': str(e)}), 500
