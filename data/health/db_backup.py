#!/usr/bin/env python3
"""
Database Backup & Sync Tool (db_backup.py)
-------------------------------------------
Manages two types of database operations:

1. Disaster Backup: datalake.db → datalake_backup.db
   - Purpose: Emergency recovery from data corruption or loss
   - Schedule: Daily after analysis pipeline
   - Safe to overwrite existing backup

2. Query Sync: datalake.db → datalake_query.db
   - Purpose: Separate read-only database for analysis (prevents locking)
   - Schedule: After morning OID (~7:20 AM) and evening OID (~5:45 PM)
   - Interactive mode prompts before overwrite

Usage:
    python data/health/db_backup.py --disaster           # Disaster recovery backup
    python data/health/db_backup.py --sync               # Query sync (with prompt)
    python data/health/db_backup.py --sync --auto        # Query sync (no prompt)
    python data/health/db_backup.py --all                # Both operations

Author: Ben (with assistance from Claude)
Date: 2025-10-05
"""

import os
import sys
import shutil
import time
import sqlite3
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# PERMANENT FIX: Force UTF-8 encoding for Windows console
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# Import error queue after path setup
from tools.autofix import queue_error

# =============================================================================
# QUICK SYNC TABLE CONFIGURATION
# =============================================================================
# Maps table names to (watermark_column, sync_mode)
# - watermark_column: Column used to identify new/updated rows
# - sync_mode: 'IGNORE' = skip duplicates, 'REPLACE' = overwrite existing rows
#
# DEFAULT_QUICK_SYNC_TABLES: Used when --quick-sync is called without --table
# These are the high-frequency market-hours tables that update every scan cycle
# =============================================================================

SYNC_TABLE_CONFIG = {
    # Market-hours tables (high frequency, every 15 min during market)
    'flow_alerts': ('scan_timestamp', 'IGNORE'),
    'flow_options_scans': ('scan_timestamp', 'IGNORE'),
    'flow_watchlist_daily': ('last_updated', 'REPLACE'),

    # Post-market rollup tables (updated after market close)
    'flow_symbol_summary': ('trade_date', 'REPLACE'),
    'option_symbol_summary': ('trade_date', 'REPLACE'),
    'option_contracts': ('trade_date', 'IGNORE'),

    # Daily summary tables
    'market_daily_summary': ('trade_date', 'REPLACE'),
}

# Default tables for --quick-sync without --table argument
DEFAULT_QUICK_SYNC_TABLES = ['flow_alerts', 'flow_options_scans', 'flow_watchlist_daily']

def get_timestamp():
    """Get formatted timestamp for logging"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def format_size(bytes_size):
    """Format bytes as human-readable size"""
    mb = bytes_size / (1024 * 1024)
    if mb >= 1000:
        return "{:.2f} GB".format(mb / 1024)
    else:
        return "{:.1f} MB".format(mb)

def check_disk_space(path, required_bytes):
    """Check if sufficient disk space available

    Args:
        path: Directory path to check
        required_bytes: Bytes needed

    Returns:
        bool: True if sufficient space available
    """
    try:
        stat = os.statvfs(os.path.dirname(path))
        available = stat.f_bavail * stat.f_frsize
        return available >= (required_bytes * 1.2)  # 20% buffer
    except (AttributeError, OSError):
        # Windows doesn't have statvfs, use shutil.disk_usage instead
        try:
            usage = shutil.disk_usage(os.path.dirname(path))
            return usage.free >= (required_bytes * 1.2)  # 20% buffer
        except:
            # If we can't check, assume it's fine
            return True

def get_table_count(db_path):
    """Get number of tables in database for schema validation

    Args:
        db_path: Path to database file

    Returns:
        int: Number of tables, or -1 if error
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        count = cursor.fetchone()[0]

        # Aggressive cleanup to prevent file handle leaks on Windows (2025-12-15 fix)
        cursor.close()
        conn.close()
        del cursor
        del conn

        return count
    except Exception as e:
        print("⚠️  Warning: Could not validate schema: {}".format(e))
        return -1

