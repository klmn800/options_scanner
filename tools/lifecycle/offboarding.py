"""
Symbol Offboarding & Management (offboarding.py)
-------------------------------------------------
Handles offboarding symbols to purgatory, restoring from purgatory,
universe dashboard display, and interactive suspect review.

PRD 0013 — Symbol Lifecycle Management (FR-10, FR-11, FR-12, FR-13, FR-14)
"""

import json
import os
import sqlite3
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.timezone_utils import now_eastern
from tools.lifecycle.audit import (
    log_lifecycle_event, get_recent_events, get_pending_suspects,
)
from tools.lifecycle.ui import prompt_yes_no, prompt_choice, prompt_text


def offboard_symbol(symbol, db_path):
    """Move a symbol to purgatory (stop all collection).

    Steps:
      1. Confirm symbol exists and is in fm_universe or daily_only
      2. Show current status
      3. Prompt for reason
      4. UPDATE symbol_metadata SET universe_tier='purgatory'
      5. DELETE from earnings_upcoming
      6. Log offboarded event
      7. Print confirmation

    Args:
        symbol: Stock ticker (already uppercased)
        db_path: Path to datalake.db
    """
    symbol = symbol.upper()

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT symbol, company_name, universe_tier, sector, industry, protected_reason '
            'FROM symbol_metadata WHERE symbol = ?',
            (symbol,)
        ).fetchone()

    if not row:
        print(f'Symbol {symbol} not found in symbol_metadata.')
        return

    current_tier = row['universe_tier']
    name = row['company_name'] or symbol
    protected = row['protected_reason']

    if current_tier == 'purgatory':
        print(f'{symbol} ({name}) is already in purgatory.')
        return

    if current_tier == 'removed':
        print(f'{symbol} ({name}) is already removed.')
        return

    if current_tier not in ('fm_universe', 'daily_only'):
        print(f'{symbol} ({name}) has unexpected tier: {current_tier}')
        return

    # Show current status
    print(f'\n  {symbol} — {name}')
    print(f'  Current tier:  {current_tier}')
    print(f'  Sector:        {row["sector"] or "N/A"}')
    print(f'  Industry:      {row["industry"] or "N/A"}')
    if protected:
        print(f'  Protected:     {protected}')
        print(f'  WARNING: This symbol has protected status ({protected}).')

    # Confirm
    if not prompt_yes_no(f'Offboard {symbol} to purgatory?'):
        print('Cancelled.')
        return

    # Reason
    reason = prompt_text('Reason for offboarding')
    if not reason:
        reason = 'No reason provided'

    today = now_eastern().strftime('%Y-%m-%d')

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        # Update tier
        conn.execute(
            'UPDATE symbol_metadata SET universe_tier = ?, tier_changed_date = ?, '
            'notes = COALESCE(notes || \'; \', \'\') || ? '
            'WHERE symbol = ?',
            ('purgatory', today, f'Offboarded {today}: {reason}', symbol)
        )

        # Remove from earnings_upcoming
        cursor = conn.execute(
            'DELETE FROM earnings_upcoming WHERE symbol = ?', (symbol,)
        )
        earnings_removed = cursor.rowcount

        conn.commit()

    # Log event
    event_id = log_lifecycle_event(
        db_path=db_path,
        symbol=symbol,
        event_type='offboarded',
        tier='purgatory',
        reason=reason,
        operator='human',
        metadata_dict={
            'previous_tier': current_tier,
            'protected_reason': protected,
            'earnings_upcoming_removed': earnings_removed,
        }
    )

    print(f'\nOffboarded {symbol} to purgatory. Event ID: {event_id}')
    if earnings_removed:
        print(f'  Removed {earnings_removed} row(s) from earnings_upcoming.')
    print('  Production data will archive naturally on next Friday cycle.')


