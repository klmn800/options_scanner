#!/usr/bin/env python3
"""
Earnings Intelligence Main Orchestrator (ei_main.py)
----------------------------------------------------
Orchestrator for the Earnings Intelligence daily pipeline.

Operational Modes:
1. --daily-pipeline: Unified 8-sub-step pipeline (6:35 AM pre-market, Step 1.2)
   Lite refresh, snapshots, archive, post-calc, expected moves, watchlist, news, arbitrage
2. --morning-scan: Standalone arbitrage scanner (available but not scheduled)
3. --all: Run daily pipeline (auto-detect mode)

Weekly refresh is handled separately by ei_collector.py, called directly
from main_runners.py on Fridays (Step 5.2). It does not go through this file.

Pipeline Components:
- ei_snapshot_collector.py: Daily IV/price snapshot collection
- ei_post_earnings_calc.py: Post-earnings calculation engine
- ei_moves_upcoming.py: Expected moves calculation
- ei_watchlist.py: Earnings watchlist population and lifecycle
- ei_arbitrage_scanner.py: Sector sympathy IV arbitrage scanner

Part of: Earnings Intelligence System (PRD 0003)
Author: Ben (with Claude)
Date: 2025-10-10
"""

import os
import sys
import time
import logging
import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# Add project root and tools to path for imports
def get_project_root():
    """Get the root directory of the project"""
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

project_root = get_project_root()
tools_dir = os.path.join(project_root, 'tools')

if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import now_eastern, eastern_date_string, eastern_isoformat
from log_utils import beautiful_log
import sqlite3


# =============================================================================
# EXECUTION FUNCTIONS
# =============================================================================

