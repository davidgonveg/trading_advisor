from data.storage.database import Database
from datetime import datetime, timezone

db = Database()
conn = db.get_connection()
cursor = conn.cursor()

# Check for data on 2026-02-02
query = """
SELECT symbol, timestamp, open, high, low, close, volume
FROM market_data
WHERE symbol IN ('GLD', 'XLK')
AND date(timestamp) = '2026-02-02'
ORDER BY symbol, timestamp
"""

cursor.execute(query)
rows = cursor.fetchall()

if rows:
    print(f"Found {len(rows)} bars for 2026-02-02:")
    for row in rows:
        print(f"  {row[0]} | {row[1]} | O:{row[2]} H:{row[3]} L:{row[4]} C:{row[5]} V:{row[6]}")
else:
    print("NO DATA FOUND for 2026-02-02")
    
    # Check what's the latest data we have
    cursor.execute("""
        SELECT symbol, MAX(timestamp) as latest
        FROM market_data
        WHERE symbol IN ('GLD', 'XLK')
        GROUP BY symbol
    """)
    latest = cursor.fetchall()
    print("\nLatest data available:")
    for row in latest:
        print(f"  {row[0]}: {row[1]}")

conn.close()
