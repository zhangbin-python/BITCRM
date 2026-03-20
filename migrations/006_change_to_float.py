"""Change pipeline numeric columns from INTEGER to FLOAT (4 decimal places)"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

import sqlite3

db_path = os.path.join(current_dir, '..', 'instance', 'bitcrm.db')
if not os.path.exists(db_path):
    db_path = os.path.join(current_dir, 'instance', 'bitcrm.db')
db_path = os.path.abspath(db_path)

print('=' * 50)
print('修改 pipeline 数值字段为 FLOAT (4位小数)')
print('=' * 50)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Columns to change from INTEGER to FLOAT
float_columns = {
    'tcv_usd': 'FLOAT',
    'mrc_usd': 'FLOAT',
    'otc_usd': 'FLOAT',
    'gp_margin': 'FLOAT',
    'gp': 'FLOAT',
}

# Backup data
cursor.execute('CREATE TABLE IF NOT EXISTS pipeline_backup AS SELECT * FROM pipeline')
print('1. 创建备份表')

# Drop original table
cursor.execute('DROP TABLE pipeline')
print('2. 删除原表')

# Create new table with FLOAT columns
cursor.execute('''
    CREATE TABLE pipeline (
        id INTEGER NOT NULL,
        name TEXT,
        company VARCHAR(200),
        industry VARCHAR(100),
        position VARCHAR(100),
        email VARCHAR(120),
        mobile_number VARCHAR(50),
        owner_id INTEGER,
        sales_lead_id INTEGER,
        product VARCHAR(200),
        tcv_usd FLOAT,
        contract_term_yrs INTEGER,
        mrc_usd FLOAT,
        otc_usd FLOAT,
        gp_margin FLOAT,
        gp FLOAT,
        mg VARCHAR(50),
        est_sign_date DATE,
        est_act_date DATE,
        award_date DATE,
        proposal_sent_date DATE,
        win_rate FLOAT,
        stage VARCHAR(50),
        level VARCHAR(50),
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
print('3. 创建新表 (FLOAT)')

# Copy data with rounding to 4 decimal places
columns = ['tcv_usd', 'mrc_usd', 'otc_usd', 'gp_margin', 'gp']
for col in columns:
    cursor.execute(f'UPDATE pipeline_backup SET {col} = ROUND({col}, 4)')
print('4. 数值四舍五入到4位小数')

# Restore data
cursor.execute('INSERT INTO pipeline SELECT * FROM pipeline_backup')
print('5. 恢复数据')

# Clean up
cursor.execute('DROP TABLE pipeline_backup')
print('6. 删除备份表')

conn.commit()

# Verify
cursor.execute('PRAGMA table_info(pipeline)')
print('\n验证 - 字段类型:')
for col in cursor.fetchall():
    if col[1] in ['tcv_usd', 'mrc_usd', 'otc_usd', 'gp_margin', 'gp']:
        print(f'  {col[1]}: {col[2]}')

conn.close()
print('\n完成！数值字段现在使用 FLOAT (4位小数)')
