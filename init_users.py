#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app import create_app
from extensions import db
from models import User
from werkzeug.security import generate_password_hash

app = create_app()
with app.app_context():
    print('=' * 50)
    print('创建默认用户')
    print('=' * 50)
    
    # 先删除所有现有用户
    deleted = User.query.delete()
    print(f'已删除 {deleted} 个现有用户')
    
    users = [
        {'username': 'Admin', 'password': '123', 'role': 'Admin'},
        {'username': 'Anthony', 'password': '123', 'role': 'Admin'},
        {'username': 'Bruce', 'password': '123', 'role': 'Sales'},
        {'username': 'Cean', 'password': '123', 'role': 'Admin'},
        {'username': 'Eric', 'password': '123', 'role': 'Sales'},
        {'username': 'Jam', 'password': '123', 'role': 'Sales'},
        {'username': 'Jeromo', 'password': '123', 'role': 'Sales'},
        {'username': 'Jokie', 'password': '123', 'role': 'Sales'},
        {'username': 'Joseph', 'password': '123', 'role': 'Sales'},
        {'username': 'Lancey', 'password': '123', 'role': 'Sales'},
        {'username': 'Lancey m', 'password': '123', 'role': 'Sales'},
        {'username': 'Marketing', 'password': '123', 'role': 'Marketing'},
        {'username': 'Romeo', 'password': '123', 'role': 'Marketing'},
        {'username': 'Sherwin', 'password': '123', 'role': 'Sales'},
        {'username': 'Uly', 'password': '123', 'role': 'Sales'},
    ]
    
    for u in users:
        print('创建: ' + u['username'] + ' (' + u['role'] + ')')
        new_user = User(
            username=u['username'],
            password_hash=generate_password_hash(u['password']),
            email=u['username'].lower().replace(' ', '') + '@bit.com',
            role=u['role'],
            is_active=True
        )
        db.session.add(new_user)
    
    db.session.commit()
    
    print('=' * 50)
    print('当前用户列表')
    print('=' * 50)
    all_users = User.query.all()
    for u in all_users:
        print('用户名: ' + u.username + ', 角色: ' + u.role)
    print('共 ' + str(len(all_users)) + ' 个用户')
