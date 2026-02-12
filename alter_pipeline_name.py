#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alter pipeline table to allow NULL for name field"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app import create_app
from extensions import db

app = create_app()
with app.app_context():
    print('=' * 50)
    print('修改 pipeline 表，允许 name 为 NULL')
    print('=' * 50)
    
    # SQLite 不支持 ALTER COLUMN，需要重建表
    # 步骤：创建新表 -> 复制数据 -> 删除旧表 -> 重命名
    
    # 1. 创建临时新表
    db.session.execute(db.text('''
        CREATE TABLE pipeline_new (
            id INTEGER NOT NULL,
            name TEXT,
            company TEXT,
            industry TEXT,
            position TEXT,
            email TEXT,
            mobile_number TEXT,
            owner_id INTEGER,
            sales_lead_id INTEGER,
            product TEXT,
            tcv_usd FLOAT,
            contract_term_yrs FLOAT,
            mrc_usd FLOAT,
            otc_usd FLOAT,
            gp_margin FLOAT,
            gp FLOAT,
            mg TEXT,
            est_sign_date DATE,
            est_act_date DATE,
            win_rate FLOAT,
            stage TEXT,
            level TEXT,
            date_added DATE,
            stuckpoint TEXT,
            comments TEXT,
            follow_up TEXT,
            date_entered DATE,
            created_at DATETIME,
            updated_at DATETIME,
            m1 FLOAT,
            m2 FLOAT,
            m3 FLOAT,
            m4 FLOAT,
            m5 FLOAT,
            m6 FLOAT,
            m7 FLOAT,
            m8 FLOAT,
            m9 FLOAT,
            m10 FLOAT,
            m11 FLOAT,
            m12 FLOAT,
            FOREIGN KEY (owner_id) REFERENCES user (id),
            FOREIGN KEY (sales_lead_id) REFERENCES sales_lead (id),
            PRIMARY KEY (id)
        )
    '''))
    print('1. 创建新表 pipeline_new')
    
    # 2. 复制数据
    db.session.execute(db.text('INSERT INTO pipeline_new SELECT * FROM pipeline'))
    print('2. 复制数据到新表')
    
    # 3. 删除旧表
    db.session.execute(db.text('DROP TABLE pipeline'))
    print('3. 删除旧表 pipeline')
    
    # 4. 重命名新表
    db.session.execute(db.text('ALTER TABLE pipeline_new RENAME TO pipeline'))
    print('4. 重命名新表为 pipeline')
    
    # 5. 重建索引（如果需要）
    db.session.execute(db.text('CREATE INDEX ix_pipeline_owner_id ON pipeline (owner_id)'))
    db.session.execute(db.text('CREATE INDEX ix_pipeline_sales_lead_id ON pipeline (sales_lead_id)'))
    print('5. 重建索引')
    
    db.session.commit()
    
    # 验证
    result = db.session.execute(db.text('PRAGMA table_info(pipeline)')).fetchall()
    print('\n验证 - name 列信息:')
    for col in result:
        if col[1] == 'name':
            print(f'  列名: {col[1]}, 类型: {col[2]}, nullable: {not col[3]}')
            break
    
    print('\n完成！name 字段现在允许 NULL')
