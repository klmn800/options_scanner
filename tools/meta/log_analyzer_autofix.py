#!/usr/bin/env python3
"""
Log Analyzer with Auto-Fix - PROOF OF CONCEPT
==============================================
Enhanced log analyzer that detects errors and spawns Claude Code to fix them.

This is a test version for the self-healing system POC.

Features:
- Detects critical errors in logs
- Checks auto-fix manager for safety limits
- Spawns Claude Code with error context and fix instructions
- Tracks fix attempts to prevent infinite loops

Usage:
    python tools/meta/log_analyzer_autofix.py                # Scan and auto-fix
    python tools/meta/log_analyzer_autofix.py --no-spawn     # Detect only, don't spawn Claude
    python tools/meta/log_analyzer_autofix.py --hours 1      # Scan last hour

Author: Ben (with Claude)
Date: 2025-10-16
"""

import os
import sys
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.error_logger import get_trigger_phrase
from tools.meta.auto_fix_manager import AutoFixManager


def find_recent_logs(hours_back=24):
    """Find log files modified within the specified hours"""
    logs_dir = project_root / "logs"
    if not logs_dir.exists():
        return []

    cutoff_time = datetime.now() - timedelta(hours=hours_back)
    recent_logs = []

    for log_file in logs_dir.glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime > cutoff_time:
                recent_logs.append(log_file)
        except Exception as e:
            print(f"Warning: Could not check {log_file.name}: {e}")

    return sorted(recent_logs, key=lambda p: p.stat().st_mtime, reverse=True)


def extract_error_details(log_files):
    """Extract detailed error information for auto-fix

    Returns:
        list: List of error detail dicts with context for Claude Code
    """
    trigger = get_trigger_phrase()
    errors = []

    for log_file in log_files:
        try:
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

                for i, line in enumerate(lines):
                    if trigger in line:
                        # Extract error context (5 lines before, 10 lines after)
                        start = max(0, i - 5)
                        end = min(len(lines), i + 10)
                        context_lines = lines[start:end]

                        # Parse error details from context
                        error_message = None
                        file_path = None
                        exception_type = None

                        for ctx_line in context_lines:
                            # Look for error message
                            if "ERROR" in ctx_line and "|" in ctx_line:
                                parts = ctx_line.split("|")
                                if len(parts) >= 2:
                                    error_message = parts[0].split("ERROR")[-1].strip()

                            # Look for file path
                            if "Context:" in ctx_line and "file=" in ctx_line:
                                file_match = ctx_line.split("file=")
                                if len(file_match) > 1:
                                    file_path = file_match[1].split(",")[0].strip()

                            # Look for exception type
                            if "Exception:" in ctx_line:
                                exc_match = ctx_line.split("Exception:")
                                if len(exc_match) > 1:
                                    exception_type = exc_match[1].split(":")[0].strip()

                        errors.append({
                            "log_file": log_file.name,
                            "error_message": error_message or "Unknown error",
                            "file_path": file_path,
                            "exception_type": exception_type,
                            "context": "".join(context_lines),
                            "timestamp": datetime.now().isoformat()
                        })

        except Exception as e:
            print(f"Warning: Could not read {log_file.name}: {e}")

    return errors


def spawn_claude_for_fix(error_details):
    """Spawn Claude Code to fix the error

    Args:
        error_details: Dict with error information

    Returns:
        bool: True if Claude was spawned successfully
    """
    # Write detailed error context to temp file
    temp_dir = project_root / "logs"
    temp_file = temp_dir / "autofix_context.txt"

    context_content = f"""AUTO-FIX CONTEXT
================
Error Message: {error_details['error_message']}
File: {error_details['file_path'] or 'Unknown'}
Exception Type: {error_details['exception_type'] or 'Unknown'}
Log File: {error_details['log_file']}

ERROR CONTEXT (from logs):
{error_details['context']}

END OF CONTEXT
"""

    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(context_content)
    except Exception as e:
        print(f"Warning: Could not write context file: {e}")

    # Build simple, direct prompt (avoids CMD escaping issues)
    # The detailed context is in the file if Claude needs it
    prompt = (
        "CRITICAL ERROR DETECTED - AUTO-FIX MODE. "
        f"Error: {error_details['error_message']} in {error_details.get('file_path') or 'test_self_healing.py'}. "
        "Read logs/autofix_context.txt for full details. "
        "Find the bug, fix it, test the logic, and report when complete."
    )

    # Write batch file to handle prompt passing (Windows CMD escaping is hard)
    batch_file = temp_dir / "launch_autofix.bat"
    batch_content = f'''@echo off
cd /d {project_root}
claude "{prompt}"
pause
'''

    try:
        with open(batch_file, 'w', encoding='utf-8') as f:
            f.write(batch_content)
    except Exception as e:
        print(f"Warning: Could not write batch file: {e}")
        return False

    try:
        # Launch batch file in new window
        cmd = f'start cmd /k "{batch_file}"'

        print("\n" + "=" * 70)
        print("🤖 SPAWNING CLAUDE CODE FOR AUTO-FIX")
        print("=" * 70)
        print(f"Error: {error_details['error_message']}")
        print(f"File: {error_details['file_path'] or 'Unknown'}")
        print(f"Context saved to: {temp_file}")
        print(f"Launcher script: {batch_file}")
        print("\nOpening Claude Code in new window...")
        print("Claude will analyze and fix the error.")
        print("=" * 70)

        # Spawn Claude Code via batch file
        subprocess.Popen(cmd, shell=True)

        # Give it a moment to start
        import time
        time.sleep(2)

        return True

    except Exception as e:
        print(f"❌ Failed to spawn Claude Code: {e}")
        return False


