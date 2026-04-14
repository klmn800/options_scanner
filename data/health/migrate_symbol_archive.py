#!/usr/bin/env python3
"""
Migrate Symbol Data Between Sector Archives

Moves all historical data for a single symbol from one sector archive to another.
Used when reassigning symbols to different archive databases (e.g., moving NVDA from
"technology" to "airline_suppliers").

Features:
- Migrates 12 tables including symbol_metadata
- Optional backfill for missing metadata (--backfill-metadata)
- Optional backfill for missing historical prices (--backfill-prices)
- Calls FMP API scripts automatically when data is missing

Usage:
    python data/health/migrate_symbol_archive.py --symbol NVDA --from technology --to crypto
    python data/health/migrate_symbol_archive.py --symbol DAL --from airlines --to test_archive --dry-run
    python data/health/migrate_symbol_archive.py --symbol CCJ --from technology --to nuclear --backfill-metadata --backfill-prices

Exit Codes:
    0: Success (all tables migrated)
    1: Validation error (missing archive, symbol not found)
    2: Migration error (copy/verify/delete failed)
"""

import sqlite3
import sys
import os
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Dict, Tuple, List
from datetime import datetime

# Setup UTF-8 encoding for stdout (Windows compatibility)
sys.stdout.reconfigure(encoding='utf-8')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
SECTOR_ARCHIVE_DIR = PROJECT_ROOT / 'data' / 'sector_archive'
LOGS_DIR = PROJECT_ROOT / 'logs'

# Tables to migrate (in order of foreign key dependencies)
# Primary data tables first, then reference tables
MIGRATION_TABLES = [
    'flow_options_scans',      # Contract-level intraday scans
    'option_contracts',        # Daily OI tracking
    'flow_alerts',             # Flow alerts
    'flow_symbol_summary',     # Daily alert metrics
    'option_symbol_summary',   # Symbol-level OI/IV summaries
    'historical_prices',       # Price data
    'earnings_events',         # Earnings with journal
    'earnings_upcoming',       # Pending earnings
    'news_articles',           # News articles
    'news_symbol_sentiment',   # Sentiment scores
    'alert_contract_tracking', # Alert profitability
    'symbol_metadata',         # Symbol metadata (1 row per symbol)
]


def setup_file_logging(symbol: str) -> logging.FileHandler:
    """
    Setup file logging for migration process.

    Args:
        symbol: Stock ticker being migrated

    Returns:
        FileHandler for cleanup
    """
    # Create logs directory if needed
    LOGS_DIR.mkdir(exist_ok=True)

    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"migration_{symbol}_{timestamp}.log"

    # Add file handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    logger.info(f"Migration log: {log_file}")
    return file_handler


def validate_archives(from_archive: str, to_archive: str) -> Tuple[bool, str]:
    """
    Validate that both archives exist.

    Args:
        from_archive: Source archive name
        to_archive: Target archive name

    Returns:
        (True, "") if valid, (False, "error message") if invalid
    """
    # Check source exists
    source_path = SECTOR_ARCHIVE_DIR / f"{from_archive}.db"
    if not source_path.exists():
        return False, f"Source archive not found: {source_path}"

    # Check target exists
    target_path = SECTOR_ARCHIVE_DIR / f"{to_archive}.db"
    if not target_path.exists():
        return False, f"Target archive not found: {target_path}"

    # Check they're different
    if from_archive == to_archive:
        return False, "Source and target archives must be different"

    return True, ""


def count_symbol_rows(archive_path: Path, symbol: str, table_name: str) -> int:
    """
    Count rows for symbol in specific table.

    Args:
        archive_path: Path to archive database
        symbol: Stock ticker
        table_name: Table to query

    Returns:
        Row count (0 if table doesn't have symbol column)
    """
    try:
        conn = sqlite3.connect(str(archive_path))
        cursor = conn.cursor()

        # Check if table has 'symbol' column
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]

        if 'symbol' not in columns:
            conn.close()
            return 0

        # Count rows
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE symbol = ?", (symbol,))
        count = cursor.fetchone()[0]
        conn.close()

        return count

    except sqlite3.Error as e:
        logger.warning(f"Error counting rows in {table_name}: {e}")
        return 0