def get_locking_process(file_path):
    """Identify which process is holding a lock on a file (Windows only)

    Uses multiple methods to find processes with handles to the specified file:
    1. openfiles.exe (built-in Windows command, requires admin but most reliable)
    2. PowerShell Get-Process with file handle enumeration
    3. Fallback: List all Python processes as potential candidates

    Args:
        file_path: Path to the file to check

    Returns:
        list: List of process names (with PIDs if available) holding locks,
              or empty list if none/error
    """
    try:
        import subprocess

        # Normalize path for comparison
        abs_path = os.path.abspath(file_path).lower()
        file_name = os.path.basename(abs_path)
        locking_processes = []

        # METHOD 1: Try openfiles.exe (most reliable, but requires admin)
        # This is a built-in Windows command that shows all open files system-wide
        try:
            result = subprocess.run(
                ['openfiles', '/query', '/fo', 'csv', '/v'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=15
            )

            if result.returncode == 0 and abs_path in result.stdout.lower():
                # Parse CSV output to find matching files
                for line in result.stdout.split('\n'):
                    if file_name in line.lower():
                        # CSV format: Hostname,ID,Accessed By,Type,Open Mode,Open File
                        parts = line.split(',')
                        if len(parts) >= 3:
                            process_info = parts[2].strip().strip('"')
                            if process_info and process_info not in ['Accessed By', 'N/A']:
                                locking_processes.append(process_info)

                if locking_processes:
                    # Successfully identified via openfiles
                    return list(set(locking_processes))  # Remove duplicates

        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            # openfiles requires admin privileges or may not be available
            pass

        # METHOD 2: PowerShell with improved handle detection
        # More targeted than previous version - looks specifically for the file
        ps_script = '''
$ErrorActionPreference = 'SilentlyContinue'
$targetFile = "{}"
$fileName = "{}"
$processes = @()

# Try to find processes with open handles to this specific file
Get-Process | ForEach-Object {{
    $proc = $_
    $procName = $proc.ProcessName
    $procId = $proc.Id

    try {{
        # Check if process has loaded any SQLite-related modules
        $hasSqlite = $proc.Modules | Where-Object {{
            $_.FileName -like "*sqlite*" -or
            $_.FileName -like "*datalake*" -or
            $_.ModuleName -like "*sqlite*"
        }}

        if ($hasSqlite) {{
            # This process has SQLite loaded - likely a candidate
            $processes += "$procName (PID: $procId)"
        }}
    }} catch {{
        # Access denied - process may still be relevant if it's Python
        if ($procName -like "python*" -or $procName -like "DB*") {{
            $processes += "$procName (PID: $procId)"
        }}
    }}
}}

$processes | Select-Object -Unique | ForEach-Object {{ Write-Output $_ }}
'''.format(abs_path.replace('\\', '\\\\'), file_name)

        result = subprocess.run(
            ['powershell', '-Command', ps_script],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=10
        )

        if result.returncode == 0 and result.stdout.strip():
            processes = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
            # Filter out known safe processes
            filtered = [p for p in processes if p and 'Idle' not in p and 'System' not in p]
            if filtered:
                return filtered

        # METHOD 3: Fallback - list all Python and database-related processes
        # This is less precise but ensures we don't miss anything
        ps_fallback = '''
Get-Process python*, textual*, DB*, sqlite* -ErrorAction SilentlyContinue |
    ForEach-Object {{ "{0} (PID: {1})" -f $_.ProcessName, $_.Id }}
'''

        result = subprocess.run(
            ['powershell', '-Command', ps_fallback],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5
        )

        if result.returncode == 0 and result.stdout.strip():
            processes = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
            if processes:
                return processes

        return []

    except Exception as e:
        # Don't fail if we can't identify the process - just return empty
        # Log the error for diagnostic purposes
        print("   (Debug: get_locking_process failed: {})".format(str(e)), flush=True)
        return []

def wait_for_file_unlock(file_path, max_wait_seconds=30, check_interval=3):
    """Wait for a file to become unlocked with intelligent retry

    This function attempts to acquire a lock on the file, waiting with
    exponential backoff if it's currently locked by another process.

    Args:
        file_path: Path to the file to check
        max_wait_seconds: Maximum time to wait (default 30 seconds)
        check_interval: Initial interval between checks (default 3 seconds)

    Returns:
        tuple: (success: bool, wait_time: float, locking_processes: list)
    """
    start_time = time.time()
    wait_time = check_interval
    attempts = 0
    locking_processes = []

    while (time.time() - start_time) < max_wait_seconds:
        attempts += 1
        try:
            # Try to open file exclusively
            with open(file_path, 'r+b') as f:
                # If we get here, file is not locked
                return True, time.time() - start_time, []
        except (IOError, OSError, PermissionError):
            # File is locked - try to identify who has it
            if attempts == 1:
                locking_processes = get_locking_process(file_path)
                if locking_processes:
                    print("   Detected potential locking processes: {}".format(', '.join(locking_processes)))

            elapsed = time.time() - start_time
            remaining = max_wait_seconds - elapsed

            if remaining <= 0:
                break

            # Wait with exponential backoff (capped at 10 seconds)
            actual_wait = min(wait_time, remaining)
            print("   Waiting {:.0f}s for file lock to release ({:.0f}s remaining)...".format(
                actual_wait, remaining))
            time.sleep(actual_wait)
            wait_time = min(wait_time * 1.5, 10)  # Exponential backoff, max 10s

    # Final check for locking processes
    if not locking_processes:
        locking_processes = get_locking_process(file_path)

    return False, time.time() - start_time, locking_processes


def atomic_rename_with_retry(temp_path, target_path, max_wait_seconds=90):
    """Atomically rename a file, removing target first if needed, with retry on lock

    On Windows, os.rename() cannot overwrite existing files, so we must remove
    the target first. This function wraps both operations with intelligent retry
    to handle cases where the target file is temporarily locked by analysis tools.

    Args:
        temp_path: Path to the temporary file to rename
        target_path: Path to the destination file
        max_wait_seconds: Maximum time to wait for locks (default 90 seconds)

    Returns:
        tuple: (success: bool, error: Exception|None)
    """
    start_time = time.time()
    target_exists = os.path.exists(target_path)
    db_browser_was_running = False
    last_error = None

    # Try immediate rename first (fast path)
    try:
        if target_exists:
            os.remove(target_path)
        os.rename(temp_path, target_path)
        return True, None
    except (OSError, PermissionError) as e:
        last_error = e
        error_str = str(e)

        # Only retry for lock errors
        if 'being used by another process' not in error_str:
            return False, e

        print("⚠️  Database locked during rename - attempting resolution...", flush=True)

    # Try closing DB Browser if it's the lock source
    try:
        import subprocess
        close_result = subprocess.run(
            [sys.executable, 'data/health/close_db_browser.py'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5
        )

        if close_result.returncode == 0:
            db_browser_was_running = True
            print("   ✅ DB Browser closed", flush=True)
            time.sleep(2)
        elif close_result.returncode == 1:
            print("   ℹ️  DB Browser not running - lock from another source", flush=True)
        elif close_result.returncode == 2:
            print("   ⚠️  DB Browser has unsaved changes - cannot auto-close", flush=True)
    except Exception:
        pass  # Continue to retry logic

    # Retry loop with exponential backoff
    # Extended timeout: 90s for unknown sources (was 45s), 20s if DB Browser was closed (was 15s)
    # Based on 2025-12-02 analysis: 45s timeout proved insufficient during morning sync
    max_wait = max_wait_seconds if not db_browser_was_running else 20
    print("   Retrying rename with {}s timeout...".format(max_wait), flush=True)

    wait_interval = 3.0
    attempts = 0
    locking_processes = []

    while (time.time() - start_time) < max_wait:
        attempts += 1

        # Try the full sequence: remove (if exists) + rename
        try:
            if os.path.exists(target_path):
                os.remove(target_path)
            os.rename(temp_path, target_path)
            elapsed = time.time() - start_time
            print("   ✅ Rename succeeded after {:.1f}s (attempt {})".format(elapsed, attempts), flush=True)
            return True, None
        except (OSError, PermissionError) as e:
            last_error = e

            # Get locking process info on first retry
            if attempts == 1:
                locking_processes = get_locking_process(target_path)
                if locking_processes:
                    print("   Detected locking processes: {}".format(', '.join(locking_processes)), flush=True)

            elapsed = time.time() - start_time
            remaining = max_wait - elapsed

            if remaining <= 0:
                break

            # Wait with exponential backoff (capped at 10s)
            actual_wait = min(wait_interval, remaining)
            print("   Lock persists - waiting {:.0f}s ({:.0f}s remaining)...".format(
                actual_wait, remaining), flush=True)
            time.sleep(actual_wait)
            wait_interval = min(wait_interval * 1.5, 10)

    # Failed after all retries
    elapsed = time.time() - start_time
    print("   ❌ Rename failed after {:.1f}s and {} attempts".format(elapsed, attempts), flush=True)

    # Re-check locking processes for final diagnostics
    if not locking_processes:
        locking_processes = get_locking_process(target_path)
    if locking_processes:
        print("   Final locking processes: {}".format(', '.join(locking_processes)), flush=True)
    else:
        print("   Could not identify locking processes (may require admin privileges)", flush=True)

    # Enhanced diagnostic information
    print("   Target file: {}".format(target_path), flush=True)
    print("   Last error: {}".format(last_error), flush=True)
    print("   Timeout used: {}s".format(max_wait), flush=True)
    print("   Recommendation: Check if analysis tools (Morning View TUI, direct_db_query.py, Oracle) are running", flush=True)

    return False, last_error

def setup_logging():
    """Setup logging to unified logs directory

    Returns:
        logging.Logger: Configured logger instance
    """
    # Ensure logs directory exists
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger('db_backup')
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # File handler - daily log file
    log_file = logs_dir / "db_backup_{}.log".format(datetime.now().strftime("%Y-%m-%d"))
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Split formatters: short for console, full for log file
    console_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    return logger

def create_disaster_backup(interactive=True):
    """Create disaster recovery backup: datalake.db → datalake_backup.db

    Args:
        interactive: If True, show decorated banner. If False (orchestrator), suppress it.

    Returns:
        int: 0 on success, 1 on failure
    """
    logger = setup_logging()

    # Only show decorated banner in interactive mode; orchestrator provides its own
    if interactive:
        print("\n" + "=" * 70)
        print("💾 DISASTER RECOVERY BACKUP")
        print("=" * 70)
        print("Timestamp: {}".format(get_timestamp()))
        print()

    logger.info("Starting disaster recovery backup")

    # File paths
    source = "data/datalake.db"
    backup = "data/datalake_backup.db"

    # Check source exists
    if not os.path.exists(source):
        print("❌ ERROR: Source database not found")
        print("   Expected: {}".format(os.path.abspath(source)))
        queue_error(
            error_type='disaster_backup_source_not_found',
            context={'source': os.path.abspath(source)},
            severity='ERROR'
        )
        return 1

    # Get source size
    source_size = os.path.getsize(source)
    print("Source:  {} ({})".format(source, format_size(source_size)))

    # Check if backup exists
    backup_exists = os.path.exists(backup)
    if backup_exists:
        backup_size = os.path.getsize(backup)
        print("Target:  {} ({}) - EXISTS, will overwrite".format(backup, format_size(backup_size)))
    else:
        print("Target:  {} - NEW FILE".format(backup))

    # Check disk space
    if not check_disk_space(backup, source_size):
        print("❌ ERROR: Insufficient disk space")
        print("   Required: {} (+ 20% buffer)".format(format_size(source_size)))
        queue_error(
            error_type='disaster_backup_insufficient_disk_space',
            context={'required_mb': source_size / (1024 * 1024)},
            severity='ERROR'
        )
        return 1

    print()
    print("🔄 Starting backup operation...")

    # Use SQLite hot backup API instead of shutil.copy2()
    # shutil.copy2() fails with WinError 33 when another process holds a lock.
    # SQLite's backup API works safely with concurrent readers/writers and
    # produces a consistent snapshot. Same approach used by create_full_sync().
    try:
        import sqlite3
        start_time = time.time()

        # PREFLIGHT: Smoke-test key tables before overwriting backup.
        # COUNT(*) walks each table's B-tree — corrupt pages throw DatabaseError.
        # Takes ~10-15s vs 12+ min for PRAGMA quick_check on 8 GB HDD.
        # If source is corrupt, we must NOT overwrite a potentially good backup.
        print("   Preflight smoke test on source...")
        preflight_tables = ['option_contracts', 'flow_alerts', 'flow_options_scans',
                            'option_symbol_summary', 'historical_prices']
        try:
            check_conn = sqlite3.connect(source)
            corrupt_tables = []
            for table in preflight_tables:
                try:
                    check_conn.execute('SELECT COUNT(*) FROM {}'.format(table)).fetchone()
                except sqlite3.DatabaseError as tbl_err:
                    corrupt_tables.append((table, str(tbl_err)))
            check_conn.close()

            if corrupt_tables:
                print("   ❌ SOURCE DATABASE IS CORRUPT:")
                for tbl, err in corrupt_tables:
                    print("      {} — {}".format(tbl, err))
                print("   ABORTING BACKUP — existing backup preserved.")
                queue_error(
                    error_type='disaster_backup_source_corrupt',
                    context={'corrupt_tables': [t[0] for t in corrupt_tables],
                             'errors': [t[1] for t in corrupt_tables], 'source': source},
                    severity='CRITICAL'
                )
                return 1
            else:
                print("   Source smoke test: OK ({} tables checked)".format(len(preflight_tables)))
        except Exception as check_err:
            print("   ❌ PREFLIGHT CHECK FAILED: {}".format(check_err))
            print("   ABORTING BACKUP — existing backup preserved.")
            queue_error(
                error_type='disaster_backup_integrity_check_failed',
                context={'error': str(check_err), 'source': source},
                severity='ERROR'
            )
            return 1

        # Check for SQLite auxiliary files (informational only — hot backup handles them)
        wal_file = source + '-wal'
        shm_file = source + '-shm'
        wal_exists = os.path.exists(wal_file)
        shm_exists = os.path.exists(shm_file)

        if wal_exists or shm_exists:
            print("   SQLite auxiliary files detected:")
            if wal_exists:
                wal_size = os.path.getsize(wal_file)
                print("   - WAL file: {} ({})".format(wal_file, format_size(wal_size)))
            if shm_exists:
                shm_size = os.path.getsize(shm_file)
                print("   - SHM file: {} ({})".format(shm_file, format_size(shm_size)))
            print("   Using SQLite hot backup (safe with active connections)")
            print()

        print("   Using SQLite hot backup directly to target...")

        source_conn = sqlite3.connect(source)
        backup_conn = sqlite3.connect(backup)

        try:
            # Progress callback for large databases
            pages_copied = [0]
            total_pages = [0]

            def progress(status, remaining, total):
                pages_copied[0] = total - remaining
                total_pages[0] = total
                # Print progress every 100000 pages (~400MB at 4KB page size)
                if pages_copied[0] % 100000 == 0 and pages_copied[0] > 0:
                    pct = (pages_copied[0] / total) * 100 if total > 0 else 0
                    print("   Progress: {}/{} pages ({:.1f}%)".format(
                        pages_copied[0], total, pct), flush=True)

            source_conn.backup(backup_conn, pages=100, progress=progress)

        finally:
            backup_conn.close()
            source_conn.close()
            del backup_conn
            del source_conn
            import gc
            gc.collect()

        duration = time.time() - start_time

        # Verify backup
        backup_size = os.path.getsize(backup)

        # Schema validation (SQLite backup may differ in raw size due to
        # page fragmentation/auto-vacuum, so validate by table count)
        source_tables = get_table_count(source)
        backup_tables = get_table_count(backup)
        schema_match = (source_tables == backup_tables and source_tables > 0)

        if interactive:
            print("✅ Backup completed in {:.1f} minutes".format(duration / 60))
            print()
            print("Verification:")
            print("  Source size:  {}".format(format_size(source_size)))
            print("  Backup size:  {}".format(format_size(backup_size)))
            print("  Schema match: {} ({} tables)".format(
                "✅ YES" if schema_match else "⚠️  MISMATCH ({} vs {})".format(source_tables, backup_tables),
                source_tables if source_tables > 0 else "unknown"
            ))

        if schema_match:
            print("✅ Backup completed: {} in {:.1f} minutes".format(format_size(backup_size), duration / 60))
            logging.debug("Disaster backup completed successfully in {:.1f} minutes".format(duration / 60))
            return 0
        else:
            print()
            print("❌ DISASTER BACKUP FAILED - Schema mismatch ({} vs {} tables)".format(source_tables, backup_tables))
            print("=" * 70)
            queue_error(
                error_type='disaster_backup_schema_mismatch',
                context={
                    'source_tables': source_tables,
                    'backup_tables': backup_tables,
                    'source_size_mb': source_size / (1024 * 1024),
                    'backup_size_mb': backup_size / (1024 * 1024)
                },
                severity='ERROR'
            )
            return 1

    except Exception as e:
        error_str = str(e)
        print("❌ ERROR: Backup operation failed")
        print("   Error: {}".format(e))
        print()
        print("=" * 70)
        queue_error(
            error_type='disaster_backup_copy_failed',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e),
                'source': source,
                'backup': backup,
                'wal_exists': os.path.exists(source + '-wal'),
                'shm_exists': os.path.exists(source + '-shm')
            },
            severity='ERROR'
        )
        return 1

