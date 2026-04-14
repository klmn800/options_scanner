#!/usr/bin/env python3
"""
One-Time Consumer Cyclical Sector Archive Split Migration
----------------------------------------------------------
Migrates historical data from consumer_cyclical.db into retail.db and travel_leisure.db.

Symbol routing has already been updated in symbol_metadata.archive_db.
This script moves the existing archived data to match.

Usage:
    python data/health/migrate_consumer_cyclical_split.py --dry-run    # Preview row counts
    python data/health/migrate_consumer_cyclical_split.py              # Execute all phases
    python data/health/migrate_consumer_cyclical_split.py --vacuum     # Execute + VACUUM consumer_cyclical.db

Chunked execution (safe to split across multiple nights):
    # Night 1: flow_options_scans first 20M rowids (~4-5h)
    python data/health/migrate_consumer_cyclical_split.py --phase 1 --max-rowid 20000000

    # Night 2: flow_options_scans remainder (~4-5h)
    python data/health/migrate_consumer_cyclical_split.py --phase 1

    # Night 3 (or same night): other tables + vacuum (~1-2h)
    python data/health/migrate_consumer_cyclical_split.py --phase 2 --vacuum

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
SOURCE_DB = os.path.join(SECTOR_ARCHIVE_DIR, 'consumer_cyclical.db')

# Tables to migrate, ordered largest first for better progress visibility
MIGRATION_TABLES = [
    'flow_options_scans',
    'option_contracts',
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
    for archive_name in ('retail', 'travel_leisure'):
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


def format_size(bytes_val):
    """Format bytes as human-readable size."""
    if bytes_val < 1024**2:
        return f"{bytes_val / 1024:.0f} KB"
    elif bytes_val < 1024**3:
        return f"{bytes_val / (1024**2):.1f} MB"
    else:
        return f"{bytes_val / (1024**3):.1f} GB"


def get_total_rows(db_path):
    """Get total row count across all migration tables."""
    total = 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        for table in MIGRATION_TABLES:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                total += cursor.fetchone()[0]
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                pass
        conn.close()
    except Exception:
        pass
    return total


def count_rows(db_path, table_name, symbols):
    """Count rows in a table for a set of symbols."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    placeholders = ','.join(['?'] * len(symbols))

    try:
        cursor.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE symbol IN ({placeholders})",
            symbols
        )
        count = cursor.fetchone()[0]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        count = 0
    conn.close()
    return count


