#!/usr/bin/env python3
"""
Trade Positions & Trade Calls — schema + (later) refresh helper
================================================================
Owns DDL for two tables:

  trade_positions  — materialized current portfolio. Aggregated from
                     trade_executions. Rows REMOVED when net_qty hits 0.
                     position_key matches flow_alerts.contract_hash exactly.

  trade_calls      — thesis log. One row per trade idea, regardless of
                     whether it ultimately fills. Lifecycle:
                     proposed → open → closed | abandoned.

Design doc: agents/trading_advisor/proposals/011_morning_orientation_table.md

Phase 1 (this file): schema + --init CLI.
Phase 2c (later):    refresh_trade_positions() helper, called from every
                     trade_executions write site (tools/trade_ingest.py and
                     the FM cycle's run_periodic block in fm_main.py).

Usage:
    python tools/trade_positions.py --init          # Create tables + index in datalake.db
    python tools/trade_positions.py --init-views    # Create the four TA-scoped views
    python tools/trade_positions.py --reconcile     # Full rebuild of trade_positions from trade_executions

Reads/writes: data/datalake.db (mirrors DELETEs/UPDATEs to data/datalake_query.db)
"""

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from log_utils import beautiful_log

logger = logging.getLogger(__name__)


# ── Schema ───────────────────────────────────────────────────────────

