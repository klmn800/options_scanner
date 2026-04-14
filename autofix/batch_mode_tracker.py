#!/usr/bin/env python3
"""
Batch Mode Tracker - Session Discovery and Context Loading
===========================================================
Finds immediate mode sessions to review and prepares context for batch review.

Key Functions:
- find_todays_errors(): Find all unfixed errors from today's queue
- load_historical_journals(): Load past 30 days for pattern detection
- should_skip_batch_mode(): Check if Friday archive is running

Author: Ben (with Claude)
Date: 2025-11-11
"""

import json
import os
import sys
import psutil
from pathlib import Path
from datetime import datetime, timedelta

# Configure UTF-8 encoding for Windows compatibility (MANDATORY)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


def eastern_date_string():
    """Get current Eastern date as YYYY-MM-DD string"""
    # Import here to avoid circular dependency
    import sys
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from tools.timezone_utils import now_eastern
    return now_eastern().strftime('%Y-%m-%d')


def find_todays_errors():
    """Read today's error queue for all unfixed errors

    Returns:
        list: All errors from today needing fixes (fix_status='pending')
            Each error has: timestamp, error_type, severity, context, etc.
    """
    # Import from tools.autofix
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from tools.autofix import get_todays_errors

        errors = get_todays_errors()

        # Filter to unfixed errors only
        pending_errors = [
            error for error in errors
            if error.get('fix_status') == 'pending'
        ]

        # Some errors are known-transient: they self-heal on the next cycle
        # (e.g., quick sync lock contention, transient memory pressure).
        # Skip these UNLESS the same error_type recurs 3+ times — that's a
        # pattern worth investigating, not a fluke.
        # Other WARNING errors (news API failures, metadata issues) may need
        # review on first occurrence, so we don't filter those.
        # (2026-02-25 Batch Fix)
        TRANSIENT_CATEGORIES = {'lock_error', 'memory_error'}

        # Count transient errors by type
        transient_counts = {}
        for error in pending_errors:
            category = error.get('context', {}).get('error_category', '')
            if category in TRANSIENT_CATEGORIES:
                et = error.get('error_type', '')
                transient_counts[et] = transient_counts.get(et, 0) + 1

        # Decide which transient error_types have recurred enough to escalate
        recurring_types = {et for et, count in transient_counts.items() if count >= 3}

        actionable_errors = []
        for error in pending_errors:
            category = error.get('context', {}).get('error_category', '')
            et = error.get('error_type', '')

            if category in TRANSIENT_CATEGORIES:
                if et in recurring_types:
                    # Recurred 3+ times — escalate for review
                    error['_escalated_from_transient'] = True
                    error['_transient_count'] = transient_counts[et]
                    actionable_errors.append(error)
                # else: skip — one-off transient, will self-heal
            else:
                actionable_errors.append(error)

        return actionable_errors

    except Exception as e:
        print(f"⚠️  Warning: Could not read error queue: {e}")
        return []




def load_historical_journals(lookback_days=30):
    """Load past N days of journals for pattern detection

    Args:
        lookback_days: Number of days to look back (default 30)

    Returns:
        list: Journal entries with date and content
            [{'date': '2025-11-10', 'content': '...'}, ...]
    """
    journals = []

    for i in range(lookback_days):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        journal_file = Path(f'autofix/logs/auto_fix_journal_{date}.md')

        if journal_file.exists():
            try:
                with open(journal_file, 'r', encoding='utf-8') as f:
                    journals.append({
                        'date': date,
                        'content': f.read()
                    })
            except Exception as e:
                print(f"⚠️  Warning: Could not read journal {journal_file}: {e}")

    return journals


def should_skip_batch_mode():
    """Check if Friday archive is still running

    Returns:
        tuple: (skip: bool, reason: str)
            - (True, "Friday archive still running") if should skip
            - (False, "All clear for batch mode") if safe to proceed
    """
    try:
        for proc in psutil.process_iter(['cmdline']):
            try:
                cmdline_list = proc.info.get('cmdline')
                if cmdline_list is None:
                    continue
                cmdline = ' '.join(str(arg) for arg in cmdline_list)
                if 'db_archive_sector.py' in cmdline:
                    return True, "Friday archive still running"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        print(f"⚠️  Warning: Could not check running processes: {e}")
        # Fail safe - don't skip if we can't check

    return False, "All clear for batch mode"




if __name__ == '__main__':
    # Test mode - demonstrate functionality
    print("Batch Mode Tracker - Test Mode")
    print("=" * 70)
    print()

    # Test 1: Find today's errors
    print("Test 1: Finding pending errors from today...")
    errors = find_todays_errors()
    print(f"Found {len(errors)} error(s) needing review")
    for error in errors:
        print(f"  - {error['error_type']} @ {error['timestamp']}")
    print()

    # Test 2: Load historical journals
    print("Test 2: Loading historical journals (past 30 days)...")
    journals = load_historical_journals(lookback_days=30)
    print(f"Found {len(journals)} journal(s)")
    for journal in journals[:5]:  # Show first 5
        print(f"  - {journal['date']}: {len(journal['content'])} characters")
    print()

    # Test 3: Check archive status
    print("Test 3: Checking if Friday archive is running...")
    skip, reason = should_skip_batch_mode()
    print(f"Skip batch mode: {skip}")
    print(f"Reason: {reason}")
