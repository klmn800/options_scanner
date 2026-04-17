#!/usr/bin/env python3
"""
One-Time Migration: Populate Universe Columns in symbol_metadata
-----------------------------------------------------------------
Reads all lists from core/symbols_klmn800.py and populates the new
PRD 0013 columns: universe_tier, protected_reason, is_etf, tier_changed_date, notes.

Run once. Idempotent (safe to re-run — overwrites previous values).

Usage:
    python data/health/migrate_universe_to_db.py --dry-run   # Preview only
    python data/health/migrate_universe_to_db.py              # Execute

PRD 0013 — Symbol Lifecycle Management
"""

import os
import sys
import sqlite3
import argparse
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

sys.stdout.reconfigure(encoding='utf-8')

from core.symbols_klmn800 import (
    FM_UNIVERSE, DAILY_ONLY, KLMN_800_SYMBOLS,
    AIRLINE_PLAY_SYMBOLS, ETF_SYMBOLS, KLMN_ADR_COMPONENT, FM_CHERRY_PICKS,
)


# Cherry pick notes — preserved from the original comment in symbols_klmn800.py
CHERRY_PICK_NOTES = {
    'DIS': 'High daily options volume',
    'ET': 'High daily options volume',
    'MO': 'High daily options volume',
    'ABT': 'High daily options volume',
    'S': 'High daily options volume',
    'AKAM': 'High daily options volume',
    'PENN': 'Thematic: gambling',
    'ELF': 'Thematic: beauty',
    'DOCU': 'Thematic: SaaS',
    'ALLY': 'Thematic: fintech',
    'AGNC': 'Cheap + very liquid options',
    'NLY': 'Cheap + very liquid options',
    'MPT': 'Cheap + very liquid options',
    'CC': 'Cheap + very liquid options',
    'DNN': 'Nuclear energy / defense crossover',
    'BWXT': 'Nuclear energy / defense crossover',
}


def build_migration_plan(db_path):
    """Build a plan of what changes to make for each symbol.

    Returns:
        list[dict]: One entry per symbol with all column values to set.
    """
    fm_set = set(FM_UNIVERSE)
    daily_set = set(DAILY_ONLY)
    active_set = set(KLMN_800_SYMBOLS)
    adr_set = set(KLMN_ADR_COMPONENT)
    airline_set = set(AIRLINE_PLAY_SYMBOLS)
    cherry_set = set(FM_CHERRY_PICKS)
    etf_set = set(ETF_SYMBOLS)

    today = datetime.now().strftime('%Y-%m-%d')

    # Get all symbols currently in symbol_metadata
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT symbol, is_etf FROM symbol_metadata')
        db_symbols = {row[0]: row[1] for row in cursor.fetchall()}

    plan = []
    for symbol in sorted(db_symbols.keys()):
        # Determine universe_tier
        if symbol in fm_set:
            tier = 'fm_universe'
        elif symbol in daily_set:
            tier = 'daily_only'
        elif symbol not in active_set:
            tier = 'removed'
        else:
            tier = 'unknown'  # shouldn't happen

        # Determine protected_reason (priority: airline > adr > cherry_pick)
        protected_reason = None
        if symbol in airline_set:
            protected_reason = 'airline'
        elif symbol in adr_set:
            protected_reason = 'adr'
        elif symbol in cherry_set:
            protected_reason = 'cherry_pick'

        # Determine is_etf — trust existing DB value (from metadata collector's detect_etf),
        # but ensure ETF_SYMBOLS list members are all marked
        current_is_etf = db_symbols[symbol]
        is_etf = 1 if (symbol in etf_set or current_is_etf) else 0
        # JETS is in AIRLINE_PLAY_SYMBOLS but also an ETF
        if symbol == 'JETS':
            is_etf = 1

        # Build notes
        notes = None
        if symbol in cherry_set:
            notes = CHERRY_PICK_NOTES.get(symbol, 'Cherry pick (2026-03-16)')
        if symbol not in active_set:
            notes = 'Ghost symbol: in metadata but not in any active list at migration time'

        plan.append({
            'symbol': symbol,
            'universe_tier': tier,
            'protected_reason': protected_reason,
            'is_etf': is_etf,
            'tier_changed_date': today,
            'notes': notes,
        })

    return plan


