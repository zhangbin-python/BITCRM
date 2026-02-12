@echo off
cd /d "C:\Users\zhang\clawd\BITCRM"
python -c "
import sys
sys.path.insert(0, '.')
from app import create_app
from extensions import db
from models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    users = [
        {'username': 'admin', 'password': 'admin123', 'role': 'admin', 'is_active': True},
        {'username': 'bruce', 'password': 'bruce123', 'role': 'admin', 'is_active': True},
        {'username': 'john', 'password': 'john123', 'role': 'member', 'is_active': True},
        {'username': 'jane', 'password': 'jane123', 'role': 'member', 'is_active': True},
    ]
    
    for u in users:
        existing = User.query.filter_by(username=u['username']).first()
        if existing:
            print(f'更新用户: {u[\"username\"]}')
            existing.password_hash = generate_password_hash(u['password'])
            existing.role = u['role']
            existing.is_active = u['is_active']
        else:
            print(f'创建用户: {u[\"username\"]}')
            new_user = User(
                username=u['username'],
                password_hash=generate_password_hash(u['password']),
                email=f'{u[\"username\"]}@bit.com',
                role=u['role'],
                is_active=u['is_active']
            )
            db.session.add(new_user)
    
    db.session.commit()
    print('完成！')
"
pause
