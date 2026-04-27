"""
Earnings Watchlist Writer Module

Manages the `earnings_watchlist` table in datalake.db — a lean, investor-facing
table that surfaces earnings opportunities for morning review.

Entry criteria (new rows):
- earnings_play_signal in (WATCH, BUY, STRONG BUY)
- days_to_earnings <= 14 (calendar days)
- Total open interest >= 4000 (from option_symbol_summary)

Lifecycle: UPCOMING -> TODAY -> T+1 -> T+2 -> T+3 -> deleted at T+4

Existing rows are updated daily with fresh data. Signal downgrades update the
column but do NOT delete the row. Rows are only removed at T+4 cleanup.

Database Operations:
    Reads: earnings_upcoming, option_symbol_summary, flow_symbol_summary,
           historical_prices, earnings_moves, earnings_events,
           news_symbol_sentiment (backfill sentiment for watchlist gaps)
    Writes: earnings_watchlist (CREATE, INSERT/UPDATE, DELETE)

Autofix Integration:
    Fatal failures in populate_watchlist() queue via queue_error() with
    severity='ERROR' and context including failed_step='watchlist_population'.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.autofix import queue_error
from tools.decimal_formatter import clean_database_row
from tools.log_utils import beautiful_log
from tools.timezone_utils import now_eastern, eastern_isoformat, eastern_date_string


# ---------------------------------------------------------------------------
# Table DDL
# ---------------------------------------------------------------------------

def _create_table(cursor):
    """Create earnings_watchlist table and indexes if they don't exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS earnings_watchlist (
            symbol TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            current_price REAL,
            days_to_earnings INTEGER NOT NULL,
            earnings_date TEXT NOT NULL,
            earnings_time TEXT,
            earnings_play_signal TEXT,
            iv_percentile_30d REAL,
            relative_underpricing_pct REAL,
            historical_avg_move_pct REAL,
            straddle_expected_move_pct REAL,
            oi_balance_text TEXT,
            vol_balance_text TEXT,
            iv_front_month_change_5d REAL,
            alert_count_5d INTEGER,
            news_sentiment_label TEXT,
            news_sentiment_score REAL,
            news_article_count INTEGER,
            first_appeared_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_updated TEXT NOT NULL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ew_earnings_date ON earnings_watchlist(earnings_date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ew_status ON earnings_watchlist(status)"
    )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def _cleanup_expired(cursor, today):
    """Delete rows that are T+4 past earnings OR more than 14 days away.

    Matches the 14-day entry criteria in _get_qualifying_symbols() so symbols
    don't persist indefinitely after their distance exceeds the window.

    Returns:
        int: Number of rows removed.
    """
    today_str = today.isoformat()

    # T+4: earnings happened 4+ days ago
    cursor.execute(
        "DELETE FROM earnings_watchlist WHERE julianday(?) - julianday(earnings_date) >= 4",
        (today_str,),
    )
    removed_past = cursor.rowcount

    # Too far out: earnings > 14 days in the future
    cursor.execute(
        "DELETE FROM earnings_watchlist WHERE julianday(earnings_date) - julianday(?) > 14",
        (today_str,),
    )
    removed_far = cursor.rowcount

    removed = removed_past + removed_far
    if removed > 0:
        parts = []
        if removed_past:
            parts.append("{} T+4+".format(removed_past))
        if removed_far:
            parts.append("{} >14d out".format(removed_far))
        logging.info("   ├─ Cleaned up {} expired entries ({})".format(removed, ", ".join(parts)))
    return removed


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _compute_status_and_days(earnings_date_str, today):
    """Compute (status, days_to_earnings) from earnings_date and today.

    days_to_earnings is calendar days to earnings.
    Positive = future, 0 = earnings day, negative = past (post-earnings tracking).
    Status encodes post-earnings position: T+1 / T+2 / T+3.
    """
    earnings_dt = datetime.strptime(earnings_date_str, "%Y-%m-%d").date()
    diff = (earnings_dt - today).days  # positive = future, negative = past

    if diff > 0:
        return ("UPCOMING", diff)
    elif diff == 0:
        return ("TODAY", 0)
    elif diff == -1:
        return ("T+1", -1)
    elif diff == -2:
        return ("T+2", -2)
    elif diff == -3:
        return ("T+3", -3)
    else:
        # Should have been cleaned up — handle gracefully
        return ("T+{}".format(abs(diff)), diff)


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------

