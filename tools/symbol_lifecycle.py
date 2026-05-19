#!/usr/bin/env python3
"""
Symbol Lifecycle Management CLI (symbol_lifecycle.py)
------------------------------------------------------
Primary entry point for onboarding, offboarding, and managing
the KLMN symbol universe.

Interactive usage:
    python tools/symbol_lifecycle.py --add ACME
    python tools/symbol_lifecycle.py --offboard ACME
    python tools/symbol_lifecycle.py --restore ACME
    python tools/symbol_lifecycle.py --move-tier ACME
    python tools/symbol_lifecycle.py --rename PSTG P
    python tools/symbol_lifecycle.py --list
    python tools/symbol_lifecycle.py --review

Non-interactive usage (for agents):
    python tools/symbol_lifecycle.py --add ACME --no-interaction \\
        --tier fm_universe --archive-db technology
    python tools/symbol_lifecycle.py --offboard ACME --no-interaction \\
        --reason "delisted"
    python tools/symbol_lifecycle.py --restore ACME --no-interaction \\
        --tier daily_only
    python tools/symbol_lifecycle.py --move-tier ACME --no-interaction \\
        --reason "lowered conviction"
    python tools/symbol_lifecycle.py --rename PSTG P --no-interaction

Exit codes: 0 success, 1 capability failure, 2 invalid invocation.
--review is intentionally interactive-only.

PRD 0013 — Symbol Lifecycle Management
"""

import os
import sys
import argparse

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

sys.stdout.reconfigure(encoding='utf-8')


def get_db_path():
    return os.path.join(project_root, 'data', 'datalake.db')


def main():
    parser = argparse.ArgumentParser(
        description='Symbol Lifecycle Management — onboard, offboard, and manage the KLMN universe',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Interactive examples:
  %(prog)s --add ACME                       Interactive onboarding
  %(prog)s --offboard ACME                  Move ACME to purgatory
  %(prog)s --restore ACME                   Restore ACME from purgatory
  %(prog)s --move-tier ACME                 Toggle tier
  %(prog)s --rename PSTG P                  Rename ticker across all DBs
  %(prog)s --list                           Universe dashboard
  %(prog)s --review                         Triage pending suspects

Non-interactive examples (for agents):
  %(prog)s --add ACME --no-interaction --tier fm_universe --archive-db technology
  %(prog)s --offboard ACME --no-interaction --reason "delisted"
  %(prog)s --restore ACME --no-interaction --tier daily_only
  %(prog)s --move-tier ACME --no-interaction --reason "lowered conviction"
  %(prog)s --rename PSTG P --no-interaction
        """)

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--add', metavar='SYMBOL', help='Onboard a new symbol')
    group.add_argument('--offboard', metavar='SYMBOL', help='Move symbol to purgatory')
    group.add_argument('--restore', metavar='SYMBOL', help='Restore symbol from purgatory')
    group.add_argument('--move-tier', metavar='SYMBOL',
                       help='Toggle tier (fm_universe <-> daily_only)')
    group.add_argument('--rename', nargs=2, metavar=('OLD', 'NEW'),
                       help='Rename ticker across all databases')
    group.add_argument('--list', action='store_true', help='Show universe dashboard')
    group.add_argument('--review', action='store_true',
                       help='Triage pending suspects (interactive only)')

    parser.add_argument('--no-interaction', action='store_true',
                        help='Skip all prompts; required values must come from flags')
    parser.add_argument('--tier', choices=['fm_universe', 'daily_only'],
                        help='Tier for --add and --restore (required under --no-interaction)')
    parser.add_argument('--archive-db', metavar='NAME',
                        help='Archive DB for --add (auto-routed by sector if omitted)')
    parser.add_argument('--create-archive', action='store_true',
                        help='For --add: allow auto-creation of a missing archive DB')
    parser.add_argument('--reason', metavar='TEXT',
                        help='Reason for --offboard or --move-tier (required under --no-interaction)')
    parser.add_argument('--force', action='store_true',
                        help='Override blocking guards (for --add and --rename)')

    args = parser.parse_args()
    db_path = get_db_path()

    if args.review and args.no_interaction:
        print('ERROR: --review is interactive-only (per-suspect triage). '
              'Use --list to view suspects or --offboard SYMBOL to act on one.')
        sys.exit(2)

    ok = True
    if args.add:
        from tools.lifecycle.onboarding import onboard_symbol
        ok = onboard_symbol(
            args.add.upper(), db_path,
            no_interaction=args.no_interaction,
            tier=args.tier,
            archive_db=args.archive_db,
            create_archive=args.create_archive,
            force=args.force,
        )
    elif args.offboard:
        from tools.lifecycle.offboarding import offboard_symbol
        ok = offboard_symbol(
            args.offboard.upper(), db_path,
            no_interaction=args.no_interaction,
            reason=args.reason,
        )
    elif args.restore:
        from tools.lifecycle.offboarding import restore_symbol
        ok = restore_symbol(
            args.restore.upper(), db_path,
            no_interaction=args.no_interaction,
            tier=args.tier,
        )
    elif args.move_tier:
        from tools.lifecycle.offboarding import move_tier
        ok = move_tier(
            args.move_tier.upper(), db_path,
            no_interaction=args.no_interaction,
            reason=args.reason,
        )
    elif args.rename:
        from tools.lifecycle.renaming import rename_symbol
        ok = rename_symbol(
            args.rename[0].upper(), args.rename[1].upper(), db_path,
            no_interaction=args.no_interaction,
            force=args.force,
        )
    elif args.list:
        from tools.lifecycle.offboarding import list_universe
        list_universe(db_path)
    elif args.review:
        from tools.lifecycle.offboarding import review_pending
        review_pending(db_path)

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