def restore_symbol(symbol, db_path):
    """Restore a symbol from purgatory back to active universe.

    Steps:
      1. Confirm symbol is in purgatory
      2. Prompt for tier (fm_universe or daily_only)
      3. UPDATE symbol_metadata
      4. Log purgatory_restored event
      5. Print confirmation

    Args:
        symbol: Stock ticker (already uppercased)
        db_path: Path to datalake.db
    """
    symbol = symbol.upper()

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            'SELECT symbol, company_name, universe_tier, sector, industry, notes '
            'FROM symbol_metadata WHERE symbol = ?',
            (symbol,)
        ).fetchone()

    if not row:
        print(f'Symbol {symbol} not found in symbol_metadata.')
        return

    current_tier = row['universe_tier']
    name = row['company_name'] or symbol

    if current_tier != 'purgatory':
        print(f'{symbol} ({name}) is not in purgatory (current tier: {current_tier}).')
        return

    # Show current info
    print(f'\n  {symbol} — {name}')
    print(f'  Sector:    {row["sector"] or "N/A"}')
    print(f'  Industry:  {row["industry"] or "N/A"}')
    if row['notes']:
        print(f'  Notes:     {row["notes"]}')

    # Confirm
    if not prompt_yes_no(f'Restore {symbol} from purgatory?'):
        print('Cancelled.')
        return

    # Tier selection
    tier = prompt_choice('Restore to which tier:', [
        ('fm_universe', 'FM_UNIVERSE  (full intraday scan)'),
        ('daily_only', 'DAILY_ONLY   (OP/EI only)'),
    ])
    if tier is None:
        print('Cancelled.')
        return

    today = now_eastern().strftime('%Y-%m-%d')

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.execute(
            'UPDATE symbol_metadata SET universe_tier = ?, tier_changed_date = ? '
            'WHERE symbol = ?',
            (tier, today, symbol)
        )
        conn.commit()

    # Log event
    event_id = log_lifecycle_event(
        db_path=db_path,
        symbol=symbol,
        event_type='purgatory_restored',
        tier=tier,
        reason=f'Restored from purgatory to {tier}',
        operator='human',
        metadata_dict={
            'previous_tier': 'purgatory',
        }
    )

    print(f'\nRestored {symbol} to {tier}. Event ID: {event_id}')
    print('  Data collection will resume on next pipeline cycle.')
    if tier == 'fm_universe':
        print('  Tip: Run `python tools/symbol_lifecycle.py --add ' + symbol +
              '` to regenerate FM baseline if needed.')


def list_universe(db_path):
    """Display universe dashboard with tier counts, recent activity, suspects.

    Args:
        db_path: Path to datalake.db
    """
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row

        # Tier counts
        tier_rows = conn.execute(
            'SELECT universe_tier, COUNT(*) as cnt FROM symbol_metadata '
            'GROUP BY universe_tier ORDER BY cnt DESC'
        ).fetchall()

        # Protected counts
        protected_rows = conn.execute(
            'SELECT protected_reason, COUNT(*) as cnt FROM symbol_metadata '
            'WHERE protected_reason IS NOT NULL '
            'GROUP BY protected_reason ORDER BY cnt DESC'
        ).fetchall()

        # ETF count
        etf_count = conn.execute(
            'SELECT COUNT(*) FROM symbol_metadata WHERE is_etf = 1'
        ).fetchone()[0]

        # Total
        total = conn.execute('SELECT COUNT(*) FROM symbol_metadata').fetchone()[0]

        # Purgatory residents
        purgatory = conn.execute(
            'SELECT symbol, company_name, tier_changed_date, notes '
            'FROM symbol_metadata WHERE universe_tier = ? '
            'ORDER BY tier_changed_date DESC',
            ('purgatory',)
        ).fetchall()

    # Recent lifecycle events (30 days)
    recent = get_recent_events(db_path, days=30)

    # Pending suspects
    suspects = get_pending_suspects(db_path)

    # --- Display ---
    print('\n=== Symbol Universe Dashboard ===')
    print(f'\nTotal symbols: {total}')

    # Tier breakdown
    print('\nTier Breakdown:')
    for row in tier_rows:
        tier = row['universe_tier'] or '(none)'
        print(f'  {tier:<20} {row["cnt"]:>5}')

    # Protected groups
    if protected_rows:
        print('\nProtected Groups:')
        for row in protected_rows:
            print(f'  {row["protected_reason"]:<20} {row["cnt"]:>5}')

    if etf_count:
        print(f'\nETFs (is_etf=1):       {etf_count}')

    # Pending suspects
    if suspects:
        print(f'\nPending Suspects ({len(suspects)}):')
        for s in suspects:
            meta = json.loads(s.get('metadata_json') or '{}')
            days_missing = meta.get('consecutive_missing_days', '?')
            last_date = meta.get('last_data_date', 'never')
            print(f'  {s["symbol"]:<8} {days_missing} days missing, last data: {last_date}  '
                  f'(flagged {s["event_date"]})')
    else:
        print('\nPending Suspects: None')

    # Recent activity
    if recent:
        print(f'\nRecent Activity (last 30 days, {len(recent)} events):')
        for evt in recent[:15]:  # Cap at 15 for readability
            print(f'  {evt["event_date"]}  {evt["event_type"]:<22} {evt["symbol"]:<8} '
                  f'{evt.get("reason") or ""}')
        if len(recent) > 15:
            print(f'  ... and {len(recent) - 15} more')
    else:
        print('\nRecent Activity: None (last 30 days)')

    # Purgatory residents
    if purgatory:
        print(f'\nPurgatory Residents ({len(purgatory)}):')
        for p in purgatory[:20]:
            name = p['company_name'] or ''
            date = p['tier_changed_date'] or 'unknown'
            notes = p['notes'] or ''
            # Truncate notes for display
            if len(notes) > 60:
                notes = notes[:57] + '...'
            print(f'  {p["symbol"]:<8} {name:<30} since {date}  {notes}')
        if len(purgatory) > 20:
            print(f'  ... and {len(purgatory) - 20} more')


