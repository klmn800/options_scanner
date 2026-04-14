"""Apply the updated max_pain_analysis view with baselines."""

import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/sector_archive/airlines.db'

with open('research/create_max_pain_view_with_baselines.sql', 'r') as f:
    sql = f.read()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Execute the SQL
cursor.executescript(sql)

print("View updated successfully")

# Test query
cursor.execute("SELECT COUNT(*) FROM max_pain_analysis")
count = cursor.fetchone()[0]
print(f"View contains {count} rows")

conn.close()