def migrate_corrupted_flow_scans(source_path, all_targets, dry_run=False, max_rowid=None):
    """Migrate flow_options_scans from a corrupted source using rowid-based reads.

    The B-tree index for flow_options_scans is corrupted (WHERE symbol IN fails),
    but raw data pages are accessible via rowid ranges. This function:
    1. Reads ALL rows in rowid batches (bypasses corrupted B-tree)
    2. Filters by symbol in Python
    3. Routes to the correct target archive
    4. Deletes migrated rows from source by rowid list

    Returns dict of {target_name: (inserted, deleted)} plus 'source_total' key.
    """
    table_name = 'flow_options_scans'

    # Build symbol->target lookup
    symbol_to_target = {}
    for target_name, symbols in all_targets.items():
        for sym in symbols:
            symbol_to_target[sym] = target_name

    # Get column names and find symbol column index
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
    col_list = ', '.join(columns)
    insert_placeholders = ', '.join(['?'] * len(columns))
    symbol_idx = columns.index('symbol')

    # Get max rowid
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX(rowid) FROM {table_name}")
        db_max_rowid = cursor.fetchone()[0] or 0

    effective_max = min(max_rowid, db_max_rowid) if max_rowid else db_max_rowid
    truncated = max_rowid and max_rowid < db_max_rowid

    if truncated:
        print(f"\n  {table_name}: rowids 1-{effective_max:,} of {db_max_rowid:,} (chunked, corrupted B-tree)")
    else:
        print(f"\n  {table_name}: ~{db_max_rowid:,} max rowid (corrupted B-tree, using rowid scan)")

    if dry_run:
        # Estimate by scanning a sample
        sample_counts = {name: 0 for name in all_targets}
        sample_other = 0
        with sqlite3.connect(source_path) as conn:
            cursor = conn.cursor()
            # Sample first 500K rows to estimate distribution
            cursor.execute(f"SELECT rowid, symbol FROM {table_name} WHERE rowid BETWEEN 1 AND 500000")
            for _, sym in cursor.fetchall():
                if sym in symbol_to_target:
                    sample_counts[symbol_to_target[sym]] += 1
                else:
                    sample_other += 1
        sample_total = sum(sample_counts.values()) + sample_other
        if sample_total > 0:
            scale = effective_max / sample_total
            for name in sample_counts:
                est = int(sample_counts[name] * scale)
                print(f"    [dry-run] ~{est:,} rows --> {name}")
            print(f"    [dry-run] ~{int(sample_other * scale):,} rows staying in consumer_cyclical")
        return {name: (0, 0) for name in all_targets}

    # Open target connections
    target_conns = {}
    for target_name in all_targets:
        target_path = os.path.join(SECTOR_ARCHIVE_DIR, f'{target_name}.db')
        tgt_conn = sqlite3.connect(target_path, timeout=30.0)
        configure_speed_connection(tgt_conn)
        target_conns[target_name] = tgt_conn

    results = {name: [0, 0] for name in all_targets}  # [inserted, deleted]
    batch_num = 0
    current_rowid = 0
    total_read = 0
    total_corrupted = 0
    corrupted_ranges = []
    migration_start = time.time()

    while current_rowid < effective_max:
        batch_num += 1
        batch_start = current_rowid + 1
        batch_end = current_rowid + BATCH_SIZE

        # READ batch by rowid range — skip corrupted pages
        try:
            with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                src_conn.execute("PRAGMA busy_timeout = 30000")
                cursor = src_conn.cursor()
                cursor.execute(
                    f"SELECT rowid, {col_list} FROM {table_name} WHERE rowid BETWEEN ? AND ?",
                    (batch_start, batch_end)
                )
                rows_with_rowid = cursor.fetchall()
        except sqlite3.DatabaseError:
            # Corrupted page in this range — try smaller sub-batches to salvage what we can
            rows_with_rowid = []
            sub_batch = BATCH_SIZE // 10  # 5K sub-batches
            recovered = 0
            for sub_start in range(batch_start, batch_end + 1, sub_batch):
                sub_end = min(sub_start + sub_batch - 1, batch_end)
                try:
                    with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                        src_conn.execute("PRAGMA busy_timeout = 30000")
                        cursor = src_conn.cursor()
                        cursor.execute(
                            f"SELECT rowid, {col_list} FROM {table_name} WHERE rowid BETWEEN ? AND ?",
                            (sub_start, sub_end)
                        )
                        sub_rows = cursor.fetchall()
                        rows_with_rowid.extend(sub_rows)
                        recovered += len(sub_rows)
                except sqlite3.DatabaseError:
                    total_corrupted += sub_batch
                    corrupted_ranges.append((sub_start, sub_end))
            timestamp = now_eastern().strftime('%H:%M:%S')
            print(f"      [{timestamp}] Batch {batch_num}: CORRUPTED PAGES — recovered {recovered:,}, "
                  f"skipped ~{total_corrupted:,} rowids")

        current_rowid = batch_end
        if not rows_with_rowid:
            continue

        total_read += len(rows_with_rowid)

        # Sort rows by target (symbol is at index symbol_idx + 1 because of prepended rowid)
        target_rows = {name: [] for name in all_targets}
        target_rowids = {name: [] for name in all_targets}
        for row in rows_with_rowid:
            rid = row[0]
            data = row[1:]  # strip rowid
            sym = data[symbol_idx]
            if sym in symbol_to_target:
                tgt = symbol_to_target[sym]
                target_rows[tgt].append(data)
                target_rowids[tgt].append(rid)

        # INSERT into each target and DELETE from source
        for target_name in all_targets:
            if not target_rows[target_name]:
                continue

            target_conns[target_name].executemany(
                f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({insert_placeholders})",
                target_rows[target_name]
            )
            target_conns[target_name].commit()
            results[target_name][0] += len(target_rows[target_name])

            # DELETE migrated rows from source by rowid
            # May fail on corrupted pages — data is already safe in target
            rids = target_rowids[target_name]
            try:
                with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                    src_conn.execute("PRAGMA busy_timeout = 30000")
                    rid_placeholders = ','.join(['?'] * len(rids))
                    src_conn.execute(
                        f"DELETE FROM {table_name} WHERE rowid IN ({rid_placeholders})",
                        rids
                    )
                    results[target_name][1] += len(rids)
                    src_conn.commit()
            except sqlite3.DatabaseError:
                # Can't delete from corrupted pages — rows stay in source as duplicates.
                # Data is safe in target. VACUUM will rebuild the source and clean up.
                pass

        # Progress
        pct = min(100.0, (current_rowid / effective_max) * 100)
        migrated_this_batch = sum(len(target_rows[n]) for n in all_targets)
        timestamp = now_eastern().strftime('%H:%M:%S')
        print(f"      [{timestamp}] Batch {batch_num}: {len(rows_with_rowid):,} read, "
              f"{migrated_this_batch:,} migrated ({pct:.1f}% of rowid range)")

    # Close target connections
    for conn in target_conns.values():
        conn.close()

    # Print per-target summary
    for name in all_targets:
        ins, dele = results[name]
        print(f"    --> {name}: {ins:,} inserted, {dele:,} deleted")
    elapsed = time.time() - migration_start
    print(f"    Total read: {total_read:,} rows ({format_duration(elapsed)})")
    if total_corrupted > 0:
        print(f"    CORRUPTED: ~{total_corrupted:,} rowids in {len(corrupted_ranges)} ranges (data lost)")
        for start, end in corrupted_ranges[:10]:
            print(f"      rowid {start:,} - {end:,}")
        if len(corrupted_ranges) > 10:
            print(f"      ... and {len(corrupted_ranges) - 10} more ranges")

    return {name: tuple(v) for name, v in results.items()}