def review_pending(db_path):
    """Interactive review of pending suspect symbols.

    Shows each unresolved suspect and prompts for action:
      (o)ffboard — move to purgatory
      (r)estore — keep active (dismiss suspect)
      (d)ismiss — log as reviewed, no action
      (s)kip — leave for later

    Args:
        db_path: Path to datalake.db
    """
    suspects = get_pending_suspects(db_path)

    if not suspects:
        print('No pending suspects to review.')
        return

    print(f'\n=== Pending Suspect Review ({len(suspects)} symbols) ===')

    reviewed = 0
    for i, suspect in enumerate(suspects, 1):
        meta = json.loads(suspect.get('metadata_json') or '{}')
        days_missing = meta.get('consecutive_missing_days', '?')
        last_date = meta.get('last_data_date', 'never')
        symbol = suspect['symbol']

        # Fetch current metadata for context
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                'SELECT company_name, sector, industry, universe_tier, protected_reason '
                'FROM symbol_metadata WHERE symbol = ?',
                (symbol,)
            ).fetchone()

        name = row['company_name'] if row else 'Unknown'
        sector = row['sector'] if row else 'N/A'
        tier = row['universe_tier'] if row else 'N/A'
        protected = row['protected_reason'] if row else None

        print(f'\n--- [{i}/{len(suspects)}] {symbol} — {name} ---')
        print(f'  Sector:    {sector}')
        print(f'  Tier:      {tier}')
        print(f'  Missing:   {days_missing} consecutive trading days')
        print(f'  Last data: {last_date}')
        print(f'  Flagged:   {suspect["event_date"]}')
        if protected:
            print(f'  Protected: {protected}')

        # Action prompt
        print('\n  Actions:')
        print('    [o] Offboard to purgatory')
        print('    [d] Dismiss (mark as reviewed, keep active)')
        print('    [s] Skip (review later)')
        print('    [q] Quit review')

        while True:
            try:
                action = input('  Action: ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                print('\nReview interrupted.')
                return

            if action in ('o', 'd', 's', 'q'):
                break
            print('  Please enter o, d, s, or q')

        if action == 'q':
            print('Review ended.')
            break

        if action == 's':
            continue

        if action == 'o':
            reason = prompt_text('  Reason for offboarding')
            if not reason:
                reason = f'Offboarded via suspect review (missing {days_missing} days)'

            today = now_eastern().strftime('%Y-%m-%d')
            with sqlite3.connect(db_path, timeout=30.0) as conn:
                conn.execute(
                    'UPDATE symbol_metadata SET universe_tier = ?, tier_changed_date = ?, '
                    'notes = COALESCE(notes || \'; \', \'\') || ? '
                    'WHERE symbol = ?',
                    ('purgatory', today, f'Offboarded {today}: {reason}', symbol)
                )
                conn.execute(
                    'DELETE FROM earnings_upcoming WHERE symbol = ?', (symbol,)
                )
                conn.commit()

            log_lifecycle_event(
                db_path=db_path,
                symbol=symbol,
                event_type='offboarded',
                tier='purgatory',
                reason=reason,
                operator='human',
                metadata_dict={
                    'previous_tier': tier,
                    'via': 'suspect_review',
                    'days_missing': days_missing,
                }
            )
            print(f'  Offboarded {symbol} to purgatory.')
            reviewed += 1

        elif action == 'd':
            reason = prompt_text('  Dismissal note (optional)')
            if not reason:
                reason = 'Dismissed by user during suspect review'

            log_lifecycle_event(
                db_path=db_path,
                symbol=symbol,
                event_type='suspect_classified',
                tier=tier,
                reason=reason,
                operator='human',
                metadata_dict={
                    'days_missing': days_missing,
                    'classification': 'dismissed',
                }
            )
            print(f'  Dismissed suspect for {symbol}.')
            reviewed += 1

    print(f'\nReview complete. {reviewed} action(s) taken.')
