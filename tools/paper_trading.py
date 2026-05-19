#!/usr/bin/env python3
"""
Paper Trading — Shared Schema & Persistence Helpers
===================================================
Common functions used by both `tools/paper_trade.py` (CLI),
`tools/paper_poll.py` (order/balance polling), and
`tools/paper_close_engine.py` (Phase B auto-close engine).

Tables (all in `data/paper.db`):
  - paper_executions          immutable log of fills
  - paper_positions           current/closed position rows
                              status: 'open' | 'closing' | 'closed'
  - paper_account_snapshots   daily balance snapshot

Phase B moved paper_* tables out of data/datalake.db to eliminate
write-lock contention with Flow Monitor's intraday scans. Migration is
a one-shot via `paper_migrate_to_paper_db.py`.

Position-key convention is reused from `trade_ingest._make_position_key()`
so paper and real positions share the same key format.

Close conditions (Phase B) live in `paper_positions.close_conditions_json`.
NULL by default — the close engine ignores positions with no conditions
set. Schema documented in `parse_close_conditions()` below.

Reads/writes: data/paper.db
Dependencies: tools/trade_ingest.py (_make_position_key), tools/decimal_formatter.py
"""

import json
import logging
import os
import sqlite3
import sys
from datetime import datetime

# Project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from decimal_formatter import clean_database_row
from trade_ingest import _make_position_key
from timezone_utils import now_eastern

logger = logging.getLogger(__name__)

PAPER_DB_PATH = os.path.join(project_root, 'data', 'paper.db')

# Option contract multiplier (1 contract = 100 shares)
OPTION_MULTIPLIER = 100

# Close-conditions JSON schema version. Bump when adding fields.
CLOSE_CONDITIONS_SCHEMA_VERSION = 1

# Valid status values for paper_positions
POSITION_STATUSES = ('open', 'closing', 'closed')


# ── Connection ───────────────────────────────────────────────────────