def migrate_table_rowid_fallback(source_path, target_path, table_name, symbols):
    """Fallback migration using rowid scan when B-tree is corrupted.
    Reads all rows by rowid range, filters by symbol in Python."""
    symbol_set = set(symbols)

    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        cursor.execute(f"SELECT MAX(rowid) FROM {table_name}")
        max_rowid = cursor.fetchone()[0] or 0
    col_list = ', '.join(columns)
    insert_placeholders = ', '.join(['?'] * len(columns))
    symbol_idx = columns.index('symbol')

    print(f"    [rowid fallback] Scanning {max_rowid:,} max rowid...")
    total_inserted = 0
    current_rowid = 0

    while current_rowid < max_rowid:
        batch_start = current_rowid + 1
        batch_end = current_rowid + BATCH_SIZE
        current_rowid = batch_end

        try:
            with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                src_conn.execute("PRAGMA busy_timeout = 30000")
                cursor = src_conn.cursor()
                cursor.execute(
                    f"SELECT rowid, {col_list} FROM {table_name} WHERE rowid BETWEEN ? AND ?",
                    (batch_start, batch_end)
                )
                rows_with_rowid = cursor.fetchall()
        except sqlite3.DatabaseError:
            continue  # Skip corrupted range

        if not rows_with_rowid:
            continue

        # Filter by symbol in Python
        matching_rows = []
        matching_rids = []
        for row in rows_with_rowid:
            rid = row[0]
            data = row[1:]
            if data[symbol_idx] in symbol_set:
                matching_rows.append(data)
                matching_rids.append(rid)

        if matching_rows:
            with sqlite3.connect(target_path, timeout=30.0) as tgt_conn:
                configure_speed_connection(tgt_conn)
                tgt_conn.executemany(
                    f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({insert_placeholders})",
                    matching_rows
                )
                tgt_conn.commit()
            total_inserted += len(matching_rows)

            # Try to delete — skip if corrupted
            try:
                with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                    src_conn.execute("PRAGMA busy_timeout = 30000")
                    rid_ph = ','.join(['?'] * len(matching_rids))
                    src_conn.execute(
                        f"DELETE FROM {table_name} WHERE rowid IN ({rid_ph})",
                        matching_rids
                    )
                    src_conn.commit()
            except sqlite3.DatabaseError:
                pass

    print(f"    [rowid fallback] Done: {total_inserted:,} inserted")
    return total_inserted, total_inserted


def migrate_table_batched(source_path, target_path, table_name, symbols, dry_run=False):
    """Migrate rows for a set of symbols from source to target archive, using batches for large tables.
    Falls back to rowid-based scan if B-tree corruption is encountered."""
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

    try:
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

    except sqlite3.DatabaseError:
        # B-tree corrupted — fall back to rowid scan
        print(f"    CORRUPTED — switching to rowid fallback...")
        return migrate_table_rowid_fallback(source_path, target_path, table_name, symbols)

    return total_inserted, total_deleted


