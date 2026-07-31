#!/usr/bin/env python3
"""Create Sales Activities, soft-delete, audit, and Task completion schema."""
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import create_app
from config import basedir
from extensions import db
from schema_updates import ensure_sales_activity_columns


def backup_sqlite(app):
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not uri.startswith('sqlite:///'):
        return None
    source = uri[len('sqlite:///'):]
    if not os.path.isabs(source):
        source = os.path.join(basedir, source)
    if not os.path.exists(source):
        return None
    backup_dir = os.path.join(os.path.dirname(source), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    destination = os.path.join(backup_dir, f'bitcrm-before-sales-activities-{datetime.now():%Y%m%d-%H%M%S}.db')
    shutil.copy2(source, destination)
    return destination


def upgrade():
    app = create_app()
    with app.app_context():
        backup = backup_sqlite(app)
        if backup:
            print(f'[OK] Database backup: {backup}')
        ensure_sales_activity_columns()
        db.create_all()
        print('[OK] Sales Activities schema is ready.')


if __name__ == '__main__':
    upgrade()
