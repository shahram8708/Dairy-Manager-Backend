from flask import Blueprint, request, jsonify
from datetime import datetime
from decimal import Decimal
from models import db
from models.product import Product
from models.product_price import ProductPrice
from utils.auth import admin_required, login_required_any, get_current_user
from utils.audit import log_audit
from utils.validators import validate_required, sanitize_string

products_bp = Blueprint('products', __name__)


@products_bp.route('', methods=['GET'])
@login_required_any
def list_products():
    try:
        query = Product.query.order_by(Product.display_order, Product.name)
        is_active = request.args.get('is_active')
        if is_active is not None:
            query = query.filter_by(is_active=is_active.lower() == 'true')
        products = query.all()
        return jsonify({'products': [p.to_dict() for p in products]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@products_bp.route('/<int:product_id>', methods=['GET'])
@login_required_any
def get_product(product_id):
    try:
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        prices = ProductPrice.query.filter_by(product_id=product_id).order_by(ProductPrice.effective_from.desc()).all()
        return jsonify({
            'product': product.to_dict(),
            'prices': [p.to_dict() for p in prices]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@products_bp.route('', methods=['POST'])
@admin_required
def create_product():
    try:
        data = request.get_json()
        errors = validate_required(data, ['name'])
        if errors:
            return jsonify({'error': errors[0]}), 400

        product = Product(
            name=sanitize_string(data.get('name')),
            pack_size=sanitize_string(data.get('pack_size')),
            outer_unit=sanitize_string(data.get('outer_unit')) or 'Crate',
            pieces_per_unit=data.get('pieces_per_unit'),
            display_order=data.get('display_order', 0),
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.session.add(product)
        db.session.flush()

        user = get_current_user()
        log_audit(user.id, 'create', 'product', product.id, after=product.to_dict(include_price=False))
        db.session.commit()
        return jsonify({'product': product.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@products_bp.route('/<int:product_id>', methods=['PUT'])
@admin_required
def update_product(product_id):
    try:
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        data = request.get_json()
        before = product.to_dict(include_price=False)

        if 'name' in data and data['name']:
            product.name = sanitize_string(data['name'])
        if 'pack_size' in data:
            product.pack_size = sanitize_string(data.get('pack_size'))
        if 'outer_unit' in data:
            product.outer_unit = sanitize_string(data.get('outer_unit')) or 'Crate'
        if 'pieces_per_unit' in data:
            product.pieces_per_unit = data.get('pieces_per_unit')
        if 'display_order' in data:
            product.display_order = data.get('display_order', 0)
        if 'is_active' in data:
            product.is_active = data.get('is_active')

        user = get_current_user()
        log_audit(user.id, 'update', 'product', product.id, before=before, after=product.to_dict(include_price=False))
        db.session.commit()
        return jsonify({'product': product.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@products_bp.route('/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    try:
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        before = product.to_dict(include_price=False)
        product.is_active = False

        user = get_current_user()
        log_audit(user.id, 'delete', 'product', product.id, before=before)
        db.session.commit()
        return jsonify({'message': 'Product deactivated'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@products_bp.route('/<int:product_id>/price', methods=['POST'])
@admin_required
def set_price(product_id):
    try:
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        data = request.get_json()
        price_value = data.get('price_per_unit')
        if price_value is None:
            return jsonify({'error': 'price_per_unit is required'}), 400

        try:
            price_decimal = Decimal(str(price_value))
            if price_decimal <= 0:
                return jsonify({'error': 'Price must be greater than zero'}), 400
        except Exception:
            return jsonify({'error': 'Invalid price value'}), 400

        user = get_current_user()
        now = datetime.utcnow()

        current_price = ProductPrice.query.filter_by(
            product_id=product_id, effective_to=None
        ).first()

        old_price_dict = current_price.to_dict() if current_price else None

        if current_price:
            current_price.effective_to = now

        new_price = ProductPrice(
            product_id=product_id,
            price_per_unit=price_decimal,
            effective_from=now,
            effective_to=None,
            set_by=user.id,
            created_at=now
        )
        db.session.add(new_price)
        db.session.flush()

        log_audit(user.id, 'update', 'product_price', product_id,
                  before=old_price_dict, after=new_price.to_dict())
        db.session.commit()
        return jsonify({'price': new_price.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@products_bp.route('/<int:product_id>/prices', methods=['GET'])
@login_required_any
def list_prices(product_id):
    try:
        product = Product.query.get(product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404

        prices = ProductPrice.query.filter_by(product_id=product_id)\
            .order_by(ProductPrice.effective_from.desc()).all()
        return jsonify({'prices': [p.to_dict() for p in prices]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
