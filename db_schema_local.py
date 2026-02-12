import sqlite3

conn = sqlite3.connect(r'C:\Users\zhang\clawd\BITCRM\instance\bitcrm.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cursor.fetchall()
print('='*70)
print('DB Tables')
print('='*70)
for t in tables:
    print(f'  - {t[0]}')
print()

# Get table schema
for table in [t[0] for t in tables]:
    print(f'\n{"="*70}')
    print(f'Table: {table}')
    print('='*70)
    cursor.execute(f'PRAGMA table_info({table})')
    columns = cursor.fetchall()
    print(f'   Column{" "*26} Type')
    print('-'*70)
    for col in columns:
        pk = '[PK]' if col[5] else '   '
        print(f'   {pk} {col[1]:26} {col[2]}')
    
    cursor.execute(f'PRAGMA foreign_key_list({table})')
    fks = cursor.fetchall()
    if fks:
        print('\n   Foreign Keys:')
        for fk in fks:
            print(f'      {fk[3]} -> {fk[2]}.{fk[4]}')

conn.close()
print('\n' + '='*70)
