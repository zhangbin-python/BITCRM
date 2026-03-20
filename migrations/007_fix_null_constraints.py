"""Fix NULL constraints in pipeline table"""
import sys
import os
import sqlite3

current_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(current_dir, '..', 'instance', 'bitcrm.db')
db_path = os.path.abspath(db_path)

print('=' * 50)
print('修复 pipeline 表的 NULL 约束')
print('=' * 50)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Columns that should allow NULL
nullable_columns = [
    'name',
    'company', 
    'industry',
    'position',
    'email',
    'mobile_number',
    'product',
    'tcv_usd',
    'mrc_usd',
    'otc_usd',
    'gp_margin',
    'gp',
    'mg',
    'est_sign_date',
    'est_act_date',
    'award_date',
    'proposal_sent_date',
    'win_rate',
    'stage',
    'level',
    'stuckpoint',
    'comments',
    'follow_up',
]

# Create new table with proper NULL constraints
cursor.execute('''
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
        contract_term_yrs INTEGER,
        mrc_usd FLOAT,
        otc_usd FLOAT,
        gp_margin FLOAT,
        gp FLOAT,
        mg TEXT,
        est_sign_date DATE,
        est_act_date DATE,
        award_date DATE,
        proposal_sent_date DATE,
        win_rate FLOAT,
        stage TEXT,
        level TEXT,
        date_added DATE,
        stuckpoint TEXT,
        comments TEXT,
        follow_up TEXT,
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
        PRIMARY KEY (id),
        FOREIGN KEY (owner_id) REFERENCES user (id),
        FOREIGN KEY (sales_lead_id) REFERENCES sales_leads (id)
    )
''')
print('1. 创建新表 (正确的NULL约束)')

# Copy data
cursor.execute('INSERT INTO pipeline_new SELECT * FROM pipeline')
print('2. 复制数据')

# Drop old table
cursor.execute('DROP TABLE pipeline')
print('3. 删除旧表')

# Rename
cursor.execute('ALTER TABLE pipeline_new RENAME TO pipeline')
print('4. 重命名新表')

# Recreate indexes
cursor.execute('CREATE INDEX ix_pipeline_owner_id ON pipeline (owner_id)')
cursor.execute('CREATE INDEX ix_pipeline_sales_lead_id ON pipeline (sales_lead_id)')
cursor.execute('CREATE INDEX ix_pipeline_est_act_date ON pipeline (est_act_date)')
cursor.execute('CREATE INDEX ix_pipeline_stage ON pipeline (stage)')
print('5. 重建索引')

conn.commit()

# Verify
cursor.execute('PRAGMA table_info(pipeline)')
print('\n验证 - 字段NULL约束:')
for col in cursor.fetchall():
    if col[1] in nullable_columns or col[1] in ['id', 'owner_id', 'contract_term_yrs', 'date_added', 'created_at', 'updated_at']:
        print(f'  {col[1]}: nullable={col[3]}')

conn.close()
print('\n完成！所有可选字段现在允许 NULL')