def _ensure_schema(conn):
    """Create trade_positions and trade_calls tables (and supporting indexes)
    if they don't exist. Idempotent — safe to call repeatedly.

    Reads: nothing
    Writes: trade_positions, trade_calls (CREATE TABLE, CREATE INDEX)
    """
    cursor = conn.cursor()

    # trade_calls created first because trade_positions.trade_call_ref FK references it.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME NOT NULL,
            symbol TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            strike REAL,
            option_type TEXT,
            expiration_date DATE,
            direction TEXT,
            conviction INTEGER,
            planned_qty INTEGER,
            entry_price_target REAL,
            target_pct REAL,
            stop_pct REAL,
            time_stop_date DATE,
            catalyst_date DATE,
            catalyst_type TEXT,
            thesis TEXT,
            pattern_tag TEXT,
            status TEXT NOT NULL,
            closed_at DATETIME,
            outcome_pct REAL,
            grade_notes TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_positions (
            position_key TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            instrument_type TEXT,
            strike REAL,
            option_type TEXT,
            expiration_date DATE,
            net_qty INTEGER NOT NULL,
            avg_buy_price REAL,
            total_cost REAL,
            opened_at DATETIME,
            last_action_at DATETIME,
            target_pct REAL,
            stop_pct REAL,
            time_stop_date DATE,
            trade_call_ref INTEGER REFERENCES trade_calls(id),
            notes TEXT
        )
    """)

    # Indexes — keep minimal. N is small (typically <30 trade_calls, <10 positions).
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name IN ('trade_positions', 'trade_calls')")
    existing = {row[0] for row in cursor.fetchall()}

    if 'idx_trade_calls_symbol' not in existing:
        cursor.execute("CREATE INDEX idx_trade_calls_symbol ON trade_calls(symbol)")
    if 'idx_trade_calls_status' not in existing:
        cursor.execute("CREATE INDEX idx_trade_calls_status ON trade_calls(status)")
    if 'idx_trade_positions_symbol' not in existing:
        cursor.execute("CREATE INDEX idx_trade_positions_symbol ON trade_positions(symbol)")

    conn.commit()


def _ensure_views(conn):
    """Create the four TA-scoped views.

    Views are TA-scoped (filtered to trade_positions ∪ open trade_calls). Defined
    in datalake.db so the page-level full sync (db_backup.py:1572) propagates
    them to datalake_query.db, which is where TA actually queries them.

    Dependency order:
      1. ta_v_positions_live          (independent)
      2. ta_v_symbol_dashboard        (depends on ta_v_positions_live)
      3. ta_v_position_flow_recent    (independent)
      4. ta_v_position_oi_context     (independent)

    DROP IF EXISTS is used so re-running --init-views always reflects the
    current Python source. Views have no data of their own — safe to drop/recreate.

    Reads: nothing
    Writes: 4 views (DROP + CREATE)
    """
    cursor = conn.cursor()

    # 1. ta_v_positions_live ───────────────────────────────────────────
    # Position-level live state with marks from the latest flow_options_scans
    # row per contract (options) or per symbol (stock). Latest-scan lookup uses
    # PK index for options (contract_hash, scan_timestamp) and the new
    # idx_flow_scans_symbol_scan for stocks.
    cursor.execute("DROP VIEW IF EXISTS ta_v_positions_live")
    cursor.execute("""
        CREATE VIEW ta_v_positions_live AS
        WITH option_marks AS (
            SELECT
                fos.contract_hash AS position_key,
                fos.scan_timestamp AS mark_timestamp,
                fos.last_price AS option_mark,
                fos.underlying_price,
                fos.iv,
                fos.delta
            FROM flow_options_scans fos
            INNER JOIN (
                SELECT contract_hash, MAX(scan_timestamp) AS max_ts
                FROM flow_options_scans
                WHERE contract_hash IN (
                    SELECT position_key FROM trade_positions WHERE instrument_type = 'option'
                )
                GROUP BY contract_hash
            ) latest
                ON fos.contract_hash = latest.contract_hash
                AND fos.scan_timestamp = latest.max_ts
        ),
        stock_marks AS (
            SELECT
                fos.symbol,
                MAX(fos.scan_timestamp) AS mark_timestamp,
                fos.underlying_price AS stock_mark
            FROM flow_options_scans fos
            INNER JOIN (
                SELECT symbol, MAX(scan_timestamp) AS max_ts
                FROM flow_options_scans
                WHERE symbol IN (
                    SELECT symbol FROM trade_positions WHERE instrument_type = 'stock'
                )
                GROUP BY symbol
            ) latest
                ON fos.symbol = latest.symbol
                AND fos.scan_timestamp = latest.max_ts
            GROUP BY fos.symbol
        )
        SELECT
            tp.position_key, tp.symbol, tp.instrument_type,
            tp.strike, tp.option_type, tp.expiration_date,
            tp.net_qty, tp.avg_buy_price, tp.total_cost,
            tp.target_pct, tp.stop_pct, tp.time_stop_date,
            tp.trade_call_ref, tp.notes,

            CASE
                WHEN tp.instrument_type = 'option' THEN om.option_mark
                WHEN tp.instrument_type = 'stock' THEN sm.stock_mark
            END AS current_mark,

            CASE
                WHEN tp.instrument_type = 'option' THEN om.mark_timestamp
                WHEN tp.instrument_type = 'stock' THEN sm.mark_timestamp
            END AS mark_timestamp,

            om.underlying_price,
            om.iv,
            om.delta,

            ROUND(tp.avg_buy_price * (1 + tp.target_pct / 100.0), 4) AS target_price,
            ROUND(tp.avg_buy_price * (1 - tp.stop_pct / 100.0), 4) AS stop_price,

            CASE
                WHEN tp.instrument_type = 'option' AND om.option_mark IS NOT NULL THEN
                    ROUND((om.option_mark - tp.avg_buy_price) / tp.avg_buy_price * 100.0, 2)
                WHEN tp.instrument_type = 'stock' AND sm.stock_mark IS NOT NULL THEN
                    ROUND((sm.stock_mark - tp.avg_buy_price) / tp.avg_buy_price * 100.0, 2)
            END AS current_pnl_pct,

            CASE
                WHEN tp.instrument_type = 'option' AND om.option_mark IS NOT NULL THEN
                    ROUND((om.option_mark - tp.avg_buy_price) * tp.net_qty * 100.0, 2)
                WHEN tp.instrument_type = 'stock' AND sm.stock_mark IS NOT NULL THEN
                    ROUND((sm.stock_mark - tp.avg_buy_price) * tp.net_qty, 2)
            END AS current_pnl_dollars,

            CASE
                WHEN tp.instrument_type = 'option' AND om.option_mark IS NOT NULL AND om.option_mark > 0 THEN
                    ROUND((tp.avg_buy_price * (1 + tp.target_pct / 100.0) - om.option_mark) / om.option_mark * 100.0, 2)
                WHEN tp.instrument_type = 'stock' AND sm.stock_mark IS NOT NULL AND sm.stock_mark > 0 THEN
                    ROUND((tp.avg_buy_price * (1 + tp.target_pct / 100.0) - sm.stock_mark) / sm.stock_mark * 100.0, 2)
            END AS pct_to_target,

            CASE
                WHEN tp.instrument_type = 'option' AND om.option_mark IS NOT NULL AND om.option_mark > 0 THEN
                    ROUND((tp.avg_buy_price * (1 - tp.stop_pct / 100.0) - om.option_mark) / om.option_mark * 100.0, 2)
                WHEN tp.instrument_type = 'stock' AND sm.stock_mark IS NOT NULL AND sm.stock_mark > 0 THEN
                    ROUND((tp.avg_buy_price * (1 - tp.stop_pct / 100.0) - sm.stock_mark) / sm.stock_mark * 100.0, 2)
            END AS pct_to_stop,

            CASE
                WHEN tp.instrument_type = 'option' AND tp.expiration_date IS NOT NULL THEN
                    CAST(JULIANDAY(tp.expiration_date) - JULIANDAY(date('now')) AS INTEGER)
            END AS dte_remaining,

            CASE
                WHEN tp.time_stop_date IS NOT NULL THEN
                    CAST(JULIANDAY(tp.time_stop_date) - JULIANDAY(date('now')) AS INTEGER)
            END AS days_to_time_stop

        FROM trade_positions tp
        LEFT JOIN option_marks om ON tp.position_key = om.position_key
        LEFT JOIN stock_marks sm ON tp.symbol = sm.symbol AND tp.instrument_type = 'stock'
    """)

    # 2. ta_v_symbol_dashboard ─────────────────────────────────────────
    # 37-col symbol orientation. Aggregations on trade_positions/ta_v_positions_live
    # collapse multi-position symbols to one row (SUM net_qty, AVG pnl_pct).
    cursor.execute("DROP VIEW IF EXISTS ta_v_symbol_dashboard")
    cursor.execute("""
        CREATE VIEW ta_v_symbol_dashboard AS
        SELECT
            sd.symbol, sd.company_name, sd.sector, sd.industry, sd.is_etf,
            sd.liquidity_tier, sd.avg_volume, sd.market_cap_category, sd.beta,
            sd.week_52_high, sd.week_52_low, sd.close_price, sd.pct_of_52w_range,
            sd.iv_front_month, sd.iv_30dte, sd.iv_skew,
            sd.total_open_interest, sd.put_call_ratio, sd.oi_balance_text,
            sd.top_call_display, sd.top_put_display, sd.max_pain,
            sd.alert_count_5d, sd.total_premium_tracked,
            sd.news_sentiment_score, sd.news_sentiment_label, sd.news_article_count,
            sd.next_earnings_date, sd.days_to_earnings,
            sd.options_date, sd.flow_date,

            eu.earnings_time,
            eu.earnings_play_signal,
            eu.relative_underpricing_pct,
            eu.date_confirmed_by,

            tc.catalyst_date,
            tc.catalyst_type,

            COALESCE(tp.net_qty_total, 0) AS net_qty,
            pl.current_pnl_pct
        FROM symbol_dashboard sd
        LEFT JOIN earnings_upcoming eu ON sd.symbol = eu.symbol
        LEFT JOIN (
            -- Earliest open catalyst per symbol. SQLite's MIN() exception
            -- pulls catalyst_type from the row where MIN(catalyst_date) lives.
            SELECT symbol, MIN(catalyst_date) AS catalyst_date, catalyst_type
            FROM trade_calls
            WHERE status IN ('proposed','open') AND catalyst_date IS NOT NULL
            GROUP BY symbol
        ) tc ON sd.symbol = tc.symbol
        LEFT JOIN (
            SELECT symbol, SUM(net_qty) AS net_qty_total
            FROM trade_positions
            GROUP BY symbol
        ) tp ON sd.symbol = tp.symbol
        LEFT JOIN (
            SELECT symbol, AVG(current_pnl_pct) AS current_pnl_pct
            FROM ta_v_positions_live
            GROUP BY symbol
        ) pl ON sd.symbol = pl.symbol
        WHERE sd.symbol IN (
            SELECT symbol FROM trade_positions
            UNION
            SELECT symbol FROM trade_calls WHERE status IN ('proposed','open')
        )
    """)

    # 3. ta_v_position_flow_recent ─────────────────────────────────────
    # Burst-event lens: 5-day flow alerts on universe symbols.
    cursor.execute("DROP VIEW IF EXISTS ta_v_position_flow_recent")
    cursor.execute("""
        CREATE VIEW ta_v_position_flow_recent AS
        SELECT
            fa.trade_date, fa.symbol, fa.strike, fa.option_type, fa.expiration_date,
            fa.dte, fa.moneyness,
            fa.volume, fa.open_interest, fa.next_day_oi,
            fa.oi_resolution, fa.oi_change_contracts,
            fa.premium_value, fa.alert_reason, fa.alert_level,
            fa.roll_detected,
            fa.iv, fa.iv_percentile_30d,
            fa.underlying_price,
            CASE
                WHEN tp.position_key IS NOT NULL THEN 'held'
                ELSE 'tracked'
            END AS scope_reason
        FROM flow_alerts fa
        LEFT JOIN trade_positions tp ON fa.symbol = tp.symbol
        WHERE fa.trade_date >= date('now', '-5 days')
          AND fa.symbol IN (
              SELECT symbol FROM trade_positions
              UNION
              SELECT symbol FROM trade_calls WHERE status IN ('proposed','open')
          )
    """)

    # 4. ta_v_position_oi_context ──────────────────────────────────────
    # Slow-build lens: per-contract OI/IV trend on universe symbols.
    # Mirrors v_oi_timing_context join pattern (today vs yesterday) but with
    # TA scope, OI threshold of 100, and richer columns.
    cursor.execute("DROP VIEW IF EXISTS ta_v_position_oi_context")
    cursor.execute("""
        CREATE VIEW ta_v_position_oi_context AS
        SELECT
            o_today.contract_hash, o_today.symbol, o_today.strike, o_today.option_type,
            o_today.expiration_date, o_today.trade_date, o_today.dte,

            o_today.open_interest,
            o_today.oi_change_5d, o_today.oi_change_pct_5d,
            o_today.oi_change_10d, o_today.oi_change_pct_10d,
            o_today.oi_momentum_5d, o_today.build_pattern,

            o_today.volume, o_today.volume_avg_5d,

            o_today.oi_build_start_date, o_today.oi_build_start_price,

            o_yesterday.underlying_price AS current_price,
            o_yesterday.iv,
            o_yesterday.iv_percentile_20day AS iv_percentile,
            o_today.iv_change_5d,

            CASE
                WHEN o_today.option_type = 'PUT'  AND o_today.oi_build_start_price > o_yesterday.underlying_price
                    THEN 'PREDICTIVE (bought puts when stock was higher)'
                WHEN o_today.option_type = 'PUT'  AND o_today.oi_build_start_price < o_yesterday.underlying_price
                    THEN 'CHASING (bought puts after stock fell)'
                WHEN o_today.option_type = 'CALL' AND o_today.oi_build_start_price < o_yesterday.underlying_price
                    THEN 'PREDICTIVE (bought calls when stock was lower)'
                WHEN o_today.option_type = 'CALL' AND o_today.oi_build_start_price > o_yesterday.underlying_price
                    THEN 'CHASING (bought calls after stock rose)'
                ELSE 'NEUTRAL'
            END AS positioning_type,

            CAST(JULIANDAY(o_today.trade_date) - JULIANDAY(o_today.oi_build_start_date) AS INTEGER) AS oi_build_days_since,
            ROUND((o_yesterday.underlying_price - o_today.oi_build_start_price) / o_today.oi_build_start_price * 100, 2) AS oi_build_price_move_pct,

            CASE
                WHEN tp.position_key IS NOT NULL THEN 'held'
                ELSE 'tracked'
            END AS scope_reason

        FROM option_contracts o_today
        JOIN option_contracts o_yesterday
            ON o_today.contract_hash = o_yesterday.contract_hash
            AND o_yesterday.trade_date = (
                SELECT MAX(trade_date) FROM option_contracts
                WHERE trade_date < (SELECT MAX(trade_date) FROM option_contracts)
            )
        LEFT JOIN trade_positions tp ON o_today.symbol = tp.symbol
        WHERE o_today.symbol IN (
                SELECT symbol FROM trade_positions
                UNION
                SELECT symbol FROM trade_calls WHERE status IN ('proposed','open')
            )
          AND o_today.open_interest > 100
          AND o_today.oi_build_start_date IS NOT NULL
          AND o_today.trade_date = (SELECT MAX(trade_date) FROM option_contracts)
    """)

    conn.commit()


def _ensure_flow_scans_symbol_index(conn):
    """Create idx_flow_scans_symbol_scan on flow_options_scans(symbol, scan_timestamp DESC)
    if it doesn't exist. Required by ta_v_positions_live for fast latest-scan-per-symbol
    lookups against the 26M-row table.

    Reads: nothing
    Writes: flow_options_scans (CREATE INDEX only)
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_flow_scans_symbol_scan'"
    )
    if cursor.fetchone() is None:
        cursor.execute(
            "CREATE INDEX idx_flow_scans_symbol_scan "
            "ON flow_options_scans(symbol, scan_timestamp DESC)"
        )
        conn.commit()
        return True
    return False