def get_connection():
    """Open a connection to data/paper.db with Row factory.

    Phase B moved paper_* tables out of data/datalake.db to avoid
    write-lock contention with Flow Monitor.
    """
    conn = sqlite3.connect(PAPER_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema ───────────────────────────────────────────────────────────

def _ensure_schema(conn):
    """Create paper_* tables and indexes if they don't exist. Idempotent.

    Reads: nothing
    Writes: paper_executions, paper_positions, paper_account_snapshots (CREATE)
    """
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_timestamp DATETIME,
            action TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            fill_price REAL NOT NULL,
            total_cost REAL,
            option_type TEXT,
            strike REAL,
            expiration_date DATE,
            option_symbol TEXT,
            position_key TEXT NOT NULL,
            tag TEXT NOT NULL DEFAULT 'manual',
            source_event_id TEXT,
            tradier_order_id TEXT,
            broker TEXT NOT NULL DEFAULT 'tradier_sandbox',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tag, source_event_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_key TEXT NOT NULL,
            tag TEXT NOT NULL,
            instrument_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            option_symbol TEXT,
            option_type TEXT,
            strike REAL,
            expiration_date DATE,
            quantity REAL NOT NULL,
            cost_basis_per_unit REAL,
            total_cost REAL,
            opened_at DATETIME,
            opening_execution_id INTEGER REFERENCES paper_executions(id),
            closed_at DATETIME,
            closing_execution_id INTEGER REFERENCES paper_executions(id),
            exit_price_per_unit REAL,
            realized_pnl REAL,
            close_reason TEXT,
            close_conditions_json TEXT,
            closing_submitted_at DATETIME,
            status TEXT NOT NULL DEFAULT 'open',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Phase B addition: closing_submitted_at column for DBs created before B
    cursor.execute("PRAGMA table_info(paper_positions)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if 'closing_submitted_at' not in existing_cols:
        cursor.execute("ALTER TABLE paper_positions ADD COLUMN closing_submitted_at DATETIME")

    # Phase B: bridge table from --open submission to fill-time position
    # creation. cmd_open writes a row here keyed by tradier_order_id; the
    # poller pops it when processing the fill and copies close_conditions_json
    # to the new paper_positions row.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_pending_conditions (
            tradier_order_id TEXT PRIMARY KEY,
            close_conditions_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_account_snapshots (
            snapshot_date DATE PRIMARY KEY,
            total_equity REAL,
            cash REAL,
            long_market_value REAL,
            short_market_value REAL,
            open_pl REAL,
            close_pl REAL,
            buying_power REAL,
            option_buying_power REAL,
            raw_response_json TEXT,
            snapshotted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing = {row[0] for row in cursor.fetchall()}

    if 'idx_paper_executions_symbol' not in existing:
        cursor.execute("CREATE INDEX idx_paper_executions_symbol ON paper_executions(symbol)")
    if 'idx_paper_executions_position_key' not in existing:
        cursor.execute("CREATE INDEX idx_paper_executions_position_key ON paper_executions(position_key)")
    if 'idx_paper_executions_tag' not in existing:
        cursor.execute("CREATE INDEX idx_paper_executions_tag ON paper_executions(tag)")
    if 'idx_paper_executions_tradier_order_id' not in existing:
        cursor.execute("CREATE INDEX idx_paper_executions_tradier_order_id ON paper_executions(tradier_order_id)")
    if 'idx_paper_positions_status_symbol' not in existing:
        cursor.execute("CREATE INDEX idx_paper_positions_status_symbol ON paper_positions(status, symbol)")
    if 'idx_paper_positions_tag_status' not in existing:
        cursor.execute("CREATE INDEX idx_paper_positions_tag_status ON paper_positions(tag, status)")

    conn.commit()


# ── Helpers ──────────────────────────────────────────────────────────

def _is_closing_action(action):
    """Return True if the action closes (or reduces) an existing position."""
    a = (action or '').lower()
    return a in ('sell', 'sell_to_close', 'buy_to_close')


# ── Close-Conditions Helpers (Phase B) ───────────────────────────────

# Vocabulary of close conditions. Field name → expected Python type (for
# validation). All fields nullable; null = condition inactive.
CLOSE_CONDITION_FIELDS = {
    'take_profit_pct': float,
    'stop_loss_pct': float,
    'max_hold_days': int,
    'expire_before_dte': int,
    'underlying_target_above': float,
    'underlying_target_below': float,
}


def parse_close_conditions(json_str):
    """Decode a paper_positions.close_conditions_json string into a dict.

    Returns a dict with every field in CLOSE_CONDITION_FIELDS, defaulting
    absent/null fields to None. Returns None if input is None or empty.
    Malformed JSON returns None and logs a warning (engine should skip
    the position rather than crash).

    Schema:
        {
            "schema_version": 1,
            "take_profit_pct": 25.0,         # close when pnl_pct >= value
            "stop_loss_pct": -30.0,          # close when pnl_pct <= value
            "max_hold_days": 5,              # close after N calendar days
            "expire_before_dte": 1,          # close option at <= N DTE
            "underlying_target_above": 750,  # close when underlying >= value
            "underlying_target_below": 720,  # close when underlying <= value
        }

    Any field may be null; the engine treats null as "condition inactive."
    """
    if not json_str:
        return None
    try:
        raw = json.loads(json_str)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Malformed close_conditions_json: %s — %s", json_str, e)
        return None
    if not isinstance(raw, dict):
        logger.warning("close_conditions_json is not a dict: %r", raw)
        return None
    out = {'schema_version': raw.get('schema_version', CLOSE_CONDITIONS_SCHEMA_VERSION)}
    for field in CLOSE_CONDITION_FIELDS:
        out[field] = raw.get(field)
    return out


def build_close_conditions(take_profit_pct=None, stop_loss_pct=None,
                           max_hold_days=None, expire_before_dte=None,
                           underlying_target_above=None,
                           underlying_target_below=None):
    """Build a close_conditions JSON string from individual flag values.

    Returns None if all conditions are None (= NULL in DB column).
    Otherwise returns a JSON string with schema_version set and absent
    fields stored as null (so the JSON shape stays stable).

    Use at --open time and --update-conditions time. The CLI's flag
    parser maps argparse args directly into the kwargs here.
    """
    values = {
        'take_profit_pct': take_profit_pct,
        'stop_loss_pct': stop_loss_pct,
        'max_hold_days': max_hold_days,
        'expire_before_dte': expire_before_dte,
        'underlying_target_above': underlying_target_above,
        'underlying_target_below': underlying_target_below,
    }
    if all(v is None for v in values.values()):
        return None

    # Type-validate provided values
    for field, value in values.items():
        if value is None:
            continue
        expected = CLOSE_CONDITION_FIELDS[field]
        try:
            values[field] = expected(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"close condition {field!r}={value!r} not {expected.__name__}: {e}")

    payload = {'schema_version': CLOSE_CONDITIONS_SCHEMA_VERSION, **values}
    return json.dumps(payload)


def summarize_close_conditions(json_str):
    """Render a terse one-line summary of conditions for `--positions` output.

    Returns 'unmonitored' if no conditions, else 'TP+25/SL-30/5d/...'
    """
    conds = parse_close_conditions(json_str)
    if conds is None:
        return 'unmonitored'
    parts = []
    if conds.get('take_profit_pct') is not None:
        parts.append(f"TP+{conds['take_profit_pct']:g}")
    if conds.get('stop_loss_pct') is not None:
        parts.append(f"SL{conds['stop_loss_pct']:+g}")
    if conds.get('max_hold_days') is not None:
        parts.append(f"{conds['max_hold_days']}d")
    if conds.get('expire_before_dte') is not None:
        parts.append(f"dte<={conds['expire_before_dte']}")
    if conds.get('underlying_target_above') is not None:
        parts.append(f">${conds['underlying_target_above']:g}")
    if conds.get('underlying_target_below') is not None:
        parts.append(f"<${conds['underlying_target_below']:g}")
    return '/'.join(parts) if parts else 'unmonitored'


def _compute_total_cost(quantity, fill_price, instrument_type):
    """qty * fill_price * multiplier (100 for option, 1 for stock)."""
    if quantity is None or fill_price is None:
        return None
    multiplier = OPTION_MULTIPLIER if instrument_type == 'option' else 1
    return float(quantity) * float(fill_price) * multiplier


def make_position_key_from_execution(exec_dict):
    """Build position_key from an execution dict using shared convention."""
    return _make_position_key(
        symbol=exec_dict['symbol'],
        instrument_type=exec_dict['instrument_type'],
        option_type=exec_dict.get('option_type'),
        strike=exec_dict.get('strike'),
        expiration_date=exec_dict.get('expiration_date'),
    )


# ── Persistence ──────────────────────────────────────────────────────

def record_execution(conn, execution):
    """Insert a fill row into paper_executions.

    Args:
        conn: sqlite3.Connection
        execution: dict with keys matching paper_executions columns.
            Required: action, instrument_type, symbol, quantity, fill_price.
            Optional: execution_timestamp, option_type, strike, expiration_date,
                      option_symbol, tag, source_event_id, tradier_order_id,
                      broker, notes.

    Returns:
        int — the new row's `id`.

    Raises:
        sqlite3.IntegrityError on duplicate (tag, source_event_id).
    """
    # Defaults
    exec_row = dict(execution)
    exec_row.setdefault('execution_timestamp', now_eastern().isoformat(sep=' ', timespec='seconds'))
    exec_row.setdefault('tag', 'manual')
    exec_row.setdefault('broker', 'tradier_sandbox')
    exec_row.setdefault('option_symbol', None)
    exec_row.setdefault('option_type', None)
    exec_row.setdefault('strike', None)
    exec_row.setdefault('expiration_date', None)
    exec_row.setdefault('source_event_id', None)
    exec_row.setdefault('tradier_order_id', None)
    exec_row.setdefault('notes', None)

    # Compute total_cost if not provided
    if exec_row.get('total_cost') is None:
        exec_row['total_cost'] = _compute_total_cost(
            exec_row.get('quantity'),
            exec_row.get('fill_price'),
            exec_row.get('instrument_type'),
        )

    # Compute position_key if not provided
    if not exec_row.get('position_key'):
        exec_row['position_key'] = make_position_key_from_execution(exec_row)

    # clean_database_row may nullify strings not in skip list (option_symbol,
    # tag, source_event_id, tradier_order_id). Restore them after the call.
    preserved = {
        'option_symbol': exec_row.get('option_symbol'),
        'tag': exec_row.get('tag'),
        'source_event_id': exec_row.get('source_event_id'),
        'tradier_order_id': exec_row.get('tradier_order_id'),
        'execution_timestamp': exec_row.get('execution_timestamp'),
        'expiration_date': exec_row.get('expiration_date'),
    }
    cleaned = clean_database_row(exec_row)
    for k, v in preserved.items():
        cleaned[k] = v

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO paper_executions (
            execution_timestamp, action, instrument_type, symbol, quantity,
            fill_price, total_cost, option_type, strike, expiration_date,
            option_symbol, position_key, tag, source_event_id,
            tradier_order_id, broker, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cleaned.get('execution_timestamp'),
        cleaned.get('action'),
        cleaned.get('instrument_type'),
        cleaned.get('symbol'),
        cleaned.get('quantity'),
        cleaned.get('fill_price'),
        cleaned.get('total_cost'),
        cleaned.get('option_type'),
        cleaned.get('strike'),
        cleaned.get('expiration_date'),
        cleaned.get('option_symbol'),
        cleaned.get('position_key'),
        cleaned.get('tag'),
        cleaned.get('source_event_id'),
        cleaned.get('tradier_order_id'),
        cleaned.get('broker'),
        cleaned.get('notes'),
    ))
    conn.commit()
    return cursor.lastrowid


def open_or_update_position(conn, execution, execution_id):
    """Open a new position row on a BUY, or close/reduce one on a SELL.

    Args:
        conn: sqlite3.Connection
        execution: same dict shape used in record_execution()
        execution_id: rowid returned by record_execution()

    Behavior:
        - Opening fill (buy / buy_to_open / sell_to_open):
            INSERT a new paper_positions row with status='open'.
            If a matching open row exists (same position_key + tag), average
            in by recomputing cost_basis_per_unit (weighted by quantity).
        - Closing fill (sell / sell_to_close / buy_to_close):
            UPDATE the matching open row to status='closed', set realized_pnl.
    """
    cursor = conn.cursor()
    instrument_type = execution.get('instrument_type')
    multiplier = OPTION_MULTIPLIER if instrument_type == 'option' else 1
    quantity = float(execution.get('quantity', 0))
    fill_price = float(execution.get('fill_price', 0))
    position_key = execution.get('position_key') or make_position_key_from_execution(execution)
    tag = execution.get('tag', 'manual')
    closing = _is_closing_action(execution.get('action'))

    if closing:
        # Close the oldest open-or-closing position with matching key+tag.
        # 'closing' is the Phase B intermediate state set when an engine or
        # manual --close has submitted a close order but the fill hasn't
        # been recorded yet.
        cursor.execute("""
            SELECT id, quantity, cost_basis_per_unit, realized_pnl, status
            FROM paper_positions
            WHERE position_key = ? AND tag = ? AND status IN ('open', 'closing')
            ORDER BY opened_at ASC, id ASC
            LIMIT 1
        """, (position_key, tag))
        row = cursor.fetchone()
        if not row:
            logger.warning(
                "No open paper_positions row for position_key=%s tag=%s — closing fill recorded but not matched",
                position_key, tag
            )
            return None

        pos_id = row['id']
        existing_qty = float(row['quantity'] or 0)
        cost_basis = float(row['cost_basis_per_unit'] or 0)
        prior_realized = float(row['realized_pnl'] or 0)

        # Sold quantity is capped at existing — extras (shouldn't normally happen)
        # are logged and dropped on the floor for this row. Caller can open a
        # short row separately if that's the intent.
        close_qty = min(quantity, existing_qty)
        if close_qty < quantity:
            logger.warning(
                "Closing qty %s exceeds open qty %s for position_id=%s; closing %s, ignoring excess",
                quantity, existing_qty, pos_id, close_qty,
            )

        leg_pnl = (fill_price - cost_basis) * close_qty * multiplier
        new_realized = prior_realized + leg_pnl
        remaining_qty = existing_qty - close_qty
        closed_at = execution.get('execution_timestamp') or now_eastern().isoformat(sep=' ', timespec='seconds')

        if remaining_qty <= 0:
            # Full close — flip status, set terminal fields
            cursor.execute("""
                UPDATE paper_positions
                SET quantity = 0,
                    status = 'closed',
                    closed_at = ?,
                    closing_execution_id = ?,
                    exit_price_per_unit = ?,
                    realized_pnl = ?,
                    close_reason = COALESCE(close_reason, 'manual'),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (closed_at, execution_id, fill_price, new_realized, pos_id))
        else:
            # Partial close — decrement qty, accumulate realized_pnl, keep open
            new_total_cost = remaining_qty * cost_basis * multiplier
            cursor.execute("""
                UPDATE paper_positions
                SET quantity = ?,
                    total_cost = ?,
                    closing_execution_id = ?,
                    exit_price_per_unit = ?,
                    realized_pnl = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (remaining_qty, new_total_cost, execution_id, fill_price, new_realized, pos_id))
        conn.commit()
        return pos_id

    # Opening fill — average in if an open row exists
    cursor.execute("""
        SELECT id, quantity, cost_basis_per_unit, total_cost
        FROM paper_positions
        WHERE position_key = ? AND tag = ? AND status = 'open'
        ORDER BY opened_at ASC, id ASC
        LIMIT 1
    """, (position_key, tag))
    existing = cursor.fetchone()

    if existing:
        new_qty = float(existing['quantity']) + quantity
        if new_qty == 0:
            new_cost_basis = 0.0
        else:
            prior_cost = float(existing['cost_basis_per_unit'] or 0) * float(existing['quantity'])
            new_cost_basis = (prior_cost + fill_price * quantity) / new_qty
        new_total_cost = new_qty * new_cost_basis * multiplier
        cursor.execute("""
            UPDATE paper_positions
            SET quantity = ?, cost_basis_per_unit = ?, total_cost = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_qty, new_cost_basis, new_total_cost, existing['id']))
        conn.commit()
        return existing['id']

    # Fresh open. close_conditions_json may be supplied via the execution
    # dict (paper_poll pops it from paper_pending_conditions before calling).
    total_cost = _compute_total_cost(quantity, fill_price, instrument_type)
    opened_at = execution.get('execution_timestamp') or now_eastern().isoformat(sep=' ', timespec='seconds')
    close_conditions_json = execution.get('close_conditions_json')
    cursor.execute("""
        INSERT INTO paper_positions (
            position_key, tag, instrument_type, symbol, option_symbol,
            option_type, strike, expiration_date, quantity,
            cost_basis_per_unit, total_cost, opened_at,
            opening_execution_id, close_conditions_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
    """, (
        position_key,
        tag,
        instrument_type,
        execution.get('symbol'),
        execution.get('option_symbol'),
        execution.get('option_type'),
        execution.get('strike'),
        execution.get('expiration_date'),
        quantity,
        fill_price,
        total_cost,
        opened_at,
        execution_id,
        close_conditions_json,
    ))
    conn.commit()
    return cursor.lastrowid


# ── Pending-Conditions Bridge (Phase B) ───────────────────────────────

def set_pending_conditions(conn, tradier_order_id, close_conditions_json):
    """Stash close conditions for a pending --open order.

    Called by cmd_open after broker submits the order. The poller pops this
    row when the fill is recorded and copies the JSON to paper_positions.
    """
    if not tradier_order_id or not close_conditions_json:
        return
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO paper_pending_conditions
            (tradier_order_id, close_conditions_json)
        VALUES (?, ?)
    """, (str(tradier_order_id), close_conditions_json))
    conn.commit()


def pop_pending_conditions(conn, tradier_order_id):
    """Read + delete a pending-conditions row by tradier_order_id.

    Returns the close_conditions_json string, or None if no pending row.
    Safe to call multiple times — second call returns None.
    """
    if not tradier_order_id:
        return None
    cursor = conn.cursor()
    cursor.execute("""
        SELECT close_conditions_json
        FROM paper_pending_conditions
        WHERE tradier_order_id = ?
    """, (str(tradier_order_id),))
    row = cursor.fetchone()
    if not row:
        return None
    cursor.execute(
        "DELETE FROM paper_pending_conditions WHERE tradier_order_id = ?",
        (str(tradier_order_id),),
    )
    conn.commit()
    return row[0]


def snapshot_balance(conn, balances):
    """Insert (or replace) today's row in paper_account_snapshots.

    Args:
        conn: sqlite3.Connection
        balances: dict — the `balances` object from
                  Tradier GET /accounts/{id}/balances. Tradier nests cash/margin
                  details under sub-objects depending on account type.
    """
    today = now_eastern().date().isoformat()

    # Tradier returns either {'balances': {...}} or just {...}; normalize.
    bal = balances.get('balances', balances) if isinstance(balances, dict) else {}

    total_equity = bal.get('total_equity')
    open_pl = bal.get('open_pl')
    close_pl = bal.get('close_pl')
    long_mv = bal.get('long_market_value')
    short_mv = bal.get('short_market_value')

    # Cash & buying power may be on top-level or nested in 'cash' / 'margin' / 'pdt' sub-objects.
    cash = bal.get('total_cash')
    if cash is None:
        for sub in ('cash', 'margin', 'pdt'):
            sub_obj = bal.get(sub) or {}
            if isinstance(sub_obj, dict) and sub_obj.get('cash_available') is not None:
                cash = sub_obj.get('cash_available')
                break

    buying_power = None
    option_buying_power = None
    for sub in ('cash', 'margin', 'pdt'):
        sub_obj = bal.get(sub) or {}
        if isinstance(sub_obj, dict):
            if buying_power is None and sub_obj.get('stock_buying_power') is not None:
                buying_power = sub_obj.get('stock_buying_power')
            if option_buying_power is None and sub_obj.get('option_buying_power') is not None:
                option_buying_power = sub_obj.get('option_buying_power')

    raw_json = json.dumps(balances, default=str)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO paper_account_snapshots (
            snapshot_date, total_equity, cash, long_market_value,
            short_market_value, open_pl, close_pl, buying_power,
            option_buying_power, raw_response_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        today, total_equity, cash, long_mv, short_mv,
        open_pl, close_pl, buying_power, option_buying_power, raw_json,
    ))
    conn.commit()
    return today
