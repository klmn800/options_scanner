#!/usr/bin/env python3
"""
Repair a corrupted sector archive by rebuilding it from scratch.

Reads all data via rowid scan (bypasses corrupted B-trees),
writes to a fresh database, then swaps files.

Usage:
    python data/health/repair_archive.py airlines              # Repair airlines.db
    python data/health/repair_archive.py financial_services     # Repair financial_services.db
    python data/health/repair_archive.py airlines --dry-run     # Preview without writing
    python data/health/repair_archive.py airlines --tables      # List tables and row counts

Author: Ben (with assistance from Claude)
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

ARCHIVE_DIR = os.path.join(project_root, 'data', 'sector_archive')
BATCH_SIZE = 50_000


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


def get_tables(db_path):
    """Get list of tables in the database."""
    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables


def get_create_statement(db_path, table_name):
    """Get the CREATE TABLE statement for a table."""
    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_columns(db_path, table_name):
    """Get column names for a table."""
    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    return columns


def get_max_rowid(db_path, table_name):
    """Get max rowid for a table. Returns 0 if empty or error."""
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX(rowid) FROM {table_name}")
        result = cursor.fetchone()[0]
        conn.close()
        return result or 0
    except sqlite3.DatabaseError:
        return -1  # Can't even get max rowid


def count_rows_safe(db_path, table_name):
    """Try COUNT(*), fall back to max rowid estimate if B-tree is corrupt."""
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        conn.close()
        return count, "exact"
    except sqlite3.DatabaseError:
        max_rid = get_max_rowid(db_path, table_name)
        if max_rid > 0:
            return max_rid, "~maxrowid"
        elif max_rid == 0:
            return 0, "empty"
        else:
            return -1, "unreadable"


def rebuild_table(source_path, target_conn, table_name, dry_run=False):
    """Rebuild a single table via rowid scan.

    Returns (rows_copied, rows_skipped, duration_seconds).
    """
    columns = get_columns(source_path, table_name)
    if not columns:
        print(f"    SKIP: no columns found")
        return 0, 0, 0

    col_list = ', '.join(columns)
    placeholders = ', '.join(['?'] * len(columns))
    max_rowid = get_max_rowid(source_path, table_name)

    if max_rowid == 0:
        print(f"    empty table")
        return 0, 0, 0
    if max_rowid == -1:
        print(f"    UNREADABLE — cannot access rowids")
        return 0, 0, 0

    if dry_run:
        count, method = count_rows_safe(source_path, table_name)
        print(f"    {count:,} rows ({method}), max rowid {max_rowid:,}")
        return 0, 0, 0

    start = time.time()
    total_copied = 0
    total_skipped = 0
    current_rowid = 0

    while current_rowid < max_rowid:
        batch_start = current_rowid + 1
        batch_end = current_rowid + BATCH_SIZE
        current_rowid = batch_end

        try:
            with sqlite3.connect(source_path, timeout=30) as src_conn:
                src_conn.execute("PRAGMA busy_timeout = 30000")
                cursor = src_conn.cursor()
                cursor.execute(
                    f"SELECT {col_list} FROM {table_name} WHERE rowid BETWEEN ? AND ?",
                    (batch_start, batch_end)
                )
                rows = cursor.fetchall()
        except sqlite3.DatabaseError:
            # Try smaller sub-batches
            rows = []
            sub_size = BATCH_SIZE // 10
            sub_skipped = 0
            for sub_start in range(batch_start, batch_end + 1, sub_size):
                sub_end = min(sub_start + sub_size - 1, batch_end)
                try:
                    with sqlite3.connect(source_path, timeout=30) as src_conn:
                        src_conn.execute("PRAGMA busy_timeout = 30000")
                        cursor = src_conn.cursor()
                        cursor.execute(
                            f"SELECT {col_list} FROM {table_name} WHERE rowid BETWEEN ? AND ?",
                            (sub_start, sub_end)
                        )
                        rows.extend(cursor.fetchall())
                except sqlite3.DatabaseError:
                    sub_skipped += sub_size
            if sub_skipped:
                total_skipped += sub_skipped
                timestamp = now_eastern().strftime('%H:%M:%S')
                print(f"      [{timestamp}] CORRUPT PAGES — recovered {len(rows):,}, skipped ~{sub_skipped:,} rowids")

        if not rows:
            continue

        target_conn.executemany(
            f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({placeholders})",
            rows
        )
        target_conn.commit()
        total_copied += len(rows)

        # Progress every 10 batches
        pct = min(100.0, (current_rowid / max_rowid) * 100)
        batch_num = current_rowid // BATCH_SIZE
        if batch_num % 10 == 0 or current_rowid >= max_rowid:
            timestamp = now_eastern().strftime('%H:%M:%S')
            print(f"      [{timestamp}] {total_copied:,} rows ({pct:.0f}%)")

    duration = time.time() - start
    return total_copied, total_skipped, duration


def main():
    parser = argparse.ArgumentParser(description='Repair a corrupted sector archive')
    parser.add_argument('archive', help='Archive name (e.g. airlines, financial_services)')
    parser.add_argument('--dry-run', action='store_true', help='Preview tables and row counts without repairing')
    parser.add_argument('--tables', action='store_true', help='List tables only')
    parser.add_argument('--no-swap', action='store_true', help='Build repaired DB but do not swap files')
    args = parser.parse_args()

    archive_name = args.archive.replace('.db', '')
    source_path = os.path.join(ARCHIVE_DIR, f'{archive_name}.db')
    repair_path = os.path.join(ARCHIVE_DIR, f'{archive_name}_repaired.db')
    backup_path = os.path.join(ARCHIVE_DIR, f'{archive_name}_corrupt.bak')

    if not os.path.exists(source_path):
        print(f"ERROR: {source_path} not found")
        sys.exit(1)

    source_size = os.path.getsize(source_path)
    print("=" * 60)
    print(f"SECTOR ARCHIVE REPAIR: {archive_name}.db")
    print("=" * 60)
    print(f"Source: {source_path} ({format_size(source_size)})")
    print(f"Time: {now_eastern().strftime('%Y-%m-%d %H:%M:%S EST')}")
    if args.dry_run:
        print("Mode: DRY RUN")
    print()

    # Get tables
    tables = [t for t in get_tables(source_path) if not t.startswith('sqlite_')]
    print(f"Tables found: {len(tables)}")

    if args.tables:
        for table in tables:
            count, method = count_rows_safe(source_path, table)
            print(f"  {table}: {count:,} rows ({method})")
        return

    if args.dry_run:
        print("\nDry run — scanning tables:\n")
        for table in tables:
            print(f"  {table}:")
            columns = get_columns(source_path, table)
            print(f"    {len(columns)} columns")
            rebuild_table(source_path, None, table, dry_run=True)
        print("\nDry run complete. Run without --dry-run to repair.")
        return

    # Remove leftover repair file if exists
    if os.path.exists(repair_path):
        os.remove(repair_path)
        print(f"Removed leftover {os.path.basename(repair_path)}")

    # Create fresh target database
    print(f"\nCreating fresh database: {os.path.basename(repair_path)}")
    target_conn = sqlite3.connect(repair_path, timeout=30)
    target_conn.execute("PRAGMA busy_timeout = 30000")
    target_conn.execute("PRAGMA journal_mode = WAL")
    target_conn.execute("PRAGMA synchronous = NORMAL")
    target_conn.execute("PRAGMA cache_size = -256000")

    # Create all tables with schema from source
    for table in tables:
        create_sql = get_create_statement(source_path, table)
        if create_sql:
            target_conn.execute(create_sql)
            target_conn.commit()

    # Rebuild each table
    total_copied = 0
    total_skipped = 0
    repair_start = time.time()

    for table in tables:
        print(f"\n  {table}:")
        copied, skipped, duration = rebuild_table(source_path, target_conn, table)
        total_copied += copied
        total_skipped += skipped
        if copied > 0:
            print(f"    Done: {copied:,} rows in {format_duration(duration)}")
            if skipped > 0:
                print(f"    WARNING: ~{skipped:,} rowids skipped (corrupt pages)")
        elif duration > 0:
            print(f"    0 rows (empty)")

    target_conn.close()

    repair_duration = time.time() - repair_start
    repair_size = os.path.getsize(repair_path)

    print(f"\n{'=' * 60}")
    print(f"REPAIR COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Rows copied:  {total_copied:,}")
    print(f"  Rows skipped: {total_skipped:,}")
    print(f"  Duration:     {format_duration(repair_duration)}")
    print(f"  Source size:  {format_size(source_size)}")
    print(f"  Repair size:  {format_size(repair_size)}")

    if args.no_swap:
        print(f"\n  --no-swap: repaired file at {repair_path}")
        print(f"  To swap manually:")
        print(f"    mv \"{source_path}\" \"{backup_path}\"")
        print(f"    mv \"{repair_path}\" \"{source_path}\"")
        return

    # Swap files — retry up to 3 times if file is locked
    print(f"\n  Swapping files...")
    if os.path.exists(backup_path):
        os.remove(backup_path)

    # Remove any WAL/SHM/journal files from the corrupt source
    for suffix in ['-wal', '-shm', '-journal']:
        sidecar = source_path + suffix
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
                print(f"  Removed {os.path.basename(sidecar)}")
            except PermissionError:
                print(f"  WARNING: Could not remove {os.path.basename(sidecar)} (locked) — will retry after swap")

    for attempt in range(3):
        try:
            os.rename(source_path, backup_path)
            os.rename(repair_path, source_path)
            break
        except PermissionError:
            if attempt < 2:
                print(f"  File locked, retrying in 5s... (attempt {attempt + 2}/3)")
                time.sleep(5)
            else:
                print(f"\n  ERROR: File is locked by another process.")
                print(f"  Repaired data is safe at: {os.path.basename(repair_path)}")
                print(f"  Swap manually when the lock clears:")
                print(f"    mv \"{source_path}\" \"{backup_path}\"")
                print(f"    mv \"{repair_path}\" \"{source_path}\"")
                return

    # Remove WAL/SHM from repaired file (now at source_path)
    for suffix in ['-wal', '-shm']:
        sidecar = source_path + suffix
        if os.path.exists(sidecar):
            os.remove(sidecar)

    print(f"  Corrupt file backed up to: {os.path.basename(backup_path)}")
    print(f"  Repaired file now at:      {os.path.basename(source_path)}")
    print(f"\n  Verify with: python data/health/check_archive_integrity.py")


if __name__ == "__main__":
    main()
