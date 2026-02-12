@echo off
cd /d "C:\Users\zhang\clawd\BITCRM"
python -c "
import sys
sys.path.insert(0, '.')
from app import create_app
from extensions import db
from models import User, WeeklyMetrics
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

app = create_app()
with app.app_context():
    # 1. 创建默认用户
    print('=' * 50)
    print('创建默认用户')
    print('=' * 50)
    
    users = [
        {'username': 'admin', 'password': 'admin123', 'role': 'admin'},
        {'username': 'bruce', 'password': 'bruce123', 'role': 'admin'},
        {'username': 'john', 'password': 'john123', 'role': 'member'},
        {'username': 'jane', 'password': 'jane123', 'role': 'member'},
    ]
    
    for u in users:
        existing = User.query.filter_by(username=u['username']).first()
        if existing:
            print(f'更新: {u[\"username\"]}')
            existing.password_hash = generate_password_hash(u['password'])
            existing.role = u['role']
            existing.is_active = True
        else:
            print(f'创建: {u[\"username\"]}')
            new_user = User(
                username=u['username'],
                password_hash=generate_password_hash(u['password']),
                email=f'{u[\"username\"]}@bit.com',
                role=u['role'],
                is_active=True
            )
            db.session.add(new_user)
    
    db.session.commit()
    
    # 2. 显示所有用户
    print('=' * 50)
    print('当前用户列表')
    print('=' * 50)
    all_users = User.query.all()
    for u in all_users:
        print(f'用户名: {u.username}, 角色: {u.role}')
    print(f'共 {len(all_users)} 个用户')
    print('=' * 50)
"
pause
