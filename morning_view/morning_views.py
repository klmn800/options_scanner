#!/usr/bin/env python3
"""
Morning Views - Daily Options Watchlist CLI

Usage:
    python morning_views.py                    # Show daily watchlist
    python morning_views.py --symbol AAL       # Deep dive on AAL
    python morning_views.py --limit 10         # Show top 10 only
    python morning_views.py --config custom.json  # Use custom config

Output:
    - Console display with emoji symbols (safe encoding)
    - Log file: morning_view/logs/morning_view_YYYY-MM-DD.md

Safety Features:
    - Decimal policy: All numeric values formatted to standard precision
    - Emoji handling: Fallback to ASCII if unicode encoding fails
    - Eastern timezone: All timestamps use EST/EDT
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

        # Markdown output directory (separate from logging)
        self.log_dir = Path(__file__).parent / 'logs'
        self.log_dir.mkdir(exist_ok=True)

        # Get display date (yesterday for complete data)
        self.display_date = self._get_display_date()

        # Emoji safety: Try to use emojis, fallback to ASCII if encoding fails
        self.use_emojis = self._test_emoji_support()

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

    def _test_emoji_support(self):
        """
        Test if the terminal supports emoji output.

        Returns:
            bool: True if emojis work, False to use ASCII fallback
        """
        try:
            # Try to encode common emoji
            test = "📊🎯💡🔍"
            test.encode(sys.stdout.encoding or 'utf-8')
            return True
        except (UnicodeEncodeError, AttributeError):
            return False

    def _emoji(self, emoji_char, ascii_fallback):
        """
        Return emoji if supported, otherwise ASCII fallback.

        Args:
            emoji_char: Unicode emoji character
            ascii_fallback: ASCII alternative

        Returns:
            str: Emoji or ASCII fallback
        """
        return emoji_char if self.use_emojis else ascii_fallback

    def _format_row(self, row):
        """
        Apply decimal policy formatting to a database row.

        Args:
            row: sqlite3.Row object

        Returns:
            dict: Cleaned row with proper decimal precision
        """
        # Convert Row to dict
        row_dict = dict(row)
        # Apply decimal formatting
        formatted = clean_database_row(row_dict)
        # Replace None with 0 for numeric fields to prevent format errors
        for key, value in formatted.items():
            if value is None:
                formatted[key] = 0
        return formatted

    def _write_log(self, content):
        """
        Write output to daily log file.

        Args:
            content: String content to write (markdown format)
        """
        log_file = self.log_dir / f"morning_view_{eastern_date_string()}.md"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def _parse_comparison_args(self, strikes_str, expirations_str):
        """
        Parse and validate strikes and expirations for 4-option comparison.

        Args:
            strikes_str: Comma-separated strikes (e.g., "11,12")
            expirations_str: Comma-separated dates (e.g., "10/10,10/24")

        Returns:
            tuple: (strikes_list, expirations_list) or (None, error_message)

        Examples:
            >>> _parse_comparison_args("11,12", "10/10,10/24")
            ([11.0, 12.0], ['2025-10-10', '2025-10-24'])
        """
        now = now_eastern()
        current_year = now.year

        # Parse strikes
        try:
            strikes = [float(s.strip()) for s in strikes_str.split(',')]
            if len(strikes) != 2:
                return None, f"Error: Exactly 2 strikes required, got {len(strikes)}"
        except ValueError as e:
            return None, f"Error parsing strikes: {e}"

        # Parse expirations
        try:
            exp_dates = []
            for exp in expirations_str.split(','):
                exp = exp.strip()
                # Parse MM/DD format
                if '/' in exp:
                    month, day = exp.split('/')
                    # Determine year (if date already passed this year, assume next year)
                    exp_date_obj = datetime(current_year, int(month), int(day)).date()
                    if exp_date_obj < now.date():
                        exp_date_obj = datetime(current_year + 1, int(month), int(day)).date()
                    exp_dates.append(exp_date_obj.isoformat())
                else:
                    return None, f"Error: Expiration must be MM/DD format, got '{exp}'"

            if len(exp_dates) != 2:
                return None, f"Error: Exactly 2 expirations required, got {len(exp_dates)}"

        except (ValueError, IndexError) as e:
            return None, f"Error parsing expirations: {e}"

        return (strikes, exp_dates), None

    def _fetch_comparison_contracts(self, symbol, strikes, expirations):
        """
        Fetch 4 call option contracts for comparison from v_option_comparison view.

        Args:
            symbol: Stock symbol (e.g., 'AAL')
            strikes: List of 2 strike prices [11.0, 12.0]
            expirations: List of 2 expiration dates ['2025-10-10', '2025-10-24']

        Returns:
            dict: Nested dict organized by strike and expiration, or None if data missing

        Structure:
            {
                11.0: {
                    '2025-10-10': {contract_data},
                    '2025-10-24': {contract_data}
                },
                12.0: {
                    '2025-10-10': {contract_data},
                    '2025-10-24': {contract_data}
                }
            }
        """
        cursor = self.conn.cursor()

        # Build query for all 4 contracts (CALL options only)
        query = """
        SELECT * FROM v_option_comparison
        WHERE symbol = ?
          AND strike IN (?, ?)
          AND expiration_date IN (?, ?)
          AND option_type = 'CALL'
        ORDER BY strike, expiration_date
        """

        cursor.execute(query, (symbol, strikes[0], strikes[1], expirations[0], expirations[1]))
        results = cursor.fetchall()

        if len(results) != 4:
            return None  # Missing data

        # Organize by strike and expiration
        contracts = {}
        for row in results:
            formatted = self._format_row(row)
            strike = formatted['strike']
            exp = formatted['expiration_date']

            if strike not in contracts:
                contracts[strike] = {}
            contracts[strike][exp] = formatted

        return contracts

    def show_option_comparison(self, symbol, strikes_str, exp_str):
        """
        Display side-by-side comparison of 4 call option contracts.

        Args:
            symbol: Stock symbol (e.g., 'AAL')
            strikes_str: Comma-separated strikes (e.g., "11,12")
            exp_str: Comma-separated expirations (e.g., "10/10,10/24")

        Displays:
            4-column table comparing:
            - Strike $X (exp1) | Strike $X (exp2) | Strike $Y (exp1) | Strike $Y (exp2)
            With metrics: Last Price, Delta, Gamma, Theta, Vega, IV, Breakeven, etc.
        """
        # Validate required arguments
        if not strikes_str or not exp_str:
            warn_emoji = self._emoji("⚠️", "!")
            print(f"\n{warn_emoji}  Error: Both --strikes and --exp are required for comparison")
            print(f"   Example: python morning_views.py --compare AAL --strikes 11,12 --exp 10/10,10/24\n")
            return

        # Parse arguments
        result, error = self._parse_comparison_args(strikes_str, exp_str)
        if error:
            warn_emoji = self._emoji("⚠️", "!")
            print(f"\n{warn_emoji}  {error}\n")
            return

        strikes, expirations = result

        # Fetch contracts
        print(f"🔍 Querying 4-option comparison for {symbol}...")
        contracts = self._fetch_comparison_contracts(symbol, strikes, expirations)

        if not contracts:
            warn_emoji = self._emoji("⚠️", "!")
            print(f"\n{warn_emoji}  Could not find all 4 contracts for comparison")
            print(f"   Symbol: {symbol}")
            print(f"   Strikes: {strikes[0]}, {strikes[1]}")
            print(f"   Expirations: {expirations[0]}, {expirations[1]}")
            print(f"   Note: Only CALL options with 7-60 DTE are available in v_option_comparison view\n")
            return

        # Display header
        compare_emoji = self._emoji("🔬", "[COMPARE]")
        print(f"\n{compare_emoji} 4-Option Comparison: {symbol} CALL Options")
        print(f"{'='*140}\n")

        # Get the 4 contracts (ordered)
        s1, s2 = sorted(strikes)
        e1, e2 = sorted(expirations)

        c1 = contracts[s1][e1]  # Strike 1, Exp 1
        c2 = contracts[s1][e2]  # Strike 1, Exp 2
        c3 = contracts[s2][e1]  # Strike 2, Exp 1
        c4 = contracts[s2][e2]  # Strike 2, Exp 2

        # Column headers
        h1 = f"${s1} {e1}"
        h2 = f"${s1} {e2}"
        h3 = f"${s2} {e1}"
        h4 = f"${s2} {e2}"

        # Print table
        col_width = 18
        print(f"{'Metric':<25} {h1:^{col_width}} {h2:^{col_width}} {h3:^{col_width}} {h4:^{col_width}}")
        print(f"{'-'*140}")

        # Pricing
        print(f"{'Last Price':<25} ${c1['last_price']:^17.2f} ${c2['last_price']:^17.2f} ${c3['last_price']:^17.2f} ${c4['last_price']:^17.2f}")
        print(f"{'Underlying Price':<25} ${c1['underlying_price']:^17.2f} ${c2['underlying_price']:^17.2f} ${c3['underlying_price']:^17.2f} ${c4['underlying_price']:^17.2f}")

        # Greeks
        print(f"\n{'--- GREEKS ---':<25}")
        print(f"{'Delta':<25} {c1['delta']:^18.4f} {c2['delta']:^18.4f} {c3['delta']:^18.4f} {c4['delta']:^18.4f}")
        print(f"{'Gamma':<25} {c1['gamma']:^18.4f} {c2['gamma']:^18.4f} {c3['gamma']:^18.4f} {c4['gamma']:^18.4f}")
        print(f"{'Theta ($/day)':<25} ${c1['theta_decay_dollars']:^17.2f} ${c2['theta_decay_dollars']:^17.2f} ${c3['theta_decay_dollars']:^17.2f} ${c4['theta_decay_dollars']:^17.2f}")
        print(f"{'Vega ($/IV point)':<25} ${c1['vega_dollars_per_iv_point']:^17.2f} ${c2['vega_dollars_per_iv_point']:^17.2f} ${c3['vega_dollars_per_iv_point']:^17.2f} ${c4['vega_dollars_per_iv_point']:^17.2f}")
        print(f"{'IV':<25} {c1['IV']:^18.4f} {c2['IV']:^18.4f} {c3['IV']:^18.4f} {c4['IV']:^18.4f}")

        # Efficiency metrics
        print(f"\n{'--- EFFICIENCY ---':<25}")
        print(f"{'Delta per Dollar':<25} {c1['delta_per_dollar']:^18.2f} {c2['delta_per_dollar']:^18.2f} {c3['delta_per_dollar']:^18.2f} {c4['delta_per_dollar']:^18.2f}")
        print(f"{'Breakeven Price':<25} ${c1['breakeven_price']:^17.2f} ${c2['breakeven_price']:^17.2f} ${c3['breakeven_price']:^17.2f} ${c4['breakeven_price']:^17.2f}")
        print(f"{'Breakeven Move %':<25} {c1['breakeven_move_pct']:^17.2f}% {c2['breakeven_move_pct']:^17.2f}% {c3['breakeven_move_pct']:^17.2f}% {c4['breakeven_move_pct']:^17.2f}%")
        print(f"{'In Gamma Zone':<25} {'Yes' if c1['in_gamma_zone'] else 'No':^18} {'Yes' if c2['in_gamma_zone'] else 'No':^18} {'Yes' if c3['in_gamma_zone'] else 'No':^18} {'Yes' if c4['in_gamma_zone'] else 'No':^18}")

        # Time-to-target analysis (from daily_analysis probability calculations)
        print(f"\n{'--- TIME-TO-TARGET ANALYSIS ---':<25}")

        # Required move to strike
        rm1 = c1.get('required_move_to_strike_pct')
        rm2 = c2.get('required_move_to_strike_pct')
        rm3 = c3.get('required_move_to_strike_pct')
        rm4 = c4.get('required_move_to_strike_pct')
        print(f"{'Req Move to Strike':<25} {f'{rm1:.2f}%' if rm1 else 'ITM':^18} {f'{rm2:.2f}%' if rm2 else 'ITM':^18} {f'{rm3:.2f}%' if rm3 else 'ITM':^18} {f'{rm4:.2f}%' if rm4 else 'ITM':^18}")

        # Days to reach strike
        d1 = c1.get('days_to_reach_strike')
        d2 = c2.get('days_to_reach_strike')
        d3 = c3.get('days_to_reach_strike')
        d4 = c4.get('days_to_reach_strike')
        print(f"{'Days to Strike':<25} {f'{d1:.1f}' if d1 else 'N/A':^18} {f'{d2:.1f}' if d2 else 'N/A':^18} {f'{d3:.1f}' if d3 else 'N/A':^18} {f'{d4:.1f}' if d4 else 'N/A':^18}")

        # Time advantage ratio
        r1 = c1.get('time_advantage_ratio')
        r2 = c2.get('time_advantage_ratio')
        r3 = c3.get('time_advantage_ratio')
        r4 = c4.get('time_advantage_ratio')
        print(f"{'Time Advantage Ratio':<25} {f'{r1:.2f}x' if r1 else 'N/A':^18} {f'{r2:.2f}x' if r2 else 'N/A':^18} {f'{r3:.2f}x' if r3 else 'N/A':^18} {f'{r4:.2f}x' if r4 else 'N/A':^18}")

        # Time pressure level
        p1 = c1.get('time_pressure_level') or 'N/A'
        p2 = c2.get('time_pressure_level') or 'N/A'
        p3 = c3.get('time_pressure_level') or 'N/A'
        p4 = c4.get('time_pressure_level') or 'N/A'
        print(f"{'Time Pressure':<25} {p1:^18} {p2:^18} {p3:^18} {p4:^18}")

        # Value breakdown
        print(f"\n{'--- VALUE BREAKDOWN ---':<25}")
        print(f"{'Intrinsic Value':<25} ${c1['intrinsic_value']:^17.2f} ${c2['intrinsic_value']:^17.2f} ${c3['intrinsic_value']:^17.2f} ${c4['intrinsic_value']:^17.2f}")
        print(f"{'Extrinsic Value':<25} ${c1['extrinsic_value']:^17.2f} ${c2['extrinsic_value']:^17.2f} ${c3['extrinsic_value']:^17.2f} ${c4['extrinsic_value']:^17.2f}")
        print(f"{'Moneyness':<25} {c1['moneyness']:^18} {c2['moneyness']:^18} {c3['moneyness']:^18} {c4['moneyness']:^18}")

        # Volume/OI
        print(f"\n{'--- LIQUIDITY ---':<25}")
        print(f"{'Open Interest':<25} {c1['open_interest']:^18,} {c2['open_interest']:^18,} {c3['open_interest']:^18,} {c4['open_interest']:^18,}")
        print(f"{'Volume':<25} {c1['volume']:^18,} {c2['volume']:^18,} {c3['volume']:^18,} {c4['volume']:^18,}")
        print(f"{'DTE':<25} {c1['dte']:^18} {c2['dte']:^18} {c3['dte']:^18} {c4['dte']:^18}")

        # Analysis summary
        print(f"\n{'='*140}")
        target_emoji = self._emoji("🎯", "[BEST]")
        print(f"{target_emoji} Best Delta Efficiency:")

        # Find best delta per dollar
        delta_efficiencies = [
            (c1['delta_per_dollar'], f"${s1} {e1}"),
            (c2['delta_per_dollar'], f"${s1} {e2}"),
            (c3['delta_per_dollar'], f"${s2} {e1}"),
            (c4['delta_per_dollar'], f"${s2} {e2}")
        ]
        best_delta_eff = max(delta_efficiencies, key=lambda x: x[0])
        print(f"   {best_delta_eff[1]} - {best_delta_eff[0]:.2f} delta per dollar spent")

        # Find lowest breakeven move
        breakeven_moves = [
            (c1['breakeven_move_pct'], f"${s1} {e1}"),
            (c2['breakeven_move_pct'], f"${s1} {e2}"),
            (c3['breakeven_move_pct'], f"${s2} {e1}"),
            (c4['breakeven_move_pct'], f"${s2} {e2}")
        ]
        easiest_breakeven = min(breakeven_moves, key=lambda x: abs(x[0]))
        print(f"\n{target_emoji} Easiest Breakeven:")
        print(f"   {easiest_breakeven[1]} - {abs(easiest_breakeven[0]):.2f}% move required")

        print(f"\n{'='*140}\n")

    def show_watchlist(self, limit=None):
        """
        Display the daily watchlist with ALL views.

        Strategy: Show v_morning_discovery PLUS v_symbol_oi_detail for each symbol.
        User will see complete picture and can pare back what's overwhelming later.
        """
        if limit is None:
            limit = self.config['display']['watchlist_limit']

        self.logger.info(f"Starting watchlist generation (limit: {limit})")
        print("🔍 Querying morning discovery view...")
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM v_morning_discovery LIMIT ?", (limit,))
        watchlist_results = cursor.fetchall()

        if not watchlist_results:
            warn_emoji = self._emoji("⚠️", "!")
            print(f"\n{warn_emoji}  No symbols found matching criteria\n")
            self.logger.warning("No symbols found matching watchlist criteria")
            return

        self.logger.info(f"Found {len(watchlist_results)} symbols for watchlist")
        print(f"✓ Found {len(watchlist_results)} symbols for today's watchlist\n")

        # Get market context from first row (apply decimal formatting)
        first_row = self._format_row(watchlist_results[0])
        market_direction = first_row.get('market_direction', 'Unknown')
        regime = first_row.get('market_regime', 'Unknown')

        # Build output (both console and log)
        output_lines = []
        now = now_eastern()
        header_emoji = self._emoji("📊", "[DATA]")

        header = f"\n{header_emoji} Morning Views - {eastern_date_string()}"
        header += f" (Displaying data from {self.display_date} with OI changes through today)"
        header += f"\nMarket: {market_direction} | Regime: {regime}\n"
        header += f"Showing {len(watchlist_results)} symbols with ALL view data"

        output_lines.append(header)
        print(header)

        # Display ALL views for each symbol
        # Ben wants to see EVERYTHING first, then decide what to keep
        for i, wl_row in enumerate(watchlist_results, 1):
            # Apply decimal formatting
            formatted = self._format_row(wl_row)
            symbol = formatted['symbol']
            print(f"📊 Processing {i}/{len(watchlist_results)}: {symbol}")

            # Build comprehensive display for this symbol
            separator = "=" * 120
            output_lines.append(separator)
            print(separator)

            # Rank and symbol header
            rank_line = f"#{i} - {symbol}"
            output_lines.append(rank_line)
            print(rank_line)
            output_lines.append("-" * 120)
            print("-" * 120)

            # SECTION 1: v_morning_watchlist data
            section1_emoji = self._emoji("📋", "[WATCHLIST]")
            section1 = f"\n{section1_emoji} WATCHLIST VIEW"
            output_lines.append(section1)
            print(section1)

            # Core metrics
            price_change = formatted.get('price_change_5d_pct')
            price_change_str = f"{price_change:+.1f}%" if price_change is not None else "N/A"
            core = (f"  Price: ${formatted.get('close_price') or 0:.2f} | "
                   f"5d Change: {price_change_str} | "
                   f"Confluence Score: {formatted.get('confluence_score') or 0} | "
                   f"Primary Signal: {formatted.get('primary_signal') or 'N/A'}")
            output_lines.append(core)
            print(core)

            # Directional analysis
            direction = (f"  Direction: {formatted.get('direction_bias') or 'N/A'} | "
                        f"Conviction: {formatted.get('conviction_level') or 'N/A'} | "
                        f"Put/Call Ratio: {formatted.get('put_call_ratio') or 0:.2f}")
            output_lines.append(direction)
            print(direction)

            # Open Interest
            oi = (f"  Total OI: {formatted.get('total_open_interest') or 0:,} | "
                 f"Call OI: {formatted.get('total_call_oi') or 0:,} | "
                 f"Put OI: {formatted.get('total_put_oi') or 0:,}")
            output_lines.append(oi)
            print(oi)

            # Flow alerts
            flow = f"  Active Alerts (7d): {formatted.get('active_alerts_count', 0)}"
            output_lines.append(flow)
            print(flow)

            # News sentiment
            sentiment_avg = formatted.get('news_sentiment_avg')
            sentiment_str = f"{sentiment_avg:.3f}" if sentiment_avg else "N/A"
            news = (f"  News Sentiment: {formatted.get('news_sentiment', 'N/A')} "
                   f"(avg: {sentiment_str})")
            output_lines.append(news)
            print(news)

            # Options volume surge
            vol_surge = formatted.get('volume_surge_factor')
            if vol_surge is not None and vol_surge > 0:
                vol_str = f"{vol_surge:.2f}x"
            else:
                vol_str = "N/A"
            volume_line = f"  Option Volume Surge (vs 20d avg): {vol_str}"
            output_lines.append(volume_line)
            print(volume_line)

            # Earnings
            if formatted.get('earnings_days_ahead'):
                earnings = (f"  {self._emoji('📅', '[EARNINGS]')} Earnings in {formatted.get('earnings_days_ahead')} days | "
                           f"Expected: {formatted.get('exp_move_pct', 0):.1f}% | "
                           f"Historical: {formatted.get('hist_move_pct', 0):.1f}% | "
                           f"Diff: {formatted.get('diff_move_pct', 0):.1f}% | "
                           f"Signal: {formatted.get('earnings_play_signal', 'N/A')}")
                output_lines.append(earnings)
                print(earnings)

            # Sector/Industry
            sector_line = f"  Sector: {formatted.get('sector', 'N/A')} | Industry: {formatted.get('industry', 'N/A')}"
            output_lines.append(sector_line)
            print(sector_line)

            # SECTION 2: v_symbol_oi_detail data
            cursor.execute("SELECT * FROM v_symbol_oi_detail WHERE symbol = ?", (symbol,))
            oi_detail = cursor.fetchone()

            if oi_detail:
                oi_formatted = self._format_row(oi_detail)

                section2_emoji = self._emoji("🎯", "[OI DETAIL]")
                section2 = f"\n{section2_emoji} OI DISTRIBUTION VIEW"
                output_lines.append(section2)
                print(section2)

                # Top strikes
                top_calls = f"  Top 5 Calls: {oi_formatted.get('top_call_display', 'N/A')}"
                top_puts = f"  Top 5 Puts: {oi_formatted.get('top_put_display', 'N/A')}"
                output_lines.append(top_calls)
                output_lines.append(top_puts)
                print(top_calls)
                print(top_puts)

                # Time distribution
                time_dist = (f"  Time Distribution - "
                            f"0-7 DTE: {oi_formatted.get('oi_0_7_days_percent', 0):.1f}% | "
                            f"8-21 DTE: {oi_formatted.get('oi_8_21_days_percent', 0):.1f}% | "
                            f"22-35 DTE: {oi_formatted.get('oi_22_35_days_percent', 0):.1f}% | "
                            f"36-60 DTE: {oi_formatted.get('oi_36_60_days_percent', 0):.1f}%")
                output_lines.append(time_dist)
                print(time_dist)

                # Moneyness distribution (handle None values) - ITM, ATM, OTM only
                money_dist = (f"  Calls: ITM {oi_formatted.get('itm_call_pct') or 0:.1f}% | "
                             f"ATM {oi_formatted.get('atm_call_pct') or 0:.1f}% | "
                             f"OTM {oi_formatted.get('otm_call_pct') or 0:.1f}%")
                money_dist2 = (f"  Puts:  ITM {oi_formatted.get('itm_put_pct') or 0:.1f}% | "
                              f"ATM {oi_formatted.get('atm_put_pct') or 0:.1f}% | "
                              f"OTM {oi_formatted.get('otm_put_pct') or 0:.1f}%")
                output_lines.append(money_dist)
                output_lines.append(money_dist2)
                print(money_dist)
                print(money_dist2)

                # Greek exposures (formatted as millions/thousands with clear labels)
                net_delta = (oi_formatted.get('net_delta_exposure') or 0) / 1_000_000
                total_gamma = (oi_formatted.get('total_gamma_exposure') or 0) / 1_000_000
                net_vega = (oi_formatted.get('net_vega_exposure') or 0) / 1_000
                delta_sign = "+" if net_delta >= 0 else ""
                vega_sign = "+" if net_vega >= 0 else ""
                greeks = (f"  Greeks - Net Delta Exposure: {delta_sign}{net_delta:.2f}M shares | "
                         f"Total Gamma Exposure: {total_gamma:.2f}M | "
                         f"Max Gamma Strike: ${oi_formatted.get('max_gamma_strike') or 0:.2f} | "
                         f"Net Vega Exposure: {vega_sign}{net_vega:.0f}K")
                output_lines.append(greeks)
                print(greeks)

                # Max pain (calculate distance from current price)
                max_pain_val = oi_formatted.get('max_pain_by_friday', 0)
                current_price = oi_formatted.get('close_price', 0)

                if max_pain_val > 0 and current_price > 0:
                    distance_pct = ((max_pain_val - current_price) / current_price) * 100
                else:
                    distance_pct = 0

                max_pain = (f"  Max Pain: ${max_pain_val:.2f} | "
                           f"Distance: {distance_pct:+.1f}%")
                output_lines.append(max_pain)
                print(max_pain)

            # SECTION 3: v_oi_timing_context (top 3 contracts)
            cursor.execute("""
                SELECT * FROM v_oi_timing_context
                WHERE symbol = ?
                ORDER BY open_interest DESC
                LIMIT 3
            """, (symbol,))
            timing_rows = cursor.fetchall()

            if timing_rows:
                section3_emoji = self._emoji("🧠", "[TIMING]")
                section3 = f"\n{section3_emoji} OI TIMING CONTEXT (Top 3 Contracts)"
                output_lines.append(section3)
                print(section3)

                for t_row in timing_rows:
                    t_formatted = self._format_row(t_row)
                    timing_line = (f"  ${t_formatted.get('strike', 0)} {t_formatted.get('option_type', 'N/A')} {t_formatted.get('expiration_date', 'N/A')} | "
                                  f"OI: {t_formatted.get('open_interest', 0):,} | "
                                  f"Built: {t_formatted.get('oi_build_start_date', 'N/A')} @ ${t_formatted.get('oi_build_start_price', 0):.2f} | "
                                  f"{t_formatted.get('positioning_type', 'N/A')}")
                    output_lines.append(timing_line)
                    print(timing_line)

            output_lines.append("")  # Blank line between symbols
            print("")

        tip_emoji = self._emoji("💡", "[TIP]")
        footer = f"\n{tip_emoji} Tip: Use --symbol SYMBOL for even more detail (4-option comparison)\n"
        output_lines.append(footer)
        print(footer)

        # Write log file
        print("\n💾 Writing markdown log file...")
        log_content = "\n".join(output_lines)
        self._write_log(log_content)
        print(f"✓ Log file written to: {self.log_dir / f'morning_view_{eastern_date_string()}.md'}")

        # Email watchlist if --email flag provided
        if hasattr(self, 'args') and self.args.email:
            print("\n📧 Preparing email delivery...")
            self._email_watchlist()
            print("✓ Email process complete")

    def _email_watchlist(self):
        """Email morning watchlist as .docx using existing document_emailer"""
        try:
            self.logger.info("Starting email delivery process")
            # Import emailer
            from tools.document_emailer import DocumentEmailer

            print("   Reading markdown file...")
            # Read the markdown file we just created
            md_file = self.log_dir / f"morning_view_{eastern_date_string()}.md"
            with open(md_file, 'r', encoding='utf-8') as f:
                md_content = f.read()

            # Create emailer instance
            emailer = DocumentEmailer()

            print("   Converting to Word document...")
            # Create .docx using emailer
            docx_path = str(md_file).replace('.md', '.docx')
            emailer.create_word_document(
                title=f"Morning Watchlist - {eastern_date_string()}",
                content=md_content,
                output_path=docx_path
            )

            self.logger.info(f"Created Word document: {docx_path}")
            print("   Sending email (this may take 10-15 seconds)...")
            # Send email
            success = emailer.send_document_email(
                subject=f"Morning Watchlist - {eastern_date_string()}",
                body_text="Your daily options watchlist is attached. Generated at 7:30 AM EST.",
                document_path=docx_path
            )

            if success:
                print(f"   ✅ Watchlist emailed successfully")
                self.logger.info("Email sent successfully")
            else:
                print(f"   ⚠️  Email failed (check logs/email_activity.log)")
                self.logger.error("Email delivery failed")

        except Exception as e:
            print(f"   ⚠️  Failed to email watchlist: {e}")
            self.logger.error(f"Email delivery exception: {e}")
            # Don't fail the whole script if email fails

    def show_symbol_detail(self, symbol):
        """Show detailed analysis for a specific symbol with volume profile"""
        cursor = self.conn.cursor()

        # Get symbol overview
        cursor.execute("SELECT * FROM v_morning_discovery WHERE symbol = ?", (symbol,))
        overview = cursor.fetchone()

        if not overview:
            error_emoji = self._emoji("❌", "[X]")
            print(f"\n{error_emoji} Symbol {symbol} not found in watchlist\n")
            return

        # Apply decimal formatting
        overview = self._format_row(overview)

        # Get OI distribution
        cursor.execute("SELECT * FROM v_symbol_oi_detail WHERE symbol = ?", (symbol,))
        oi_detail = cursor.fetchone()
        if oi_detail:
            oi_detail = self._format_row(oi_detail)

        # Get OI timing context
        cursor.execute("""
            SELECT * FROM v_oi_timing_context
            WHERE symbol = ?
            ORDER BY oi_build_start_date ASC
            LIMIT 10
        """, (symbol,))
        timing = [self._format_row(row) for row in cursor.fetchall()]

        # Display with emoji safety
        chart_emoji = self._emoji("📈", "[CHART]")
        print(f"\n{chart_emoji} {symbol} - Detailed Analysis")
        print(f"{'='*80}\n")

        # Overview
        print(f"Price: ${overview.get('close_price', 0):.2f} | "
              f"Confluence Score: {overview.get('confluence_score', 0)} | "
              f"Bias: {overview.get('direction_bias', 'N/A')} ({overview.get('conviction_level', 'N/A')} conviction)")
        print(f"Market: {overview.get('market_direction', 'N/A')} ({overview.get('market_regime', 'N/A')}) | "
              f"Sector: {overview.get('sector', 'N/A')} / {overview.get('industry', 'N/A')}")

        # Earnings
        if overview.get('earnings_days_ahead'):
            cal_emoji = self._emoji("📅", "[CAL]")
            print(f"\n{cal_emoji} Earnings in {overview.get('earnings_days_ahead')} days:")
            print(f"   Expected move: {overview.get('exp_move_pct', 0):.1f}% | "
                  f"Historical avg: {overview.get('hist_move_pct', 0):.1f}% | "
                  f"Signal: {overview.get('earnings_play_signal', 'N/A')}")

        # OI Distribution
        if oi_detail:
            target_emoji = self._emoji("🎯", "[OI]")
            print(f"\n{target_emoji} Open Interest Distribution:")
            print(f"   Total Call OI: {oi_detail.get('total_call_oi', 0):,} | Total Put OI: {oi_detail.get('total_put_oi', 0):,}")
            print(f"   Put/Call Ratio: {oi_detail.get('put_call_ratio', 0):.2f}")
            print(f"   Top Calls: {oi_detail.get('top_call_display', 'N/A')}")
            print(f"   Top Puts: {oi_detail.get('top_put_display', 'N/A')}")

            # Calculate max pain distance
            max_pain_val = oi_detail.get('max_pain_by_friday', 0)
            current_price = oi_detail.get('close_price', 0)
            if max_pain_val > 0 and current_price > 0:
                distance_pct = ((max_pain_val - current_price) / current_price) * 100
            else:
                distance_pct = 0
            print(f"   Max Pain: ${max_pain_val:.2f} ({distance_pct:+.1f}% from current)")

            # Time distribution
            clock_emoji = self._emoji("⏱️", "[TIME]")
            print(f"\n{clock_emoji}  Time Distribution:")
            print(f"   0-7 DTE: {oi_detail.get('oi_0_7_days_percent', 0):.1f}% | "
                  f"8-21 DTE: {oi_detail.get('oi_8_21_days_percent', 0):.1f}% | "
                  f"22-35 DTE: {oi_detail.get('oi_22_35_days_percent', 0):.1f}% | "
                  f"36-60 DTE: {oi_detail.get('oi_36_60_days_percent', 0):.1f}%")

        # OI Timing Context (Smart Money vs Retail)
        if timing:
            brain_emoji = self._emoji("🧠", "[TIMING]")
            print(f"\n{brain_emoji} OI Timing Context (Smart Money vs Retail):")
            print(f"   {'Strike':<8}{'Type':<6}{'Exp':<12}{'OI':<10}{'Built':<12}{'@Price':<10}{'Positioning Type':<50}{'Days':<6}")
            print(f"   {'-'*110}")
            for t in timing[:5]:  # Top 5
                print(f"   ${t.get('strike', 0):<7}{t.get('option_type', 'N/A'):<6}{t.get('expiration_date', 'N/A'):<12}"
                      f"{t.get('open_interest', 0):<10,}{t.get('oi_build_start_date', 'N/A'):<12}"
                      f"${t.get('oi_build_start_price', 0):<9.2f}{t.get('positioning_type', 'N/A'):<50}"
                      f"{t.get('oi_build_days_since', 0):<6}")

        # Volume Profile Analysis (from salvaged daily_analysis tool)
        try:
            # Import volume profile calculator
            sys.path.insert(0, str(Path(__file__).parent.parent / 'tools'))
            from volume_profile_calculator import calculate_volume_profile

            volume_emoji = self._emoji("📊", "[VOLUME]")
            print(f"\n{volume_emoji} Volume Profile Analysis (60-day):")

            # Calculate volume profile
            vp_result = calculate_volume_profile(
                self.conn,
                symbol,
                trade_date=overview.get('trade_date'),
                current_price=overview.get('close_price')
            )

            if vp_result.get('status') == 'success':
                poc = vp_result['point_of_control']
                va = vp_result['value_area']
                current_ctx = vp_result['current_price_context']
                nearest = vp_result['nearest_zones']

                print(f"   Current Price: ${current_ctx['current_price']:.2f} ({current_ctx['position'].replace('_', ' ').upper()})")
                print(f"   Distance from POC: {current_ctx['distance_from_poc']:+.2f}%")
                print(f"")
                print(f"   Point of Control (POC): ${poc['price']:.2f} - Strongest support/resistance")
                print(f"   Value Area: ${va['low']:.2f} - ${va['high']:.2f} (Fair value range with {va['volume_coverage_percent']:.1f}% of volume)")
                print(f"")

                # High Volume Nodes (price magnets)
                if vp_result.get('high_volume_nodes'):
                    print(f"   High Volume Nodes (Top 3 Price Magnets):")
                    for i, hvn in enumerate(vp_result['high_volume_nodes'][:3], 1):
                        print(f"      #{i}: ${hvn['price']:.2f} - {hvn['strength'].upper()} node")

                # Nearest trading levels
                print(f"")
                if nearest.get('hvn_above'):
                    print(f"   Next Resistance (HVN): ${nearest['hvn_above']['price']:.2f}")
                if nearest.get('hvn_below'):
                    print(f"   Next Support (HVN): ${nearest['hvn_below']['price']:.2f}")

            else:
                print(f"   Volume profile calculation unavailable: {vp_result.get('note', 'Unknown error')}")

        except Exception as e:
            print(f"   Volume profile calculation failed: {str(e)}")

        print(f"\n{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Morning Views - Daily Options Watchlist',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python morning_views.py                    # Show today's watchlist
  python morning_views.py --symbol AAL       # Deep dive on AAL
  python morning_views.py --limit 10         # Show top 10 only
  python morning_views.py --config custom.json  # Use custom config
        """
    )

    parser.add_argument('--symbol', help='Show detailed analysis for specific symbol')
    parser.add_argument('--limit', type=int, help='Number of symbols to show in watchlist')
    parser.add_argument('--config', default='morning_view/config.json', help='Path to config file')
    parser.add_argument('--email', action='store_true', help='Email watchlist as .docx attachment')

    # Phase 2: 4-option comparison feature
    parser.add_argument('--compare', help='Symbol for 4-option comparison (e.g., AAL)')
    parser.add_argument('--strikes', help='Two strikes comma-separated (e.g., "11,12")')
    parser.add_argument('--exp', help='Two expirations comma-separated (e.g., "10/10,10/24")')

    args = parser.parse_args()

    # Initialize
    mv = MorningViews(config_path=args.config)
    mv.args = args  # Store args for email flag access

    # Execute with proper cleanup (2025-12-16 fix)
    try:
        if args.compare:
            # Phase 2: 4-option comparison feature
            mv.show_option_comparison(args.compare.upper(), args.strikes, args.exp)
        elif args.symbol:
            mv.show_symbol_detail(args.symbol.upper())
        else:
            mv.show_watchlist(limit=args.limit)
    finally:
        # CRITICAL: Close database connection to prevent file handle leaks
        # Without this, connection remains open and blocks query database sync
        mv.close()

if __name__ == "__main__":
    main()