def estimate_migration(from_archive: str, symbol: str) -> Dict[str, int]:
    """
    Estimate row counts for migration.

    Args:
        from_archive: Source archive name
        symbol: Stock ticker

    Returns:
        Dict mapping table_name → row_count
    """
    source_path = SECTOR_ARCHIVE_DIR / f"{from_archive}.db"
    row_counts = {}

    for table_name in MIGRATION_TABLES:
        count = count_symbol_rows(source_path, symbol, table_name)
        row_counts[table_name] = count

    return row_counts


def migrate_table(
    source_path: Path,
    target_path: Path,
    symbol: str,
    table_name: str,
    dry_run: bool
) -> Tuple[bool, int, str]:
    """
    Migrate symbol data for single table.

    Process:
        1. Copy rows from source to target
        2. Verify row counts match
        3. Delete rows from source (if not dry-run)

    Args:
        source_path: Source archive path
        target_path: Target archive path
        symbol: Stock ticker
        table_name: Table to migrate
        dry_run: If True, skip actual operations

    Returns:
        (success: bool, rows_migrated: int, error_message: str)
    """
    try:
        # Count rows in source
        source_count = count_symbol_rows(source_path, symbol, table_name)

        if source_count == 0:
            return True, 0, ""  # Nothing to migrate

        if dry_run:
            return True, source_count, ""

        # Connect to both databases
        source_conn = sqlite3.connect(str(source_path))
        target_conn = sqlite3.connect(str(target_path))

        source_cursor = source_conn.cursor()
        target_cursor = target_conn.cursor()

        # Get column list
        source_cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in source_cursor.fetchall()]
        col_list = ', '.join(columns)

        # Count pre-existing rows in target (may have data from prior archive runs)
        target_before = count_symbol_rows(target_path, symbol, table_name)
        if target_before > 0:
            logger.info(f"  Note: target already has {target_before:,} pre-existing rows")

        # Step 1: Copy data (INSERT OR IGNORE skips rows that already exist by PK)
        source_cursor.execute(f"SELECT {col_list} FROM {table_name} WHERE symbol = ?", (symbol,))
        rows = source_cursor.fetchall()

        if rows:
            placeholders = ', '.join(['?'] * len(columns))
            target_cursor.executemany(
                f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({placeholders})",
                rows
            )
            target_conn.commit()

        # Step 2: Verify — target should have at least source_count rows
        # (may have more from prior archive runs, that's fine)
        target_after = count_symbol_rows(target_path, symbol, table_name)
        new_rows = target_after - target_before

        if target_after < source_count:
            source_conn.close()
            target_conn.close()
            return False, 0, f"Verification failed: target has {target_after} rows, expected at least {source_count}"

        # Step 3: Delete from source
        source_cursor.execute(f"DELETE FROM {table_name} WHERE symbol = ?", (symbol,))
        source_conn.commit()

        # Final verification
        final_source_count = count_symbol_rows(source_path, symbol, table_name)
        if final_source_count != 0:
            logger.warning(f"Source still has {final_source_count} rows after delete (possible concurrent writes)")

        source_conn.close()
        target_conn.close()

        return True, new_rows, ""

    except sqlite3.Error as e:
        return False, 0, f"Database error: {e}"
    except Exception as e:
        return False, 0, f"Unexpected error: {e}"