def display_plan(plan):
    """Print a summary of the migration plan."""
    from collections import Counter

    tier_counts = Counter(p['universe_tier'] for p in plan)
    protection_counts = Counter(p['protected_reason'] for p in plan if p['protected_reason'])
    etf_count = sum(1 for p in plan if p['is_etf'])
    notes_count = sum(1 for p in plan if p['notes'])

    print("\nMigration Plan Summary")
    print("=" * 50)
    print(f"Total symbols to update: {len(plan)}")
    print()
    print("Universe Tier:")
    for tier, count in sorted(tier_counts.items()):
        print(f"  {tier:20s} {count}")
    print()
    print("Protected Reason:")
    for reason, count in sorted(protection_counts.items()):
        print(f"  {reason:20s} {count}")
    print(f"  {'(none)':20s} {sum(1 for p in plan if not p['protected_reason'])}")
    print()
    print(f"ETF flag set: {etf_count}")
    print(f"Notes set: {notes_count}")

    # Show removed/ghost symbols
    removed = [p for p in plan if p['universe_tier'] == 'removed']
    if removed:
        print(f"\nGhost symbols (will be marked 'removed'):")
        for p in removed:
            print(f"  {p['symbol']:8s} — {p['notes']}")


def execute_migration(db_path, plan):
    """Execute the migration plan against the database."""
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()
        updated = 0
        for p in plan:
            cursor.execute('''
                UPDATE symbol_metadata
                SET universe_tier = ?,
                    protected_reason = ?,
                    is_etf = ?,
                    tier_changed_date = ?,
                    notes = ?
                WHERE symbol = ?
            ''', (
                p['universe_tier'],
                p['protected_reason'],
                p['is_etf'],
                p['tier_changed_date'],
                p['notes'],
                p['symbol'],
            ))
            if cursor.rowcount > 0:
                updated += 1
        conn.commit()
    return updated


def verify_migration(db_path):
    """Run parity checks after migration."""
    print("\nVerification Queries")
    print("=" * 50)

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()

        # Tier counts
        cursor.execute('SELECT universe_tier, COUNT(*) FROM symbol_metadata GROUP BY universe_tier ORDER BY universe_tier')
        print("Universe tier counts:")
        for row in cursor.fetchall():
            print(f"  {str(row[0]):20s} {row[1]}")

        # ETF count
        cursor.execute('SELECT COUNT(*) FROM symbol_metadata WHERE is_etf = 1')
        print(f"\nis_etf=1 count: {cursor.fetchone()[0]}")

        # ADR count
        cursor.execute("SELECT COUNT(*) FROM symbol_metadata WHERE protected_reason = 'adr'")
        print(f"protected_reason='adr' count: {cursor.fetchone()[0]}")

        # Airline count
        cursor.execute("SELECT COUNT(*) FROM symbol_metadata WHERE protected_reason = 'airline'")
        print(f"protected_reason='airline' count: {cursor.fetchone()[0]}")

        # Cherry pick count
        cursor.execute("SELECT COUNT(*) FROM symbol_metadata WHERE protected_reason = 'cherry_pick'")
        print(f"protected_reason='cherry_pick' count: {cursor.fetchone()[0]}")

        # NULL tier check
        cursor.execute('SELECT COUNT(*) FROM symbol_metadata WHERE universe_tier IS NULL')
        null_count = cursor.fetchone()[0]
        print(f"\nNULL universe_tier: {null_count} (should be 0)")

        # Cross-check: Python list counts vs DB
        from core.symbols_klmn800 import FM_UNIVERSE, DAILY_ONLY, ETF_SYMBOLS, KLMN_ADR_COMPONENT, AIRLINE_PLAY_SYMBOLS
        cursor.execute("SELECT COUNT(*) FROM symbol_metadata WHERE universe_tier = 'fm_universe'")
        db_fm = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM symbol_metadata WHERE universe_tier = 'daily_only'")
        db_daily = cursor.fetchone()[0]

        print(f"\nParity checks:")
        print(f"  FM_UNIVERSE:  Python={len(FM_UNIVERSE):4d}  DB={db_fm:4d}  {'MATCH' if len(FM_UNIVERSE) == db_fm else 'MISMATCH'}")
        print(f"  DAILY_ONLY:   Python={len(DAILY_ONLY):4d}  DB={db_daily:4d}  {'MATCH' if len(DAILY_ONLY) == db_daily else 'MISMATCH'}")


def main():
    parser = argparse.ArgumentParser(description='Migrate symbol universe to symbol_metadata columns')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    args = parser.parse_args()

    db_path = os.path.join(project_root, 'data', 'datalake.db')

    print("PRD 0013 — Universe Migration to symbol_metadata")
    print("=" * 50)
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")

    plan = build_migration_plan(db_path)
    display_plan(plan)

    if args.dry_run:
        print("\n[DRY RUN] No changes written.")
        return 0

    print(f"\nExecuting migration...")
    updated = execute_migration(db_path, plan)
    print(f"Updated {updated} rows.")

    verify_migration(db_path)

    return 0


if __name__ == '__main__':
    exit(main())