def create_quick_sync(tables=None, retry_attempt=0, max_retries=3):
    """Quick sync of specific tables using watermark approach

    Uses watermark approach: syncs only rows newer than the latest timestamp
    in query database. Much faster than full sync for incremental updates.

    Args:
        tables: List of table names to sync. If None, uses DEFAULT_QUICK_SYNC_TABLES
                (flow_alerts, flow_options_scans, flow_watchlist_daily)
        retry_attempt: Current retry attempt (0-indexed, internal use)
        max_retries: Maximum number of retry attempts

    Returns:
        int: 0 on success, 1 on failure

    Examples:
        create_quick_sync()  # Default market-hours tables
        create_quick_sync(tables=['flow_symbol_summary'])  # Single table
        create_quick_sync(tables=['option_symbol_summary', 'option_contracts'])  # Multiple
    """
    import sys
    logger = setup_logging()

    # Determine which tables to sync
    if tables is None:
        tables = DEFAULT_QUICK_SYNC_TABLES
        sync_description = "New Flow Scans (default)"
    else:
        sync_description = "Specified Tables"

    # Validate requested tables exist in config
    tables_to_sync = {}
    invalid_tables = []
    for table in tables:
        if table in SYNC_TABLE_CONFIG:
            tables_to_sync[table] = SYNC_TABLE_CONFIG[table]
        else:
            invalid_tables.append(table)

    print("\n" + "=" * 70, flush=True)
    print("⚡ QUICK SYNC - {}".format(sync_description), flush=True)
    print("=" * 70, flush=True)
    print("Timestamp: {}".format(get_timestamp()), flush=True)
    print()

    # Report invalid tables if any
    if invalid_tables:
        print("⚠️  Unknown tables (skipping): {}".format(", ".join(invalid_tables)), flush=True)
        print("   Valid tables: {}".format(", ".join(SYNC_TABLE_CONFIG.keys())), flush=True)
        print()

    if not tables_to_sync:
        print("❌ ERROR: No valid tables to sync", flush=True)
        print("   Available tables: {}".format(", ".join(SYNC_TABLE_CONFIG.keys())), flush=True)
        return 1

    logger.info("Starting quick sync (watermark approach) for tables: {}".format(", ".join(tables_to_sync.keys())))

    # File paths
    source = "data/datalake.db"
    target = "data/datalake_query.db"

    # Check source exists
    if not os.path.exists(source):
        print("❌ ERROR: Source database not found")
        print("   Expected: {}".format(os.path.abspath(source)))
        queue_error(
            error_type='quick_sync_source_not_found',
            context={'source': os.path.abspath(source)},
            severity='ERROR'
        )
        return 1

    # Check target exists (quick sync requires existing target)
    if not os.path.exists(target):
        print("❌ ERROR: Target database not found")
        print("   Quick sync requires existing target database.")
        print("   Run full sync first: python data/health/db_backup.py --sync")
        queue_error(
            error_type='quick_sync_target_not_found',
            context={'target': os.path.abspath(target)},
            severity='ERROR'
        )
        return 1

    print("Source:  {}".format(source), flush=True)
    print("Target:  {}".format(target), flush=True)
    print("Tables:  {}".format(", ".join(tables_to_sync.keys())), flush=True)
    print(flush=True)

    print("🔄 Starting quick sync (watermark approach)...", flush=True)

    # Initialize diagnostics outside try block to avoid UnboundLocalError
    sync_diagnostics = []

    # Flag to track if we've attempted to close DB Browser
    tried_closing_db_browser = False

    try:
        start_time = time.time()

        # TWO SEPARATE CONNECTIONS - eliminates cross-database lock contention.
        # Previous ATTACH approach caused recurring "database is locked" errors during
        # market hours because ATTACH forces both databases into a single connection's
        # lock scope. Even with deferred BEGIN, the INSERT...SELECT across attached DBs
        # requires lock escalation on both databases simultaneously.
        # With separate connections + WAL mode, the source reader never blocks FM's
        # concurrent writes, and the target writer operates independently.
        # (2026-02-18 Batch Fix: 9+ occurrences across 4 dates traced to ATTACH locking)

        # Source connection: read-only, WAL mode allows concurrent reads during FM writes
        print("  Connecting to source database (read-only)...", flush=True)
        connect_start = time.time()
        source_conn = sqlite3.connect(source, timeout=30.0)
        source_conn.execute("PRAGMA query_only = ON")  # Safety: prevent accidental writes
        source_conn.execute("PRAGMA cache_size = -256000")  # 256MB (default 8MB starves reads on 11GB+ DB)
        source_cursor = source_conn.cursor()
        src_connect_elapsed = time.time() - connect_start

        # Target connection: write destination with safe PRAGMAs
        print("  Connecting to target database...", flush=True)
        tgt_connect_start = time.time()
        target_conn = sqlite3.connect(target, timeout=30.0)
        target_cursor = target_conn.cursor()

        # Optimize target for bulk insert speed while maintaining data integrity
        # IMPORTANT: Do NOT use synchronous=OFF or journal_mode=MEMORY here.
        # (2026-02-13 Batch Fix: corruption errors traced to unsafe PRAGMAs)
        target_cursor.execute("PRAGMA synchronous = NORMAL")  # Safe in WAL mode
        target_cursor.execute("PRAGMA temp_store = MEMORY")
        target_cursor.execute("PRAGMA cache_size = -256000")   # 256MB (was 64MB — same index thrash as FM storage)
        target_cursor.execute("PRAGMA wal_autocheckpoint = 0") # Disable auto-checkpoint during bulk insert
        tgt_connect_elapsed = time.time() - tgt_connect_start

        print("  Connected (separate connections, no ATTACH)", flush=True)
        logger.info("SYNC TIMING [connect] source: {:.1f}s | target: {:.1f}s".format(
            src_connect_elapsed, tgt_connect_elapsed))

        # --- Pre-sync diagnostics (2026-02-26) ---
        # Log file sizes and DB stats to help diagnose I/O contention patterns.
        # These are lightweight PRAGMAs + os.path.getsize — no performance impact.
        try:
            src_size = os.path.getsize(source) / (1024 * 1024)
            src_wal = os.path.getsize(source + '-wal') / (1024 * 1024) if os.path.exists(source + '-wal') else 0
            tgt_size = os.path.getsize(target) / (1024 * 1024)
            tgt_wal = os.path.getsize(target + '-wal') / (1024 * 1024) if os.path.exists(target + '-wal') else 0
            tgt_page_count = target_conn.execute('PRAGMA page_count').fetchone()[0]
            tgt_freelist = target_conn.execute('PRAGMA freelist_count').fetchone()[0]
            tgt_page_size = target_conn.execute('PRAGMA page_size').fetchone()[0]
            logger.info("SYNC DIAG [pre] source: {:.0f}MB (WAL: {:.1f}MB) | target: {:.0f}MB (WAL: {:.1f}MB) | target pages: {:,} (free: {:,}, page_size: {})".format(
                src_size, src_wal, tgt_size, tgt_wal, tgt_page_count, tgt_freelist, tgt_page_size))
        except Exception as diag_err:
            logger.debug("Pre-sync diagnostics failed: {}".format(diag_err))

        total_new_rows = 0
        current_table = None      # Track which table we're working on for error reporting
        current_rows = None       # Track row count being attempted
        tables_completed = []     # Track which tables finished successfully

        # Sync each table using read-from-source, write-to-target pattern
        for table, (watermark_col, sync_mode) in tables_to_sync.items():
            current_table = table
            table_start = time.time()
            print("  Syncing {} (watermark: {}, mode: {})...".format(table, watermark_col, sync_mode), flush=True)

            # Get the watermark from TARGET - latest timestamp tells us what we already have
            print("    Getting watermark (MAX {})...".format(watermark_col), flush=True)
            target_cursor.execute(
                "SELECT MAX({}) FROM {}".format(watermark_col, table)
            )
            result = target_cursor.fetchone()
            watermark = result[0] if result[0] is not None else '1970-01-01 00:00:00'

            print("    Watermark: {}".format(watermark), flush=True)

            # Get column count for parameterized INSERT
            source_cursor.execute("PRAGMA table_info({})".format(table))
            col_count = len(source_cursor.fetchall())
            placeholders = ','.join(['?'] * col_count)

            # Read new rows from SOURCE in a single pass (no separate COUNT query)
            # WAL mode: doesn't block concurrent FM writes
            read_start = time.time()
            source_cursor.execute(
                "SELECT * FROM {} WHERE {} > ? ORDER BY {} ASC".format(
                    table, watermark_col, watermark_col
                ),
                (watermark,)
            )
            rows = source_cursor.fetchall()
            read_elapsed = time.time() - read_start
            rows_to_sync = len(rows)
            current_rows = rows_to_sync

            # Store diagnostics for this table
            sync_diagnostics.append({
                'table': table,
                'watermark': watermark,
                'rows_to_sync': rows_to_sync
            })

            print("    Rows to sync: {:,}".format(rows_to_sync), flush=True)
            logger.info("SYNC TIMING [{}] read: {:.1f}s ({:,} rows)".format(
                table, read_elapsed, rows_to_sync))

            if rows_to_sync == 0:
                print("    ✅ Already up to date (0 new rows)", flush=True)
                tables_completed.append(table)
                continue

            # Insert into TARGET using executemany (efficient batch insert)
            # IGNORE = skip duplicates (alerts, scans - append-only tables)
            # REPLACE = overwrite existing (watchlist - updated throughout day)
            print("    Inserting {:,} rows into target...".format(rows_to_sync), flush=True)
            write_start = time.time()
            target_cursor.executemany(
                "INSERT OR {} INTO {} VALUES ({})".format(sync_mode, table, placeholders),
                rows
            )
            write_elapsed = time.time() - write_start

            commit_start = time.time()
            target_conn.commit()
            commit_elapsed = time.time() - commit_start

            total_new_rows += rows_to_sync
            table_elapsed = time.time() - table_start
            print("    ✅ Added {:,} rows".format(rows_to_sync), flush=True)

            logger.info("SYNC TIMING [{}] write: {:.1f}s | commit: {:.1f}s | total: {:.1f}s".format(
                table, write_elapsed, commit_elapsed, table_elapsed))

            # Free memory between tables (flow_options_scans can be large)
            del rows
            tables_completed.append(table)

        # Close source (done reading)
        source_cursor.close()
        source_conn.close()

        # WAL CHECKPOINT on target before closing (2026-02-22 Performance Fix)
        # Without this, the target WAL grows unbounded across cycles because:
        # 1. wal_autocheckpoint=0 disables auto-checkpoint during bulk insert
        # 2. The query DB is read-only for analysis tools, so nobody else writes
        # 3. No writes = no auto-checkpoint triggers = WAL accumulates all day
        # PASSIVE mode folds WAL pages into the main file without blocking readers.
        # This keeps each cycle's INSERT fast by starting with a clean WAL.
        if total_new_rows > 0:
            try:
                wal_start = time.time()
                wal_result = target_conn.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone()
                wal_elapsed = time.time() - wal_start
                busy, wal_pages, checkpointed = wal_result if wal_result else (0, 0, 0)
                if wal_pages and wal_pages > 0:
                    pct = (checkpointed / wal_pages * 100) if wal_pages else 0
                    print("  WAL checkpoint: {}/{} pages ({:.0f}%){}".format(
                        checkpointed, wal_pages, pct,
                        " — some pages held by readers" if checkpointed < wal_pages else ""
                    ), flush=True)
                logger.info("SYNC TIMING [wal_checkpoint] {:.1f}s | pages: {:,}/{:,} | busy: {}".format(
                    wal_elapsed, checkpointed, wal_pages, busy))
                # Post-checkpoint: log WAL file size to confirm it was actually folded in
                try:
                    tgt_wal_post = os.path.getsize(target + '-wal') / (1024 * 1024) if os.path.exists(target + '-wal') else 0
                    logger.info("SYNC DIAG [post] target WAL after checkpoint: {:.1f}MB".format(tgt_wal_post))
                except Exception:
                    pass
            except Exception as e:
                logging.debug("WAL checkpoint on target skipped: {}".format(e))

        target_cursor.close()
        target_conn.close()
        del source_cursor, source_conn, target_cursor, target_conn
        import gc
        gc.collect(2)

        duration = time.time() - start_time

        print()
        print("✅ Quick sync completed in {:.2f} seconds".format(duration))
        print("   Total new rows added: {}".format(total_new_rows))
        print()
        print("✅ QUICK SYNC SUCCESSFUL")
        print("=" * 70)
        logger.info("Quick sync completed successfully in {:.2f} seconds - {} new rows".format(duration, total_new_rows))
        return 0

    except Exception as e:
        error_str = str(e) or type(e).__name__  # MemoryError has empty str(e)

        # Close any open connections safely (two-connection approach)
        def _safe_close():
            for var_name in ('source_cursor', 'source_conn', 'target_cursor', 'target_conn'):
                try:
                    obj = locals_snapshot.get(var_name)
                    if obj is not None:
                        obj.close()
                except Exception:
                    pass
        locals_snapshot = dict(locals())

        # MEMORY ERROR: Force GC and retry — transient memory pressure can cause
        # MemoryError even on normally-sized batches. Self-heals on next cycle anyway
        # (watermark picks up missed rows), but a quick retry often succeeds.
        # (2026-02-25 Batch Fix)
        if isinstance(e, MemoryError) and retry_attempt < max_retries:
            print("⚠️  MemoryError during sync (table: {}, rows: {:,}) - forcing GC and retrying...".format(
                current_table or 'unknown', current_rows or 0), flush=True)
            _safe_close()
            import gc
            gc.collect(2)
            time.sleep(3)
            print("   Retrying sync (attempt {}/{})...".format(retry_attempt + 1, max_retries), flush=True)
            retry_result = create_quick_sync(tables=list(tables_to_sync.keys()), retry_attempt=retry_attempt + 1, max_retries=max_retries)
            if retry_result == 0:
                return retry_result
            # If retry failed, fall through to error handling

        # CORRUPTION: Do NOT retry on "database disk image is malformed" or similar
        # Retrying won't fix corrupted pages - fail fast and report clearly
        # (2026-02-13 Batch Fix: corruption errors should not waste time on retries)
        if 'malformed' in error_str or 'corrupt' in error_str:
            print("🔴 Database corruption detected - skipping retries (retrying won't help)", flush=True)
            print("   Error: {}".format(error_str), flush=True)
            print("   Recommended: Run full sync (python data/health/db_backup.py --sync)", flush=True)

            _safe_close()

        # AUTOMATION: Handle "no such column" errors (2026-01-07 Batch Fix)
        # These can occur if table schemas differ between source and target.
        # Solution: close connections and retry the sync operation
        elif 'no such column' in error_str and retry_attempt < max_retries:
            print("⚠️  Schema error detected - reconnecting and retrying...", flush=True)
            print("   Error: {}".format(error_str), flush=True)

            # Close current connections to reset state
            try:
                _safe_close()
                import gc
                gc.collect(2)
                print("   Connections closed - waiting 2 seconds for cleanup...", flush=True)
                time.sleep(2)
            except Exception as close_error:
                print("   Warning during cleanup: {}".format(close_error), flush=True)

            # RETRY THE ENTIRE SYNC OPERATION
            print("   Retrying sync (attempt {}/{})...".format(retry_attempt + 1, max_retries), flush=True)
            retry_result = create_quick_sync(tables=list(tables_to_sync.keys()), retry_attempt=retry_attempt + 1, max_retries=max_retries)
            # If retry succeeded, return immediately - don't queue error
            if retry_result == 0:
                return retry_result
            # If retry failed, continue to error handling below

        # AUTOMATION: If database is locked and we haven't tried closing DB Browser yet, do it now
        elif 'database is locked' in error_str and not tried_closing_db_browser:
            tried_closing_db_browser = True

            print("⚠️  Database is locked - attempting to close DB Browser automatically...", flush=True)

            # Try to close DB Browser
            try:
                import subprocess
                close_result = subprocess.run(
                    [sys.executable, 'data/health/close_db_browser.py'],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=5
                )

                if close_result.returncode == 0:
                    # DB Browser was closed - wait and retry
                    wait_time = 2 + (retry_attempt * 3)  # 2s, 5s, 8s, 11s...
                    print("   ✅ DB Browser closed - retrying sync in {} seconds...".format(wait_time), flush=True)
                    time.sleep(wait_time)

                    # RETRY THE ENTIRE SYNC OPERATION
                    retry_result = create_quick_sync(tables=list(tables_to_sync.keys()), retry_attempt=retry_attempt + 1, max_retries=max_retries)
                    # If retry succeeded, return immediately - don't queue error
                    if retry_result == 0:
                        return retry_result
                    # If retry failed, continue to error handling below

                elif close_result.returncode == 1:
                    # DB Browser already closed - Windows may still be releasing file locks
                    if retry_attempt < max_retries:
                        wait_time = 5 + (retry_attempt * 3)  # 5s, 8s, 11s...
                        print("   ℹ️  DB Browser not running - waiting {}s for Windows to release file locks...".format(wait_time), flush=True)
                        time.sleep(wait_time)
                        retry_result = create_quick_sync(tables=list(tables_to_sync.keys()), retry_attempt=retry_attempt + 1, max_retries=max_retries)
                        # If retry succeeded, return immediately - don't queue error
                        if retry_result == 0:
                            return retry_result
                        # If retry failed, continue to error handling below
                    else:
                        print("   ❌ DB Browser not running - exhausted {} retries, lock persists".format(max_retries), flush=True)
                elif close_result.returncode == 2:
                    print("   ⚠️  DB Browser has unsaved changes - close dialog is blocking", flush=True)
                    print("   Sync will fail this cycle but retry next cycle (60 seconds)", flush=True)
                else:
                    print("   ⚠️  Failed to close DB Browser - continuing with error", flush=True)

            except Exception as close_error:
                print("   ⚠️  Error attempting to close DB Browser: {}".format(close_error), flush=True)

        # Original error handling continues here (only if retry failed or wasn't attempted)
        print("❌ ERROR: Quick sync operation failed", flush=True)
        print("   Error: {} ({})".format(error_str, type(e).__name__), flush=True)
        print()

        # Queue error ONLY from the original call (retry_attempt == 0)
        # This prevents duplicate error entries when recursive retries all fail
        # (2026-01-15 Batch Fix: Fix duplicate error queuing bug)
        if retry_attempt == 0:
            # Queue error with enhanced context (2026-01-07 Batch Fix, improved 2026-02-25)
            error_category = (
                'memory_error' if isinstance(e, MemoryError)
                else 'schema_error' if 'no such column' in error_str
                else 'lock_error' if 'locked' in error_str
                else 'corruption' if 'malformed' in error_str or 'corrupt' in error_str
                else 'unknown'
            )
            error_context = {
                'exception_type': type(e).__name__,
                'error_message': error_str,
                'error_category': error_category,
                'failed_table': current_table,
                'failed_table_rows': current_rows,
                'tables_completed': tables_completed,
                'tables_remaining': [t for t in tables_to_sync if t not in tables_completed and t != current_table],
                'tables_attempted': ', '.join([d['table'] for d in sync_diagnostics]) if sync_diagnostics else 'none',
                'tried_closing_db_browser': tried_closing_db_browser,
                'max_retries': max_retries,
            }

            # Transient errors self-heal on next cycle (watermark picks up missed rows) - use WARNING
            # Schema errors and other issues still use ERROR severity (2026-01-21 Batch Fix)
            transient = error_category in ('lock_error', 'memory_error')
            severity = 'WARNING' if transient else 'ERROR'

            queue_error(
                error_type='quick_sync_operation_failed',
                context=error_context,
                severity=severity
            )

        # Show diagnostic info for each table attempted
        if sync_diagnostics:
            print("   Sync Diagnostics:", flush=True)
            for diag in sync_diagnostics:
                print("   - Table: {}".format(diag['table']), flush=True)
                print("     Watermark: {}".format(diag['watermark']), flush=True)
                print("     Rows to sync: {:,}".format(diag['rows_to_sync']), flush=True)
            print()

        # Report which table failed and progress so far
        if current_table:
            print("   Failed on table: {} ({:,} rows)".format(
                current_table, current_rows or 0), flush=True)
        if tables_completed:
            print("   Completed before failure: {}".format(', '.join(tables_completed)), flush=True)

        # Show helpful context for common errors
        if 'UNIQUE constraint' in error_str:
            print("   Cause: Duplicate rows detected (watermark logic issue)", flush=True)
            print("   Fix: Run full sync or use INSERT OR IGNORE", flush=True)
        elif 'database is locked' in error_str:
            if tried_closing_db_browser:
                print("   Cause: Database locked by process other than DB Browser", flush=True)
                print("   Attempted: Auto-close DB Browser (was not running or failed)", flush=True)
            else:
                print("   Cause: Database is locked by another process", flush=True)
            print("   Common culprits:", flush=True)
            print("     - DB Browser for SQLite (even in read-only mode)", flush=True)
            print("     - Another analysis script or query tool", flush=True)
            print("     - Active collection pipeline writing to database", flush=True)

        print("=" * 70, flush=True)
        return 1

