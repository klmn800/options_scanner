#!/usr/bin/env python3
"""
Options Position Tracker

A lightweight, standalone tool for tracking options positions with entry/exit
management. Self-contained with its own database schema, no external dependencies.

Features:
- Interactive and CLI modes for adding positions
- Automatic P&L tracking
- Position status management (OPEN/CLOSED)
- Simple SQLite backend

Usage:
    # Interactive mode (recommended for first-time users)
    python add_position.py --interactive

    # Command-line mode
    python add_position.py --add --symbol NVDA --strike 350 --expiration 2024-12-20 \\
        --type CALL --entry-date 2024-09-23 --entry-price 5.50 --reasoning "Bullish on earnings"

    # List all positions
    python add_position.py --list

    # List open positions only
    python add_position.py --list --open-only

    # Close a position
    python add_position.py --close --position-id 1 --exit-price 7.25

Database Schema:
    The tool automatically creates a 'positions' table with the following structure:
    - id: Auto-incrementing position ID
    - contract_hash: Unique identifier (SYMBOL|STRIKE|EXPIRATION|TYPE)
    - symbol: Stock ticker
    - strike: Strike price
    - expiration_date: Option expiration date
    - option_type: CALL or PUT
    - entry_date: Date position was entered
    - entry_price: Premium paid per contract
    - exit_date: Date position was closed (NULL if still open)
    - exit_price: Premium received on close (NULL if still open)
    - reasoning: Entry thesis/reasoning
    - status: OPEN or CLOSED
    - created_at: Timestamp of record creation

Author: Ben
Date: 2025-10-13
License: MIT
"""

import sys
import sqlite3
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# Configure UTF-8 encoding for Windows compatibility (MANDATORY)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Default database path (can be overridden with --db-path)
DEFAULT_DB_PATH = "positions.db"


