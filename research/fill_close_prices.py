"""Fill missing close_price values in option_symbol_summary from historical_prices."""

import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/sector_archive/airlines.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get rows with missing close_price
cursor.execute("""
    SELECT symbol, trade_date
    FROM option_symbol_summary
    WHERE close_price IS NULL
    ORDER BY trade_date, symbol
""")

missing = cursor.fetchall()
print(f"Found {len(missing)} rows with missing close_price")

# Update each one
updated = 0
skipped = 0

for symbol, trade_date in missing:
    # Get close price from historical_prices
    cursor.execute("""
        SELECT close_price
        FROM historical_prices
        WHERE symbol = ? AND trade_date = ?
    """, (symbol, trade_date))

    result = cursor.fetchone()

    if result and result[0] is not None:
        close_price = result[0]
        cursor.execute("""
            UPDATE option_symbol_summary
            SET close_price = ?
            WHERE symbol = ? AND trade_date = ?
        """, (close_price, symbol, trade_date))
        updated += 1
        print(f"Updated {symbol} {trade_date}: {close_price}")
    else:
        skipped += 1
        print(f"Skipped {symbol} {trade_date}: no price data (likely weekend/holiday)")

conn.commit()
conn.close()

print(f"\nSummary:")
print(f"  Updated: {updated}")
print(f"  Skipped: {skipped} (no price data available)")
