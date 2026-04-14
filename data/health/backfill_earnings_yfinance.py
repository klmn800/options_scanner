"""Backfill missing earnings_events and earnings_moves using yfinance historical data.

Discovers earnings dates from yfinance that are missing from our DB, inserts them
into earnings_events, then computes price moves from historical_prices.

yfinance provides data through ~April 2025. Q3-Q4 2025 gaps need a different source.

Usage:
    python data/health/backfill_earnings_yfinance.py              # Full backfill
    python data/health/backfill_earnings_yfinance.py --dry-run    # Preview gaps
    python data/health/backfill_earnings_yfinance.py --symbol MSFT # Single symbol
    python data/health/backfill_earnings_yfinance.py --limit 50   # First N symbols
"""

import argparse
import os
import sqlite3
import sys
import time
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
PRODUCTION_DB = os.path.join(PROJECT_ROOT, 'data', 'datalake.db')

# Add project root to path for imports
sys.path.insert(0, PROJECT_ROOT)


def get_symbols():
    """Get all symbols from our universe via symbol_metadata."""
    conn = sqlite3.connect(PRODUCTION_DB)
    cursor = conn.execute("SELECT DISTINCT symbol FROM symbol_metadata ORDER BY symbol")
    symbols = [row[0] for row in cursor.fetchall()]
    conn.close()
    return symbols


def get_existing_earnings(conn, symbol):
    """Get set of earnings dates already in earnings_events for a symbol."""
    cursor = conn.execute(
        "SELECT earnings_date FROM earnings_events WHERE symbol = ?", (symbol,)
    )
    return {row[0] for row in cursor.fetchall()}


def get_existing_moves(conn, symbol):
    """Get set of earnings dates already in earnings_moves for a symbol."""
    cursor = conn.execute(
        "SELECT earnings_date FROM earnings_moves WHERE symbol = ? AND move_1day_pct IS NOT NULL",
        (symbol,)
    )
    return {row[0] for row in cursor.fetchall()}


def fetch_yfinance_earnings(symbol):
    """Fetch historical earnings dates from yfinance.

    Returns list of dicts: [{date, eps_estimate, reported_eps, surprise_pct, is_amc}, ...]
    Sorted oldest first.
    """
    import yfinance as yf

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.get_earnings_dates(limit=100)
        if df is None or len(df) == 0:
            return []

        # Filter to Earnings events only (exclude Meetings etc)
        if 'Event Type' in df.columns:
            df = df[df['Event Type'] == 'Earnings']

        results = []
        for idx in df.index:
            dt = idx
            date_str = dt.strftime('%Y-%m-%d')

            # Skip future dates (no actual EPS = not yet reported)
            reported_eps = df.loc[idx, 'Reported EPS'] if 'Reported EPS' in df.columns else None
            if reported_eps is None or (hasattr(reported_eps, '__float__') and str(reported_eps) == 'nan'):
                continue

            # Determine BMO/AMC from timestamp hour
            hour = dt.hour
            if hour < 12:
                earnings_time = 'bmo'
            elif hour >= 16:
                earnings_time = 'amc'
            else:
                earnings_time = 'Unknown'

            eps_est = df.loc[idx, 'EPS Estimate'] if 'EPS Estimate' in df.columns else None
            surprise = df.loc[idx, 'Surprise(%)'] if 'Surprise(%)' in df.columns else None

            # Convert NaN to None
            import math
            if eps_est is not None and (isinstance(eps_est, float) and math.isnan(eps_est)):
                eps_est = None
            if reported_eps is not None and (isinstance(reported_eps, float) and math.isnan(reported_eps)):
                reported_eps = None
            if surprise is not None and (isinstance(surprise, float) and math.isnan(surprise)):
                surprise = None

            results.append({
                'date': date_str,
                'eps_estimate': float(eps_est) if eps_est is not None else None,
                'reported_eps': float(reported_eps) if reported_eps is not None else None,
                'surprise_pct': float(surprise) if surprise is not None else None,
                'earnings_time': earnings_time,
            })

        results.sort(key=lambda x: x['date'])
        return results

    except Exception as e:
        return []


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