def _get_qualifying_symbols(cursor, today):
    """Get symbols that should appear on the earnings watchlist.

    Two populations:
    1. New qualifying symbols from earnings_upcoming (signal + date + OI).
    2. Existing watchlist symbols — refreshed regardless of current signal.

    Returns:
        list[dict]: Each dict has earnings_upcoming fields for one symbol.
    """
    today_str = today.isoformat()
    cutoff_date = (today + timedelta(days=14)).isoformat()

    # 1. New qualifying symbols from earnings_upcoming + OI >= 4000
    cursor.execute("""
        SELECT eu.symbol, eu.earnings_date, eu.earnings_time, eu.earnings_play_signal,
               eu.relative_underpricing_pct,
               eu.historical_avg_move_pct, eu.straddle_expected_move_pct
        FROM earnings_upcoming eu
        INNER JOIN (
            SELECT symbol,
                   (COALESCE(total_call_oi, 0) + COALESCE(total_put_oi, 0)) AS total_oi
            FROM option_symbol_summary
            WHERE trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
        ) oss ON eu.symbol = oss.symbol AND oss.total_oi >= 4000
        WHERE eu.earnings_play_signal IN ('WATCH', 'BUY', 'STRONG BUY')
          AND eu.earnings_date >= ?
          AND eu.earnings_date <= ?
    """, (today_str, cutoff_date))

    results = {}
    for row in cursor.fetchall():
        results[row[0]] = {
            "symbol": row[0],
            "earnings_date": row[1],
            "earnings_time": row[2],
            "earnings_play_signal": row[3],
            "relative_underpricing_pct": row[4],
            "historical_avg_move_pct": row[5],
            "straddle_expected_move_pct": row[6],
        }

    # 2. Existing watchlist symbols — stay until T+4 regardless of signal
    cursor.execute("SELECT symbol, earnings_date FROM earnings_watchlist")
    for sym, earn_date in cursor.fetchall():
        if sym in results:
            continue  # Already covered by qualifying query

        # Refresh from earnings_upcoming if available
        cursor.execute("""
            SELECT earnings_date, earnings_time, earnings_play_signal,
                   relative_underpricing_pct,
                   historical_avg_move_pct, straddle_expected_move_pct
            FROM earnings_upcoming WHERE symbol = ?
        """, (sym,))
        eu_row = cursor.fetchone()
        if eu_row:
            results[sym] = {
                "symbol": sym,
                "earnings_date": eu_row[0],
                "earnings_time": eu_row[1],
                "earnings_play_signal": eu_row[2],
                "relative_underpricing_pct": eu_row[3],
                "historical_avg_move_pct": eu_row[4],
                "straddle_expected_move_pct": eu_row[5],
            }
        else:
            # earnings_upcoming row may have been archived — use watchlist's stored date
            results[sym] = {
                "symbol": sym,
                "earnings_date": earn_date,
                "earnings_time": None,
                "earnings_play_signal": None,
                "relative_underpricing_pct": None,
                "historical_avg_move_pct": None,
                "straddle_expected_move_pct": None,
            }

    return list(results.values())


def _volume_balance_text(volume_put_call_ratio):
    """Derive a text label from the put/call volume ratio.

    Mirrors the OI balance text thresholds from op_symbol_rollup.py but
    describes *volume* (today's trading activity) rather than OI
    (accumulated positions).
    """
    if volume_put_call_ratio is None:
        return None
    if volume_put_call_ratio < 0.5:
        return "Clear Call Vol"
    elif volume_put_call_ratio < 0.77:
        return "Heavy Call Vol"
    elif volume_put_call_ratio <= 1.3:
        return "Balanced Vol"
    elif volume_put_call_ratio <= 1.9:
        return "Heavy Put Vol"
    else:
        return "Clear Put Vol"


