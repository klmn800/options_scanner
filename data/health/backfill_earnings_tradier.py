"""Backfill missing earnings_events and earnings_moves using Tradier Corporate Calendars API.

Fetches historical earnings report dates from Tradier's /beta/markets/fundamentals/calendars
endpoint, inserts missing events, infers BMO/AMC timing, and computes price moves.

Tradier provides actual report dates (not fiscal quarter ends), supports batching 50+ symbols
per call, and has ~18 years of history. No EPS data --just dates and fiscal quarter info.

Usage:
    python data/health/backfill_earnings_tradier.py                    # Full backfill
    python data/health/backfill_earnings_tradier.py --dry-run          # Preview gaps
    python data/health/backfill_earnings_tradier.py --symbol AAPL      # Single symbol
    python data/health/backfill_earnings_tradier.py --limit 50         # First N symbols
    python data/health/backfill_earnings_tradier.py --moves-only       # Skip fetch, just compute moves
    python data/health/backfill_earnings_tradier.py --skip-timing      # Skip BMO/AMC inference
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
PRODUCTION_DB = os.path.join(PROJECT_ROOT, 'data', 'datalake.db')
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config.json')

sys.path.insert(0, PROJECT_ROOT)

# Tradier endpoint
TRADIER_CALENDARS_URL = 'https://api.tradier.com/beta/markets/fundamentals/calendars'

# Date range for backfill (covers full 2025 + Q1 2026 = 5 quarters)
BACKFILL_FROM = '2025-01-01'
BACKFILL_TO = '2026-03-31'

# Tradier event_type → fiscal quarter
EVENT_TYPE_MAP = {7: 1, 8: 2, 9: 3, 10: 4}
EARNINGS_EVENT_TYPES = {7, 8, 9, 10}

# Batch size for Tradier API calls
DEFAULT_BATCH_SIZE = 50


def load_config():
    """Load config.json and return Tradier API key."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return config['tradier']['api_key']


