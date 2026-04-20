import sqlite3

conn = sqlite3.connect('schaefer.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("[OK] Database tables created:")
for table in tables:
    print(f"  - {table[0]}")
    
    # Get column info for each table
    cursor.execute(f"PRAGMA table_info({table[0]});")
    columns = cursor.fetchall()
    print(f"    Columns: {', '.join([col[1] for col in columns])}")

conn.close()
