from decimal import Decimal, InvalidOperation

VALID_PAYMENT_MODES = ['Cash', 'Online/UPI', 'Bank Transfer', 'Cheque']


def validate_required(data, fields):
    errors = []
    if not data:
        return ['Request body is required']
    for field in fields:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f'{field} is required')
    return errors


def validate_decimal(value, field_name):
    if value is None:
        return None
    try:
        d = Decimal(str(value))
        if d.is_nan() or d.is_infinite():
            return f'{field_name} must be a valid number'
        return None
    except (InvalidOperation, ValueError, TypeError):
        return f'{field_name} must be a valid number'


def validate_payment_mode(mode):
    if mode not in VALID_PAYMENT_MODES:
        return f'Payment mode must be one of: {", ".join(VALID_PAYMENT_MODES)}'
    return None


def sanitize_string(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return str(value).strip() or None
