#!/usr/bin/env python3
"""
Symbol Universe Repository (symbols_klmn800.py)
------------------------------------------------
Database-backed symbol universe for the KLMN options scanner.

All symbol lists are sourced from `symbol_metadata` in datalake.db.
The `get_specialty_list()` function is the sole entry point for all
consumers (Option Pipeline, Flow Monitor, Earnings Intel, etc.).

To add or remove symbols, use the lifecycle CLI:
    python tools/symbol_lifecycle.py --add ACME
    python tools/symbol_lifecycle.py --offboard ACME
    python tools/symbol_lifecycle.py --restore ACME
    python tools/symbol_lifecycle.py --list

Never edit this file to change the symbol universe.

History:
    2025-06-07  Created with hardcoded Python list literals
    2026-03-16  Reorganized: source-based -> purpose-based grouping
    2026-04-16  PRD 0013: DB migration, get_specialty_list() queries DB
    2026-04-17  PRD 0013 Task 2.7: Removed Python list literals entirely.
                DB (symbol_metadata.universe_tier) is sole source of truth.
"""


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_specialty_list(list_name, db_path=None):
    """
    Get specialty symbol list by name from symbol_metadata database.

    Args:
        list_name (str): Name of the specialty list to retrieve
        db_path (str, optional): Path to datalake.db. Auto-resolves if None.

    Returns:
        list: Sorted list of symbols for the specified specialty list

    Raises:
        ValueError: If list_name is not recognized
        RuntimeError: If database query fails (no fallback)

    Available specialty lists:
        - 'klmn_800': Full ~820-symbol universe (OP, EI, metadata, etc.)
        - 'fm_scan': FM scan universe (~388 symbols scanned by Flow Monitor)
        - 'fm_cherry_picks': Cherry-picked symbols kept in FM for volume/thematic reasons
        - 'daily_only': Symbols tracked by OP/EI but not FM
        - 'klmn_adr': ADR / foreign-listed symbols with US options
        - 'airline_play': Airline industry tracking symbols
        - 'etf': ETF symbols for market/sector exposure
    """
    import os
    import sqlite3

    # DB query mapping: list_name -> (SQL WHERE clause, params)
    _DB_QUERIES = {
        'klmn_800':       ("WHERE universe_tier IN ('fm_universe', 'daily_only')", []),
        'fm_scan':        ("WHERE universe_tier = 'fm_universe'", []),
        'daily_only':     ("WHERE universe_tier = 'daily_only'", []),
        'klmn_adr':       ("WHERE protected_reason = 'adr'", []),
        'airline_play':   ("WHERE protected_reason = 'airline'", []),
        'fm_cherry_picks':("WHERE protected_reason = 'cherry_pick'", []),
        'etf':            ("WHERE is_etf = 1", []),
    }

    list_key = list_name.lower()
    if list_key not in _DB_QUERIES:
        available = ', '.join(_DB_QUERIES.keys())
        raise ValueError(f"Unknown specialty list '{list_name}'. Available: {available}")

    if db_path is None:
        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(_project_root, 'data', 'datalake.db')

    where_clause, params = _DB_QUERIES[list_key]
    with sqlite3.connect(db_path, timeout=10.0) as conn:
        rows = conn.execute(
            f"SELECT symbol FROM symbol_metadata {where_clause} ORDER BY symbol",
            params
        ).fetchall()
        return [r[0] for r in rows]


def get_specialty_info():
    """
    Get information about available specialty symbol lists.

    Returns:
        dict: Dictionary with list names as keys and symbol counts as values
    """
    return {name: len(get_specialty_list(name)) for name in get_available_specialty_lists()}


def get_available_specialty_lists():
    """
    Get list of available specialty list names.

    Returns:
        list: List of available specialty list names
    """
    return ['klmn_800', 'fm_scan', 'fm_cherry_picks', 'daily_only', 'klmn_adr', 'airline_play', 'etf']