def backfill_symbol(conn, symbol, existing_events, existing_moves, dry_run=False):
    """Backfill one symbol. Returns (events_added, moves_added, yf_dates_count)."""
    yf_dates = fetch_yfinance_earnings(symbol)
    if not yf_dates:
        return 0, 0, 0

    events_added = 0
    moves_added = 0

    for entry in yf_dates:
        date_str = entry['date']

        # Skip if event already exists
        if date_str in existing_events:
            # But check if moves are missing for this existing event
            if date_str not in existing_moves and not dry_run:
                moves = compute_moves(conn, symbol, date_str, entry['earnings_time'])
                if moves.get('move_1day_pct') is not None:
                    # Find the existing event_id
                    cursor = conn.execute(
                        "SELECT event_id FROM earnings_events WHERE symbol = ? AND earnings_date = ?",
                        (symbol, date_str)
                    )
                    row = cursor.fetchone()
                    if row:
                        event_id = row[0]
                        _insert_move(conn, event_id, symbol, date_str, moves)
                        moves_added += 1
            elif date_str not in existing_moves and dry_run:
                moves_added += 1  # Count it for dry-run
            continue

        if dry_run:
            events_added += 1
            if date_str not in existing_moves:
                moves_added += 1
            continue

        # Insert earnings_event
        conn.execute("""
            INSERT OR IGNORE INTO earnings_events
            (symbol, earnings_date, earnings_time, estimated_eps, actual_eps,
             eps_surprise_pct, source, is_backfilled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'yfinance_backfill', 1, CURRENT_TIMESTAMP)
        """, (
            symbol, date_str, entry['earnings_time'],
            entry['eps_estimate'], entry['reported_eps'], entry['surprise_pct']
        ))
        events_added += 1
        existing_events.add(date_str)

        # Compute and insert moves if not already present
        if date_str not in existing_moves:
            moves = compute_moves(conn, symbol, date_str, entry['earnings_time'])
            if moves.get('move_1day_pct') is not None:
                # Get the event_id we just inserted
                cursor = conn.execute(
                    "SELECT event_id FROM earnings_events WHERE symbol = ? AND earnings_date = ?",
                    (symbol, date_str)
                )
                row = cursor.fetchone()
                if row:
                    event_id = row[0]
                    _insert_move(conn, event_id, symbol, date_str, moves)
                    moves_added += 1

    return events_added, moves_added, len(yf_dates)


def _insert_move(conn, event_id, symbol, earnings_date, moves):
    """Insert a single earnings_moves row. Skips if (symbol, earnings_date) already exists."""
    # Safety check — don't create duplicates
    cursor = conn.execute(
        "SELECT 1 FROM earnings_moves WHERE symbol = ? AND earnings_date = ?",
        (symbol, earnings_date)
    )
    if cursor.fetchone():
        return

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


def main():
    parser = argparse.ArgumentParser(description='Backfill earnings data from yfinance')
    parser.add_argument('--dry-run', action='store_true', help='Preview gaps without writing')
    parser.add_argument('--symbol', type=str, help='Backfill single symbol')
    parser.add_argument('--limit', type=int, help='Process first N symbols only')
    args = parser.parse_args()

    mode_label = "DRY RUN" if args.dry_run else "LIVE"

    if args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = get_symbols()

    if args.limit:
        symbols = symbols[:args.limit]

    print(f"\n{'=' * 60}")
    print("  BACKFILL EARNINGS FROM YFINANCE")
    print(f"{'=' * 60}")
    print(f"  Symbols:  {len(symbols)}")
    print(f"  Mode:     {mode_label}")
    print(f"  Target:   {PRODUCTION_DB}")
    print(f"  Source:   yfinance historical earnings (through ~April 2025)")
    print(f"{'=' * 60}\n")

    conn = sqlite3.connect(PRODUCTION_DB)
    if not args.dry_run:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

    start_time = time.time()
    total_events = 0
    total_moves = 0
    total_yf_dates = 0
    symbols_with_gaps = 0
    symbols_no_yf = 0
    errors = 0

    try:
        for i, symbol in enumerate(symbols, 1):
            try:
                existing_events = get_existing_earnings(conn, symbol)
                existing_moves = get_existing_moves(conn, symbol)

                events_added, moves_added, yf_count = backfill_symbol(
                    conn, symbol, existing_events, existing_moves, args.dry_run
                )

                if yf_count == 0:
                    symbols_no_yf += 1

                if events_added > 0 or moves_added > 0:
                    symbols_with_gaps += 1
                    label = "would add" if args.dry_run else "added"
                    print(f"  [{i}/{len(symbols)}] {symbol}: {label} {events_added} events, {moves_added} moves (yf has {yf_count} dates)")
                    total_events += events_added
                    total_moves += moves_added

                total_yf_dates += yf_count

                # Commit every 25 symbols
                if not args.dry_run and i % 25 == 0:
                    conn.commit()

                # Progress line every 100 symbols (for symbols with no gaps)
                if i % 100 == 0 and events_added == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    eta = (len(symbols) - i) / rate if rate > 0 else 0
                    print(f"  [{i}/{len(symbols)}] ... {rate:.1f} symbols/sec, ~{int(eta)}s remaining")

            except Exception as e:
                errors += 1
                print(f"  [{i}/{len(symbols)}] {symbol}: ERROR — {e}")

        if not args.dry_run:
            conn.commit()

    except KeyboardInterrupt:
        print("\n\nInterrupted! Committing work done so far...")
        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print(f"\n{'=' * 60}")
    if args.dry_run:
        print(f"  DRY RUN COMPLETE ({minutes}m {seconds}s)")
    else:
        print(f"  BACKFILL COMPLETE ({minutes}m {seconds}s)")
    print(f"{'=' * 60}")
    print(f"  Symbols processed:  {len(symbols)}")
    print(f"  Symbols with gaps:  {symbols_with_gaps}")
    print(f"  No yfinance data:   {symbols_no_yf}")
    print(f"  Events {'found' if args.dry_run else 'added'}:  {total_events:,}")
    print(f"  Moves {'found' if args.dry_run else 'added'}:   {total_moves:,}")
    if errors:
        print(f"  Errors:             {errors}")
    print()


if __name__ == '__main__':
    main()