def _pull_option_summary_data(cursor, symbols):
    """Batch query option_symbol_summary for price, IV percentile, OI/vol balance,
    and 5-day front-month IV change.

    IV percentile may be NULL on today's row (needs 20+ days of history in
    the 30-day window — can fail near archive boundaries). Falls back to
    the previous trading day's value when today's is NULL.

    Returns:
        dict: keyed by symbol -> {current_price, iv_percentile_30d,
              oi_balance_text, vol_balance_text, iv_front_month_change_5d}
    """
    if not symbols:
        return {}

    placeholders = ",".join("?" * len(symbols))
    cursor.execute("""
        SELECT symbol, close_price, symbol_iv_percentile_30d,
               oi_balance_text, volume_put_call_ratio, iv_front_month
        FROM option_symbol_summary
        WHERE trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
          AND symbol IN ({})
    """.format(placeholders), symbols)

    result = {}
    missing_iv = []
    missing_vol = []
    current_front_month = {}
    for row in cursor.fetchall():
        result[row[0]] = {
            "current_price": row[1],
            "iv_percentile_30d": row[2],
            "oi_balance_text": row[3],
            "vol_balance_text": _volume_balance_text(row[4]),
            "iv_front_month_change_5d": None,
        }
        if row[5] is not None:
            current_front_month[row[0]] = row[5]
        if row[2] is None:
            missing_iv.append(row[0])
        if row[4] is None:
            missing_vol.append(row[0])

    # Backfill IV percentile from previous trading day if today's is NULL
    if missing_iv:
        ph2 = ",".join("?" * len(missing_iv))
        cursor.execute("""
            SELECT symbol, symbol_iv_percentile_30d
            FROM option_symbol_summary
            WHERE trade_date = (
                SELECT MAX(trade_date) FROM option_symbol_summary
                WHERE trade_date < (SELECT MAX(trade_date) FROM option_symbol_summary)
            )
              AND symbol IN ({})
              AND symbol_iv_percentile_30d IS NOT NULL
        """.format(ph2), missing_iv)
        for row in cursor.fetchall():
            if row[0] in result:
                result[row[0]]["iv_percentile_30d"] = row[1]

    # Backfill volume ratio from previous trading day if today's is NULL
    # (morning OP writes rows pre-market with no volume data yet)
    if missing_vol:
        ph_vol = ",".join("?" * len(missing_vol))
        cursor.execute("""
            SELECT symbol, volume_put_call_ratio
            FROM option_symbol_summary
            WHERE trade_date = (
                SELECT MAX(trade_date) FROM option_symbol_summary
                WHERE trade_date < (SELECT MAX(trade_date) FROM option_symbol_summary)
            )
              AND symbol IN ({})
              AND volume_put_call_ratio IS NOT NULL
        """.format(ph_vol), missing_vol)
        for row in cursor.fetchall():
            if row[0] in result:
                result[row[0]]["vol_balance_text"] = _volume_balance_text(row[1])

    # 5-day front-month IV change (ramp indicator)
    if current_front_month:
        fm_symbols = list(current_front_month.keys())
        ph3 = ",".join("?" * len(fm_symbols))
        cursor.execute("""
            SELECT symbol, iv_front_month
            FROM option_symbol_summary
            WHERE trade_date = (
                SELECT DISTINCT trade_date FROM option_symbol_summary
                ORDER BY trade_date DESC LIMIT 1 OFFSET 5
            )
              AND symbol IN ({})
              AND iv_front_month IS NOT NULL
        """.format(ph3), fm_symbols)
        for row in cursor.fetchall():
            sym, old_iv = row[0], row[1]
            if sym in current_front_month and old_iv and old_iv > 0:
                change = ((current_front_month[sym] - old_iv) / old_iv) * 100
                result[sym]["iv_front_month_change_5d"] = round(change, 1)

    return result


# ---------------------------------------------------------------------------
# Flow alert enrichment
# ---------------------------------------------------------------------------

def _enrich_flow_alerts(cursor, symbols):
    """Query flow_symbol_summary for alert_count_5d.

    Returns:
        dict: symbol -> {alert_count_5d: int}. Missing symbols are absent.
    """
    if not symbols:
        return {}

    placeholders = ",".join("?" * len(symbols))
    cursor.execute("""
        SELECT symbol, alert_count_5d
        FROM flow_symbol_summary
        WHERE symbol IN ({})
          AND trade_date = (SELECT MAX(trade_date) FROM flow_symbol_summary)
    """.format(placeholders), symbols)

    result = {}
    for row in cursor.fetchall():
        if row[1] is not None:
            result[row[0]] = {"alert_count_5d": row[1]}
    return result


# ---------------------------------------------------------------------------
# News sentiment backfill from existing data
# ---------------------------------------------------------------------------

_BULLISH_LABELS = {'Bullish', 'Somewhat-Bullish'}
_BEARISH_LABELS = {'Bearish', 'Somewhat-Bearish'}


