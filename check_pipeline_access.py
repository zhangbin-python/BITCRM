import sqlite3

conn = sqlite3.connect(r'instance\bitcrm.db')
cursor = conn.cursor()

# Get user ID for Cean
cursor.execute("SELECT id, username, role FROM users WHERE username = 'Cean'")
cean = cursor.fetchone()
print(f'Cean: {cean}')
cean_id = cean[0]
print()

# Pipelines where Cean is owner
cursor.execute(f'''
    SELECT p.id, p.name, p.company, p.owner_id, u.username
    FROM pipeline p
    JOIN users u ON p.owner_id = u.id
    WHERE p.owner_id = {cean_id}
''')
owned = cursor.fetchall()
print(f'=== Pipelines owned by Cean ({len(owned)}) ===')
for p in owned:
    print(f'  ID={p[0]}: {p[1]} ({p[2]}) - Owner: {p[4]}')
print()

# Pipelines where Cean is in support team
cursor.execute(f'''
    SELECT p.id, p.name, p.company, p.owner_id, u.username
    FROM pipeline p
    JOIN pipeline_support ps ON p.id = ps.pipeline_id
    JOIN users u ON p.owner_id = u.id
    WHERE ps.user_id = {cean_id}
''')
supported = cursor.fetchall()
print(f'=== Pipelines where Cean is in support team ({len(supported)}) ===')
for p in supported:
    print(f'  ID={p[0]}: {p[1]} ({p[2]}) - Owner: {p[4]}')
print()

# Pipelines owned by Eric
cursor.execute("SELECT id, username, role FROM users WHERE username = 'Eric'")
eric = cursor.fetchone()
print(f'Eric: {eric}')
eric_id = eric[0]
cursor.execute(f'''
    SELECT p.id, p.name, p.company
    FROM pipeline p
    WHERE p.owner_id = {eric_id}
''')
eric_pipelines = cursor.fetchall()
print(f'=== Pipelines owned by Eric ({len(eric_pipelines)}) ===')
for p in eric_pipelines:
    print(f'  ID={p[0]}: {p[1]} ({p[2]})')
print()

# Check if Eric is in Cean's support (or vice versa)
print('=== Checking support relationships ===')
cursor.execute('''
    SELECT ps.pipeline_id, p.name, ps.user_id, u.username
    FROM pipeline_support ps
    JOIN pipeline p ON ps.pipeline_id = p.id
    JOIN users u ON ps.user_id = u.id
    WHERE p.owner_id = (SELECT id FROM users WHERE username = 'Eric')
''')
eric_supports = cursor.fetchall()
print(f'People in Eric pipeline support teams:')
for s in eric_supports:
    print(f'  Pipeline {s[0]} ({s[1]}): {s[3]} (user_id={s[2]})')
print()

conn.close()
