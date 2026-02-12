"""
BITCRM Configuration Module
Contains all application configuration settings.
"""
import os

# Base directory
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration class."""
    
    # Secret key for session management
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-in-production'
    
    # Database configuration - Support Zeabur PostgreSQL
    DATABASE_URL = os.environ.get('DATABASE_URL') or \
        os.environ.get('DATABASE_URI') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'bitcrm.db')
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,  # Recycle connections after 1 hour
        'pool_size': int(os.environ.get('DB_POOL_SIZE') or '10'),  # Connection pool size
        'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW') or '20'),  # Max overflow connections
    }
    
    # Flask-Babel configuration
    BABEL_DEFAULT_LOCALE = 'en'
    BABEL_DEFAULT_TIMEZONE = 'UTC'
    LANGUAGES = ['en', 'zh']
    
    # File upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(basedir, 'instance', 'uploads')
    ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
    
    # Excel template paths
    EXCEL_TEMPLATES_FOLDER = os.path.join(basedir, 'instance', 'templates')
    
    # Pagination
    PAGE_SIZE = 20
    
    # Flask-Caching configuration
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    ENV = 'development'


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    ENV = 'production'
    
    # In production, ensure SECRET_KEY is set via environment
    @staticmethod
    def init_app(app):
        if not app.config['SECRET_KEY']:
            raise ValueError("SECRET_KEY must be set in production environment")


# Configuration dictionary for easy access
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