# ── Refresh helper ───────────────────────────────────────────────────

def refresh_trade_positions(conn, position_key=None, mirror_conn=None):
    """Recompute trade_positions from trade_executions.

    Args:
        conn: sqlite3 connection to datalake.db (write-active).
        position_key: If given, recompute that one position. If None, full
                      reconciliation across every distinct position_key in
                      trade_executions (plus any orphan rows in trade_positions).
        mirror_conn: Optional pre-opened connection to datalake_query.db. If
                     None, opens one as needed and closes when done. Pass an
                     existing connection if calling from a context that already
                     has one open (e.g., to reuse the txn).

    Behavior per position:
        - net_qty = SUM(buy qty) - SUM(sell qty) over trade_executions.
        - net_qty == 0 with existing row: DELETE the row (mirrored). If a
          trade_call_ref is set, flip that trade_call to status='closed' and
          set closed_at (mirrored).
        - net_qty != 0 with no existing row: INSERT, then attempt auto-link to
          most-recent matching status='proposed' trade_call. On match, copy
          target_pct/stop_pct/time_stop_date and flip the trade_call to 'open'
          (mirrored).
        - net_qty != 0 with existing row: UPDATE the computed columns
          (net_qty, avg_buy_price, total_cost, opened_at, last_action_at)
          and propagate notes from trade_executions (chronological concat
          of all non-null execution notes; NULL preserves existing value
          via COALESCE). User-editable fields (target_pct, stop_pct,
          time_stop_date, trade_call_ref) are preserved.

    Mirroring: quick-sync (db_backup.py) is INSERT-only and cannot propagate
    DELETEs or UPDATEs to existing rows. The refresh helper writes those
    directly to datalake_query.db so the per-turn TA hook and dashboard views
    (which read from query DB) see current state without lag.

    Auto-link match criteria:
        options: symbol + strike + expiration_date + option_type + status='proposed'
        stocks:  symbol + instrument_type='stock' + status='proposed'
        Tiebreaker: latest created_at wins (refined re-pitches beat earlier
        proposals; earlier rows fall to a future 'abandoned' sweep).

    Returns:
        Counter dict with keys: created, updated, deleted, auto_linked, closed_calls.
    """
    if position_key is None:
        keys = [r[0] for r in conn.execute(
            "SELECT DISTINCT position_key FROM trade_executions"
        ).fetchall()]
        # Orphans: trade_positions rows whose key is no longer in trade_executions.
        # Should not happen under normal flow (executions are immutable), but
        # full reconcile cleans them up defensively.
        orphans = [r[0] for r in conn.execute(
            "SELECT position_key FROM trade_positions "
            "WHERE position_key NOT IN (SELECT DISTINCT position_key FROM trade_executions)"
        ).fetchall()]
        keys.extend(orphans)
    else:
        keys = [position_key]

    own_mirror = False
    if mirror_conn is None:
        query_db = os.path.join(project_root, 'data', 'datalake_query.db')
        if os.path.exists(query_db):
            mirror_conn = sqlite3.connect(query_db)
            own_mirror = True

    counters = {'created': 0, 'updated': 0, 'deleted': 0, 'auto_linked': 0, 'closed_calls': 0}

    try:
        for key in keys:
            result = _refresh_one_position(conn, mirror_conn, key)
            for k, v in result.items():
                counters[k] += v
        conn.commit()
        if mirror_conn:
            mirror_conn.commit()
    finally:
        if own_mirror and mirror_conn:
            mirror_conn.close()

    return counters