def validate_specialty_symbols(symbols, list_name='klmn_800'):
    """
    Validate that symbols exist in the specified specialty list.

    Args:
        symbols (list): List of symbols to validate
        list_name (str): Specialty list to validate against

    Returns:
        tuple: (valid_symbols, invalid_symbols)
    """
    specialty_symbols = set(get_specialty_list(list_name))
    symbols_set = set(symbols)

    valid_symbols = list(symbols_set.intersection(specialty_symbols))
    invalid_symbols = list(symbols_set.difference(specialty_symbols))

    return valid_symbols, invalid_symbols


def get_klmn_800_breakdown():
    """
    Get breakdown of KLMN 800 components.

    Returns:
        dict: Breakdown showing FM Universe vs Daily Only
    """
    fm_count = len(get_specialty_list('fm_scan'))
    daily_count = len(get_specialty_list('daily_only'))
    return {
        'total_symbols': len(get_specialty_list('klmn_800')),
        'fm_universe': fm_count,
        'daily_only': daily_count,
        'etf_count': len(get_specialty_list('etf')),
        'airline_count': len(get_specialty_list('airline_play')),
        'adr_count': len(get_specialty_list('klmn_adr')),
        'cherry_pick_count': len(get_specialty_list('fm_cherry_picks')),
        'composition': f"{fm_count} FM Universe + {daily_count} Daily Only",
    }


def get_symbol_count(list_name):
    """
    Get count of symbols in specified specialty list.

    Args:
        list_name (str): Name of the specialty list

    Returns:
        int: Number of symbols in the specialty list
    """
    return len(get_specialty_list(list_name))


def is_symbol_in_klmn_800(symbol):
    """
    Check if symbol is in the KLMN 800 universe.

    Args:
        symbol (str): Symbol to check

    Returns:
        bool: True if symbol is in KLMN 800, False otherwise
    """
    return symbol.upper() in get_specialty_list('klmn_800')


# Usage examples for testing
if __name__ == "__main__":
    print("Symbol Universe Repository (DB-backed)")
    print("=" * 60)

    # Show specialty list information
    info = get_specialty_info()
    print("Available specialty lists:")
    for list_name, count in info.items():
        status = "[OK]" if count > 0 else "[empty]"
        print(f"  {list_name}: {count:,} symbols {status}")

    # Show breakdown
    breakdown = get_klmn_800_breakdown()
    print(f"\nUniverse Breakdown:")
    print(f"  Total: {breakdown['total_symbols']:,} symbols")
    print(f"  Composition: {breakdown['composition']}")
    print(f"  ETFs: {breakdown['etf_count']}")
    print(f"  Airlines: {breakdown['airline_count']}")
    print(f"  ADRs: {breakdown['adr_count']}")
    print(f"  Cherry Picks: {breakdown['cherry_pick_count']}")

    # Verify no overlap and no missing
    fm_set = set(get_specialty_list('fm_scan'))
    daily_set = set(get_specialty_list('daily_only'))
    full_set = set(get_specialty_list('klmn_800'))
    overlap = fm_set & daily_set
    print(f"\nIntegrity Checks:")
    print(f"  FM + Daily Only = {len(fm_set) + len(daily_set)} (should equal {len(full_set)})")
    print(f"  Overlap: {len(overlap)} (should be 0)")
    if overlap:
        print(f"  WARNING - Overlapping symbols: {sorted(overlap)}")

    # Verify protected groups are in FM_UNIVERSE
    jets_in_fm = 'JETS' in fm_set
    airline_in_fm = set(get_specialty_list('airline_play')) - fm_set
    adr_in_fm = set(get_specialty_list('klmn_adr')) - fm_set
    cherry_in_fm = set(get_specialty_list('fm_cherry_picks')) - fm_set
    print(f"  JETS in FM: {jets_in_fm} (should be True)")
    print(f"  Airlines missing from FM: {len(airline_in_fm)} (should be 0)")
    print(f"  ADRs missing from FM: {len(adr_in_fm)} (should be 0)")
    print(f"  Cherry picks missing from FM: {len(cherry_in_fm)} (should be 0)")
