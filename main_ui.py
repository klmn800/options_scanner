#!/usr/bin/env python3
"""
Main Orchestrator UI Utilities (main_ui.py)
===========================================
Display and logging utilities for the options scanner orchestrator.

Contains:
- beautiful_log: Delegates to tools/log_utils.py (console + log file)
- create_status_box: Delegates to tools/log_utils.py (console + log file)
- print_banner: Startup banner display
- coffee_break: Timed pause with countdown
- safe_print: Safe console output
- log_subprocess_error: Subprocess error logging
- display_autofix_output: Autofix banner display

Used by: main.py (CleanOrchestrator inherits from OrchestratorUIMixin)
"""

import json
import sys
import time

# Add project tools to path
import os
project_root = os.path.dirname(os.path.abspath(__file__))
tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import now_eastern
from tools.autofix import queue_error
from tools.log_utils import (
    beautiful_log as _beautiful_log,
    create_status_box as _create_status_box,
    phase_header as _phase_header,
    _safe_print,
    _pad_to_width,
)


class OrchestratorUIMixin:
    """Mixin class providing UI/display methods for the orchestrator"""

    def safe_print(self, message=""):
        """Safe print that won't crash on closed stdout"""
        _safe_print(message)

    def log_subprocess_error(self, script_name, result):
        """Log subprocess errors using critical error logger

        Args:
            script_name: Name of script that failed
            result: subprocess.CompletedProcess result object
        """
        if result.returncode != 0:
            error_details = {
                'script': script_name,
                'exit_code': result.returncode
            }

            # Capture stderr if available
            if hasattr(result, 'stderr') and result.stderr:
                error_details['stderr'] = result.stderr[:500]  # First 500 chars

            # Capture stdout if available (may contain error messages)
            if hasattr(result, 'stdout') and result.stdout:
                error_details['stdout'] = result.stdout[:500]

            queue_error(
                error_type='subprocess_failed',
                context={
                    'script': script_name,
                    'exit_code': result.returncode,
                    **error_details
                },
                severity='ERROR'
            )

    def display_autofix_output(self, result):
        """Display autofix banner and logs from subprocess stdout if present

        When a subprocess triggers autofix immediate mode, the banner and logs
        are printed to the subprocess's stdout. This method detects and displays
        that output in main.py's console for user visibility.

        Args:
            result: subprocess.CompletedProcess result object

        Returns:
            bool: True if autofix output was detected and displayed
        """
        if not result.stdout:
            return False

        # Check if autofix banner is present
        if '\U0001f6a8' not in result.stdout and 'SPAWNING AUTO-FIX' not in result.stdout:
            return False

        # Display the autofix output
        _safe_print()
        _safe_print("=" * 70)
        _safe_print("\U0001f6a8 AUTOFIX IMMEDIATE MODE TRIGGERED IN SUBPROCESS")
        _safe_print("=" * 70)
        _safe_print(result.stdout)
        _safe_print("=" * 70)
        _safe_print()

        return True

    def _get_symbol_count(self):
        """Get actual KLMN 800 symbol count for banner display."""
        try:
            from core.symbols_klmn800 import get_symbols_klmn800
            return len(get_symbols_klmn800())
        except Exception:
            return 800  # Fallback

    def print_banner(self, mode="full"):
        """Display startup banner — dynamic for 'full' mode, static for single-step modes."""
        now = now_eastern()
        W = 67  # Inner box width
        S = "\u2551"  # Side char ║
        B = "\u2550"  # Border char ═

        def row(text):
            _safe_print("{} {} {}".format(S, _pad_to_width(text, W - 2), S))

        def blank():
            _safe_print("{} {:<{}} {}".format(S, "", W - 2, S))

        _safe_print()
        _safe_print("\u2554" + B * W + "\u2557")
        row("\U0001f680 OPTIONS SCANNER ORCHESTRATOR v4.0")
        _safe_print("\u2560" + B * W + "\u2563")
        row("\U0001f4c5 {}".format(now.strftime("%A, %B %d, %Y")))
        row("\u23f0 {}".format(now.strftime("%I:%M:%S %p EST")))
        row("\U0001f3ed Production System: {}".format("Active" if self.is_trading_day() else "Weekend Mode"))
        _safe_print("\u2560" + B * W + "\u2563")

        if mode == "full":
            is_friday = now.weekday() == 4

            row("\U0001f31f TODAY'S SCHEDULE")
            blank()
            row("Phase 1: Pre-Market (6:35 AM)")
            row("  1.1  Morning Option Pipeline Refresh")
            row("  1.2  Earnings Intelligence")
            row("  1.3  Metadata Collection")
            row("  1.4  Query Database Sync")
            row("  1.5  Morning Views (email)")
            blank()
            row("Phase 2: Flow Monitor (9:15 AM - 5:00 PM)")
            row("  2.1  Pre-Market Setup")
            row("  2.2  Market Hours Monitoring")
            row("  2.3  Market Close")
            row("  2.4  Historical Backfill")
            row("  2.5  Market Regime Summary")
            row("  2.6  Symbol Rollup")
            row("  2.7  Daily Evaluation")
            blank()
            row("Phase 3: Post-Market (~5:00 PM)")
            row("  3.1  Evening Option Pipeline Refresh")
            row("  3.2  Airline Play Tracking (7 symbols)")
            row("  3.3  Query Database Sync (Final)")
            blank()
            row("Phase 4: Evening Operations")
            row("  4.1  Daily Backup")
            row("  4.2  Autofix Review")

            if is_friday:
                blank()
                row("Phase 5: Friday Operations")
                row("  5.1  Weekly Backup")
                row("  5.2  Earnings Calendar Refresh")
                row("  5.3  Sector Archive (3-tier)")
            else:
                blank()
                row("Phase 5: Weekly ops (Friday only - skipped today)")

            blank()
            row("Phase 6: System Maintenance")
            row("  6.1  Performance Data Collection")

            blank()
            row("\U0001f3af Mission: Complete daily options analysis workflow")

        elif mode == "option-morning":
            row("\U0001f305 MORNING OPTION PIPELINE")
            blank()
            row("Target: Collect fresh Open Interest for KLMN symbols")
            row("Strategy: Collection \u2192 Rollup \u2192 OI Timing Analysis")
            blank()
            row("\U0001f3af Mission: Fresh OI data before market open")

        elif mode == "flow-monitor":
            row("\U0001f4c8 FLOW MONITOR PIPELINE")
            blank()
            row("Pre-Market: System preparation and setup")
            row("Market Hours: Real-time flow monitoring (9:30 AM - 4:00 PM)")
            row("Post-Market: Daily analysis and evaluation")
            blank()
            row("\U0001f3af Mission: Complete daily options flow monitoring cycle")

        elif mode == "option-evening":
            row("\U0001f306 EVENING OPTION PIPELINE")
            blank()
            row("Target: Update KLMN symbols with end-of-day volume")
            row("Strategy: Collection \u2192 Rollup \u2192 OI Timing Analysis")
            row("Result: Volume-enriched data for overnight analysis")
            blank()
            row("\U0001f3af Mission: Complete dataset with volume data")

        elif mode == "test":
            row("\U0001f9ea TEST MODE - DEVELOPMENT PIPELINE")
            blank()
            row("Universe: Limited symbol set for testing")
            row("Purpose: Development and debugging")
            row("Safety: Non-production environment")
            blank()
            row("\U0001f3af Mission: Validate system functionality safely")

        _safe_print("\u255a" + B * W + "\u255d")
        _safe_print()

    def beautiful_log(self, message, level='info'):
        """Delegates to shared log_utils.beautiful_log (console + log file)"""
        _beautiful_log(message, level)

    def create_status_box(self, title, content_lines, success=True):
        """Delegates to shared log_utils.create_status_box (console + log file)"""
        _create_status_box(title, content_lines, success)

    def phase_header(self, title, phase_number=None):
        """Delegates to shared log_utils.phase_header (console + log file)"""
        _phase_header(title, phase_number)

    def coffee_break(self, seconds, context="Taking a break", after_step=None):
        """Timed pause between operations with dynamic 'Up Next' display.

        Args:
            seconds: Duration to sleep
            context: Human-readable context message
            after_step: Name of the step that just completed (must match a
                        STEP_SEQUENCE entry). Used to look up the next step.
        """
        lines = [context]
        if seconds >= 60:
            m = seconds // 60
            lines.append("Duration: {} minute{}".format(m, "" if m == 1 else "s"))
        else:
            lines.append("Duration: {} second{}".format(seconds, "" if seconds == 1 else "s"))
        lines.append("Press Ctrl+C to safely stop Option Scanner system.")

        # Dynamic "Up Next" lookup
        if after_step and hasattr(self, 'STEP_SEQUENCE'):
            try:
                idx = self.STEP_SEQUENCE.index(after_step)
                if idx + 1 < len(self.STEP_SEQUENCE):
                    lines.append("Up Next: {}".format(self.STEP_SEQUENCE[idx + 1]))
            except ValueError:
                pass  # after_step not in sequence — skip "Up Next"

        _create_status_box("\u2615 Coffee Break", lines)
        time.sleep(seconds)
        print("")


