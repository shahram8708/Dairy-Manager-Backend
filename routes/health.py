from flask import Blueprint, jsonify
from datetime import datetime, timezone

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health_check():
    """Lightweight health check endpoint. No DB access, no auth."""
    try:
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        return jsonify({'error': 'Health check failed', 'detail': str(e)}), 500
