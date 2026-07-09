import sqlite3

for db_file in ['db/oil_data.db', 'db/market_data.db', 'db/oil_markets.db']:
    try:
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        print(f"\n{db_file}:")
        print("Tables:", tables)
        
        if tables:
            # Check first table for structure
            t = tables[0]
            c.execute(f"PRAGMA table_info({t})")
            cols = [col[1] for col in c.fetchall()]
            print(f"  {t} columns: {cols}")
            c.execute(f"SELECT COUNT(*) FROM {t}")
            count = c.fetchone()[0]
            print(f"  {t} rows: {count}")
        
        conn.close()
    except Exception as e:
        print(f"Error with {db_file}: {e}")
