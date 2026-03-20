"""Add award_date and proposal_sent_date to pipeline table"""
import sys
import os
import sqlite3

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
bitcrm_dir = os.path.dirname(current_dir)
sys.path.insert(0, bitcrm_dir)

# Direct SQLite connection
db_path = os.path.join(bitcrm_dir, 'instance', 'bitcrm.db')

print('=' * 50)
print('添加 award_date 和 proposal_sent_date 字段')
print('=' * 50)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check columns
cursor.execute('PRAGMA table_info(pipeline)')
columns = [c[1] for c in cursor.fetchall()]

if 'award_date' in columns:
    print('award_date 已存在，跳过')
else:
    cursor.execute('ALTER TABLE pipeline ADD COLUMN award_date DATE')
    print('添加 award_date 字段')

if 'proposal_sent_date' in columns:
    print('proposal_sent_date 已存在，跳过')
else:
    cursor.execute('ALTER TABLE pipeline ADD COLUMN proposal_sent_date DATE')
    print('添加 proposal_sent_date 字段')

conn.commit()

# Verify
cursor.execute('PRAGMA table_info(pipeline)')
columns = [c[1] for c in cursor.fetchall()]
print(f'\n当前 pipeline 表字段: {len(columns)}')
print(f'award_date: {"award_date" in columns}')
print(f'proposal_sent_date: {"proposal_sent_date" in columns}')

conn.close()
print('\n完成！')
