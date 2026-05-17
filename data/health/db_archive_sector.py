#!/usr/bin/env python3
"""
Sector-Based Database Archiver (db_archive_sector.py)
------------------------------------------------------
Three-tier retention policy archiving to sector-specific databases.

Tier 1 (7d, MOVE):  flow_options_scans, flow_alerts (COPY override — kept in prod)
Tier 2 (30d, MOVE): option_contracts (hybrid: expired OR older than 30d)
Tier 3 (90d, COPY): Reference data (historical_prices, earnings_events, news_*,
                    market_daily_summary) AND, with per-table 300d
                    retention_days_override: option_symbol_summary,
                    flow_symbol_summary, flow_daily_aggregates

P028 (2026-05-15): tier1 retention cut 15→7d, summary tables migrated tier2→tier3
with 300d override, new flow_daily_aggregates table added to tier3, and
per-table `retention_days_override` plumbing added at 5 sites (tier1/2/3
dispatchers, cleanup_tier3_production, analyze_archive_impact).

Routes data to data/sector_archive/{sector}.db based on symbol.archive_db in
the symbol_metadata table.

Usage:
  python data/health/db_archive_sector.py --all-tiers              # Production run
  python data/health/db_archive_sector.py --tier 1                 # Just Tier 1
  python data/health/db_archive_sector.py --test-mode              # Test on Airlines only
  python data/health/db_archive_sector.py --test-mode --tier 1     # Test Tier 1 on Airlines
  python data/health/db_archive_sector.py --dry-run                # Analyze impact, no writes

Author: Ben (with assistance from Claude)
"""

import os
import sys
import sqlite3
import argparse
import signal
import time
import json
import logging
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

# Force UTF-8 encoding for Windows console
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

from timezone_utils import now_eastern

# =============================================================================
# LOGGING SETUP
# =============================================================================

# Module-level logger — initialized by setup_logging(), used throughout
logger = logging.getLogger('DB_ARCHIVE')

def setup_logging():
    """Set up logging to centralized logs directory with both file and console output.

    Uses split formatters:
      - Console: short format (HH:MM:SS - message) for clean orchestrator streaming
      - File: full format (YYYY-MM-DD HH:MM:SS - DB_ARCHIVE - LEVEL - message) for forensics
    """
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    date_str = now_eastern().strftime('%Y-%m-%d')
    log_file = os.path.join(logs_dir, f'db_archive_{date_str}.log')

    # Console handler - short format for orchestrator streaming
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(message)s',
        datefmt='%H:%M:%S'
    ))

    # File handler - full format for forensic analysis
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    # Configure named logger (not root) to avoid cross-contamination
    logger = logging.getLogger('DB_ARCHIVE')
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # prevent root logger duplication

    return logger

def setup_diagnostic_logging():
    """Set up separate diagnostic log for high-level summaries only

    Returns:
        logging.Logger: Diagnostic logger instance
    """
    logs_dir = os.path.join(project_root, 'logs', 'diagnostic')
    os.makedirs(logs_dir, exist_ok=True)

    date_str = now_eastern().strftime('%Y-%m-%d')
    logfile_name = f'db_archive_{date_str}.log'
    logfile = os.path.join(logs_dir, logfile_name)

    diag_logger = logging.getLogger('db_archive_diagnostic')
    diag_logger.setLevel(logging.INFO)
    diag_logger.propagate = False  # Don't send to root logger

    # Clear existing handlers
    diag_logger.handlers = []

    # File handler only (no console spam)
    file_handler = logging.FileHandler(logfile, encoding='utf-8')
    formatter = logging.Formatter('%(message)s')  # Simple format
    file_handler.setFormatter(formatter)
    diag_logger.addHandler(file_handler)

    return diag_logger

def log_diagnostic_summary(diag_logger, tier, **metrics):
    """Write high-level diagnostic summary for archive operations

    Args:
        diag_logger: Diagnostic logger instance
        tier: Tier number (1, 2, 3) or 'complete' for final summary
        **metrics: Tier-specific metrics to log
    """
    try:
        now = now_eastern().strftime('%Y-%m-%d %H:%M:%S')

        if tier == 'start':
            # Archive start message
            time_limit = metrics.get('time_limit_hours', 0)
            if time_limit > 0:
                diag_logger.info(f"[{now}] Archive Started | Time Limit: {time_limit:.1f} hours")
            else:
                diag_logger.info(f"[{now}] Archive Started")

        elif tier in [1, 2, 3]:
            # Tier completion summary
            rows_archived = metrics.get('rows_archived', 0)
            rows_deleted = metrics.get('rows_deleted', 0)
            sectors_affected = metrics.get('sectors_affected', set())
            sectors = len(sectors_affected) if isinstance(sectors_affected, set) else sectors_affected
            duration = metrics.get('duration_seconds', 0)
            errors = metrics.get('errors', 0)

            # Format tier-specific message
            if tier == 3:
                # Tier 3 is COPY mode (no deletes)
                msg = f"[{now}] Tier {tier} Complete: {rows_archived:,} rows archived | {sectors} sectors | {duration/3600:.1f} hours"
            else:
                # Tier 1 & 2 are MOVE mode (archive + delete)
                msg = f"[{now}] Tier {tier} Complete: {rows_archived:,} rows archived, {rows_deleted:,} deleted | {sectors} sectors | {duration/3600:.1f} hours"

            if errors > 0:
                msg += f" | {errors} errors"

            diag_logger.info(msg)

        elif tier == 'complete':
            # Final summary
            total_archived = metrics.get('total_archived', 0)
            total_deleted = metrics.get('total_deleted', 0)
            total_time = metrics.get('total_time_seconds', 0)
            total_errors = metrics.get('total_errors', 0)
            success = metrics.get('success', False)

            diag_logger.info(f"[{now}] Archive Complete | Total: {total_archived:,} rows archived, {total_deleted:,} deleted | {total_time/3600:.1f} hours | Success: {'YES' if success else 'NO'}")
            if total_errors > 0:
                diag_logger.info(f"[{now}] Total Errors: {total_errors}")

    except Exception as e:
        logger.error(f"Error writing diagnostic summary: {e}")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_duration(seconds):
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return "{:.1f}s".format(seconds)
    elif seconds < 3600:
        return "{:.1f} min".format(seconds / 60)
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return "{}h {}m".format(hours, mins)


def _rows_label(count):
    """Format row count with singular/plural grammar."""
    return "1 row" if count == 1 else "{:,} rows".format(count)


def _configure_archive_connection(conn):
    """Apply PRAGMAs for bulk archive writes on HDD.

    Uses WAL mode + NORMAL sync for crash safety while still being fast.
    The big cache and WAL batching provide most of the speed benefit
    without risking corruption on power loss or antivirus interference.
    """
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -256000")  # 256 MB


def _drop_archive_indexes(archive_path, table_name):
    """Drop secondary indexes on a table in an archive database.

    Archives are index-free by policy (write-heavy, rarely queried).
    This strips any leftover indexes from before the policy change.
    PK-backing autoindexes (sql IS NULL) are excluded — they can't be dropped.
    """
    indexes = []
    try:
        with sqlite3.connect(archive_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                (table_name,)
            )
            indexes = cursor.fetchall()
            for idx_name, _ in indexes:
                cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")
            conn.commit()
        if indexes:
            logger.debug(f"  Dropped {len(indexes)} indexes on {table_name} in {os.path.basename(archive_path)}")
    except Exception as e:
        logger.warning(f"  Index drop failed for {table_name} in {os.path.basename(archive_path)}: {e}")
    return indexes



# Schema migration tracking for P-066: first-only INFO, rest at DEBUG
_schema_migrations_logged = set()  # Tracks (table_name, column_name) tuples already reported at INFO
_schema_migration_counts = {}  # Tracks {(table_name, column_name): count_of_sectors} for summary


def _log_schema_migration_summary(table_name):
    """Log a summary of schema migrations for a table, then clear tracking for that table.

    Called after all sectors have been processed for a given table.
    """
    summaries = []
    keys_to_remove = []
    for key, count in _schema_migration_counts.items():
        if key[0] == table_name:
            summaries.append((key[1], count))
            keys_to_remove.append(key)

    for col_name, count in summaries:
        if count > 1:
            logger.info(f"  Schema sync: added {col_name} to {table_name} in {count} sector archives")

    # Clean up tracking for this table
    for key in keys_to_remove:
        _schema_migration_counts.pop(key, None)
        _schema_migrations_logged.discard(key)


# Configuration
DEFAULT_SOURCE_DB = 'datalake.db'  # Production database
TEST_SOURCE_DB = 'archive_2025_10.db'  # Test subset (October 2025 data)

# Set source database (production mode)
SOURCE_DB = DEFAULT_SOURCE_DB

# Global flags for graceful shutdown
shutdown_requested = False
time_limit_seconds = None
script_start_time = None