def run_daily_pipeline():
    """Execute unified earnings intelligence pipeline

    Sub-steps:
    1. Lite earnings refresh (near-term date verification + dispute flagging)
    2. Snapshot collection (IV/price for upcoming earnings)
    3. Archive past earnings (earnings_upcoming → earnings_events)
    4. Post-earnings calculation (for T-3 day events)
    5. Expected moves update (for all upcoming events)
    6. Watchlist population (earnings_watchlist table)
    7. News enrichment (Alpha Vantage sentiment for new/T-1 symbols)
    8. Arbitrage scan (sector sympathy opportunities)

    Returns:
        dict: Structured result with success, sub_tasks, alert_details, and summary metrics
    """
    # Only setup logging if not already configured (when running standalone)
    if not logging.getLogger().handlers:
        setup_logging('INFO', 'daily_pipeline')

    now = now_eastern()

    # Initialize health reporter and diagnostic logger
    from strategies.earnings_intel.ei_health_reporter import EIHealthReporter
    health_reporter = EIHealthReporter('daily-pipeline')
    diag_logger = setup_diagnostic_logging('daily-pipeline')

    mode_start = time.time()
    diag_logger.info("[{}] Daily Pipeline Started".format(now.strftime('%Y-%m-%d %H:%M:%S')))

    # Initialize metrics
    lite_refresh_results = {'symbols_checked': 0, 'dates_updated': 0, 'disputes_flagged': 0}
    snapshot_results = {'snapshots_created': 0, 'events_processed': 0, 'errors': 0}
    archive_results = {'archived': 0}
    calc_results = {'moves_calculated': 0, 'events_ready': 0, 'errors': 0}
    moves_results = {'processed': 0, 'failed': 0, 'alerts': 0, 'alert_details': []}
    watchlist_results = {'watchlist_count': 0, 'watchlist_new': 0, 'symbols': []}
    news_results = {'news_enriched': 0, 'news_skipped': 0, 'budget_exhausted': False}
    arb_results = {'opportunities_found': 0, 'earnings_today': 0, 'high_quality': 0,
                   'medium_quality': 0, 'low_quality': 0, 'persisted': 0}
    lite_refresh_success = True
    watchlist_success = False
    news_success = True
    arb_success = True

    try:
        # Import pipeline components
        import sys
        strategies_path = os.path.join(project_root, 'strategies', 'earnings_intel')
        if strategies_path not in sys.path:
            sys.path.insert(0, strategies_path)

        from strategies.earnings_intel.ei_snapshot_collector import SnapshotCollector
        from strategies.earnings_intel.ei_post_earnings_calc import PostEarningsCalculator
        from strategies.earnings_intel.ei_watchlist import populate_watchlist
        from strategies.earnings_intel.ei_arbitrage_scanner import ArbitrageScanner
        from strategies.earnings_intel.ei_lite_refresh import run_lite_refresh

        # Sub-step 1: Lite earnings refresh (near-term date verification)
        print("")
        beautiful_log("Lite Earnings Refresh (1/8)", 'info')
        beautiful_log("Verifying near-term earnings dates against yfinance + Finnhub", 'info')
        logging.info("   ├─ Scope: unconfirmed symbols within 21 days")
        logging.info("   └─ Flags disputes for earnings researcher agent")
        lite_refresh_start = time.time()
        try:
            db_path = os.path.join(project_root, 'data', 'datalake.db')
            perf_db_path = os.path.join(project_root, 'data', 'performance.db')
            lite_refresh_results = run_lite_refresh(
                db_path=db_path, perf_db_path=perf_db_path)
            lite_refresh_success = lite_refresh_results.get('success', False)
            health_reporter.track_task_result(
                'Lite Earnings Refresh',
                lite_refresh_success,
                symbols_checked=lite_refresh_results.get('symbols_checked', 0),
                dates_updated=lite_refresh_results.get('dates_updated', 0),
                disputes_flagged=lite_refresh_results.get('disputes_flagged', 0),
                duration=time.time() - lite_refresh_start
            )
        except Exception as e:
            logging.warning("   └─ Lite refresh failed: {}".format(e))
            lite_refresh_success = False
            health_reporter.track_task_result('Lite Earnings Refresh', False, error=str(e))
        lite_refresh_time = time.time() - lite_refresh_start

        # Sub-step 2: Snapshot collection
        print("")
        beautiful_log("Snapshot Collection (2/8)", 'info')
        beautiful_log("Collecting end-of-day snapshots for upcoming earnings", 'info')
        logging.info("   ├─ Window: T-7 to T+5 around earnings date")
        logging.info("   └─ Sources: historical_prices (OHLC) + option_symbol_summary (IV)")
        snapshot_start = time.time()
        try:
            collector = SnapshotCollector()
            snapshot_results = collector.collect_daily_snapshots()
            snapshot_success = snapshot_results['errors'] == 0
            logging.info("   └─ Snapshots: {} created".format(snapshot_results['snapshots_created']))
            health_reporter.track_task_result(
                'Snapshot Collection',
                snapshot_success,
                snapshots_created=snapshot_results.get('snapshots_created', 0),
                events_processed=snapshot_results.get('events_processed', 0),
                errors=snapshot_results.get('errors', 0),
                duration=time.time() - snapshot_start
            )
        except Exception as e:
            logging.warning("   └─ Snapshot collection failed: {}".format(e))
            snapshot_success = False
            health_reporter.track_task_result('Snapshot Collection', False, error=str(e))
        snapshot_time = time.time() - snapshot_start

        # Sub-step 3: Archive past earnings (earnings_upcoming → earnings_events)
        print("")
        beautiful_log("Archive Past Earnings (3/8)", 'info')
        beautiful_log("Moving past-date earnings to events archive", 'info')
        logging.info("   ├─ Source: earnings_upcoming WHERE earnings_date < today")
        logging.info("   └─ Target: earnings_events (INSERT OR IGNORE, preserves signals)")
        archive_start = time.time()
        archive_success = True
        try:
            db_path = os.path.join(project_root, 'data', 'datalake.db')
            conn = sqlite3.connect(db_path, timeout=30)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO earnings_events
                    (symbol, earnings_date, fiscal_year, fiscal_quarter,
                     estimated_eps, actual_eps, earnings_time, source, is_backfilled,
                     earnings_play_signal, relative_underpricing_pct,
                     straddle_expected_move_pct,
                     historical_avg_move_pct, historical_avg_move_alltime_pct,
                     historical_quarters_used, eps_estimate, revenue_estimate)
                SELECT
                    symbol, earnings_date, NULL, NULL,
                    NULL, NULL, earnings_time, 'earnings_upcoming', 0,
                    earnings_play_signal, relative_underpricing_pct,
                    straddle_expected_move_pct,
                    historical_avg_move_pct, historical_avg_move_alltime_pct,
                    historical_quarters_used, eps_estimate, revenue_estimate
                FROM earnings_upcoming
                WHERE earnings_date < DATE('now')
                AND earnings_date IS NOT NULL
            """)
            archived = cursor.rowcount
            conn.commit()
            conn.close()
            archive_results = {'archived': archived}
            logging.info("   Archived {} past events".format(archived))
            health_reporter.track_task_result(
                'Archive Past Earnings', True,
                events_archived=archived,
                duration=time.time() - archive_start)
        except Exception as e:
            logging.warning("   Archive failed: {}".format(e))
            archive_success = False
            health_reporter.track_task_result('Archive Past Earnings', False, error=str(e))
        archive_time = time.time() - archive_start

        # Sub-step 3.5: Backfill event_id on earnings_snapshots
        # Closes the writer race (writer runs in Sub-step 2 BEFORE this archive
        # step has populated earnings_events) and picks up pre-earnings rows
        # whose events have now archived. Idempotent — WHERE event_id IS NULL.
        # SQL uses `UPDATE ... FROM` form (SQLite 3.33+). The correlated-subquery
        # form with JULIANDAY(es.earnings_date) inside the inner WHERE is rejected
        # by SQLite 3.49 with "no such column" — see proposals/feedback/020_*.md.
        # Events are quarterly (~90d apart), so the 3-day window matches at most
        # one event per snapshot row in practice; no closest-match LIMIT needed.
        print("")
        beautiful_log("Backfill event_id on earnings_snapshots (3.5/8)", 'info')
        backfill_start = time.time()
        try:
            db_path = os.path.join(project_root, 'data', 'datalake.db')
            conn = sqlite3.connect(db_path, timeout=30)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE earnings_snapshots AS es
                SET event_id = ee.event_id
                FROM earnings_events AS ee
                WHERE es.event_id IS NULL
                  AND ee.symbol = es.symbol
                  AND ABS(JULIANDAY(ee.earnings_date) - JULIANDAY(es.earnings_date)) <= 3
            """)
            rows_populated = cursor.rowcount
            conn.commit()
            conn.close()
            logging.info("   Populated event_id on {} earnings_snapshots rows".format(rows_populated))
            health_reporter.track_task_result(
                'event_id Backfill', True,
                rows_populated=rows_populated,
                duration=time.time() - backfill_start)
        except Exception as e:
            logging.warning("   event_id backfill failed: {}".format(e))
            health_reporter.track_task_result('event_id Backfill', False, error=str(e))
        backfill_time = time.time() - backfill_start

        # Sub-step 4: Post-earnings calculation
        print("")
        beautiful_log("Post-Earnings Calculation (4/8)", 'info')
        beautiful_log("Calculating price moves and IV crush for T+3 events", 'info')
        logging.info("   ├─ Sources: earnings_snapshots → historical_prices fallback")
        calc_start = time.time()
        try:
            calculator = PostEarningsCalculator()
            calc_results = calculator.calculate_post_earnings_metrics()
            calc_success = calc_results['errors'] == 0
            logging.info("   └─ Moves calculated: {}".format(calc_results['moves_calculated']))
            health_reporter.track_task_result(
                'Post-Earnings Calculation',
                calc_success,
                moves_calculated=calc_results.get('moves_calculated', 0),
                events_ready=calc_results.get('events_ready', 0),
                errors=calc_results.get('errors', 0),
                duration=time.time() - calc_start
            )
        except Exception as e:
            logging.warning("   └─ Calculation failed: {}".format(e))
            calc_success = False
            health_reporter.track_task_result('Post-Earnings Calculation', False, error=str(e))
        calc_time = time.time() - calc_start

        # Sub-step 5: Expected moves update (check if exists first)
        print("")
        beautiful_log("Expected Moves Update (5/8)", 'info')
        beautiful_log("Recalculating signals with latest IV data", 'info')
        logging.info("   ├─ Methods: ATM straddle (primary) + IV-based (fallback)")
        logging.info("   └─ Universe: all symbols with earnings_date >= today")
        moves_start = time.time()
        moves_upcoming_path = os.path.join(strategies_path, 'ei_moves_upcoming.py')
        if os.path.exists(moves_upcoming_path):
            try:
                from strategies.earnings_intel.ei_moves_upcoming import update_expected_moves
                moves_results = update_expected_moves()
                moves_success = True
                health_reporter.track_task_result(
                    'Expected Moves Update',
                    True,
                    moves_updated=moves_results.get('processed', 0),
                    duration=time.time() - moves_start
                )
            except Exception as e:
                logging.warning("   └─ Update failed: {}".format(e))
                moves_success = False
                health_reporter.track_task_result('Expected Moves Update', False, error=str(e))
        else:
            logging.info("   └─ ei_moves_upcoming.py not yet implemented - skipping")
            moves_success = True  # Don't fail if not implemented yet
            health_reporter.track_task_result('Expected Moves Update', True, skipped=True)
        moves_time = time.time() - moves_start

        # Sub-step 6: Watchlist population
        print("")
        beautiful_log("Watchlist Population (6/8)", 'info')
        beautiful_log("Filtering to actionable earnings plays", 'info')
        logging.info("   ├─ Entry: signal >= WATCH, <=14 days, OI >= 4,000")
        logging.info("   └─ Lifecycle: UPCOMING → TODAY → T+1 → T+2 → T+3 → delete T+4")
        watchlist_start = time.time()
        try:
            wl_result = populate_watchlist()
            watchlist_success = wl_result.get('success', False)
            watchlist_results = {
                'watchlist_count': wl_result.get('watchlist_count', 0),
                'watchlist_new': wl_result.get('watchlist_new', 0),
                'symbols': wl_result.get('watchlist_symbols', []),
                'removed': wl_result.get('removed_count', 0),
                'breakdown': wl_result.get('watchlist_breakdown', {}),
            }
            health_reporter.track_task_result(
                'Watchlist Population',
                watchlist_success,
                watchlist_count=watchlist_results['watchlist_count'],
                new_entries=watchlist_results['watchlist_new'],
                duration=time.time() - watchlist_start
            )
        except Exception as e:
            logging.warning("   └─ Watchlist population failed: {}".format(e))
            watchlist_success = False
            health_reporter.track_task_result('Watchlist Population', False, error=str(e))
        watchlist_time = time.time() - watchlist_start

        # Sub-step 7: News enrichment (depends on sub-step 6)
        print("")
        beautiful_log("News Enrichment (7/8)", 'info')
        beautiful_log("Adding news sentiment scores to earnings watchlist", 'info')
        logging.info("   ├─ Retrieving articles and sentiment scores from Alpha Vantage")
        logging.info("   ├─ Targets: new watchlist entries + T-1 symbols")
        logging.info("   └─ Lookback: 3 days, limit 50 articles/symbol")
        news_start = time.time()
        news_enriched = 0
        news_no_sentiment = 0
        news_failed = 0
        news_skipped = 0
        news_budget_exhausted = False
        news_budget_remaining = 25  # Track for summary
        try:
            if not watchlist_success or watchlist_results.get('watchlist_count', 0) == 0:
                logging.info("   No watchlist entries to enrich — skipping")
                news_success = True
            else:
                from tools.news_sentiment import get_budget_status, enrich_watchlist_symbol, create_av_client
                from tools.decimal_formatter import clean_database_row

                # Shared AV client — keeps per-minute rate limiter alive across calls
                av_client = create_av_client()

                db_path = os.path.join(project_root, 'data', 'datalake.db')
                today_str = eastern_date_string()
                now_ts = eastern_isoformat()

                # Get symbols needing news: new entries today OR T-1 (days_to_earnings = 1)
                with sqlite3.connect(db_path) as conn:
                    conn.execute("PRAGMA busy_timeout = 30000")
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT symbol FROM earnings_watchlist
                        WHERE first_appeared_date = ? OR days_to_earnings = 1
                    """, (today_str,))
                    candidates = [row[0] for row in cursor.fetchall()]

                if not candidates:
                    logging.info("   No symbols need news enrichment today")
                    news_success = True
                else:
                    # Filter out symbols already fetched today
                    symbols_to_enrich = []
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("PRAGMA busy_timeout = 30000")
                        cursor = conn.cursor()
                        for sym in candidates:
                            cursor.execute("""
                                SELECT COUNT(*) FROM news_symbol_sentiment
                                WHERE symbol = ? AND DATE(time_collected) = ?
                            """, (sym, today_str))
                            count = cursor.fetchone()[0]
                            if count == 0:
                                symbols_to_enrich.append(sym)
                            else:
                                news_skipped += 1

                    if not symbols_to_enrich:
                        logging.info("   All {} candidates already have today's news".format(
                            len(candidates)))
                        news_success = True
                    else:
                        # Check budget before starting
                        budget = get_budget_status(av_client=av_client)
                        news_budget_remaining = budget.get('remaining', 0)
                        if not budget.get('can_make_request', False):
                            logging.info("   Budget exhausted ({}/25 used) — skipping {}".format(
                                budget.get('used', 25), ', '.join(symbols_to_enrich)))
                            news_budget_exhausted = True
                            news_success = True  # Budget exhaustion is not an error
                        else:
                            logging.info("   Fetching news for {} symbols (budget: {}/25 remaining)".format(
                                len(symbols_to_enrich), news_budget_remaining))

                            for sym in symbols_to_enrich:
                                # Re-check budget each iteration
                                budget = get_budget_status(av_client=av_client)
                                news_budget_remaining = budget.get('remaining', 0)
                                if not budget.get('can_make_request', False):
                                    remaining_syms = symbols_to_enrich[
                                        symbols_to_enrich.index(sym):]
                                    logging.info("   Budget exhausted — skipped: {}".format(
                                        ', '.join(remaining_syms)))
                                    news_budget_exhausted = True
                                    break

                                result = enrich_watchlist_symbol(sym, av_client=av_client)
                                if result.get('success') and result.get('sentiment'):
                                    sentiment = result['sentiment']
                                    cleaned = clean_database_row(sentiment)

                                    # Per-symbol result line
                                    logging.info("     {}: {} articles, score={} ({})".format(
                                        sym,
                                        cleaned.get('news_article_count', 0),
                                        cleaned.get('news_sentiment_score', 'N/A'),
                                        cleaned.get('news_sentiment_label', 'No Data')
                                    ))

                                    with sqlite3.connect(db_path) as conn:
                                        conn.execute("PRAGMA busy_timeout = 30000")
                                        conn.execute("""
                                            UPDATE earnings_watchlist
                                            SET news_sentiment_score = ?,
                                                news_sentiment_label = ?,
                                                news_article_count = ?,
                                                last_updated = ?
                                            WHERE symbol = ?
                                        """, (
                                            cleaned.get('news_sentiment_score'),
                                            cleaned.get('news_sentiment_label'),
                                            cleaned.get('news_article_count'),
                                            now_ts,
                                            sym
                                        ))
                                        conn.commit()
                                    news_enriched += 1
                                elif result.get('success'):
                                    # No sentiment for this symbol (articles don't mention it)
                                    logging.info("     {}: no symbol-specific sentiment".format(sym))
                                    news_no_sentiment += 1
                                else:
                                    logging.info("     {}: fetch failed".format(sym))
                                    news_failed += 1

                            # Update final budget after all calls
                            budget = get_budget_status(av_client=av_client)
                            news_budget_remaining = budget.get('remaining', 0)
                            news_success = True

            news_results = {
                'news_enriched': news_enriched,
                'news_skipped': news_no_sentiment + news_failed,  # backward compat
                'news_no_sentiment': news_no_sentiment,
                'news_failed': news_failed,
                'budget_exhausted': news_budget_exhausted,
                'budget_remaining': news_budget_remaining,
            }

            # Persist API usage counters to daily_state.json
            ei_api_calls = news_enriched + news_no_sentiment + news_failed
            if ei_api_calls > 0:
                try:
                    from main_ui import _save_news_api_usage
                    _save_news_api_usage(
                        source='ei',
                        api_calls=ei_api_calls,
                        symbols_enriched=news_enriched,
                        zero_article_calls=news_failed,
                    )
                except Exception as usage_err:
                    logging.debug("Could not save news API usage: {}".format(usage_err))

            logging.info("   Enriched: {} | No sentiment: {} | Failed: {} | Budget remaining: {}/25".format(
                news_enriched, news_no_sentiment, news_failed, news_budget_remaining))

            # Refresh watchlist_symbols so console table includes news sentiment
            if news_enriched > 0:
                try:
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("PRAGMA busy_timeout = 30000")
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT * FROM earnings_watchlist ORDER BY days_to_earnings ASC, earnings_date ASC"
                        )
                        columns = [desc[0] for desc in cursor.description]
                        watchlist_results['symbols'] = [dict(zip(columns, row)) for row in cursor.fetchall()]
                except Exception as refresh_err:
                    logging.debug("Could not refresh watchlist for display: {}".format(refresh_err))

            health_reporter.track_task_result(
                'News Enrichment',
                news_success,
                enriched=news_enriched,
                skipped=news_skipped,
                budget_exhausted=news_budget_exhausted,
                duration=time.time() - news_start
            )
        except Exception as e:
            logging.warning("   News enrichment failed: {}".format(e))
            news_success = False
            health_reporter.track_task_result('News Enrichment', False, error=str(e))
        news_time = time.time() - news_start

        # Sub-step 8: Arbitrage scan (independent of other sub-steps)
        # Scans for sector sympathy IV plays: when a stock reports earnings,
        # its industry peers often see correlated moves. The scanner finds peers
        # with cheap IV relative to the primary's buildup, scores them by
        # IV discount + historical correlation, and persists to earnings_sector_effects.
        # Currently in development — needs historical data to accumulate in
        # earnings_sector_effects before the correlation component adds value.
        print("")
        beautiful_log("Arbitrage Scan (8/8)", 'info')
        beautiful_log("Scanning for sector sympathy IV opportunities", 'info')
        logging.info("   ├─ Finds peers with cheap IV when a stock reports earnings")
        logging.info("   └─ Status: in development — accumulating historical correlation data")
        arb_start = time.time()
        # try:
        #     scanner = ArbitrageScanner()
        #     scan_results = scanner.scan_morning_opportunities()
        #
        #     if scan_results.get('earnings_today', 0) == 0:
        #         logging.info("  No earnings reporting today — arbitrage scan skipped")
        #         arb_success = True
        #     else:
        #         arb_success = scan_results.get('errors', 0) == 0
        #         arb_results = {
        #             'opportunities_found': scan_results.get('opportunities_found', 0),
        #             'earnings_today': scan_results.get('earnings_today', 0),
        #             'high_quality': scan_results.get('high_quality', 0),
        #             'medium_quality': scan_results.get('medium_quality', 0),
        #             'low_quality': scan_results.get('low_quality', 0),
        #             'persisted': scan_results.get('persisted', 0),
        #         }
        #         logging.info("  Arbitrage: {} opportunities from {} earnings".format(
        #             arb_results['opportunities_found'], arb_results['earnings_today']))
        #
        #     health_reporter.track_task_result(
        #         'Arbitrage Scanner',
        #         arb_success,
        #         earnings_today=arb_results.get('earnings_today', 0),
        #         opportunities_found=arb_results.get('opportunities_found', 0),
        #         duration=time.time() - arb_start
        #     )
        # except Exception as e:
        #     logging.warning("  Arbitrage scan failed: {}".format(e))
        #     arb_success = False
        #     health_reporter.track_task_result('Arbitrage Scanner', False, error=str(e))
        arb_success = True
        health_reporter.track_task_result('Arbitrage Scanner', True, skipped=True)
        arb_time = time.time() - arb_start

        # Summary — pipeline success = completed (per PRD Req 28: True if pipeline
        # itself didn't crash, even if individual sub-steps failed)
        all_success = True
        total_time = time.time() - mode_start
        sub_successes = [lite_refresh_success, snapshot_success, archive_success,
                         calc_success, moves_success, watchlist_success,
                         news_success, arb_success]
        tasks_successful = sum(sub_successes)
        total_errors = (snapshot_results.get('errors', 0) +
                        calc_results.get('errors', 0) +
                        moves_results.get('failed', 0))

        # Log diagnostic summary
        log_diagnostic_summary(
            diag_logger,
            'daily-pipeline',
            lite_refresh_checked=lite_refresh_results.get('symbols_checked', 0),
            lite_refresh_updated=lite_refresh_results.get('dates_updated', 0),
            lite_refresh_disputes=lite_refresh_results.get('disputes_flagged', 0),
            lite_refresh_time=lite_refresh_time,
            snapshots_created=snapshot_results.get('snapshots_created', 0),
            events_processed=snapshot_results.get('events_processed', 0),
            snapshot_time=snapshot_time,
            events_archived=archive_results.get('archived', 0),
            archive_time=archive_time,
            moves_calculated=calc_results.get('moves_calculated', 0),
            events_ready=calc_results.get('events_ready', 0),
            calc_time=calc_time,
            moves_updated=moves_results.get('processed', 0),
            moves_time=moves_time,
            watchlist_count=watchlist_results.get('watchlist_count', 0),
            watchlist_new=watchlist_results.get('watchlist_new', 0),
            watchlist_time=watchlist_time,
            news_enriched=news_results.get('news_enriched', 0),
            news_time=news_time,
            arb_opportunities=arb_results.get('opportunities_found', 0),
            arb_time=arb_time,
            total_time=total_time,
            tasks_successful=tasks_successful,
            total_sub_steps=8
        )

        # Generate health report
        health_reporter.generate_health_report(all(sub_successes))
        health_reporter.write_json_health_status()

        return {
            'success': all_success,
            'duration_seconds': total_time,
            'errors': total_errors,
            'failed_symbols': [],
            'sub_tasks': {
                'lite_refresh': {
                    'success': lite_refresh_success,
                    'duration_seconds': lite_refresh_time,
                    'symbols_checked': lite_refresh_results.get('symbols_checked', 0),
                    'dates_updated': lite_refresh_results.get('dates_updated', 0),
                    'disputes_flagged': lite_refresh_results.get('disputes_flagged', 0),
                },
                'snapshots': {
                    'success': snapshot_success,
                    'duration_seconds': snapshot_time,
                    'data_date': snapshot_results.get('data_date'),
                    'events_in_window': snapshot_results.get('events_in_window', 0),
                    'events_processed': snapshot_results.get('events_processed', 0),
                    'snapshots_created': snapshot_results.get('snapshots_created', 0),
                    'snapshots_skipped': snapshot_results.get('snapshots_skipped', 0),
                    'errors': snapshot_results.get('errors', 0),
                },
                'archive': {
                    'success': archive_success,
                    'duration_seconds': archive_time,
                    'events_archived': archive_results.get('archived', 0),
                },
                'calculations': {
                    'success': calc_success,
                    'duration_seconds': calc_time,
                    'trade_date': calc_results.get('trade_date'),
                    'events_ready': calc_results.get('events_ready', 0),
                    'moves_calculated': calc_results.get('moves_calculated', 0),
                    'sector_effects_calculated': calc_results.get('sector_effects_calculated', 0),
                    'errors': calc_results.get('errors', 0),
                },
                'expected_moves': {
                    'success': moves_success,
                    'duration_seconds': moves_time,
                    'processed': moves_results.get('processed', 0),
                    'failed': moves_results.get('failed', 0),
                    'alerts': moves_results.get('alerts', 0),
                },
                'watchlist': {
                    'success': watchlist_success,
                    'duration_seconds': watchlist_time,
                    'watchlist_count': watchlist_results.get('watchlist_count', 0),
                    'new_entries': watchlist_results.get('watchlist_new', 0),
                    'removed': watchlist_results.get('removed', 0),
                    'breakdown': watchlist_results.get('breakdown', {}),
                },
                'news_enrichment': {
                    'success': news_success,
                    'duration_seconds': news_time,
                    'enriched': news_results.get('news_enriched', 0),
                    'skipped': news_results.get('news_skipped', 0),
                    'budget_exhausted': news_results.get('budget_exhausted', False),
                },
                'arbitrage': {
                    'success': arb_success,
                    'duration_seconds': arb_time,
                    'earnings_today': arb_results.get('earnings_today', 0),
                    'opportunities_found': arb_results.get('opportunities_found', 0),
                    'high_quality': arb_results.get('high_quality', 0),
                    'medium_quality': arb_results.get('medium_quality', 0),
                    'low_quality': arb_results.get('low_quality', 0),
                    'persisted': arb_results.get('persisted', 0),
                },
            },
            # Top-level summary fields (PRD Req 10)
            'snapshots_created': snapshot_results.get('snapshots_created', 0),
            'moves_calculated': calc_results.get('moves_calculated', 0),
            'alerts_triggered': moves_results.get('alerts', 0),
            'alert_details': moves_results.get('alert_details', []),
            'watchlist_count': watchlist_results.get('watchlist_count', 0),
            'watchlist_new': watchlist_results.get('watchlist_new', 0),
            'watchlist_symbols': watchlist_results.get('symbols', []),
            'signals_updated': moves_results.get('processed', 0),
            'watchlist_breakdown': watchlist_results.get('breakdown', {}),
            'news_enriched': news_results.get('news_enriched', 0),
            'arb_opportunities': arb_results.get('opportunities_found', 0),
        }

    except Exception as e:
        logging.error("Daily pipeline failed: {}".format(e))
        traceback.print_exc()
        health_reporter.track_error()

        # Generate health report even on failure
        health_reporter.generate_health_report(False)
        health_reporter.write_json_health_status()
        return {
            'success': False,
            'failure_reason': str(e),
            'duration_seconds': time.time() - mode_start,
            'errors': 1,
            'failed_symbols': [],
            'sub_tasks': {},
            'snapshots_created': 0,
            'moves_calculated': 0,
            'alerts_triggered': 0,
            'alert_details': [],
            'watchlist_count': 0,
            'watchlist_new': 0,
            'watchlist_symbols': [],
            'signals_updated': 0,
            'watchlist_breakdown': {},
            'news_enriched': 0,
            'arb_opportunities': 0,
        }

def run_morning_scan():
    """Execute morning arbitrage scan mode (6:30 AM daily)

    NOTE: As of PRD 0008, the arbitrage scan is also available as sub-step 7
    of run_daily_pipeline(). This standalone function is kept for backward
    compatibility with main.py Step 1.2 until the orchestrator is updated.

    Tasks:
    1. Scan today's earnings for arbitrage opportunities
    2. Find peers with cheap IV (sector sympathy plays)
    3. Update morning view flags

    Returns:
        dict: Structured result with success, scan metrics, and error info
    """
    # Only setup logging if not already configured (when running standalone)
    if not logging.getLogger().handlers:
        setup_logging('INFO', 'morning_scan')

    now = now_eastern()

    # Initialize health reporter and diagnostic logger
    from strategies.earnings_intel.ei_health_reporter import EIHealthReporter
    health_reporter = EIHealthReporter('morning-scan')
    diag_logger = setup_diagnostic_logging('morning-scan')

    mode_start = time.time()
    diag_logger.info("[{}] Morning Scan Started".format(now.strftime('%Y-%m-%d %H:%M:%S')))

    # Failure result template
    def _failure_result(reason, duration):
        return {
            'success': False,
            'failure_reason': reason,
            'duration_seconds': duration,
            'errors': 1,
            'failed_symbols': [],
            'scan_date': '',
            'earnings_today': 0,
            'opportunities_found': 0,
            'high_quality': 0,
            'medium_quality': 0,
            'low_quality': 0,
            'persisted': 0,
        }

    try:
        # Import scanner
        import sys
        strategies_path = os.path.join(project_root, 'strategies', 'earnings_intel')
        if strategies_path not in sys.path:
            sys.path.insert(0, strategies_path)

        from strategies.earnings_intel.ei_arbitrage_scanner import ArbitrageScanner

        scanner = ArbitrageScanner()
        scan_start = time.time()
        scan_results = scanner.scan_morning_opportunities()
        scan_time = time.time() - scan_start

        # Early exit: no earnings today — single line, skip full output
        if scan_results.get('earnings_today', 0) == 0:
            logging.info("No earnings reporting today — scan skipped.")
            total_time = time.time() - mode_start
            diag_logger.info("[{}] Morning Scan: No earnings today ({:.1f}s)".format(
                now_eastern().strftime('%Y-%m-%d %H:%M:%S'), scan_time))
            health_reporter.track_task_result('Arbitrage Scanner', True, earnings_today=0, duration=scan_time)
            health_reporter.generate_health_report(True)
            health_reporter.write_json_health_status()
            return {
                'success': True,
                'duration_seconds': total_time,
                'errors': 0,
                'failed_symbols': [],
                'scan_date': scan_results.get('scan_date', ''),
                'earnings_today': 0,
                'opportunities_found': 0,
                'high_quality': 0,
                'medium_quality': 0,
                'low_quality': 0,
                'persisted': 0,
            }

        # Earnings found — show full results
        scan_success = scan_results['errors'] == 0

        logging.info("  Scan complete: {} opportunities found from {} earnings events".format(
            scan_results['opportunities_found'], scan_results['earnings_today']))
        logging.info("   High quality: {} | Medium: {} | Low: {}".format(
            scan_results['high_quality'],
            scan_results['medium_quality'],
            scan_results['low_quality']
        ))

        health_reporter.track_task_result(
            'Arbitrage Scanner',
            scan_success,
            earnings_today=scan_results.get('earnings_today', 0),
            opportunities_found=scan_results.get('opportunities_found', 0),
            high_quality=scan_results.get('high_quality', 0),
            medium_quality=scan_results.get('medium_quality', 0),
            low_quality=scan_results.get('low_quality', 0),
            errors=scan_results.get('errors', 0),
            duration=scan_time
        )

        # Summary
        total_time = time.time() - mode_start

        # Log diagnostic summary
        log_diagnostic_summary(
            diag_logger,
            'morning-scan',
            earnings_today=scan_results.get('earnings_today', 0),
            opportunities_found=scan_results.get('opportunities_found', 0),
            high_quality=scan_results.get('high_quality', 0),
            medium_quality=scan_results.get('medium_quality', 0),
            low_quality=scan_results.get('low_quality', 0),
            scan_time=scan_time,
            total_time=total_time
        )

        # Generate health report
        health_reporter.generate_health_report(scan_success)
        health_reporter.write_json_health_status()

        return {
            'success': scan_success,
            'duration_seconds': total_time,
            'errors': scan_results.get('errors', 0),
            'failed_symbols': [],
            'scan_date': scan_results.get('scan_date', ''),
            'earnings_today': scan_results.get('earnings_today', 0),
            'opportunities_found': scan_results.get('opportunities_found', 0),
            'high_quality': scan_results.get('high_quality', 0),
            'medium_quality': scan_results.get('medium_quality', 0),
            'low_quality': scan_results.get('low_quality', 0),
            'persisted': scan_results.get('persisted', 0),
        }

    except Exception as e:
        logging.error("Morning scan failed: {}".format(e))
        traceback.print_exc()
        health_reporter.track_error()

        # Generate health report even on failure
        health_reporter.generate_health_report(False)
        health_reporter.write_json_health_status()
        return _failure_result(str(e), time.time() - mode_start)

def run_all_mode():
    """Execute all mode - runs the daily pipeline.

    Weekly refresh is handled separately by ei_collector.py (Friday Phase 5).

    Returns:
        bool: True if all tasks successful, False otherwise
    """
    logging.info("Running daily pipeline...")
    result = run_daily_pipeline()
    return result.get('success', False)

# =============================================================================
# LOGGING SETUP (Pattern from oid_main.py)
# =============================================================================

def setup_logging(log_level='INFO', mode=None):
    """Configure logging for EP orchestrator with UTF-8 encoding

    Args:
        log_level: Logging level (INFO, DEBUG, etc.)
        mode: Execution mode for log file naming

    Returns:
        str: Path to log file
    """
    # CHANGED: Create centralized logs directory at project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # CHANGED: Centralized location, renamed from ei to earnings_intel, include mode in filename
    date_str = datetime.now().strftime('%Y-%m-%d')
    if mode:
        log_filename = 'earnings_intel_{}_{}.log'.format(mode, date_str)
    else:
        log_filename = 'earnings_intel_{}.log'.format(date_str)

    log_file_path = os.path.join(logs_dir, log_filename)

    # Configure logging with UTF-8 encoding
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatters — file keeps milliseconds, console gets clean HH:MM:SS
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_formatter.default_msec_format = None

    # File handler with UTF-8 encoding
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(console_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers = []

    # Add our handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info("Logging initialized - Level: {} - File: {}".format(log_level, log_filename))
    if mode:
        logging.info("Execution mode: {}".format(mode))

    return log_file_path

def setup_diagnostic_logging(mode):
    """Set up separate diagnostic log for high-level summaries only

    Args:
        mode: Execution mode for log file naming

    Returns:
        logging.Logger: Diagnostic logger instance
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    logs_dir = Path(project_root) / "logs" / "diagnostic"
    logs_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime('%Y-%m-%d')
    logfile_name = 'earnings_intel_{}_{}.log'.format(mode, date_str)
    logfile = logs_dir / logfile_name

    diag_logger = logging.getLogger('earnings_intel_diagnostic_{}'.format(mode))
    diag_logger.setLevel(logging.INFO)
    diag_logger.propagate = False  # Don't send to root logger

    # Clear existing handlers
    diag_logger.handlers = []

    # File handler only (no console spam)
    file_handler = logging.FileHandler(logfile, encoding='utf-8')
    formatter = logging.Formatter('%(message)s')  # Simple format
    file_handler.setFormatter(formatter)
    diag_logger.addHandler(file_handler)

    return diag_logger

