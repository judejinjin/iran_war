import sqlite3
import json
from datetime import datetime, timedelta

conn = sqlite3.connect('db/oil_data.db')
c = conn.cursor()

# Get today's futures data
c.execute("SELECT * FROM futures_curves WHERE date = '2026-05-28' ORDER BY symbol, contract_month")
rows = c.fetchall()

if not rows:
    # Try recent dates
    c.execute("SELECT DISTINCT date FROM futures_curves ORDER BY date DESC LIMIT 5")
    dates = [r[0] for r in c.fetchall()]
    print(f"No data for 2026-05-28. Available dates: {dates}")
    if dates:
        c.execute(f"SELECT * FROM futures_curves WHERE date = '{dates[0]}' ORDER BY symbol, contract_month")
        rows = c.fetchall()

c.execute("PRAGMA table_info(futures_curves)")
cols = [col[1] for col in c.fetchall()]

result = [dict(zip(cols, row)) for row in rows]

# Group by symbol
cl_data = [r for r in result if r['symbol'] == 'CL']
coil_data = [r for r in result if r['symbol'] == 'COIL']

print(f"Date: {result[0]['date'] if result else 'N/A'}")
print(f"\nCL (WTI) front contracts:")
for contract in cl_data[:6]:
    print(f"  {contract['contract_month']}: ${contract['settlement_price']:.2f}")

print(f"\nCOIL (Brent) front contracts:")
for contract in coil_data[:6]:
    print(f"  {contract['contract_month']}: ${contract['settlement_price']:.2f}")

# Calculate curve shape
if len(cl_data) >= 2:
    cl_front = cl_data[0]['settlement_price']
    cl_6m = cl_data[5]['settlement_price'] if len(cl_data) > 5 else cl_data[-1]['settlement_price']
    cl_shape = "BACKWARDATION" if cl_front > cl_6m else "CONTANGO"
    cl_spread = cl_front - cl_6m
    print(f"\nCL curve: {cl_shape} (M1-M6: ${cl_spread:.2f})")

if len(coil_data) >= 2:
    coil_front = coil_data[0]['settlement_price']
    coil_6m = coil_data[5]['settlement_price'] if len(coil_data) > 5 else coil_data[-1]['settlement_price']
    coil_shape = "BACKWARDATION" if coil_front > coil_6m else "CONTANGO"
    coil_spread = coil_front - coil_6m
    print(f"COIL curve: {coil_shape} (M1-M6: ${coil_spread:.2f})")

print(f"\nBrent front month: ${coil_data[0]['settlement_price']:.2f}" if coil_data else "No COIL data")

conn.close()