# ── Daily State Persistence ──────────────────────────────────────────────
# Persists FM session stats, sync performance, and news API usage to a JSON
# file. Read at end-of-day by performance writer. Overwritten at the start
# of each daily cycle.

DAILY_STATE_PATH = os.path.join(project_root, 'logs', 'daily_state.json')


def _reset_daily_state(date_str):
    """Overwrite daily_state.json with empty structure. Called at start of each daily cycle."""
    state = {'date': date_str, 'fm_session': {}}
    os.makedirs(os.path.dirname(DAILY_STATE_PATH), exist_ok=True)
    with open(DAILY_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def _load_daily_state():
    """Load daily_state.json. Returns None if file missing or date doesn't match today."""
    try:
        with open(DAILY_STATE_PATH, 'r') as f:
            state = json.load(f)
        if state.get('date') == now_eastern().strftime('%Y-%m-%d'):
            return state
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def _save_fm_session(session_dict):
    """Update FM session stats in daily_state.json. Called after each FM cycle."""
    state = _load_daily_state() or {
        'date': now_eastern().strftime('%Y-%m-%d'),
        'fm_session': {},
    }
    state['fm_session'] = session_dict
    os.makedirs(os.path.dirname(DAILY_STATE_PATH), exist_ok=True)
    with open(DAILY_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def _save_sync_performance(sync_type, duration_seconds, size_display=None, pages=None, tables=None, success=True):
    """Append a sync performance entry to daily_state.json.

    Args:
        sync_type: 'full' or 'quick'
        duration_seconds: Wall-clock duration in seconds
        size_display: Human-readable size string (e.g. '7.16 GB')
        pages: Number of pages copied (full sync only)
        tables: Number of tables synced
        success: Whether the sync succeeded
    """
    state = _load_daily_state() or {
        'date': now_eastern().strftime('%Y-%m-%d'),
        'fm_session': {},
    }
    if 'sync_performance' not in state:
        state['sync_performance'] = []

    entry = {
        'timestamp': now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
        'sync_type': sync_type,
        'success': success,
        'duration_seconds': round(duration_seconds, 1),
    }
    if size_display:
        entry['size_display'] = size_display
    if pages is not None:
        entry['pages'] = pages
    if tables is not None:
        entry['tables'] = int(tables)

    state['sync_performance'].append(entry)
    os.makedirs(os.path.dirname(DAILY_STATE_PATH), exist_ok=True)
    with open(DAILY_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)


def _save_news_api_usage(source, api_calls=0, symbols_enriched=0, zero_article_calls=0):
    """Increment news API usage counters in daily_state.json.

    Called by EI and FM after their news enrichment runs. Counters accumulate
    across multiple calls (e.g., FM calls once per cycle with new watchlist entries).

    Args:
        source: 'ei', 'fm', or 'other'
        api_calls: Total API calls consumed (each uses budget)
        symbols_enriched: Calls that returned usable sentiment data
        zero_article_calls: Calls that returned no usable data (wasted budget)
    """
    state = _load_daily_state() or {
        'date': now_eastern().strftime('%Y-%m-%d'),
        'fm_session': {},
    }
    if 'news_api_usage' not in state:
        state['news_api_usage'] = {
            'calls_ei': 0,
            'calls_fm': 0,
            'calls_other': 0,
            'symbols_enriched': 0,
            'zero_article_calls': 0,
        }

    usage = state['news_api_usage']
    calls_key = 'calls_{}'.format(source)
    if calls_key not in usage:
        calls_key = 'calls_other'

    usage[calls_key] = usage.get(calls_key, 0) + api_calls
    usage['symbols_enriched'] = usage.get('symbols_enriched', 0) + symbols_enriched
    usage['zero_article_calls'] = usage.get('zero_article_calls', 0) + zero_article_calls

    os.makedirs(os.path.dirname(DAILY_STATE_PATH), exist_ok=True)
    with open(DAILY_STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)
