"""
Controlled SQLite backup test: WAL mode vs DELETE mode timing.

Backs up data/datalake_backup.db (stable, no concurrent writers) to a
temporary target using SQLite's online backup API, measuring total
wall-clock time including post-close checkpoint.

Two runs: target in WAL mode (current behavior), target in DELETE mode (proposed fix).
Output is a single line per run with elapsed seconds and final file sizes.
"""

import os
import sqlite3
import sys
import time

SOURCE = r'E:\options_scanner\data\datalake_backup.db'
TARGET = r'E:\options_scanner\data\.sync_test_target.db'


def cleanup():
    for ext in ('', '-wal', '-shm', '-journal'):
        p = TARGET + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception as e:
                print('  cleanup failed for {}: {}'.format(p, e))


def run(mode):
    cleanup()
    src = sqlite3.connect(SOURCE)
    tgt = sqlite3.connect(TARGET)
    # Force target into requested journal mode BEFORE backup
    cur = tgt.execute('PRAGMA journal_mode={}'.format(mode))
    actual_mode = cur.fetchone()[0]
    cur.close()

    pages_copied = [0]
    total_pages = [0]

    def progress(status, remaining, total):
        pages_copied[0] = total - remaining
        total_pages[0] = total

    t0 = time.time()
    src.backup(tgt, pages=100, progress=progress)
    backup_elapsed = time.time() - t0

    # Capture file sizes BEFORE close (WAL still present in WAL mode)
    wal_before_close = 0
    wal_path = TARGET + '-wal'
    if os.path.exists(wal_path):
        wal_before_close = os.path.getsize(wal_path)
    db_before_close = os.path.getsize(TARGET)

    # Close target — in WAL mode this triggers checkpoint
    close_t0 = time.time()
    tgt.close()
    src.close()
    close_elapsed = time.time() - close_t0

    db_after_close = os.path.getsize(TARGET)
    wal_after_close = 0
    if os.path.exists(wal_path):
        wal_after_close = os.path.getsize(wal_path)

    total = backup_elapsed + close_elapsed

    print('mode={} actual={} backup_sec={:.1f} close_sec={:.1f} total_sec={:.1f} pages={} db_pre={:.2f}GB wal_pre={:.2f}GB db_post={:.2f}GB wal_post={:.2f}GB'.format(
        mode,
        actual_mode,
        backup_elapsed,
        close_elapsed,
        total,
        total_pages[0],
        db_before_close / 1e9,
        wal_before_close / 1e9,
        db_after_close / 1e9,
        wal_after_close / 1e9,
    ), flush=True)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'wal'
    run(mode)
    cleanup()