def log_diagnostic_summary(diag_logger, mode, **metrics):
    """Write high-level diagnostic summary for this operation

    Args:
        diag_logger: Diagnostic logger instance
        mode: Operational mode
        **metrics: Mode-specific metrics to log
    """
    try:
        now = now_eastern().strftime('%Y-%m-%d %H:%M:%S')

        if mode == 'daily-pipeline':
            # Daily pipeline summary (8 sub-steps)
            diag_logger.info("[{}] Lite Refresh: {} checked | {} updated | {} disputes | {:.1f}s".format(
                now,
                metrics.get('lite_refresh_checked', 0),
                metrics.get('lite_refresh_updated', 0),
                metrics.get('lite_refresh_disputes', 0),
                metrics.get('lite_refresh_time', 0)
            ))
            diag_logger.info("[{}] Snapshots: {} created | {} events processed | {:.1f}s".format(
                now,
                metrics.get('snapshots_created', 0),
                metrics.get('events_processed', 0),
                metrics.get('snapshot_time', 0)
            ))
            diag_logger.info("[{}] Archive: {} events archived | {:.1f}s".format(
                now,
                metrics.get('events_archived', 0),
                metrics.get('archive_time', 0)
            ))
            diag_logger.info("[{}] Post-Calc: {} moves calculated | {} events analyzed | {:.1f}s".format(
                now,
                metrics.get('moves_calculated', 0),
                metrics.get('events_ready', 0),
                metrics.get('calc_time', 0)
            ))
            diag_logger.info("[{}] Expected Moves: {} updated | {:.1f}s".format(
                now,
                metrics.get('moves_updated', 0),
                metrics.get('moves_time', 0)
            ))
            diag_logger.info("[{}] Watchlist: {} symbols ({} new) | {:.1f}s".format(
                now,
                metrics.get('watchlist_count', 0),
                metrics.get('watchlist_new', 0),
                metrics.get('watchlist_time', 0)
            ))
            diag_logger.info("[{}] News: {} enriched | {:.1f}s".format(
                now,
                metrics.get('news_enriched', 0),
                metrics.get('news_time', 0)
            ))
            diag_logger.info("[{}] Arbitrage: {} opportunities | {:.1f}s".format(
                now,
                metrics.get('arb_opportunities', 0),
                metrics.get('arb_time', 0)
            ))
            total_sub = metrics.get('total_sub_steps', 8)
            diag_logger.info("[{}] Daily Pipeline Complete | Total: {:.1f}s | Success: {}/{}".format(
                now,
                metrics.get('total_time', 0),
                metrics.get('tasks_successful', 0),
                total_sub
            ))

        elif mode == 'morning-scan':
            # Morning scan summary
            diag_logger.info("[{}] Scan: {} earnings today | {} opportunities found ({} HIGH, {} MED, {} LOW) | {:.1f}s".format(
                now,
                metrics.get('earnings_today', 0),
                metrics.get('opportunities_found', 0),
                metrics.get('high_quality', 0),
                metrics.get('medium_quality', 0),
                metrics.get('low_quality', 0),
                metrics.get('scan_time', 0)
            ))
            diag_logger.info("[{}] Morning Scan Complete | Total: {:.1f}s | Success: 1/1".format(
                now,
                metrics.get('total_time', 0)
            ))

    except Exception as e:
        logging.error("Error writing diagnostic summary: {}".format(e))

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Earnings Intelligence Daily Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution Modes:
  --daily-pipeline    Run unified 6-step pipeline (pre-market 6:35 AM)
  --morning-scan      Run standalone arbitrage scanner
  --all              Run daily pipeline

