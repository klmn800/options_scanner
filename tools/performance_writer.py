#!/usr/bin/env python3
"""
Performance Writer (performance_writer.py)
==========================================
End-of-day writer for data/performance.db.

Called once per trading day during Phase 6: System Maintenance.
Reads accumulated data from in-memory results dicts, daily_state.json,
and FMSessionStats, then writes all 13 tables in a single transaction.

Schema reference: docs/performance_tracking_enhancement/performance_db_schema.md
PRD: tasks/0007-prd-performance-tracking-database.md

Created: 2026-02-23
"""

import json
import logging
import os
import re
import sqlite3

logger = logging.getLogger(__name__)

# Default path for performance database
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'performance.db')


def ensure_schema(db_path=None):
    """Create performance.db and all 17 tables if they don't exist.

    Args:
        db_path: Path to performance database. Defaults to data/performance.db.

    Returns:
        str: The resolved db_path (useful when caller passes None).
    """
    if db_path is None:
        db_path = DB_PATH

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10)
    try:
        cursor = conn.cursor()

        # Table 1: daily_context
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_context (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,

                market_regime       TEXT,
                market_direction    TEXT,
                spy_change_pct      REAL,
                vix_close           REAL,

                universe_size       INTEGER,
                symbols_with_data   INTEGER,

                news_api_calls_used INTEGER,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 2: op_pipeline_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS op_pipeline_performance (
                trade_date          TEXT NOT NULL,
                run_type            TEXT NOT NULL,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                collection_seconds  REAL,
                symbols_collected   INTEGER,
                symbols_failed      INTEGER,
                total_contracts     INTEGER,
                api_calls           INTEGER,

                rollup_seconds      REAL,
                symbols_processed   INTEGER,
                summaries_created   INTEGER,

                timing_seconds      REAL,
                contracts_updated   INTEGER,
                contracts_skipped   INTEGER,

                health_status       TEXT,
                collection_rate     REAL,

                no_contract_count   INTEGER,
                total_options_seen  INTEGER,
                total_options_filtered INTEGER,

                error_count         INTEGER DEFAULT 0,
                details             TEXT,

                recorded_at         TEXT NOT NULL,
                PRIMARY KEY (trade_date, run_type)
            )
        """)

        # Migration: add data quality columns to existing op_pipeline_performance
        for col, col_type in [
            ('no_contract_count', 'INTEGER'),
            ('total_options_seen', 'INTEGER'),
            ('total_options_filtered', 'INTEGER'),
        ]:
            try:
                cursor.execute("ALTER TABLE op_pipeline_performance ADD COLUMN {} {}".format(col, col_type))
            except Exception:
                pass  # Column already exists

        # Table 3: ei_pipeline_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ei_pipeline_performance (
                trade_date          TEXT NOT NULL,
                run_type            TEXT NOT NULL,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,
                error_count         INTEGER DEFAULT 0,

                snapshots_created   INTEGER,
                moves_calculated    INTEGER,
                alerts_triggered    INTEGER,
                snapshot_seconds    REAL,
                calculation_seconds REAL,
                expected_move_seconds REAL,

                earnings_today      INTEGER,
                opportunities_found INTEGER,
                high_quality        INTEGER,
                medium_quality      INTEGER,
                low_quality         INTEGER,
                persisted           INTEGER,

                earnings_found      INTEGER,
                events_archived     INTEGER,
                records_cleaned     INTEGER,
                upcoming_count      INTEGER,
                fetch_seconds       REAL,
                archive_seconds     REAL,
                cleanup_seconds     REAL,

                watchlist_count     INTEGER,
                watchlist_new       INTEGER,
                news_enriched       INTEGER,
                watchlist_seconds   REAL,
                news_seconds        REAL,

                details             TEXT,
                recorded_at         TEXT NOT NULL,
                PRIMARY KEY (trade_date, run_type)
            )
        """)

        # Migrate existing ei_pipeline_performance tables (PRD 0008)
        for col_def in [
            "watchlist_count INTEGER",
            "watchlist_new INTEGER",
            "news_enriched INTEGER",
            "watchlist_seconds REAL",
            "news_seconds REAL",
        ]:
            try:
                cursor.execute(
                    "ALTER TABLE ei_pipeline_performance ADD COLUMN {}".format(col_def))
            except Exception:
                pass  # "duplicate column name" — already exists

        # Table 4: fm_pre_market_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fm_pre_market_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                alerts_resolved     INTEGER,
                alerts_building     INTEGER,
                alerts_closing      INTEGER,
                alerts_neutral      INTEGER,
                alerts_not_found    INTEGER,

                sentiment_updated   INTEGER,
                sentiment_building  INTEGER,
                sentiment_closing   INTEGER,
                sentiment_neutral   INTEGER,

                sync_success        INTEGER,
                alerts_synced       INTEGER,
                watchlist_synced    INTEGER,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 5: fm_cycle_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fm_cycle_performance (
                trade_date          TEXT NOT NULL,
                scan_timestamp      TEXT NOT NULL,
                cycle_number        INTEGER,
                day_of_week         INTEGER NOT NULL,
                success             INTEGER NOT NULL,

                cycle_seconds       REAL,
                collection_seconds  REAL,
                storage_seconds     REAL,
                analysis_seconds    REAL,
                analysis_query_seconds   REAL,
                analysis_scoring_seconds REAL,
                analysis_db_write_seconds REAL,
                alert_seconds       REAL,

                sync_seconds        REAL,
                sync_rows           INTEGER,

                contracts_collected INTEGER,
                alerts_generated    INTEGER,
                symbols_attempted   INTEGER,
                symbols_with_data   INTEGER,

                recorded_at         TEXT NOT NULL,
                PRIMARY KEY (trade_date, scan_timestamp)
            )
        """)

        # Table 6: fm_post_market_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fm_post_market_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,
                tasks_successful    INTEGER,
                error_count         INTEGER DEFAULT 0,

                backfill_seconds    REAL,
                backfill_symbols_updated INTEGER,
                backfill_symbols_total   INTEGER,

                regime_seconds      REAL,

                rollup_seconds      REAL,
                rollup_symbols_processed INTEGER,
                rollup_summaries_created INTEGER,
                rollup_errors       INTEGER,

                evaluation_seconds  REAL,

                cleanup_seconds     REAL,
                entries_archived    INTEGER,
                entries_deleted     INTEGER,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 7: sync_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_performance (
                trade_date          TEXT NOT NULL,
                sync_type           TEXT NOT NULL,
                sync_timestamp      TEXT NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                pages               INTEGER,
                size_mb             REAL,
                size_display        TEXT,
                tables              INTEGER,

                rows_synced         INTEGER,

                recorded_at         TEXT NOT NULL,
                PRIMARY KEY (trade_date, sync_type, sync_timestamp)
            )
        """)

        # Table 8: metadata_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                symbols_processed   INTEGER,
                quotes_fetched      INTEGER,
                fundamentals_fetched INTEGER,
                betas_calculated    INTEGER,
                db_writes_successful INTEGER,
                db_writes_failed    INTEGER,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 9: morning_views_performance (Step 1.6 removed 2026-08-31;
        # table kept for historical rows, no writer remains)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS morning_views_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                email_sent          INTEGER,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 10: backup_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backup_performance (
                trade_date          TEXT NOT NULL,
                backup_type         TEXT NOT NULL,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                backup_size_mb      REAL,
                table_count         INTEGER,
                size_verified       INTEGER,

                recorded_at         TEXT NOT NULL,
                PRIMARY KEY (trade_date, backup_type)
            )
        """)

        # Table 11: batch_mode_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS batch_mode_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                total_errors        INTEGER,
                unique_error_types  INTEGER,
                sessions_spawned    INTEGER,
                skipped             INTEGER,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 12: airline_play_performance (strategy retired 2026-08-31;
        # table kept for historical rows, no writer remains)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS airline_play_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                symbols_processed   INTEGER,
                symbols_failed      INTEGER,

                contracts_tracked   INTEGER,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 13: sector_archive_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sector_archive_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,

                tier1_rows_archived INTEGER,
                tier1_rows_deleted  INTEGER,
                tier2_rows_archived INTEGER,
                tier2_rows_deleted  INTEGER,
                tier3_rows_archived INTEGER,
                tier3_rows_deleted  INTEGER,
                total_rows_archived INTEGER,
                total_rows_deleted  INTEGER,
                error_count         INTEGER DEFAULT 0,

                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 14: news_api_usage
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_api_usage (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                calls_used          INTEGER NOT NULL,
                calls_available     INTEGER NOT NULL,
                calls_ei            INTEGER,
                calls_fm            INTEGER,
                calls_other         INTEGER,
                symbols_enriched    INTEGER,
                zero_article_calls  INTEGER,
                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 15: earnings_date_sources
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earnings_date_sources (
                trade_date      TEXT NOT NULL,
                symbol          TEXT NOT NULL,
                stored_date     TEXT,
                yfinance_date   TEXT,
                finnhub_date    TEXT,
                finnhub_timing  TEXT,
                date_source     TEXT NOT NULL,
                conflict        INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (trade_date, symbol)
            )
        """)

        # Table 16: fm_baseline_performance
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fm_baseline_performance (
                trade_date          TEXT NOT NULL PRIMARY KEY,
                day_of_week         INTEGER NOT NULL,
                duration_seconds    REAL,
                success             INTEGER NOT NULL,
                symbols_processed   INTEGER,
                baselines_created   INTEGER,
                baselines_updated   INTEGER,
                error_count         INTEGER DEFAULT 0,
                recorded_at         TEXT NOT NULL
            )
        """)

        # Table 17: earnings_date_disputes
        # Written intraday by ei_collector._write_confirmed_disputes() and
        # ei_lite_refresh.py; read by the earnings_researcher agent launcher.
        # Lives here (not just in EXECUTION_PLAN's one-time DDL) so it survives
        # a performance.db rebuild — see the June 2026 reformat that dropped it.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS earnings_date_disputes (
                trade_date      TEXT NOT NULL,
                symbol          TEXT NOT NULL,
                db_date         TEXT,
                db_time         TEXT,
                yfinance_date   TEXT,
                finnhub_date    TEXT,
                dispute_reason  TEXT,        -- 'date_disagreement', 'unknown_time', 'both', 'confirmed_row_diverged'
                resolution      TEXT,        -- 'confirmed_ben', 'confirmed_agent', 'unresolved', 'skipped'
                resolved_date   TEXT,
                resolved_time   TEXT,
                resolved_at     TEXT,
                research_url    TEXT,
                notes           TEXT,
                PRIMARY KEY (trade_date, symbol)
            )
        """)

        conn.commit()
        logger.info("Performance database schema verified: %s", db_path)
    finally:
        conn.close()

    return db_path


