import sys
sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')
from app import create_app
from extensions import db

app = create_app()
with app.app_context():
    print("Dropping and recreating database tables...")
    db.drop_all()
    db.create_all()
    print("Database recreated successfully!")