# Three-tier archival policy configuration
TIER_POLICIES = {
    'tier1': {
        'retention_days': 7,  # P028: cut 15→7. flow_alerts unaffected (mode='copy' override skips DELETE)
        'mode': 'move',  # INSERT into archive + DELETE from production
        'tables': {
            'flow_options_scans': {
                'date_column': 'trade_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',  # Route by symbol to sector archive
                'primary_key': ['contract_hash', 'scan_timestamp']
            },
            'flow_alerts': {
                'date_column': 'trade_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['id'],
                'mode': 'copy'  # Table-level override: copy to archives, don't delete from production
            }
        }
    },
    'tier2': {
        'retention_days': 30,
        'mode': 'move',  # INSERT into archive + DELETE from production
        'tables': {
            'option_contracts': {
                'date_column': 'trade_date',
                'expiration_column': 'expiration_date',  # Special: hybrid strategy
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['contract_hash', 'trade_date'],
                'hybrid_strategy': True  # Archive if expired OR old
            }
        }
    },
    'tier3': {
        'retention_days': 90,
        'mode': 'copy',  # INSERT into archive, DELETE from production in separate cleanup pass
        'tables': {
            'historical_prices': {
                'date_column': 'trade_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['symbol', 'trade_date'],
                'skip_cleanup': True  # Retained in production — small table, needed by post-earnings calc
            },
            'earnings_events': {
                'date_column': 'earnings_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['symbol', 'earnings_date'],
                'skip_cleanup': True  # Retained in production — small table, needed by post-earnings calc
            },
            'news_symbol_sentiment': {
                'date_column': 'article_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['article_url', 'symbol']
            },
            'news_articles': {
                'date_column': 'article_date',
                'symbols_column': 'symbols_mentioned',  # JSON array
                'routing': 'symbols_mentioned',  # Special: parse JSON and route to multiple sectors
                'primary_key': ['article_url']
            },
            'market_daily_summary': {
                'date_column': 'trade_date',
                'routing': 'all_sectors',  # Special: copy to every sector archive
                'primary_key': ['trade_date']
            },
            'option_symbol_summary': {
                'date_column': 'trade_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['symbol', 'trade_date'],
                'retention_days_override': 300  # P028: extended retention for baseline/research
            },
            'flow_symbol_summary': {
                'date_column': 'trade_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['trade_date', 'symbol'],  # PK order differs from option_symbol_summary
                'retention_days_override': 300  # P028: extended retention for baseline/research
            },
            'flow_daily_aggregates': {
                'date_column': 'trade_date',
                'symbol_column': 'symbol',
                'routing': 'symbol',
                'primary_key': ['symbol', 'trade_date'],
                'retention_days_override': 300  # P028: new aggregate replacing flow_options_scans for baselines
            }
        }
    }
}


