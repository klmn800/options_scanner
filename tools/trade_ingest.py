#!/usr/bin/env python3
"""
Trade Ingest Pipeline — Phase 1: Email Parser & Execution Logger
================================================================
Parses Robinhood trade confirmation emails from Gmail and stores
executions in the `trade_executions` table.

Email flow:
  Robinhood → account-holder@example.com → klmn800alerts@gmail.com (auto-forward)

Usage:
    python tools/trade_ingest.py                      # Ingest new emails
    python tools/trade_ingest.py --dry-run             # Parse without writing
    python tools/trade_ingest.py --recent              # Show recent executions
    python tools/trade_ingest.py --recent --symbol X   # Filter by symbol
    python tools/trade_ingest.py --manual --symbol ERIC --action buy \\
        --type option --option-type call --strike 12 --expiry 2026-05-15 \\
        --qty 1 --price 0.55                           # Manual entry

Reads/writes: data/datalake.db (trade_executions table)
Dependencies: tools/email_reader.py (GmailReader), tools/decimal_formatter.py
"""

import argparse
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, date

# Project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from timezone_utils import now_eastern
from decimal_formatter import clean_database_row
from log_utils import beautiful_log
from trade_positions import refresh_trade_positions

logger = logging.getLogger(__name__)

# ── Schema ───────────────────────────────────────────────────────────

