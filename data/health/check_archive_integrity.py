#!/usr/bin/env python3
"""
Check integrity of all sector archive databases.

Runs PRAGMA integrity_check on each archive file.
Reports OK or lists corruption details per file.
"""

import os
import sys
import sqlite3
import time

ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sector_archive')


def check_archive(db_path):
    """Run full integrity_check on a single archive. Returns (status, details, duration_s)."""
    db_name = os.path.basename(db_path)
    size_gb = os.path.getsize(db_path) / (1024 ** 3)
    print(f"  Checking {db_name} ({size_gb:.1f} GB) ...", end=" ", flush=True)

    start = time.time()
    try:
        conn = sqlite3.connect(db_path, timeout=60.0)
        conn.execute("PRAGMA busy_timeout = 60000")
        results = conn.execute("PRAGMA integrity_check").fetchall()
        conn.close()
    except Exception as e:
        duration = time.time() - start
        print(f"ERROR ({duration:.0f}s)")
        return "ERROR", str(e), duration

    duration = time.time() - start

    if len(results) == 1 and results[0][0] == "ok":
        print(f"OK ({duration:.0f}s)")
        return "OK", None, duration
    else:
        # Collect corruption details (limit output to first 20 lines)
        details = [r[0] for r in results[:20]]
        if len(results) > 20:
            details.append(f"... and {len(results) - 20} more issues")
        print(f"CORRUPT ({len(results)} issues, {duration:.0f}s)")
        return "CORRUPT", details, duration


def main():
    print(f"Sector Archive Integrity Check")
    print(f"Archive directory: {ARCHIVE_DIR}")
    print()

    # Find all .db files, skip -wal and -shm
    db_files = sorted([
        os.path.join(ARCHIVE_DIR, f)
        for f in os.listdir(ARCHIVE_DIR)
        if f.endswith('.db') and not f.endswith(('-wal', '-shm', '-journal'))
    ])

    print(f"Found {len(db_files)} archive databases\n")

    results = {}
    total_start = time.time()

    for db_path in db_files:
        name = os.path.basename(db_path)
        status, details, duration = check_archive(db_path)
        results[name] = (status, details, duration)

    total_duration = time.time() - total_start

    # Summary
    print(f"\n{'=' * 60}")
    print(f"SUMMARY (total: {total_duration:.0f}s / {total_duration/60:.1f} min)")
    print(f"{'=' * 60}")

    ok_count = sum(1 for s, _, _ in results.values() if s == "OK")
    corrupt_count = sum(1 for s, _, _ in results.values() if s == "CORRUPT")
    error_count = sum(1 for s, _, _ in results.values() if s == "ERROR")

    print(f"  OK:      {ok_count}")
    print(f"  CORRUPT: {corrupt_count}")
    print(f"  ERROR:   {error_count}")

    if corrupt_count > 0 or error_count > 0:
        print(f"\nProblematic archives:")
        for name, (status, details, duration) in sorted(results.items()):
            if status != "OK":
                print(f"\n  {name} [{status}]:")
                if details and isinstance(details, list):
                    for line in details:
                        print(f"    {line}")
                elif details:
                    print(f"    {details}")


if __name__ == "__main__":
    main()