def get_symbols(conn, single_symbol=None):
    """Get non-ETF symbols from symbol_metadata."""
    if single_symbol:
        return [single_symbol.upper()]
    cursor = conn.execute("""
        SELECT DISTINCT symbol FROM symbol_metadata
        WHERE is_etf = 0 OR is_etf IS NULL
        ORDER BY symbol
    """)
    return [row[0] for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Phase 1: Fetch from Tradier
# ---------------------------------------------------------------------------

def fetch_tradier_calendars(token, symbols_batch):
    """Fetch corporate calendars for a batch of symbols from Tradier.

    Returns raw JSON response (list of items, one per symbol).
    Retries up to 3 times with backoff.
    """
    import requests

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    params = {'symbols': ','.join(symbols_batch)}

    for attempt in range(3):
        try:
            response = requests.get(
                TRADIER_CALENDARS_URL, headers=headers,
                params=params, timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return data
                return []
            elif response.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"    Tradier API {response.status_code} for batch of {len(symbols_batch)}")
                if attempt < 2:
                    time.sleep(1 * (2 ** attempt))
        except Exception as e:
            print(f"    Request error: {e}")
            if attempt < 2:
                time.sleep(2 * (2 ** attempt))

    return []


def parse_calendar_response(items, target_from, target_to):
    """Parse Tradier calendar response into earnings event dicts.

    Returns list of {symbol, earnings_date, fiscal_year, fiscal_quarter, event_status}.
    """
    events = []
    for item in items:
        symbol = item.get('request', '')
        if not symbol:
            continue

        results = item.get('results', [])
        if not results:
            continue

        for result in results:
            if not isinstance(result, dict):
                continue
            tables = result.get('tables', {})
            if not tables:
                continue
            calendars = tables.get('corporate_calendars')
            if not calendars:
                continue

            for cal in calendars:
                event_type = cal.get('event_type')
                if event_type not in EARNINGS_EVENT_TYPES:
                    continue

                earnings_date = str(cal.get('begin_date_time', ''))[:10]
                if not earnings_date or earnings_date < target_from or earnings_date > target_to:
                    continue

                # Only take Confirmed events (historical, not estimates)
                status = cal.get('event_status', '')
                if status != 'Confirmed':
                    continue

                events.append({
                    'symbol': symbol,
                    'earnings_date': earnings_date,
                    'fiscal_year': cal.get('event_fiscal_year'),
                    'fiscal_quarter': EVENT_TYPE_MAP.get(event_type),
                    'event_status': status,
                })

    return events


def phase1_fetch_events(token, symbols, batch_size):
    """Fetch earnings events from Tradier for all symbols.

    Returns (events_list, stats_dict).
    """
    all_events = []
    no_data_symbols = []
    total_api_calls = 0

    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

    for batch_idx, batch in enumerate(batches, 1):
        items = fetch_tradier_calendars(token, batch)
        total_api_calls += 1

        if items:
            events = parse_calendar_response(items, BACKFILL_FROM, BACKFILL_TO)
            symbols_with_data = {e['symbol'] for e in events}
            no_data = [s for s in batch if s not in symbols_with_data]
            no_data_symbols.extend(no_data)
            all_events.extend(events)
        else:
            no_data_symbols.extend(batch)

        processed = min(batch_idx * batch_size, len(symbols))
        print(f"  [{processed}/{len(symbols)}] Batch {batch_idx}/{len(batches)} "
              f"-- {len(events) if items else 0} events found")

        # Small delay between batches
        if batch_idx < len(batches):
            time.sleep(0.5)

    stats = {
        'total_events': len(all_events),
        'symbols_with_data': len(set(e['symbol'] for e in all_events)),
        'no_data_symbols': len(no_data_symbols),
        'api_calls': total_api_calls,
    }

    return all_events, stats


# ---------------------------------------------------------------------------
# Phase 2: Upsert events into earnings_events
# ---------------------------------------------------------------------------

def phase2_upsert_events(conn, events, dry_run):
    """Insert new events and update existing ones with fiscal info.

    Returns stats dict: {inserted, updated, skipped}.
    """
    inserted = 0
    updated = 0
    skipped = 0

    for event in events:
        symbol = event['symbol']
        earnings_date = event['earnings_date']
        fiscal_year = event['fiscal_year']
        fiscal_quarter = event['fiscal_quarter']

        # Check if exists
        cursor = conn.execute(
            "SELECT event_id, fiscal_year FROM earnings_events WHERE symbol = ? AND earnings_date = ?",
            (symbol, earnings_date)
        )
        existing = cursor.fetchone()

        if existing is None:
            # New event --INSERT
            if not dry_run:
                conn.execute("""
                    INSERT OR IGNORE INTO earnings_events
                    (symbol, earnings_date, fiscal_year, fiscal_quarter,
                     source, is_backfilled, created_at)
                    VALUES (?, ?, ?, ?, 'tradier_calendars', 1, CURRENT_TIMESTAMP)
                """, (symbol, earnings_date, fiscal_year, fiscal_quarter))
            inserted += 1
        elif existing[1] is None:
            # Exists but missing fiscal info --UPDATE
            if not dry_run:
                conn.execute("""
                    UPDATE earnings_events
                    SET fiscal_year = ?, fiscal_quarter = ?
                    WHERE symbol = ? AND earnings_date = ?
                    AND fiscal_year IS NULL
                """, (fiscal_year, fiscal_quarter, symbol, earnings_date))
            updated += 1
        else:
            skipped += 1

    if not dry_run:
        conn.commit()

    return {'inserted': inserted, 'updated': updated, 'skipped': skipped}


# ---------------------------------------------------------------------------
# Phase 3: BMO/AMC timing inference
# ---------------------------------------------------------------------------

def get_symbol_typical_timing(conn, symbol):
    """Get the most common earnings_time for a symbol from its history.

    Returns 'bmo', 'amc', or None. Uses mode from last 8 quarters
    to filter out noise.
    """
    cursor = conn.execute("""
        SELECT earnings_time, COUNT(*) as cnt
        FROM earnings_events
        WHERE symbol = ?
          AND earnings_time IN ('bmo', 'amc')
        GROUP BY earnings_time
        ORDER BY cnt DESC
        LIMIT 1
    """, (symbol,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None


def infer_bmo_amc_from_prices(conn, symbol, earnings_date):
    """Infer BMO/AMC from price gap analysis as fallback.

    Returns 'bmo', 'amc', or None (uncertain).
    """
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row

    # T-1 close
    cursor.execute("""
        SELECT close_price FROM historical_prices
        WHERE symbol = ? AND trade_date < ?
        ORDER BY trade_date DESC LIMIT 1
    """, (symbol, earnings_date))
    row = cursor.fetchone()
    if not row or not row['close_price']:
        return None
    t_minus_1_close = row['close_price']

    # T0 OHLC
    cursor.execute("""
        SELECT open_price, close_price FROM historical_prices
        WHERE symbol = ? AND trade_date >= ?
        ORDER BY trade_date ASC LIMIT 1
    """, (symbol, earnings_date))
    row = cursor.fetchone()
    if not row or not row['open_price'] or not row['close_price']:
        return None
    t0_open = row['open_price']
    t0_close = row['close_price']

    # T+1 open
    earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d')
    t1_date = (earnings_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT open_price FROM historical_prices
        WHERE symbol = ? AND trade_date >= ?
        ORDER BY trade_date ASC LIMIT 1
    """, (symbol, t1_date))
    row = cursor.fetchone()
    if not row or not row['open_price']:
        return None
    t1_open = row['open_price']

    # Gap analysis
    bmo_gap = abs(t0_open - t_minus_1_close) / t_minus_1_close
    amc_gap = abs(t1_open - t0_close) / t0_close

    # Require minimum 0.5% gap to even consider
    if max(bmo_gap, amc_gap) < 0.005:
        return None

    if bmo_gap > amc_gap * 2:
        return 'bmo'
    elif amc_gap > bmo_gap * 2:
        return 'amc'

    return None


def phase3_infer_timing(conn, dry_run, symbol_filter=None):
    """Infer BMO/AMC timing for events with NULL/Unknown timing.

    Primary: carry forward symbol's historical timing pattern.
    Fallback: price gap inference for symbols with no timing history.

    Returns stats dict.
    """
    if symbol_filter:
        cursor = conn.execute("""
            SELECT event_id, symbol, earnings_date FROM earnings_events
            WHERE earnings_date BETWEEN ? AND ?
              AND symbol = ?
              AND (earnings_time IS NULL OR earnings_time = 'Unknown' OR earnings_time = '')
            ORDER BY symbol, earnings_date
        """, (BACKFILL_FROM, BACKFILL_TO, symbol_filter))
    else:
        cursor = conn.execute("""
            SELECT event_id, symbol, earnings_date FROM earnings_events
            WHERE earnings_date BETWEEN ? AND ?
              AND (earnings_time IS NULL OR earnings_time = 'Unknown' OR earnings_time = '')
            ORDER BY symbol, earnings_date
        """, (BACKFILL_FROM, BACKFILL_TO))
    candidates = cursor.fetchall()

    if not candidates:
        return {'total': 0, 'from_history': 0, 'from_prices': 0, 'uncertain': 0}

    from_history = 0
    from_prices = 0
    uncertain = 0

    # Cache per-symbol timing lookups
    timing_cache = {}

    for event_id, symbol, earnings_date in candidates:
        # Try history first
        if symbol not in timing_cache:
            timing_cache[symbol] = get_symbol_typical_timing(conn, symbol)

        timing = timing_cache[symbol]

        if timing:
            if not dry_run:
                conn.execute(
                    "UPDATE earnings_events SET earnings_time = ? WHERE event_id = ?",
                    (timing, event_id)
                )
            from_history += 1
        else:
            # Fallback: price gap inference
            timing = infer_bmo_amc_from_prices(conn, symbol, earnings_date)
            if timing:
                if not dry_run:
                    conn.execute(
                        "UPDATE earnings_events SET earnings_time = ? WHERE event_id = ?",
                        (timing, event_id)
                    )
                from_prices += 1
            else:
                uncertain += 1

    if not dry_run:
        conn.commit()

    return {
        'total': len(candidates),
        'from_history': from_history,
        'from_prices': from_prices,
        'uncertain': uncertain,
    }


# ---------------------------------------------------------------------------
# Phase 4: Compute missing earnings_moves
# ---------------------------------------------------------------------------

def compute_moves(conn, symbol, earnings_date, earnings_time):
    """Compute price moves from historical_prices, matching ei_post_earnings_calc logic.

    Returns dict with move columns, or empty dict if insufficient price data.
    """
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row

    def get_close_on_or_before(target_date):
        cursor.execute("""
            SELECT close_price FROM historical_prices
            WHERE symbol = ? AND trade_date <= ?
            ORDER BY trade_date DESC LIMIT 1
        """, (symbol, target_date))
        row = cursor.fetchone()
        return row['close_price'] if row else None

    def get_close_on_or_after(target_date):
        cursor.execute("""
            SELECT close_price FROM historical_prices
            WHERE symbol = ? AND trade_date >= ?
            ORDER BY trade_date ASC LIMIT 1
        """, (symbol, target_date))
        row = cursor.fetchone()
        return row['close_price'] if row else None

    def get_ohlc_on_or_after(target_date):
        cursor.execute("""
            SELECT open_price, high_price, low_price, close_price FROM historical_prices
            WHERE symbol = ? AND trade_date >= ?
            ORDER BY trade_date ASC LIMIT 1
        """, (symbol, target_date))
        return cursor.fetchone()

    is_amc = earnings_time and earnings_time.lower() == 'amc'
    earnings_dt = datetime.strptime(earnings_date, '%Y-%m-%d')
    t_minus_1 = (earnings_dt - timedelta(days=1)).strftime('%Y-%m-%d')

    # Baseline: T(-1) for BMO/unknown, T0 for AMC
    if is_amc:
        baseline = get_close_on_or_after(earnings_date)
        post_start_date = (earnings_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        baseline = get_close_on_or_before(t_minus_1)
        post_start_date = earnings_date

    if not baseline or baseline <= 0:
        return {}

    moves = {'pre_earnings_close': round(baseline, 2)}

    # Close-to-close moves
    for n_days, label in [(1, 'move_1day_pct'), (2, 'move_2day_pct'),
                          (3, 'move_3day_pct'), (5, 'move_5day_pct')]:
        offset = datetime.strptime(post_start_date, '%Y-%m-%d') + timedelta(days=n_days - 1)
        close_n = get_close_on_or_after(offset.strftime('%Y-%m-%d'))
        if close_n:
            moves[label] = round(((close_n - baseline) / baseline) * 100, 2)

    # max_intraday_move_pct from post-earnings OHLC
    ohlc = get_ohlc_on_or_after(post_start_date)
    if ohlc and baseline > 0:
        peaks = []
        if ohlc['high_price']:
            peaks.append(((ohlc['high_price'] - baseline) / baseline) * 100)
        if ohlc['low_price']:
            peaks.append(((ohlc['low_price'] - baseline) / baseline) * 100)
        if peaks:
            moves['max_intraday_move_pct'] = round(max(peaks, key=abs), 2)

    # Direction
    if moves.get('move_1day_pct') is not None:
        moves['move_direction'] = 'up' if moves['move_1day_pct'] > 0 else 'down'

    return moves


def phase4_compute_moves(conn, dry_run, symbol_filter=None):
    """Compute earnings_moves for events that don't have them.

    Returns stats dict: {eligible, filled, no_data}.
    """
    # Find events in range with no moves
    if symbol_filter:
        cursor = conn.execute("""
            SELECT e.event_id, e.symbol, e.earnings_date, e.earnings_time
            FROM earnings_events e
            LEFT JOIN earnings_moves m ON e.symbol = m.symbol AND e.earnings_date = m.earnings_date
            WHERE e.earnings_date BETWEEN ? AND ?
              AND e.symbol = ?
              AND m.symbol IS NULL
            ORDER BY e.earnings_date, e.symbol
        """, (BACKFILL_FROM, BACKFILL_TO, symbol_filter))
    else:
        cursor = conn.execute("""
            SELECT e.event_id, e.symbol, e.earnings_date, e.earnings_time
            FROM earnings_events e
            LEFT JOIN earnings_moves m ON e.symbol = m.symbol AND e.earnings_date = m.earnings_date
            WHERE e.earnings_date BETWEEN ? AND ?
              AND m.symbol IS NULL
            ORDER BY e.earnings_date, e.symbol
        """, (BACKFILL_FROM, BACKFILL_TO))
    candidates = cursor.fetchall()

    if not candidates:
        return {'eligible': 0, 'filled': 0, 'no_data': 0}

    filled = 0
    no_data = 0

    for i, (event_id, symbol, earnings_date, earnings_time) in enumerate(candidates, 1):
        moves = compute_moves(conn, symbol, earnings_date, earnings_time)

        if moves.get('move_1day_pct') is not None:
            if not dry_run:
                # Dedup check
                existing = conn.execute(
                    "SELECT 1 FROM earnings_moves WHERE symbol = ? AND earnings_date = ?",
                    (symbol, earnings_date)
                ).fetchone()
                if not existing:
                    conn.execute("""
                        INSERT INTO earnings_moves
                        (event_id, symbol, earnings_date, pre_earnings_close,
                         move_1day_pct, move_2day_pct, move_3day_pct, move_5day_pct,
                         max_intraday_move_pct, move_direction, calculated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        event_id, symbol, earnings_date,
                        moves.get('pre_earnings_close'),
                        moves.get('move_1day_pct'),
                        moves.get('move_2day_pct'),
                        moves.get('move_3day_pct'),
                        moves.get('move_5day_pct'),
                        moves.get('max_intraday_move_pct'),
                        moves.get('move_direction'),
                    ))
            filled += 1
        else:
            no_data += 1

        # Progress every 200
        if i % 200 == 0:
            print(f"    [{i}/{len(candidates)}] ... {filled} filled, {no_data} no data")
            if not dry_run:
                conn.commit()

    if not dry_run:
        conn.commit()

    return {'eligible': len(candidates), 'filled': filled, 'no_data': no_data}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Backfill earnings data from Tradier Corporate Calendars API'
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview gaps without writing')
    parser.add_argument('--symbol', type=str, help='Backfill single symbol')
    parser.add_argument('--limit', type=int, help='Process first N symbols only')
    parser.add_argument('--moves-only', action='store_true',
                        help='Skip event fetch (phases 1-2), just compute missing moves')
    parser.add_argument('--skip-timing', action='store_true',
                        help='Skip BMO/AMC inference (phase 3)')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Symbols per Tradier API call (default: {DEFAULT_BATCH_SIZE})')
    args = parser.parse_args()

    mode_label = "DRY RUN" if args.dry_run else "LIVE"

    # Load API key
    token = load_config()

    # Connect to DB
    conn = sqlite3.connect(PRODUCTION_DB)
    if not args.dry_run:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

    # Get symbols
    symbols = get_symbols(conn, args.symbol)
    if args.limit:
        symbols = symbols[:args.limit]

    print(f"\n{'=' * 60}")
    print("  BACKFILL EARNINGS FROM TRADIER CALENDARS")
    print(f"{'=' * 60}")
    print(f"  Symbols:  {len(symbols)}")
    print(f"  Mode:     {mode_label}")
    print(f"  Target:   {PRODUCTION_DB}")
    print(f"  Source:   Tradier /beta/markets/fundamentals/calendars")
    print(f"  Range:    {BACKFILL_FROM} to {BACKFILL_TO}")
    if args.moves_only:
        print(f"  Phases:   3-4 only (--moves-only)")
    if args.skip_timing:
        print(f"  Phases:   Skipping phase 3 (--skip-timing)")
    print(f"{'=' * 60}\n")

    start_time = time.time()

    try:
        # Phase 1 & 2: Fetch and upsert events
        if not args.moves_only:
            print("=== Phase 1: Fetch earnings events from Tradier ===")
            events, fetch_stats = phase1_fetch_events(token, symbols, args.batch_size)
            print(f"\n  Fetch complete: {fetch_stats['total_events']} events from "
                  f"{fetch_stats['symbols_with_data']} symbols "
                  f"({fetch_stats['api_calls']} API calls, "
                  f"{fetch_stats['no_data_symbols']} no data)\n")

            print("=== Phase 2: Insert/Update earnings_events ===")
            upsert_stats = phase2_upsert_events(conn, events, args.dry_run)
            verb = "Would insert" if args.dry_run else "Inserted"
            print(f"  {verb}: {upsert_stats['inserted']} new events")
            print(f"  Updated: {upsert_stats['updated']} events (fiscal year/quarter filled)")
            print(f"  Skipped: {upsert_stats['skipped']} (already complete)\n")
        else:
            fetch_stats = {'total_events': 0, 'symbols_with_data': 0, 'no_data_symbols': 0, 'api_calls': 0}
            upsert_stats = {'inserted': 0, 'updated': 0, 'skipped': 0}

        # Phase 3: BMO/AMC timing
        symbol_filter = args.symbol.upper() if args.symbol else None
        if not args.skip_timing:
            print("=== Phase 3: BMO/AMC Timing Inference ===")
            timing_stats = phase3_infer_timing(conn, args.dry_run, symbol_filter)
            print(f"  Candidates: {timing_stats['total']} events with Unknown timing")
            print(f"  From history: {timing_stats['from_history']}")
            print(f"  From prices: {timing_stats['from_prices']}")
            print(f"  Uncertain: {timing_stats['uncertain']}\n")
        else:
            timing_stats = {'total': 0, 'from_history': 0, 'from_prices': 0, 'uncertain': 0}

        # Phase 4: Compute moves
        print("=== Phase 4: Compute missing earnings_moves ===")
        moves_stats = phase4_compute_moves(conn, args.dry_run, symbol_filter)
        verb = "Would fill" if args.dry_run else "Filled"
        print(f"  Eligible: {moves_stats['eligible']} events without moves")
        print(f"  {verb}: {moves_stats['filled']}")
        print(f"  No price data: {moves_stats['no_data']}\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted! Committing work done so far...")
        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print(f"{'=' * 60}")
    if args.dry_run:
        print(f"  DRY RUN COMPLETE ({minutes}m {seconds}s)")
    else:
        print(f"  BACKFILL COMPLETE ({minutes}m {seconds}s)")
    print(f"{'=' * 60}")
    if not args.moves_only:
        print(f"  Events inserted:    {upsert_stats['inserted']}")
        print(f"  Events enriched:    {upsert_stats['updated']}")
    if not args.skip_timing:
        total_inferred = timing_stats['from_history'] + timing_stats['from_prices']
        print(f"  Timing inferred:    {total_inferred} ({timing_stats['from_history']} history, "
              f"{timing_stats['from_prices']} prices)")
    print(f"  Moves computed:     {moves_stats['filled']}")
    print(f"  No price data:      {moves_stats['no_data']}")
    if not args.moves_only:
        print(f"  Symbols no data:    {fetch_stats['no_data_symbols']}")
    print(f"{'=' * 60}\n")


if __name__ == '__main__':
    main()
