#!/usr/bin/env python3
"""
Repair corrupted option_contracts table in datalake.db.

Rebuilds ONLY the option_contracts table by:
1. Creating a temporary table with the same schema
2. Copying all readable rows via rowid scan (bypasses corrupt B-tree pages)
3. Dropping the corrupt original table
4. Renaming the repaired table into place
5. Recreating indexes

This is a targeted repair — all other tables in datalake.db are untouched.

Usage:
    python data/health/repair_option_contracts.py              # Full repair
    python data/health/repair_option_contracts.py --dry-run    # Preview damage assessment
    python data/health/repair_option_contracts.py --verify     # Verify after repair

Background: On 2026-04-07, HDD corruption hit 7 B-tree pages in option_contracts,
affecting ~35K rowids in the 23.3M-23.5M range (dates 2026-04-06 and 2026-04-07).
691 errors queued during evening OP pipeline run.

Author: Autofix Batch Mode (2026-04-07)
"""

import os
import sys
import sqlite3
import argparse
import time
from datetime import datetime

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

# Force UTF-8 encoding for Windows console
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

from timezone_utils import now_eastern

DB_PATH = os.path.join(project_root, 'data', 'datalake.db')
BATCH_SIZE = 50_000
TABLE_NAME = 'option_contracts'
TEMP_TABLE = 'option_contracts_repaired'


def format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f} min"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def format_size(bytes_val):
    if bytes_val < 1024**2:
        return f"{bytes_val / 1024:.0f} KB"
    elif bytes_val < 1024**3:
        return f"{bytes_val / (1024**2):.1f} MB"
    else:
        return f"{bytes_val / (1024**3):.1f} GB"


def get_create_statement(conn):
    """Get the CREATE TABLE statement for option_contracts."""
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_columns(conn):
    """Get column names for option_contracts."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
    return [row[1] for row in cursor.fetchall()]


def get_indexes(conn):
    """Get CREATE INDEX statements for option_contracts (excluding autoindex)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (TABLE_NAME,)
    )
    return cursor.fetchall()


def assess_damage(conn):
    """Scan the table to identify corrupt regions."""
    print("\nDamage Assessment:")
    print("-" * 50)

    # Get rowid range
    try:
        min_rowid = conn.execute(f"SELECT MIN(rowid) FROM {TABLE_NAME}").fetchone()[0]
        max_rowid = conn.execute(f"SELECT MAX(rowid) FROM {TABLE_NAME}").fetchone()[0]
        print(f"  Rowid range: {min_rowid:,} to {max_rowid:,}")
    except Exception as e:
        print(f"  Cannot read rowid range: {e}")
        return

    # Scan in 50K chunks
    total_readable = 0
    total_corrupt_chunks = 0
    corrupt_ranges = []

    chunk = 50_000
    for start in range(min_rowid, max_rowid + 1, chunk):
        end = min(start + chunk - 1, max_rowid)
        try:
            r = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE rowid BETWEEN ? AND ?",
                (start, end)
            ).fetchone()
            total_readable += r[0]
        except sqlite3.DatabaseError:
            total_corrupt_chunks += 1
            corrupt_ranges.append((start, end))

    print(f"  Readable rows: {total_readable:,}")
    print(f"  Corrupt 50K-chunks: {total_corrupt_chunks}")
    if corrupt_ranges:
        print(f"  Corrupt rowid ranges:")
        for s, e in corrupt_ranges:
            # Try to identify dates in surrounding readable data
            try:
                dates = conn.execute(
                    f"SELECT DISTINCT trade_date FROM {TABLE_NAME} WHERE rowid BETWEEN ? AND ? ORDER BY trade_date",
                    (s - 5000, s - 1)
                ).fetchall()
                date_str = ', '.join(d[0] for d in dates) if dates else 'unknown'
            except:
                date_str = 'unknown'
            print(f"    {s:,} - {e:,} (near dates: {date_str})")

    print(f"\n  Estimated data loss: {total_corrupt_chunks} chunks (sub-batch recovery will minimize loss)")
    return min_rowid, max_rowid, total_readable