def _refresh_one_position(conn, mirror_conn, position_key):
    """Process a single position_key. Returns counter dict."""
    counters = {'created': 0, 'updated': 0, 'deleted': 0, 'auto_linked': 0, 'closed_calls': 0}

    agg = _aggregate_executions(conn, position_key)
    existing = conn.execute(
        "SELECT trade_call_ref FROM trade_positions WHERE position_key = ?",
        (position_key,)
    ).fetchone()

    # No executions for this key (orphan or never existed).
    if agg is None:
        if existing is not None:
            _delete_position(conn, mirror_conn, position_key)
            counters['deleted'] = 1
            # Don't auto-close trade_call: orphan state means we can't confirm
            # the position actually opened/closed via real fills.
        return counters

    net_qty = agg['net_qty']

    # Position closed (net_qty hit zero).
    if net_qty == 0:
        if existing is not None:
            trade_call_ref = existing[0]
            _delete_position(conn, mirror_conn, position_key)
            counters['deleted'] = 1
            if trade_call_ref is not None:
                _close_trade_call(conn, mirror_conn, trade_call_ref)
                counters['closed_calls'] = 1
        return counters

    # Position open: compute aggregates.
    avg_buy_price = (
        round(agg['buy_total_value'] / agg['buy_total_qty'], 4)
        if agg['buy_total_qty'] > 0 else None
    )
    total_cost = round(agg['net_total_cost'], 2) if agg['net_total_cost'] is not None else None

    if existing is None:
        link_info = _try_auto_link(conn, mirror_conn, agg)
        target_pct = link_info['target_pct'] if link_info else None
        stop_pct = link_info['stop_pct'] if link_info else None
        time_stop_date = link_info['time_stop_date'] if link_info else None
        trade_call_ref = link_info['id'] if link_info else None

        insert_sql = """
            INSERT INTO trade_positions (
                position_key, symbol, instrument_type, strike, option_type, expiration_date,
                net_qty, avg_buy_price, total_cost, opened_at, last_action_at,
                target_pct, stop_pct, time_stop_date, trade_call_ref, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        insert_params = (position_key, agg['symbol'], agg['instrument_type'],
                         agg['strike'], agg['option_type'], agg['expiration_date'],
                         net_qty, avg_buy_price, total_cost, agg['opened_at'], agg['last_action_at'],
                         target_pct, stop_pct, time_stop_date, trade_call_ref, agg['notes_concat'])
        conn.execute(insert_sql, insert_params)
        if mirror_conn is not None:
            mirror_conn.execute(insert_sql, insert_params)
        counters['created'] = 1
        if link_info is not None:
            counters['auto_linked'] = 1
    else:
        # COALESCE on notes: when no executions have non-null notes, agg['notes_concat']
        # is NULL and the existing trade_positions.notes value is preserved. Any non-null
        # concatenation overwrites — chronological recompute, so we always reflect the
        # current set of execution notes rather than appending blindly.
        update_sql = """
            UPDATE trade_positions
               SET net_qty = ?, avg_buy_price = ?, total_cost = ?,
                   opened_at = ?, last_action_at = ?,
                   notes = COALESCE(?, notes)
             WHERE position_key = ?
        """
        update_params = (net_qty, avg_buy_price, total_cost,
                         agg['opened_at'], agg['last_action_at'], agg['notes_concat'], position_key)
        conn.execute(update_sql, update_params)
        if mirror_conn is not None:
            mirror_conn.execute(update_sql, update_params)
        counters['updated'] = 1

    return counters


def _aggregate_executions(conn, position_key):
    """Aggregate trade_executions for one position_key. Returns dict or None."""
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN action='buy' THEN quantity ELSE -quantity END),
            SUM(CASE WHEN action='buy' THEN quantity * fill_price ELSE 0 END),
            SUM(CASE WHEN action='buy' THEN quantity ELSE 0 END),
            SUM(CASE WHEN action='buy' THEN total_cost ELSE -total_cost END),
            MIN(CASE WHEN action='buy' THEN execution_timestamp END),
            MAX(execution_timestamp),
            MAX(symbol), MAX(instrument_type),
            MAX(strike), MAX(option_type), MAX(expiration_date)
        FROM trade_executions
        WHERE position_key = ?
    """, (position_key,)).fetchone()

    if row is None or row[0] is None:
        return None

    # Normalize option_type to uppercase ('CALL'/'PUT') for consistency with
    # trade_calls and option_contracts. trade_executions stores lowercase
    # (carried over from the CLI/email parser, which match flow_alerts case);
    # trade_positions and trade_calls use uppercase per proposal convention.
    # Without this, _try_auto_link's WHERE option_type = ? misses matches.
    option_type = row[9].upper() if row[9] else None

    note_rows = conn.execute("""
        SELECT execution_timestamp, action, notes
        FROM trade_executions
        WHERE position_key = ? AND notes IS NOT NULL AND TRIM(notes) != ''
        ORDER BY execution_timestamp ASC, id ASC
    """, (position_key,)).fetchall()

    notes_concat = None
    if note_rows:
        lines = []
        for ts, action, note in note_rows:
            date_part = (ts or '')[:10] or '????-??-??'
            lines.append("{} {}: {}".format(date_part, action, note.strip()))
        notes_concat = "\n".join(lines)

    return {
        'net_qty': int(row[0]),
        'buy_total_value': row[1] or 0.0,
        'buy_total_qty': int(row[2] or 0),
        'net_total_cost': row[3],
        'opened_at': row[4],
        'last_action_at': row[5],
        'symbol': row[6],
        'instrument_type': row[7],
        'strike': row[8],
        'option_type': option_type,
        'expiration_date': row[10],
        'notes_concat': notes_concat,
    }