def write_daily_performance(trade_date, results, step_durations, fm_session_data=None,
                            sync_entries=None, news_api_data=None, db_path=None):
    """Write all performance data for one trading day to performance.db.

    Called once at end-of-day during Phase 6: System Maintenance.
    Writes all 15 tables in a single transaction. On failure, logs a
    warning and returns — never raises, never blocks the orchestrator.

    Args:
        trade_date: 'YYYY-MM-DD' string
        results: Dict of step_name → result dict (or bool/'skipped' for legacy).
                 Keys are orchestrator step names like '1.1 Morning Option Pipeline'.
        step_durations: Dict of step_name → wall-clock seconds from main.py.
        fm_session_data: Dict from daily_state.json 'fm_session' key, or None.
                         Contains per-cycle timing lists, scan_timestamps, etc.
        sync_entries: List of sync performance entry dicts from daily_state.json
                      'sync_performance' key, or None.
        news_api_data: Dict from daily_state.json 'news_api_usage' key, or None.
                       Contains per-source call counts and enrichment stats.
        db_path: Path to performance database. Defaults to data/performance.db.

    Returns:
        dict: {'success': bool, 'rows_written': int} or {'success': False} on error.
    """
    if db_path is None:
        db_path = DB_PATH

    import sys
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from timezone_utils import now_eastern
    recorded_at = now_eastern().strftime('%Y-%m-%d %H:%M:%S')

    # Parse day_of_week from trade_date
    from datetime import datetime
    try:
        dt = datetime.strptime(trade_date, '%Y-%m-%d')
        day_of_week = dt.weekday()  # 0=Mon through 4=Fri
    except (ValueError, TypeError):
        logger.warning("Performance writer: invalid trade_date '%s', skipping", trade_date)
        return {'success': False}

    if fm_session_data is None:
        fm_session_data = {}
    if sync_entries is None:
        sync_entries = []

    try:
        ensure_schema(db_path)
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        total_rows = 0

        try:
            # Table 1: daily_context
            total_rows += _write_daily_context(cursor, trade_date, day_of_week,
                                               recorded_at, fm_session_data, results)

            # Table 2: op_pipeline_performance
            total_rows += _write_op_performance(cursor, trade_date, day_of_week,
                                                recorded_at, results, step_durations)

            # Table 3: ei_pipeline_performance
            total_rows += _write_ei_performance(cursor, trade_date, day_of_week,
                                                recorded_at, results, step_durations)

            # Tables 4-6: FM pre-market, cycle, post-market
            total_rows += _write_fm_tables(cursor, trade_date, day_of_week,
                                           recorded_at, fm_session_data, results,
                                           step_durations)

            # Table 7: sync_performance
            total_rows += _write_sync_performance(cursor, trade_date, recorded_at,
                                                  sync_entries)

            # Tables 8-13: subprocess and simple steps
            total_rows += _write_subprocess_tables(cursor, trade_date, day_of_week,
                                                   recorded_at, results, step_durations)

            # Table 14: news_api_usage
            total_rows += _write_news_api_usage(cursor, trade_date, recorded_at,
                                                 news_api_data)

            conn.commit()
            logger.info("Performance data saved: %d rows across 15 tables for %s",
                        total_rows, trade_date)
            return {'success': True, 'rows_written': total_rows}

        except Exception as e:
            conn.rollback()
            logger.warning("Performance writer transaction failed: %s", e)
            return {'success': False, 'error': str(e)}
        finally:
            conn.close()

    except Exception as e:
        logger.warning("Performance writer could not open database: %s", e)
        return {'success': False, 'error': str(e)}