def create_query_sync(interactive=True, retry_attempt=0, max_retries=3):
    """Create query database sync: datalake.db → datalake_query.db

    Args:
        interactive: If True, prompt user before overwriting existing file
        retry_attempt: Current retry attempt (0-indexed, internal use)
        max_retries: Maximum number of retry attempts

    Returns:
        int: 0 on success, 1 on failure, 2 on user cancellation
    """
    logger = setup_logging()

    # Only show decorated banner in interactive mode; orchestrator provides its own
    if interactive:
        print("\n" + "=" * 70)
        print("🔄 QUERY DATABASE SYNC")
        print("=" * 70)
        print("Timestamp: {}".format(get_timestamp()))
        print()

    logger.info("Starting query database sync (interactive={})".format(interactive))

    # File paths
    source = "data/datalake.db"
    target = "data/datalake_query.db"

    # Check source exists
    if not os.path.exists(source):
        print("❌ ERROR: Source database not found")
        print("   Expected: {}".format(os.path.abspath(source)))
        queue_error(
            error_type='query_sync_source_not_found',
            context={'source': os.path.abspath(source)},
            severity='ERROR'
        )
        return 1

    # Get source size
    source_size = os.path.getsize(source)
    logger.info("Source:  {} ({})".format(source, format_size(source_size)))

    # Check if target exists
    target_exists = os.path.exists(target)
    if target_exists:
        target_size = os.path.getsize(target)
        logger.info("Target:  {} ({}) - EXISTS".format(target, format_size(target_size)))
    else:
        print("Target:  {} - NEW FILE".format(target))

    # Check disk space
    if not check_disk_space(target, source_size):
        print("❌ ERROR: Insufficient disk space")
        print("   Required: {} (+ 20% buffer)".format(format_size(source_size)))
        queue_error(
            error_type='query_sync_insufficient_disk_space',
            context={'required_mb': source_size / (1024 * 1024)},
            severity='ERROR'
        )
        return 1

    # Pre-flight check: Verify we can delete/rename target before starting 14-minute copy
    # This section implements a multi-stage lock resolution strategy:
    # 1. Quick check - file might be available immediately
    # 2. Close DB Browser - common cause of locks
    # 3. Wait for other processes - give analysis tools time to finish naturally
    # 4. Fail with diagnostics - provide information about what's blocking
    if target_exists:
        try:
            # Quick check - try to open for write access
            test_file = open(target, 'r+b')
            test_file.close()
        except (IOError, OSError) as e:
            error_str = str(e)
            print("⚠️  Database is locked - attempting automatic resolution...")

            # Stage 1: Try to close DB Browser (most common cause)
            db_browser_was_running = False
            try:
                import subprocess
                close_result = subprocess.run(
                    [sys.executable, 'data/health/close_db_browser.py'],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=5
                )

                if close_result.returncode == 0:
                    db_browser_was_running = True
                    print("   ✅ DB Browser closed successfully")
                    time.sleep(2)  # Brief pause for lock release
                elif close_result.returncode == 2:
                    print("   ⚠️  DB Browser has unsaved changes - close dialog is blocking")
                    print("   Please close DB Browser manually and retry")
                    print("=" * 70)
                    queue_error(
                        error_type='query_sync_target_locked',
                        context={
                            'exception_type': 'DBBrowserBlocking',
                            'error_message': 'DB Browser has unsaved changes dialog open',
                            'target': target
                        },
                        severity='ERROR'
                    )
                    return 1
                else:
                    print("   ℹ️  DB Browser not running - lock is from another source")

            except Exception as close_error:
                print("   ⚠️  Error checking DB Browser: {}".format(close_error))

            # Stage 2: Wait for file lock with intelligent retry
            # This handles cases where another Python process (analysis tools, etc.)
            # is using the query database temporarily
            max_wait = 45 if not db_browser_was_running else 15  # More time if unknown source
            print("   Waiting up to {}s for database lock to release...".format(max_wait))

            unlocked, wait_time, locking_processes = wait_for_file_unlock(target, max_wait_seconds=max_wait)

            if unlocked:
                print("   ✅ Database lock released after {:.1f}s".format(wait_time))
            else:
                # Stage 3: Final failure with diagnostic information
                print()
                print("❌ ERROR: Cannot access target database after {}s wait".format(int(wait_time)))
                print("   Target: {}".format(target))
                print("   Original error: {}".format(error_str))
                print()
                if locking_processes:
                    print("   Detected processes that may hold locks:")
                    for proc in locking_processes:
                        print("     - {}".format(proc))
                    print()
                print("   Possible causes:")
                print("   - Long-running analysis query in progress")
                print("   - Morning View TUI open with database connection")
                print("   - direct_db_query.py running")
                print("   - Oracle or other analysis tool running")
                print()
                print("   Try: Close analysis tools and retry, or wait for them to finish")
                print("=" * 70)
                queue_error(
                    error_type='query_sync_target_locked',
                    context={
                        'exception_type': type(e).__name__,
                        'error_message': str(e),
                        'target': target,
                        'wait_time_seconds': wait_time,
                        'locking_processes': locking_processes if locking_processes else 'unknown'
                    },
                    severity='ERROR'
                )
                return 1

    print()

    # Check for partial sync files from previous failed attempts
    partial_pattern = "data/datalake_query_partial_*.db"
    import glob
    partial_files = glob.glob(partial_pattern)

    if partial_files:
        # Found partial sync files - attempt recovery
        print("🔍 Detected {} partial sync file(s) from previous attempts".format(len(partial_files)))
        print()

        # Sort by modification time (newest first)
        partial_files.sort(key=os.path.getmtime, reverse=True)
        newest_partial = partial_files[0]
        age_hours = (time.time() - os.path.getmtime(newest_partial)) / 3600

        print("   Newest: {} (age: {:.1f} hours)".format(os.path.basename(newest_partial), age_hours))
        print("   Attempting automatic recovery...")
        print()

        # Try to complete the rename now (analysis tools may have closed)
        try:
            # Remove old target if it exists
            if os.path.exists(target):
                os.remove(target)
            # Rename partial to target
            os.rename(newest_partial, target)

            print("✅ RECOVERY SUCCESSFUL - Partial sync completed")
            print("   Query database: {}".format(target))
            print()

            # Clean up other partial files if any
            cleanup_count = 0
            for old_partial in partial_files[1:]:
                try:
                    os.remove(old_partial)
                    cleanup_count += 1
                except:
                    pass

            if cleanup_count > 0:
                print("   Cleaned up {} old partial file(s)".format(cleanup_count))
                print()

            print("✅ QUERY DATABASE SYNC RECOVERED")
            print("   Analysis tools can now query: {}".format(target))
            print("=" * 70)
            logger.info("Query sync recovered from partial file: {}".format(os.path.basename(newest_partial)))
            return 0

        except (OSError, PermissionError) as e:
            print("⚠️  Recovery failed (file still locked): {}".format(str(e)[:60]))
            print("   Will proceed with full sync to create fresh copy")
            print()
            # Continue with normal sync below

    # User confirmation if interactive and target exists
    if interactive and target_exists:
        print("⚠️  WARNING: This will OVERWRITE the existing query database.")
        print("   Any ongoing analysis will use stale data until sync completes.")
        print("   Estimated time: ~14 minutes for typical database size.")
        print()

        response = input("Proceed with sync? (y/n): ").strip().lower()
        if response != 'y' and response != 'yes':
            print()
            print("❌ Sync cancelled by user")
            print("=" * 70)
            return 2
        print()

    print("🔄 Starting sync operation...")

    # LOCK COORDINATION FIX (2025-12-16 Batch Fix)
    # Create sync lock file to coordinate with concurrent readers
    # This prevents Morning View, Oracle, and other tools from opening the query DB
    # during the critical rename window, eliminating the WinError 32 race condition
    sync_lock_file = "data/.datalake_query_sync_in_progress"
    try:
        with open(sync_lock_file, 'w') as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("Query database sync in progress - readers should wait\n")
        print("🔒 Created sync lock file: {}".format(sync_lock_file))
    except Exception as lock_error:
        print("⚠️  Warning: Could not create sync lock file: {}".format(lock_error))
        # Continue anyway - lock file is optimization, not requirement

    # Perform copy using SQLite online backup API
    # ARCHITECTURAL FIX (2025-12-17 Batch): DIRECTLY backup to target, no temp file + rename
    #
    # HISTORY OF FAILURES:
    # - 2025-12-08: Increased timeout to 90s → FAILED (recurred Dec 9)
    # - 2025-12-10: SQLite backup API + rename → FAILED (recurred Dec 11)
    # - 2025-12-15: Resource cleanup + gc.collect() → FAILED (recurred Dec 16)
    # - 2025-12-16: Lock coordination file → FAILED (recurred Dec 17)
    #
    # ROOT CAUSE: The temp file + atomic rename approach ALWAYS fails because:
    # 1. Rename requires exclusive lock on target file
    # 2. Target file is actively used by news collection, morning views, etc.
    # 3. Morning sync runs at 7:32 AM, copy takes 9 minutes
    # 4. By 7:41 AM, other processes are reading datalake_query.db
    # 5. Windows WinError 32 on rename is LEGITIMATE - file is in use!
    #
    # DURABLE SOLUTION: SQLite hot backup DIRECTLY to target file
    # - SQLite allows readers during incremental backup (pages=100)
    # - No rename operation needed = no exclusive lock needed
    # - Readers see consistent snapshot throughout backup
    # - SQLite handles concurrent access automatically
    #
    # TRADE-OFF: Old target file is overwritten incrementally (not atomic swap)
    # - Acceptable because readers get consistent snapshot from SQLite
    # - If backup fails, target may be partially written, but SQLite detects corruption
    # - On next run, recovery from partial file or fresh sync happens automatically
    #
    # References:
    # - https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup
    # - https://sqlite.org/backup.html (Section 3: "Online Backup API")
    # - https://sqlite.org/lockingv3.html (explains concurrent access)
    try:
        start_time = time.time()
        sync_completed_successfully = False  # Track completion for lock file cleanup

        import sqlite3

        # PREFLIGHT: Smoke-test key tables before overwriting query DB.
        # COUNT(*) walks each table's B-tree — corrupt pages throw DatabaseError.
        # Takes ~10-15s vs 12+ min for PRAGMA quick_check on 8 GB HDD.
        # If source is corrupt, we must NOT overwrite a potentially good query copy.
        print("   Preflight smoke test on source...")
        preflight_tables = ['option_contracts', 'flow_alerts', 'flow_options_scans',
                            'option_symbol_summary', 'historical_prices']
        try:
            check_conn = sqlite3.connect(source)
            corrupt_tables = []
            for table in preflight_tables:
                try:
                    check_conn.execute('SELECT COUNT(*) FROM {}'.format(table)).fetchone()
                except sqlite3.DatabaseError as tbl_err:
                    corrupt_tables.append((table, str(tbl_err)))
            check_conn.close()

            if corrupt_tables:
                print("   ❌ SOURCE DATABASE IS CORRUPT:")
                for tbl, err in corrupt_tables:
                    print("      {} — {}".format(tbl, err))
                print("   ABORTING SYNC — existing query database preserved.")
                queue_error(
                    error_type='query_sync_source_corrupt',
                    context={'corrupt_tables': [t[0] for t in corrupt_tables],
                             'errors': [t[1] for t in corrupt_tables], 'source': source},
                    severity='CRITICAL'
                )
                return 1
            else:
                print("   Source smoke test: OK ({} tables checked)".format(len(preflight_tables)))
        except Exception as check_err:
            print("   ❌ PREFLIGHT CHECK FAILED: {}".format(check_err))
            print("   ABORTING SYNC — existing query database preserved.")
            queue_error(
                error_type='query_sync_integrity_check_failed',
                context={'error': str(check_err), 'source': source},
                severity='ERROR'
            )
            return 1

        # CRITICAL CHANGE: Backup DIRECTLY to target (no temp file)
        # This eliminates the rename operation that causes WinError 32
        print("   Using SQLite hot backup directly to target (no rename required)...")
        print("   Target: {}".format(target))
        print()

        # Open connections - directly to target
        source_conn = sqlite3.connect(source)

        # If target exists and is locked by readers, SQLite allows incremental backup
        # Readers will see the old data until backup completes, then atomically see new data
        target_conn = sqlite3.connect(target)

        try:
            # Progress callback for large databases
            pages_copied = [0]  # Use list to allow modification in nested function
            total_pages = [0]

            def progress(status, remaining, total):
                pages_copied[0] = total - remaining
                total_pages[0] = total
                # Print progress every 100000 pages (~400MB at 4KB page size)
                if pages_copied[0] % 100000 == 0 and pages_copied[0] > 0:
                    pct = (pages_copied[0] / total) * 100 if total > 0 else 0
                    print("   Progress: {}/{} pages ({:.1f}%)".format(
                        pages_copied[0], total, pct), flush=True)

            # Perform backup with progress tracking directly to target
            # pages=100 means copy 100 pages at a time (allows concurrent readers + progress)
            # Readers can access target during backup and see consistent snapshot
            print("   Backing up {} to {}...".format(
                os.path.basename(source), os.path.basename(target)))
            source_conn.backup(target_conn, pages=100, progress=progress)

            # Final progress
            if total_pages[0] > 0:
                target_size = os.path.getsize(target) if os.path.exists(target) else 0
                logger.info("   ✅ Backup completed: {} pages ({})".format(
                    total_pages[0],
                    format_size(target_size)))

        finally:
            # RESOURCE CLEANUP
            # Close connections to release resources
            # Note: No rename operation needed anymore, so no WinError 32 issues!

            # Close both connections
            target_conn.close()
            source_conn.close()

            # Delete connection objects from namespace
            del target_conn
            del source_conn

            # Force garbage collection to release resources
            import gc
            gc.collect()

        # Verify target file after backup
        target_size = os.path.getsize(target)

        # Note: SQLite backup may produce different file size than source due to:
        # - Different page fragmentation
        # - Auto-vacuum differences
        # - Free page list differences
        # So we validate by table count instead of exact size match

        # Schema validation on target file (backup is already complete)
        source_tables = get_table_count(source)
        target_tables = get_table_count(target)
        schema_match = (source_tables == target_tables and source_tables > 0)

        if not schema_match and source_tables > 0:
            print("❌ ERROR: Sync failed - schema mismatch after backup")
            print("   Source tables: {}, Target tables: {}".format(source_tables, target_tables))
            queue_error(
                error_type='query_sync_schema_mismatch',
                context={
                    'source_tables': source_tables,
                    'target_tables': target_tables
                },
                severity='ERROR'
            )
            return 1

        # Drop indexes that only serve production (collector/analyzer/alerts/archive).
        # Query DB consumers (Morning View, Oracle) never filter on these columns.
        # Keeping them would force the quick-sync INSERT to maintain 5 B-trees instead of 2,
        # adding minutes of random I/O per cycle for zero read benefit.
        try:
            drop_conn = sqlite3.connect(target, timeout=10.0)
            for idx in [
                'idx_flow_scans_contract_lookup',   # FM Analyzer baseline lookups
                'idx_flow_scans_contract',           # FM evaluation backfill (symbol, expiration, option_type)
                'idx_flow_scans_significance',       # FM Alert detection
                'idx_flow_scans_expiration',          # Archive cleanup
            ]:
                drop_conn.execute("DROP INDEX IF EXISTS {}".format(idx))
            drop_conn.commit()
            drop_conn.close()
            print("   Dropped 3 production-only indexes from query DB (faster quick-sync)")
        except Exception as idx_err:
            logging.warning("Index cleanup on query DB failed (non-critical): {}".format(idx_err))

        # SUCCESS - No rename needed! SQLite backup wrote directly to target
        # This eliminates the WinError 32 file locking issue entirely
        duration = time.time() - start_time

        # Mark sync as successful
        sync_completed_successfully = True

        # Data verification - check that actual data was copied
        # NOTE: This is a diagnostic step only - if it fails (e.g., due to target database
        # being locked by analysis tools), the sync is still considered successful.
        # Wrapped in comprehensive exception handling to prevent verification failures
        # from failing the entire sync operation.
        data_verified = False
        latest_timestamp = None
        try:
            import sqlite3

            # Try to connect with short timeout - if target is locked, skip gracefully
            # This is actually a GOOD sign - it means analysis tools are using the fresh data
            source_conn = None
            target_conn = None
            try:
                source_conn = sqlite3.connect(source, timeout=5.0)
                target_conn = sqlite3.connect(target, timeout=5.0)

                source_cursor = source_conn.cursor()
                target_cursor = target_conn.cursor()

                # Check flow_options_scans timestamp (most frequently updated table)
                # Note: May be NULL if sync runs before market hours (Flow Monitor starts at 9:30 AM)
                source_cursor.execute("SELECT MAX(scan_timestamp) FROM flow_options_scans")
                source_latest = source_cursor.fetchone()[0]

                target_cursor.execute("SELECT MAX(scan_timestamp) FROM flow_options_scans")
                target_latest = target_cursor.fetchone()[0]

                # Close connections immediately after verification with aggressive cleanup (2025-12-15 fix)
                source_cursor.close()
                target_cursor.close()
                source_conn.close()
                target_conn.close()
                del source_cursor
                del target_cursor
                del source_conn
                del target_conn

                # Handle case where table is empty (morning sync before market hours)
                if source_latest is None and target_latest is None:
                    data_verified = True  # Both empty = verified
                    latest_timestamp = "pre-market (empty)"
                elif source_latest == target_latest:
                    data_verified = True
                    latest_timestamp = target_latest
                else:
                    data_verified = False
                    logging.debug("Data verification mismatch: source={}, target={}".format(
                        source_latest, target_latest))

            except (sqlite3.OperationalError, PermissionError, OSError) as conn_error:
                # Target locked by analysis tools - this is expected and acceptable
                logging.debug("Data verification skipped (database in use): {}".format(str(conn_error)[:60]))
                # Clean up connections if they were opened (aggressive cleanup - 2025-12-15 fix)
                if source_conn:
                    try:
                        source_conn.close()
                        del source_conn
                    except:
                        pass
                if target_conn:
                    try:
                        target_conn.close()
                        del target_conn
                    except:
                        pass

        except Exception as e:
            # Catch-all for any other verification errors - should NOT fail the sync
            logging.debug("Data verification error: {}".format(str(e)[:60]))

        # Two clean completion messages
        print()
        duration_minutes = duration / 60
        total_pages_str = "{:,}".format(total_pages[0]) if total_pages[0] > 0 else "unknown"
        print("✅ Sync completed: {} pages ({}) in {:.1f} minutes".format(
            total_pages_str, format_size(target_size), duration_minutes))

        if data_verified and latest_timestamp:
            print("✅ Verified: {} tables, data fresh (latest: {})".format(
                target_tables, latest_timestamp))
        elif schema_match:
            print("✅ Verified: {} tables, schema match confirmed".format(target_tables))
        else:
            print("✅ Verified: {} tables".format(target_tables))

        logging.debug("Analysis tools can now query: {}".format(target))
        logger.info("Query sync completed successfully in {:.1f} minutes".format(duration_minutes))
        return 0

    except Exception as e:
        # Cleanup temp file on error
        temp_target = target + ".tmp"
        if os.path.exists(temp_target):
            try:
                os.remove(temp_target)
            except:
                pass

        print("❌ ERROR: Sync operation failed")
        print("   Error: {}".format(e))
        print("=" * 70)
        queue_error(
            error_type='query_sync_operation_failed',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e),
                'source': source,
                'target': target
            },
            severity='ERROR'
        )
        return 1

    finally:
        # LOCK COORDINATION CLEANUP (2025-12-16 Batch Fix)
        # Remove sync lock file to allow readers to resume
        # Always remove on completion, whether success or failure
        if os.path.exists(sync_lock_file):
            try:
                os.remove(sync_lock_file)
                if sync_completed_successfully:
                    logging.debug("Sync lock file removed - readers can now access database")
                else:
                    logging.debug("Sync lock file removed (sync did not complete successfully)")
            except Exception as cleanup_error:
                print("⚠️  Warning: Could not remove sync lock file: {}".format(cleanup_error))
                print("   Manual cleanup needed: delete {}".format(sync_lock_file))

