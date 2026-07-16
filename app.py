import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db

jwt = JWTManager()


def create_app():
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    app.config.from_object(Config)

    db.init_app(app)
    jwt.init_app(app)
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True,
         allow_headers=['Content-Type', 'Authorization'],
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

    from routes.health import health_bp
    from routes.auth import auth_bp
    from routes.agencies import agencies_bp
    from routes.products import products_bp
    from routes.dealers import dealers_bp
    from routes.deliveries import deliveries_bp
    from routes.payments import payments_bp
    from routes.reports import reports_bp
    from routes.users import users_bp
    from routes.settings import settings_bp

    app.register_blueprint(health_bp, url_prefix='/api/v1')
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(agencies_bp, url_prefix='/api/v1/agencies')
    app.register_blueprint(products_bp, url_prefix='/api/v1/products')
    app.register_blueprint(dealers_bp, url_prefix='/api/v1/dealers')
    app.register_blueprint(deliveries_bp, url_prefix='/api/v1/deliveries')
    app.register_blueprint(payments_bp, url_prefix='/api/v1/payments')
    app.register_blueprint(reports_bp, url_prefix='/api/v1/reports')
    app.register_blueprint(users_bp, url_prefix='/api/v1/users')
    app.register_blueprint(settings_bp, url_prefix='/api/v1/settings')

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token has expired'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({'error': 'Invalid token'}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({'error': 'Authorization token required'}), 401

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Resource not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': 'Internal server error'}), 500

    with app.app_context():
        db.create_all()
        seed_data()

    return app


def seed_data():
    from models.user import User
    from models.agency import Agency
    from models.settings import BusinessSettings

    if User.query.first() is None:
        admin = User(
            username=Config.SEED_ADMIN_USERNAME,
            role='admin',
            full_name='System Administrator',
            is_active=True
        )
        admin.set_password(Config.SEED_ADMIN_PASSWORD)
        db.session.add(admin)
        db.session.flush()

        nr = Agency(name='NR Marketing', shift_label='AM', contact_person='', phone='', is_active=True)
        swara = Agency(name='Swara Agency', shift_label='PM', contact_person='', phone='', is_active=True)
        db.session.add(nr)
        db.session.add(swara)

        settings = BusinessSettings(business_name='Dairy Distribution Business')
        db.session.add(settings)

        db.session.commit()


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=Config.DEBUG, use_reloader=False)
