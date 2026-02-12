"""
BITCRM Extensions
Flask extensions initialization.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_babel import Babel
from flask_migrate import Migrate
from flask_caching import Cache

db = SQLAlchemy()
login_manager = LoginManager()
babel = Babel()
migrate = Migrate()
cache = Cache()
