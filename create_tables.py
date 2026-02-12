import sys
sys.path.insert(0, '.')

from app import create_app
from extensions import db

app = create_app()

with app.app_context():
    # Add dashboard_filters column to users table
    try:
        db.session.execute('ALTER TABLE users ADD COLUMN dashboard_filters TEXT')
        db.session.commit()
        print('✅ dashboard_filters column added!')
    except Exception as e:
        print(f'Column might already exist: {e}')
        db.session.rollback()
    
    # Create all new tables
    db.create_all()
    print('✅ All tables created!')
