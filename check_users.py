import sys
sys.path.insert(0, 'C:/Users/zhang/clawd/BITCRM')
from models import User
from app import create_app
from extensions import db

app = create_app()
with app.app_context():
    print('Users:', User.query.count())
    for u in User.query.all():
        print(f'  - {u.username} ({u.role})')