def init_database(db_path: str) -> None:
    """Initialize the database with positions table if it doesn't exist.

    Args:
        db_path: Path to SQLite database file
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_hash TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strike REAL NOT NULL,
            expiration_date TEXT NOT NULL,
            option_type TEXT NOT NULL CHECK(option_type IN ('CALL', 'PUT')),
            entry_date TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_date TEXT,
            exit_price REAL,
            reasoning TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'CLOSED')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(contract_hash, entry_date)
        )
        """)

        # Create index for faster lookups
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_status
        ON positions(status)
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_symbol
        ON positions(symbol, expiration_date)
        """)

        conn.commit()


def create_contract_hash(symbol: str, strike: float, expiration: str, option_type: str) -> str:
    """Create standardized contract hash.

    Args:
        symbol: Stock ticker (e.g., 'NVDA')
        strike: Strike price (e.g., 350.0)
        expiration: Expiration date in YYYY-MM-DD format
        option_type: 'CALL' or 'PUT'

    Returns:
        Contract hash string (e.g., 'NVDA|350.0|2024-12-20|CALL')
    """
    return f"{symbol.upper()}|{strike}|{expiration}|{option_type.upper()}"


def parse_contract_hash(contract_hash: str) -> Tuple[str, float, str, str]:
    """Parse contract hash into components.

    Args:
        contract_hash: Contract hash string

    Returns:
        Tuple of (symbol, strike, expiration, option_type)

    Raises:
        ValueError: If contract hash format is invalid
    """
    try:
        parts = contract_hash.split('|')
        if len(parts) != 4:
            raise ValueError("Invalid format")

        symbol = parts[0].upper()
        strike = float(parts[1])
        expiration = parts[2]
        option_type = parts[3].upper()

        if option_type not in ('CALL', 'PUT'):
            raise ValueError("Option type must be CALL or PUT")

        return symbol, strike, expiration, option_type

    except (IndexError, ValueError) as e:
        raise ValueError(f"Invalid contract hash format. Expected: SYMBOL|STRIKE|YYYY-MM-DD|TYPE") from e


def add_position(
    db_path: str,
    symbol: str,
    strike: float,
    expiration: str,
    option_type: str,
    entry_date: str,
    entry_price: float,
    reasoning: Optional[str] = None
) -> bool:
    """Add a new position to the database.

    Args:
        db_path: Path to database file
        symbol: Stock ticker
        strike: Strike price
        expiration: Expiration date (YYYY-MM-DD)
        option_type: 'CALL' or 'PUT'
        entry_date: Entry date (YYYY-MM-DD)
        entry_price: Premium paid per contract
        reasoning: Optional entry thesis

    Returns:
        True if position added successfully, False otherwise
    """
    try:
        contract_hash = create_contract_hash(symbol, strike, expiration, option_type)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Check for duplicate
            cursor.execute("""
                SELECT id FROM positions
                WHERE contract_hash = ? AND entry_date = ?
            """, (contract_hash, entry_date))

            if cursor.fetchone():
                print(f"❌ Position already exists for {contract_hash} with entry date {entry_date}")
                return False

            # Insert new position
            cursor.execute("""
                INSERT INTO positions (
                    contract_hash, symbol, strike, expiration_date, option_type,
                    entry_date, entry_price, reasoning, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
            """, (contract_hash, symbol.upper(), strike, expiration, option_type.upper(),
                  entry_date, entry_price, reasoning))

            position_id = cursor.lastrowid
            conn.commit()

            print(f"✅ Position added successfully (ID: {position_id})")
            print(f"   Contract: {contract_hash}")
            print(f"   Entry: {entry_date} @ ${entry_price:.2f}")
            if reasoning:
                print(f"   Thesis: {reasoning}")

            return True

    except Exception as e:
        print(f"❌ Error adding position: {e}")
        return False


def close_position(db_path: str, position_id: int, exit_price: float, exit_date: Optional[str] = None) -> bool:
    """Close an open position.

    Args:
        db_path: Path to database file
        position_id: Position ID to close
        exit_price: Premium received on close
        exit_date: Exit date (defaults to today)

    Returns:
        True if position closed successfully, False otherwise
    """
    if exit_date is None:
        exit_date = date.today().strftime('%Y-%m-%d')

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            # Get position details
            cursor.execute("""
                SELECT contract_hash, entry_price, status
                FROM positions
                WHERE id = ?
            """, (position_id,))

            result = cursor.fetchone()
            if not result:
                print(f"❌ Position ID {position_id} not found")
                return False

            contract_hash, entry_price, status = result

            if status == 'CLOSED':
                print(f"❌ Position {position_id} is already closed")
                return False

            # Close position
            cursor.execute("""
                UPDATE positions
                SET exit_date = ?, exit_price = ?, status = 'CLOSED'
                WHERE id = ?
            """, (exit_date, exit_price, position_id))

            conn.commit()

            # Calculate P&L
            pnl = exit_price - entry_price
            pnl_pct = (pnl / entry_price) * 100

            print(f"✅ Position closed successfully")
            print(f"   ID: {position_id} ({contract_hash})")
            print(f"   Entry: ${entry_price:.2f} → Exit: ${exit_price:.2f}")
            print(f"   P&L: ${pnl:.2f} ({pnl_pct:+.1f}%)")

            return True

    except Exception as e:
        print(f"❌ Error closing position: {e}")
        return False


def list_positions(db_path: str, open_only: bool = False) -> List[Dict]:
    """List all positions.

    Args:
        db_path: Path to database file
        open_only: If True, only show open positions

    Returns:
        List of position dictionaries
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            query = """
                SELECT id, contract_hash, symbol, strike, expiration_date, option_type,
                       entry_date, entry_price, exit_date, exit_price, reasoning, status
                FROM positions
            """

            if open_only:
                query += " WHERE status = 'OPEN'"

            query += " ORDER BY entry_date DESC, symbol"

            cursor.execute(query)
            positions = [dict(row) for row in cursor.fetchall()]

            if not positions:
                print("📭 No positions found")
                return []

            # Display positions
            print(f"\n{'='*100}")
            print(f"{'ID':<5} {'Contract':<30} {'Entry Date':<12} {'Entry $':<10} {'Exit $':<10} {'P&L %':<10} {'Status':<8}")
            print(f"{'='*100}")

            for pos in positions:
                contract_display = f"{pos['symbol']} {pos['strike']:.0f} {pos['option_type']} {pos['expiration_date']}"

                pnl_str = ""
                if pos['exit_price']:
                    pnl = pos['exit_price'] - pos['entry_price']
                    pnl_pct = (pnl / pos['entry_price']) * 100
                    pnl_str = f"{pnl_pct:+.1f}%"

                exit_price_str = f"${pos['exit_price']:.2f}" if pos['exit_price'] else "-"

                print(f"{pos['id']:<5} {contract_display:<30} {pos['entry_date']:<12} "
                      f"${pos['entry_price']:<9.2f} {exit_price_str:<10} {pnl_str:<10} {pos['status']:<8}")

                if pos['reasoning']:
                    print(f"      Thesis: {pos['reasoning']}")

            print(f"{'='*100}\n")

            # Summary stats
            total = len(positions)
            open_count = sum(1 for p in positions if p['status'] == 'OPEN')
            closed_count = total - open_count

            if closed_count > 0:
                closed_positions = [p for p in positions if p['status'] == 'CLOSED']
                avg_pnl = sum((p['exit_price'] - p['entry_price']) / p['entry_price'] * 100
                             for p in closed_positions) / closed_count
                winners = sum(1 for p in closed_positions if p['exit_price'] > p['entry_price'])
                win_rate = (winners / closed_count) * 100

                print(f"📊 Summary: {total} total positions ({open_count} open, {closed_count} closed)")
                print(f"   Closed positions: Avg P&L {avg_pnl:+.1f}% | Win rate {win_rate:.0f}%")
            else:
                print(f"📊 Summary: {total} total positions (all open)")

            return positions

    except Exception as e:
        print(f"❌ Error listing positions: {e}")
        return []


def interactive_mode(db_path: str) -> bool:
    """Interactive mode for adding positions.

    Args:
        db_path: Path to database file

    Returns:
        True if position added successfully, False otherwise
    """
    print("\n" + "="*60)
    print("  Options Position Tracker - Interactive Mode")
    print("="*60 + "\n")

    try:
        # Get contract details
        symbol = input("Symbol (e.g., NVDA): ").strip().upper()
        if not symbol:
            print("❌ Symbol is required")
            return False

        strike = float(input("Strike price (e.g., 350): ").strip())

        expiration = input("Expiration date (YYYY-MM-DD): ").strip()
        # Basic date validation
        datetime.strptime(expiration, '%Y-%m-%d')

        option_type = input("Option type (CALL/PUT): ").strip().upper()
        if option_type not in ('CALL', 'PUT'):
            print("❌ Option type must be CALL or PUT")
            return False

        # Get entry details
        entry_date_input = input("Entry date (YYYY-MM-DD, press Enter for today): ").strip()
        entry_date = entry_date_input if entry_date_input else date.today().strftime('%Y-%m-%d')

        entry_price = float(input("Entry price (premium paid per contract): ").strip())

        reasoning = input("Entry reasoning/thesis (optional): ").strip()
        reasoning = reasoning if reasoning else None

        # Confirm
        print("\n" + "-"*60)
        print("📝 Position Summary:")
        print(f"   Contract: {symbol} {strike:.0f} {option_type} {expiration}")
        print(f"   Entry: {entry_date} @ ${entry_price:.2f}")
        if reasoning:
            print(f"   Thesis: {reasoning}")
        print("-"*60)

        confirm = input("\nAdd this position? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Cancelled")
            return False

        return add_position(db_path, symbol, strike, expiration, option_type,
                          entry_date, entry_price, reasoning)

    except ValueError as e:
        print(f"❌ Invalid input: {e}")
        return False
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Options Position Tracker - Lightweight position management tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python add_position.py --interactive

  # Add position via command line
  python add_position.py --add --symbol NVDA --strike 350 --expiration 2024-12-20 \\
      --type CALL --entry-date 2024-09-23 --entry-price 5.50

  # List all positions
  python add_position.py --list

  # List open positions only
  python add_position.py --list --open-only

  # Close a position
  python add_position.py --close --position-id 1 --exit-price 7.25
        """
    )

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--interactive', '-i', action='store_true',
                           help='Interactive mode for adding positions')
    mode_group.add_argument('--add', '-a', action='store_true',
                           help='Add position via command line')
    mode_group.add_argument('--close', '-c', action='store_true',
                           help='Close an open position')
    mode_group.add_argument('--list', '-l', action='store_true',
                           help='List all positions')

    # Position details for --add mode
    parser.add_argument('--symbol', help='Stock symbol (e.g., NVDA)')
    parser.add_argument('--strike', type=float, help='Strike price')
    parser.add_argument('--expiration', help='Expiration date (YYYY-MM-DD)')
    parser.add_argument('--type', dest='option_type', choices=['CALL', 'PUT', 'call', 'put'],
                       help='Option type (CALL or PUT)')
    parser.add_argument('--entry-date', help='Entry date (YYYY-MM-DD, defaults to today)')
    parser.add_argument('--entry-price', type=float, help='Entry price (premium per contract)')
    parser.add_argument('--reasoning', help='Entry reasoning/thesis')

    # Position details for --close mode
    parser.add_argument('--position-id', type=int, help='Position ID to close')
    parser.add_argument('--exit-price', type=float, help='Exit price (premium received)')
    parser.add_argument('--exit-date', help='Exit date (YYYY-MM-DD, defaults to today)')

    # Listing options
    parser.add_argument('--open-only', action='store_true',
                       help='Show only open positions (use with --list)')

    # Database path
    parser.add_argument('--db-path', default=DEFAULT_DB_PATH,
                       help=f'Database file path (default: {DEFAULT_DB_PATH})')

    args = parser.parse_args()

    # Initialize database
    init_database(args.db_path)

    # Handle modes
    if args.interactive:
        success = interactive_mode(args.db_path)
        sys.exit(0 if success else 1)

    elif args.add:
        # Validate required arguments
        if not all([args.symbol, args.strike, args.expiration, args.option_type, args.entry_price]):
            parser.error("--add mode requires: --symbol, --strike, --expiration, --type, --entry-price")

        entry_date = args.entry_date if args.entry_date else date.today().strftime('%Y-%m-%d')

        success = add_position(
            args.db_path,
            args.symbol,
            args.strike,
            args.expiration,
            args.option_type.upper(),
            entry_date,
            args.entry_price,
            args.reasoning
        )
        sys.exit(0 if success else 1)

    elif args.close:
        if not args.position_id or not args.exit_price:
            parser.error("--close mode requires: --position-id, --exit-price")

        success = close_position(args.db_path, args.position_id, args.exit_price, args.exit_date)
        sys.exit(0 if success else 1)

    elif args.list:
        list_positions(args.db_path, args.open_only)
        sys.exit(0)

    else:
        # No mode specified - show help and list positions
        parser.print_help()
        print("\n")
        list_positions(args.db_path)
        sys.exit(0)


if __name__ == "__main__":
    main()
