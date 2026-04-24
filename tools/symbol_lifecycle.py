#!/usr/bin/env python3
"""
Symbol Lifecycle Management CLI (symbol_lifecycle.py)
------------------------------------------------------
Primary human entry point for onboarding, offboarding, and managing
the KLMN symbol universe.

Usage:
    python tools/symbol_lifecycle.py --add ACME          # Onboard a new symbol
    python tools/symbol_lifecycle.py --offboard ACME     # Move to purgatory
    python tools/symbol_lifecycle.py --restore ACME      # Restore from purgatory
    python tools/symbol_lifecycle.py --move-tier ACME    # Change tier (fm_universe <-> daily_only)
    python tools/symbol_lifecycle.py --rename PSTG P     # Rename ticker across all DBs
    python tools/symbol_lifecycle.py --list              # Universe dashboard
    python tools/symbol_lifecycle.py --review            # Review pending suspects

PRD 0013 — Symbol Lifecycle Management
"""

import os
import sys
import argparse

# Project root setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

sys.stdout.reconfigure(encoding='utf-8')


def get_db_path():
    """Get path to datalake.db"""
    return os.path.join(project_root, 'data', 'datalake.db')


def cmd_add(symbol):
    """Onboard a new symbol to the universe."""
    from tools.lifecycle.onboarding import onboard_symbol
    onboard_symbol(symbol, get_db_path())


def cmd_move_tier(symbol):
    """Change a symbol's tier (fm_universe <-> daily_only)."""
    from tools.lifecycle.offboarding import move_tier
    move_tier(symbol, get_db_path())


def cmd_offboard(symbol):
    """Move a symbol to purgatory (stop collection)."""
    from tools.lifecycle.offboarding import offboard_symbol
    offboard_symbol(symbol, get_db_path())


def cmd_restore(symbol):
    """Restore a symbol from purgatory."""
    from tools.lifecycle.offboarding import restore_symbol
    restore_symbol(symbol, get_db_path())


def cmd_list():
    """Display universe dashboard."""
    from tools.lifecycle.offboarding import list_universe
    list_universe(get_db_path())


def cmd_rename(old_symbol, new_symbol):
    """Rename a symbol across all databases."""
    from tools.lifecycle.renaming import rename_symbol
    rename_symbol(old_symbol, new_symbol, get_db_path())


def cmd_review():
    """Review pending lifecycle suspects."""
    from tools.lifecycle.offboarding import review_pending
    review_pending(get_db_path())


def main():
    parser = argparse.ArgumentParser(
        description='Symbol Lifecycle Management — onboard, offboard, and manage the KLMN universe',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --add ACME          Onboard ACME with interactive prompts
  %(prog)s --offboard ACME     Move ACME to purgatory
  %(prog)s --restore ACME      Restore ACME from purgatory
  %(prog)s --move-tier ACME    Change tier (fm_universe <-> daily_only)
  %(prog)s --rename PSTG P     Rename ticker across all databases
  %(prog)s --list              Show universe dashboard
  %(prog)s --review            Review pending lifecycle actions
        """)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--add', metavar='SYMBOL', help='Onboard a new symbol')
    group.add_argument('--offboard', metavar='SYMBOL', help='Move symbol to purgatory')
    group.add_argument('--restore', metavar='SYMBOL', help='Restore symbol from purgatory')
    group.add_argument('--move-tier', metavar='SYMBOL', help='Change tier (fm_universe <-> daily_only)')
    group.add_argument('--rename', nargs=2, metavar=('OLD', 'NEW'), help='Rename ticker across all databases')
    group.add_argument('--list', action='store_true', help='Show universe dashboard')
    group.add_argument('--review', action='store_true', help='Review pending suspects')

    args = parser.parse_args()

    if args.add:
        cmd_add(args.add.upper())
    elif args.offboard:
        cmd_offboard(args.offboard.upper())
    elif args.restore:
        cmd_restore(args.restore.upper())
    elif args.move_tier:
        cmd_move_tier(args.move_tier.upper())
    elif args.rename:
        cmd_rename(args.rename[0].upper(), args.rename[1].upper())
    elif args.list:
        cmd_list()
    elif args.review:
        cmd_review()


if __name__ == '__main__':
    main()