def _backfill_news_from_existing(cursor, now_ts, max_age_days=3):
    """Backfill news sentiment for watchlist symbols from news_symbol_sentiment.

    Queries the same source table that Flow Monitor uses, applying the same
    relevance-weighted aggregation as compute_sentiment_summary() in
    tools/news_sentiment.py.

    Only fills symbols whose earnings_watchlist.news_sentiment_score is NULL.

    Args:
        cursor: Active database cursor
        now_ts: Timestamp string for last_updated
        max_age_days: Max article age to consider (default 3)

    Returns:
        int: Number of symbols backfilled
    """
    # Find watchlist symbols missing news
    cursor.execute(
        "SELECT symbol FROM earnings_watchlist WHERE news_sentiment_score IS NULL"
    )
    missing = [row[0] for row in cursor.fetchall()]
    if not missing:
        return 0

    # Query news_symbol_sentiment for recent articles
    placeholders = ','.join('?' for _ in missing)
    cursor.execute("""
        SELECT symbol, symbol_sentiment_score, relevance_score, symbol_sentiment_label
        FROM news_symbol_sentiment
        WHERE symbol IN ({})
          AND article_date >= date('now', '-{} days')
    """.format(placeholders, max_age_days), missing)

    rows = cursor.fetchall()
    if not rows:
        return 0

    # Group by symbol and compute weighted sentiment
    from collections import defaultdict
    by_symbol = defaultdict(list)
    for symbol, score, relevance, label in rows:
        by_symbol[symbol].append((score, relevance, label))

    backfilled = 0
    for symbol, articles in by_symbol.items():
        total_weight = sum(r for _, r, _ in articles)
        if total_weight > 0:
            weighted_score = sum(s * r for s, r, _ in articles) / total_weight
        else:
            weighted_score = sum(s for s, _, _ in articles) / len(articles)

        # Bucket labels (same logic as news_sentiment.py)
        counts = {'Bullish': 0, 'Bearish': 0, 'Neutral': 0}
        for _, _, label in articles:
            if label in _BULLISH_LABELS:
                counts['Bullish'] += 1
            elif label in _BEARISH_LABELS:
                counts['Bearish'] += 1
            else:
                counts['Neutral'] += 1

        _short = {'Bullish': 'Bull', 'Bearish': 'Bear', 'Neutral': 'Neutral'}
        label_parts = []
        for cat in ('Bullish', 'Bearish', 'Neutral'):
            if counts[cat] > 0:
                label_parts.append("{} {}".format(_short[cat], counts[cat]))
        distribution_label = '/'.join(label_parts) if label_parts else 'No Data'

        cleaned = clean_database_row({'news_sentiment_score': weighted_score})

        try:
            cursor.execute("""
                UPDATE earnings_watchlist
                SET news_sentiment_score = ?,
                    news_sentiment_label = ?,
                    news_article_count = ?,
                    last_updated = ?
                WHERE symbol = ?
            """, (
                cleaned['news_sentiment_score'],
                distribution_label,
                len(articles),
                now_ts,
                symbol,
            ))
            backfilled += 1
        except Exception as e:
            logging.warning("   News backfill UPDATE failed for {}: {}".format(symbol, e))

    return backfilled


# ---------------------------------------------------------------------------
# Apply enrichments
# ---------------------------------------------------------------------------