# ── Internal helpers (called by write_daily_performance) ─────────────────


def _r(val):
    """Round a numeric value to 2 decimal places. Returns None if val is None."""
    if val is None:
        return None
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def _result_success(result):
    """Extract success bool from a result that may be dict, bool, or 'skipped'.

    Returns:
        int: 1 for success, 0 for failure. 'skipped' returns 0.
    """
    if isinstance(result, dict):
        return 1 if result.get('success', False) else 0
    if result == 'skipped':
        return 0
    return 1 if result else 0


def _write_daily_context(cursor, trade_date, day_of_week, recorded_at,
                         fm_session_data, results):
    """Write daily_context table. Returns row count (0 or 1)."""
    # Market conditions from datalake_query.db
    market_regime = None
    market_direction = None
    spy_change_pct = None
    vix_close = None

    try:
        query_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'data', 'datalake_query.db')
        if os.path.exists(query_db):
            qconn = sqlite3.connect(query_db, timeout=5)
            qconn.row_factory = sqlite3.Row
            try:
                row = qconn.execute(
                    "SELECT regime_classification, market_direction, spy_change_percent, vix_close "
                    "FROM market_daily_summary WHERE trade_date = ? LIMIT 1",
                    (trade_date,)
                ).fetchone()
                if row:
                    market_regime = row['regime_classification']
                    market_direction = row['market_direction']
                    spy_change_pct = row['spy_change_percent']
                    vix_close = row['vix_close']
            finally:
                qconn.close()
    except Exception as e:
        logger.debug("Could not read market_daily_summary: %s", e)

    # Universe size
    universe_size = None
    try:
        from core.symbols_klmn800 import get_specialty_list
        universe_size = len(get_specialty_list('klmn_800'))
    except Exception:
        pass

    # Symbols with data (from FM session — max across all cycles)
    symbols_with_data = None
    if fm_session_data:
        swd_list = fm_session_data.get('symbols_with_data', [])
        if swd_list:
            symbols_with_data = max(swd_list)

    # News API budget — read counter file directly (avoids fragile client instantiation)
    news_api_calls_used = None
    try:
        counter_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     'cache', 'alphavantage_daily_usage.json')
        if os.path.exists(counter_file):
            import json as _json
            with open(counter_file, 'r') as f:
                counter = _json.load(f)
            # Only use count if it's from today (daily_reset_time starts with date)
            reset_time = counter.get('daily_reset_time', '')
            if reset_time.startswith(trade_date):
                news_api_calls_used = counter.get('daily_request_count', 0)
    except Exception:
        pass

    cursor.execute(
        "INSERT OR REPLACE INTO daily_context "
        "(trade_date, day_of_week, market_regime, market_direction, spy_change_pct, "
        "vix_close, universe_size, symbols_with_data, news_api_calls_used, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (trade_date, day_of_week, market_regime, market_direction, _r(spy_change_pct),
         _r(vix_close), universe_size, symbols_with_data, news_api_calls_used, recorded_at)
    )
    return 1


