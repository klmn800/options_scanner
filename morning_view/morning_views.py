#!/usr/bin/env python3
"""
Morning Views - TUI view schema

Owns the SQL views and the user_watchlist table that the Morning View TUI
(mv_main.py / tui_data.py) reads: v_morning_discovery, v_symbol_oi_detail,
v_oi_timing_context, v_option_comparison, v_live_market_snapshot.

Instantiating MorningViews (re)creates the views — main_runners uses this
after query-DB syncs, which destroy views. The former CLI/report/email
features (emailed watchlist, option comparison, symbol detail) were removed
2026-08-31; see docs/HISTORICAL_NOTES.md.
"""

import sqlite3
import argparse
import json
import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Force UTF-8 encoding for Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# Import required tools for safety and consistency
sys.path.insert(0, str(Path(__file__).parent.parent))  # Add project root
from tools.decimal_formatter import clean_database_row
from tools.timezone_utils import now_eastern, eastern_date_string

class MorningViews:
    def __init__(self, config_path='morning_view/config.json'):
        # Load configuration - handle both running from root and from morning_view/
        if not os.path.exists(config_path):
            # Try alternative path if running from morning_view/ directory
            alt_path = 'config.json' if config_path == 'morning_view/config.json' else config_path
            if os.path.exists(alt_path):
                config_path = alt_path

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # Connect to database
        db_path = self.config['database']['path']
        if not os.path.isabs(db_path):
            # Make relative to project root
            project_root = Path(__file__).parent.parent
            db_path = project_root / db_path

        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row  # Access columns by name

        # Create database views if they don't exist
        self._ensure_views_exist()

        # Setup logging to centralized logs directory
        project_root = Path(__file__).parent.parent
        logs_dir = project_root / 'logs'
        logs_dir.mkdir(exist_ok=True)

        date_str = now_eastern().strftime('%Y-%m-%d')
        log_file = logs_dir / f'morning_views_{date_str}.log'

        # Configure logging
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [MORNING_VIEWS] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)

        # Console handler (minimal - keep print() for main output)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)  # Only warnings/errors to console
        console_handler.setFormatter(formatter)

        # Configure logger
        self.logger = logging.getLogger('morning_views')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []  # Clear any existing handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # Get display date (yesterday for complete data)
        self.display_date = self._get_display_date()


    def close(self):
        """
        Close database connection and clean up resources

        CRITICAL FIX (2025-12-16): Properly close database connection to prevent
        file handle leaks on Windows. Without this, the connection remains open
        until Python's garbage collector runs, which can interfere with database
        sync operations that need to rename the file.

        Research: https://github.com/python/cpython/issues/135117
        Related: WinError 32 during query database sync operations
        """
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.close()
                self.logger.debug("Database connection closed")
            except Exception as e:
                self.logger.warning(f"Error closing database connection: {e}")

    def _ensure_views_exist(self):
        """
        Create database views if they don't exist.

        DATA TIMING FOR MORNING VIEWS:
        -------------------------------
        Morning Views runs at ~7:30 AM after morning OID scan.

        OID Pipeline Schedule:
        - Morning (~6:35 AM): Updates OPEN INTEREST for today
        - Evening (~5:00 PM): Updates VOLUME and GREEKS for today

        Therefore at 7:30 AM:
        - TODAY's row: Has fresh OI (lagging indicator showing current positions)
        - YESTERDAY's row: Has complete volume, price, greeks data

        VIEW IMPLEMENTATION:
        Self-join on option_symbol_summary:
        - OI fields from TODAY (s_today.trade_date = DATE('now'))
        - Volume, price, greeks from YESTERDAY (s_yesterday.trade_date < DATE('now'))

        This gives most accurate morning picture: current positioning with complete market context.
        """
        cursor = self.conn.cursor()

        # Create user_watchlist table for persistent user-curated watchlist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_watchlist (
            symbol TEXT PRIMARY KEY,
            added_date TEXT NOT NULL,
            added_reason TEXT,
            user_notes TEXT,
            priority INTEGER DEFAULT 0,
            removed_date TEXT,
            FOREIGN KEY (symbol) REFERENCES symbol_metadata(symbol)
        )
        ''')

        # Create index for fast filtering of active watchlist
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_watchlist_active
        ON user_watchlist(removed_date)
        ''')

        # Drop and recreate views to ensure they're up to date
        views_to_drop = ['v_morning_discovery', 'v_symbol_oi_detail', 'v_oi_timing_context', 'v_option_comparison', 'v_live_market_snapshot']
        for view in views_to_drop:
            try:
                cursor.execute(f"DROP VIEW IF EXISTS {view}")
            except:
                pass
        self.conn.commit()  # Commit drops before creating new views

        # View 1.5: Morning Discovery (Trigger-based feed with CTE pattern for Phase 1)
        cursor.execute('''
        CREATE VIEW IF NOT EXISTS v_morning_discovery AS
        WITH base_data AS (
            SELECT
                s_today.symbol,
                s_yesterday.close_price,
                COALESCE(
                    (SELECT underlying_price
                     FROM flow_options_scans
                     WHERE symbol = s_today.symbol
                     ORDER BY scan_timestamp DESC
                     LIMIT 1),
                    s_yesterday.close_price
                ) as current_price,
                s_yesterday.option_volume as volume,
                s_today.put_call_ratio,
                s_today.total_open_interest,
                s_today.total_call_oi,
                s_today.total_put_oi,

                (SELECT ROUND(((s_yesterday.close_price - h5.close_price) / NULLIF(h5.close_price, 0)) * 100, 1)
                 FROM historical_prices h5
                 WHERE h5.symbol = s_yesterday.symbol
                 AND h5.trade_date < s_yesterday.trade_date
                 ORDER BY h5.trade_date DESC
                 LIMIT 1 OFFSET 4
                ) as price_change_5d_pct,

                CASE
                    WHEN s_today.put_call_ratio > 2.0 THEN 'BEARISH'
                    WHEN s_today.put_call_ratio > 1.3 THEN 'SOMEWHAT_BEARISH'
                    WHEN s_today.put_call_ratio < 0.5 THEN 'BULLISH'
                    WHEN s_today.put_call_ratio < 0.8 THEN 'SOMEWHAT_BULLISH'
                    ELSE 'NEUTRAL'
                END as direction_bias,

                CASE
                    WHEN s_today.top_call_pct_of_total > 30 OR s_today.top_put_pct_of_total > 30 THEN 'HIGH'
                    WHEN s_today.top_call_pct_of_total > 15 OR s_today.top_put_pct_of_total > 15 THEN 'MEDIUM'
                    ELSE 'LOW'
                END as conviction_level,

                e.earnings_days_ahead,
                e.straddle_expected_move_pct AS exp_move_pct,
                e.historical_avg_move_pct AS hist_move_pct,
                e.move_difference_pct AS diff_move_pct,
                e.earnings_play_signal,
                e.earnings_alert,

                COALESCE(opts.active_alert_count, 0) as active_alert_count,
                COALESCE(opts.new_alert_count, 0) as new_alert_count,
                COALESCE(opts.days_since_last_alert, 999) as days_since_last_alert,

                COALESCE(opts.alert_count_5d, 0) as recent_alert_count_5d,

                (SELECT AVG(symbol_sentiment_score)
                 FROM news_symbol_sentiment ns
                 WHERE ns.symbol = s_today.symbol
                 AND DATE(ns.article_date) >= DATE('now', '-5 days')
                ) as news_sentiment_avg,

                CASE
                    WHEN (SELECT AVG(symbol_sentiment_score)
                          FROM news_symbol_sentiment ns
                          WHERE ns.symbol = s_today.symbol
                          AND DATE(ns.article_date) >= DATE('now', '-5 days')) >= 0.15 THEN 'Bullish'
                    WHEN (SELECT AVG(symbol_sentiment_score)
                          FROM news_symbol_sentiment ns
                          WHERE ns.symbol = s_today.symbol
                          AND DATE(ns.article_date) >= DATE('now', '-5 days')) >= 0.05 THEN 'Somewhat-Bullish'
                    WHEN (SELECT AVG(symbol_sentiment_score)
                          FROM news_symbol_sentiment ns
                          WHERE ns.symbol = s_today.symbol
                          AND DATE(ns.article_date) >= DATE('now', '-5 days')) <= -0.15 THEN 'Bearish'
                    WHEN (SELECT AVG(symbol_sentiment_score)
                          FROM news_symbol_sentiment ns
                          WHERE ns.symbol = s_today.symbol
                          AND DATE(ns.article_date) >= DATE('now', '-5 days')) <= -0.05 THEN 'Somewhat-Bearish'
                    ELSE 'Neutral'
                END as news_sentiment,

                ROUND(s_yesterday.option_volume / NULLIF((SELECT AVG(s2.option_volume)
                                                FROM option_symbol_summary s2
                                                WHERE s2.symbol = s_yesterday.symbol
                                                AND s2.trade_date BETWEEN DATE(s_yesterday.trade_date, '-20 days') AND DATE(s_yesterday.trade_date, '-1 days')), 0), 2) as volume_surge_factor,

                (
                    CASE WHEN COALESCE(opts.active_alert_count, 0) > 0
                    THEN 1 ELSE 0 END
                    +
                    CASE WHEN s_yesterday.option_volume > (SELECT AVG(s2.option_volume) * 1.5
                                                 FROM option_symbol_summary s2
                                                 WHERE s2.symbol = s_yesterday.symbol
                                                 AND s2.trade_date BETWEEN DATE(s_yesterday.trade_date, '-20 days') AND DATE(s_yesterday.trade_date, '-1 days'))
                    THEN 1 ELSE 0 END
                    +
                    CASE WHEN e.earnings_days_ahead BETWEEN 1 AND 30 THEN 1 ELSE 0 END
                    +
                    CASE WHEN ABS((SELECT AVG(symbol_sentiment_score)
                                   FROM news_symbol_sentiment ns
                                   WHERE ns.symbol = s_today.symbol
                                   AND DATE(ns.article_date) >= DATE('now', '-5 days'))) >= 0.10
                    THEN 1 ELSE 0 END
                    +
                    CASE WHEN s_today.top_call_pct_of_total > 30 OR s_today.top_put_pct_of_total > 30 THEN 1 ELSE 0 END
                ) as confluence_score,

                CASE
                    WHEN COALESCE(opts.active_alert_count, 0) > 0
                    THEN 'FLOW_ALERT'
                    WHEN e.earnings_days_ahead BETWEEN 1 AND 30 THEN 'EARNINGS_CATALYST'
                    WHEN s_yesterday.option_volume > (SELECT AVG(s2.option_volume) * 1.5
                                            FROM option_symbol_summary s2
                                            WHERE s2.symbol = s_yesterday.symbol
                                            AND s2.trade_date BETWEEN DATE(s_yesterday.trade_date, '-20 days') AND DATE(s_yesterday.trade_date, '-1 days'))
                    THEN 'VOLUME_SURGE'
                    ELSE 'OI_SIGNAL'
                END as primary_signal,

                COALESCE(m.market_direction, 'NEUTRAL') as market_direction,
                COALESCE(m.regime_classification, 'normal') as market_regime,

                meta.sector,
                meta.industry,

                s_yesterday.trade_date,

                -- Calculate trigger flags in CTE
                CASE WHEN COALESCE(opts.active_alert_count, 0) > 0 THEN 1 ELSE 0 END as trigger_flow_alert,
                CASE WHEN e.earnings_alert = 1 THEN 1 ELSE 0 END as trigger_earnings_play

            FROM option_symbol_summary s_today
            JOIN option_symbol_summary s_yesterday
                ON s_today.symbol = s_yesterday.symbol
                AND s_yesterday.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary WHERE trade_date < (SELECT MAX(trade_date) FROM option_symbol_summary))
            JOIN symbol_metadata meta ON s_today.symbol = meta.symbol
            LEFT JOIN earnings_upcoming e ON s_today.symbol = e.symbol
            LEFT JOIN market_daily_summary m ON DATE(m.trade_date) = DATE(s_yesterday.trade_date)
            LEFT JOIN flow_symbol_summary opts
                ON s_today.symbol = opts.symbol
                AND opts.trade_date = (SELECT MAX(trade_date) FROM flow_symbol_summary)
            LEFT JOIN user_watchlist uw
                ON s_today.symbol = uw.symbol
                AND uw.removed_date IS NULL

            WHERE
                s_today.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
                AND s_yesterday.close_price < 60
                AND s_today.total_open_interest > 500
                AND meta.is_etf = 0
        )
        SELECT
            symbol,
            close_price,
            current_price,
            volume,
            put_call_ratio,
            total_open_interest,
            total_call_oi,
            total_put_oi,
            price_change_5d_pct,
            direction_bias,
            conviction_level,
            earnings_days_ahead,
            exp_move_pct,
            hist_move_pct,
            diff_move_pct,
            earnings_play_signal,
            earnings_alert,
            active_alert_count,
            new_alert_count,
            days_since_last_alert,
            recent_alert_count_5d,
            news_sentiment_avg,
            news_sentiment,
            volume_surge_factor,
            confluence_score,
            primary_signal,
            market_direction,
            market_regime,
            sector,
            industry,
            trade_date,
            trigger_flow_alert,
            trigger_earnings_play
        FROM base_data
        WHERE trigger_flow_alert = 1 OR trigger_earnings_play = 1
        ORDER BY
            new_alert_count DESC,
            recent_alert_count_5d DESC,
            active_alert_count DESC,
            diff_move_pct DESC,
            days_since_last_alert ASC
        ''')

        # View 2: Symbol OI Detail (Hybrid: Today's OI + Yesterday's other data)
        cursor.execute('''
        CREATE VIEW v_symbol_oi_detail AS
        SELECT
            s_today.symbol,
            s_yesterday.trade_date,
            s_yesterday.close_price,
            COALESCE(
                (SELECT underlying_price
                 FROM flow_options_scans
                 WHERE symbol = s_today.symbol
                 ORDER BY scan_timestamp DESC
                 LIMIT 1),
                s_yesterday.close_price
            ) as current_price,
            s_today.total_open_interest,
            s_today.total_call_oi,
            s_today.total_put_oi,
            s_today.put_call_ratio,
            s_today.oi_balance_text,
            s_today.top_call_strike,
            s_today.top_call_expiration,
            s_today.top_call_oi,
            s_today.top_call_pct_of_total,
            s_today.top_call_display,
            s_today.top_put_strike,
            s_today.top_put_expiration,
            s_today.top_put_oi,
            s_today.top_put_pct_of_total,
            s_today.top_put_display,
            s_today.oi_0_7_days,
            s_today.oi_8_21_days,
            s_today.oi_22_35_days,
            s_today.oi_36_60_days,
            s_today.oi_0_7_days_percent,
            s_today.oi_8_21_days_percent,
            s_today.oi_22_35_days_percent,
            s_today.oi_36_60_days_percent,
            s_today.call_oi_0_7_days,
            s_today.call_oi_8_21_days,
            s_today.call_oi_22_35_days,
            s_today.call_oi_36_60_days,
            s_today.put_oi_0_7_days,
            s_today.put_oi_8_21_days,
            s_today.put_oi_22_35_days,
            s_today.put_oi_36_60_days,
            s_yesterday.option_volume,
            s_yesterday.call_volume,
            s_yesterday.put_volume,
            s_yesterday.volume_put_call_ratio,
            s_yesterday.call_iv_avg,
            s_yesterday.put_iv_avg,
            s_yesterday.iv_skew,
            s_yesterday.symbol_iv_percentile_30d,
            s_yesterday.total_delta_exposure,
            s_yesterday.call_delta_exposure,
            s_yesterday.put_delta_exposure,
            s_yesterday.net_delta_exposure,
            s_yesterday.total_gamma_exposure,
            s_yesterday.max_gamma_strike,
            s_yesterday.total_theta_exposure,
            s_yesterday.total_vega_exposure,
            s_yesterday.call_vega_exposure,
            s_yesterday.put_vega_exposure,
            s_yesterday.net_vega_exposure,
            s_today.deep_itm_call_oi,
            s_today.itm_call_oi,
            s_today.atm_call_oi,
            s_today.otm_call_oi,
            s_today.deep_otm_call_oi,
            s_today.deep_itm_put_oi,
            s_today.itm_put_oi,
            s_today.atm_put_oi,
            s_today.otm_put_oi,
            s_today.deep_otm_put_oi,
            s_today.deep_itm_call_pct,
            s_today.itm_call_pct,
            s_today.atm_call_pct,
            s_today.otm_call_pct,
            s_today.deep_otm_call_pct,
            s_today.deep_itm_put_pct,
            s_today.itm_put_pct,
            s_today.atm_put_pct,
            s_today.otm_put_pct,
            s_today.deep_otm_put_pct,
            s_yesterday.avg_bid_ask_spread_pct,
            s_today.max_pain_by_friday
        FROM option_symbol_summary s_today
        JOIN option_symbol_summary s_yesterday
            ON s_today.symbol = s_yesterday.symbol
            AND s_yesterday.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary WHERE trade_date < (SELECT MAX(trade_date) FROM option_symbol_summary))
        WHERE s_today.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
        ''')

        # View 3: OI Timing Context (Today's OI with yesterday's price context)
        cursor.execute('''
        CREATE VIEW v_oi_timing_context AS
        SELECT
            o_today.contract_hash,
            o_today.symbol,
            o_today.strike,
            o_today.option_type,
            o_today.expiration_date,
            o_today.trade_date,
            o_today.open_interest,
            o_today.dte as dte,

            o_today.oi_build_start_date,
            o_today.oi_build_start_price,

            o_yesterday.underlying_price as current_price,
            o_yesterday.iv as iv,
            o_yesterday.iv_percentile_20day as iv_percentile,

            CASE
                WHEN o_today.option_type = 'PUT' AND o_today.oi_build_start_price > o_yesterday.underlying_price
                THEN 'PREDICTIVE (bought puts when stock was higher)'
                WHEN o_today.option_type = 'PUT' AND o_today.oi_build_start_price < o_yesterday.underlying_price
                THEN 'CHASING (bought puts after stock fell)'
                WHEN o_today.option_type = 'CALL' AND o_today.oi_build_start_price < o_yesterday.underlying_price
                THEN 'PREDICTIVE (bought calls when stock was lower)'
                WHEN o_today.option_type = 'CALL' AND o_today.oi_build_start_price > o_yesterday.underlying_price
                THEN 'CHASING (bought calls after stock rose)'
                ELSE 'NEUTRAL'
            END as positioning_type,

            CAST(JULIANDAY(o_today.trade_date) - JULIANDAY(o_today.oi_build_start_date) AS INTEGER) as oi_build_days_since,

            ROUND((o_yesterday.underlying_price - o_today.oi_build_start_price) / o_today.oi_build_start_price * 100, 2) as oi_build_price_move_pct

        FROM option_contracts o_today
        JOIN option_contracts o_yesterday
            ON o_today.contract_hash = o_yesterday.contract_hash
            AND o_yesterday.trade_date = (SELECT MAX(trade_date) FROM option_contracts WHERE trade_date < (SELECT MAX(trade_date) FROM option_contracts))
        WHERE
            o_today.symbol IN (SELECT symbol FROM v_morning_discovery)
            AND o_today.open_interest > 1000
            AND o_today.oi_build_start_date IS NOT NULL
            AND o_today.trade_date = (SELECT MAX(trade_date) FROM option_contracts)
        ''')

        # View 4: Option Comparison (Today's OI + Yesterday's pricing/greeks + Time-to-Target Analysis)
        cursor.execute('''
        CREATE VIEW v_option_comparison AS
        SELECT
            o_today.contract_hash,
            o_today.symbol,
            o_today.trade_date,
            o_today.strike,
            o_today.expiration_date,
            o_today.option_type,
            o_today.dte AS dte,
            o_yesterday.moneyness,

            o_yesterday.last_price,
            o_yesterday.underlying_price,

            o_yesterday.delta,
            o_yesterday.gamma,
            o_yesterday.theta,
            o_yesterday.vega,
            o_yesterday.iv AS IV,
            o_yesterday.iv_percentile_20day AS iv_percentile,

            o_today.open_interest,
            o_yesterday.volume,

            CASE
                WHEN o_today.option_type = 'CALL' THEN o_today.strike + o_yesterday.last_price
                WHEN o_today.option_type = 'PUT' THEN o_today.strike - o_yesterday.last_price
            END as breakeven_price,

            CASE
                WHEN o_today.option_type = 'CALL' THEN ROUND(((o_today.strike + o_yesterday.last_price) / o_yesterday.underlying_price - 1) * 100, 2)
                WHEN o_today.option_type = 'PUT' THEN ROUND((1 - (o_today.strike - o_yesterday.last_price) / o_yesterday.underlying_price) * 100, 2)
            END as breakeven_move_pct,

            ROUND(ABS(o_yesterday.delta) / NULLIF(o_yesterday.last_price, 0), 2) as delta_per_dollar,

            CASE WHEN o_yesterday.gamma > 0.05 THEN 1 ELSE 0 END as in_gamma_zone,

            ROUND(o_yesterday.theta * 100, 2) as theta_decay_dollars,

            ROUND(o_yesterday.vega * 100, 2) as vega_dollars_per_iv_point,

            CASE
                WHEN o_today.option_type = 'CALL' AND o_yesterday.underlying_price > o_today.strike
                THEN ROUND(o_yesterday.underlying_price - o_today.strike, 2)
                WHEN o_today.option_type = 'PUT' AND o_yesterday.underlying_price < o_today.strike
                THEN ROUND(o_today.strike - o_yesterday.underlying_price, 2)
                ELSE 0
            END as intrinsic_value,

            ROUND(o_yesterday.last_price - CASE
                WHEN o_today.option_type = 'CALL' AND o_yesterday.underlying_price > o_today.strike
                THEN o_yesterday.underlying_price - o_today.strike
                WHEN o_today.option_type = 'PUT' AND o_yesterday.underlying_price < o_today.strike
                THEN o_today.strike - o_yesterday.underlying_price
                ELSE 0
            END, 2) as extrinsic_value,

            s_yesterday.avg_bid_ask_spread_pct,

            -- TIME-TO-TARGET ANALYSIS (from daily_analysis probability calculations)

            -- Required move to reach strike (percent, only for OTM)
            CASE
                WHEN o_today.option_type = 'CALL' AND o_today.strike > o_yesterday.underlying_price
                THEN ROUND((o_today.strike - o_yesterday.underlying_price) / o_yesterday.underlying_price * 100, 2)
                WHEN o_today.option_type = 'PUT' AND o_today.strike < o_yesterday.underlying_price
                THEN ROUND((o_yesterday.underlying_price - o_today.strike) / o_yesterday.underlying_price * 100, 2)
                ELSE NULL
            END as required_move_to_strike_pct,

            -- Days to reach strike using IV formula: 365 × (Required Move % / IV)²
            CASE
                WHEN o_today.option_type = 'CALL' AND o_today.strike > o_yesterday.underlying_price
                     AND o_yesterday.iv > 0 AND o_yesterday.underlying_price > 0
                THEN ROUND(365.0 * POWER((o_today.strike - o_yesterday.underlying_price) / o_yesterday.underlying_price / o_yesterday.iv, 2), 2)
                WHEN o_today.option_type = 'PUT' AND o_today.strike < o_yesterday.underlying_price
                     AND o_yesterday.iv > 0 AND o_yesterday.underlying_price > 0
                THEN ROUND(365.0 * POWER((o_yesterday.underlying_price - o_today.strike) / o_yesterday.underlying_price / o_yesterday.iv, 2), 2)
                ELSE NULL
            END as days_to_reach_strike,

            -- Time advantage ratio: DTE / days_to_reach_strike
            CASE
                WHEN o_today.option_type = 'CALL' AND o_today.strike > o_yesterday.underlying_price
                     AND o_yesterday.iv > 0 AND o_yesterday.underlying_price > 0
                THEN ROUND(o_today.dte / NULLIF(
                    365.0 * POWER((o_today.strike - o_yesterday.underlying_price) / o_yesterday.underlying_price / o_yesterday.iv, 2), 0), 2)
                WHEN o_today.option_type = 'PUT' AND o_today.strike < o_yesterday.underlying_price
                     AND o_yesterday.iv > 0 AND o_yesterday.underlying_price > 0
                THEN ROUND(o_today.dte / NULLIF(
                    365.0 * POWER((o_yesterday.underlying_price - o_today.strike) / o_yesterday.underlying_price / o_yesterday.iv, 2), 0), 2)
                ELSE NULL
            END as time_advantage_ratio,

            -- Time pressure level: COMFORTABLE (>1.5), TIGHT (1.0-1.5), CRITICAL (<1.0)
            CASE
                WHEN o_today.option_type = 'CALL' AND o_today.strike > o_yesterday.underlying_price
                     AND o_yesterday.iv > 0 AND o_yesterday.underlying_price > 0
                THEN CASE
                    WHEN o_today.dte / NULLIF(
                        365.0 * POWER((o_today.strike - o_yesterday.underlying_price) / o_yesterday.underlying_price / o_yesterday.iv, 2), 0) > 1.5
                    THEN 'COMFORTABLE'
                    WHEN o_today.dte / NULLIF(
                        365.0 * POWER((o_today.strike - o_yesterday.underlying_price) / o_yesterday.underlying_price / o_yesterday.iv, 2), 0) >= 1.0
                    THEN 'TIGHT'
                    ELSE 'CRITICAL'
                END
                WHEN o_today.option_type = 'PUT' AND o_today.strike < o_yesterday.underlying_price
                     AND o_yesterday.iv > 0 AND o_yesterday.underlying_price > 0
                THEN CASE
                    WHEN o_today.dte / NULLIF(
                        365.0 * POWER((o_yesterday.underlying_price - o_today.strike) / o_yesterday.underlying_price / o_yesterday.iv, 2), 0) > 1.5
                    THEN 'COMFORTABLE'
                    WHEN o_today.dte / NULLIF(
                        365.0 * POWER((o_yesterday.underlying_price - o_today.strike) / o_yesterday.underlying_price / o_yesterday.iv, 2), 0) >= 1.0
                    THEN 'TIGHT'
                    ELSE 'CRITICAL'
                END
                ELSE NULL
            END as time_pressure_level

        FROM option_contracts o_today
        JOIN option_contracts o_yesterday
            ON o_today.contract_hash = o_yesterday.contract_hash
            AND o_yesterday.trade_date = (SELECT MAX(trade_date) FROM option_contracts WHERE trade_date < (SELECT MAX(trade_date) FROM option_contracts))
        JOIN option_symbol_summary s_yesterday
            ON o_yesterday.symbol = s_yesterday.symbol
            AND o_yesterday.trade_date = s_yesterday.trade_date

        WHERE
            o_today.dte BETWEEN 7 AND 60
            AND o_yesterday.last_price > 0
            AND o_today.trade_date = (SELECT MAX(trade_date) FROM option_contracts)
        ''')

        # View 5: Live Market Snapshot (Real-time market data from flow_options_scans)
        cursor.execute('''
        CREATE VIEW IF NOT EXISTS v_live_market_snapshot AS
        WITH latest_scan AS (
            SELECT MAX(scan_timestamp) as ts, trade_date
            FROM flow_options_scans
            WHERE trade_date = DATE('now')
            GROUP BY trade_date
        ),
        spy_data AS (
            SELECT
                MAX(underlying_price) as underlying_price,
                MAX(underlying_change_pct) as underlying_change_pct
            FROM flow_options_scans
            WHERE symbol = 'SPY'
              AND scan_timestamp = (SELECT ts FROM latest_scan)
        ),
        vix_data AS (
            SELECT
                MAX(underlying_price) as underlying_price,
                MAX(underlying_change_pct) as underlying_change_pct
            FROM flow_options_scans
            WHERE symbol = 'VIX'
              AND scan_timestamp = (SELECT ts FROM latest_scan)
        ),
        market_breadth AS (
            SELECT
                COUNT(CASE WHEN underlying_change_pct > 0 THEN 1 END) as advancing,
                COUNT(CASE WHEN underlying_change_pct < 0 THEN 1 END) as declining,
                ROUND(
                    CAST(COUNT(CASE WHEN underlying_change_pct > 0 THEN 1 END) AS REAL) /
                    NULLIF(COUNT(CASE WHEN underlying_change_pct < 0 THEN 1 END), 0),
                    2
                ) as adv_dec_ratio
            FROM (
                SELECT DISTINCT symbol, underlying_change_pct
                FROM flow_options_scans
                WHERE scan_timestamp = (SELECT ts FROM latest_scan)
            )
        )
        SELECT
            (SELECT ts FROM latest_scan) as last_updated,
            (SELECT trade_date FROM latest_scan) as trade_date,
            spy_data.underlying_price as spy_price,
            spy_data.underlying_change_pct as spy_change_pct,
            vix_data.underlying_price as vix_price,
            vix_data.underlying_change_pct as vix_change_pct,
            market_breadth.advancing as advancing_stocks,
            market_breadth.declining as declining_stocks,
            market_breadth.adv_dec_ratio,
            CASE
                WHEN spy_data.underlying_change_pct > 1.0 AND vix_data.underlying_change_pct < -5.0 THEN 'Strong Bull'
                WHEN spy_data.underlying_change_pct > 0.5 AND vix_data.underlying_change_pct < 0 THEN 'Bull'
                WHEN spy_data.underlying_change_pct < -1.0 AND vix_data.underlying_change_pct > 5.0 THEN 'Strong Bear'
                WHEN spy_data.underlying_change_pct < -0.5 AND vix_data.underlying_change_pct > 0 THEN 'Bear'
                ELSE 'Neutral'
            END as market_direction,
            CASE
                WHEN vix_data.underlying_price < 15 THEN 'LOW'
                WHEN vix_data.underlying_price BETWEEN 15 AND 20 THEN 'NORMAL'
                WHEN vix_data.underlying_price BETWEEN 20 AND 30 THEN 'ELEVATED'
                ELSE 'PANIC'
            END as volatility_regime
        FROM spy_data, vix_data, market_breadth
        ''')

        self.conn.commit()

    def _get_display_date(self):
        """
        Get the most recent trading day with complete data.

        DATA TIMING LOGIC (CRITICAL - READ THIS):
        ------------------------------------------
        OID Pipeline runs twice daily:
        1. MORNING SCAN (~6:35 AM): Updates OPEN INTEREST only for today's trade_date
        2. EVENING SCAN (~5:00 PM): Updates VOLUME and GREEKS for today's trade_date

        Morning Views runs AFTER morning OID scan (~7:30 AM):
        - Today's row exists but only has OI (volume=0, greeks incomplete)
        - Yesterday's row has complete data (OI + volume + greeks)

        IMPLEMENTATION:
        Use explicit date logic: SELECT MAX(trade_date) WHERE trade_date < DATE('now')
        This returns the most recent historical day (yesterday), not today.

        All views use the same logic to ensure consistency.
        Today's fresh OI can be shown separately if needed via joins.

        Returns:
            str: ISO date string (YYYY-MM-DD) for yesterday (complete data)
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(trade_date) FROM option_symbol_summary WHERE trade_date < (SELECT MAX(trade_date) FROM option_symbol_summary)")
        result = cursor.fetchone()

        if result and result[0]:
            return result[0]

        # Fallback: use yesterday if no data found
        now = now_eastern()
        yesterday = (now - timedelta(days=1)).date()
        return yesterday.isoformat()
