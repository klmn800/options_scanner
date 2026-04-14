"""Apply the max_pain_analysis view to utilities.db with baselines."""

import sqlite3
import sys

db_path = 'data/sector_archive/utilities.db'
sql_file = 'research/utilities_create_max_pain_view.sql'

with open(sql_file, 'r') as f:
    sql = f.read()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Execute the SQL
cursor.executescript(sql)

print("View created successfully")

# Test query
cursor.execute("SELECT COUNT(*) FROM max_pain_analysis")
count = cursor.fetchone()[0]
print(f"View contains {count} rows")

# Show sample
cursor.execute("""
SELECT symbol, COUNT(*) as weeks, SUM(hit_max_pain_1pct) as hits
FROM max_pain_analysis
GROUP BY symbol
ORDER BY symbol
""")

print("\nSymbol coverage:")
print("Symbol | Weeks | Hits")
print("-------|-------|-----")
for row in cursor.fetchall():
    print(f"{row[0]:6s} | {row[1]:5d} | {row[2]:4d}")

conn.close()
