#!/usr/bin/env python3
"""
One-Time Technology Sector Archive Split Migration
---------------------------------------------------
Migrates historical data from technology.db into semiconductors.db and software.db.

Symbol routing has already been updated in symbol_metadata.archive_db.
This script moves the existing archived data to match.

Usage:
    python data/health/migrate_technology_split.py --dry-run    # Preview row counts
    python data/health/migrate_technology_split.py              # Execute migration
    python data/health/migrate_technology_split.py --vacuum     # Execute + VACUUM technology.db

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

# Paths
DATALAKE_PATH = os.path.join(project_root, 'data', 'datalake.db')
SECTOR_ARCHIVE_DIR = os.path.join(project_root, 'data', 'sector_archive')
TECHNOLOGY_DB = os.path.join(SECTOR_ARCHIVE_DIR, 'technology.db')

# Tables to migrate, ordered largest first for better progress visibility
MIGRATION_TABLES = [
    'flow_options_scans',       # ~64M total, ~35M to move
    'option_contracts',         # ~3.7M total, ~2M to move
    'flow_symbol_summary',
    'option_symbol_summary',
    'historical_prices',
    'flow_alerts',
    'earnings_events',
    'earnings_upcoming',
    'news_articles',
    'news_symbol_sentiment',
    'alert_contract_tracking',
    'symbol_metadata',
]

BATCH_SIZE = 50_000  # Rows per batch for large tables
BATCH_THRESHOLD = 100_000  # Tables with more rows than this use batched migration


def get_symbol_lists():
    """Read symbol lists from datalake.db symbol_metadata."""
    conn = sqlite3.connect(DATALAKE_PATH)
    cursor = conn.cursor()

    targets = {}
    for archive_name in ('semiconductors', 'software'):
        cursor.execute(
            "SELECT symbol FROM symbol_metadata WHERE archive_db = ? ORDER BY symbol",
            (archive_name,)
        )
        targets[archive_name] = [row[0] for row in cursor.fetchall()]

    conn.close()
    return targets


def configure_speed_connection(conn):
    """Apply PRAGMAs for bulk writes on HDD. WAL + NORMAL sync for crash safety."""
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -256000")  # 256 MB


def format_duration(seconds):
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f} min"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def count_rows(db_path, table_name, symbols):
    """Count rows in a table for a set of symbols."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    placeholders = ','.join(['?'] * len(symbols))

    # symbol_metadata uses 'symbol' column too
    try:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE symbol IN ({placeholders})",
            symbols
        )
        count = cursor.fetchone()[0]
    except sqlite3.OperationalError:
        count = 0
    conn.close()
    return count


def migrate_table_batched(source_path, target_path, table_name, symbols, dry_run=False):
    """Migrate rows for a set of symbols from source to target archive, using batches for large tables."""
    placeholders = ','.join(['?'] * len(symbols))

    # Count source rows
    source_count = count_rows(source_path, table_name, symbols)
    if source_count == 0:
        return 0, 0

    if dry_run:
        return source_count, 0

    # Get column names from source
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
    col_list = ', '.join(columns)
    insert_placeholders = ', '.join(['?'] * len(columns))

    use_batches = source_count > BATCH_THRESHOLD
    total_inserted = 0
    total_deleted = 0

    if use_batches:
        # Batched migration: SELECT/INSERT/DELETE in chunks
        batch_num = 0
        while True:
            batch_num += 1

            # SELECT batch from source (ORDER BY rowid for sequential reads)
            with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                src_conn.execute("PRAGMA busy_timeout = 30000")
                cursor = src_conn.cursor()
                cursor.execute(
                    f"SELECT {col_list} FROM {table_name} WHERE symbol IN ({placeholders}) ORDER BY rowid LIMIT ?",
                    symbols + [BATCH_SIZE]
                )
                rows = cursor.fetchall()

            if not rows:
                break

            # INSERT into target
            with sqlite3.connect(target_path, timeout=30.0) as tgt_conn:
                configure_speed_connection(tgt_conn)
                tgt_conn.executemany(
                    f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({insert_placeholders})",
                    rows
                )
                tgt_conn.commit()
            total_inserted += len(rows)

            # DELETE from source (same rows we just read — ORDER BY rowid LIMIT matches)
            with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                src_conn.execute("PRAGMA busy_timeout = 30000")
                cursor = src_conn.cursor()
                cursor.execute(
                    f"DELETE FROM {table_name} WHERE rowid IN "
                    f"(SELECT rowid FROM {table_name} WHERE symbol IN ({placeholders}) ORDER BY rowid LIMIT ?)",
                    symbols + [BATCH_SIZE]
                )
                total_deleted += cursor.rowcount
                src_conn.commit()

            # Progress
            pct = min(100.0, (total_deleted / source_count) * 100)
            timestamp = now_eastern().strftime('%H:%M:%S')
            print(f"      [{timestamp}] Batch {batch_num}: {len(rows):,} rows ({pct:.1f}%)")
    else:
        # Small table: single pass
        with sqlite3.connect(source_path, timeout=30.0) as src_conn:
            src_conn.execute("PRAGMA busy_timeout = 30000")
            cursor = src_conn.cursor()
            cursor.execute(
                f"SELECT {col_list} FROM {table_name} WHERE symbol IN ({placeholders})",
                symbols
            )
            rows = cursor.fetchall()

        if rows:
            with sqlite3.connect(target_path, timeout=30.0) as tgt_conn:
                configure_speed_connection(tgt_conn)
                tgt_conn.executemany(
                    f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({insert_placeholders})",
                    rows
                )
                tgt_conn.commit()
            total_inserted = len(rows)

            with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                src_conn.execute("PRAGMA busy_timeout = 30000")
                cursor = src_conn.cursor()
                cursor.execute(
                    f"DELETE FROM {table_name} WHERE symbol IN ({placeholders})",
                    symbols
                )
                total_deleted = cursor.rowcount
                src_conn.commit()

    return total_inserted, total_deleted