def _write_op_performance(cursor, trade_date, day_of_week, recorded_at,
                          results, step_durations):
    """Write op_pipeline_performance table. Returns row count (0-2)."""
    rows = 0

    op_mapping = {
        '1.1 Morning Option Pipeline': 'morning',
        '3.2 Evening Option Pipeline': 'evening',
    }

    for step_name, run_type in op_mapping.items():
        result = results.get(step_name)
        if result is None or result == 'skipped':
            continue
        if not isinstance(result, dict):
            # Legacy bool — write minimal row
            cursor.execute(
                "INSERT OR REPLACE INTO op_pipeline_performance "
                "(trade_date, run_type, day_of_week, duration_seconds, success, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (trade_date, run_type, day_of_week,
                 _r(step_durations.get(step_name)), _result_success(result), recorded_at)
            )
            rows += 1
            continue

        # Rich dict from OP pipeline
        collection = result.get('collection', {})
        rollup = result.get('rollup', {})
        timing = result.get('timing', {})
        health = result.get('health', {})
        pipeline_health = health.get('pipeline_health', {})
        errors = result.get('errors', [])

        details = None
        failed_symbols = collection.get('failed_symbols', [])
        if failed_symbols or errors:
            details = json.dumps({'failed_symbols': failed_symbols, 'errors': errors})

        cursor.execute(
            "INSERT OR REPLACE INTO op_pipeline_performance "
            "(trade_date, run_type, day_of_week, duration_seconds, success, "
            "collection_seconds, symbols_collected, symbols_failed, total_contracts, api_calls, "
            "rollup_seconds, symbols_processed, summaries_created, "
            "timing_seconds, contracts_updated, contracts_skipped, "
            "health_status, collection_rate, "
            "no_contract_count, total_options_seen, total_options_filtered, "
            "error_count, details, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, run_type, day_of_week,
             _r(result.get('total_execution_time', step_durations.get(step_name))),
             _result_success(result),
             _r(collection.get('execution_time')),
             collection.get('symbols_collected'),
             collection.get('symbols_failed', 0),
             collection.get('total_contracts'),
             collection.get('api_calls'),
             _r(rollup.get('execution_time')),
             rollup.get('symbols_processed'),
             rollup.get('summaries_created'),
             _r(timing.get('execution_time')),
             timing.get('contracts_updated'),
             timing.get('contracts_skipped'),
             pipeline_health.get('overall_status'),
             _r(pipeline_health.get('collection_phase', {}).get('collection_rate')),
             collection.get('no_contract_count', 0),
             collection.get('total_options_seen'),
             collection.get('total_options_filtered'),
             len(errors),
             details,
             recorded_at)
        )
        rows += 1

    return rows


