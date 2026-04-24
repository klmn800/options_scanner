"""
Symbol Renaming (renaming.py)
------------------------------
Renames a ticker symbol across the entire database ecosystem.
Dynamically discovers all tables with a 'symbol' column so new
tables are picked up automatically without code changes.

Databases covered: datalake.db, performance.db, datalake_query.db,
and the symbol's sector archive.

PRD 0013 — Symbol Lifecycle Management
"""

import os
import sqlite3
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.timezone_utils import now_eastern
from tools.lifecycle.audit import log_lifecycle_event
from tools.lifecycle.ui import prompt_yes_no


# Columns that reference ticker symbols but aren't named exactly 'symbol'.
# Auto-discovered alongside 'symbol' columns in every table.
_EXTRA_SYMBOL_COLUMNS = {'primary_symbol', 'peer_symbol'}


def _discover_symbol_columns(conn):
    """Find all tables with columns that reference ticker symbols.

    Auto-discovers:
      - Any column named exactly 'symbol'
      - Known alias columns (primary_symbol, peer_symbol)

    Returns:
        list of (table_name, column_name) tuples
    """
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    results = []
    for (table_name,) in tables:
        cols = conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
        for col in cols:
            col_name = col[1]
            if col_name == 'symbol' or col_name in _EXTRA_SYMBOL_COLUMNS:
                results.append((table_name, col_name))
    return results


def _update_database(db_path, old_symbol, new_symbol, db_label):
    """Update all symbol references in a single database file.

    Args:
        db_path: Path to the .db file
        old_symbol: Current ticker
        new_symbol: New ticker
        db_label: Display name for console output

    Returns:
        dict of {'table.column': rows_updated} for tables that had matches
    """
    results = {}

    if not os.path.exists(db_path):
        return results

    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            targets = _discover_symbol_columns(conn)

            for table_name, col_name in targets:
                cursor = conn.execute(
                    f"UPDATE [{table_name}] SET [{col_name}] = ? WHERE [{col_name}] = ?",
                    (new_symbol, old_symbol)
                )
                if cursor.rowcount > 0:
                    results[f"{table_name}.{col_name}"] = cursor.rowcount

            conn.commit()
    except Exception as e:
        print(f"  ERROR updating {db_label}: {e}")

    return results


def rename_symbol(old_symbol, new_symbol, db_path):
    """Rename a symbol across the entire database ecosystem.

    Steps:
      1. Validate old symbol exists, warn if new symbol already exists
      2. Show current info and prompt for confirmation
      3. Dynamically discover and UPDATE all tables with 'symbol' columns
         in datalake.db, performance.db, query DB, and sector archive
      4. Append rename note to symbol_metadata
      5. Log lifecycle event

    Args:
        old_symbol: Current ticker (already uppercased)
        new_symbol: New ticker (already uppercased)
        db_path: Path to datalake.db
    """
    # --- Validation ---
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row

        old_row = conn.execute(
            'SELECT * FROM symbol_metadata WHERE symbol = ?', (old_symbol,)
        ).fetchone()

        if not old_row:
            print(f'\n  {old_symbol} not found in symbol_metadata.')
            return

        new_row = conn.execute(
            'SELECT symbol, universe_tier, sector, company_name '
            'FROM symbol_metadata WHERE symbol = ?',
            (new_symbol,)
        ).fetchone()

        if new_row:
            print(f'\n  WARNING: {new_symbol} already exists in symbol_metadata!')
            print(f'    Company: {new_row["company_name"] or "N/A"}')
            print(f'    Tier:    {new_row["universe_tier"]}')
            print(f'    Sector:  {new_row["sector"] or "N/A"}')
            if not prompt_yes_no(
                f'  {new_symbol} already exists. Continue anyway?', default='n'
            ):
                print('  Cancelled.')
                return

    # --- Show info ---
    name = old_row['company_name'] or old_symbol
    current_tier = old_row['universe_tier']
    protected = old_row['protected_reason']
    archive_db = old_row['archive_db']

    print(f'\n  Rename: {old_symbol} -> {new_symbol}')
    print(f'  Company:   {name}')
    print(f'  Tier:      {current_tier}')
    print(f'  Sector:    {old_row["sector"] or "N/A"}')
    print(f'  Industry:  {old_row["industry"] or "N/A"}')
    if protected:
        print(f'  Protected: {protected}')
    if archive_db:
        print(f'  Archive:   {archive_db}')

    if not prompt_yes_no(f'  Proceed with rename {old_symbol} -> {new_symbol}?'):
        print('  Cancelled.')
        return

    # --- Build database list ---
    data_dir = os.path.dirname(db_path)
    databases = [
        ('datalake.db', db_path),
    ]

    perf_path = os.path.join(data_dir, 'performance.db')
    if os.path.exists(perf_path):
        databases.append(('performance.db', perf_path))

    # Skip datalake_query.db — it's a file-level copy updated by daily sync

    if archive_db:
        archive_file = archive_db if archive_db.endswith('.db') else f'{archive_db}.db'
        archive_path = os.path.join(data_dir, 'sector_archive', archive_file)
        if os.path.exists(archive_path):
            databases.append((f'archive:{archive_db}', archive_path))
        else:
            print(f'  WARNING: Archive {archive_db} not found, skipping')

    # --- Update all databases ---
    total_updated = 0
    all_results = {}

    for db_label, db_file in databases:
        print(f'\n  Updating {db_label}...')
        results = _update_database(db_file, old_symbol, new_symbol, db_label)

        if results:
            for key, count in sorted(results.items()):
                print(f'    {key}: {count:,} rows')
                total_updated += count
            all_results[db_label] = results
        else:
            print(f'    (no matching rows)')

    # --- Append rename note to symbol_metadata ---
    today = now_eastern().strftime('%Y-%m-%d')
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.execute(
            "UPDATE symbol_metadata SET "
            "notes = COALESCE(notes || '; ', '') || ? "
            "WHERE symbol = ?",
            (f'Renamed from {old_symbol} on {today}', new_symbol)
        )
        conn.commit()

    # --- Log lifecycle event ---
    event_meta = {
        'old_symbol': old_symbol,
        'new_symbol': new_symbol,
        'total_rows_updated': total_updated,
        'databases_updated': list(all_results.keys()),
    }

    log_lifecycle_event(
        db_path=db_path,
        symbol=new_symbol,
        event_type='renamed',
        tier=current_tier,
        reason=f'Renamed from {old_symbol}',
        operator='human',
        metadata_dict=event_meta
    )

    # --- Summary ---
    print(f'\n  Done: {old_symbol} -> {new_symbol}')
    print(f'  {total_updated:,} total rows updated across {len(databases)} databases')
    print(f'  Lifecycle event logged')
