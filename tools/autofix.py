#!/usr/bin/env python3
"""
Auto-Fix System - Entry Point
==============================
Provides clean interface for strategies to trigger autonomous error fixing.

Usage:
    from tools.autofix import handle_error

    # Immediate spawn for critical errors
    handle_error(
        error_type='no_contracts_stored',
        context={'symbols_attempted': 800, 'api_calls': 1500},
        severity='CRITICAL'
    )

    # Deferred to batch mode for non-critical errors
    handle_error(
        error_type='api_slow_response',
        context={'avg_response_time': 5.2},
        severity='ERROR'
    )

Architecture:
- Wraps existing main_fix_launcher.py (proven in production)
- Logs with [LOGANALYZER-ALERT] trigger for batch mode detection
- Spawns Claude Code as autofix user via scheduled task (immediate mode)
- Rate limiting: 3 attempts per error type/day, 5 spawns per hour
- Escalation protocol: Attempt 1 (LOW) → 2 (MEDIUM) → 3 (HIGH) → Human

Author: Ben (with Claude)
Date: 2025-11-04
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path for imports
def get_project_root():
    """Get project root directory"""
    return Path(__file__).parent.parent

project_root = get_project_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# ==============================================================================
# Error Queue System - Unified error tracking for Immediate and Batch Autofix
# ==============================================================================

import json
import inspect
from datetime import datetime, timedelta


def _get_todays_date():
    """Get current Eastern date as YYYY-MM-DD string"""
    try:
        from tools.timezone_utils import now_eastern
        return now_eastern().strftime('%Y-%m-%d')
    except:
        # Fallback to system time if timezone_utils unavailable
        return datetime.now().strftime('%Y-%m-%d')


def _get_error_file_path(date=None):
    """Get path to error queue file for given date

    Args:
        date: Date string YYYY-MM-DD (default: today)

    Returns:
        Path: Path to error queue JSON file
    """
    if date is None:
        date = _get_todays_date()
    return project_root / 'autofix' / 'errors' / f'errors_{date}.json'


def _detect_source_info():
    """Auto-detect source file and line number from call stack

    Returns:
        dict: {'file': 'path/to/file.py', 'line': 123}
    """
    try:
        # Walk up the stack to find the caller (skip autofix.py frames)
        for frame_info in inspect.stack():
            filepath = frame_info.filename
            # Skip autofix.py and this file
            if 'autofix.py' not in filepath and 'error_logger.py' not in filepath:
                return {
                    'file': filepath.replace(str(project_root) + os.sep, ''),
                    'line': frame_info.lineno
                }
    except:
        pass
    return {'file': 'unknown', 'line': 0}


def queue_error(error_type, context=None, severity='ERROR', source_info=None):
    """Write error to daily queue for Autofix processing

    Args:
        error_type (str): Short error identifier (e.g., 'database_locked', 'api_timeout')
        context (dict): Error details and diagnostics (optional)
        severity (str): 'CRITICAL' or 'ERROR' (default: 'ERROR')
        source_info (dict): Manual source info {'file': 'path', 'line': 123} (auto-detected if None)

    Returns:
        str: Path to error file where error was written

    Example:
        queue_error(
            error_type='database_sync_failed',
            context={'error': str(e), 'retry_count': 3},
            severity='ERROR'
        )
    """
    if context is None:
        context = {}

    if source_info is None:
        source_info = _detect_source_info()

    # Create error entry
    error_entry = {
        'timestamp': datetime.now().isoformat(),
        'error_type': error_type,
        'severity': severity,
        'context': context,
        'source_file': source_info.get('file', 'unknown'),
        'source_line': source_info.get('line', 0),
        'handled_by': 'none',  # Will be set to 'immediate' or 'batch' when processed
        'fix_status': 'pending',
        'fix_timestamp': None,
        'attempt_count': 0,
        'notes': ''
    }

    # Get today's error file
    error_file = _get_error_file_path()

    # Read existing errors (if file exists)
    errors = []
    if error_file.exists():
        try:
            with open(error_file, 'r', encoding='utf-8') as f:
                errors = json.load(f)
        except Exception as e:
            logging.warning(f"Could not read error queue {error_file}: {e}")
            errors = []

    # Append new error
    errors.append(error_entry)

    # Write back to file
    try:
        error_file.parent.mkdir(parents=True, exist_ok=True)
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(errors, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to write to error queue {error_file}: {e}")
        return None

    return str(error_file)


def get_todays_errors():
    """Read today's error queue

    Returns:
        list: All errors from today's queue (empty list if no errors)
    """
    error_file = _get_error_file_path()

    if not error_file.exists():
        return []

    try:
        with open(error_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to read error queue {error_file}: {e}")
        return []


def mark_error_fixed(error_timestamp, notes="", fix_status='fixed'):
    """Mark error as fixed in today's queue

    Args:
        error_timestamp (str): ISO timestamp of error to mark (from error entry)
        notes (str): Description of what was done to fix it
        fix_status (str): Status to set ('fixed', 'failed', 'in_progress')

    Returns:
        bool: True if error was found and marked, False otherwise
    """
    error_file = _get_error_file_path()

    if not error_file.exists():
        logging.warning(f"Error queue file not found: {error_file}")
        return False

    try:
        # Read errors
        with open(error_file, 'r', encoding='utf-8') as f:
            errors = json.load(f)

        # Find and update error
        found = False
        for error in errors:
            if error['timestamp'] == error_timestamp:
                error['fix_status'] = fix_status
                error['fix_timestamp'] = datetime.now().isoformat()
                error['notes'] = notes
                error['attempt_count'] = error.get('attempt_count', 0) + 1
                found = True
                break

        if not found:
            logging.warning(f"Error with timestamp {error_timestamp} not found in queue")
            return False

        # Write back
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(errors, f, indent=2)

        return True

    except Exception as e:
        logging.error(f"Failed to mark error fixed: {e}")
        return False


def _mark_duplicate_errors(error_type, representative_timestamp, duplicate_timestamps):
    """Mark duplicate errors as handled by deduplication

    Args:
        error_type (str): Error type that was deduplicated
        representative_timestamp (str): Timestamp of the error that will be fixed
        duplicate_timestamps (list): Timestamps of duplicate errors to mark

    Returns:
        int: Number of duplicates marked
    """
    if not duplicate_timestamps:
        return 0

    error_file = _get_error_file_path()

    if not error_file.exists():
        logging.warning(f"Error queue file not found: {error_file}")
        return 0

    try:
        # Read errors
        with open(error_file, 'r', encoding='utf-8') as f:
            errors = json.load(f)

        # Mark duplicates
        marked_count = 0
        for error in errors:
            if error['timestamp'] in duplicate_timestamps and error['error_type'] == error_type:
                error['handled_by'] = 'batch_deduplication'
                error['fix_status'] = 'deduplicated'
                error['fix_timestamp'] = datetime.now().isoformat()
                error['notes'] = f"Deduplicated with {representative_timestamp} (same error_type)"
                marked_count += 1

        # Write back
        with open(error_file, 'w', encoding='utf-8') as f:
            json.dump(errors, f, indent=2)

        return marked_count

    except Exception as e:
        logging.error(f"Failed to mark duplicate errors: {e}")
        return 0


def get_error_history(days=30):
    """Read past N days of errors for pattern detection

    Args:
        days (int): Number of days to look back (default: 30)

    Returns:
        dict: {date: [errors...]} for each date with errors
    """
    history = {}

    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        error_file = _get_error_file_path(date)

        if error_file.exists():
            try:
                with open(error_file, 'r', encoding='utf-8') as f:
                    history[date] = json.load(f)
            except Exception as e:
                logging.warning(f"Could not read error history for {date}: {e}")

    return history


def handle_error(error_type, context=None, severity='CRITICAL', main_py_pid=None):
    """
    Trigger autofix system for production errors

    Args:
        error_type (str): Short error identifier (e.g., 'duplicate_contracts', 'no_data_stored')
        context (dict): Error details and diagnostics
            - For collection errors: {'symbols_attempted': 800, 'contracts_stored': 0}
            - For duplicate errors: {'duplicate_count': 5, 'symbol': 'AAPL'}
            - For API errors: {'api_calls_failed': 10, 'error_code': 429}
        severity (str): 'CRITICAL' triggers immediate spawn, 'ERROR' waits for batch mode
        main_py_pid (int): Optional PID of main.py process (for restart validation)

    Returns:
        bool: True if autofix spawned successfully, False if blocked by rate limits
              (only for ERROR severity - CRITICAL severity exits immediately)

    Behavior:
        CRITICAL severity:
            1. Writes error to daily queue (autofix/errors/errors_YYYY-MM-DD.json)
            2. Checks rate limits (3 per error type/day, 5/hour globally)
            3. Spawns Claude Code immediately as autofix user
            4. Exits process with sys.exit(1) - changes require restart

        ERROR severity:
            1. Writes error to daily queue (autofix/errors/errors_YYYY-MM-DD.json)
            2. Waits for batch mode (end-of-day review in main.py)
            3. Returns False (no immediate action)

    Example:
        # In strategy code after detecting silent failure:
        from tools.autofix import handle_error

        stats = self.storage.get_collection_stats(trade_date)
        if stats['total_contracts'] == 0 and symbols_attempted > 0:
            handle_error(
                error_type='no_contracts_stored',
                context={
                    'trade_date': trade_date,
                    'symbols_attempted': len(symbols_list),
                    'api_calls_made': stats['api_calls'],
                    'timestamp': now_eastern().isoformat()
                },
                severity='CRITICAL'
            )
    """
    # Ensure context is a dict
    if context is None:
        context = {}

    # Add main.py PID to context if provided
    if main_py_pid:
        context['main_py_pid'] = main_py_pid

    # Initialize logger
    logger = logging.getLogger('autofix')

    # 1. Write error to daily queue (unified system)
    error_file = queue_error(
        error_type=error_type,
        context=context,
        severity=severity
    )

    logger.info(f"Error queued for autofix: {error_type} (severity={severity}) -> {error_file}")

    # 2. If severity is CRITICAL, spawn immediately and exit
    if severity == 'CRITICAL':
        _spawn_immediate_fix(error_type, context, main_py_pid)
        logger.info(f"CRITICAL error - exiting immediately so autofix changes can be applied on restart")
        sys.exit(1)  # Exit immediately - changes require restart

    # 3. Otherwise (ERROR severity), wait for batch mode
    logger.info(f"Error logged for batch mode review: {error_type}")
    return False


def _mark_error_handled_by_immediate(error_type):
    """Mark most recent error of this type as handled by immediate mode

    Args:
        error_type: Error type to mark
    """
    try:
        errors = get_todays_errors()

        # Find most recent error of this type (last in list)
        for error in reversed(errors):
            if error['error_type'] == error_type and error['handled_by'] == 'none':
                # Update the error file directly
                error_file = _get_error_file_path()
                with open(error_file, 'r', encoding='utf-8') as f:
                    all_errors = json.load(f)

                # Find and update
                for e in reversed(all_errors):
                    if e['error_type'] == error_type and e['handled_by'] == 'none':
                        e['handled_by'] = 'immediate'
                        e['fix_status'] = 'in_progress'
                        break

                # Write back
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(all_errors, f, indent=2)
                break
    except Exception as e:
        logging.warning(f"Could not mark error as handled by immediate mode: {e}")


def _spawn_immediate_fix(error_type, context, main_py_pid=None):
    """
    Spawn Claude Code immediately for critical errors

    Internal function - called by handle_error() for CRITICAL severity

    Args:
        error_type: Error type string
        context: Error context dict
        main_py_pid: Optional main.py PID

    Returns:
        bool: True if spawned, False if blocked
    """
    try:
        # Mark error as handled by immediate mode
        _mark_error_handled_by_immediate(error_type)

        # Import launcher from autofix directory
        autofix_dir = project_root / 'autofix'
        if str(autofix_dir) not in sys.path:
            sys.path.insert(0, str(autofix_dir))

        from main_fix_launcher import launch_claude_fix

        # Build error context for launcher
        error_context = {
            'error_type': error_type,
            **context
        }

        # Add main.py PID if provided
        if main_py_pid:
            error_context['main_py_pid'] = main_py_pid

        # Launch Claude Code (returns True if spawned, False if rate limited)
        return launch_claude_fix(error_context)

    except Exception as e:
        logging.error(f"Failed to spawn autofix for {error_type}: {e}")
        return False


def get_error_queue(max_sessions=10):
    """Read and deduplicate today's error queue WITHOUT processing.

    Use this to display the queue to the user before spawning fix sessions.

    Args:
        max_sessions: Max errors to return (default 10, None for unlimited)

    Returns:
        dict with keys:
            - total_errors: Raw error count
            - unique_errors: Count after dedup
            - error_summary: List of error dicts for display
            - errors_to_fix: Full error objects (for passing to process_error_queue)
            - skipped: True if batch mode should be skipped
            - skip_reason: Why it was skipped
    """
    import sys
    from pathlib import Path

    autofix_dir = project_root / 'autofix'
    if str(autofix_dir) not in sys.path:
        sys.path.insert(0, str(autofix_dir))

    try:
        from batch_mode_tracker import (
            find_todays_errors,
            should_skip_batch_mode
        )

        # Check if should skip (Friday archive)
        skip, reason = should_skip_batch_mode()
        if skip:
            logging.info(f"Batch mode skipped: {reason}")
            return {
                'total_errors': 0,
                'unique_errors': 0,
                'error_summary': [],
                'errors_to_fix': [],
                'skipped': True,
                'skip_reason': reason
            }

        # Find all pending errors from today's queue
        errors = find_todays_errors()

        if not errors:
            logging.debug("No pending errors today - batch mode not needed")
            return {
                'total_errors': 0,
                'unique_errors': 0,
                'error_summary': [],
                'errors_to_fix': []
            }

        logging.info(f"Found {len(errors)} pending error(s) to fix")

        # Deduplicate errors by error_type (spawn once per unique type)
        error_groups = {}
        for error in errors:
            error_type = error['error_type']
            if error_type not in error_groups:
                error_groups[error_type] = []
            error_groups[error_type].append((error['timestamp'], error))

        unique_errors = {}
        duplicate_info = {}

        for error_type, timestamp_error_pairs in error_groups.items():
            representative_ts, representative_error = timestamp_error_pairs[0]
            representative_error['occurrence_count'] = len(timestamp_error_pairs)
            unique_errors[error_type] = representative_error

            if len(timestamp_error_pairs) > 1:
                duplicate_timestamps = [ts for ts, _ in timestamp_error_pairs[1:]]
                duplicate_info[error_type] = (representative_ts, duplicate_timestamps)

        errors_to_fix = list(unique_errors.values())
        logging.info(f"Deduplicated to {len(errors_to_fix)} unique error type(s)")

        # Mark duplicate errors
        if duplicate_info:
            for error_type, (rep_ts, dup_timestamps) in duplicate_info.items():
                marked = _mark_duplicate_errors(error_type, rep_ts, dup_timestamps)
                logging.info(f"Marked {marked} duplicate(s) for {error_type} as deduplicated")

        # Limit to max_sessions if specified
        if max_sessions:
            errors_to_fix = errors_to_fix[:max_sessions]

        return {
            'total_errors': len(errors),
            'unique_errors': len(errors_to_fix),
            'error_summary': [
                {
                    'error_type': e['error_type'],
                    'severity': e['severity'],
                    'timestamp': e['timestamp'],
                    'occurrence_count': e.get('occurrence_count', 1)
                }
                for e in errors_to_fix
            ],
            'errors_to_fix': errors_to_fix
        }

    except Exception as e:
        logging.error(f"Error reading batch queue: {e}")
        return {
            'total_errors': 0,
            'unique_errors': 0,
            'error_summary': [],
            'errors_to_fix': []
        }


def process_error_queue(errors_to_fix):
    """Spawn fix sessions for errors returned by get_error_queue().

    Args:
        errors_to_fix: List of error dicts from get_error_queue()['errors_to_fix']

    Returns:
        int: Number of sessions spawned
    """
    import sys
    from pathlib import Path

    autofix_dir = project_root / 'autofix'
    if str(autofix_dir) not in sys.path:
        sys.path.insert(0, str(autofix_dir))

    from batch_mode_spawner import spawn_batch_fix_for_error

    sessions_spawned = 0
    for i, error in enumerate(errors_to_fix, 1):
        logging.info(f"Spawning batch fix {i}/{len(errors_to_fix)}: {error['error_type']}")
        spawn_batch_fix_for_error(error, wait_for_completion=True)
        logging.info(f"Batch fix {i} complete - moving to next")
        sessions_spawned += 1

    return sessions_spawned


def check_and_spawn_batch_mode(lookback_hours=24, max_sessions=10):
    """Batch mode: Fix all pending errors from today (legacy single-call interface).

    Combines get_error_queue() + process_error_queue() for backward compatibility.
    New callers should use the two-phase API for better display control.

    Args:
        lookback_hours: Not used (reviews today only) - kept for backward compatibility
        max_sessions: Max errors to fix (default 10, set to None for unlimited)

    Returns:
        dict: Structured results for display
    """
    queue = get_error_queue(max_sessions=max_sessions)

    if queue.get('skipped'):
        return {
            'sessions_spawned': 0,
            'total_errors': 0,
            'unique_errors': 0,
            'error_summary': [],
            'skipped': True,
            'skip_reason': queue.get('skip_reason', 'Unknown')
        }

    errors_to_fix = queue.get('errors_to_fix', [])
    sessions_spawned = 0

    if errors_to_fix:
        sessions_spawned = process_error_queue(errors_to_fix)

    return {
        'sessions_spawned': sessions_spawned,
        'total_errors': queue['total_errors'],
        'unique_errors': queue['unique_errors'],
        'error_summary': queue['error_summary']
    }


# ==============================================================================
# Self-Monitoring Utilities
# ==============================================================================
# These help strategies detect anomalies that should trigger autofix

def check_collection_health(stats, expected_symbols=800, min_success_rate=0.95):
    """
    Check if collection results are healthy

    Detects silent failures and statistical anomalies in data collection

    Args:
        stats (dict): Collection statistics
            - total_contracts: Number of contracts stored
            - symbols_attempted: Number of symbols processed
            - failed_symbols: Number of symbols that failed
            - api_calls_made: Number of API calls
        expected_symbols (int): Expected number of symbols (default 800 for KLMN)
        min_success_rate (float): Minimum acceptable success rate (default 0.95 = 95%)

    Returns:
        dict: Health check results
            - healthy (bool): True if collection is healthy
            - issues (list): List of issue descriptions
            - should_trigger_autofix (bool): True if autofix should be triggered
            - error_type (str): Suggested error_type for handle_error()
            - context (dict): Context to pass to handle_error()

    Example:
        # In collector after running collection:
        from tools.autofix import check_collection_health, handle_error

        stats = self.storage.get_collection_stats(trade_date)
        health = check_collection_health(stats, expected_symbols=800)

        if not health['healthy'] and health['should_trigger_autofix']:
            handle_error(
                error_type=health['error_type'],
                context=health['context'],
                severity='CRITICAL'
            )
    """
    issues = []
    should_trigger = False
    error_type = None
    context = {}

    total_contracts = stats.get('total_contracts', 0)
    symbols_attempted = stats.get('symbols_attempted', 0)
    failed_symbols = stats.get('failed_symbols', 0)

    # Check 1: Zero contracts stored (silent failure)
    if total_contracts == 0 and symbols_attempted > 0:
        issues.append("CRITICAL: Zero contracts stored despite attempting collection")
        should_trigger = True
        error_type = 'no_contracts_stored'
        context = {
            'symbols_attempted': symbols_attempted,
            'api_calls': stats.get('api_calls_made', 0),
            'failed_symbols': failed_symbols
        }

    # Check 2: Very low contract count (possible API or logic issue)
    elif total_contracts < 100 and symbols_attempted >= expected_symbols:
        issues.append(f"WARNING: Very low contract count ({total_contracts}) for {symbols_attempted} symbols")
        should_trigger = True
        error_type = 'low_contract_count'
        context = {
            'total_contracts': total_contracts,
            'symbols_attempted': symbols_attempted,
            'expected_minimum': 1000  # Rough estimate
        }

    # Check 3: High failure rate (>5% of symbols failed)
    if symbols_attempted > 0:
        failure_rate = failed_symbols / symbols_attempted
        success_rate = 1 - failure_rate

        if success_rate < min_success_rate:
            issues.append(f"WARNING: High failure rate ({failure_rate:.1%}) - {failed_symbols}/{symbols_attempted} symbols failed")
            should_trigger = True
            error_type = 'high_failure_rate'
            context = {
                'failed_symbols': failed_symbols,
                'symbols_attempted': symbols_attempted,
                'failure_rate': round(failure_rate, 3),
                'success_rate': round(success_rate, 3),
                'minimum_acceptable': min_success_rate
            }

    # Check 4: Symbol count mismatch
    if symbols_attempted > 0 and abs(symbols_attempted - expected_symbols) > 10:
        issues.append(f"WARNING: Symbol count mismatch (attempted {symbols_attempted}, expected {expected_symbols})")
        # Don't trigger autofix for this - might be intentional (test mode, filtered list)

    return {
        'healthy': len(issues) == 0,
        'issues': issues,
        'should_trigger_autofix': should_trigger,
        'error_type': error_type,
        'context': context
    }


if __name__ == '__main__':
    # Test mode - demonstrate usage
    print("Auto-Fix System - Entry Point")
    print("=" * 70)
    print()
    print("This module provides the handle_error() function for strategies.")
    print()
    print("Example usage:")
    print()
    print("    from tools.autofix import handle_error")
    print()
    print("    handle_error(")
    print("        error_type='no_contracts_stored',")
    print("        context={'symbols_attempted': 800},")
    print("        severity='CRITICAL'")
    print("    )")
    print()
    print("See module docstring for full documentation.")