def _delete_position(conn, mirror_conn, position_key):
    """DELETE the trade_positions row in production AND query DB."""
    conn.execute("DELETE FROM trade_positions WHERE position_key = ?", (position_key,))
    if mirror_conn is not None:
        mirror_conn.execute("DELETE FROM trade_positions WHERE position_key = ?", (position_key,))


def _try_auto_link(conn, mirror_conn, agg):
    """Find a matching status='proposed' trade_call. If found, flip its status
    to 'open' (in both DBs) and return its target/stop/time_stop fields.
    Tiebreaker: latest created_at wins.

    Returns: dict with id/target_pct/stop_pct/time_stop_date, or None if no match.
    """
    if agg['instrument_type'] == 'option':
        match = conn.execute("""
            SELECT id, target_pct, stop_pct, time_stop_date
            FROM trade_calls
            WHERE symbol = ? AND instrument_type = 'option'
              AND strike = ? AND expiration_date = ? AND option_type = ?
              AND status = 'proposed'
            ORDER BY created_at DESC
            LIMIT 1
        """, (agg['symbol'], agg['strike'], agg['expiration_date'], agg['option_type'])).fetchone()
    else:
        match = conn.execute("""
            SELECT id, target_pct, stop_pct, time_stop_date
            FROM trade_calls
            WHERE symbol = ? AND instrument_type = 'stock'
              AND status = 'proposed'
            ORDER BY created_at DESC
            LIMIT 1
        """, (agg['symbol'],)).fetchone()

    if match is None:
        return None

    trade_call_id, target_pct, stop_pct, time_stop = match
    conn.execute("UPDATE trade_calls SET status = 'open' WHERE id = ?", (trade_call_id,))
    if mirror_conn is not None:
        mirror_conn.execute("UPDATE trade_calls SET status = 'open' WHERE id = ?", (trade_call_id,))

    return {'id': trade_call_id, 'target_pct': target_pct,
            'stop_pct': stop_pct, 'time_stop_date': time_stop}


