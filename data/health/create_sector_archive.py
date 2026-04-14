#!/usr/bin/env python3
"""
Create New Sector Archive Database

Creates an empty sector archive database with schema aligned to production datalake.db.
Used when creating new symbol groupings (e.g., "crypto", "airline_suppliers").

Usage:
    python data/health/create_sector_archive.py --name crypto
    python data/health/create_sector_archive.py --name airline_suppliers --copy-reference
    python data/health/create_sector_archive.py --name test --dry-run

Exit Codes:
    0: Success
    1: Validation error (invalid name, already exists)
    2: Database error (schema copy failed)
"""

import sqlite3
import sys
import os
import re
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Tuple

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
DATALAKE_PATH = PROJECT_ROOT / 'data' / 'datalake.db'
SECTOR_ARCHIVE_DIR = PROJECT_ROOT / 'data' / 'sector_archive'

# Tables to create in new archive (13 normalized tables)
NORMALIZED_TABLES = [
    'symbol_metadata',
    'market_daily_summary',
    'historical_prices',
    'flow_options_scans',
    'option_contracts',
    'flow_alerts',
    'flow_symbol_summary',
    'option_symbol_summary',
    'earnings_events',
    'earnings_upcoming',
    'news_articles',
    'news_symbol_sentiment',
    'alert_contract_tracking'
]

# Reference tables to copy data from datalake
# market_daily_summary is ALWAYS copied (provides research context)
# symbol_metadata will be populated as symbols are migrated in
REFERENCE_TABLES = ['market_daily_summary']


def validate_archive_name(name: str) -> Tuple[bool, str]:
    """
    Validate archive name format and uniqueness.

    Args:
        name: Proposed archive name

    Returns:
        (True, "") if valid, (False, "error message") if invalid
    """
    # Check format: lowercase, starts with letter, can contain underscores/numbers
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        return False, (
            "Invalid name format. Must be lowercase, start with letter, "
            "and contain only letters, numbers, and underscores."
        )

    # Check length
    if len(name) > 50:
        return False, "Name too long (max 50 characters)."

    # Check uniqueness
    archive_path = SECTOR_ARCHIVE_DIR / f"{name}.db"
    if archive_path.exists():
        return False, f"Archive already exists: {archive_path}"

    return True, ""


def get_table_schema(source_db: Path, table_name: str) -> str:
    """
    Get CREATE TABLE statement from source database.

    Args:
        source_db: Path to source database
        table_name: Table name

    Returns:
        CREATE TABLE SQL statement

    Raises:
        sqlite3.Error: If table doesn't exist or query fails
    """
    conn = sqlite3.connect(str(source_db))
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        result = cursor.fetchone()

        if not result:
            raise ValueError(f"Table '{table_name}' not found in {source_db}")

        return result[0]

    finally:
        conn.close()


def get_table_indexes(source_db: Path, table_name: str) -> List[str]:
    """
    Get CREATE INDEX statements for a table.

    Args:
        source_db: Path to source database
        table_name: Table name

    Returns:
        List of CREATE INDEX SQL statements
    """
    conn = sqlite3.connect(str(source_db))
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (table_name,)
        )
        return [row[0] for row in cursor.fetchall()]

    finally:
        conn.close()


def copy_reference_data(source_db: Path, target_db: Path, table_name: str) -> int:
    """
    Copy reference data from source to target.

    Args:
        source_db: Source database path
        target_db: Target database path
        table_name: Table to copy

    Returns:
        Number of rows copied
    """
    source_conn = sqlite3.connect(str(source_db))
    target_conn = sqlite3.connect(str(target_db))

    try:
        # Get column names
        source_cursor = source_conn.cursor()
        source_cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in source_cursor.fetchall()]
        col_list = ', '.join(columns)

        # Copy data
        source_cursor.execute(f"SELECT {col_list} FROM {table_name}")
        rows = source_cursor.fetchall()

        if rows:
            placeholders = ', '.join(['?'] * len(columns))
            target_cursor = target_conn.cursor()
            target_cursor.executemany(
                f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})",
                rows
            )
            target_conn.commit()

        return len(rows)

    finally:
        source_conn.close()
        target_conn.close()


