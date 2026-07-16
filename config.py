import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret-key')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'change-this-jwt-secret')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///dairy.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=365)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=365)
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'
    SEED_ADMIN_USERNAME = os.environ.get('SEED_ADMIN_USERNAME')
    SEED_ADMIN_PASSWORD = os.environ.get('SEED_ADMIN_PASSWORD')
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'http://127.0.0.1:3000,http://127.0.0.1:3000').split(',')
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
