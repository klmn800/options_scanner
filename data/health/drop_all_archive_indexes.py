#!/usr/bin/env python3
"""Drop all secondary indexes from all sector archive databases.

Safe to run anytime — only drops user-created indexes, not PK-backing autoindexes.
Skips archives that fail to open (e.g. corrupted).
"""

import os
import sys
import sqlite3
import time

ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sector_archive')


def drop_indexes(db_path):
    db_name = os.path.basename(db_path)
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
        indexes = cursor.fetchall()

        if not indexes:
            print(f"  {db_name}: no secondary indexes")
            conn.close()
            return 0

        for idx_name, tbl_name in indexes:
            cursor.execute(f"DROP INDEX IF EXISTS [{idx_name}]")

        conn.commit()
        conn.close()
        print(f"  {db_name}: dropped {len(indexes)} indexes")
        return len(indexes)

    except Exception as e:
        print(f"  {db_name}: SKIPPED — {e}")
        return 0


def main():
    print(f"Dropping secondary indexes from all sector archives")
    print(f"Archive directory: {ARCHIVE_DIR}\n")

    db_files = sorted([
        os.path.join(ARCHIVE_DIR, f)
        for f in os.listdir(ARCHIVE_DIR)
        if f.endswith('.db')
    ])

    total_dropped = 0
    start = time.time()

    for db_path in db_files:
        total_dropped += drop_indexes(db_path)

    elapsed = time.time() - start
    print(f"\nDone: {total_dropped} indexes dropped across {len(db_files)} archives ({elapsed:.0f}s)")


if __name__ == "__main__":
    main()
