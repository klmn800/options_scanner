#!/usr/bin/env python3
"""
Paper Trading — One-Shot Migration: datalake.db → paper.db
==========================================================
Phase B prereq. Moves paper_executions, paper_positions, and
paper_account_snapshots from data/datalake.db into a dedicated
data/paper.db file.

Motivation
----------
State A acceptance test (2026-05-19) confirmed that Flow Monitor's
concurrent writes to data/datalake.db can exceed the 10s SQLite
busy_timeout used by paper_trading.py — triggering "database is locked"
errors during peak FM scan bursts. The Phase B close engine writes
every 2 min, so contention will only get worse. Isolating the paper_*
tables into their own DB eliminates that risk entirely.

Behavior
--------
1. Creates data/paper.db (if not present) with the full paper_* schema
   via paper_trading._ensure_schema(). Idempotent.
2. For each of the three paper_* tables: SELECT every row from
   datalake.db, INSERT into paper.db preserving primary-key IDs.
   Uses INSERT OR IGNORE so re-runs are safe.
3. Reports row counts on both sides.
4. By default, leaves the source tables in data/datalake.db intact
   (read-only safety copy). Pass --drop-source to remove them after
   verifying the migration.

Idempotent — re-running on an already-migrated DB no-ops.

Usage
-----
    python tools/paper_migrate_to_paper_db.py          # dry copy + report
    python tools/paper_migrate_to_paper_db.py --drop-source  # remove source tables
    python tools/paper_migrate_to_paper_db.py --verify-only  # no copy, just report
"""

import argparse
import os
import sqlite3
import sys

# Project root + import shims
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import paper_trading  # noqa: E402

SOURCE_DB = os.path.join(project_root, 'data', 'datalake.db')
TARGET_DB = os.path.join(project_root, 'data', 'paper.db')

PAPER_TABLES = ('paper_executions', 'paper_positions', 'paper_account_snapshots')


def _table_exists(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _row_count(conn, table_name):
    if not _table_exists(conn, table_name):
        return None
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0]


def _column_names(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def _copy_table(src_conn, dst_conn, table_name):
    """SELECT every row from src, INSERT OR IGNORE into dst preserving columns."""
    if not _table_exists(src_conn, table_name):
        print(f"  {table_name}: source table missing, skipped")
        return 0

    src_cur = src_conn.cursor()
    src_cur.execute(f"SELECT * FROM {table_name}")
    rows = src_cur.fetchall()
    if not rows:
        print(f"  {table_name}: 0 source rows, nothing to copy")
        return 0

    cols = _column_names(src_conn, table_name)
    placeholders = ','.join(['?'] * len(cols))
    col_list = ','.join(cols)
    sql = f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({placeholders})"

    dst_cur = dst_conn.cursor()
    inserted = 0
    for row in rows:
        dst_cur.execute(sql, tuple(row))
        if dst_cur.rowcount > 0:
            inserted += 1
    dst_conn.commit()

    print(f"  {table_name}: {len(rows)} source rows, {inserted} inserted (rest already present)")
    return inserted


def main():
    parser = argparse.ArgumentParser(description='Migrate paper_* tables to data/paper.db')
    parser.add_argument('--drop-source', action='store_true',
                        help='Drop paper_* tables from datalake.db after migration (default: leave intact)')
    parser.add_argument('--verify-only', action='store_true',
                        help='No copy, just report row counts on both sides')
    args = parser.parse_args()

    if not os.path.exists(SOURCE_DB):
        print(f"ERROR: source DB not found: {SOURCE_DB}")
        return 1

    print(f"Source: {SOURCE_DB}")
    print(f"Target: {TARGET_DB}")
    print()

    # Ensure target schema exists (no-op if already there)
    target_conn = sqlite3.connect(TARGET_DB, timeout=10)
    target_conn.row_factory = sqlite3.Row
    paper_trading._ensure_schema(target_conn)

    source_conn = sqlite3.connect(SOURCE_DB, timeout=10)
    source_conn.row_factory = sqlite3.Row

    if args.verify_only:
        print("Row counts (--verify-only):")
        for tbl in PAPER_TABLES:
            src = _row_count(source_conn, tbl)
            dst = _row_count(target_conn, tbl)
            print(f"  {tbl}: source={src}, target={dst}")
        source_conn.close()
        target_conn.close()
        return 0

    print("Copying rows (INSERT OR IGNORE — re-runs are safe):")
    for tbl in PAPER_TABLES:
        _copy_table(source_conn, target_conn, tbl)
    print()

    print("Post-migration row counts:")
    for tbl in PAPER_TABLES:
        src = _row_count(source_conn, tbl)
        dst = _row_count(target_conn, tbl)
        match = "OK" if src == dst else "MISMATCH"
        print(f"  {tbl}: source={src}, target={dst}  [{match}]")
    print()

    if args.drop_source:
        # Verify counts match before dropping
        mismatches = []
        for tbl in PAPER_TABLES:
            src = _row_count(source_conn, tbl)
            dst = _row_count(target_conn, tbl)
            if src != dst:
                mismatches.append((tbl, src, dst))
        if mismatches:
            print("ERROR: refusing to --drop-source because of count mismatches:")
            for tbl, src, dst in mismatches:
                print(f"  {tbl}: source={src}, target={dst}")
            source_conn.close()
            target_conn.close()
            return 2

        print("Dropping paper_* tables from datalake.db (--drop-source):")
        cur = source_conn.cursor()
        for tbl in PAPER_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {tbl}")
            print(f"  dropped {tbl}")
        source_conn.commit()
        print()
        print("Source tables dropped. Future paper_* writes go to data/paper.db only.")
    else:
        print("Source tables left intact (no --drop-source). Run again with --drop-source")
        print("after one day of clean operation against paper.db to clean up.")

    source_conn.close()
    target_conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
