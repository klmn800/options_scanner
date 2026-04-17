"""
Symbol Lifecycle Audit Trail (audit.py)
---------------------------------------
Manages the symbol_lifecycle_events table in datalake.db.
Logs all onboarding, offboarding, purgatory, and suspect events.

Table: symbol_lifecycle_events
  event_id        INTEGER PRIMARY KEY AUTOINCREMENT
  symbol          TEXT NOT NULL (indexed)
  event_type      TEXT NOT NULL
  event_date      DATE NOT NULL
  event_timestamp TEXT NOT NULL
  tier            TEXT
  reason          TEXT
  operator        TEXT NOT NULL
  metadata_json   TEXT

PRD 0013 — Symbol Lifecycle Management
"""

import json
import os
import sqlite3
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.timezone_utils import now_eastern


def get_default_db_path():
    """Get path to datalake.db"""
    return os.path.join(project_root, 'data', 'datalake.db')


def _ensure_lifecycle_table(conn):
    """Create symbol_lifecycle_events table if it doesn't exist.

    Called lazily on first use from any audit function.
    """
    conn.execute('''
        CREATE TABLE IF NOT EXISTS symbol_lifecycle_events (
            event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            event_type      TEXT NOT NULL,
            event_date      DATE NOT NULL,
            event_timestamp TEXT NOT NULL,
            tier            TEXT,
            reason          TEXT,
            operator        TEXT NOT NULL,
            metadata_json   TEXT
        )
    ''')
    # Index for symbol lookups and recent-event queries
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_lifecycle_symbol
        ON symbol_lifecycle_events (symbol)
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_lifecycle_event_date
        ON symbol_lifecycle_events (event_date)
    ''')


def log_lifecycle_event(db_path, symbol, event_type, tier, reason, operator, metadata_dict=None):
    """Log a lifecycle event to the audit trail.

    Args:
        db_path: Path to datalake.db
        symbol: Stock ticker
        event_type: One of: onboarded, offboarded, purgatory_added,
                    purgatory_restored, suspect_detected, suspect_classified,
                    rename_from, rename_to
        tier: Current tier at time of event (fm_universe, daily_only, purgatory, removed)
        reason: Free-form reason text
        operator: Who triggered this (human, autofix, collector, health_check)
        metadata_dict: Optional dict of extra context (serialized to JSON)

    Returns:
        int: The event_id of the inserted row
    """
    now = now_eastern()
    event_date = now.strftime('%Y-%m-%d')
    event_timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    metadata_json = json.dumps(metadata_dict) if metadata_dict else None

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        _ensure_lifecycle_table(conn)
        cursor = conn.execute('''
            INSERT INTO symbol_lifecycle_events
            (symbol, event_type, event_date, event_timestamp, tier, reason, operator, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, event_type, event_date, event_timestamp, tier, reason, operator, metadata_json))
        conn.commit()
        return cursor.lastrowid


def get_recent_events(db_path, days=30):
    """Get lifecycle events from the last N days.

    Args:
        db_path: Path to datalake.db
        days: Lookback window in calendar days

    Returns:
        list[dict]: Events sorted by event_timestamp descending
    """
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        _ensure_lifecycle_table(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT * FROM symbol_lifecycle_events
            WHERE event_date >= date('now', ?)
            ORDER BY event_timestamp DESC
        ''', (f'-{days} days',)).fetchall()
        return [dict(r) for r in rows]


def get_pending_suspects(db_path):
    """Get suspect_detected events with no subsequent resolution.

    A suspect is "pending" if there's a suspect_detected event for a symbol
    but no later offboarded, purgatory_restored, or suspect_classified event.

    Returns:
        list[dict]: Pending suspect events
    """
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        _ensure_lifecycle_table(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('''
            SELECT s.* FROM symbol_lifecycle_events s
            WHERE s.event_type = 'suspect_detected'
              AND NOT EXISTS (
                  SELECT 1 FROM symbol_lifecycle_events r
                  WHERE r.symbol = s.symbol
                    AND r.event_type IN ('offboarded', 'purgatory_restored', 'suspect_classified')
                    AND r.event_timestamp > s.event_timestamp
              )
            ORDER BY s.event_date DESC
        ''').fetchall()
        return [dict(r) for r in rows]


def is_suspect_already_logged(db_path, symbol):
    """Check if a symbol already has an unresolved suspect_detected event.

    Used by health check for idempotency — don't log duplicate suspects.

    Returns:
        bool: True if an unresolved suspect event exists
    """
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        _ensure_lifecycle_table(conn)
        row = conn.execute('''
            SELECT 1 FROM symbol_lifecycle_events s
            WHERE s.symbol = ?
              AND s.event_type = 'suspect_detected'
              AND NOT EXISTS (
                  SELECT 1 FROM symbol_lifecycle_events r
                  WHERE r.symbol = s.symbol
                    AND r.event_type IN ('offboarded', 'purgatory_restored', 'suspect_classified')
                    AND r.event_timestamp > s.event_timestamp
              )
            LIMIT 1
        ''', (symbol,)).fetchone()
        return row is not None