def _write_ei_performance(cursor, trade_date, day_of_week, recorded_at,
                          results, step_durations):
    """Write ei_pipeline_performance table. Returns row count (0-3)."""
    rows = 0

    ei_mapping = {
        '1.2 Earnings Intelligence': 'daily_pipeline',
        '5.3 Earnings Refresh': 'weekly_refresh',
    }

    for step_name, run_type in ei_mapping.items():
        result = results.get(step_name)
        if result is None or result == 'skipped':
            continue
        if not isinstance(result, dict):
            cursor.execute(
                "INSERT OR REPLACE INTO ei_pipeline_performance "
                "(trade_date, run_type, day_of_week, duration_seconds, success, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (trade_date, run_type, day_of_week,
                 _r(step_durations.get(step_name)), _result_success(result), recorded_at)
            )
            rows += 1
            continue

        sub_tasks = result.get('sub_tasks', {})
        duration = _r(result.get('duration_seconds', step_durations.get(step_name)))

        # Build column values — NULL for non-applicable run types
        # daily_pipeline: snapshots, moves, alerts, watchlist, news, arbitrage sub-tasks
        # weekly_refresh: earnings_found, events_archived, records_cleaned, upcoming_count, sub_tasks(fetch/archive/cleanup)
        vals = {
            'snapshots_created': result.get('snapshots_created'),
            'moves_calculated': result.get('moves_calculated'),
            'alerts_triggered': result.get('alerts_triggered'),
            'snapshot_seconds': _r(sub_tasks.get('snapshots', {}).get('duration_seconds')),
            'calculation_seconds': _r(sub_tasks.get('calculations', {}).get('duration_seconds')),
            'expected_move_seconds': _r(sub_tasks.get('expected_moves', {}).get('duration_seconds')),
            'earnings_today': result.get('arb_opportunities') if run_type == 'daily_pipeline'
                              else result.get('earnings_today'),
            'opportunities_found': sub_tasks.get('arbitrage', {}).get('opportunities_found')
                                   if run_type == 'daily_pipeline' else result.get('opportunities_found'),
            'high_quality': sub_tasks.get('arbitrage', {}).get('high_quality')
                            if run_type == 'daily_pipeline' else result.get('high_quality'),
            'medium_quality': sub_tasks.get('arbitrage', {}).get('medium_quality')
                              if run_type == 'daily_pipeline' else result.get('medium_quality'),
            'low_quality': sub_tasks.get('arbitrage', {}).get('low_quality')
                           if run_type == 'daily_pipeline' else result.get('low_quality'),
            'persisted': sub_tasks.get('arbitrage', {}).get('persisted')
                         if run_type == 'daily_pipeline' else result.get('persisted'),
            'earnings_found': result.get('earnings_found'),
            'events_archived': result.get('events_archived'),
            'records_cleaned': result.get('records_cleaned'),
            'upcoming_count': result.get('upcoming_count'),
            'fetch_seconds': _r(sub_tasks.get('fetch', {}).get('duration_seconds')),
            'archive_seconds': _r(sub_tasks.get('archive', {}).get('duration_seconds')),
            'cleanup_seconds': _r(sub_tasks.get('cleanup', {}).get('duration_seconds')),
            'watchlist_count': result.get('watchlist_count'),
            'watchlist_new': result.get('watchlist_new'),
            'news_enriched': result.get('news_enriched'),
            'watchlist_seconds': _r(sub_tasks.get('watchlist', {}).get('duration_seconds')),
            'news_seconds': _r(sub_tasks.get('news_enrichment', {}).get('duration_seconds')),
        }

        cursor.execute(
            "INSERT OR REPLACE INTO ei_pipeline_performance "
            "(trade_date, run_type, day_of_week, duration_seconds, success, error_count, "
            "snapshots_created, moves_calculated, alerts_triggered, "
            "snapshot_seconds, calculation_seconds, expected_move_seconds, "
            "earnings_today, opportunities_found, high_quality, medium_quality, low_quality, persisted, "
            "earnings_found, events_archived, records_cleaned, upcoming_count, "
            "fetch_seconds, archive_seconds, cleanup_seconds, "
            "watchlist_count, watchlist_new, news_enriched, watchlist_seconds, news_seconds, "
            "details, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, run_type, day_of_week, duration,
             _result_success(result),
             result.get('errors', result.get('error_count', 0)),
             vals['snapshots_created'], vals['moves_calculated'], vals['alerts_triggered'],
             vals['snapshot_seconds'], vals['calculation_seconds'], vals['expected_move_seconds'],
             vals['earnings_today'], vals['opportunities_found'],
             vals['high_quality'], vals['medium_quality'], vals['low_quality'], vals['persisted'],
             vals['earnings_found'], vals['events_archived'], vals['records_cleaned'], vals['upcoming_count'],
             vals['fetch_seconds'], vals['archive_seconds'], vals['cleanup_seconds'],
             vals['watchlist_count'], vals['watchlist_new'], vals['news_enriched'],
             vals['watchlist_seconds'], vals['news_seconds'],
             None,  # details — populated if needed
             recorded_at)
        )
        rows += 1

    return rows


