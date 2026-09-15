import sqlite3, sys, os
sys.path.insert(0, '.')
conn = sqlite3.connect('data/sscp.db')
cur = conn.cursor()
cur.execute("PRAGMA table_info(settings)")
cols = [r[1] for r in cur.fetchall()]
print('Current settings columns:', cols)
if 'doctor_logo_path' not in cols:
    cur.execute('ALTER TABLE settings ADD COLUMN doctor_logo_path TEXT')
    print('Added doctor_logo_path column')
else:
    print('Column already exists')
conn.commit()
conn.close()
print('Done.')
