#!/usr/bin/env python3
"""
Morning Views TUI - Database Helper Module

Provides query functions for the TUI to access Morning Views data.
Read queries target datalake_query.db (read-only).
Write queries target datalake.db (for watchlist persistence).
"""

import sqlite3
import logging
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class MorningViewsData:
    """Database query helper for Morning Views TUI"""

    def __init__(self, db_path: str = None):
        """
        Initialize database paths (connections opened per-query).

        Args:
            db_path: Path to read database (defaults to datalake_query.db)
        """
        project_root = Path(__file__).parent.parent

        if db_path is None:
            # Default to query database (read-only)
            db_path = project_root / 'data' / 'datalake_query.db'

        self.db_path = str(db_path)

        # Write database for watchlist persistence (always datalake.db)
        self.write_db_path = str(project_root / 'data' / 'datalake.db')

        # Verify read database exists
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        # Verify write database exists
        if not Path(self.write_db_path).exists():
            raise FileNotFoundError(f"Write database not found: {self.write_db_path}")

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Load tradeable filter config
        config_path = project_root / 'config.json'
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                filter_config = config.get('tradeable_filter', {})
                self.max_underlying_price = filter_config.get('max_underlying_price', 60.0)
                self.min_open_interest = filter_config.get('min_open_interest', 500)
        except FileNotFoundError:
            self.logger.warning(f"Config file not found at {config_path}, using default tradeable filter values")
            self.max_underlying_price = 60.0
            self.min_open_interest = 500
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file {config_path}: {e}")
            self.logger.warning("Using default tradeable filter values due to config error")
            self.max_underlying_price = 60.0
            self.min_open_interest = 500
        except (KeyError, TypeError) as e:
            self.logger.warning(f"Config file structure issue: {e}. Using default tradeable filter values")
            self.max_underlying_price = 60.0
            self.min_open_interest = 500

    def _get_connection(self):
        """
        Get a fresh read database connection (context manager pattern)

        Respects sync lock file to avoid WinError 32 during database sync operations.
        If sync is in progress, waits briefly and retries (2025-12-16 Batch Fix).
        """
        # Check for sync lock file (coordination with db_backup.py sync)
        project_root = Path(__file__).parent.parent
        sync_lock_file = project_root / 'data' / '.datalake_query_sync_in_progress'

        max_retries = 3
        retry_delay = 2.0  # seconds

        for attempt in range(max_retries):
            if not sync_lock_file.exists():
                # No sync in progress - safe to open connection
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                return conn

            # Sync in progress - wait and retry
            if attempt < max_retries - 1:
                self.logger.debug(f"Database sync in progress, waiting {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                # Final attempt - log warning but continue (graceful degradation)
                self.logger.warning(f"Database sync still in progress after {max_retries} attempts, proceeding anyway")
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                return conn

    def _get_write_connection(self):
        """Get a fresh write database connection for watchlist operations"""
        conn = sqlite3.connect(self.write_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """Convert sqlite3.Row to dictionary"""
        return dict(row) if row else {}

    def _rows_to_dicts(self, rows: List[sqlite3.Row]) -> List[Dict]:
        """Convert list of sqlite3.Row to list of dictionaries"""
        return [self._row_to_dict(row) for row in rows]

    # ========== Discovery & Watchlist Queries ==========

    def get_discovery(self, limit: int = None) -> List[Dict]:
        """
        Get discovery feed (all symbols meeting triggers, sorted by temporal relevance).

        Args:
            limit: Optional limit on number of symbols (default None = show all)

        Returns:
            List of dicts with discovery data
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if limit is not None:
                cursor.execute("""
                    SELECT
                        symbol,
                        close_price,
                        price_change_5d_pct,
                        confluence_score,
                        direction_bias,
                        conviction_level,
                        primary_signal,
                        active_alert_count,
                        new_alert_count,
                        days_since_last_alert,
                        recent_alert_count_5d,
                        earnings_days_ahead,
                        earnings_alert,
                        exp_move_pct,
                        hist_move_pct,
                        diff_move_pct,
                        earnings_play_signal,
                        news_sentiment,
                        news_sentiment_avg,
                        volume_surge_factor,
                        put_call_ratio,
                        total_open_interest,
                        market_direction,
                        market_regime,
                        sector,
                        industry,
                        trigger_flow_alert,
                        trigger_earnings_play
                    FROM v_morning_discovery
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT
                        symbol,
                        close_price,
                        price_change_5d_pct,
                        confluence_score,
                        direction_bias,
                        conviction_level,
                        primary_signal,
                        active_alert_count,
                        new_alert_count,
                        days_since_last_alert,
                        recent_alert_count_5d,
                        earnings_days_ahead,
                        earnings_alert,
                        exp_move_pct,
                        hist_move_pct,
                        diff_move_pct,
                        earnings_play_signal,
                        news_sentiment,
                        news_sentiment_avg,
                        volume_surge_factor,
                        put_call_ratio,
                        total_open_interest,
                        market_direction,
                        market_regime,
                        sector,
                        industry,
                        trigger_flow_alert,
                        trigger_earnings_play
                    FROM v_morning_discovery
                """)

            return self._rows_to_dicts(cursor.fetchall())

    def get_my_watchlist(self, sort_mode: str = 'relevance') -> List[Dict]:
        """
        Get user's persistent watchlist with current trigger context.

        **Database Target:** WRITE database (datalake.db)
        - User watchlist is stored in production database for persistence
        - This is a READ operation on the write database

        Args:
            sort_mode: Sort order - 'relevance', 'date_added', or 'alphabetical' (default 'relevance')

        Returns:
            List of dicts with watchlist data including trigger status
        """
        # Use write connection to read watchlist (it's stored in datalake.db)
        with self._get_write_connection() as conn:
            cursor = conn.cursor()

            # Determine sort order
            if sort_mode == 'date_added':
                order_clause = "ORDER BY uw.added_date DESC"
            elif sort_mode == 'alphabetical':
                order_clause = "ORDER BY uw.symbol ASC"
            else:  # relevance (default)
                order_clause = """
                ORDER BY
                    (COALESCE(opts.new_alert_count, 0) * 3 +
                     COALESCE(opts.active_alert_count, 0) * 2 +
                     COALESCE(ABS(e.move_difference_pct), 0)) DESC
                """

            query = f"""
                SELECT
                    uw.symbol,
                    uw.added_date,
                    uw.added_reason,
                    uw.user_notes,
                    uw.priority,
                    s.close_price,
                    COALESCE(opts.active_alert_count, 0) as active_alert_count,
                    COALESCE(opts.new_alert_count, 0) as new_alert_count,
                    COALESCE(opts.days_since_last_alert, 999) as days_since_last_alert,
                    COALESCE(opts.alert_count_5d, 0) as recent_alert_count_5d,
                    e.earnings_days_ahead,
                    e.earnings_alert,
                    e.move_difference_pct,
                    CASE WHEN COALESCE(opts.active_alert_count, 0) > 0 THEN 1 ELSE 0 END as trigger_flow_alert,
                    CASE WHEN e.earnings_alert = 1 THEN 1 ELSE 0 END as trigger_earnings_play,
                    (COALESCE(opts.new_alert_count, 0) * 3 +
                     COALESCE(opts.active_alert_count, 0) * 2 +
                     COALESCE(ABS(e.move_difference_pct), 0)) as relevance_score
                FROM user_watchlist uw
                LEFT JOIN option_symbol_summary s
                    ON uw.symbol = s.symbol
                    AND s.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary WHERE trade_date < (SELECT MAX(trade_date) FROM option_symbol_summary))
                LEFT JOIN flow_symbol_summary opts
                    ON uw.symbol = opts.symbol
                    AND opts.trade_date = (SELECT MAX(trade_date) FROM flow_symbol_summary)
                LEFT JOIN earnings_upcoming e
                    ON uw.symbol = e.symbol
                WHERE uw.removed_date IS NULL
                {order_clause}
            """

            cursor.execute(query)
            return self._rows_to_dicts(cursor.fetchall())

    def add_to_watchlist(self, symbol: str, added_reason: str = None) -> bool:
        """
        Add symbol to user's watchlist.

        **Database Target:** WRITE database (datalake.db)
        - Writes directly to production database for persistence

        Args:
            symbol: Stock ticker symbol
            added_reason: Optional reason for adding (e.g., "FLOW_ALERT + EARNINGS_PLAY")

        Returns:
            True on success, False on failure
        """
        try:
            with self._get_write_connection() as conn:
                cursor = conn.cursor()

                # Check if symbol already exists (including removed ones)
                cursor.execute("""
                    SELECT removed_date FROM user_watchlist WHERE symbol = ?
                """, (symbol,))

                existing = cursor.fetchone()

                if existing:
                    # Symbol exists - if removed, un-remove it; if active, nothing to do
                    if existing['removed_date'] is not None:
                        cursor.execute("""
                            UPDATE user_watchlist
                            SET removed_date = NULL, added_date = ?, added_reason = ?
                            WHERE symbol = ?
                        """, (datetime.now().date().isoformat(), added_reason, symbol))
                        conn.commit()
                        self.logger.info(f"Re-added {symbol} to watchlist (was previously removed)")
                        return True
                    else:
                        # Already on watchlist
                        self.logger.info(f"{symbol} already on watchlist")
                        return True
                else:
                    # New symbol - insert
                    cursor.execute("""
                        INSERT INTO user_watchlist (symbol, added_date, added_reason)
                        VALUES (?, ?, ?)
                    """, (symbol, datetime.now().date().isoformat(), added_reason))
                    conn.commit()
                    self.logger.info(f"Added {symbol} to watchlist")
                    return True

        except sqlite3.Error as e:
            self.logger.error(f"Failed to add {symbol} to watchlist: {e}")
            return False

    def remove_from_watchlist(self, symbol: str) -> bool:
        """
        Remove symbol from user's watchlist (soft delete).

        **Database Target:** WRITE database (datalake.db)
        - Writes directly to production database for persistence

        Args:
            symbol: Stock ticker symbol

        Returns:
            True on success, False on failure
        """
        try:
            with self._get_write_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE user_watchlist
                    SET removed_date = ?
                    WHERE symbol = ? AND removed_date IS NULL
                """, (datetime.now().date().isoformat(), symbol))

                conn.commit()

                if cursor.rowcount > 0:
                    self.logger.info(f"Removed {symbol} from watchlist")
                    return True
                else:
                    self.logger.warning(f"{symbol} not found on watchlist (or already removed)")
                    return False

        except sqlite3.Error as e:
            self.logger.error(f"Failed to remove {symbol} from watchlist: {e}")
            return False

    def is_on_watchlist(self, symbol: str) -> bool:
        """
        Check if symbol is on user's watchlist.

        **Database Target:** WRITE database (datalake.db)
        - User watchlist is stored in production database for persistence
        - This is a READ operation on the write database

        Args:
            symbol: Stock ticker symbol

        Returns:
            True if on watchlist, False otherwise
        """
        # Use write connection to read watchlist (it's stored in datalake.db)
        with self._get_write_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM user_watchlist
                WHERE symbol = ? AND removed_date IS NULL
            """, (symbol,))

            return cursor.fetchone() is not None


    def get_market_context(self) -> Dict:
        """
        Get current market context (direction, regime).

        Returns:
            Dict with market_direction and market_regime
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT market_direction, market_regime
                FROM v_morning_discovery
                LIMIT 1
            """)

            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
            else:
                return {'market_direction': 'Unknown', 'market_regime': 'Unknown'}

    # ========== Symbol Detail Queries ==========

    def get_symbol_overview(self, symbol: str) -> Optional[Dict]:
        """
        Get overview data for a specific symbol from discovery feed.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with symbol overview data, or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM v_morning_discovery
                WHERE symbol = ?
            """, (symbol,))

            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

    def get_oi_distribution(self, symbol: str) -> Optional[Dict]:
        """
        Get OI distribution details for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with OI distribution data, or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM v_symbol_oi_detail
                WHERE symbol = ?
            """, (symbol,))

            row = cursor.fetchone()
            return self._row_to_dict(row) if row else None

    def get_oi_timing(self, symbol: str, limit: int = 10) -> List[Dict]:
        """
        Get OI timing analysis (smart money vs retail) for a symbol.

        Prioritizes contracts with flow alerts (shows institutional activity even if OI=0 now),
        then sorts by highest OI to show where positions are concentrated.

        Args:
            symbol: Stock ticker symbol
            limit: Number of contracts to return (default 10)

        Returns:
            List of dicts with OI timing data for top contracts
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    v.contract_hash,
                    v.symbol,
                    v.strike,
                    v.option_type,
                    v.expiration_date,
                    v.open_interest,
                    v.dte,
                    v.oi_build_start_date,
                    v.oi_build_start_price,
                    v.current_price,
                    v.iv,
                    v.iv_percentile,
                    v.positioning_type,
                    v.oi_build_days_since,
                    v.oi_build_price_move_pct,
                    -- Flag if this contract has recent flow alerts
                    CASE WHEN EXISTS (
                        SELECT 1 FROM flow_alerts fa
                        WHERE fa.symbol = v.symbol
                          AND fa.strike = v.strike
                          AND fa.option_type = v.option_type
                          AND fa.expiration_date = v.expiration_date
                          AND fa.trade_date >= DATE('now', '-14 days')
                    ) THEN 1 ELSE 0 END as has_flow_alert
                FROM v_oi_timing_context v
                WHERE v.symbol = ?
                ORDER BY
                    has_flow_alert DESC,  -- Flow alerts first (institutional activity)
                    v.open_interest DESC, -- Then highest OI (current positioning)
                    v.expiration_date ASC -- Then nearest expiration
                LIMIT ?
            """, (symbol, limit))

            return self._rows_to_dicts(cursor.fetchall())

    def get_contract_history(self, contract_hash: str) -> List[Dict]:
        """
        Get historical data for a specific contract.

        Args:
            contract_hash: Unique contract identifier

        Returns:
            List of dicts with daily OI/volume/IV history ordered by date (oldest first)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    trade_date,
                    open_interest,
                    oi_change,
                    oi_change_pct,
                    oi_change_1d,
                    oi_change_5d,
                    oi_momentum_5d,
                    volume,
                    volume_avg_5d,
                    volume_ratio_5d,
                    iv,
                    iv_change_1d,
                    iv_change_5d,
                    iv_percentile_20day,
                    underlying_price,
                    delta,
                    gamma,
                    theta,
                    vega,
                    dte,
                    moneyness,
                    build_pattern,
                    building_unwinding,
                    oi_build_start_date,
                    oi_build_start_price
                FROM option_contracts
                WHERE contract_hash = ?
                ORDER BY trade_date ASC
            """, (contract_hash,))

            return self._rows_to_dicts(cursor.fetchall())

    def get_option_comparison(self, symbol: str, option_type: str = 'CALL',
                             min_dte: int = 7, max_dte: int = 60) -> List[Dict]:
        """
        Get option contracts for comparison.

        Args:
            symbol: Stock ticker symbol
            option_type: 'CALL' or 'PUT' (default CALL)
            min_dte: Minimum days to expiration (default 7)
            max_dte: Maximum days to expiration (default 60)

        Returns:
            List of dicts with option comparison data
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    contract_hash,
                    symbol,
                    strike,
                    expiration_date,
                    option_type,
                    dte,
                    moneyness,
                    last_price,
                    underlying_price,
                    delta,
                    gamma,
                    theta,
                    vega,
                    IV as iv,
                    iv_percentile,
                    open_interest,
                    volume,
                    breakeven_price,
                    breakeven_move_pct,
                    delta_per_dollar,
                    in_gamma_zone,
                    theta_decay_dollars,
                    vega_dollars_per_iv_point,
                    intrinsic_value,
                    extrinsic_value,
                    avg_bid_ask_spread_pct
                FROM v_option_comparison
                WHERE symbol = ?
                  AND option_type = ?
                  AND dte BETWEEN ? AND ?
                ORDER BY expiration_date ASC, strike ASC
            """, (symbol, option_type, min_dte, max_dte))

            return self._rows_to_dicts(cursor.fetchall())

    # ========== Search Queries ==========

    def search_symbol(self, search_term: str) -> List[Dict]:
        """
        Search for symbols matching search term.

        Args:
            search_term: Partial symbol or company name

        Returns:
            List of matching symbols with basic info
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            search_pattern = f"%{search_term.upper()}%"

            cursor.execute("""
                SELECT
                    symbol,
                    close_price,
                    confluence_score,
                    direction_bias,
                    primary_signal
                FROM v_morning_discovery
                WHERE symbol LIKE ?
                ORDER BY confluence_score DESC
            """, (search_pattern,))

            return self._rows_to_dicts(cursor.fetchall())

    # ========== Earnings Calendar Queries ==========

    def get_earnings_calendar(self, days_ahead: int = 10, tradeable_only: bool = True, end_date: str = None) -> Dict[str, List[Dict]]:
        """
        Get earnings grouped by date for specified date range.
        Optionally filters to tradeable symbols using config.json tradeable_filter values.

        Args:
            days_ahead: Number of days ahead (ignored if end_date provided)
            tradeable_only: If True, filter using config tradeable_filter (default True)
            end_date: Optional end date (YYYY-MM-DD) to fetch up to

        Returns:
            Dict mapping date strings to list of earnings dicts
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build WHERE clause based on filter
            if tradeable_only:
                filter_clause = f"""
                    AND hp.close_price <= {self.max_underlying_price}
                    AND os.total_open_interest >= {self.min_open_interest}
                """
            else:
                filter_clause = ""

            # Use end_date if provided, otherwise calculate from days_ahead
            if end_date:
                date_filter = f"AND e.earnings_date <= '{end_date}'"
            else:
                date_filter = f"AND e.earnings_date <= DATE('now', '+{days_ahead + 5} days')"

            cursor.execute(f"""
                SELECT
                    e.symbol,
                    e.earnings_date,
                    e.earnings_time,
                    e.earnings_days_ahead,
                    e.straddle_expected_move_pct,
                    e.historical_avg_move_pct,
                    e.move_difference_pct,
                    e.earnings_play_signal,
                    e.earnings_alert,
                    sm.sector,
                    sm.industry,
                    hp.close_price,
                    os.total_open_interest
                FROM earnings_upcoming e
                LEFT JOIN symbol_metadata sm ON e.symbol = sm.symbol
                LEFT JOIN historical_prices hp
                    ON e.symbol = hp.symbol
                    AND hp.trade_date = (SELECT MAX(trade_date) FROM historical_prices WHERE symbol = e.symbol)
                LEFT JOIN option_symbol_summary os
                    ON e.symbol = os.symbol
                    AND os.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary WHERE symbol = e.symbol)
                WHERE e.earnings_date >= DATE('now')
                  {date_filter}
                  {filter_clause}
                ORDER BY e.earnings_date ASC, e.symbol ASC
            """)

            rows = cursor.fetchall()

            # Group by date
            earnings_by_date = {}
            for row in rows:
                date_str = row['earnings_date']
                if date_str not in earnings_by_date:
                    earnings_by_date[date_str] = []
                earnings_by_date[date_str].append(self._row_to_dict(row))

            return earnings_by_date

    # ========== Flow Alerts Queries ==========

    def get_flow_alerts(self, days_back: int = 14, symbol: str = None) -> List[Dict]:
        """
        Get recent flow alerts sorted by timestamp (newest first).
        Filters to tradeable symbols using config.json tradeable_filter values.

        Args:
            days_back: Number of days to look back (default 14 = 2 weeks)
            symbol: Optional symbol filter (default None = all symbols)

        Returns:
            List of dicts with flow alert data
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Build symbol filter clause
            if symbol:
                symbol_clause = "AND symbol = ?"
                params = (self.max_underlying_price, self.min_open_interest, days_back, symbol)
            else:
                symbol_clause = ""
                params = (self.max_underlying_price, self.min_open_interest, days_back)

            cursor.execute(f"""
                SELECT
                    trade_date,
                    symbol,
                    strike,
                    expiration_date,
                    option_type,
                    moneyness,
                    underlying_price,
                    volume,
                    open_interest,
                    iv,
                    last_price,
                    significance_score,
                    alert_timestamp
                FROM flow_alerts
                WHERE underlying_price <= ?
                  AND open_interest >= ?
                  AND trade_date >= DATE('now', '-' || ? || ' days')
                  {symbol_clause}
                ORDER BY alert_timestamp DESC
            """, params)

            return self._rows_to_dicts(cursor.fetchall())

    # ========== Utility Queries ==========

    def get_display_date(self) -> str:
        """
        Get the display date for current data.

        Returns:
            ISO date string (YYYY-MM-DD)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(trade_date)
                FROM option_symbol_summary
                WHERE trade_date < (SELECT MAX(trade_date) FROM option_symbol_summary)
            """)

            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
            else:
                return "No data"

    def get_latest_scan_time(self) -> Optional[str]:
        """
        Get timestamp of most recent Flow Monitor scan.

        Returns:
            Timestamp string (YYYY-MM-DD HH:MM:SS) or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(scan_timestamp)
                FROM flow_options_scans
            """)

            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
            else:
                return None

    def check_views_exist(self) -> bool:
        """
        Check if Morning Views SQL views exist in database.

        Returns:
            True if all views exist, False otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            required_views = [
                'v_morning_discovery',
                'v_symbol_oi_detail',
                'v_oi_timing_context',
                'v_option_comparison'
            ]

            for view_name in required_views:
                cursor.execute("""
                    SELECT name
                    FROM sqlite_master
                    WHERE type='view' AND name=?
                """, (view_name,))

                if not cursor.fetchone():
                    return False

            return True


# Singleton instance for convenience
_data_instance = None

def get_data() -> MorningViewsData:
    """
    Get singleton data instance.

    Returns:
        MorningViewsData instance
    """
    global _data_instance
    if _data_instance is None:
        _data_instance = MorningViewsData()
    return _data_instance
