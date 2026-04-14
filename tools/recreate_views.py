#!/usr/bin/env python3
"""
Quick script to recreate Morning Views database views with updated schema.
Run this once to add iv_percentile column to views.
"""

import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from morning_view.morning_views import MorningViews

def main():
    print("Recreating Morning Views database views...")

    # Create MorningViews instance - this will recreate views
    config_path = Path(__file__).parent.parent / 'morning_view' / 'config.json'
    mv = MorningViews(str(config_path))

    print("✓ Views recreated successfully")

    # Verify iv_percentile column exists in v_option_comparison
    conn = mv.conn
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(v_option_comparison)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'iv_percentile' in columns:
        print("✓ Verified: iv_percentile column exists in v_option_comparison")
    else:
        print("✗ ERROR: iv_percentile column NOT found in v_option_comparison")
        print(f"Available columns: {columns}")

    # Check v_oi_timing_context too
    cursor.execute("PRAGMA table_info(v_oi_timing_context)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'iv_percentile' in columns:
        print("✓ Verified: iv_percentile column exists in v_oi_timing_context")
    else:
        print("✗ ERROR: iv_percentile column NOT found in v_oi_timing_context")
        print(f"Available columns: {columns}")

    conn.close()
    print("\nViews ready. You can now restart the TUI.")

if __name__ == "__main__":
    main()