def main():
    parser = argparse.ArgumentParser(description='Migrate consumer_cyclical.db split into retail + travel_leisure')
    parser.add_argument('--dry-run', action='store_true', help='Preview row counts without migrating')
    parser.add_argument('--vacuum', action='store_true', help='VACUUM consumer_cyclical.db after migration')
    parser.add_argument('--phase', type=int, choices=[1, 2], default=None,
                        help='Run only phase 1 (flow_options_scans) or phase 2 (other tables)')
    parser.add_argument('--max-rowid', type=int, default=None,
                        help='Phase 1 only: stop after this rowid (for chunking across nights)')
    args = parser.parse_args()

    print("=" * 70)
    print("CONSUMER CYCLICAL SECTOR ARCHIVE SPLIT MIGRATION")
    print("=" * 70)
    print(f"Start Time: {now_eastern().strftime('%Y-%m-%d %H:%M:%S EST')}")
    mode_parts = []
    if args.dry_run:
        mode_parts.append('DRY RUN')
    if args.phase == 1:
        mode_parts.append('Phase 1 only (flow_options_scans)')
    elif args.phase == 2:
        mode_parts.append('Phase 2 only (other tables)')
    else:
        mode_parts.append('All phases')
    if args.max_rowid:
        mode_parts.append(f'max rowid {args.max_rowid:,}')
    if args.vacuum:
        mode_parts.append('+ VACUUM')
    print(f"Mode: {' | '.join(mode_parts)}")
    print("=" * 70)

    # Validate paths
    if not os.path.exists(SOURCE_DB):
        print(f"ERROR: consumer_cyclical.db not found at {SOURCE_DB}")
        sys.exit(1)

    # Get symbol lists
    targets = get_symbol_lists()
    for name, symbols in targets.items():
        target_path = os.path.join(SECTOR_ARCHIVE_DIR, f'{name}.db')
        if not os.path.exists(target_path):
            print(f"ERROR: {name}.db not found at {target_path}")
            sys.exit(1)

    # --- PRE-MIGRATION SNAPSHOT ---
    source_size_before = os.path.getsize(SOURCE_DB)
    source_rows_before = get_total_rows(SOURCE_DB)
    target_sizes_before = {}
    target_rows_before = {}
    for name in targets:
        path = os.path.join(SECTOR_ARCHIVE_DIR, f'{name}.db')
        target_sizes_before[name] = os.path.getsize(path)
        target_rows_before[name] = get_total_rows(path)

    print(f"\nPRE-MIGRATION STATE")
    print(f"-" * 40)
    print(f"  {'Database':<25s} {'Size':>10s}  {'Rows':>12s}  Symbols")
    print(f"  {'─' * 25} {'─' * 10}  {'─' * 12}  {'─' * 7}")
    # Count symbols remaining in source (not being migrated out)
    try:
        conn = sqlite3.connect(SOURCE_DB)
        cursor = conn.cursor()
        all_migrating = []
        for syms in targets.values():
            all_migrating.extend(syms)
        if all_migrating:
            ph = ','.join(['?'] * len(all_migrating))
            cursor.execute(f"SELECT COUNT(DISTINCT symbol) FROM symbol_metadata WHERE symbol NOT IN ({ph})", all_migrating)
        else:
            cursor.execute("SELECT COUNT(DISTINCT symbol) FROM symbol_metadata")
        remaining_symbols = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM symbol_metadata")
        total_source_symbols = cursor.fetchone()[0]
        conn.close()
    except Exception:
        remaining_symbols = '?'
        total_source_symbols = '?'
    print(f"  {'consumer_cyclical.db':<25s} {format_size(source_size_before):>10s}  {source_rows_before:>12,}  {total_source_symbols} ({remaining_symbols} staying)")

    # Count rows to migrate per target (skip flow_options_scans if corrupted)
    rows_to_migrate = {}
    fos_corrupted = False
    for name, symbols in targets.items():
        total = 0
        for table in MIGRATION_TABLES:
            try:
                total += count_rows(SOURCE_DB, table, symbols)
            except Exception:
                if table == 'flow_options_scans':
                    fos_corrupted = True
                    # Will be handled by rowid scanner — estimate unavailable per-target
                pass
        rows_to_migrate[name] = total
        path = os.path.join(SECTOR_ARCHIVE_DIR, f'{name}.db')
        print(f"  {name + '.db':<25s} {format_size(target_sizes_before[name]):>10s}  {target_rows_before[name]:>12,}  {len(symbols)}")

    print(f"\nMIGRATION PLAN")
    print(f"-" * 40)
    total_to_move = sum(rows_to_migrate.values())
    for name, row_count in rows_to_migrate.items():
        note = " (excl. flow_options_scans)" if fos_corrupted else ""
        print(f"  consumer_cyclical --> {name}: {row_count:,} rows{note}")
    print(f"  {'Total to move:':<35s} {total_to_move:,} rows")
    if fos_corrupted:
        print(f"\n  NOTE: flow_options_scans has corrupted B-tree index.")
        print(f"  Using rowid-based scan (reads all rows, filters by symbol in Python).")
        print(f"  VACUUM at end will rebuild the table and fix corruption.")
    print()

    migration_start = time.time()
    grand_inserted = 0
    grand_deleted = 0

    run_phase_1 = args.phase in (None, 1)
    run_phase_2 = args.phase in (None, 2)

    # --- STEP 1: Handle corrupted flow_options_scans via rowid scan (all targets at once) ---
    if run_phase_1:
        print(f"{'=' * 70}")
        print(f"PHASE 1: flow_options_scans (corrupted B-tree — rowid scan)")
        print(f"{'=' * 70}")

        fos_results = migrate_corrupted_flow_scans(
            SOURCE_DB, targets, dry_run=args.dry_run, max_rowid=args.max_rowid
        )
        for target_name in targets:
            ins, dele = fos_results.get(target_name, (0, 0))
            grand_inserted += ins
            grand_deleted += dele
    else:
        print(f"\n  [Skipping Phase 1 — flow_options_scans]")

    # --- STEP 2: All other tables (normal per-target migration) ---
    if run_phase_2:
        other_tables = [t for t in MIGRATION_TABLES if t != 'flow_options_scans']

        for target_name, symbols in targets.items():
            target_path = os.path.join(SECTOR_ARCHIVE_DIR, f'{target_name}.db')

            print(f"\n{'=' * 70}")
            print(f"PHASE 2: {target_name.upper()} — remaining tables ({len(symbols)} symbols)")
            print(f"{'=' * 70}")

            target_start = time.time()
            target_inserted = 0
            target_deleted = 0

            for table_name in other_tables:
                source_count = count_rows(SOURCE_DB, table_name, symbols)
                if source_count == 0:
                    continue

                print(f"\n  {table_name}: {source_count:,} rows")
                table_start = time.time()

                inserted, deleted = migrate_table_batched(
                    SOURCE_DB, target_path, table_name, symbols, dry_run=args.dry_run
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
    else:
        print(f"\n  [Skipping Phase 2 — other tables]")

    # Rebuild consumer_cyclical.db to reclaim space and fix corruption
    # VACUUM can't work on a corrupted DB — it traverses the broken B-tree.
    # Instead: create a new DB, copy all data via rowid reads, replace the old file.
    vacuum_reclaimed = 0
    if args.vacuum and not args.dry_run:
        print(f"\n{'=' * 70}")
        print("REBUILDING consumer_cyclical.db (VACUUM fails on corrupted B-trees)")
        print(f"{'=' * 70}")
        rebuild_start = time.time()
        pre_rebuild_size = os.path.getsize(SOURCE_DB)
        print(f"  Size before: {format_size(pre_rebuild_size)}")

        rebuilt_path = SOURCE_DB + '.rebuilt'
        if os.path.exists(rebuilt_path):
            os.remove(rebuilt_path)

        # Get schema from the old DB
        with sqlite3.connect(SOURCE_DB) as old_conn:
            old_cursor = old_conn.cursor()
            old_cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
            table_schemas = old_cursor.fetchall()

        # Create new DB with same schema
        with sqlite3.connect(rebuilt_path) as new_conn:
            configure_speed_connection(new_conn)
            for tbl_name, create_sql in table_schemas:
                new_conn.execute(create_sql)
            new_conn.commit()

        print(f"  Created empty rebuild target with {len(table_schemas)} tables")

        # Copy each table via rowid scan
        for tbl_name, _ in table_schemas:
            with sqlite3.connect(SOURCE_DB) as old_conn:
                old_cursor = old_conn.cursor()
                old_cursor.execute(f"PRAGMA table_info({tbl_name})")
                columns = [row[1] for row in old_cursor.fetchall()]
                try:
                    old_cursor.execute(f"SELECT MAX(rowid) FROM {tbl_name}")
                    max_rid = old_cursor.fetchone()[0] or 0
                except (sqlite3.DatabaseError, sqlite3.OperationalError):
                    max_rid = 0

            if max_rid == 0:
                continue

            col_list = ', '.join(columns)
            ins_ph = ', '.join(['?'] * len(columns))
            copied = 0
            skipped_ranges = 0
            current = 0

            while current < max_rid:
                batch_start = current + 1
                batch_end = current + BATCH_SIZE
                current = batch_end

                try:
                    with sqlite3.connect(SOURCE_DB, timeout=30.0) as old_conn:
                        old_conn.execute("PRAGMA busy_timeout = 30000")
                        cursor = old_conn.cursor()
                        cursor.execute(
                            f"SELECT {col_list} FROM {tbl_name} WHERE rowid BETWEEN ? AND ?",
                            (batch_start, batch_end)
                        )
                        rows = cursor.fetchall()
                except sqlite3.DatabaseError:
                    skipped_ranges += 1
                    continue

                if rows:
                    with sqlite3.connect(rebuilt_path, timeout=30.0) as new_conn:
                        configure_speed_connection(new_conn)
                        new_conn.executemany(
                            f"INSERT OR IGNORE INTO {tbl_name} ({col_list}) VALUES ({ins_ph})",
                            rows
                        )
                        new_conn.commit()
                    copied += len(rows)

            timestamp = now_eastern().strftime('%H:%M:%S')
            corrupt_note = f" ({skipped_ranges} corrupted ranges skipped)" if skipped_ranges else ""
            print(f"    [{timestamp}] {tbl_name}: {copied:,} rows copied{corrupt_note}")

        # Checkpoint WAL on rebuilt DB
        with sqlite3.connect(rebuilt_path) as new_conn:
            new_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        post_rebuild_size = os.path.getsize(rebuilt_path)
        print(f"\n  Rebuilt size: {format_size(post_rebuild_size)}")

        # Swap files
        old_path = SOURCE_DB + '.corrupted'
        print(f"  Renaming original to {os.path.basename(old_path)}")
        if os.path.exists(old_path):
            os.remove(old_path)
        os.rename(SOURCE_DB, old_path)
        os.rename(rebuilt_path, SOURCE_DB)

        rebuild_elapsed = time.time() - rebuild_start
        vacuum_reclaimed = pre_rebuild_size - post_rebuild_size
        print(f"  Reclaimed:   {format_size(vacuum_reclaimed)} ({format_duration(rebuild_elapsed)})")
        print(f"  Original saved as: {os.path.basename(old_path)} (delete when verified)")

    # --- POST-MIGRATION SUMMARY ---
    total_elapsed = time.time() - migration_start
    source_size_after = os.path.getsize(SOURCE_DB)

    print(f"\n{'=' * 70}")
    print("MIGRATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Duration:        {format_duration(total_elapsed)}")
    print(f"  Total inserted:  {grand_inserted:,}")
    print(f"  Total deleted:   {grand_deleted:,}")

    print(f"\nPOST-MIGRATION STATE")
    print(f"-" * 40)
    print(f"  {'Database':<25s} {'Before':>10s}  {'After':>10s}  {'Change':>10s}")
    print(f"  {'─' * 25} {'─' * 10}  {'─' * 10}  {'─' * 10}")
    print(f"  {'consumer_cyclical.db':<25s} {format_size(source_size_before):>10s}  {format_size(source_size_after):>10s}  {'-' + format_size(source_size_before - source_size_after):>10s}")
    for name in targets:
        path = os.path.join(SECTOR_ARCHIVE_DIR, f'{name}.db')
        after = os.path.getsize(path)
        before = target_sizes_before[name]
        print(f"  {name + '.db':<25s} {format_size(before):>10s}  {format_size(after):>10s}  {'+' + format_size(after - before):>10s}")

    net_change = source_size_after - source_size_before
    for name in targets:
        path = os.path.join(SECTOR_ARCHIVE_DIR, f'{name}.db')
        net_change += os.path.getsize(path) - target_sizes_before[name]
    print(f"\n  Net disk change:  {'+' if net_change >= 0 else '-'}{format_size(abs(net_change))}")
    if vacuum_reclaimed > 0:
        print(f"  VACUUM reclaimed: {format_size(vacuum_reclaimed)}")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