def _write_fm_tables(cursor, trade_date, day_of_week, recorded_at,
                     fm_session_data, results, step_durations):
    """Write FM tables (pre-market, cycles, post-market). Returns total row count."""
    rows = 0

    # FM pre-market (from results dict under '2.0 Flow Monitor')
    fm_result = results.get('2. Flow Monitor')
    if isinstance(fm_result, dict):
        pre_market = fm_result.get('pre_market', {})
        if pre_market and isinstance(pre_market, dict):
            sub = pre_market.get('sub_tasks', {})
            alert_res = sub.get('alert_resolution', {})
            sentiment = sub.get('sentiment_update', {})
            sync = sub.get('sync', {})

            cursor.execute(
                "INSERT OR REPLACE INTO fm_pre_market_performance "
                "(trade_date, day_of_week, duration_seconds, success, "
                "alerts_resolved, alerts_building, alerts_closing, alerts_neutral, alerts_not_found, "
                "sentiment_updated, sentiment_building, sentiment_closing, sentiment_neutral, "
                "sync_success, alerts_synced, watchlist_synced, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (trade_date, day_of_week,
                 _r(pre_market.get('duration_seconds')),
                 _result_success(pre_market),
                 alert_res.get('alerts_resolved'), alert_res.get('building'),
                 alert_res.get('closing'), alert_res.get('neutral'),
                 alert_res.get('not_found'),
                 sentiment.get('symbols_updated'), sentiment.get('building'),
                 sentiment.get('closing'), sentiment.get('neutral'),
                 1 if sync.get('success') else 0 if sync else None,
                 sync.get('alerts_synced'), sync.get('watchlist_synced'),
                 recorded_at)
            )
            rows += 1

    # FM per-cycle rows (from fm_session_data lists)
    if fm_session_data and fm_session_data.get('cycle_times'):
        num_cycles = len(fm_session_data['cycle_times'])
        scan_timestamps = fm_session_data.get('scan_timestamps', [])
        contracts_collected = fm_session_data.get('contracts_collected', [])
        alerts_generated = fm_session_data.get('alerts_generated', [])
        symbols_attempted = fm_session_data.get('symbols_attempted', [])
        symbols_with_data = fm_session_data.get('symbols_with_data', [])

        for i in range(num_cycles):
            # scan_timestamp is the PK — skip if missing
            ts = scan_timestamps[i] if i < len(scan_timestamps) else ''
            if not ts:
                continue

            def _get(lst, idx, default=None):
                return lst[idx] if idx < len(lst) else default

            cursor.execute(
                "INSERT OR REPLACE INTO fm_cycle_performance "
                "(trade_date, scan_timestamp, cycle_number, day_of_week, success, "
                "cycle_seconds, collection_seconds, storage_seconds, "
                "analysis_seconds, analysis_query_seconds, analysis_scoring_seconds, "
                "analysis_db_write_seconds, alert_seconds, "
                "sync_seconds, sync_rows, "
                "contracts_collected, alerts_generated, symbols_attempted, symbols_with_data, "
                "recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (trade_date, ts, i + 1, day_of_week,
                 1,  # if we have timing data, the cycle ran
                 _r(_get(fm_session_data['cycle_times'], i)),
                 _r(_get(fm_session_data.get('collection_times', []), i)),
                 _r(_get(fm_session_data.get('storage_times', []), i)),
                 _r(_get(fm_session_data.get('analysis_times', []), i)),
                 _r(_get(fm_session_data.get('analysis_query_times', []), i)),
                 _r(_get(fm_session_data.get('analysis_scoring_times', []), i)),
                 _r(_get(fm_session_data.get('analysis_db_write_times', []), i)),
                 _r(_get(fm_session_data.get('alert_times', []), i)),
                 _r(_get(fm_session_data.get('sync_times', []), i)),
                 _get(fm_session_data.get('sync_rows', []), i),
                 _get(contracts_collected, i, 0),
                 _get(alerts_generated, i, 0),
                 _get(symbols_attempted, i, 0),
                 _get(symbols_with_data, i, 0),
                 recorded_at)
            )
            rows += 1

    # FM post-market (from results dict)
    if isinstance(fm_result, dict):
        post_market = fm_result.get('post_market', {})
        if post_market and isinstance(post_market, dict):
            sub = post_market.get('sub_tasks', {})
            backfill = sub.get('backfill', {})
            regime = sub.get('market_regime', {})
            rollup = sub.get('symbol_rollup', {})
            evaluation = sub.get('evaluation', {})
            cleanup = sub.get('watchlist_cleanup', {})

            cursor.execute(
                "INSERT OR REPLACE INTO fm_post_market_performance "
                "(trade_date, day_of_week, duration_seconds, success, "
                "tasks_successful, error_count, "
                "backfill_seconds, backfill_symbols_updated, backfill_symbols_total, "
                "regime_seconds, "
                "rollup_seconds, rollup_symbols_processed, rollup_summaries_created, rollup_errors, "
                "evaluation_seconds, "
                "cleanup_seconds, entries_archived, entries_deleted, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (trade_date, day_of_week,
                 _r(post_market.get('duration_seconds')),
                 _result_success(post_market),
                 post_market.get('tasks_successful'),
                 post_market.get('errors', post_market.get('error_count', 0)),
                 _r(backfill.get('duration_seconds')),
                 backfill.get('symbols_updated'),
                 backfill.get('symbols_total'),
                 _r(regime.get('duration_seconds')),
                 _r(rollup.get('duration_seconds')),
                 rollup.get('symbols_processed'),
                 rollup.get('summaries_created'),
                 rollup.get('errors', 0),
                 _r(evaluation.get('duration_seconds')),
                 _r(cleanup.get('duration_seconds')),
                 cleanup.get('entries_archived', 0),
                 cleanup.get('entries_deleted', 0),
                 recorded_at)
            )
            rows += 1

    return rows


def _write_sync_performance(cursor, trade_date, recorded_at, sync_entries):
    """Write sync_performance table from daily_state.json entries. Returns row count."""
    rows = 0

    for entry in sync_entries:
        ts = entry.get('timestamp', recorded_at)
        sync_type = entry.get('sync_type', 'full')
        success = 1 if entry.get('success', False) else 0

        # Parse size_mb from size_display (e.g. '7.16 GB' → 7331.84)
        size_mb = None
        size_display = entry.get('size_display')
        if size_display:
            size_mb = _parse_size_to_mb(size_display)

        cursor.execute(
            "INSERT OR REPLACE INTO sync_performance "
            "(trade_date, sync_type, sync_timestamp, duration_seconds, success, "
            "pages, size_mb, size_display, tables, rows_synced, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, sync_type, ts,
             _r(entry.get('duration_seconds')),
             success,
             entry.get('pages'),
             _r(size_mb),
             size_display,
             entry.get('tables'),
             entry.get('rows_synced'),
             recorded_at)
        )
        rows += 1

    return rows