def rebuild_table(conn, dry_run=False):
    """Rebuild option_contracts via rowid scan into a temp table."""
    columns = get_columns(conn)
    if not columns:
        print("ERROR: Cannot read column info")
        return 0, 0

    col_list = ', '.join(columns)
    placeholders = ', '.join(['?'] * len(columns))

    try:
        min_rowid = conn.execute(f"SELECT MIN(rowid) FROM {TABLE_NAME}").fetchone()[0] or 0
        max_rowid = conn.execute(f"SELECT MAX(rowid) FROM {TABLE_NAME}").fetchone()[0] or 0
    except:
        print("ERROR: Cannot read rowid range")
        return 0, 0

    if max_rowid == 0:
        print("  Table is empty")
        return 0, 0

    if dry_run:
        print(f"  Would scan rowids {min_rowid:,} to {max_rowid:,}")
        return 0, 0

    # Get CREATE TABLE statement and build temp table
    create_sql = get_create_statement(conn)
    if not create_sql:
        print("ERROR: Cannot read CREATE TABLE statement")
        return 0, 0

    # Create temp table with same schema
    # Handle both quoted ("option_contracts") and unquoted variants
    temp_create = create_sql
    for old_name in [f'"{TABLE_NAME}"', TABLE_NAME]:
        temp_create = temp_create.replace(
            f'CREATE TABLE IF NOT EXISTS {old_name}',
            f'CREATE TABLE "{TEMP_TABLE}"'
        ).replace(
            f'CREATE TABLE {old_name}',
            f'CREATE TABLE "{TEMP_TABLE}"'
        )
    conn.execute(f"DROP TABLE IF EXISTS {TEMP_TABLE}")
    conn.execute(temp_create)
    conn.commit()
    print(f"  Created temp table: {TEMP_TABLE}")

    # Copy data via rowid scan
    start_time = time.time()
    total_copied = 0
    total_skipped = 0
    current_rowid = min_rowid - 1

    while current_rowid < max_rowid:
        batch_start = current_rowid + 1
        batch_end = min(current_rowid + BATCH_SIZE, max_rowid)
        current_rowid = batch_end

        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {col_list} FROM {TABLE_NAME} WHERE rowid BETWEEN ? AND ? ORDER BY rowid",
                (batch_start, batch_end)
            )
            rows = cursor.fetchall()
        except sqlite3.DatabaseError:
            # Corrupt batch — try smaller sub-batches to recover what we can
            rows = []
            sub_size = BATCH_SIZE // 10
            sub_skipped = 0
            for sub_start in range(batch_start, batch_end + 1, sub_size):
                sub_end = min(sub_start + sub_size - 1, batch_end)
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT {col_list} FROM {TABLE_NAME} WHERE rowid BETWEEN ? AND ? ORDER BY rowid",
                        (sub_start, sub_end)
                    )
                    rows.extend(cursor.fetchall())
                except sqlite3.DatabaseError:
                    # Even smaller — try 500-row chunks
                    micro_size = 500
                    for micro_start in range(sub_start, sub_end + 1, micro_size):
                        micro_end = min(micro_start + micro_size - 1, sub_end)
                        try:
                            cursor = conn.cursor()
                            cursor.execute(
                                f"SELECT {col_list} FROM {TABLE_NAME} WHERE rowid BETWEEN ? AND ? ORDER BY rowid",
                                (micro_start, micro_end)
                            )
                            rows.extend(cursor.fetchall())
                        except sqlite3.DatabaseError:
                            sub_skipped += (micro_end - micro_start + 1)

            if sub_skipped > 0:
                total_skipped += sub_skipped
                ts = now_eastern().strftime('%H:%M:%S')
                print(f"    [{ts}] CORRUPT PAGES at rowid ~{batch_start:,} — recovered {len(rows):,}, skipped ~{sub_skipped:,} rowids")

        if rows:
            conn.executemany(
                f"INSERT OR IGNORE INTO {TEMP_TABLE} ({col_list}) VALUES ({placeholders})",
                rows
            )
            conn.commit()
            total_copied += len(rows)

        # Progress every 10 batches
        pct = min(100.0, ((current_rowid - min_rowid) / (max_rowid - min_rowid)) * 100) if max_rowid > min_rowid else 100
        batch_num = (current_rowid - min_rowid) // BATCH_SIZE
        if batch_num % 10 == 0 or current_rowid >= max_rowid:
            ts = now_eastern().strftime('%H:%M:%S')
            print(f"    [{ts}] {total_copied:,} rows ({pct:.0f}%)")

    duration = time.time() - start_time
    return total_copied, total_skipped, duration


def swap_tables(conn):
    """Drop corrupt original, rename repaired table."""
    print("\n  Swapping tables...")
    # Drop indexes first — corrupt table may resist DROP TABLE
    try:
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (TABLE_NAME,)
        ).fetchall():
            try:
                conn.execute(f"DROP INDEX IF EXISTS {row[0]}")
            except sqlite3.DatabaseError:
                pass
    except:
        pass

    # Try normal DROP, fall back to dropping via sqlite_master manipulation
    try:
        conn.execute(f'DROP TABLE "{TABLE_NAME}"')
    except sqlite3.DatabaseError:
        print("  DROP TABLE failed on corrupt table — using workaround...")
        # Close and reopen to ensure clean state, then try again
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
        conn.close()
        # Reopen and try with a fresh connection
        conn = sqlite3.connect(db_path, timeout=60)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA cache_size = -256000")
        try:
            conn.execute(f'DROP TABLE "{TABLE_NAME}"')
        except sqlite3.DatabaseError:
            # Last resort: rename repaired table to a usable name, leave corrupt one
            alt_name = TABLE_NAME + "_corrupt_20260407"
            print(f"  Cannot drop corrupt table. Renaming it to {alt_name}")
            try:
                conn.execute(f'ALTER TABLE "{TABLE_NAME}" RENAME TO "{alt_name}"')
            except sqlite3.DatabaseError:
                print("  Cannot rename either. Repaired data is in: {}".format(TEMP_TABLE))
                print("  Manual fix: open DB Browser, drop '{}', rename '{}' to '{}'".format(
                    TABLE_NAME, TEMP_TABLE, TABLE_NAME))
                conn.commit()
                return conn

    conn.execute(f'ALTER TABLE "{TEMP_TABLE}" RENAME TO "{TABLE_NAME}"')
    conn.commit()
    print(f"  Dropped corrupt {TABLE_NAME}, renamed {TEMP_TABLE} -> {TABLE_NAME}")
    return conn