def preflight_database_check():
    """Pre-flight check: verify the production database is writable.

    Opens a connection with a short timeout and attempts a BEGIN IMMEDIATE
    transaction to test write access. This catches locked databases early
    instead of silently waiting for minutes per batch.

    Returns:
        bool: True if database is writable, False if locked or inaccessible
    """
    source_path = os.path.join(project_root, 'data', SOURCE_DB)

    if not os.path.exists(source_path):
        print(f"❌ PRE-FLIGHT FAILED: Database not found: {source_path}")
        logger.error(f"Pre-flight failed: database not found at {source_path}")
        return False

    try:
        conn = sqlite3.connect(source_path, timeout=5.0)
        conn.execute("PRAGMA busy_timeout = 5000")  # 5 second timeout
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        conn.close()
        print("✅ Pre-flight check: Database is writable")
        logger.debug("Pre-flight check PASSED: database is writable")
        return True
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            print(f"❌ PRE-FLIGHT FAILED: Database is locked!")
            print(f"   Another process holds a write lock on {SOURCE_DB}")
            print(f"   Archive cannot proceed until the lock is released.")
            logger.error(f"Pre-flight FAILED: database is locked - {e}")
        else:
            print(f"❌ PRE-FLIGHT FAILED: Database error: {e}")
            logger.error(f"Pre-flight FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ PRE-FLIGHT FAILED: Unexpected error: {e}")
        logger.error(f"Pre-flight FAILED: unexpected error - {e}")
        return False


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully"""
    global shutdown_requested
    shutdown_requested = True
    print("\n⚠️ SHUTDOWN REQUESTED - Will complete current operation safely...")
    print("Please wait for current batch to finish to avoid database corruption.")


def check_shutdown():
    """Check if shutdown was requested or time limit exceeded"""
    global shutdown_requested, time_limit_seconds, script_start_time

    if shutdown_requested:
        return True

    # Check time limit if set
    if time_limit_seconds is not None and script_start_time is not None:
        elapsed = time.time() - script_start_time
        if elapsed >= time_limit_seconds:
            print(f"\n⏰ TIME LIMIT REACHED ({elapsed:.0f}s / {time_limit_seconds}s) - Graceful shutdown...")
            return True

    return False


def _retry_on_lock(operation, description, max_retries=3, delays=(5, 15, 30)):
    """Retry a database operation on 'database is locked' errors.

    Args:
        operation: Callable that performs the database operation. Should raise on failure.
        description: Human-readable description for log messages (e.g. "Tier1 airlines batch 3")
        max_retries: Maximum number of retry attempts
        delays: Tuple of sleep durations in seconds between retries

    Returns:
        tuple: (success: bool, result_or_error: any)
            On success: (True, operation_return_value)
            On failure: (False, error_string)
    """
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            result = operation()
            return (True, result)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < max_retries:
                delay = delays[attempt] if attempt < len(delays) else delays[-1]
                print(f"      ⚠️ Database locked on {description} - retry {attempt + 1}/{max_retries} in {delay}s...")
                logger.warning(f"Database locked on {description} - retry {attempt + 1}/{max_retries} in {delay}s")
                time.sleep(delay)
                continue
            else:
                return (False, str(e))
        except Exception as e:
            return (False, str(e))

    return (False, f"Max retries ({max_retries}) exceeded for {description}")


def introspect_table_schema(source_db, table_name):
    """Introspect table schema from source database.

    Args:
        source_db (str): Source database filename
        table_name (str): Table name to introspect

    Returns:
        dict: Schema information with 'columns' and 'create_statement'
    """
    db_path = os.path.join(project_root, 'data', source_db)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Get actual CREATE TABLE statement from sqlite_master
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        result = cursor.fetchone()

        if not result:
            return None

        create_stmt = result[0]

        # Replace CREATE TABLE with CREATE TABLE IF NOT EXISTS (handle both quoted and unquoted)
        create_stmt = create_stmt.replace('CREATE TABLE "{}\"'.format(table_name),
                                          'CREATE TABLE IF NOT EXISTS "{}\"'.format(table_name))
        create_stmt = create_stmt.replace("CREATE TABLE {}".format(table_name),
                                          "CREATE TABLE IF NOT EXISTS {}".format(table_name))

        # Get column information for column list
        cursor.execute("PRAGMA table_info({})".format(table_name))
        columns = cursor.fetchall()

        return {
            'columns': [col[1] for col in columns],
            'create_statement': create_stmt
        }


def get_symbol_archive_db(symbol, source_db='datalake.db'):
    """Get archive database name for a symbol from symbol_metadata table.

    Uses archive_db column which handles industry-specific routing
    (airlines, asset_management) and sector-based routing.

    Args:
        symbol (str): Stock symbol
        source_db (str): Source database filename

    Returns:
        str: Archive database name (e.g., 'airlines', 'technology'), or None if not found
    """
    db_path = os.path.join(project_root, 'data', source_db)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT archive_db FROM symbol_metadata WHERE symbol=?", (symbol,))
        result = cursor.fetchone()

        if result:
            return result[0]
        else:
            return None


def get_all_archive_dbs(source_db='datalake.db'):
    """Get list of all unique archive databases from symbol_metadata.

    Args:
        source_db (str): Source database filename

    Returns:
        list: List of archive database names (e.g., ['airlines', 'technology', ...])
    """
    db_path = os.path.join(project_root, 'data', source_db)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT archive_db FROM symbol_metadata WHERE archive_db IS NOT NULL ORDER BY archive_db")
        return [row[0] for row in cursor.fetchall()]


def get_archive_db_path(archive_db_name):
    """Get path to archive database.

    Args:
        archive_db_name (str): Archive database name (e.g., 'airlines', 'technology')

    Returns:
        str: Path to archive database file
    """
    # archive_db values are already normalized (lowercase, underscores)
    return os.path.join(project_root, 'data', 'sector_archive', f'{archive_db_name}.db')


def ensure_table_in_archive(archive_path, table_name, source_db='datalake.db'):
    """Ensure table exists in sector archive with correct schema.

    If table exists but has missing columns, adds them via ALTER TABLE.

    Args:
        archive_path (str): Path to sector archive database
        table_name (str): Table name to create
        source_db (str): Source database to introspect schema from

    Returns:
        bool: True if table exists/created/updated, False on error
    """
    try:
        # Get schema from source database
        schema = introspect_table_schema(source_db, table_name)

        if not schema:
            print(f"      ⚠️ WARNING: Could not introspect schema for {table_name}")
            return False

        # Ensure sector archive directory exists
        os.makedirs(os.path.dirname(archive_path), exist_ok=True)

        with sqlite3.connect(archive_path) as archive_conn:
            archive_cursor = archive_conn.cursor()

            # Check if table already exists
            archive_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            table_exists = archive_cursor.fetchone() is not None

            if table_exists:
                # Table exists - check if schema needs updating
                archive_cursor.execute(f"PRAGMA table_info({table_name})")
                existing_columns = {col[1] for col in archive_cursor.fetchall()}  # Set of column names
                source_columns = set(schema['columns'])

                missing_columns = source_columns - existing_columns

                if missing_columns:
                    # P-066: First occurrence at INFO, subsequent at DEBUG
                    sector_name = os.path.basename(archive_path).replace('.db', '')
                    is_first_for_any_column = False
                    for col_name in missing_columns:
                        key = (table_name, col_name)
                        if key not in _schema_migrations_logged:
                            is_first_for_any_column = True
                            break

                    if is_first_for_any_column:
                        print(f"      🔧 Updating {table_name} schema: adding {len(missing_columns)} missing columns")
                        logger.info(f"Adding {len(missing_columns)} missing columns to {table_name} in {os.path.basename(archive_path)}")
                    else:
                        logger.debug(f"Adding {len(missing_columns)} missing columns to {table_name} in {os.path.basename(archive_path)}")

                    # Get full column definitions from source database
                    source_path = os.path.join(project_root, 'data', source_db)
                    with sqlite3.connect(source_path) as source_conn:
                        source_cursor = source_conn.cursor()
                        source_cursor.execute(f"PRAGMA table_info({table_name})")
                        source_col_info = {col[1]: col for col in source_cursor.fetchall()}  # {name: (cid, name, type, notnull, dflt_value, pk)}

                    # Add missing columns one by one
                    for col_name in missing_columns:
                        col_info = source_col_info[col_name]
                        col_type = col_info[2]  # type
                        notnull = col_info[3]  # notnull
                        default = col_info[4]  # default value

                        # Build ALTER TABLE statement
                        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"

                        # SQLite doesn't support NOT NULL in ALTER TABLE if there's no default
                        # So we only add defaults, not NOT NULL constraints on ALTER
                        if default is not None:
                            alter_sql += f" DEFAULT {default}"

                        try:
                            archive_cursor.execute(alter_sql)
                            key = (table_name, col_name)
                            if key not in _schema_migrations_logged:
                                logger.info(f"  Added column: {col_name} {col_type}")
                                _schema_migrations_logged.add(key)
                            else:
                                logger.debug(f"  Added column: {col_name} {col_type} (in {sector_name})")
                            # Track count for summary
                            if key not in _schema_migration_counts:
                                _schema_migration_counts[key] = 0
                            _schema_migration_counts[key] += 1
                        except Exception as col_error:
                            print(f"      ⚠️ WARNING: Could not add column {col_name}: {col_error}")
                            logger.warning(f"  Failed to add column {col_name}: {col_error}")
            else:
                # Table doesn't exist - create it with full schema
                archive_cursor.execute(schema['create_statement'])

            # NOTE: Secondary indexes (date, symbol) intentionally NOT created on archives.
            # Archives are write-heavy (weekly bulk inserts) and rarely queried.
            # Indexes are dropped by _drop_archive_indexes() during archiving.
            # If you need fast queries for research, manually CREATE INDEX on the
            # specific sector archive — see memory/archive_no_indexes.md.

        return True

    except Exception as e:
        print(f"      ❌ ERROR: Failed to ensure table {table_name} in {os.path.basename(archive_path)}: {e}")

        # Trigger autofix for table creation failures
        from tools.autofix import handle_error
        handle_error(
            error_type='archive_table_creation_failed',
            context={'table': table_name, 'archive': os.path.basename(archive_path), 'error': str(e)},
            severity='ERROR'  # Batch mode - archive continues with other tables
        )
        return False


def archive_table_tier1_tier2(table_name, tier_config, table_config, retention_days, test_mode=False):
    """Archive Tier 1 or Tier 2 table to sector archives (MOVE or COPY mode).

    Supports table-level mode override for mixed MOVE/COPY behavior within a tier.

    Args:
        table_name (str): Table name to archive
        tier_config (dict): Tier configuration
        table_config (dict): Table-specific configuration
        retention_days (int): Retention window in days
        test_mode (bool): If True, only process Airlines sector

    Returns:
        dict: Statistics (total_archived, total_deleted, sectors_affected, errors)
    """
    source_db = SOURCE_DB
    source_path = os.path.join(project_root, 'data', source_db)
    batch_size = 50000

    # Check for table-level mode override
    table_mode = table_config.get('mode', tier_config['mode'])

    stats = {
        'total_archived': 0,
        'total_deleted': 0,
        'sectors_affected': set(),  # Track sector names (set, not count)
        'errors': []
    }

    # Build WHERE clause for retention
    date_column = table_config['date_column']
    cutoff_date = (datetime.now().date() - timedelta(days=retention_days)).strftime('%Y-%m-%d')

    # Special handling for option_contracts hybrid strategy
    if table_config.get('hybrid_strategy'):
        expiration_column = table_config['expiration_column']
        where_clause = f"({expiration_column} < DATE('now') OR {date_column} < ?)"
        params = (cutoff_date,)
    else:
        where_clause = f"{date_column} < ?"
        params = (cutoff_date,)

    # Add test mode filter (airlines archive only)
    if test_mode:
        symbol_column = table_config.get('symbol_column')
        if symbol_column:
            where_clause += f" AND {symbol_column} IN (SELECT symbol FROM symbol_metadata WHERE archive_db='airlines')"

    # P-067: Check total row count first — skip entirely if 0 rows
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}", params)
        grand_total = cursor.fetchone()[0]

    if grand_total == 0:
        print(f"\n  {table_name}: 0 rows (skipped)")
        logger.info(f"Archiving {table_name} | cutoff: {cutoff_date} | 0 rows, skipped")
        return stats

    print(f"\n  Archiving {table_name} (cutoff: {cutoff_date}, mode: {table_mode.upper()})")
    logger.info(f"Archiving {table_name} | cutoff: {cutoff_date} | mode: {table_mode.upper()} | retention: {retention_days}d")

    # Get all sectors to process
    if test_mode:
        sectors = ['airlines']
    else:
        sectors = get_all_archive_dbs(source_db)

    # Process each sector
    for sector in sectors:
        if check_shutdown():
            print("    ⚠️ Shutdown requested - stopping archive")
            break

        sector_archive_path = get_archive_db_path(sector)

        # Ensure table exists in sector archive
        if not ensure_table_in_archive(sector_archive_path, table_name, source_db):
            stats['errors'].append(f"{sector}: Failed to create table")
            continue

        # Build sector-specific WHERE clause
        symbol_column = table_config.get('symbol_column')
        if not symbol_column:
            # Skip tables without symbol column (shouldn't happen for Tier 1/2)
            continue

        sector_where = f"{where_clause} AND {symbol_column} IN (SELECT symbol FROM symbol_metadata WHERE archive_db=?)"
        sector_params = params + (sector,)

        # Count rows to archive for this sector
        with sqlite3.connect(source_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {sector_where}", sector_params)
            sector_total = cursor.fetchone()[0]

        if sector_total == 0:
            continue

        print(f"    Processing {sector}: {_rows_label(sector_total)}")
        logger.info(f"  {table_name} | {sector}: {sector_total:,} rows to process")
        stats['sectors_affected'].add(sector)

        # Drop any leftover secondary indexes (archives are index-free by policy)
        _drop_archive_indexes(sector_archive_path, table_name)

        # Calculate total batches for progress suppression decision
        total_batches = (sector_total + batch_size - 1) // batch_size

        # Archive in batches using SEPARATE connections (no ATTACH)
        # This avoids cross-database WAL locking where the source db lock
        # extends across both databases, widening the contention window.
        # Pattern: Read from source → Insert into archive → Delete from source
        sector_archived = 0
        sector_deleted = 0
        batch_num = 0
        batch_offset = 0  # For COPY mode pagination (MOVE mode uses DELETE to advance)
        pk_cols = table_config['primary_key']
        sector_lock_failed = False

        # ORDER BY rowid for sequential source reads (much faster on HDD than PK order)
        order_by = "rowid"

        # Get column names for parameterized insert
        schema = introspect_table_schema(source_db, table_name)
        if not schema:
            stats['errors'].append(f"{sector}: Could not introspect schema")
            continue
        column_names = schema['columns']
        placeholders = ', '.join(['?'] * len(column_names))
        columns_str = ', '.join(column_names)

        while True:
            batch_num += 1

            def _run_batch_t12():
                """Execute a single Tier 1/2 batch with separate connections."""
                # Step 1: Read batch from source (short-lived connection)
                # MOVE mode: DELETE advances the window, so LIMIT alone works
                # COPY mode: No deletion, so use OFFSET to paginate
                with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                    src_conn.execute("PRAGMA busy_timeout = 30000")
                    src_cursor = src_conn.cursor()
                    if table_mode == 'copy':
                        select_sql = f"SELECT * FROM {table_name} WHERE {sector_where} ORDER BY {order_by} LIMIT ? OFFSET ?"
                        src_cursor.execute(select_sql, sector_params + (batch_size, batch_offset))
                    else:
                        select_sql = f"SELECT * FROM {table_name} WHERE {sector_where} ORDER BY {order_by} LIMIT ?"
                        src_cursor.execute(select_sql, sector_params + (batch_size,))
                    rows = src_cursor.fetchall()

                if not rows:
                    return (0, 0, True)  # done

                # Step 2: Insert into archive (separate connection to sector archive)
                with sqlite3.connect(sector_archive_path, timeout=30.0) as arc_conn:
                    _configure_archive_connection(arc_conn)
                    insert_sql = f"INSERT OR IGNORE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                    arc_conn.executemany(insert_sql, rows)
                    arc_conn.commit()

                # Step 3: Delete from source (MOVE mode only, short-lived connection)
                # Uses subquery-based DELETE (same pattern as original ATTACH code)
                # to avoid "Expression tree too large" with big OR-based PK lists
                deleted = 0
                if table_mode == 'move':
                    with sqlite3.connect(source_path, timeout=30.0) as del_conn:
                        del_conn.execute("PRAGMA busy_timeout = 30000")
                        del_cursor = del_conn.cursor()
                        pk_select = ', '.join(pk_cols)
                        if len(pk_cols) == 1:
                            del_sql = f"""DELETE FROM {table_name}
                                WHERE {pk_cols[0]} IN (
                                    SELECT {pk_cols[0]} FROM {table_name}
                                    WHERE {sector_where} ORDER BY {order_by} LIMIT ?
                                )"""
                        else:
                            pk_tuple = f"({pk_select})"
                            del_sql = f"""DELETE FROM {table_name}
                                WHERE {pk_tuple} IN (
                                    SELECT {pk_select} FROM {table_name}
                                    WHERE {sector_where} ORDER BY {order_by} LIMIT ?
                                )"""
                        del_cursor.execute(del_sql, sector_params + (batch_size,))
                        deleted = del_cursor.rowcount
                        del_conn.commit()

                return (len(rows), deleted, False)

            batch_desc = f"T1/T2 {table_name} {sector} batch {batch_num}"
            success, result = _retry_on_lock(_run_batch_t12, batch_desc)

            if success:
                inserted_count, deleted_count, done = result
                if done:
                    break

                sector_archived += inserted_count
                sector_deleted += deleted_count
                if table_mode == 'copy':
                    batch_offset += inserted_count  # Advance offset for COPY mode pagination

                # Progress indicator with timestamp (suppress for single-batch sectors)
                timestamp = now_eastern().strftime('%H:%M:%S')

                if table_mode == 'copy':
                    progress_pct = (sector_archived / sector_total) * 100
                    if total_batches >= 2:
                        print(f"      [{timestamp}] Batch {batch_num}: {_rows_label(inserted_count)} copied ({progress_pct:.1f}%)")
                else:
                    progress_pct = (sector_deleted / sector_total) * 100
                    if total_batches >= 2:
                        if inserted_count != deleted_count:
                            print(f"      [{timestamp}] Batch {batch_num}: Inserted {inserted_count:,}, Deleted {deleted_count:,} ({inserted_count - deleted_count:,} duplicates)")
                        else:
                            print(f"      [{timestamp}] Batch {batch_num}: {_rows_label(deleted_count)} ({progress_pct:.1f}%)")

                # Log every 5th batch to file for forensic detail
                if batch_num % 5 == 0:
                    logger.debug(f"  {table_name} | {sector}: batch {batch_num} | archived={sector_archived:,} deleted={sector_deleted:,} ({progress_pct:.1f}%)")
            else:
                error_str = result

                if "database is locked" in error_str.lower():
                    sector_lock_failed = True
                    stats['errors'].append(f"{sector}: Batch {batch_num} locked after retries: {error_str}")
                    print(f"      ❌ LOCKED: {sector} batch {batch_num} failed after retries")
                    logger.error(f"  {table_name} | {sector}: batch {batch_num} LOCKED after retries")
                else:
                    stats['errors'].append(f"{sector}: Batch {batch_num} failed: {error_str}")
                    print(f"      ❌ ERROR: Batch {batch_num} failed: {error_str}")

                    # Trigger autofix for non-lock batch failures (tier 1/2)
                    from tools.autofix import handle_error
                    handle_error(
                        error_type='archive_batch_tier1_tier2_failed',
                        context={'sector': sector, 'batch': batch_num, 'table': table_name, 'error': error_str},
                        severity='ERROR'
                    )
                break

        if table_mode == 'copy':
            print(f"      ✓ {sector}: {_rows_label(sector_archived)} copied to archive")
            logger.info(f"  {table_name} | {sector} DONE: {sector_archived:,} rows copied")
        else:
            print(f"      ✓ {sector}: {_rows_label(sector_deleted)} archived")
            logger.info(f"  {table_name} | {sector} DONE: {sector_archived:,} archived, {sector_deleted:,} deleted")
        stats['total_archived'] += sector_archived
        stats['total_deleted'] += sector_deleted

    # P-066: Log schema migration summary after all sectors processed for this table
    _log_schema_migration_summary(table_name)

    return stats


def archive_table_tier3(table_name, tier_config, table_config, retention_days, test_mode=False):
    """Archive Tier 3 table to sector archives (COPY mode - no deletion yet).

    Args:
        table_name (str): Table name to archive
        tier_config (dict): Tier configuration
        table_config (dict): Table-specific configuration
        retention_days (int): Retention window in days
        test_mode (bool): If True, only process Airlines sector

    Returns:
        dict: Statistics (total_archived, sectors_affected, errors)
    """
    source_db = SOURCE_DB
    source_path = os.path.join(project_root, 'data', source_db)
    batch_size = 50000

    stats = {
        'total_archived': 0,
        'sectors_affected': set(),  # Track sector names (set, not count)
        'errors': []
    }

    # Build WHERE clause for retention
    date_column = table_config['date_column']
    cutoff_date = (datetime.now().date() - timedelta(days=retention_days)).strftime('%Y-%m-%d')
    where_clause = f"{date_column} < ?"
    params = (cutoff_date,)

    routing = table_config.get('routing')

    # Special handling for market_daily_summary (copy to all sectors)
    if routing == 'all_sectors':
        return archive_market_data_all_sectors(table_name, table_config, cutoff_date, test_mode)

    # Special handling for news_articles (parse symbols_mentioned JSON)
    if routing == 'symbols_mentioned':
        return archive_news_articles(table_name, table_config, cutoff_date, test_mode)

    # P-067: Check total row count first — skip entirely if 0 rows
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}", params)
        grand_total = cursor.fetchone()[0]

    if grand_total == 0:
        print(f"\n  {table_name}: 0 rows (skipped)")
        logger.info(f"Archiving {table_name} | cutoff: {cutoff_date} | 0 rows, skipped")
        return stats

    # Standard symbol-based routing
    print(f"\n  Archiving {table_name} (cutoff: {cutoff_date}, mode: COPY)")
    logger.info(f"Archiving {table_name} | cutoff: {cutoff_date} | mode: COPY | retention: {retention_days}d")

    # Get all sectors to process
    if test_mode:
        sectors = ['airlines']
    else:
        sectors = get_all_archive_dbs(source_db)

    # Process each sector
    for sector in sectors:
        if check_shutdown():
            print("    ⚠️ Shutdown requested - stopping archive")
            break

        sector_archive_path = get_archive_db_path(sector)

        # Ensure table exists in sector archive
        if not ensure_table_in_archive(sector_archive_path, table_name, source_db):
            stats['errors'].append(f"{sector}: Failed to create table")
            continue

        # Build sector-specific WHERE clause
        symbol_column = table_config.get('symbol_column')
        if not symbol_column:
            continue

        sector_where = f"{where_clause} AND {symbol_column} IN (SELECT symbol FROM symbol_metadata WHERE archive_db=?)"
        sector_params = params + (sector,)

        # Count rows to archive for this sector
        with sqlite3.connect(source_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {sector_where}", sector_params)
            sector_total = cursor.fetchone()[0]

        if sector_total == 0:
            continue

        print(f"    Processing {sector}: {_rows_label(sector_total)}")
        logger.info(f"  {table_name} | {sector}: {sector_total:,} rows to process")
        stats['sectors_affected'].add(sector)

        # Drop any leftover secondary indexes (archives are index-free by policy)
        _drop_archive_indexes(sector_archive_path, table_name)

        # Calculate total batches for progress suppression decision
        total_batches = (sector_total + batch_size - 1) // batch_size

        # Archive in batches using SEPARATE connections (no ATTACH, COPY mode - no DELETE)
        # Same pattern as Tier 1/2: avoids cross-database WAL locking.
        # Since COPY mode doesn't delete from source, we use OFFSET to paginate.
        sector_archived = 0
        batch_num = 0
        batch_offset = 0  # Track offset since rows aren't deleted from source
        pk_cols = table_config['primary_key']
        sector_lock_failed = False

        # ORDER BY rowid for sequential source reads (much faster on HDD than PK order)
        order_by = "rowid"

        # Get column names for parameterized insert
        schema = introspect_table_schema(source_db, table_name)
        if not schema:
            stats['errors'].append(f"{sector}: Could not introspect schema")
            continue
        column_names = schema['columns']
        placeholders = ', '.join(['?'] * len(column_names))
        columns_str = ', '.join(column_names)

        while True:
            batch_num += 1

            def _run_batch_t3():
                """Execute a single Tier 3 batch with separate connections."""
                # Step 1: Read batch from source using OFFSET (short-lived connection)
                with sqlite3.connect(source_path, timeout=30.0) as src_conn:
                    src_conn.execute("PRAGMA busy_timeout = 30000")
                    src_cursor = src_conn.cursor()
                    select_sql = f"SELECT * FROM {table_name} WHERE {sector_where} ORDER BY {order_by} LIMIT ? OFFSET ?"
                    src_cursor.execute(select_sql, sector_params + (batch_size, batch_offset))
                    rows = src_cursor.fetchall()

                if not rows:
                    return (0, True)  # done

                # Step 2: Insert into archive (separate connection to sector archive)
                with sqlite3.connect(sector_archive_path, timeout=30.0) as arc_conn:
                    _configure_archive_connection(arc_conn)
                    insert_sql = f"INSERT OR IGNORE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                    arc_conn.executemany(insert_sql, rows)
                    arc_conn.commit()

                # No Step 3 - Tier 3 is COPY only (no delete from source)
                return (len(rows), False)

            batch_desc = f"T3 {table_name} {sector} batch {batch_num}"
            success, result = _retry_on_lock(_run_batch_t3, batch_desc)

            if success:
                inserted_count, done = result
                if done:
                    break

                sector_archived += inserted_count
                batch_offset += inserted_count  # Advance offset for COPY mode pagination

                # Progress indicator with timestamp (suppress for single-batch sectors)
                timestamp = now_eastern().strftime('%H:%M:%S')
                progress_pct = (sector_archived / sector_total) * 100 if sector_total > 0 else 100
                if total_batches >= 2:
                    print(f"      [{timestamp}] Batch {batch_num}: {_rows_label(inserted_count)} copied ({progress_pct:.1f}%)")
            else:
                error_str = result

                if "database is locked" in error_str.lower():
                    sector_lock_failed = True
                    stats['errors'].append(f"{sector}: Batch {batch_num} locked after retries: {error_str}")
                    print(f"      ❌ LOCKED: {sector} batch {batch_num} failed after retries")
                    logger.error(f"  {table_name} | {sector}: batch {batch_num} LOCKED after retries")
                else:
                    stats['errors'].append(f"{sector}: Batch {batch_num} failed: {error_str}")
                    print(f"      ❌ ERROR: Batch {batch_num} failed: {error_str}")

                    # Trigger autofix for non-lock batch failures (tier 3)
                    from tools.autofix import handle_error
                    handle_error(
                        error_type='archive_batch_tier3_failed',
                        context={'sector': sector, 'batch': batch_num, 'table': table_name, 'error': error_str},
                        severity='ERROR'
                    )
                break

        print(f"      ✓ {sector}: {_rows_label(sector_archived)} copied")
        logger.info(f"  {table_name} | {sector} DONE: {sector_archived:,} rows copied")
        stats['total_archived'] += sector_archived

    # P-066: Log schema migration summary after all sectors processed for this table
    _log_schema_migration_summary(table_name)

    return stats


def archive_market_data_all_sectors(table_name, table_config, cutoff_date, test_mode=False):
    """Archive market_daily_summary to all sector archives.

    Args:
        table_name (str): Table name (market_daily_summary)
        table_config (dict): Table configuration
        cutoff_date (str): Cutoff date (YYYY-MM-DD)
        test_mode (bool): If True, only process Airlines sector

    Returns:
        dict: Statistics
    """
    source_db = SOURCE_DB
    source_path = os.path.join(project_root, 'data', source_db)

    stats = {
        'total_archived': 0,
        'sectors_affected': set(),  # Track sector names (set, not count)
        'errors': []
    }

    print(f"\n  Archiving {table_name} to all sectors (cutoff: {cutoff_date}, mode: COPY)")
    logger.debug(f"Archiving {table_name} to all sectors | cutoff: {cutoff_date} | mode: COPY")

    # Check if table exists in source database
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            print(f"    ⚠️ Table {table_name} not found in source database")
            return stats

    # Get sectors to process
    if test_mode:
        sectors = ['airlines']
    else:
        sectors = get_all_archive_dbs(source_db)

    # Build WHERE clause
    date_column = table_config['date_column']
    where_clause = f"{date_column} < ?"

    # Count total rows to copy
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}", (cutoff_date,))
        total_rows = cursor.fetchone()[0]

    if total_rows == 0:
        print(f"  {table_name}: 0 rows (skipped)")
        return stats

    # Copy to each sector archive (broadcast: same rows to all sectors)
    sectors_copied = 0

    for sector in sectors:
        if check_shutdown():
            print("    ⚠️ Shutdown requested - stopping archive")
            break

        sector_archive_path = get_archive_db_path(sector)

        # Ensure table exists in sector archive
        if not ensure_table_in_archive(sector_archive_path, table_name, source_db):
            stats['errors'].append(f"{sector}: Failed to create table")
            continue

        # Use separate connections instead of ATTACH to avoid WAL locking issues
        # This prevents conflicts with ensure_table_in_archive()'s recent connection
        try:
            # Read data from source database
            with sqlite3.connect(source_path, timeout=30.0) as source_conn:
                source_conn.row_factory = sqlite3.Row
                source_cursor = source_conn.cursor()
                source_cursor.execute("PRAGMA busy_timeout = 30000")

                # Fetch rows to copy
                select_sql = f"SELECT * FROM {table_name} WHERE {where_clause}"
                source_cursor.execute(select_sql, (cutoff_date,))
                rows = source_cursor.fetchall()

                if not rows:
                    continue  # Nothing to copy for this sector

                # Get column names
                column_names = [desc[0] for desc in source_cursor.description]

            # Write to sector archive database (separate connection)
            with sqlite3.connect(sector_archive_path, timeout=30.0) as archive_conn:
                _configure_archive_connection(archive_conn)
                archive_cursor = archive_conn.cursor()

                # Build INSERT statement
                placeholders = ', '.join(['?'] * len(column_names))
                columns_str = ', '.join(column_names)
                insert_sql = f"INSERT OR IGNORE INTO {table_name} ({columns_str}) VALUES ({placeholders})"

                # Bulk insert using executemany for efficiency
                archive_cursor.executemany(insert_sql, [tuple(row) for row in rows])
                inserted_count = archive_cursor.rowcount
                archive_conn.commit()

                logger.debug(f"  {table_name} | {sector} DONE: {inserted_count:,} rows copied")
                stats['total_archived'] += inserted_count
                stats['sectors_affected'].add(sector)
                sectors_copied += 1

        except Exception as e:
            stats['errors'].append(f"{sector}: {e}")
            print(f"      ❌ ERROR: {sector}: {e}")

            # Trigger autofix for sector processing failures
            from tools.autofix import handle_error
            handle_error(
                error_type='archive_sector_processing_failed',
                context={'sector': sector, 'table': table_name, 'error': str(e)},
                severity='ERROR'  # Batch mode - other sectors continue
            )

    # Single summary line for broadcast table
    if sectors_copied > 0:
        print(f"    ✓ {table_name}: {_rows_label(total_rows)} copied to {sectors_copied} sectors")
        logger.debug(f"  {table_name}: {total_rows:,} rows copied to {sectors_copied} sectors (broadcast)")

    return stats


def archive_news_articles(table_name, table_config, cutoff_date, test_mode=False):
    """Archive news_articles by parsing symbols_mentioned JSON.

    Args:
        table_name (str): Table name (news_articles)
        table_config (dict): Table configuration
        cutoff_date (str): Cutoff date (YYYY-MM-DD)
        test_mode (bool): If True, only process Airlines sector

    Returns:
        dict: Statistics
    """
    source_db = SOURCE_DB
    source_path = os.path.join(project_root, 'data', source_db)

    stats = {
        'total_archived': 0,
        'sectors_affected': set(),  # Track sector names (set, not count)
        'errors': []
    }

    print(f"\n  Archiving {table_name} by symbols_mentioned (cutoff: {cutoff_date}, mode: COPY)")

    # Check if table exists in source database
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not cursor.fetchone():
            print(f"    ⚠️ Table {table_name} not found in source database")
            return stats

    # Get sectors to process
    if test_mode:
        target_sectors = {'airlines'}
    else:
        target_sectors = set(get_all_archive_dbs(source_db))

    # Build WHERE clause
    date_column = table_config['date_column']
    where_clause = f"{date_column} < ?"

    # Get all articles to archive
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM {table_name} WHERE {where_clause}", (cutoff_date,))
        columns = [desc[0] for desc in cursor.description]
        articles = cursor.fetchall()

    if not articles:
        print("    No articles to archive")
        return stats

    print(f"    Processing {len(articles):,} articles")

    # Build sector archives mapping
    sector_archives = {}
    for sector in target_sectors:
        sector_archive_path = get_archive_db_path(sector)
        if ensure_table_in_archive(sector_archive_path, table_name, source_db):
            sector_archives[sector] = sector_archive_path
        else:
            stats['errors'].append(f"{sector}: Failed to create table")

    # Get symbol → archive_db mapping
    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, archive_db FROM symbol_metadata")
        symbol_sector_map = {row[0]: row[1] for row in cursor.fetchall() if row[1]}

    # Process each article
    symbols_mentioned_idx = columns.index('symbols_mentioned') if 'symbols_mentioned' in columns else None
    all_sectors_used = set()  # Track unique sectors across all articles

    for article in articles:
        if check_shutdown():
            print("    ⚠️ Shutdown requested - stopping archive")
            break

        # Parse symbols_mentioned JSON
        if symbols_mentioned_idx is not None and article[symbols_mentioned_idx]:
            try:
                symbols = json.loads(article[symbols_mentioned_idx])
                if not isinstance(symbols, list):
                    symbols = []
            except:
                symbols = []
        else:
            symbols = []

        # Route to sector archives
        sectors_for_article = set()
        for symbol in symbols:
            sector = symbol_sector_map.get(symbol)
            if sector and sector in target_sectors:
                sectors_for_article.add(sector)

        # Insert into each relevant sector archive
        for sector in sectors_for_article:
            if sector not in sector_archives:
                continue

            all_sectors_used.add(sector)  # Track unique sectors

            try:
                with sqlite3.connect(sector_archives[sector]) as archive_conn:
                    _configure_archive_connection(archive_conn)
                    archive_cursor = archive_conn.cursor()

                    # Build INSERT statement
                    placeholders = ','.join(['?'] * len(columns))
                    insert_sql = f"INSERT OR IGNORE INTO {table_name} VALUES ({placeholders})"
                    archive_cursor.execute(insert_sql, article)

                    if archive_cursor.rowcount > 0:
                        stats['total_archived'] += 1

            except Exception as e:
                stats['errors'].append(f"{sector}: Article insert failed: {e}")

                # Trigger autofix for news article archiving failures
                from tools.autofix import handle_error
                handle_error(
                    error_type='archive_news_article_failed',
                    context={'sector': sector, 'error': str(e)},
                    severity='ERROR'  # Batch mode - continues with other articles
                )

    # Track unique sectors across all articles
    stats['sectors_affected'] = all_sectors_used

    print(f"      ✓ Archived {stats['total_archived']:,} article copies across {len(stats['sectors_affected'])} sectors")

    return stats


def cleanup_tier3_production(tier_config, test_mode=False):
    """Delete old Tier 3 data from production after copying to archives.

    Args:
        tier_config (dict): Tier 3 configuration
        test_mode (bool): If True, only cleanup Airlines sector data

    Returns:
        dict: Statistics (total_deleted, errors)
    """
    source_db = SOURCE_DB
    source_path = os.path.join(project_root, 'data', source_db)

    stats = {
        'total_deleted': 0,
        'errors': []
    }

    print(f"\n{'=' * 70}")
    print("TIER 3 CLEANUP: Deleting old reference data from production")
    print("=" * 70)

    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 30000")  # 30 seconds (was 10 min - fail fast)

        for table_name, table_config in tier_config['tables'].items():
            if check_shutdown():
                print("  ⚠️ Shutdown requested - stopping cleanup")
                break

            # Skip tables flagged to remain in production
            if table_config.get('skip_cleanup', False):
                print(f"  - {table_name}: Skipped (retained in production)")
                continue

            # P028: per-table override (skip_cleanup tables short-circuit above, so no wasted lookup)
            retention_days = table_config.get('retention_days_override', tier_config['retention_days'])
            date_column = table_config['date_column']
            cutoff_date = (datetime.now().date() - timedelta(days=retention_days)).strftime('%Y-%m-%d')

            # Build WHERE clause
            where_clause = f"{date_column} < ?"
            params = [cutoff_date]

            # Add test mode filter
            if test_mode:
                symbol_column = table_config.get('symbol_column')
                if symbol_column:
                    where_clause += f" AND {symbol_column} IN (SELECT symbol FROM symbol_metadata WHERE archive_db='airlines')"

            try:
                # Delete old data
                delete_sql = f"DELETE FROM {table_name} WHERE {where_clause}"
                cursor.execute(delete_sql, params)
                deleted_count = cursor.rowcount

                conn.commit()

                print(f"  ✓ {table_name}: Deleted {_rows_label(deleted_count)} (>{retention_days} days old)")
                stats['total_deleted'] += deleted_count

            except Exception as e:
                stats['errors'].append(f"{table_name}: {e}")
                print(f"  ❌ ERROR: {table_name}: {e}")

                # Trigger autofix for deletion failures
                from tools.autofix import handle_error
                handle_error(
                    error_type='archive_deletion_failed',
                    context={'table': table_name, 'retention_days': retention_days, 'error': str(e)},
                    severity='ERROR'  # Batch mode - continues with other tables
                )

    return stats


def optimize_sector_archives(sectors=None):
    """Run sector optimization via direct function call (no subprocess).

    Imports optimize_sector_archive() from db_optimize_sectors.py and calls it
    directly for each sector, printing one compact progress line per sector.

    Args:
        sectors: Set/list of sector names to optimize, or None for all sectors

    Returns:
        bool: True if all sectors optimized successfully, False otherwise
    """
    try:
        from data.health.db_optimize_sectors import optimize_sector_archive
    except ImportError:
        # Fallback for when running from different working directories
        try:
            from db_optimize_sectors import optimize_sector_archive
        except ImportError:
            print("  WARNING: Could not import optimize_sector_archive from db_optimize_sectors")
            return False

    sectors_list = sorted(sectors) if sectors else []
    if not sectors_list:
        return True

    total_time = 0
    success_count = 0

    for sector in sectors_list:
        result = optimize_sector_archive(sector)

        if result.get('success'):
            duration = result.get('analyze_time', 0)
            size_mb = result.get('size_mb', 0)
            total_time += duration
            success_count += 1

            dur_str = _format_duration(duration)

            # Format size
            if size_mb >= 1024:
                size_str = "{:.1f} GB".format(size_mb / 1024)
            else:
                size_str = "{:,.0f} MB".format(size_mb)

            print("  \u2713 {}: {} in {}".format(sector, size_str, dur_str))
        else:
            error_msg = result.get('error', 'unknown error')
            print("  \u2717 {}: FAILED - {}".format(sector, error_msg))

    # Summary line
    total_str = _format_duration(total_time)
    print("  Optimization complete: {}/{} sectors, total: {}".format(
        success_count, len(sectors_list), total_str))

    if success_count < len(sectors_list):
        # Log autofix for partial failures
        try:
            from tools.autofix import handle_error
            handle_error(
                error_type='archive_optimizer_failed',
                context={
                    'success_count': success_count,
                    'total_sectors': len(sectors_list),
                    'failed_sectors': [s for s in sectors_list if s not in sectors_list[:success_count]]
                },
                severity='ERROR'  # Batch mode - non-critical optimization failure
            )
        except Exception:
            pass

    return success_count == len(sectors_list)


def vacuum_production_database():
    """Run VACUUM on production database to reclaim space.

    Returns:
        bool: True if successful, False otherwise
    """
    source_db = SOURCE_DB
    source_path = os.path.join(project_root, 'data', source_db)

    print(f"\n{'=' * 70}")
    print("DATABASE CLEANUP: Running VACUUM on production database")
    print("=" * 70)
    print("⚠️ WARNING: DO NOT INTERRUPT - This may take several minutes")

    try:
        with sqlite3.connect(source_path) as conn:
            cursor = conn.cursor()

            # Point SQLite temp files to E: drive — C: drive temp dir is too small
            # for VACUUM on a 14+ GB database (needs full copy as temp file)
            data_dir = os.path.join(project_root, 'data')
            cursor.execute(f"PRAGMA temp_store_directory = '{data_dir}'")

            # Get size before VACUUM
            cursor.execute("PRAGMA page_count")
            pages_before = cursor.fetchone()[0]
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            size_before_mb = (pages_before * page_size) / (1024 * 1024)

            print(f"  Database size before: {size_before_mb:.1f} MB")
            print("  Running VACUUM...")

            start_time = time.time()
            cursor.execute("VACUUM")
            vacuum_time = time.time() - start_time

            # Get size after VACUUM
            cursor.execute("PRAGMA page_count")
            pages_after = cursor.fetchone()[0]
            size_after_mb = (pages_after * page_size) / (1024 * 1024)
            space_saved_mb = size_before_mb - size_after_mb

            print(f"\n  ✓ VACUUM complete in {_format_duration(vacuum_time)}")
            print(f"  Database size after: {size_after_mb:.1f} MB")
            print(f"  Space reclaimed: {space_saved_mb:.1f} MB ({space_saved_mb / size_before_mb * 100:.1f}%)")

        return True

    except Exception as e:
        print(f"  ❌ ERROR: VACUUM failed: {e}")

        # Trigger autofix for VACUUM failures
        from tools.autofix import handle_error
        handle_error(
            error_type='archive_vacuum_failed',
            context={'error': str(e)},
            severity='ERROR'  # Batch mode - space reclamation failure
        )
        return False


def analyze_archive_impact(tiers_to_run, test_mode=False):
    """Analyze what would be archived without actually doing it.

    Follows exact production workflow using the same source database that
    will be archived, ensuring accurate predictions.

    Args:
        tiers_to_run (list): List of tier numbers to analyze
        test_mode (bool): If True, only analyze Airlines sector

    Returns:
        dict: Analysis results with row counts and size estimates
    """
    # Use same source database as production archive
    source_db = SOURCE_DB
    source_path = os.path.join(project_root, 'data', source_db)

    analysis = {
        'tiers': {},
        'total_rows_to_archive': 0,
        'total_rows_to_delete': 0,
        'sectors_affected': set()
    }

    print(f"\n{'=' * 70}")
    print("DRY-RUN ANALYSIS: Analyzing archive impact")
    print("=" * 70)

    with sqlite3.connect(source_path) as conn:
        cursor = conn.cursor()

        for tier_num in tiers_to_run:
            tier_name = f'tier{tier_num}'
            tier_config = TIER_POLICIES[tier_name]
            retention_days = tier_config['retention_days']
            mode = tier_config['mode']

            print(f"\n{'=' * 70}")
            print(f"TIER {tier_num}: {retention_days}-day retention, {mode.upper()} mode")
            print("=" * 70)

            tier_stats = {
                'tables': {},
                'total_rows': 0,
                'total_rows_to_delete': 0,
                'retention_days': retention_days,
                'mode': mode
            }

            for table_name, table_config in tier_config['tables'].items():
                # Check if table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone():
                    print(f"\n  ⚠️ {table_name}: Table not found in database")
                    continue

                # P028: per-table override (tier-level retention_days still drives banner/stats above)
                table_retention_days = table_config.get('retention_days_override', retention_days)
                date_column = table_config['date_column']
                cutoff_date = (datetime.now().date() - timedelta(days=table_retention_days)).strftime('%Y-%m-%d')

                # Build WHERE clause
                if table_config.get('hybrid_strategy'):
                    # option_contracts: expired OR old
                    expiration_column = table_config['expiration_column']
                    where_clause = f"({expiration_column} < DATE('now') OR {date_column} < ?)"
                    params = [cutoff_date]
                else:
                    where_clause = f"{date_column} < ?"
                    params = [cutoff_date]

                # Add test mode filter (will be applied in GROUP BY query if using sector breakdown)
                test_mode_filter = ""
                if test_mode:
                    symbol_column = table_config.get('symbol_column')
                    if symbol_column:
                        test_mode_filter = f" AND {symbol_column} IN (SELECT symbol FROM symbol_metadata WHERE archive_db='airlines')"

                # Get total count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}{test_mode_filter}", params)
                total_count = cursor.fetchone()[0]

                table_stats = {
                    'total_rows': total_count,
                    'cutoff_date': cutoff_date,
                    'sectors': {}
                }

                if total_count > 0:
                    # Check for table-level mode override
                    table_mode = table_config.get('mode', mode)

                    print(f"\n  {table_name}:")
                    print(f"    Cutoff date: {cutoff_date}")
                    print(f"    Total rows to archive: {total_count:,}")
                    if table_mode != mode:
                        print(f"    Mode: {table_mode.upper()} (table override)")

                    # Get breakdown by sector (if symbol-based routing)
                    routing = table_config.get('routing')

                    if routing == 'symbol':
                        symbol_column = table_config.get('symbol_column')
                        if symbol_column:
                            # Use GROUP BY for faster analysis (single query instead of N queries)
                            # Qualify the where_clause to use table alias 't'
                            qualified_where = where_clause.replace(f"{date_column}", f"t.{date_column}")
                            if 'expiration_date' in where_clause:
                                qualified_where = qualified_where.replace(f"expiration_date", f"t.expiration_date")

                            # Build sector filter for GROUP BY query
                            sector_filter = ""
                            if test_mode:
                                sector_filter = "AND sm.archive_db = 'airlines'"

                            group_query = f"""
                                SELECT sm.archive_db, COUNT(*) as count
                                FROM {table_name} t
                                JOIN symbol_metadata sm ON t.{symbol_column} = sm.symbol
                                WHERE {qualified_where} {sector_filter}
                                GROUP BY sm.archive_db
                                ORDER BY sm.archive_db
                            """
                            cursor.execute(group_query, params)

                            for sector, sector_count in cursor.fetchall():
                                if sector and sector_count > 0:
                                    table_stats['sectors'][sector] = sector_count
                                    analysis['sectors_affected'].add(sector)
                                    print(f"      {sector}: {sector_count:,} rows")

                    elif routing == 'all_sectors':
                        # Market data - copied to all sectors
                        if test_mode:
                            sectors = ['airlines']
                        else:
                            sectors = get_all_archive_dbs(source_db)

                        print(f"      Will copy to {len(sectors)} sector(s)")
                        for sector in sectors:
                            table_stats['sectors'][sector] = total_count
                            analysis['sectors_affected'].add(sector)

                    elif routing == 'symbols_mentioned':
                        # news_articles - need to parse JSON
                        print(f"      Routing by symbols_mentioned (multiple sectors)")

                else:
                    print(f"\n  {table_name}: No data to archive")

                tier_stats['tables'][table_name] = table_stats
                tier_stats['total_rows'] += total_count

                # Track deletions based on table mode
                table_mode = table_config.get('mode', mode)
                if table_mode == 'move':
                    tier_stats['total_rows_to_delete'] += total_count

            analysis['tiers'][tier_name] = tier_stats
            analysis['total_rows_to_delete'] += tier_stats['total_rows_to_delete']
            analysis['total_rows_to_archive'] += tier_stats['total_rows']

            # Show tier summary with copy/move breakdown if mixed
            rows_to_copy = tier_stats['total_rows'] - tier_stats['total_rows_to_delete']
            if rows_to_copy > 0 and tier_stats['total_rows_to_delete'] > 0:
                print(f"\n  Tier {tier_num} Total: {tier_stats['total_rows']:,} rows ({tier_stats['total_rows_to_delete']:,} MOVE, {rows_to_copy:,} COPY)")
            else:
                print(f"\n  Tier {tier_num} Total: {tier_stats['total_rows']:,} rows ({mode.upper()})")

    # Summary
    print(f"\n{'=' * 70}")
    print("OVERALL IMPACT SUMMARY")
    print("=" * 70)
    print(f"Total rows to archive: {analysis['total_rows_to_archive']:,}")
    print(f"Total rows to delete from production: {analysis['total_rows_to_delete']:,}")
    print(f"Sectors affected: {len(analysis['sectors_affected'])}")
    if analysis['sectors_affected']:
        print(f"  {', '.join(sorted(analysis['sectors_affected']))}")

    print("=" * 70)

    return analysis


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Archive data to sector-specific databases (three-tier policy)')
    parser.add_argument('--tier', type=int, choices=[1, 2, 3],
                       help='Archive specific tier only (1, 2, or 3)')
    parser.add_argument('--all-tiers', action='store_true',
                       help='Archive all tiers (production mode)')
    parser.add_argument('--test-mode', action='store_true',
                       help='Test mode: Airlines sector only')
    parser.add_argument('--dry-run', action='store_true',
                       help='Analyze what would be archived without actually doing it')
    parser.add_argument('--time-limit', type=int,
                       help='Maximum time in seconds before graceful shutdown (for Friday runs)')
    args = parser.parse_args()

    # Setup logging (both file and console)
    logger = setup_logging()

    # Setup diagnostic logging
    diag_logger = setup_diagnostic_logging()

    # Setup signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Record start time and set time limit
    global script_start_time, time_limit_seconds
    script_start = time.time()
    script_start_time = script_start
    time_limit_seconds = args.time_limit
    start_timestamp = now_eastern()

    # Determine which tiers to run
    if args.all_tiers:
        tiers_to_run = [1, 2, 3]
        mode_desc = "All Tiers"
    elif args.tier:
        tiers_to_run = [args.tier]
        mode_desc = f"Tier {args.tier}"
    else:
        print("ERROR: Must specify either --tier N or --all-tiers")
        return 1

    print("=" * 70)
    print("SECTOR-BASED DATABASE ARCHIVER")
    print("=" * 70)
    print(f"Start Time: {start_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
    print(f"Source Database: {SOURCE_DB}")
    print(f"Mode: {mode_desc}")
    print(f"Test Mode: {'Yes (Airlines only)' if args.test_mode else 'No (All sectors)'}")
    print(f"Dry Run: {'Yes (analysis only)' if args.dry_run else 'No (will archive)'}")
    if time_limit_seconds:
        print(f"Time Limit: {time_limit_seconds}s ({time_limit_seconds/3600:.1f} hours)")
    print("=" * 70)

    # Log startup info to file (debug: print banner above covers console)
    logger.debug("=" * 70)
    logger.debug("SECTOR-BASED DATABASE ARCHIVER - STARTING")
    logger.debug(f"Source: {SOURCE_DB}, Mode: {mode_desc}, Test: {args.test_mode}, Dry-run: {args.dry_run}")
    if time_limit_seconds:
        logger.debug(f"Time limit: {time_limit_seconds}s ({time_limit_seconds/3600:.1f} hours)")
    logger.debug("=" * 70)

    # Pre-flight: verify database is writable before spending hours
    if not args.dry_run:
        if not preflight_database_check():
            logger.error("Archive aborted: pre-flight database check failed")
            from tools.autofix import handle_error
            handle_error(
                error_type='archive_preflight_database_locked',
                context={'source_db': SOURCE_DB, 'message': 'Database locked at archive start'},
                severity='ERROR'
            )
            return 1

    # Dry-run mode: analyze and exit
    if args.dry_run:
        try:
            analyze_archive_impact(tiers_to_run, test_mode=args.test_mode)

            # Dry-run complete
            script_elapsed = time.time() - script_start
            end_timestamp = now_eastern()
            print(f"\n{'=' * 70}")
            print("DRY-RUN COMPLETE")
            print("=" * 70)
            print(f"Start Time: {start_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print(f"End Time: {end_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print(f"Duration: {_format_duration(script_elapsed)}")
            print("=" * 70)
            return 0
        except Exception as e:
            print(f"\n❌ ANALYSIS ERROR: {e}")
            import traceback
            traceback.print_exc()

            # Trigger autofix for analysis mode failures
            from tools.autofix import handle_error
            handle_error(
                error_type='archive_analysis_failed',
                context={'error': str(e), 'traceback': traceback.format_exc()},
                severity='ERROR'  # Batch mode - dry-run failure
            )
            return 1

    overall_stats = {
        'total_archived': 0,
        'total_deleted': 0,
        'errors': [],
        'tier_stats': {}  # Track per-tier statistics for diagnostic logging
    }

    # Log archive start
    log_diagnostic_summary(
        diag_logger,
        'start',
        time_limit_hours=time_limit_seconds/3600 if time_limit_seconds else 0
    )

    try:
        # Tier 1: High-frequency data (15 days, MOVE)
        if 1 in tiers_to_run:
            if check_shutdown():
                print("\n⏰ Time limit reached before Tier 1 - stopping gracefully")
                return 0

            tier_start = time.time()
            tier_start_timestamp = now_eastern()
            tier1_archived = 0
            tier1_deleted = 0
            tier1_sectors = set()
            tier1_errors = 0

            print(f"\n{'=' * 70}")
            print("TIER 1: HIGH-FREQUENCY DATA (7-day retention, MOVE)")
            print("=" * 70)
            print(f"Tier 1 Start: {tier_start_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print(f"Source: {SOURCE_DB}")
            print("=" * 70)
            logger.debug("=" * 50)
            logger.debug("TIER 1 START: 7-day retention, MOVE mode")

            tier_config = TIER_POLICIES['tier1']
            for table_name, table_config in tier_config['tables'].items():
                stats = archive_table_tier1_tier2(
                    table_name,
                    tier_config,
                    table_config,
                    table_config.get('retention_days_override', tier_config['retention_days']),
                    test_mode=args.test_mode
                )
                overall_stats['total_archived'] += stats['total_archived']
                overall_stats['total_deleted'] += stats['total_deleted']
                overall_stats['errors'].extend(stats['errors'])

                # Track tier-specific stats
                tier1_archived += stats['total_archived']
                tier1_deleted += stats['total_deleted']
                tier1_sectors.update(stats.get('sectors_affected', set()))
                tier1_errors += len(stats['errors'])

                print(f"\n  ✓ {table_name} complete:")
                print(f"    Archived: {_rows_label(stats['total_archived'])}")
                print(f"    Deleted: {_rows_label(stats['total_deleted'])}")
                # Defensive: handle both set and int types for sectors_affected
                sectors = stats['sectors_affected']
                if isinstance(sectors, (set, list, tuple)) and sectors:
                    print(f"    Sectors: {', '.join(sorted(sectors))}")
                elif isinstance(sectors, int):
                    print(f"    Sectors: {sectors} sector(s)")
                else:
                    print(f"    Sectors: none")
                if stats['errors']:
                    print(f"    Errors: {len(stats['errors'])}")

            # Tier 1 complete
            tier_elapsed = time.time() - tier_start
            tier_end_timestamp = now_eastern()
            print(f"\n{'=' * 70}")
            print(f"TIER 1 COMPLETE - Duration: {_format_duration(tier_elapsed)}")
            print(f"End Time: {tier_end_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print("=" * 70)
            logger.info(f"TIER 1 COMPLETE: {tier1_archived:,} archived, {tier1_deleted:,} deleted in {tier_elapsed:.1f}s")

            # Log diagnostic summary for Tier 1
            log_diagnostic_summary(
                diag_logger,
                1,
                rows_archived=tier1_archived,
                rows_deleted=tier1_deleted,
                sectors_affected=len(tier1_sectors),
                duration_seconds=tier_elapsed,
                errors=tier1_errors
            )

        # Tier 2: Daily summaries (30 days, MOVE)
        if 2 in tiers_to_run:
            if check_shutdown():
                print("\n⏰ Time limit reached before Tier 2 - stopping gracefully")
                return 0

            tier_start = time.time()
            tier_start_timestamp = now_eastern()
            tier2_archived = 0
            tier2_deleted = 0
            tier2_sectors = set()
            tier2_errors = 0

            print(f"\n{'=' * 70}")
            print("TIER 2: DAILY SUMMARIES (30-day retention, MOVE)")
            print("=" * 70)
            print(f"Tier 2 Start: {tier_start_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print(f"Source: {SOURCE_DB}")
            print("=" * 70)
            logger.debug("=" * 50)
            logger.debug("TIER 2 START: 30-day retention, MOVE mode")

            tier_config = TIER_POLICIES['tier2']
            for table_name, table_config in tier_config['tables'].items():
                stats = archive_table_tier1_tier2(
                    table_name,
                    tier_config,
                    table_config,
                    table_config.get('retention_days_override', tier_config['retention_days']),
                    test_mode=args.test_mode
                )
                overall_stats['total_archived'] += stats['total_archived']
                overall_stats['total_deleted'] += stats['total_deleted']
                overall_stats['errors'].extend(stats['errors'])

                # Track tier-specific stats
                tier2_archived += stats['total_archived']
                tier2_deleted += stats['total_deleted']
                tier2_sectors.update(stats.get('sectors_affected', set()))
                tier2_errors += len(stats['errors'])

                print(f"\n  ✓ {table_name} complete:")
                print(f"    Archived: {_rows_label(stats['total_archived'])}")
                print(f"    Deleted: {_rows_label(stats['total_deleted'])}")
                # Defensive: handle both set and int types for sectors_affected
                sectors = stats['sectors_affected']
                if isinstance(sectors, (set, list, tuple)) and sectors:
                    print(f"    Sectors: {', '.join(sorted(sectors))}")
                elif isinstance(sectors, int):
                    print(f"    Sectors: {sectors} sector(s)")
                else:
                    print(f"    Sectors: none")
                if stats['errors']:
                    print(f"    Errors: {len(stats['errors'])}")

            # Tier 2 complete
            tier_elapsed = time.time() - tier_start
            tier_end_timestamp = now_eastern()
            print(f"\n{'=' * 70}")
            print(f"TIER 2 COMPLETE - Duration: {_format_duration(tier_elapsed)}")
            print(f"End Time: {tier_end_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print("=" * 70)
            logger.info(f"TIER 2 COMPLETE: {tier2_archived:,} archived, {tier2_deleted:,} deleted in {tier_elapsed:.1f}s")

            # Log diagnostic summary for Tier 2
            log_diagnostic_summary(
                diag_logger,
                2,
                rows_archived=tier2_archived,
                rows_deleted=tier2_deleted,
                sectors_affected=len(tier2_sectors),
                duration_seconds=tier_elapsed,
                errors=tier2_errors
            )

        # Tier 3: Reference data (90 days, COPY)
        if 3 in tiers_to_run:
            if check_shutdown():
                print("\n⏰ Time limit reached before Tier 3 - stopping gracefully")
                return 0

            # Brief delay before Tier 3 to allow WAL checkpoints from Tier 2
            print("\n⏳ Waiting 3 seconds before Tier 3 to allow WAL checkpoints...")
            time.sleep(3)

            tier_start = time.time()
            tier_start_timestamp = now_eastern()
            tier3_archived = 0
            tier3_deleted = 0
            tier3_sectors = set()
            tier3_errors = 0

            print(f"\n{'=' * 70}")
            print("TIER 3: REFERENCE DATA (90-day retention, COPY)")
            print("=" * 70)
            print(f"Tier 3 Start: {tier_start_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print(f"Source: {SOURCE_DB}")
            print("=" * 70)
            logger.debug("=" * 50)
            logger.debug("TIER 3 START: 90-day retention, COPY mode")

            tier_config = TIER_POLICIES['tier3']
            for table_name, table_config in tier_config['tables'].items():
                stats = archive_table_tier3(
                    table_name,
                    tier_config,
                    table_config,
                    table_config.get('retention_days_override', tier_config['retention_days']),
                    test_mode=args.test_mode
                )
                overall_stats['total_archived'] += stats['total_archived']
                overall_stats['errors'].extend(stats['errors'])

                # Track tier-specific stats
                tier3_archived += stats['total_archived']
                tier3_sectors.update(stats.get('sectors_affected', set()))
                tier3_errors += len(stats['errors'])

                print(f"\n  ✓ {table_name} complete:")
                print(f"    Archived: {_rows_label(stats['total_archived'])}")
                # Defensive: handle both set and int types for sectors_affected
                sectors = stats['sectors_affected']
                if isinstance(sectors, (set, list, tuple)) and sectors:
                    print(f"    Sectors: {', '.join(sorted(sectors))}")
                elif isinstance(sectors, int):
                    print(f"    Sectors: {sectors} sector(s)")
                else:
                    print(f"    Sectors: none")
                if stats['errors']:
                    print(f"    Errors: {len(stats['errors'])}")

            # Cleanup pass: Delete old Tier 3 data from production
            if not check_shutdown():
                cleanup_stats = cleanup_tier3_production(tier_config, test_mode=args.test_mode)
                overall_stats['total_deleted'] += cleanup_stats['total_deleted']
                overall_stats['errors'].extend(cleanup_stats['errors'])
                tier3_deleted += cleanup_stats['total_deleted']
                tier3_errors += len(cleanup_stats['errors'])

            # Tier 3 complete
            tier_elapsed = time.time() - tier_start
            tier_end_timestamp = now_eastern()
            print(f"\n{'=' * 70}")
            print(f"TIER 3 COMPLETE - Duration: {_format_duration(tier_elapsed)}")
            print(f"End Time: {tier_end_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
            print("=" * 70)
            logger.info(f"TIER 3 COMPLETE: {tier3_archived:,} archived, {tier3_deleted:,} deleted in {tier_elapsed:.1f}s")

            # Log diagnostic summary for Tier 3
            log_diagnostic_summary(
                diag_logger,
                3,
                rows_archived=tier3_archived,
                rows_deleted=tier3_deleted,
                sectors_affected=len(tier3_sectors),
                duration_seconds=tier_elapsed,
                errors=tier3_errors
            )

        # Optimize sector archives (ANALYZE for query performance)
        # Only optimize sectors that actually received data this run
        if overall_stats['total_archived'] > 0 and not check_shutdown():
            all_affected_sectors = set()
            if 1 in tiers_to_run:
                all_affected_sectors.update(tier1_sectors)
            if 2 in tiers_to_run:
                all_affected_sectors.update(tier2_sectors)
            if 3 in tiers_to_run:
                all_affected_sectors.update(tier3_sectors)

            print(f"\n{'=' * 70}")
            print(f"Post-Archive Cleanup: Optimizing {len(all_affected_sectors)} affected sector database(s)")
            print("=" * 70)
            optimize_sector_archives(all_affected_sectors)

        # Run VACUUM if any data was deleted
        if overall_stats['total_deleted'] > 0 and not check_shutdown():
            vacuum_success = vacuum_production_database()
        else:
            vacuum_success = True

        # Final summary
        script_elapsed = time.time() - script_start
        end_timestamp = now_eastern()
        print(f"\n{'=' * 70}")
        print("ARCHIVE COMPLETE")
        print("=" * 70)
        print(f"Start Time: {start_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
        print(f"End Time: {end_timestamp.strftime('%Y-%m-%d %H:%M:%S EST')}")
        print(f"Total Duration: {_format_duration(script_elapsed)}")
        print(f"Source Database: {SOURCE_DB}")
        print(f"\nTotal archived: {_rows_label(overall_stats['total_archived'])}")
        print(f"Total deleted: {_rows_label(overall_stats['total_deleted'])}")

        if overall_stats['errors']:
            print(f"\n⚠️ ERRORS ENCOUNTERED: {len(overall_stats['errors'])}")
            for error in overall_stats['errors']:
                print(f"  - {error}")

        print("=" * 70)

        # Log completion to file (debug: print banner above covers console)
        logger.debug("=" * 70)
        logger.debug("ARCHIVE COMPLETE")
        logger.debug(f"Duration: {script_elapsed:.1f}s ({script_elapsed/60:.1f} min)")
        logger.debug(f"Archived: {overall_stats['total_archived']:,} rows, Deleted: {overall_stats['total_deleted']:,} rows")
        if overall_stats['errors']:
            logger.warning(f"Errors encountered: {len(overall_stats['errors'])}")
            for error in overall_stats['errors']:
                logger.warning(f"  {error}")
        logger.debug("=" * 70)

        # Log diagnostic completion summary
        has_errors = len(overall_stats['errors']) > 0
        log_diagnostic_summary(
            diag_logger,
            'complete',
            total_archived=overall_stats['total_archived'],
            total_deleted=overall_stats['total_deleted'],
            total_time_seconds=script_elapsed,
            total_errors=len(overall_stats['errors']),
            success=not has_errors
        )

        # CRITICAL: Return non-zero exit code if there were any errors
        # This ensures main.py detects the failure and autofix can review
        if has_errors:
            print(f"\n❌ ARCHIVE COMPLETED WITH ERRORS - Returning exit code 1")
            logger.error(f"Archive completed with {len(overall_stats['errors'])} errors - exit code 1")
            return 1

        return 0

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Stopped by user")
        logger.warning("Archive interrupted by user (KeyboardInterrupt)")
        return 130
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

        # Log fatal error
        logger.critical(f"FATAL ERROR: {e}")
        logger.critical(traceback.format_exc())

        # Trigger autofix for fatal top-level errors
        from tools.autofix import handle_error
        handle_error(
            error_type='archive_fatal_error',
            context={'error': str(e), 'traceback': traceback.format_exc()},
            severity='CRITICAL',  # Fatal error - script dying, exit immediately
            main_py_pid=os.getppid()  # Get parent (main.py) PID
        )
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