def _parse_size_to_mb(size_str):
    """Parse a human-readable size string to megabytes.

    Examples: '7.16 GB' → 7331.84, '512.3 MB' → 512.3, '1.2 TB' → 1228800.0
    Returns None if unparseable.
    """
    if not size_str:
        return None
    m = re.match(r'([\d.]+)\s*(TB|GB|MB|KB)', size_str, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    if unit == 'TB':
        return round(val * 1024 * 1024, 2)
    elif unit == 'GB':
        return round(val * 1024, 2)
    elif unit == 'MB':
        return round(val, 2)
    elif unit == 'KB':
        return round(val / 1024, 2)
    return None


def _write_news_api_usage(cursor, trade_date, recorded_at, news_api_data):
    """Write news_api_usage table from daily_state.json counters. Returns row count (0 or 1).

    Falls back to alphavantage_daily_usage.json for calls_used if the
    daily_state counters are missing (backward compat).
    """
    if news_api_data is None:
        news_api_data = {}

    calls_ei = news_api_data.get('calls_ei', 0)
    calls_fm = news_api_data.get('calls_fm', 0)
    calls_other = news_api_data.get('calls_other', 0)
    symbols_enriched = news_api_data.get('symbols_enriched', 0)
    zero_article_calls = news_api_data.get('zero_article_calls', 0)

    # Total calls from per-source counters
    calls_used = calls_ei + calls_fm + calls_other

    # If no per-source data, fall back to the AV counter file for total
    if calls_used == 0:
        try:
            counter_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'cache', 'alphavantage_daily_usage.json')
            if os.path.exists(counter_file):
                import json as _json
                with open(counter_file, 'r') as f:
                    counter = _json.load(f)
                reset_time = counter.get('daily_reset_time', '')
                if reset_time.startswith(trade_date):
                    calls_used = counter.get('daily_request_count', 0)
        except Exception:
            pass

    # Skip writing if no data at all
    if calls_used == 0 and symbols_enriched == 0:
        return 0

    calls_available = 25 - calls_used

    cursor.execute(
        "INSERT OR REPLACE INTO news_api_usage "
        "(trade_date, calls_used, calls_available, calls_ei, calls_fm, calls_other, "
        "symbols_enriched, zero_article_calls, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (trade_date, calls_used, calls_available,
         calls_ei or None, calls_fm or None, calls_other or None,
         symbols_enriched, zero_article_calls, recorded_at)
    )
    return 1


def _write_subprocess_tables(cursor, trade_date, day_of_week, recorded_at,
                             results, step_durations):
    """Write tables for subprocess-based and simple steps. Returns total row count."""
    rows = 0

    # Table 8: metadata_performance
    meta_result = results.get('1.3 Metadata Collection')
    if meta_result is not None and meta_result != 'skipped':
        parsed = {}
        if isinstance(meta_result, dict) and meta_result.get('stdout'):
            parsed = _parse_metadata_stdout(meta_result['stdout'])

        cursor.execute(
            "INSERT OR REPLACE INTO metadata_performance "
            "(trade_date, day_of_week, duration_seconds, success, "
            "symbols_processed, quotes_fetched, fundamentals_fetched, "
            "betas_calculated, db_writes_successful, db_writes_failed, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, day_of_week,
             _r(step_durations.get('1.3 Metadata Collection')),
             _result_success(meta_result),
             parsed.get('symbols_processed'),
             parsed.get('quotes_fetched'),
             parsed.get('fundamentals_fetched'),
             parsed.get('betas_calculated'),
             parsed.get('db_writes_successful'),
             parsed.get('db_writes_failed'),
             recorded_at)
        )
        rows += 1

    # Table 10: backup_performance (daily and/or weekly)
    backup_mapping = {
        '4.1 Daily Backup': 'daily',
        '5.1 Weekly Backup': 'weekly',
    }
    for step_name, backup_type in backup_mapping.items():
        bk_result = results.get(step_name)
        if bk_result is None or bk_result == 'skipped':
            continue
        parsed = {}
        if isinstance(bk_result, dict) and bk_result.get('stdout'):
            parsed = _parse_backup_stdout(bk_result['stdout'])

        cursor.execute(
            "INSERT OR REPLACE INTO backup_performance "
            "(trade_date, backup_type, day_of_week, duration_seconds, success, "
            "backup_size_mb, table_count, size_verified, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, backup_type, day_of_week,
             _r(step_durations.get(step_name)),
             _result_success(bk_result),
             parsed.get('backup_size_mb'),
             parsed.get('table_count'),
             parsed.get('size_verified'),
             recorded_at)
        )
        rows += 1

    # Table 11: batch_mode_performance
    batch_result = results.get('4.2 Autofix Review')
    if batch_result is not None and batch_result != 'skipped':
        cursor.execute(
            "INSERT OR REPLACE INTO batch_mode_performance "
            "(trade_date, day_of_week, duration_seconds, success, "
            "total_errors, unique_error_types, sessions_spawned, skipped, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, day_of_week,
             _r(step_durations.get('4.2 Autofix Review')),
             _result_success(batch_result),
             batch_result.get('errors_found', 0) if isinstance(batch_result, dict) else None,
             batch_result.get('unique_error_types') if isinstance(batch_result, dict) else None,
             batch_result.get('sessions_spawned', 0) if isinstance(batch_result, dict) else None,
             1 if (isinstance(batch_result, dict) and batch_result.get('skipped')) else 0,
             recorded_at)
        )
        rows += 1

    # Table 13: sector_archive_performance
    archive_result = results.get('5.4 Sector Archive')
    if archive_result is not None and archive_result != 'skipped':
        parsed = {}
        if isinstance(archive_result, dict) and archive_result.get('stdout'):
            parsed = _parse_archive_stdout(archive_result['stdout'])

        cursor.execute(
            "INSERT OR REPLACE INTO sector_archive_performance "
            "(trade_date, day_of_week, duration_seconds, success, "
            "tier1_rows_archived, tier1_rows_deleted, "
            "tier2_rows_archived, tier2_rows_deleted, "
            "tier3_rows_archived, tier3_rows_deleted, "
            "total_rows_archived, total_rows_deleted, error_count, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, day_of_week,
             _r(step_durations.get('5.4 Sector Archive')),
             _result_success(archive_result),
             parsed.get('tier1_rows_archived'), parsed.get('tier1_rows_deleted'),
             parsed.get('tier2_rows_archived'), parsed.get('tier2_rows_deleted'),
             parsed.get('tier3_rows_archived'), parsed.get('tier3_rows_deleted'),
             parsed.get('total_rows_archived'), parsed.get('total_rows_deleted'),
             parsed.get('error_count', 0),
             recorded_at)
        )
        rows += 1

    # Table 16: fm_baseline_performance
    baseline_result = results.get('5.2 FM Baseline')
    if baseline_result is not None and baseline_result != 'skipped':
        cursor.execute(
            "INSERT OR REPLACE INTO fm_baseline_performance "
            "(trade_date, day_of_week, duration_seconds, success, "
            "symbols_processed, baselines_created, baselines_updated, "
            "error_count, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, day_of_week,
             _r(step_durations.get('5.2 FM Baseline')),
             _result_success(baseline_result),
             baseline_result.get('symbols_processed') if isinstance(baseline_result, dict) else None,
             baseline_result.get('baselines_created') if isinstance(baseline_result, dict) else None,
             baseline_result.get('baselines_updated') if isinstance(baseline_result, dict) else None,
             baseline_result.get('error_count', 0) if isinstance(baseline_result, dict) else 0,
             recorded_at)
        )
        rows += 1

    return rows


