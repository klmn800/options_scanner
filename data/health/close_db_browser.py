#!/usr/bin/env python3
"""
Close DB Browser for SQLite (close_db_browser.py)
--------------------------------------------------
Automatically closes DB Browser for SQLite to release database locks.

Used by quick-sync when database is locked. Sync is more important than
keeping DB Browser open - user can reopen it after sync completes.

Returns:
    0 if DB Browser was found and closed
    1 if DB Browser was not running
    2 if failed to close (permissions/access denied)
"""

import sys
import os
import time
import subprocess

# PERMANENT FIX: Force UTF-8 encoding for Windows console
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

def close_db_browser():
    """Close DB Browser for SQLite if running

    Returns:
        int: Exit code (0=closed, 1=not running, 2=failed)
    """
    try:
        # Check if DB Browser is running
        tasklist_result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq DB Browser for SQLite.exe'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if 'DB Browser for SQLite.exe' not in tasklist_result.stdout:
            print("DB Browser for SQLite is not running")
            return 1

        print("Found DB Browser for SQLite running - closing to release database lock...")

        # Try graceful close first (sends WM_CLOSE message)
        close_result = subprocess.run(
            ['taskkill', '/IM', 'DB Browser for SQLite.exe'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        if close_result.returncode == 0:
            # Verify the process actually closed (taskkill can return 0 even if dialog blocked it)
            time.sleep(1)  # Brief pause for process to terminate

            verify_result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq DB Browser for SQLite.exe'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            if 'DB Browser for SQLite.exe' in verify_result.stdout:
                print("⚠️ DB Browser is still running (likely unsaved changes dialog)")
                print("   Please save or discard changes, then sync will retry")
                return 2  # Different error code for "blocked by dialog"
            else:
                print("✅ DB Browser for SQLite closed successfully")
                return 0
        else:
            # Graceful close failed, try force close
            print("⚠️ Graceful close failed, attempting force close...")
            force_result = subprocess.run(
                ['taskkill', '/F', '/IM', 'DB Browser for SQLite.exe'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            if force_result.returncode == 0:
                print("✅ DB Browser for SQLite force-closed successfully")
                return 0
            else:
                print("❌ Failed to close DB Browser for SQLite")
                print("   Error: {}".format(force_result.stderr))
                return 2

    except Exception as e:
        print("❌ Error closing DB Browser: {}".format(e))
        return 2

if __name__ == "__main__":
    exit_code = close_db_browser()
    sys.exit(exit_code)