def _ensure_schema(conn):
    """Create trade_executions table if it doesn't exist.

    Table: trade_executions — one row per fill, immutable log from parser.
    Editable columns: notes, trade_call_ref, review_status.

    Reads: nothing
    Writes: trade_executions (CREATE TABLE, CREATE INDEX)
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_executions (
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
            position_key TEXT NOT NULL,
            broker TEXT DEFAULT 'robinhood',
            email_message_id TEXT UNIQUE,
            robinhood_order_id TEXT,
            source TEXT NOT NULL DEFAULT 'email',
            notes TEXT,
            trade_call_ref TEXT,
            review_status TEXT DEFAULT 'unreviewed',
            underlying_price_at_fill REAL,
            iv_at_fill REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check for indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='trade_executions'")
    existing = {row[0] for row in cursor.fetchall()}

    if 'idx_trade_executions_symbol' not in existing:
        cursor.execute("CREATE INDEX idx_trade_executions_symbol ON trade_executions(symbol)")
    if 'idx_trade_executions_position_key' not in existing:
        cursor.execute("CREATE INDEX idx_trade_executions_position_key ON trade_executions(position_key)")

    conn.commit()


# ── Email Parsing ────────────────────────────────────────────────────

# Month name → number mapping
_MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12
}

# Regex: Option order executed (full fill)
# "Your limit order to buy 1 contract of NKE $45.00 Call 5/15 in your
#  individual (***1763) account executed at an average price of $180.00 per
#  contract on April 2, 2026 at 3:16 PM ET."
_OPTION_EXECUTED_RE = re.compile(
    r'Your (?:limit |market )?order to (buy|sell) (\d+) contracts? of '
    r'(\w+) \$([0-9,.]+) (Call|Put) (\d{1,2}/\d{1,2}) '
    r'in your.*?account (?:executed|was executed) at an average price of '
    r'\$([0-9,.]+) per contract on '
    r'(\w+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2} [AP]M) ET',
    re.DOTALL | re.IGNORECASE
)

# Regex: Option order partially executed
# "Your limit order to buy 2 contracts of ERIC $12.00 Put 5/15 in your
#  individual (***1763) account executed on April 15, 2026 at 2:35 PM ET.
#  So far, 1 of 2 contracts were filled for an average price of $65.00 per contract."
_OPTION_PARTIAL_RE = re.compile(
    r'Your (?:limit |market )?order to (buy|sell) (\d+) contracts? of '
    r'(\w+) \$([0-9,.]+) (Call|Put) (\d{1,2}/\d{1,2}) '
    r'in your.*?account (?:executed|was executed) on '
    r'(\w+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2} [AP]M) ET.*?'
    r'So far, (\d+) of (\d+) contracts? (?:were|was) filled '
    r'for an average price of \$([0-9,.]+) per contract',
    re.DOTALL | re.IGNORECASE
)

# Regex: Stock order executed
# "Your order to buy 2 shares of RNMBY through your individual (***1763)
#  account was executed at an average price of $316.75 on March 27, 2026 at
#  2:51 PM ET."
# Quantity accepts fractional values (e.g., "0.75 shares") from Robinhood
# fractional-share buys/sells.
_STOCK_EXECUTED_RE = re.compile(
    r'Your (?:limit |market )?order to (buy|sell) (\d+(?:\.\d+)?) shares? of '
    r'(\w+) (?:through|in) your.*?account (?:was executed|executed) at an average price of '
    r'\$([0-9,.]+) on '
    r'(\w+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2} [AP]M) ET',
    re.DOTALL | re.IGNORECASE
)

# Regex: Robinhood order ID from "View order" link
_ORDER_ID_RE = re.compile(
    r'applink\.robinhood\.com/orders\?id=([0-9a-f-]{36})',
    re.IGNORECASE
)


def _parse_date_time(date_str, time_str):
    """Parse 'April 2, 2026' + '3:16 PM' into datetime.

    Returns datetime or None on failure.
    """
    try:
        combined = "{} {}".format(date_str.strip(), time_str.strip())
        return datetime.strptime(combined, "%B %d, %Y %I:%M %p")
    except ValueError:
        return None


def _parse_expiry(expiry_short, execution_date):
    """Parse '5/15' into a full date string like '2026-05-15'.

    Uses the execution year. If parsed expiry is before execution date, bumps year+1.
    """
    parts = expiry_short.split('/')
    if len(parts) != 2:
        return None
    month, day = int(parts[0]), int(parts[1])
    year = execution_date.year

    try:
        expiry = date(year, month, day)
    except ValueError:
        return None

    if expiry < execution_date.date() if isinstance(execution_date, datetime) else expiry < execution_date:
        expiry = date(year + 1, month, day)

    return expiry.isoformat()


def _make_position_key(symbol, instrument_type, option_type=None, strike=None, expiration_date=None):
    """Generate position_key matching contract_hash convention.

    Options: 'ERIC|12.0|2026-05-15|PUT' (matches flow_alerts.contract_hash)
    Stock: 'RNMBY' (just the symbol — no hash needed, absence of pipes is differentiator)
    """
    if instrument_type == 'option':
        return "{}|{}|{}|{}".format(
            symbol,
            strike if strike is not None else '0',
            expiration_date or 'unknown',
            (option_type or 'unknown').upper()
        )
    return symbol


def _extract_forwarded_body(full_body):
    """Extract the forwarded message body, stripping the forwarding header.

    Gmail auto-forwards wrap the original with:
    '---------- Forwarded message ---------'
    We want only the content after that marker.
    """
    marker = '---------- Forwarded message ---------'
    idx = full_body.find(marker)
    if idx != -1:
        # Skip past the forwarding headers (From/Date/Subject/To lines)
        after_marker = full_body[idx + len(marker):]
        # Find the end of forwarding headers (blank line after them)
        lines = after_marker.split('\n')
        body_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip header lines like "From:", "Date:", "Subject:", "To:"
            if stripped.startswith(('From:', 'Date:', 'Subject:', 'To:')):
                continue
            if stripped == '':
                continue
            # First non-header, non-blank line = body start
            body_start = i
            break
        return '\n'.join(lines[body_start:])
    return full_body


def parse_email(body, msg_id=None):
    """Parse a Robinhood trade confirmation email body into execution dict(s).

    Args:
        body: Email body text (may include forwarding wrapper)
        msg_id: Gmail message ID for dedup

    Returns:
        list of execution dicts, or empty list if no match
    """
    # Strip HTML if present (direct forwards from Gmail are raw HTML)
    if '<html' in body[:500].lower():
        text = re.sub(r'<[^>]+>', ' ', body)
    else:
        # Plain text — extract forwarded content (manual Fwd: wrapper)
        text = _extract_forwarded_body(body)

    # Normalize whitespace (emails wrap lines, HTML leaves gaps)
    text_normalized = re.sub(r'\s+', ' ', text)

    executions = []

    # Extract order ID (shared across all formats)
    order_match = _ORDER_ID_RE.search(text_normalized)
    order_id = order_match.group(1) if order_match else None

    # Try option partial fill first (more specific — has "So far" clause)
    match = _OPTION_PARTIAL_RE.search(text_normalized)
    if match:
        action = match.group(1).lower()
        # group(2) = total ordered, group(9) = filled, group(10) = total
        symbol = match.group(3).upper()
        strike = float(match.group(4).replace(',', ''))
        option_type = match.group(5).lower()
        expiry_short = match.group(6)
        date_str = match.group(7)
        time_str = match.group(8)
        filled_qty = int(match.group(9))
        # group(10) = total ordered (not used — we store filled)
        price_per_contract = float(match.group(11).replace(',', ''))

        exec_ts = _parse_date_time(date_str, time_str)
        expiry = _parse_expiry(expiry_short, exec_ts) if exec_ts else None
        fill_price = round(price_per_contract / 100, 4)  # Per-share
        total_cost = round(filled_qty * fill_price * 100, 2)

        executions.append({
            'execution_timestamp': exec_ts.strftime('%Y-%m-%d %H:%M:%S') if exec_ts else None,
            'action': action,
            'instrument_type': 'option',
            'symbol': symbol,
            'quantity': filled_qty,
            'fill_price': fill_price,
            'total_cost': total_cost,
            'option_type': option_type,
            'strike': strike,
            'expiration_date': expiry,
            'position_key': _make_position_key(symbol, 'option', option_type, strike, expiry),
            'broker': 'robinhood',
            'email_message_id': msg_id,
            'robinhood_order_id': order_id,
            'source': 'email',
        })
        return executions

    # Try option full fill
    match = _OPTION_EXECUTED_RE.search(text_normalized)
    if match:
        action = match.group(1).lower()
        qty = int(match.group(2))
        symbol = match.group(3).upper()
        strike = float(match.group(4).replace(',', ''))
        option_type = match.group(5).lower()
        expiry_short = match.group(6)
        price_per_contract = float(match.group(7).replace(',', ''))
        date_str = match.group(8)
        time_str = match.group(9)

        exec_ts = _parse_date_time(date_str, time_str)
        expiry = _parse_expiry(expiry_short, exec_ts) if exec_ts else None
        fill_price = round(price_per_contract / 100, 4)  # Per-share
        total_cost = round(qty * fill_price * 100, 2)

        executions.append({
            'execution_timestamp': exec_ts.strftime('%Y-%m-%d %H:%M:%S') if exec_ts else None,
            'action': action,
            'instrument_type': 'option',
            'symbol': symbol,
            'quantity': qty,
            'fill_price': fill_price,
            'total_cost': total_cost,
            'option_type': option_type,
            'strike': strike,
            'expiration_date': expiry,
            'position_key': _make_position_key(symbol, 'option', option_type, strike, expiry),
            'broker': 'robinhood',
            'email_message_id': msg_id,
            'robinhood_order_id': order_id,
            'source': 'email',
        })
        return executions

    # Try stock order
    match = _STOCK_EXECUTED_RE.search(text_normalized)
    if match:
        action = match.group(1).lower()
        qty = float(match.group(2))
        symbol = match.group(3).upper()
        fill_price = float(match.group(4).replace(',', ''))
        date_str = match.group(5)
        time_str = match.group(6)

        exec_ts = _parse_date_time(date_str, time_str)
        total_cost = round(qty * fill_price, 2)

        executions.append({
            'execution_timestamp': exec_ts.strftime('%Y-%m-%d %H:%M:%S') if exec_ts else None,
            'action': action,
            'instrument_type': 'stock',
            'symbol': symbol,
            'quantity': qty,
            'fill_price': fill_price,
            'total_cost': total_cost,
            'option_type': None,
            'strike': None,
            'expiration_date': None,
            'position_key': _make_position_key(symbol, 'stock'),
            'broker': 'robinhood',
            'email_message_id': msg_id,
            'robinhood_order_id': order_id,
            'source': 'email',
        })
        return executions

    return executions


# ── Database Operations ──────────────────────────────────────────────

def _insert_execution(conn, execution):
    """Insert a single execution into trade_executions.

    Uses INSERT OR IGNORE on email_message_id UNIQUE constraint for dedup.

    Returns: 'inserted', 'duplicate', or 'error'
    """
    cleaned = clean_database_row(execution)
    # Restore timestamps after clean_database_row (it nullifies date-like fields)
    cleaned['execution_timestamp'] = execution.get('execution_timestamp')
    cleaned['expiration_date'] = execution.get('expiration_date')

    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO trade_executions (
                execution_timestamp, action, instrument_type, symbol,
                quantity, fill_price, total_cost, option_type, strike,
                expiration_date, position_key, broker, email_message_id,
                robinhood_order_id, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            cleaned.get('position_key'),
            cleaned.get('broker', 'robinhood'),
            cleaned.get('email_message_id'),
            cleaned.get('robinhood_order_id'),
            cleaned.get('source', 'email'),
            now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
        ))
        conn.commit()

        if cursor.rowcount > 0:
            # Materialize the position update + auto-link to any matching
            # proposed trade_call. Failures here don't roll back the execution
            # row — that's the source of truth; trade_positions can be rebuilt
            # via `python tools/trade_positions.py --reconcile` if drift occurs.
            try:
                refresh_trade_positions(conn, position_key=cleaned.get('position_key'))
            except Exception as refresh_err:
                logger.warning("refresh_trade_positions failed for {}: {}".format(
                    cleaned.get('position_key'), refresh_err))
            return 'inserted'
        return 'duplicate'

    except Exception as e:
        logger.error("Failed to insert execution: {}".format(e))
        return 'error'


# ── Main Ingest Flow ─────────────────────────────────────────────────

def ingest_from_email(dry_run=False, quiet=False):
    """Search Gmail for Robinhood execution emails and ingest them.

    Args:
        dry_run: If True, parse and display but don't write to DB or mark read.
        quiet: If True, suppress routine logging (used when called from FM cycle).
               Errors and new inserts are still logged.

    Returns:
        dict: {'processed': N, 'inserted': N, 'skipped_duplicate': N, 'errors': N, 'parse_failures': N}
    """
    from email_reader import GmailReader

    def _log(msg, level='info'):
        if not quiet:
            beautiful_log(msg, level)
        else:
            logging.debug(msg)

    stats = {'processed': 0, 'inserted': 0, 'skipped_duplicate': 0, 'skipped_junk': 0, 'errors': 0, 'parse_failures': 0}

    # Connect to Gmail
    try:
        reader = GmailReader()
    except Exception as e:
        beautiful_log("Gmail connection failed: {}".format(e), 'error')
        stats['errors'] += 1
        return stats

    # Probe auth non-interactively. If the token is missing/revoked, skip cleanly
    # rather than counting it as an error (orchestrator doesn't have a TTY to
    # complete an OAuth browser flow).
    if not reader.authenticate(interactive=False):
        beautiful_log(
            "Gmail not authenticated — skipping trade ingest. "
            "Run `python tools/email_reader.py --auth` to re-authenticate.",
            'warning'
        )
        stats['skipped_auth'] = 1
        return stats

    # Search for unread Robinhood execution emails (forwarded)
    query = '(from:account-holder@example.com OR from:noreply@robinhood.com) (subject:"option order" OR subject:"your order") is:unread'
    _log("Searching Gmail: {}".format(query))

    try:
        messages = reader.search(query, max_results=50)
    except Exception as e:
        beautiful_log("Gmail search failed: {}".format(e), 'error')
        stats['errors'] += 1
        return stats

    if not messages:
        _log("No unread Robinhood execution emails found")
        return stats

    beautiful_log("Found {} unread execution email(s)".format(len(messages)), 'info')

    # Open database (only if not dry run)
    conn = None
    if not dry_run:
        db_path = os.path.join(project_root, 'data', 'datalake.db')
        conn = sqlite3.connect(db_path)
        _ensure_schema(conn)

    try:
        for msg_meta in messages:
            msg_id = msg_meta['id']
            subject = msg_meta.get('subject', '(no subject)')

            try:
                msg = reader.get_message(msg_id)
            except Exception as e:
                beautiful_log("  Failed to fetch message {}: {}".format(msg_id[:8], e), 'error')
                stats['errors'] += 1
                continue

            # Skip junk subjects (canceled, etc.) — mark read to clear inbox
            _JUNK_SUBJECTS = ('canceled', 'cancelled', 'pending', 'received')
            subject_lower = subject.lower()
            if any(word in subject_lower for word in _JUNK_SUBJECTS):
                _log("  Skipping junk: {}".format(subject[:60]))
                stats['skipped_junk'] += 1
                if not dry_run:
                    try:
                        reader.mark_read(msg_id)
                    except Exception:
                        pass
                continue

            body = msg.get('body', '')
            executions = parse_email(body, msg_id=msg_id)

            if not executions:
                beautiful_log("  Could not parse: {}".format(subject[:60]), 'warning')
                stats['parse_failures'] += 1
                continue

            for ex in executions:
                stats['processed'] += 1

                # Display what we found
                if ex['instrument_type'] == 'option':
                    desc = "{} {:g} {} ${} {} {} @ ${:.2f}/sh (${:.2f} total)".format(
                        ex['action'].upper(), ex['quantity'],
                        ex['symbol'], ex['strike'], ex['option_type'],
                        ex['expiration_date'], ex['fill_price'], ex['total_cost']
                    )
                else:
                    desc = "{} {:g} {} @ ${:.2f} (${:.2f} total)".format(
                        ex['action'].upper(), ex['quantity'],
                        ex['symbol'], ex['fill_price'], ex['total_cost']
                    )

                if dry_run:
                    beautiful_log("  [DRY RUN] {}".format(desc), 'info')
                    stats['inserted'] += 1  # Would-be inserts
                else:
                    result = _insert_execution(conn, ex)
                    if result == 'inserted':
                        beautiful_log("  Inserted: {}".format(desc), 'success')
                        stats['inserted'] += 1
                    elif result == 'duplicate':
                        _log("  Duplicate: {}".format(desc))
                        stats['skipped_duplicate'] += 1
                    else:
                        beautiful_log("  Error inserting: {}".format(desc), 'error')
                        stats['errors'] += 1

            # Mark email as read only after successful processing (not dry run)
            if not dry_run and executions:
                try:
                    reader.mark_read(msg_id)
                except Exception as e:
                    beautiful_log("  Failed to mark read: {}".format(e), 'warning')

    finally:
        if conn:
            conn.close()

    return stats


def show_recent(symbol=None, limit=20):
    """Display recent trade executions from the database."""
    db_path = os.path.join(project_root, 'data', 'datalake.db')
    conn = sqlite3.connect(db_path)
    _ensure_schema(conn)
    cursor = conn.cursor()

    query = """
        SELECT execution_timestamp, action, instrument_type, symbol,
               quantity, fill_price, total_cost, option_type, strike,
               expiration_date, position_key, source
        FROM trade_executions
    """
    params = []
    if symbol:
        query += " WHERE symbol = ?"
        params.append(symbol.upper())
    query += " ORDER BY execution_timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No trade executions found.")
        return

    print("\n{:<20} {:<5} {:<7} {:<6} {:>4} {:>8} {:>10} {:<6} {:>8} {:<12}".format(
        'Timestamp', 'Act', 'Type', 'Symbol', 'Qty', 'Price', 'Total', 'OptTyp', 'Strike', 'Expiry'))
    print("-" * 100)

    for row in rows:
        ts, action, itype, sym, qty, price, total, otype, strike, expiry, pkey, src = row
        print("{:<20} {:<5} {:<7} {:<6} {:>4} {:>8.2f} {:>10.2f} {:<6} {:>8} {:<12}".format(
            ts or '', action or '', itype or '', sym or '', qty or 0,
            price or 0, total or 0, otype or '', strike or 0,
            expiry or ''))


def manual_entry(args):
    """Insert a manual trade execution from CLI arguments."""
    db_path = os.path.join(project_root, 'data', 'datalake.db')
    conn = sqlite3.connect(db_path)
    _ensure_schema(conn)

    instrument_type = args.type
    option_type = getattr(args, 'option_type', None)
    strike = getattr(args, 'strike', None)
    expiry = getattr(args, 'expiry', None)

    if instrument_type == 'option':
        multiplier = 100
        if not all([option_type, strike, expiry]):
            print("Error: --option-type, --strike, and --expiry are required for option trades")
            conn.close()
            return
    else:
        multiplier = 1

    total_cost = round(args.qty * args.price * multiplier, 2)
    position_key = _make_position_key(
        args.symbol.upper(), instrument_type, option_type, strike, expiry
    )

    execution = {
        'execution_timestamp': now_eastern().strftime('%Y-%m-%d %H:%M:%S'),
        'action': args.action,
        'instrument_type': instrument_type,
        'symbol': args.symbol.upper(),
        'quantity': args.qty,
        'fill_price': args.price,
        'total_cost': total_cost,
        'option_type': option_type,
        'strike': strike,
        'expiration_date': expiry,
        'position_key': position_key,
        'broker': 'robinhood',
        'email_message_id': None,
        'robinhood_order_id': None,
        'source': 'manual',
    }

    result = _insert_execution(conn, execution)
    conn.close()

    if result == 'inserted':
        print("Manual execution inserted: {} {} {} @ ${:.2f}".format(
            args.action.upper(), args.qty, args.symbol.upper(), args.price))
    else:
        print("Insert result: {}".format(result))


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Trade Ingest Pipeline — parse Robinhood emails into trade_executions')

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true',
                      help='Parse emails without writing to DB or marking read')
    mode.add_argument('--recent', action='store_true',
                      help='Show recent trade executions')
    mode.add_argument('--manual', action='store_true',
                      help='Manual entry mode')

    # Filters for --recent
    parser.add_argument('--symbol', type=str, help='Filter by symbol (for --recent or --manual)')

    # Manual entry fields
    parser.add_argument('--action', type=str, choices=['buy', 'sell'],
                        help='Trade action (for --manual)')
    parser.add_argument('--type', type=str, choices=['option', 'stock'],
                        help='Instrument type (for --manual)')
    parser.add_argument('--option-type', type=str, choices=['call', 'put'],
                        help='Option type (for --manual, options only)')
    parser.add_argument('--strike', type=float, help='Strike price (for --manual, options only)')
    parser.add_argument('--expiry', type=str, help='Expiration date YYYY-MM-DD (for --manual, options only)')
    parser.add_argument('--qty', type=float,
                        help='Quantity (for --manual). Fractional allowed for stock.')
    parser.add_argument('--price', type=float, help='Fill price per share (for --manual)')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    sys.stdout.reconfigure(encoding='utf-8')

    if args.recent:
        show_recent(symbol=args.symbol)
        return

    if args.manual:
        if not all([args.action, args.type, args.qty, args.price, args.symbol]):
            print("Error: --manual requires --symbol, --action, --type, --qty, --price")
            return
        manual_entry(args)
        return

    # Default: ingest from email
    beautiful_log("Trade Ingest Pipeline starting", 'phase')
    stats = ingest_from_email(dry_run=args.dry_run)

    # Summary
    mode_label = "[DRY RUN] " if args.dry_run else ""
    beautiful_log("{}Processed: {} | Inserted: {} | Duplicates: {} | Junk: {} | Parse failures: {} | Errors: {}".format(
        mode_label, stats['processed'], stats['inserted'],
        stats['skipped_duplicate'], stats['skipped_junk'], stats['parse_failures'], stats['errors']
    ), 'success' if stats['errors'] == 0 else 'warning')


if __name__ == '__main__':
    main()