def main():
    parser = argparse.ArgumentParser(description='Migrate technology.db split into semiconductors + software')
    parser.add_argument('--dry-run', action='store_true', help='Preview row counts without migrating')
    parser.add_argument('--vacuum', action='store_true', help='VACUUM technology.db after migration')
    args = parser.parse_args()

    print("=" * 70)
    print("TECHNOLOGY SECTOR ARCHIVE SPLIT MIGRATION")
    print("=" * 70)
    print(f"Start Time: {now_eastern().strftime('%Y-%m-%d %H:%M:%S EST')}")
    print(f"Source: technology.db")
    print(f"Targets: semiconductors.db, software.db")
    print(f"Mode: {'DRY RUN (preview only)' if args.dry_run else 'LIVE MIGRATION'}")
    print("=" * 70)

    # Validate paths
    if not os.path.exists(TECHNOLOGY_DB):
        print(f"ERROR: technology.db not found at {TECHNOLOGY_DB}")
        sys.exit(1)

    # Get symbol lists
    targets = get_symbol_lists()
    for name, symbols in targets.items():
        target_path = os.path.join(SECTOR_ARCHIVE_DIR, f'{name}.db')
        if not os.path.exists(target_path):
            print(f"ERROR: {name}.db not found at {target_path}")
            sys.exit(1)
        print(f"\n  {name}: {len(symbols)} symbols")
        print(f"    {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")

    migration_start = time.time()
    grand_inserted = 0
    grand_deleted = 0

    # Process each target
    for target_name, symbols in targets.items():
        target_path = os.path.join(SECTOR_ARCHIVE_DIR, f'{target_name}.db')

        print(f"\n{'=' * 70}")
        print(f"MIGRATING TO {target_name.upper()}")
        print(f"{'=' * 70}")

        target_start = time.time()
        target_inserted = 0
        target_deleted = 0

        for table_name in MIGRATION_TABLES:
            source_count = count_rows(TECHNOLOGY_DB, table_name, symbols)
            if source_count == 0:
                continue

            print(f"\n  {table_name}: {source_count:,} rows")
            table_start = time.time()

            inserted, deleted = migrate_table_batched(
                TECHNOLOGY_DB, target_path, table_name, symbols, dry_run=args.dry_run
            )

            elapsed = time.time() - table_start
            if args.dry_run:
                print(f"    [dry-run] Would migrate {source_count:,} rows")
            else:
                print(f"    Done: {inserted:,} inserted, {deleted:,} deleted ({format_duration(elapsed)})")

            target_inserted += inserted
            target_deleted += deleted

        target_elapsed = time.time() - target_start
        print(f"\n  {target_name} COMPLETE: {target_inserted:,} inserted, {target_deleted:,} deleted ({format_duration(target_elapsed)})")
        grand_inserted += target_inserted
        grand_deleted += target_deleted

    # VACUUM technology.db to reclaim space
    if args.vacuum and not args.dry_run and grand_deleted > 0:
        print(f"\n{'=' * 70}")
        print("VACUUMING technology.db")
        print(f"{'=' * 70}")
        vacuum_start = time.time()
        size_before = os.path.getsize(TECHNOLOGY_DB)
        print(f"  Size before: {size_before / (1024**3):.1f} GB")

        with sqlite3.connect(TECHNOLOGY_DB) as conn:
            conn.execute("VACUUM")

        size_after = os.path.getsize(TECHNOLOGY_DB)
        vacuum_elapsed = time.time() - vacuum_start
        print(f"  Size after:  {size_after / (1024**3):.1f} GB")
        print(f"  Reclaimed:   {(size_before - size_after) / (1024**3):.1f} GB ({format_duration(vacuum_elapsed)})")

    # Summary
    total_elapsed = time.time() - migration_start
    print(f"\n{'=' * 70}")
    print("MIGRATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"Duration: {format_duration(total_elapsed)}")
    print(f"Total inserted: {grand_inserted:,}")
    print(f"Total deleted:  {grand_deleted:,}")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
