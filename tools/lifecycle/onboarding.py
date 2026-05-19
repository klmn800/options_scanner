"""
Symbol Onboarding (onboarding.py)
----------------------------------
Orchestrates the full onboarding sequence for adding a new symbol
to the KLMN universe.

Steps:
  1. Fetch info from Tradier (quotes + fundamentals + expirations)
  2. Display symbol card
  3. Run pre-flight checks
  4. Prompt for confirmation and tier
  5. Insert/update symbol_metadata
  6. Backfill historical_prices (~1 year)
  7. Backfill earnings_events via Tradier calendars
  8. Compute earnings_moves
  9. Populate earnings_upcoming
  10. Generate FM baseline (if fm_universe tier)
  11. Log lifecycle event

PRD 0013 — Symbol Lifecycle Management (FR-8)
"""

import json
import os
import sqlite3
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from tools.timezone_utils import now_eastern
from tools.lifecycle.preflight import run_preflight_checks
from tools.lifecycle.audit import log_lifecycle_event
from tools.lifecycle.routing import determine_archive_db
from tools.lifecycle.ui import (
    display_symbol_card, display_preflight_results, display_progress_step,
    prompt_yes_no, prompt_choice, prompt_archive_db,
)


def _load_tradier_token():
    """Load Tradier API token from config.json."""
    config_path = os.path.join(project_root, 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config.get('tradier', {}).get('api_key')


def fetch_symbol_info(symbol):
    """Fetch comprehensive symbol data from Tradier APIs.

    Calls quotes, fundamentals, option expirations, and earnings calendars.

    Returns:
        dict with keys: company_name, sector, industry, market_cap, avg_volume,
              last_price, expirations, last_earnings, earnings_available,
              quote_type, errors (list of non-fatal error messages)
    """
    import requests

    token = _load_tradier_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    result = {
        'company_name': 'Unknown',
        'sector': 'N/A',
        'industry': 'N/A',
        'market_cap': 0,
        'avg_volume': 0,
        'last_price': 0,
        'expirations': [],
        'last_earnings': 'N/A',
        'next_earnings': None,
        'earnings_available': False,
        'quote_type': None,
        'errors': [],
    }

    print(f'Pinging Tradier for {symbol}...')

    # 1. Quotes
    try:
        resp = requests.get(
            'https://api.tradier.com/v1/markets/quotes',
            headers=headers,
            params={'symbols': symbol},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            quote = data.get('quotes', {}).get('quote', {})
            if isinstance(quote, list):
                quote = quote[0] if quote else {}
            result['company_name'] = quote.get('description', 'Unknown')
            avg_vol = quote.get('average_volume') or 0
            if avg_vol == 0:
                # Tradier returns 0 for some symbols despite active trading
                avg_vol = quote.get('volume') or 0
                if avg_vol:
                    result['avg_volume_source'] = 'today'
            result['avg_volume'] = avg_vol
            result['last_price'] = quote.get('last') or quote.get('close') or 0
            result['quote_type'] = quote.get('type', '')
        else:
            result['errors'].append(f'Quotes API: HTTP {resp.status_code}')
    except Exception as e:
        result['errors'].append(f'Quotes API: {e}')

    # 2. Fundamentals (sector/industry/market cap)
    try:
        resp = requests.get(
            'https://api.tradier.com/beta/markets/fundamentals/company',
            headers=headers,
            params={'symbols': symbol},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data if isinstance(data, list) else data.get('data', [])
            for item in items:
                if not isinstance(item, dict):
                    continue
                for table in item.get('results', []):
                    tables = table.get('tables', {}) if isinstance(table, dict) else {}
                    asset_class = tables.get('asset_classification', {})
                    share_profile = tables.get('share_class_profile', {})
                    if asset_class:
                        from data.symbol_metadata import MORNINGSTAR_SECTOR_MAP, MORNINGSTAR_INDUSTRY_MAP
                        sector_code = asset_class.get('morningstar_sector_code')
                        industry_code = asset_class.get('morningstar_industry_code')
                        result['sector'] = MORNINGSTAR_SECTOR_MAP.get(sector_code, 'N/A')
                        result['industry'] = MORNINGSTAR_INDUSTRY_MAP.get(industry_code, 'N/A')
                    if share_profile:
                        result['market_cap'] = share_profile.get('market_cap') or 0
        else:
            result['errors'].append(f'Fundamentals API: HTTP {resp.status_code}')
    except Exception as e:
        result['errors'].append(f'Fundamentals API: {e}')

    # 3. Option expirations
    try:
        resp = requests.get(
            'https://api.tradier.com/v1/markets/options/expirations',
            headers=headers,
            params={'symbol': symbol},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            exps = data.get('expirations', {})
            if isinstance(exps, dict):
                result['expirations'] = exps.get('date', []) or []
            elif isinstance(exps, list):
                result['expirations'] = exps
    except Exception as e:
        result['errors'].append(f'Expirations API: {e}')

    # 4. Earnings calendars
    try:
        resp = requests.get(
            'https://api.tradier.com/beta/markets/fundamentals/calendars',
            headers=headers,
            params={'symbols': symbol},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            items = data if isinstance(data, list) else data.get('data', [])
            for item in items:
                if not isinstance(item, dict):
                    continue
                for table in item.get('results', []):
                    tables = table.get('tables', {}) if isinstance(table, dict) else {}
                    corp_cal = tables.get('corporate_calendars', {})
                    if corp_cal:
                        events = corp_cal if isinstance(corp_cal, list) else [corp_cal]
                        # Filter to earnings events (type 7-10 = Q1-Q4)
                        earnings = [e for e in events if isinstance(e, dict)
                                    and e.get('event_type') in (7, 8, 9, 10)]
                        if earnings:
                            result['earnings_available'] = True
                            today_str = now_eastern().strftime('%Y-%m-%d')
                            # Most recent PAST earnings + next future
                            past = [e for e in earnings
                                    if (e.get('begin_date_time', '') or '')[:10] <= today_str]
                            future = [e for e in earnings
                                      if (e.get('begin_date_time', '') or '')[:10] > today_str]
                            if past:
                                past.sort(key=lambda x: x.get('begin_date_time', ''), reverse=True)
                                result['last_earnings'] = past[0].get('begin_date_time', 'N/A')[:10]
                            if future:
                                future.sort(key=lambda x: x.get('begin_date_time', ''))
                                result['next_earnings'] = future[0].get('begin_date_time', 'N/A')[:10]
    except Exception as e:
        result['errors'].append(f'Calendars API: {e}')

    return result


def _step_insert_metadata(symbol, data, tier, archive_db, db_path):
    """Step 1: Insert/update symbol_metadata row."""
    from data.symbol_metadata import (
        categorize_market_cap, categorize_liquidity_tier, detect_etf, ensure_table_schema
    )

    ensure_table_schema(db_path)

    is_etf = detect_etf(data['company_name'], symbol, data.get('quote_type'))

    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()
        now = now_eastern().strftime('%Y-%m-%d %H:%M:%S')
        today = now_eastern().strftime('%Y-%m-%d')

        # Try UPDATE first to preserve existing columns
        cursor.execute('''
            UPDATE symbol_metadata
            SET company_name = ?, sector = ?, industry = ?,
                market_cap_category = ?, liquidity_tier = ?, is_etf = ?,
                options_available = 1, updated_at = ?,
                market_cap = ?, avg_volume = ?,
                universe_tier = ?, archive_db = ?, tier_changed_date = ?
            WHERE symbol = ?
        ''', (
            data['company_name'], data['sector'], data['industry'],
            categorize_market_cap(data['market_cap']),
            categorize_liquidity_tier(data['avg_volume']),
            is_etf, now, data['market_cap'], data['avg_volume'],
            tier, archive_db, today, symbol
        ))

        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO symbol_metadata
                (symbol, company_name, sector, industry, market_cap_category,
                 liquidity_tier, is_etf, options_available, updated_at,
                 market_cap, avg_volume, universe_tier, archive_db, tier_changed_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol, data['company_name'], data['sector'], data['industry'],
                categorize_market_cap(data['market_cap']),
                categorize_liquidity_tier(data['avg_volume']),
                is_etf, now, data['market_cap'], data['avg_volume'],
                tier, archive_db, today
            ))

        conn.commit()
    return 'done'


def _step_backfill_prices(symbol, db_path):
    """Step 2: Backfill historical_prices (~1 year)."""
    try:
        from data.tradier_historical_backfill import backfill_symbol
        count = backfill_symbol(symbol, db_path)
        return f'done  ({count} rows)' if count else 'done  (0 rows)'
    except ImportError:
        # Fallback: use TradierAPI directly
        from core.tradier_api import TradierAPI
        token = _load_tradier_token()
        api = TradierAPI(token)
        from datetime import timedelta
        end = now_eastern().strftime('%Y-%m-%d')
        start = (now_eastern() - timedelta(days=365)).strftime('%Y-%m-%d')

        resp = api.get_historical_quotes(symbol, start_date=start, end_date=end)
        if not resp or 'history' not in resp:
            return 'done  (0 rows - no history)'

        days = resp['history'].get('day', [])
        if isinstance(days, dict):
            days = [days]

        with sqlite3.connect(db_path, timeout=30.0) as conn:
            inserted = 0
            for day in days:
                try:
                    conn.execute('''
                        INSERT OR IGNORE INTO historical_prices
                        (symbol, trade_date, open_price, high_price, low_price,
                         close_price, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        symbol, day.get('date'), day.get('open'), day.get('high'),
                        day.get('low'), day.get('close'), day.get('volume')
                    ))
                    inserted += 1
                except Exception:
                    pass
            conn.commit()
        return f'done  ({inserted} rows)'


def _step_backfill_earnings(symbol, db_path):
    """Step 3: Backfill earnings_events via Tradier calendars."""
    try:
        from data.health.backfill_earnings_tradier import (
            load_config, phase1_fetch_events, phase2_upsert_events,
        )
        token = load_config()  # Returns API key string directly
        if not token:
            return 'fail  (no Tradier token)'

        # Fetch and insert earnings events for this symbol
        events, _stats = phase1_fetch_events(token, [symbol], batch_size=50)
        if not events:
            return 'done  (0 events from Tradier)'

        with sqlite3.connect(db_path, timeout=30.0) as conn:
            inserted = phase2_upsert_events(conn, events, dry_run=False)
            return f'done  ({inserted} events)'

    except Exception as e:
        return f'skip  ({e})'


def _step_compute_moves(symbol, db_path):
    """Step 4: Compute earnings_moves from events + prices."""
    try:
        from data.health.backfill_earnings_tradier import (
            phase3_infer_timing, phase4_compute_moves
        )
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            # Infer BMO/AMC timing
            phase3_infer_timing(conn, dry_run=False, symbol_filter=symbol)
            # Compute moves
            stats = phase4_compute_moves(conn, dry_run=False, symbol_filter=symbol)
            filled = stats.get('filled', 0) if isinstance(stats, dict) else stats
            return f'done  ({filled} moves)'
    except Exception as e:
        return f'skip  ({e})'


def _step_populate_upcoming(symbol, db_path):
    """Step 5: Populate earnings_upcoming with next earnings date."""
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        cursor = conn.cursor()
        today = now_eastern().strftime('%Y-%m-%d')

        # Check if there's a future earnings date in earnings_events
        cursor.execute('''
            SELECT earnings_date FROM earnings_events
            WHERE symbol = ? AND earnings_date >= ?
            ORDER BY earnings_date ASC LIMIT 1
        ''', (symbol, today))
        row = cursor.fetchone()

        if row:
            earnings_date = row[0]
            cursor.execute('''
                INSERT OR REPLACE INTO earnings_upcoming
                (symbol, earnings_date)
                VALUES (?, ?)
            ''', (symbol, earnings_date))
            conn.commit()
            return f'done  ({earnings_date})'

        # Try most recent past date as fallback indicator
        cursor.execute('''
            SELECT MAX(earnings_date) FROM earnings_events WHERE symbol = ?
        ''', (symbol,))
        row = cursor.fetchone()
        if row and row[0]:
            return f'skip  (no future date, last was {row[0]})'

        return 'skip  (no earnings data)'


def _step_generate_baseline(symbol, tier, db_path):
    """Step 6: Generate FM baseline (only for fm_universe)."""
    if tier != 'fm_universe':
        return 'skip  (daily_only tier)'

    try:
        import logging
        from strategies.flow_monitor.fm_baseline_generator import OptionBaselineGenerator
        logger = logging.getLogger()
        prev_level = logger.level
        logger.setLevel(logging.WARNING)
        try:
            gen = OptionBaselineGenerator()
            gen.generate_baselines(symbols=[symbol])
        finally:
            logger.setLevel(prev_level)
        return 'done'
    except Exception as e:
        return f'fail  ({e})'


def onboard_symbol(symbol, db_path, *, no_interaction=False, tier=None,
                   archive_db=None, create_archive=False, force=False):
    """Onboarding flow — interactive by default, scriptable via no_interaction.

    Args:
        symbol: Stock ticker (already uppercased)
        db_path: Path to datalake.db
        no_interaction: If True, skip all prompts; required values must be passed in.
        tier: 'fm_universe' or 'daily_only'. Required under no_interaction.
        archive_db: Archive DB name. Under no_interaction, defaults to
            determine_archive_db(sector, industry) if not passed.
        create_archive: Under no_interaction, allow auto-creation of missing archive DBs.
        force: Override the "already in universe" preflight failure.

    Returns:
        bool: True if onboarded, False on validation failure or user cancellation.
    """
    symbol = symbol.upper()

    # Step 1: Fetch info
    data = fetch_symbol_info(symbol)
    if data['errors']:
        for err in data['errors']:
            print(f'  API warning: {err}')

    # Step 2: Display card
    display_symbol_card(symbol, data)

    # Step 3: Pre-flight checks
    results = run_preflight_checks(symbol, data, db_path)
    display_preflight_results(results)

    operator = 'automation' if no_interaction else 'human'

    if no_interaction:
        if tier not in ('fm_universe', 'daily_only'):
            print(f'\nERROR: --tier must be fm_universe or daily_only (got: {tier!r})')
            return False

        not_in_universe = next((r for r in results if r.check_name == 'Not in universe'), None)
        if not_in_universe and not not_in_universe.passed and not force:
            print(f'\nERROR: pre-flight blocked: {not_in_universe.message}. Use --force to override.')
            return False

        if not archive_db:
            archive_db = determine_archive_db(data['sector'], data['industry'])
            if not archive_db:
                print(f'\nERROR: could not auto-route archive DB for sector={data["sector"]!r}. '
                      f'Pass --archive-db NAME.')
                return False

        if archive_db.endswith('.db'):
            archive_db = archive_db[:-3]

        archive_dir = os.path.join(project_root, 'data', 'sector_archive')
        archive_path = os.path.join(archive_dir, f'{archive_db}.db')
        if not os.path.exists(archive_path):
            if not create_archive:
                print(f'\nERROR: archive {archive_db}.db not found. '
                      f'Pass --create-archive to create it.')
                return False
            try:
                from data.health.create_sector_archive import create_sector_archive
                rc = create_sector_archive(archive_db, copy_reference=False, dry_run=False)
                if rc != 0:
                    print(f'\nERROR: failed to create archive {archive_db}.db (exit {rc})')
                    return False
            except Exception as e:
                print(f'\nERROR: failed to create archive {archive_db}.db: {e}')
                return False

        print(f'\n--no-interaction: tier={tier}, archive_db={archive_db}')
    else:
        # Step 4: Confirm
        if not prompt_yes_no(f'Add {symbol} to system?'):
            print('Cancelled.')
            return False

        # Step 5: Tier selection
        tier = prompt_choice('Tier assignment:', [
            ('fm_universe', 'FM_UNIVERSE  (full intraday scan)'),
            ('daily_only', 'DAILY_ONLY   (OP/EI only)'),
        ])
        if tier is None:
            print('Cancelled.')
            return False

        # Step 6: Archive routing
        archive_db = prompt_archive_db(data['sector'], data['industry'])
        if not archive_db:
            print('No archive DB specified. Cancelled.')
            return False

    # Execute onboarding steps
    total_steps = 7
    print('\nRunning onboarding steps:')

    step = 1
    status = _step_insert_metadata(symbol, data, tier, archive_db, db_path)
    display_progress_step(step, total_steps, 'Insert/update symbol_metadata', status)

    step = 2
    status = _step_backfill_prices(symbol, db_path)
    display_progress_step(step, total_steps, 'Backfill historical_prices', status)

    step = 3
    status = _step_backfill_earnings(symbol, db_path)
    display_progress_step(step, total_steps, 'Backfill earnings_events', status)

    step = 4
    status = _step_compute_moves(symbol, db_path)
    display_progress_step(step, total_steps, 'Compute earnings_moves', status)

    step = 5
    status = _step_populate_upcoming(symbol, db_path)
    display_progress_step(step, total_steps, 'Populate earnings_upcoming', status)

    step = 6
    status = _step_generate_baseline(symbol, tier, db_path)
    display_progress_step(step, total_steps, 'Generate FM baseline', status)

    step = 7
    event_id = log_lifecycle_event(
        db_path=db_path,
        symbol=symbol,
        event_type='onboarded',
        tier=tier,
        reason=f'{"Automated" if no_interaction else "Interactive"} onboarding via CLI',
        operator=operator,
        metadata_dict={
            'sector': data['sector'],
            'industry': data['industry'],
            'archive_db': archive_db,
            'avg_volume': data['avg_volume'],
            'market_cap': data['market_cap'],
        }
    )
    display_progress_step(step, total_steps, 'Log lifecycle event', f'done  (event #{event_id})')

    print(f'\nOnboarded {symbol}. Event ID: {event_id}')
    return True
