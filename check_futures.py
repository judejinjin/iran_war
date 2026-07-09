import sqlite3
import json

conn = sqlite3.connect('db/oil_war.db')
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# Try to find futures data in market data tables
for table_name in [t[0] for t in tables if 'future' in t[0].lower() or 'market' in t[0].lower() or 'price' in t[0].lower()]:
    print(f"\n{table_name}:")
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
    rows = cursor.fetchall()
    if rows:
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [col[1] for col in cursor.fetchall()]
        print("Columns:", cols)
        print("Sample data:", rows[0] if rows else "No data")

conn.close()