def _close_trade_call(conn, mirror_conn, trade_call_id):
    """Flip a linked trade_call to status='closed' (in both DBs).
    Sets closed_at to now. outcome_pct + grade_notes are filled in later by TA."""
    closed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        "UPDATE trade_calls SET status = 'closed', closed_at = ? WHERE id = ?",
        (closed_at, trade_call_id)
    )
    if mirror_conn is not None:
        mirror_conn.execute(
            "UPDATE trade_calls SET status = 'closed', closed_at = ? WHERE id = ?",
            (closed_at, trade_call_id)
        )


# ── CLI ──────────────────────────────────────────────────────────────

def _cmd_init(args):
    """Phase 1 setup: create tables + flow_options_scans index in datalake.db."""
    db_path = args.db or os.path.join(project_root, 'data', 'datalake.db')
    if not os.path.exists(db_path):
        logger.error("Database not found: {}".format(db_path))
        return 1

    beautiful_log("Initializing trade_positions / trade_calls schema in {}".format(db_path), 'info')

    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        beautiful_log("Tables ready: trade_calls, trade_positions", 'success')

        index_created = _ensure_flow_scans_symbol_index(conn)
        if index_created:
            beautiful_log("Created index idx_flow_scans_symbol_scan on flow_options_scans", 'success')
        else:
            beautiful_log("Index idx_flow_scans_symbol_scan already exists", 'info')
    finally:
        conn.close()

    return 0