def main():
    """Main entry point"""
    # Configure UTF-8 encoding
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        description='Log Analyzer with Auto-Fix (POC)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--hours', type=int, default=1,
                       help='Hours to look back for recent logs (default: 1 for POC)')
    parser.add_argument('--no-spawn', action='store_true',
                       help='Detect errors but do not spawn Claude Code')

    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("LOG ANALYZER WITH AUTO-FIX - PROOF OF CONCEPT")
    print("=" * 70)
    print(f"Scanning logs from past {args.hours} hour(s)...")
    print()

    # Initialize auto-fix manager
    manager = AutoFixManager()

    # Check system status
    status = manager.get_status()
    print(f"Auto-Fix Status: {'✅ Enabled' if status['enabled'] else '❌ Disabled'}")
    print(f"Circuit Breaker: {'⚠️  ACTIVE' if status['circuit_breaker_active'] else '✅ Inactive'}")
    print()

    # Find recent logs
    recent_logs = find_recent_logs(args.hours)
    if not recent_logs:
        print("No recent log files found")
        return 0

    print(f"Found {len(recent_logs)} recent log file(s):")
    for log_file in recent_logs:
        print(f"  - {log_file.name}")
    print()

    # Extract error details
    print(f"Scanning for errors (trigger: {get_trigger_phrase()})...")
    errors = extract_error_details(recent_logs)

    if not errors:
        print("\n" + "=" * 70)
        print("✅ NO ERRORS FOUND")
        print("=" * 70)
        print("All logs clean - no critical errors detected")
        return 0

    # Errors found!
    print(f"\n⚠️  Found {len(errors)} error(s)")
    print()

    # Process each error
    for idx, error in enumerate(errors, 1):
        print("=" * 70)
        print(f"ERROR #{idx}")
        print("=" * 70)
        print(f"Message: {error['error_message']}")
        print(f"File: {error['file_path'] or 'Unknown'}")
        print(f"Exception: {error['exception_type'] or 'Unknown'}")
        print(f"Log: {error['log_file']}")
        print()

        # Check if auto-fix should be attempted
        should_fix, reason = manager.should_attempt_fix(
            error['error_message'],
            error['file_path']
        )

        if not should_fix:
            print(f"⏭️  Skipping auto-fix: {reason}")
            print()
            continue

        if args.no_spawn:
            print("🔍 Would spawn Claude Code (--no-spawn flag active)")
            print()
            continue

        # Record fix attempt
        error_hash = manager.record_attempt(
            error['error_message'],
            error['file_path']
        )

        print(f"🎯 Attempting auto-fix (error hash: {error_hash})")
        print()

        # Spawn Claude Code
        success = spawn_claude_for_fix(error)

        if success:
            print()
            print("✅ Claude Code spawned successfully")
            print()
            print("⏳ Waiting for Claude to complete the fix...")
            print("   After Claude fixes the bug, run the test script again:")
            print("   python test_self_healing.py")
            print()

            # Note: In production, we would monitor Claude's output and call
            # manager.record_success(error_hash) or manager.record_failure(error_hash)
            # For POC, we'll do this manually

            return 0  # Stop after first fix attempt

        else:
            print("❌ Failed to spawn Claude Code")
            manager.record_failure(error_hash)
            print()

    print("=" * 70)


if __name__ == "__main__":
    sys.exit(main())