def recreate_indexes(conn, indexes):
    """Recreate indexes on the repaired table."""
    if not indexes:
        print("  No secondary indexes to recreate")
        return
    for name, sql in indexes:
        try:
            conn.execute(sql)
            conn.commit()
            print(f"  Recreated index: {name}")
        except Exception as e:
            print(f"  WARNING: Failed to recreate index {name}: {e}")


def verify_repair(conn):
    """Verify the repaired table is functional."""
    print("\nVerification:")
    print("-" * 50)

    tests = [
        ("COUNT(*)", f"SELECT COUNT(*) FROM {TABLE_NAME}"),
        ("MAX(trade_date)", f"SELECT MAX(trade_date) FROM {TABLE_NAME}"),
        ("Recent dates", f"SELECT trade_date, COUNT(*) FROM {TABLE_NAME} GROUP BY trade_date ORDER BY trade_date DESC LIMIT 5"),
        ("Today's data", f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE trade_date = '{now_eastern().strftime('%Y-%m-%d')}'"),
    ]

    all_pass = True
    for label, sql in tests:
        try:
            r = conn.execute(sql).fetchall()
            print(f"  PASS: {label} = {r}")
        except Exception as e:
            print(f"  FAIL: {label} = {e}")
            all_pass = False

    # Integrity check on just this table (via a targeted query)
    try:
        conn.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY rowid LIMIT 1")
        conn.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY rowid DESC LIMIT 1")
        print(f"  PASS: Rowid scan endpoints")
    except Exception as e:
        print(f"  FAIL: Rowid scan endpoints = {e}")
        all_pass = False

    return all_pass


def main():
    parser = argparse.ArgumentParser(description='Repair corrupted option_contracts table in datalake.db')
    parser.add_argument('--dry-run', action='store_true', help='Damage assessment only, no changes')
    parser.add_argument('--verify', action='store_true', help='Verify existing table integrity')
    args = parser.parse_args()

    db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    print("=" * 60)
    print("OPTION CONTRACTS TABLE REPAIR")
    print("=" * 60)
    print(f"Database: {DB_PATH} ({format_size(db_size)})")
    print(f"Time: {now_eastern().strftime('%Y-%m-%d %H:%M:%S EST')}")
    if args.dry_run:
        print("Mode: DRY RUN (assessment only)")
    print()

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -256000")  # 256 MB

    if args.verify:
        success = verify_repair(conn)
        conn.close()
        print(f"\nResult: {'ALL PASS' if success else 'FAILURES DETECTED'}")
        sys.exit(0 if success else 1)

    # Step 1: Assess damage
    result = assess_damage(conn)
    if result is None:
        print("\nERROR: Cannot assess damage — table may be completely unreadable")
        conn.close()
        sys.exit(1)

    if args.dry_run:
        print("\nDry run complete. Run without --dry-run to repair.")
        conn.close()
        return

    # Step 2: Save index definitions before they're lost
    indexes = get_indexes(conn)
    print(f"\nIndexes to recreate: {len(indexes)}")
    for name, sql in indexes:
        print(f"  {name}")

    # Step 3: Rebuild into temp table
    print(f"\nRebuilding {TABLE_NAME} via rowid scan...")
    copied, skipped, duration = rebuild_table(conn)
    print(f"\n  Rebuild complete: {copied:,} rows in {format_duration(duration)}")
    if skipped > 0:
        print(f"  Skipped: ~{skipped:,} unreadable rowids")

    if copied == 0:
        print("\nERROR: Zero rows recovered — aborting swap")
        conn.execute(f"DROP TABLE IF EXISTS {TEMP_TABLE}")
        conn.commit()
        conn.close()
        sys.exit(1)

    # Step 4: Swap tables (may return new connection if reconnect was needed)
    result_conn = swap_tables(conn)
    if result_conn is not None:
        conn = result_conn

    # Step 5: Recreate indexes
    recreate_indexes(conn, indexes)

    # Step 6: Verify
    success = verify_repair(conn)

    # Step 7: VACUUM to reclaim space (optional, can be slow on HDD)
    print("\nSkipping VACUUM (run manually if needed: PRAGMA vacuum)")

    conn.close()

    print("\n" + "=" * 60)
    print(f"REPAIR {'COMPLETE' if success else 'COMPLETED WITH WARNINGS'}")
    print(f"  Rows recovered: {copied:,}")
    print(f"  Rows lost: ~{skipped:,}")
    print(f"  Duration: {format_duration(duration)}")
    print("=" * 60)


if __name__ == '__main__':
    main()