def create_sector_archive(name: str, copy_reference: bool, dry_run: bool) -> int:
    """
    Create new sector archive database.

    Args:
        name: Archive name
        copy_reference: Whether to copy reference tables from datalake
        dry_run: If True, only validate, don't create

    Returns:
        Exit code (0=success, 1=validation error, 2=database error)
    """
    logger.info("="*70)
    logger.info("CREATE SECTOR ARCHIVE")
    logger.info("="*70)
    logger.info(f"Archive Name: {name}")
    logger.info(f"Copy Reference Data: {copy_reference}")
    logger.info(f"Dry Run: {dry_run}")
    logger.info("")

    # Validate name
    valid, error_msg = validate_archive_name(name)
    if not valid:
        logger.error(f"Validation failed: {error_msg}")
        return 1

    # Check source database exists
    if not DATALAKE_PATH.exists():
        logger.error(f"Source database not found: {DATALAKE_PATH}")
        return 2

    # Check sector archive directory exists
    if not SECTOR_ARCHIVE_DIR.exists():
        logger.error(f"Sector archive directory not found: {SECTOR_ARCHIVE_DIR}")
        return 2

    archive_path = SECTOR_ARCHIVE_DIR / f"{name}.db"

    if dry_run:
        logger.info("[DRY RUN] Would create: %s", archive_path)
        logger.info("[DRY RUN] Would copy schemas for %d tables", len(NORMALIZED_TABLES))
        if copy_reference:
            logger.info("[DRY RUN] Would copy reference data from: %s", ', '.join(REFERENCE_TABLES))
        logger.info("")
        logger.info("Validation passed. Ready to create archive.")
        return 0

    # Create new database
    logger.info(f"Creating archive: {archive_path}")
    logger.info("")

    try:
        conn = sqlite3.connect(str(archive_path))
        cursor = conn.cursor()

        # Enable WAL mode
        cursor.execute("PRAGMA journal_mode=WAL")
        conn.commit()

        # Copy table schemas
        logger.info("Copying table schemas from datalake.db...")
        logger.info("")

        for table_name in NORMALIZED_TABLES:
            try:
                # Get CREATE TABLE statement
                create_sql = get_table_schema(DATALAKE_PATH, table_name)
                cursor.execute(create_sql)

                # Get column count
                cursor.execute(f"PRAGMA table_info({table_name})")
                col_count = len(cursor.fetchall())

                logger.info(f"  ✅ Created table: {table_name} ({col_count} columns)")

                # Copy indexes
                indexes = get_table_indexes(DATALAKE_PATH, table_name)
                for index_sql in indexes:
                    cursor.execute(index_sql)

            except Exception as e:
                logger.error(f"  ❌ Failed to create table {table_name}: {e}")
                conn.close()
                # Clean up partial database
                if archive_path.exists():
                    archive_path.unlink()
                return 2

        conn.commit()
        conn.close()

        logger.info("")
        logger.info(f"✅ Archive created successfully: {archive_path}")

        # Get file size
        file_size = archive_path.stat().st_size
        file_size_kb = file_size / 1024
        logger.info(f"   File size: {file_size_kb:.1f} KB (empty)")

        # Always copy market_daily_summary for research context
        logger.info("")
        logger.info("Copying market_daily_summary for research context...")
        try:
            row_count = copy_reference_data(DATALAKE_PATH, archive_path, 'market_daily_summary')
            logger.info(f"  ✅ Copied {row_count:,} rows to market_daily_summary")
        except Exception as e:
            logger.warning(f"  ⚠️  Failed to copy market_daily_summary: {e}")
            logger.warning("     (Archive still usable, market data can be added later)")

        # Copy additional reference data if requested
        if copy_reference:
            logger.info("")
            logger.info("Copying reference data from datalake.db...")

            for table_name in REFERENCE_TABLES:
                try:
                    row_count = copy_reference_data(DATALAKE_PATH, archive_path, table_name)
                    logger.info(f"  ✅ Copied {row_count:,} rows to {table_name}")
                except Exception as e:
                    logger.error(f"  ⚠️  Failed to copy {table_name}: {e}")
                    logger.error("     (Archive still usable, reference data can be added later)")

            # Get updated file size
            file_size = archive_path.stat().st_size
            file_size_kb = file_size / 1024
            logger.info("")
            logger.info(f"   Updated file size: {file_size_kb:.1f} KB")

        logger.info("")
        logger.info("="*70)
        logger.info("SUCCESS")
        logger.info("="*70)
        logger.info(f"Archive ready: data/sector_archive/{name}.db")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Use Admin TUI to assign symbols to this archive")
        logger.info("  2. Run Friday night archiving to populate tables")
        logger.info(f"  3. Or migrate existing data: python data/health/migrate_symbol_archive.py --symbol XXX --from old_archive --to {name}")

        return 0

    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        if archive_path.exists():
            archive_path.unlink()
        return 2

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if archive_path.exists():
            archive_path.unlink()
        return 2


def main():
    parser = argparse.ArgumentParser(
        description='Create new sector archive database with aligned schema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create empty archive
  python create_sector_archive.py --name crypto

  # Create archive with reference data
  python create_sector_archive.py --name airline_suppliers --copy-reference

  # Validate name without creating
  python create_sector_archive.py --name test --dry-run

Exit Codes:
  0: Success
  1: Validation error (invalid name, already exists)
  2: Database error (schema copy failed)
        """
    )

    parser.add_argument(
        '--name',
        required=True,
        help='Archive name (lowercase, underscores only)'
    )

    parser.add_argument(
        '--copy-reference',
        action='store_true',
        help='Copy additional reference data from datalake.db (market_daily_summary is always copied)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate name and show what would be created (no actual creation)'
    )

    args = parser.parse_args()

    exit_code = create_sector_archive(args.name, args.copy_reference, args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