Weekly refresh is handled by ei_collector.py (called from main_runners.py on Fridays).

Examples:
  python ei_main.py --daily-pipeline         # Full pipeline
  python ei_main.py --morning-scan           # Arbitrage scan only
  python ei_main.py --all                    # Same as --daily-pipeline
  python ei_main.py --daily-pipeline --debug # Debug mode
        """
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--daily-pipeline', action='store_true',
                           help='Run daily pipeline (snapshots, calc, moves, watchlist, news, arbitrage)')
    mode_group.add_argument('--morning-scan', action='store_true',
                           help='Run morning arbitrage scanner')
    mode_group.add_argument('--all', action='store_true',
                           help='Run daily pipeline')

    # Optional arguments
    parser.add_argument('--no-interaction', action='store_true',
                       help='Skip all user prompts (for automation)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Set logging level (default: INFO)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode (equivalent to --log-level DEBUG)')

    return parser.parse_args()

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point for Earnings Play orchestrator"""
    # Reconfigure stdout for UTF-8 encoding (Windows compatibility)
    sys.stdout.reconfigure(encoding='utf-8')

    args = parse_arguments()

    # Determine log level
    log_level = 'DEBUG' if args.debug else args.log_level

    # Determine mode for logging
    if args.daily_pipeline:
        mode = 'daily_pipeline'
    elif args.morning_scan:
        mode = 'morning_scan'
    elif args.all:
        mode = 'all'
    else:
        mode = 'unknown'

    # Set up logging
    log_file_path = setup_logging(log_level, mode)

    logging.info("Earnings Intelligence - Mode: {} | Log: {}".format(
        mode.replace('_', ' ').title(), os.path.basename(log_file_path)))

    try:
        # Execute appropriate mode
        if args.daily_pipeline:
            result = run_daily_pipeline()
            success = result.get('success', False) if isinstance(result, dict) else result

        elif args.morning_scan:
            result = run_morning_scan()
            success = result.get('success', False) if isinstance(result, dict) else result

        elif args.all:
            success = run_all_mode()

        # Final summary
        if success:
            logging.info("Pipeline completed successfully!")
        else:
            logging.error("Pipeline failed - see log file for details")

        # Wait for user unless no-interaction mode
        if not args.no_interaction:
            input("\nPress ENTER to exit...")

        # Return success code for automation
        return 0 if success else 1

    except KeyboardInterrupt:
        logging.warning("Pipeline interrupted by user (Ctrl+C)")
        return 2
    except Exception as e:
        logging.error("Fatal error: {}".format(e))
        traceback.print_exc()
        return 3

if __name__ == "__main__":
    sys.exit(main())