def backfill_metadata(symbol: str, target_db: Path) -> bool:
    """
    Backfill missing symbol_metadata using FMP API.

    Args:
        symbol: Stock ticker
        target_db: Target archive database path

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Backfilling metadata for {symbol} using FMP API...")

    try:
        # Call fmp_symbol_metadata.py for single symbol
        script_path = PROJECT_ROOT / 'data' / 'fmp_symbol_metadata.py'
        result = subprocess.run(
            [sys.executable, str(script_path), '--no-interaction', '--symbols', symbol],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30000
        )

        if result.returncode == 0:
            # Copy newly fetched metadata from datalake to target archive
            datalake_path = PROJECT_ROOT / 'data' / 'datalake.db'

            src_conn = sqlite3.connect(str(datalake_path))
            dst_conn = sqlite3.connect(str(target_db))

            src_cursor = src_conn.cursor()
            src_cursor.execute("SELECT * FROM symbol_metadata WHERE symbol = ?", (symbol,))
            row = src_cursor.fetchone()

            if row:
                # Get column names
                src_cursor.execute("PRAGMA table_info(symbol_metadata)")
                columns = [col[1] for col in src_cursor.fetchall()]
                col_list = ', '.join(columns)
                placeholders = ', '.join(['?'] * len(columns))

                dst_cursor = dst_conn.cursor()
                dst_cursor.execute(
                    f"INSERT OR REPLACE INTO symbol_metadata ({col_list}) VALUES ({placeholders})",
                    row
                )
                dst_conn.commit()

                logger.info(f"  ✅ Metadata backfilled for {symbol}")

                src_conn.close()
                dst_conn.close()
                return True
            else:
                logger.warning(f"  ⚠️  FMP API did not return metadata for {symbol}")
                src_conn.close()
                dst_conn.close()
                return False
        else:
            logger.error(f"  ❌ FMP metadata fetch failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Metadata backfill error: {e}")
        return False


def backfill_historical_prices(symbol: str, target_db: Path) -> bool:
    """
    Backfill missing historical_prices using FMP API.

    Args:
        symbol: Stock ticker
        target_db: Target archive database path

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"Backfilling historical prices for {symbol} using Tradier API...")

    try:
        # Call tradier_historical_backfill.py for single symbol with 2021 backfill
        script_path = PROJECT_ROOT / 'data' / 'tradier_historical_backfill.py'
        result = subprocess.run(
            [sys.executable, str(script_path), '--no-interaction', '--symbols', symbol, '--backfill-2021'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60000
        )

        if result.returncode == 0:
            # Copy newly fetched prices from datalake to target archive
            datalake_path = PROJECT_ROOT / 'data' / 'datalake.db'

            src_conn = sqlite3.connect(str(datalake_path))
            dst_conn = sqlite3.connect(str(target_db))

            src_cursor = src_conn.cursor()
            src_cursor.execute("SELECT * FROM historical_prices WHERE symbol = ?", (symbol,))
            rows = src_cursor.fetchall()

            if rows:
                # Get column names
                src_cursor.execute("PRAGMA table_info(historical_prices)")
                columns = [col[1] for col in src_cursor.fetchall()]
                col_list = ', '.join(columns)
                placeholders = ', '.join(['?'] * len(columns))

                dst_cursor = dst_conn.cursor()
                dst_cursor.executemany(
                    f"INSERT OR REPLACE INTO historical_prices ({col_list}) VALUES ({placeholders})",
                    rows
                )
                dst_conn.commit()

                logger.info(f"  ✅ Historical prices backfilled: {len(rows)} rows")

                src_conn.close()
                dst_conn.close()
                return True
            else:
                logger.warning(f"  ⚠️  FMP API did not return historical prices for {symbol}")
                src_conn.close()
                dst_conn.close()
                return False
        else:
            logger.error(f"  ❌ FMP historical fetch failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Historical prices backfill error: {e}")
        return False


def migrate_symbol(
    symbol: str,
    from_archive: str,
    to_archive: str,
    dry_run: bool,
    backfill_metadata_flag: bool = False,
    backfill_prices_flag: bool = False
) -> int:
    """
    Migrate all data for a symbol between archives.

    Args:
        symbol: Stock ticker
        from_archive: Source archive name
        to_archive: Target archive name
        dry_run: If True, only estimate, don't migrate
        backfill_metadata_flag: If True, backfill missing metadata using FMP API
        backfill_prices_flag: If True, backfill missing prices using FMP API

    Returns:
        Exit code (0=success, 1=validation error, 2=migration error)
    """
    logger.info("="*70)
    logger.info("SYMBOL ARCHIVE MIGRATION")
    logger.info("="*70)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"From Archive: {from_archive}")
    logger.info(f"To Archive: {to_archive}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("")

    # Validate archives exist
    valid, error_msg = validate_archives(from_archive, to_archive)
    if not valid:
        logger.error(f"Validation failed: {error_msg}")
        return 1

    source_path = SECTOR_ARCHIVE_DIR / f"{from_archive}.db"
    target_path = SECTOR_ARCHIVE_DIR / f"{to_archive}.db"

    # Estimate row counts
    logger.info("Analyzing source data...")
    logger.info("")
    row_counts = estimate_migration(from_archive, symbol)

    total_rows = sum(row_counts.values())

    if total_rows == 0:
        logger.warning(f"No data found for {symbol} in {from_archive}")
        logger.info("")
        logger.info("Possible reasons:")
        logger.info(f"  - Symbol has not been archived yet")
        logger.info(f"  - Symbol already migrated from this archive")
        logger.info(f"  - Check symbol spelling")
        return 1

    # Display estimation
    logger.info(f"Found data for {symbol}:")
    logger.info("")
    logger.info(f"{'Table':<30} {'Rows':>10}")
    logger.info("-" * 42)

    for table_name in MIGRATION_TABLES:
        count = row_counts.get(table_name, 0)
        if count > 0:
            logger.info(f"{table_name:<30} {count:>10,}")

    logger.info("-" * 42)
    logger.info(f"{'TOTAL':<30} {total_rows:>10,}")
    logger.info("")

    if dry_run:
        logger.info("[DRY RUN] Migration plan validated. No data moved.")
        logger.info("")
        logger.info("To execute migration, remove --dry-run flag:")
        logger.info(f"  python data/health/migrate_symbol_archive.py --symbol {symbol} --from {from_archive} --to {to_archive}")
        return 0

    # Confirm before proceeding
    logger.info("Starting migration...")
    logger.info("")

    # Migrate each table
    migrated_tables = 0
    total_migrated = 0
    failed_tables = []

    for table_name in MIGRATION_TABLES:
        expected_count = row_counts.get(table_name, 0)

        if expected_count == 0:
            continue  # Skip empty tables

        logger.info(f"Migrating {table_name}... ({expected_count:,} rows)")

        success, migrated_count, error_msg = migrate_table(
            source_path, target_path, symbol, table_name, dry_run=False
        )

        if success:
            logger.info(f"  ✅ Migrated {migrated_count:,} rows")
            migrated_tables += 1
            total_migrated += migrated_count
        else:
            logger.error(f"  ❌ Failed: {error_msg}")
            failed_tables.append((table_name, error_msg))

        logger.info("")

    # Summary
    logger.info("="*70)

    if failed_tables:
        logger.error("MIGRATION COMPLETED WITH ERRORS")
        logger.info("="*70)
        logger.info(f"Successfully migrated: {migrated_tables}/{len([t for t in MIGRATION_TABLES if row_counts.get(t, 0) > 0])} tables")
        logger.info(f"Total rows migrated: {total_migrated:,}/{total_rows:,}")
        logger.info("")
        logger.error("Failed tables:")
        for table_name, error_msg in failed_tables:
            logger.error(f"  - {table_name}: {error_msg}")
        logger.info("")
        logger.warning("⚠️  Symbol partially migrated. Some data remains in source archive.")
        logger.info("Review errors above and retry failed tables manually.")
        return 2
    else:
        # Migration successful - check for backfill operations
        backfill_performed = False

        if backfill_metadata_flag:
            logger.info("")
            logger.info("Checking for missing symbol_metadata...")

            # Check if metadata exists in target
            metadata_count = count_symbol_rows(target_path, symbol, 'symbol_metadata')
            if metadata_count == 0:
                logger.info(f"  ⚠️  No metadata found for {symbol} in target archive")
                backfill_performed = True
                if backfill_metadata(symbol, target_path):
                    logger.info(f"  ✅ Metadata backfill completed")
                else:
                    logger.warning(f"  ⚠️  Metadata backfill failed (see errors above)")
            else:
                logger.info(f"  ✅ Metadata already exists ({metadata_count} row)")

        if backfill_prices_flag:
            logger.info("")
            logger.info("Checking for missing historical_prices...")

            # Check if prices exist in target
            prices_count = count_symbol_rows(target_path, symbol, 'historical_prices')
            if prices_count < 30:  # Less than 30 days of price data
                logger.info(f"  ⚠️  Limited price data for {symbol} ({prices_count} rows)")
                backfill_performed = True
                if backfill_historical_prices(symbol, target_path):
                    logger.info(f"  ✅ Historical prices backfill completed")
                else:
                    logger.warning(f"  ⚠️  Historical prices backfill failed (see errors above)")
            else:
                logger.info(f"  ✅ Sufficient price data exists ({prices_count} rows)")

        # Final success message
        logger.info("")
        logger.info("="*70)
        logger.info("SUCCESS")
        logger.info("="*70)
        logger.info(f"All tables migrated successfully")
        logger.info(f"Total rows: {total_migrated:,}")
        if backfill_performed:
            logger.info(f"Backfill operations: Completed")
        logger.info("")
        logger.info(f"✅ {symbol} data moved from {from_archive} → {to_archive}")
        logger.info("")
        logger.info("Next steps:")
        logger.info(f"  1. Verify data in target: python tools/direct_db_query.py --db data/sector_archive/{to_archive}.db --sql \"SELECT COUNT(*) FROM option_contracts WHERE symbol='{symbol}'\"")
        logger.info(f"  2. Update symbol_metadata.archive_db to '{to_archive}' (via Admin TUI or SQL)")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description='Migrate symbol data between sector archives',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Estimate migration
  python migrate_symbol_archive.py --symbol NVDA --from technology --to crypto --dry-run

  # Execute migration
  python migrate_symbol_archive.py --symbol NVDA --from technology --to crypto

  # Migrate with backfill (if metadata or prices missing)
  python migrate_symbol_archive.py --symbol CCJ --from technology --to nuclear --backfill-metadata --backfill-prices

  # Migrate after reassignment
  python migrate_symbol_archive.py --symbol DAL --from airlines --to special_situations

Exit Codes:
  0: Success (all tables migrated)
  1: Validation error (missing archive, symbol not found)
  2: Migration error (copy/verify/delete failed)

Notes:
  - Creates timestamped log file: logs/migration_{symbol}_{timestamp}.log
  - Uses Copy → Verify → Delete pattern for safety
  - Operates on 12 data tables (including symbol_metadata)
  - Backfill flags call FMP API if data is missing after migration
  - Does not modify symbol_metadata.archive_db (use Admin TUI or manual SQL)
        """
    )

    parser.add_argument(
        '--symbol',
        required=True,
        help='Stock ticker symbol to migrate (e.g., NVDA, DAL)'
    )

    parser.add_argument(
        '--from',
        dest='from_archive',
        required=True,
        help='Source archive name (e.g., technology, airlines)'
    )

    parser.add_argument(
        '--to',
        dest='to_archive',
        required=True,
        help='Target archive name (e.g., crypto, special_situations)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Estimate migration without moving data'
    )

    parser.add_argument(
        '--backfill-metadata',
        action='store_true',
        help='Backfill missing symbol_metadata using FMP API after migration'
    )

    parser.add_argument(
        '--backfill-prices',
        action='store_true',
        help='Backfill missing historical_prices using FMP API after migration (from 2021)'
    )

    args = parser.parse_args()

    # Setup file logging
    if not args.dry_run:
        file_handler = setup_file_logging(args.symbol)

    try:
        exit_code = migrate_symbol(
            args.symbol.upper(),
            args.from_archive,
            args.to_archive,
            args.dry_run,
            backfill_metadata_flag=args.backfill_metadata,
            backfill_prices_flag=args.backfill_prices
        )
        sys.exit(exit_code)

    finally:
        # Cleanup file handler
        if not args.dry_run:
            logger.removeHandler(file_handler)
            file_handler.close()


if __name__ == "__main__":
    main()
