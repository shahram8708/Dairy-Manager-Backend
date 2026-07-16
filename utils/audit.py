import json
from datetime import datetime
from flask import request
from models import db
from models.audit_log import AuditLog


def log_audit(user_id, action, entity_type, entity_id, before=None, after=None, before_value=None, after_value=None):
    ip = None
    try:
        ip = request.remote_addr
    except RuntimeError:
        pass

    before_content = before_value if before_value is not None else before
    after_content = after_value if after_value is not None else after

    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_value=json.dumps(before_content, default=str, ensure_ascii=False) if before_content else None,
        after_value=json.dumps(after_content, default=str, ensure_ascii=False) if after_content else None,
        ip_address=ip,
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.flush()