def _apply_enrichments(cursor, enrichments, now_ts):
    """UPDATE earnings_watchlist with enrichment columns for each symbol."""
    for symbol, data in enrichments.items():
        try:
            cleaned = clean_database_row(data)
            set_parts = []
            values = []
            for col, val in cleaned.items():
                set_parts.append("{} = ?".format(col))
                values.append(val)
            set_parts.append("last_updated = ?")
            values.append(now_ts)
            values.append(symbol)

            cursor.execute(
                "UPDATE earnings_watchlist SET {} WHERE symbol = ?".format(
                    ", ".join(set_parts)
                ),
                values,
            )
        except Exception as e:
            logging.warning("   Enrichment UPDATE failed for {}: {}".format(symbol, e))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def populate_watchlist(db_path=None):
    """Populate the earnings_watchlist table.

    Orchestrates: create table -> cleanup expired -> get qualifying symbols ->
    compute status/days -> pull option data -> build rows -> upsert ->
    enrich post-earnings -> enrich flow alerts -> return results.

    Args:
        db_path: Path to datalake.db.  Defaults to data/datalake.db.

    Returns:
        dict with keys: watchlist_count, watchlist_new, watchlist_breakdown,
        watchlist_symbols, removed_count.
    """
    if db_path is None:
        project_root = str(Path(__file__).parent.parent.parent)
        db_path = os.path.join(project_root, "data", "datalake.db")

    today = now_eastern().date()
    today_str = today.isoformat()
    now_ts = eastern_isoformat()

    try:
        conn = sqlite3.connect(db_path, timeout=30)
        cursor = conn.cursor()

        # Create table if needed
        _create_table(cursor)
        conn.commit()

        # Snapshot existing symbols (for new-vs-update detection)
        cursor.execute("SELECT symbol FROM earnings_watchlist")
        existing_symbols = set(row[0] for row in cursor.fetchall())

        # Cleanup T+4+ rows
        removed_count = _cleanup_expired(cursor, today)
        conn.commit()

        # Remove cleaned-up symbols from the snapshot
        cursor.execute("SELECT symbol FROM earnings_watchlist")
        existing_after_cleanup = set(row[0] for row in cursor.fetchall())

        # Get qualifying symbols (new + existing)
        qualifying = _get_qualifying_symbols(cursor, today)

        if not qualifying:
            logging.info("   └─ No qualifying symbols for earnings watchlist")
            conn.close()
            return {
                "watchlist_count": 0,
                "watchlist_new": 0,
                "watchlist_breakdown": {},
                "watchlist_symbols": [],
                "removed_count": removed_count,
            }

        # Pull supplemental option data
        symbol_list = [q["symbol"] for q in qualifying]
        option_data = _pull_option_summary_data(cursor, symbol_list)

        # Build and upsert rows
        watchlist_rows = []
        for q in qualifying:
            symbol = q["symbol"]
            status, days = _compute_status_and_days(q["earnings_date"], today)
            opt = option_data.get(symbol, {})

            row = {
                "symbol": symbol,
                "status": status,
                "current_price": opt.get("current_price"),
                "days_to_earnings": days,
                "earnings_date": q["earnings_date"],
                "earnings_time": q.get("earnings_time"),
                "earnings_play_signal": q.get("earnings_play_signal"),
                "iv_percentile_30d": opt.get("iv_percentile_30d"),
                "relative_underpricing_pct": q.get("relative_underpricing_pct"),
                "historical_avg_move_pct": q.get("historical_avg_move_pct"),
                "straddle_expected_move_pct": q.get("straddle_expected_move_pct"),
                "oi_balance_text": opt.get("oi_balance_text"),
                "vol_balance_text": opt.get("vol_balance_text"),
                "iv_front_month_change_5d": opt.get("iv_front_month_change_5d"),
                "alert_count_5d": None,
                "news_sentiment_label": None,
                "news_sentiment_score": None,
                "news_article_count": None,
            }

            cleaned = clean_database_row(row)
            # Set timestamp fields AFTER clean_database_row (it nullifies unknown date fields)
            cleaned["first_appeared_date"] = today_str
            cleaned["created_at"] = now_ts
            cleaned["last_updated"] = now_ts
            # Store status/days on the cleaned dict for enrichment use
            cleaned["status"] = status
            watchlist_rows.append(cleaned)

            try:
                cursor.execute("""
                    INSERT INTO earnings_watchlist (
                        symbol, status, current_price, days_to_earnings, earnings_date,
                        earnings_time, earnings_play_signal, iv_percentile_30d,
                        relative_underpricing_pct, historical_avg_move_pct,
                        straddle_expected_move_pct, oi_balance_text, vol_balance_text,
                        iv_front_month_change_5d, alert_count_5d,
                        news_sentiment_label, news_sentiment_score, news_article_count,
                        first_appeared_date, created_at, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    -- ON CONFLICT: deliberately omits 4 enrichment columns
                    -- (alert_count_5d, news_sentiment_*).
                    -- By excluding them from UPDATE SET, yesterday's enrichment
                    -- values survive the upsert. The enrichment pass
                    -- (_enrich_flow_alerts, news sub-step 5 in ei_main.py)
                    -- runs immediately after and overwrites with fresh data.
                    ON CONFLICT(symbol) DO UPDATE SET
                        status = excluded.status,
                        current_price = excluded.current_price,
                        days_to_earnings = excluded.days_to_earnings,
                        earnings_date = excluded.earnings_date,
                        earnings_time = excluded.earnings_time,
                        earnings_play_signal = excluded.earnings_play_signal,
                        iv_percentile_30d = COALESCE(excluded.iv_percentile_30d, earnings_watchlist.iv_percentile_30d),
                        relative_underpricing_pct = excluded.relative_underpricing_pct,
                        historical_avg_move_pct = excluded.historical_avg_move_pct,
                        straddle_expected_move_pct = excluded.straddle_expected_move_pct,
                        oi_balance_text = excluded.oi_balance_text,
                        vol_balance_text = excluded.vol_balance_text,
                        iv_front_month_change_5d = excluded.iv_front_month_change_5d,
                        last_updated = excluded.last_updated
                """, (
                    cleaned["symbol"], cleaned["status"], cleaned.get("current_price"),
                    cleaned["days_to_earnings"], cleaned["earnings_date"],
                    cleaned.get("earnings_time"), cleaned.get("earnings_play_signal"),
                    cleaned.get("iv_percentile_30d"), cleaned.get("relative_underpricing_pct"),
                    cleaned.get("historical_avg_move_pct"),
                    cleaned.get("straddle_expected_move_pct"), cleaned.get("oi_balance_text"),
                    cleaned.get("vol_balance_text"),
                    cleaned.get("iv_front_month_change_5d"),
                    cleaned.get("alert_count_5d"), cleaned.get("news_sentiment_label"),
                    cleaned.get("news_sentiment_score"), cleaned.get("news_article_count"),
                    cleaned["first_appeared_date"], cleaned["created_at"],
                    cleaned["last_updated"],
                ))
            except Exception as e:
                logging.warning("   Failed to upsert watchlist entry for {}: {}".format(symbol, e))

        conn.commit()

        # ----- Enrichment pass (base data already committed) -----
        try:
            flow_enrichments = _enrich_flow_alerts(cursor, symbol_list)

            if flow_enrichments:
                _apply_enrichments(cursor, flow_enrichments, now_ts)
                conn.commit()
        except Exception as e:
            logging.warning(
                "   Enrichment pass failed (base watchlist data preserved): {}".format(e)
            )

        # ----- News sentiment backfill from existing data -----
        try:
            news_backfilled = _backfill_news_from_existing(cursor, now_ts)
            if news_backfilled > 0:
                conn.commit()
                logging.info("   ├─ News backfill: {} symbols from existing data".format(
                    news_backfilled))
        except Exception as e:
            logging.warning(
                "   News backfill failed (non-critical): {}".format(e)
            )

        # ----- Build result dict -----
        cursor.execute("SELECT symbol FROM earnings_watchlist")
        current_symbols = set(row[0] for row in cursor.fetchall())
        new_symbols = current_symbols - existing_after_cleanup

        # Signal breakdown
        cursor.execute("""
            SELECT earnings_play_signal, COUNT(*)
            FROM earnings_watchlist
            GROUP BY earnings_play_signal
        """)
        breakdown = {}
        for row in cursor.fetchall():
            if row[0]:
                breakdown[row[0]] = row[1]

        # Full row data for console display
        cursor.execute(
            "SELECT * FROM earnings_watchlist ORDER BY days_to_earnings ASC, earnings_date ASC"
        )
        columns = [desc[0] for desc in cursor.description]
        watchlist_symbols = [dict(zip(columns, row)) for row in cursor.fetchall()]

        watchlist_count = len(watchlist_symbols)
        conn.close()

        # Log summary
        beautiful_log("Watchlist populated: {} symbols ({} new)".format(
            watchlist_count, len(new_symbols)), 'success')
        if breakdown:
            parts = []
            for sig in ("STRONG BUY", "BUY", "WATCH"):
                if sig in breakdown:
                    parts.append("{}: {}".format(sig, breakdown[sig]))
            for sig, count in sorted(breakdown.items()):
                if sig not in ("STRONG BUY", "BUY", "WATCH"):
                    parts.append("{}: {}".format(sig, count))
            if parts:
                logging.info("   └─ Breakdown: {}".format(", ".join(parts)))

        return {
            "success": True,
            "watchlist_count": watchlist_count,
            "watchlist_new": len(new_symbols),
            "watchlist_breakdown": breakdown,
            "watchlist_symbols": watchlist_symbols,
            "removed_count": removed_count,
        }

    except Exception as e:
        logging.error("   └─ Watchlist population failed: {}".format(e))
        try:
            queue_error(
                error_type='watchlist_population_failure',
                context={
                    'failed_step': 'watchlist_population',
                    'error_message': str(e),
                },
                severity='ERROR'
            )
        except Exception:
            pass  # Don't let autofix integration break the return
        return {
            "success": False,
            "watchlist_count": 0,
            "watchlist_new": 0,
            "watchlist_breakdown": {},
            "watchlist_symbols": [],
            "removed_count": 0,
        }
