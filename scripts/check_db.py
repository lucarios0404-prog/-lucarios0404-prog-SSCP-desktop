import sqlite3

conn = sqlite3.connect('data/sscp.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print('Tables:', cursor.fetchall())
cursor.execute("SELECT email, role, is_active FROM users;")
print('Users:', cursor.fetchall())