def _cmd_init_views(args):
    """Phase 3 setup: create the four TA-scoped views in datalake.db.

    Defining views in datalake.db (NOT datalake_query.db) so the page-level
    full sync propagates them. Defining only in query DB would have them
    erased on every nightly full sync.
    """
    db_path = args.db or os.path.join(project_root, 'data', 'datalake.db')
    if not os.path.exists(db_path):
        logger.error("Database not found: {}".format(db_path))
        return 1

    beautiful_log("Creating TA-scoped views in {}".format(db_path), 'info')

    conn = sqlite3.connect(db_path)
    try:
        _ensure_views(conn)
        beautiful_log(
            "Views ready: ta_v_positions_live, ta_v_symbol_dashboard, "
            "ta_v_position_flow_recent, ta_v_position_oi_context",
            'success'
        )
    finally:
        conn.close()

    return 0


def _cmd_reconcile(args):
    """Full rebuild of trade_positions from trade_executions. Used for initial
    seeding and manual recovery. DELETEs orphans, INSERTs missing positions
    (with auto-link), UPDATEs existing positions to current aggregates."""
    db_path = args.db or os.path.join(project_root, 'data', 'datalake.db')
    if not os.path.exists(db_path):
        logger.error("Database not found: {}".format(db_path))
        return 1

    beautiful_log("Reconciling trade_positions from trade_executions in {}".format(db_path), 'info')

    conn = sqlite3.connect(db_path)
    try:
        counters = refresh_trade_positions(conn)
        beautiful_log(
            "Reconcile complete: created={} updated={} deleted={} auto_linked={} closed_calls={}".format(
                counters['created'], counters['updated'], counters['deleted'],
                counters['auto_linked'], counters['closed_calls']
            ),
            'success'
        )
    finally:
        conn.close()

    return 0


def main():
    parser = argparse.ArgumentParser(description="Trade positions & trade calls — schema management")
    parser.add_argument('--init', action='store_true',
                        help="Create tables + flow_options_scans index (Phase 1 setup)")
    parser.add_argument('--init-views', action='store_true',
                        help="Create the four TA-scoped views (Phase 3 setup; idempotent — drops + recreates)")
    parser.add_argument('--reconcile', action='store_true',
                        help="Full rebuild of trade_positions from trade_executions (Phase 2c)")
    parser.add_argument('--db', help="Override database path (default: data/datalake.db)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if args.init:
        return _cmd_init(args)
    if args.init_views:
        return _cmd_init_views(args)
    if args.reconcile:
        return _cmd_reconcile(args)

    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
