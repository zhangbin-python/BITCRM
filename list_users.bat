@echo off
cd /d "C:\Users\zhang\clawd\BITCRM"
python -c "
import sys
sys.path.insert(0, '.')
from app import create_app
from extensions import db
from models import User

app = create_app()
with app.app_context():
    users = User.query.all()
    print('=' * 50)
    print('数据库中的用户:')
    print('=' * 50)
    for u in users:
        print(f'ID: {u.id}')
        print(f'用户名: {u.username}')
        print(f'密码Hash: {u.password_hash[:20]}...')
        print(f'角色: {u.role}')
        print(f'状态: {\"激活\" if u.is_active else \"禁用\"}')
        print('-' * 50)
    print(f'总共 {len(users)} 个用户')
"
pause