# ── Subprocess stdout parsers ────────────────────────────────────────────


def _parse_metadata_stdout(stdout):
    """Parse metadata collection COLLECTION SUMMARY banner.

    Returns dict with: symbols_processed, quotes_fetched, fundamentals_fetched,
    betas_calculated, db_writes_successful, db_writes_failed.
    """
    result = {}
    if not stdout:
        return result

    patterns = {
        'symbols_processed': r'Symbols processed:\s*([\d,]+)',
        'quotes_fetched': r'Quotes fetched:\s*([\d,]+)',
        'fundamentals_fetched': r'Fundamentals fetched:\s*([\d,]+)',
        'betas_calculated': r'Betas calculated:\s*([\d,]+)',
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, stdout, re.IGNORECASE)
        if m:
            result[key] = int(m.group(1).replace(',', ''))

    # Database writes: "N successful, M failed"
    m = re.search(r'Database writes:\s*([\d,]+)\s*successful', stdout, re.IGNORECASE)
    if m:
        result['db_writes_successful'] = int(m.group(1).replace(',', ''))
    m = re.search(r'([\d,]+)\s*failed', stdout, re.IGNORECASE)
    if m:
        result['db_writes_failed'] = int(m.group(1).replace(',', ''))

    return result


def _parse_backup_stdout(stdout):
    """Parse backup subprocess stdout.

    Returns dict with: backup_size_mb, table_count, size_verified.
    """
    result = {}
    if not stdout:
        return result

    # Size: look for format_size() output like "7.16 GB" or "512 MB"
    m = re.search(r'([\d.]+)\s*(TB|GB|MB|KB)', stdout, re.IGNORECASE)
    if m:
        result['backup_size_mb'] = _parse_size_to_mb(m.group(0))

    # Table count
    m = re.search(r'(\d+)\s*tables?', stdout, re.IGNORECASE)
    if m:
        result['table_count'] = int(m.group(1))

    # Verification
    if 'verified' in stdout.lower() or 'match' in stdout.lower():
        result['size_verified'] = 1
    elif 'mismatch' in stdout.lower():
        result['size_verified'] = 0

    return result


def _parse_archive_stdout(stdout):
    """Parse sector archive ARCHIVE COMPLETE banner.

    Returns dict with per-tier row counts and totals.
    """
    result = {}
    if not stdout:
        return result

    # Per-tier patterns: "TIER 1 COMPLETE: 50,000 archived, 45,000 deleted in 5400.0s"
    # (from logger.info in db_archive_sector.py — reaches stdout via console handler)
    for tier_num in [1, 2, 3]:
        archived_key = 'tier{}_rows_archived'.format(tier_num)
        deleted_key = 'tier{}_rows_deleted'.format(tier_num)

        m = re.search(
            r'Tier\s*{}\s*.*?([\d,]+)\s*archived'.format(tier_num),
            stdout, re.IGNORECASE
        )
        if m:
            result[archived_key] = int(m.group(1).replace(',', ''))

        m = re.search(
            r'Tier\s*{}\s*.*?([\d,]+)\s*deleted'.format(tier_num),
            stdout, re.IGNORECASE
        )
        if m:
            result[deleted_key] = int(m.group(1).replace(',', ''))

    # Totals
    m = re.search(r'Total archived[:\s]*([\d,]+)', stdout, re.IGNORECASE)
    if m:
        result['total_rows_archived'] = int(m.group(1).replace(',', ''))
    m = re.search(r'Total deleted[:\s]*([\d,]+)', stdout, re.IGNORECASE)
    if m:
        result['total_rows_deleted'] = int(m.group(1).replace(',', ''))

    return result