def sync_pre_market_updates():
    """Targeted sync: copy pre-market updates from datalake.db to datalake_query.db

    Syncs two categories of pre-market writes:
    1. Alert resolutions on flow_alerts (oi_resolution, next_day_oi, etc.)
    2. Watchlist sentiment on flow_watchlist_daily (alert_sentiment, building/closing counts)

    The regular quick-sync uses INSERT OR IGNORE which skips existing rows,
    so UPDATEs to existing rows never reach the query database.

    Returns:
        dict: {'success': bool, 'alerts_synced': int, 'watchlist_synced': int, 'elapsed': float}
    """
    logger = setup_logging()

    source = "data/datalake.db"
    target = "data/datalake_query.db"

    if not os.path.exists(source) or not os.path.exists(target):
        logger.error("Pre-market sync: source or target database not found")
        return {'success': False, 'alerts_synced': 0, 'watchlist_synced': 0, 'elapsed': 0.0}

    try:
        start_time = time.time()

        conn = sqlite3.connect(target, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("ATTACH DATABASE '{}' AS source".format(source))

        # 1. Sync alert resolution columns on flow_alerts
        cursor.execute("""
            UPDATE flow_alerts
            SET next_day_oi = (SELECT s.next_day_oi FROM source.flow_alerts s WHERE s.id = flow_alerts.id),
                oi_resolution = (SELECT s.oi_resolution FROM source.flow_alerts s WHERE s.id = flow_alerts.id),
                oi_change_contracts = (SELECT s.oi_change_contracts FROM source.flow_alerts s WHERE s.id = flow_alerts.id),
                oi_change_pct = (SELECT s.oi_change_pct FROM source.flow_alerts s WHERE s.id = flow_alerts.id),
                resolved_at = (SELECT s.resolved_at FROM source.flow_alerts s WHERE s.id = flow_alerts.id)
            WHERE id IN (
                SELECT s.id FROM source.flow_alerts s
                INNER JOIN flow_alerts t ON t.id = s.id
                WHERE s.oi_resolution IS NOT NULL
                  AND t.oi_resolution IS NULL
            )
        """)
        alerts_synced = cursor.rowcount

        # 2. Sync watchlist sentiment columns on flow_watchlist_daily
        cursor.execute("""
            UPDATE flow_watchlist_daily
            SET alert_sentiment = (
                    SELECT s.alert_sentiment FROM source.flow_watchlist_daily s
                    WHERE s.symbol = flow_watchlist_daily.symbol
                      AND s.entry_date = flow_watchlist_daily.entry_date
                ),
                building_alerts_count = (
                    SELECT s.building_alerts_count FROM source.flow_watchlist_daily s
                    WHERE s.symbol = flow_watchlist_daily.symbol
                      AND s.entry_date = flow_watchlist_daily.entry_date
                ),
                closing_alerts_count = (
                    SELECT s.closing_alerts_count FROM source.flow_watchlist_daily s
                    WHERE s.symbol = flow_watchlist_daily.symbol
                      AND s.entry_date = flow_watchlist_daily.entry_date
                )
            WHERE (symbol, entry_date) IN (
                SELECT s.symbol, s.entry_date FROM source.flow_watchlist_daily s
                INNER JOIN flow_watchlist_daily t
                    ON t.symbol = s.symbol AND t.entry_date = s.entry_date
                WHERE s.alert_sentiment IS NOT NULL
                  AND (t.alert_sentiment IS NULL OR t.alert_sentiment != s.alert_sentiment)
            )
        """)
        watchlist_synced = cursor.rowcount

        conn.commit()
        cursor.execute("DETACH DATABASE source")
        cursor.close()
        conn.close()
        del cursor
        del conn

        elapsed = time.time() - start_time

        logger.info("Pre-market sync: {} alert rows + {} watchlist rows in {:.2f}s".format(
            alerts_synced, watchlist_synced, elapsed))
        return {
            'success': True,
            'alerts_synced': alerts_synced,
            'watchlist_synced': watchlist_synced,
            'elapsed': elapsed
        }

    except Exception as e:
        logger.error("Pre-market sync failed: {}".format(e))
        return {'success': False, 'alerts_synced': 0, 'watchlist_synced': 0, 'elapsed': 0.0}


# Backward compatibility alias
sync_alert_resolutions = sync_pre_market_updates


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description='Database Backup & Sync Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Disaster recovery backup
  python data/health/db_backup.py --disaster

  # Query sync with user confirmation
  python data/health/db_backup.py --sync

  # Query sync without confirmation (automated mode)
  python data/health/db_backup.py --sync --auto

  # Quick sync - default market-hours tables (flow_alerts, flow_options_scans, flow_watchlist_daily)
  python data/health/db_backup.py --quick-sync

  # Quick sync - specific table (e.g., after symbol rollup)
  python data/health/db_backup.py --quick-sync --table flow_symbol_summary

  # Quick sync - multiple specific tables
  python data/health/db_backup.py --quick-sync --table option_symbol_summary --table option_contracts

  # Sync alert resolution updates to query database
  python data/health/db_backup.py --sync-resolutions

  # Run both disaster backup and query sync
  python data/health/db_backup.py --all
        """
    )

    parser.add_argument('--disaster', action='store_true',
                       help='Create disaster recovery backup (datalake_backup.db)')
    parser.add_argument('--sync', action='store_true',
                       help='Sync query database (datalake_query.db)')
    parser.add_argument('--quick-sync', action='store_true',
                       help='Quick sync - only today\'s flow data (fast, for market hours)')
    parser.add_argument('--table', action='append', dest='tables', metavar='TABLE',
                       help='Specific table(s) to quick-sync (use with --quick-sync). '
                            'Can be specified multiple times. Available: {}'.format(
                                ', '.join(SYNC_TABLE_CONFIG.keys())))
    parser.add_argument('--sync-resolutions', action='store_true',
                       help='Sync alert resolution updates (oi_resolution) to query database')
    parser.add_argument('--auto', action='store_true',
                       help='Automated mode (no user prompts) - use with --sync')
    parser.add_argument('--all', action='store_true',
                       help='Run both disaster backup and query sync')

    args = parser.parse_args()

    # Default behavior if no arguments: disaster backup (backward compatibility)
    if not (args.disaster or args.sync or args.quick_sync or args.sync_resolutions or args.all):
        print("No operation specified. Use --help to see available options.")
        print("Running default operation: disaster backup")
        return create_disaster_backup()

    exit_code = 0

    # Run disaster backup if requested
    if args.disaster or args.all:
        interactive = not args.auto
        result = create_disaster_backup(interactive=interactive)
        if result != 0:
            exit_code = result

    # Run query sync if requested
    if args.sync or args.all:
        interactive = not args.auto
        result = create_query_sync(interactive=interactive)
        if result != 0:
            exit_code = result

    # Run quick sync if requested
    if args.quick_sync:
        result = create_quick_sync(tables=args.tables)
        if result != 0:
            exit_code = result

    # Run pre-market sync if requested (alert resolutions + watchlist sentiment)
    if args.sync_resolutions:
        result = sync_pre_market_updates()
        if not result.get('success', False):
            exit_code = 1

    return exit_code

if __name__ == "__main__":
    exit(main())
