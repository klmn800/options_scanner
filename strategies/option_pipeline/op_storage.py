#!/usr/bin/env python3
"""
Open Interest Delta Storage - Clean Version (oid_storage3.py)
-----------------------------------------------------------
Streamlined storage operations for Open Interest Delta (OID) system.
Manages database operations for OI data in oid.db with clean separation of concerns.

Responsibilities:
- Database connection management with basic retry logic
- OI data insertion and retrieval operations
- Symbol summary operations for rollup processing
- Data cleanup and retention management
- Table creation and schema management

Removed from original:
- Complex retry logic with exponential backoff
- Momentum calculations (moved to analyzer)
- Report generation (handled by health reporter)
- Database optimization settings (simplified)

Author: Ben (with assistance from Claude)
Date: 2025-08-20
Version: 3.0 - Clean rewrite focused on storage operations only
"""

import sqlite3
import logging
import time
import os
import sys
from tools.decimal_formatter import clean_database_row, format_ratio, format_percentage, format_greek, format_score, format_price
from tools.autofix import queue_error, handle_error
from datetime import timedelta, datetime

# Get timezone utilities
def get_project_root():
    """Get the root directory of the project"""
    current_file = os.path.abspath(__file__)    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

project_root = get_project_root()
tools_dir = os.path.join(project_root, 'tools')

if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import eastern_isoformat, eastern_date_string


class OIDStorage:
    def __init__(self, config):
        """Initialize storage with OID configuration
        
        Args:
            config: OIDConfig instance with database path and settings
        """
        self.database_path = config.database_path
        self.retention_days = config.get_storage_params().get('retention_days', 365)
        logging.debug("Storage initialized with database: {}".format(self.database_path))
        
        # Ensure table exists
        self._ensure_tables_exist()
        
    def _ensure_tables_exist(self):
        """Create option_contracts table if it doesn't exist"""
        create_table_sql = '''
            CREATE TABLE IF NOT EXISTS option_contracts (
                contract_hash TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strike REAL NOT NULL,
                expiration_date TEXT NOT NULL,
                option_type TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open_interest INTEGER NOT NULL,
                oi_momentum_5d REAL,
                oi_change_1d INTEGER,
                oi_change_5d INTEGER,
                oi_change_10d INTEGER,
                oi_change_pct_1d REAL,
                oi_change_pct_5d REAL,
                oi_change_pct_10d REAL,
                build_pattern TEXT,
                volume INTEGER DEFAULT 0,
                building_unwinding TEXT DEFAULT 'STABLE',
                created_at TEXT NOT NULL,
                PRIMARY KEY (contract_hash, trade_date)
            )
        '''
        
        create_symbol_summary_sql = '''
            CREATE TABLE IF NOT EXISTS option_symbol_summary (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                total_open_interest INTEGER,
                total_call_oi INTEGER,
                total_put_oi INTEGER,
                put_call_ratio REAL,
                oi_balance_text TEXT,
                top_call_strike REAL,
                top_call_expiration TEXT,
                top_call_oi INTEGER,
                top_call_pct_of_total REAL,
                top_call_display TEXT,
                top_put_strike REAL,
                top_put_expiration TEXT,
                top_put_oi INTEGER,
                top_put_pct_of_total REAL,
                top_put_display TEXT,
                building_contracts_count INTEGER,
                unwinding_contracts_count INTEGER,
                analysis_timestamp TEXT,
                processing_duration_ms INTEGER,
                close_price REAL,
                option_volume INTEGER,
                call_volume INTEGER,
                put_volume INTEGER,
                volume_put_call_ratio REAL,
                call_iv_avg REAL,
                put_iv_avg REAL,
                iv_skew REAL,
                call_iv_weighted REAL,
                put_iv_weighted REAL,
                symbol_iv_percentile_30d REAL,
                total_delta_exposure REAL,
                call_delta_exposure REAL,
                put_delta_exposure REAL,
                net_delta_exposure REAL,
                total_gamma_exposure REAL,
                max_gamma_strike REAL,
                total_theta_exposure REAL,
                total_vega_exposure REAL,
                call_vega_exposure REAL,
                put_vega_exposure REAL,
                net_vega_exposure REAL,
                deep_itm_call_oi INTEGER,
                itm_call_oi INTEGER,
                atm_call_oi INTEGER,
                otm_call_oi INTEGER,
                deep_otm_call_oi INTEGER,
                deep_itm_put_oi INTEGER,
                itm_put_oi INTEGER,
                atm_put_oi INTEGER,
                otm_put_oi INTEGER,
                deep_otm_put_oi INTEGER,
                deep_itm_call_pct REAL,
                itm_call_pct REAL,
                atm_call_pct REAL,
                otm_call_pct REAL,
                deep_otm_call_pct REAL,
                deep_itm_put_pct REAL,
                itm_put_pct REAL,
                atm_put_pct REAL,
                otm_put_pct REAL,
                deep_otm_put_pct REAL,
                contracts_with_data INTEGER,
                avg_bid_ask_spread_pct REAL,
                oi_0_7_days REAL,
                oi_8_21_days REAL,
                oi_22_35_days REAL,
                oi_36_60_days REAL,
                oi_0_7_days_percent REAL,
                oi_8_21_days_percent REAL,
                oi_22_35_days_percent REAL,
                oi_36_60_days_percent REAL,
                call_oi_0_7_days REAL,
                call_oi_8_21_days REAL,
                call_oi_22_35_days REAL,
                call_oi_36_60_days REAL,
                call_oi_0_7_days_percent REAL,
                call_oi_8_21_days_percent REAL,
                call_oi_22_35_days_percent REAL,
                call_oi_36_60_days_percent REAL,
                put_oi_0_7_days REAL,
                put_oi_8_21_days REAL,
                put_oi_22_35_days REAL,
                put_oi_36_60_days REAL,
                put_oi_0_7_days_percent REAL,
                put_oi_8_21_days_percent REAL,
                put_oi_22_35_days_percent REAL,
                put_oi_36_60_days_percent REAL,
                iv_front_month REAL,
                iv_30dte REAL,
                iv_45dte REAL,
                iv_60dte REAL,
                max_pain_by_friday REAL,
                PRIMARY KEY (symbol, trade_date)
            )
        '''
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(create_table_sql)
                cursor.execute(create_symbol_summary_sql)

                # Add new time series columns if they don't exist
                self._add_time_series_columns(cursor)

                logging.debug("OP: Tables ensured to exist")
        except Exception as e:
            logging.error("OP: Failed to create tables: {}".format(e))
            raise

    def _add_time_series_columns(self, cursor):
        """Add time series columns to option_contracts table if they don't exist"""

        # First, add last_price between option_type and trade_date
        alter_statements = [
            # Last price (placed between option_type and trade_date)
            "ALTER TABLE option_contracts ADD COLUMN last_price REAL",

            # Raw end-of-day data fields
            "ALTER TABLE option_contracts ADD COLUMN underlying_price REAL",
            "ALTER TABLE option_contracts ADD COLUMN dte INTEGER",
            "ALTER TABLE option_contracts ADD COLUMN moneyness TEXT",

            # Volume time series (after group_median_oi)
            "ALTER TABLE option_contracts ADD COLUMN volume_avg_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN volume_avg_20d REAL",
            "ALTER TABLE option_contracts ADD COLUMN volume_ratio_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN volume_ratio_20d REAL",
            "ALTER TABLE option_contracts ADD COLUMN volume_percentile_rank_20d REAL",
            "ALTER TABLE option_contracts ADD COLUMN volume_change_1d INTEGER",
            "ALTER TABLE option_contracts ADD COLUMN volume_change_5d INTEGER",
            "ALTER TABLE option_contracts ADD COLUMN volume_ratio_5d_change_1d REAL",

            # IMPLIED VOLATILITY TIME SERIES
            "ALTER TABLE option_contracts ADD COLUMN iv REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_change_1d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_change_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_change_20d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_change_pct_1d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_change_pct_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_change_pct_20d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_avg_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_avg_20d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_percentile_20day REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_percentile_rank_20d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_momentum_1d REAL",
            "ALTER TABLE option_contracts ADD COLUMN iv_momentum_5d REAL",

            # GREEKS TIME SERIES
            "ALTER TABLE option_contracts ADD COLUMN delta REAL",
            "ALTER TABLE option_contracts ADD COLUMN delta_change_1d REAL",
            "ALTER TABLE option_contracts ADD COLUMN delta_change_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN delta_momentum REAL",
            "ALTER TABLE option_contracts ADD COLUMN delta_acceleration REAL",

            "ALTER TABLE option_contracts ADD COLUMN gamma REAL",
            "ALTER TABLE option_contracts ADD COLUMN gamma_change_1d REAL",
            "ALTER TABLE option_contracts ADD COLUMN gamma_change_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN gamma_momentum REAL",

            "ALTER TABLE option_contracts ADD COLUMN theta REAL",
            "ALTER TABLE option_contracts ADD COLUMN theta_change_1d REAL",
            "ALTER TABLE option_contracts ADD COLUMN theta_change_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN theta_momentum REAL",
            "ALTER TABLE option_contracts ADD COLUMN theta_avg_5d REAL",
            "ALTER TABLE option_contracts ADD COLUMN theta_daily_change_avg_5d REAL",

            "ALTER TABLE option_contracts ADD COLUMN vega REAL",
            "ALTER TABLE option_contracts ADD COLUMN vega_change_1d REAL",
            "ALTER TABLE option_contracts ADD COLUMN vega_change_5d REAL",

            # OI_SYMBOL_SUMMARY EXPANSIONS
            # Stock data
            "ALTER TABLE option_symbol_summary ADD COLUMN close_price REAL",

            # Volume metrics
            "ALTER TABLE option_symbol_summary ADD COLUMN option_volume INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN call_volume INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN put_volume INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN volume_put_call_ratio REAL",

            # IV summary metrics
            "ALTER TABLE option_symbol_summary ADD COLUMN call_iv_avg REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN put_iv_avg REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN iv_skew REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN call_iv_weighted REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN put_iv_weighted REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN symbol_iv_percentile_30d REAL",

            # Greeks exposure - Delta
            "ALTER TABLE option_symbol_summary ADD COLUMN total_delta_exposure REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN call_delta_exposure REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN put_delta_exposure REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN net_delta_exposure REAL",

            # Greeks exposure - Gamma
            "ALTER TABLE option_symbol_summary ADD COLUMN total_gamma_exposure REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN max_gamma_strike REAL",

            # Greeks exposure - Theta
            "ALTER TABLE option_symbol_summary ADD COLUMN total_theta_exposure REAL",

            # Greeks exposure - Vega
            "ALTER TABLE option_symbol_summary ADD COLUMN total_vega_exposure REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN call_vega_exposure REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN put_vega_exposure REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN net_vega_exposure REAL",

            # Moneyness distribution - Call OI
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_itm_call_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN itm_call_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN atm_call_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN otm_call_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_otm_call_oi INTEGER",

            # Moneyness distribution - Put OI
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_itm_put_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN itm_put_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN atm_put_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN otm_put_oi INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_otm_put_oi INTEGER",

            # Moneyness distribution - Call percentages
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_itm_call_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN itm_call_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN atm_call_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN otm_call_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_otm_call_pct REAL",

            # Moneyness distribution - Put percentages
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_itm_put_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN itm_put_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN atm_put_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN otm_put_pct REAL",
            "ALTER TABLE option_symbol_summary ADD COLUMN deep_otm_put_pct REAL",

            # Quality metrics
            "ALTER TABLE option_symbol_summary ADD COLUMN contracts_with_data INTEGER",
            "ALTER TABLE option_symbol_summary ADD COLUMN avg_bid_ask_spread_pct REAL"
        ]

        for alter_sql in alter_statements:
            try:
                cursor.execute(alter_sql)
            except sqlite3.OperationalError as e:
                # Column already exists - this is expected on subsequent runs
                if "duplicate column name" in str(e).lower():
                    continue
                else:
                    logging.warning("OP: Failed to add column: {}".format(e))

    def get_connection(self):
        """Return database connection with basic WAL mode settings
        
        Returns:
            sqlite3.Connection with WAL mode enabled
        """
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        return conn
    
    def _execute_with_retry(self, operation, max_retries=3):
        """Execute database operation with simple retry logic

        Args:
            operation: Function that takes a connection and returns result
            max_retries: Maximum number of retry attempts

        Returns:
            Operation result or False on failure
        """
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    return operation(conn)

            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                    wait_time = 0.1 * (attempt + 1)  # Simple linear backoff
                    logging.warning("OP: Database locked, retrying in {}s (attempt {}/{})".format(
                        wait_time, attempt + 1, max_retries))
                    time.sleep(wait_time)
                    continue
                else:
                    logging.error("OP: Database error: {}".format(e))
                    return False
            except sqlite3.DatabaseError as e:
                error_msg = str(e).lower()
                if "malformed" in error_msg or "corrupt" in error_msg:
                    # Database corruption — emergency stop the entire system.
                    # handle_error(CRITICAL) queues the error, spawns an immediate
                    # autofix session, then calls sys.exit(1). This prevents:
                    #   - Hundreds of doomed retry attempts
                    #   - Downstream backup/sync from overwriting good copies
                    logging.critical("OP: DATABASE CORRUPTION DETECTED: {}".format(e))
                    logging.critical("OP: Emergency stop. Run: python data/health/repair_option_contracts.py")
                    handle_error(
                        error_type='op_database_corruption',
                        context={
                            'exception_type': type(e).__name__,
                            'error_message': str(e),
                            'database_path': self.database_path
                        },
                        severity='CRITICAL'
                    )
                    # handle_error calls sys.exit(1) — never reaches here
                # Other DatabaseError — queue for batch review
                queue_error(
                    error_type='op_database_operation_failed',
                    context={
                        'exception_type': type(e).__name__,
                        'error_message': str(e),
                        'attempt': attempt + 1,
                        'max_retries': max_retries
                    },
                    severity='ERROR'
                )
                return False
            except Exception as e:
                queue_error(
                    error_type='op_database_operation_failed',
                    context={
                        'exception_type': type(e).__name__,
                        'error_message': str(e),
                        'attempt': attempt + 1,
                        'max_retries': max_retries
                    },
                    severity='ERROR'
                )
                return False

        logging.error("OP: Database operation failed after {} retries".format(max_retries))
        return False
    
    def insert_oi_snapshot(self, contract_data):
        """Insert single OI record with collector-only fields
        
        Args:
            contract_data: Dictionary with contract OI data from collector including:
                - contract_hash: Unique contract identifier  
                - symbol: Stock symbol
                - strike: Strike price
                - expiration_date: Option expiration date
                - option_type: CALL or PUT
                - open_interest: Current OI value
                - trade_date: Trading date (defaults to today)
                - volume: Trading volume (optional)
                - scan_timestamp: When data was collected
                - Other collector fields as needed
                
        Returns:
            bool: True if successful, False otherwise
        """
        if not contract_data:
            logging.warning("OP: No contract data to insert")
            return False
        
        def _insert_operation(conn):
            cursor = conn.cursor()
            
            # Extract required fields
            trade_date = contract_data.get('trade_date', eastern_date_string())
            contract_hash = contract_data.get('contract_hash')
            current_oi = contract_data.get('open_interest', 0)
            
            if not contract_hash:
                logging.warning("OP: Missing contract_hash in insert data")
                return False
            
            # Get previous day's OI for basic delta calculation
            prev_data = self._get_previous_oi_data(cursor, contract_hash, trade_date)

            # Calculate time series metrics (includes oi_change_1d, oi_change_pct_1d, build_pattern)
            time_series_metrics = self._calculate_time_series_metrics(cursor, contract_hash, trade_date, contract_data)

            # Extract OI change metrics from time series for building/unwinding
            oi_change_1d = time_series_metrics.get('oi_change_1d', 0)
            oi_change_pct_1d = time_series_metrics.get('oi_change_pct_1d', 0.0)

            # Determine building/unwinding status using new oi_change_1d
            building_unwinding = self._determine_oi_direction(oi_change_1d or 0, oi_change_pct_1d or 0.0)

            # Calculate moneyness if not provided
            underlying_price = contract_data.get('underlying_price', 0.0)

            # Calculate dte if not provided
            dte = contract_data.get('dte')
            if dte is None or dte == 0:
                try:
                    exp_date = datetime.strptime(contract_data.get('expiration_date', ''), '%Y-%m-%d').date()
                    trade_date_obj = datetime.strptime(trade_date, '%Y-%m-%d').date()
                    dte = (exp_date - trade_date_obj).days
                except (ValueError, TypeError):
                    dte = 0

            moneyness = contract_data.get('moneyness') or self._calculate_moneyness(
                contract_data.get('strike'),
                underlying_price,
                contract_data.get('option_type')
            )

            # Calculate bid/ask spread
            bid = contract_data.get('bid', 0.0)
            ask = contract_data.get('ask', 0.0)
            if bid > 0 and ask > 0 and ask > bid:
                midpoint = (bid + ask) / 2.0
                spread = ask - bid
                bid_ask_spread_pct = format_percentage((spread / midpoint) * 100) if midpoint > 0 else None
            else:
                bid_ask_spread_pct = None

            # INSERT with all fields including time series metrics
            insert_sql = '''
                INSERT OR REPLACE INTO option_contracts (
                    contract_hash, symbol, strike, expiration_date, option_type,
                    last_price, bid, ask, bid_ask_spread_pct, underlying_price, dte, moneyness,
                    trade_date, open_interest,
                    oi_build_start_date, oi_build_start_price, build_pattern,
                    building_unwinding, volume,

                    volume_avg_5d, volume_avg_20d, volume_ratio_5d, volume_ratio_20d,
                    volume_percentile_rank_20d, volume_change_1d, volume_change_5d, volume_ratio_5d_change_1d,

                    iv, iv_change_1d, iv_change_5d, iv_change_20d,
                    iv_change_pct_1d, iv_change_pct_5d, iv_change_pct_20d,
                    iv_avg_5d, iv_avg_20d, iv_percentile_20day,
                    iv_momentum_1d, iv_momentum_5d,

                    delta, delta_change_1d, delta_change_5d, delta_momentum, delta_acceleration,
                    gamma, gamma_change_1d, gamma_change_5d, gamma_momentum,
                    theta, theta_change_1d, theta_change_5d, theta_momentum, theta_avg_5d, theta_daily_change_avg_5d,
                    vega, vega_change_1d, vega_change_5d,

                    oi_change_1d, oi_change_5d, oi_change_10d,
                    oi_change_pct_1d, oi_change_pct_5d, oi_change_pct_10d,
                    oi_momentum_5d,

                    created_at,
                    iv_percentile_rank_20d
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''

            values = (
                contract_hash,
                contract_data.get('symbol'),
                contract_data.get('strike'),
                contract_data.get('expiration_date'),
                contract_data.get('option_type'),
                contract_data.get('last_price', 0.0),
                format_price(bid),
                format_price(ask),
                bid_ask_spread_pct,
                underlying_price,
                dte,
                moneyness,
                trade_date,
                current_oi,
                building_unwinding,
                contract_data.get('volume', 0),

                # Volume time series
                format_score(time_series_metrics.get('volume_avg_5d', 0.0)),
                format_score(time_series_metrics.get('volume_avg_20d', 0.0)),
                format_ratio(time_series_metrics.get('volume_ratio_5d', 0.0)),
                format_ratio(time_series_metrics.get('volume_ratio_20d', 0.0)),
                format_percentage(time_series_metrics.get('volume_percentile_rank_20d', 0.0)),
                time_series_metrics.get('volume_change_1d', 0),
                time_series_metrics.get('volume_change_5d', 0),
                format_ratio(time_series_metrics.get('volume_ratio_5d_change_1d', 0.0)),

                # IV time series
                contract_data.get('iv', 0.0),
                format_greek(time_series_metrics.get('iv_change_1d', 0.0)),
                format_greek(time_series_metrics.get('iv_change_5d', 0.0)),
                format_greek(time_series_metrics.get('iv_change_20d', 0.0)),
                format_percentage(time_series_metrics.get('iv_change_pct_1d', 0.0)),
                format_percentage(time_series_metrics.get('iv_change_pct_5d', 0.0)),
                format_percentage(time_series_metrics.get('iv_change_pct_20d', 0.0)),
                format_greek(time_series_metrics.get('iv_avg_5d', 0.0)),
                format_greek(time_series_metrics.get('iv_avg_20d', 0.0)),
                format_percentage(time_series_metrics.get('iv_percentile_20day', 0.0)),
                format_greek(time_series_metrics.get('iv_momentum_1d', 0.0)),
                format_greek(time_series_metrics.get('iv_momentum_5d', 0.0)),

                # Greeks time series (enforce decimal policy)
                format_greek(contract_data.get('delta', 0.0)),
                format_greek(time_series_metrics.get('delta_change_1d', 0.0)),
                format_greek(time_series_metrics.get('delta_change_5d', 0.0)),
                format_greek(time_series_metrics.get('delta_momentum', 0.0)),
                format_greek(time_series_metrics.get('delta_acceleration', 0.0)),

                format_greek(contract_data.get('gamma', 0.0)),
                format_greek(time_series_metrics.get('gamma_change_1d', 0.0)),
                format_greek(time_series_metrics.get('gamma_change_5d', 0.0)),
                format_greek(time_series_metrics.get('gamma_momentum', 0.0)),

                format_greek(contract_data.get('theta', 0.0)),
                format_greek(time_series_metrics.get('theta_change_1d', 0.0)),
                format_greek(time_series_metrics.get('theta_change_5d', 0.0)),
                format_greek(time_series_metrics.get('theta_momentum', 0.0)),
                format_greek(time_series_metrics.get('theta_avg_5d', 0.0)),
                format_greek(time_series_metrics.get('theta_daily_change_avg_5d', 0.0)),

                format_greek(contract_data.get('vega', 0.0)),
                format_greek(time_series_metrics.get('vega_change_1d', 0.0)),
                format_greek(time_series_metrics.get('vega_change_5d', 0.0)),

                # OI momentum time series
                time_series_metrics.get('oi_change_1d'),
                time_series_metrics.get('oi_change_5d'),
                time_series_metrics.get('oi_change_10d'),
                time_series_metrics.get('oi_change_pct_1d'),
                time_series_metrics.get('oi_change_pct_5d'),
                time_series_metrics.get('oi_change_pct_10d'),
                time_series_metrics.get('oi_momentum_5d'),

                time_series_metrics.get('build_pattern'),

                eastern_isoformat()
            )
            
            cursor.execute(insert_sql, values)
            logging.debug("OP: Inserted OI snapshot for contract {} on {}".format(contract_hash, trade_date))
            return True
        
        return self._execute_with_retry(_insert_operation)
    
    def bulk_insert_oi_snapshots(self, contracts_list, batch_size=5000):
        """Efficient bulk insertion of OI records with collector-only fields
        
        Args:
            contracts_list: List of contract dictionaries with OI data from collector
            batch_size: Number of records per transaction
            
        Returns:
            int: Number of records successfully inserted, -1 on failure
        """
        if not contracts_list:
            logging.warning("OP: No contracts data for bulk insert")
            return 0
        
        total_inserted = 0
        
        def _bulk_insert_operation(conn, batch):
            cursor = conn.cursor()
            
            # Prepare batch data with calculations
            prepared_batch = []
            for contract_data in batch:
                contract_hash = contract_data.get('contract_hash')
                if not contract_hash:
                    logging.warning("OP: Missing contract_hash in bulk data")
                    continue
                    
                trade_date = contract_data.get('trade_date', eastern_date_string())
                current_oi = contract_data.get('open_interest', 0)
                
                # Get previous data for deltas
                prev_data = self._get_previous_oi_data(cursor, contract_hash, trade_date)
                
                # Calculate metrics
                oi_change = current_oi - prev_data['prev_oi'] if prev_data['prev_oi'] is not None else 0
                oi_change_pct = format_percentage((oi_change / prev_data['prev_oi'] * 100) if prev_data['prev_oi'] and prev_data['prev_oi'] > 0 else 0.0)

                building_unwinding = self._determine_oi_direction(oi_change, oi_change_pct)

                # Calculate time series metrics (includes build_pattern)
                time_series_metrics = self._calculate_time_series_metrics(cursor, contract_hash, trade_date, contract_data)

                # Calculate moneyness if not provided
                underlying_price = contract_data.get('underlying_price', 0.0)

                # Calculate dte if not provided
                dte = contract_data.get('dte')
                if dte is None or dte == 0:
                    try:
                        exp_date = datetime.strptime(contract_data.get('expiration_date', ''), '%Y-%m-%d').date()
                        trade_date_obj = datetime.strptime(trade_date, '%Y-%m-%d').date()
                        dte = (exp_date - trade_date_obj).days
                    except (ValueError, TypeError):
                        dte = 0

                moneyness = contract_data.get('moneyness') or self._calculate_moneyness(
                    contract_data.get('strike'),
                    underlying_price,
                    contract_data.get('option_type')
                )

                # Calculate bid/ask spread
                bid = contract_data.get('bid', 0.0) or 0.0
                ask = contract_data.get('ask', 0.0) or 0.0
                if bid > 0 and ask > 0 and ask > bid:
                    midpoint = (bid + ask) / 2.0
                    spread = ask - bid
                    bid_ask_spread_pct = format_percentage((spread / midpoint) * 100) if midpoint > 0 else None
                else:
                    bid_ask_spread_pct = None

                # Include all fields including new time series metrics
                prepared_batch.append((
                    contract_hash,
                    contract_data.get('symbol'),
                    contract_data.get('strike'),
                    contract_data.get('expiration_date'),
                    contract_data.get('option_type'),
                    contract_data.get('last_price', 0.0),
                    format_price(bid),
                    format_price(ask),
                    bid_ask_spread_pct,
                    underlying_price,
                    dte,
                    moneyness,
                    trade_date,
                    current_oi,
                    time_series_metrics.get('oi_build_start_date'),
                    time_series_metrics.get('oi_build_start_price'),
                    time_series_metrics.get('build_pattern'),
                    building_unwinding,
                    contract_data.get('volume', 0),

                    # Volume time series
                    format_score(time_series_metrics.get('volume_avg_5d', 0.0)),
                    format_score(time_series_metrics.get('volume_avg_20d', 0.0)),
                    format_ratio(time_series_metrics.get('volume_ratio_5d', 0.0)),
                    format_ratio(time_series_metrics.get('volume_ratio_20d', 0.0)),
                    format_percentage(time_series_metrics.get('volume_percentile_rank_20d', 0.0)),
                    time_series_metrics.get('volume_change_1d', 0),
                    time_series_metrics.get('volume_change_5d', 0),
                    format_ratio(time_series_metrics.get('volume_ratio_5d_change_1d', 0.0)),

                    # IV time series
                    contract_data.get('iv', 0.0),
                    format_greek(time_series_metrics.get('iv_change_1d', 0.0)),
                    format_greek(time_series_metrics.get('iv_change_5d', 0.0)),
                    format_greek(time_series_metrics.get('iv_change_20d', 0.0)),
                    format_percentage(time_series_metrics.get('iv_change_pct_1d', 0.0)),
                    format_percentage(time_series_metrics.get('iv_change_pct_5d', 0.0)),
                    format_percentage(time_series_metrics.get('iv_change_pct_20d', 0.0)),
                    format_greek(time_series_metrics.get('iv_avg_5d', 0.0)),
                    format_greek(time_series_metrics.get('iv_avg_20d', 0.0)),
                    format_percentage(time_series_metrics.get('iv_percentile_20day', 0.0)),
                    format_greek(time_series_metrics.get('iv_momentum_1d', 0.0)),
                    format_greek(time_series_metrics.get('iv_momentum_5d', 0.0)),

                    # Greeks time series (enforce decimal policy)
                    format_greek(contract_data.get('delta', 0.0)),
                    format_greek(time_series_metrics.get('delta_change_1d', 0.0)),
                    format_greek(time_series_metrics.get('delta_change_5d', 0.0)),
                    format_greek(time_series_metrics.get('delta_momentum', 0.0)),
                    format_greek(time_series_metrics.get('delta_acceleration', 0.0)),

                    format_greek(contract_data.get('gamma', 0.0)),
                    format_greek(time_series_metrics.get('gamma_change_1d', 0.0)),
                    format_greek(time_series_metrics.get('gamma_change_5d', 0.0)),
                    format_greek(time_series_metrics.get('gamma_momentum', 0.0)),

                    format_greek(contract_data.get('theta', 0.0)),
                    format_greek(time_series_metrics.get('theta_change_1d', 0.0)),
                    format_greek(time_series_metrics.get('theta_change_5d', 0.0)),
                    format_greek(time_series_metrics.get('theta_momentum', 0.0)),
                    format_greek(time_series_metrics.get('theta_avg_5d', 0.0)),
                    format_greek(time_series_metrics.get('theta_daily_change_avg_5d', 0.0)),

                    format_greek(contract_data.get('vega', 0.0)),
                    format_greek(time_series_metrics.get('vega_change_1d', 0.0)),
                    format_greek(time_series_metrics.get('vega_change_5d', 0.0)),

                    # OI time series
                    time_series_metrics.get('oi_change_1d'),
                    time_series_metrics.get('oi_change_5d'),
                    time_series_metrics.get('oi_change_10d'),
                    time_series_metrics.get('oi_change_pct_1d'),
                    time_series_metrics.get('oi_change_pct_5d'),
                    time_series_metrics.get('oi_change_pct_10d'),
                    time_series_metrics.get('oi_momentum_5d'),

                    eastern_isoformat(),
                    format_percentage(time_series_metrics.get('iv_percentile_rank_20d', 0.0))
                ))

            # INSERT with all fields including time series metrics
            insert_sql = '''
                INSERT OR REPLACE INTO option_contracts (
                    contract_hash, symbol, strike, expiration_date, option_type,
                    last_price, bid, ask, bid_ask_spread_pct, underlying_price, dte, moneyness,
                    trade_date, open_interest,
                    oi_build_start_date, oi_build_start_price, build_pattern,
                    building_unwinding, volume,

                    volume_avg_5d, volume_avg_20d, volume_ratio_5d, volume_ratio_20d,
                    volume_percentile_rank_20d, volume_change_1d, volume_change_5d, volume_ratio_5d_change_1d,

                    iv, iv_change_1d, iv_change_5d, iv_change_20d,
                    iv_change_pct_1d, iv_change_pct_5d, iv_change_pct_20d,
                    iv_avg_5d, iv_avg_20d, iv_percentile_20day,
                    iv_momentum_1d, iv_momentum_5d,

                    delta, delta_change_1d, delta_change_5d, delta_momentum, delta_acceleration,
                    gamma, gamma_change_1d, gamma_change_5d, gamma_momentum,
                    theta, theta_change_1d, theta_change_5d, theta_momentum, theta_avg_5d, theta_daily_change_avg_5d,
                    vega, vega_change_1d, vega_change_5d,

                    oi_change_1d, oi_change_5d, oi_change_10d,
                    oi_change_pct_1d, oi_change_pct_5d, oi_change_pct_10d,
                    oi_momentum_5d,

                    created_at,
                    iv_percentile_rank_20d
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''

            cursor.executemany(insert_sql, prepared_batch)
            return cursor.rowcount
        
        # Process in batches
        for i in range(0, len(contracts_list), batch_size):
            batch = contracts_list[i:i + batch_size]
            
            result = self._execute_with_retry(lambda conn: _bulk_insert_operation(conn, batch))
            
            if result is not False:
                total_inserted += result
                logging.debug("OP: Bulk inserted batch of {} records".format(result))
            else:
                logging.error("OP: Bulk insert failed for batch starting at index {}".format(i))
                return -1
        
        logging.debug("Bulk insert completed: {} total records inserted".format(total_inserted))
        return total_inserted
    
    def get_contracts_for_symbol_date(self, symbol, trade_date):
        """Get all contracts for a specific symbol and date
        
        Args:
            symbol: Stock symbol to retrieve
            trade_date: Specific trade date in YYYY-MM-DD format
            
        Returns:
            list: List of contract dictionaries for the symbol/date
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT
                        contract_hash, symbol, strike, expiration_date, option_type,
                        trade_date, open_interest, volume, oi_change_1d, oi_change_pct_1d,
                        building_unwinding, build_pattern
                    FROM option_contracts
                    WHERE symbol = ? AND trade_date = ?
                    ORDER BY expiration_date, option_type, strike
                ''', (symbol.upper(), trade_date))

                contracts = []
                for row in cursor.fetchall():
                    contracts.append({
                        'contract_hash': row[0],
                        'symbol': row[1],
                        'strike': row[2],
                        'expiration_date': row[3],
                        'option_type': row[4],
                        'trade_date': row[5],
                        'open_interest': row[6],
                        'volume': row[7],
                        'oi_change_1d': row[8],
                        'oi_change_pct_1d': row[9],
                        'building_unwinding': row[10],
                        'build_pattern': row[11]
                    })
                
                return contracts
                
        except Exception as e:
            logging.error("OP: Error getting contracts for {} on {}: {}".format(symbol, trade_date, e))
            return []
    
    def get_symbols_for_date(self, trade_date):
        """Get all symbols that have data for a specific date
        
        Args:
            trade_date: Trade date in YYYY-MM-DD format
            
        Returns:
            list: List of symbols that have contracts on the date
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT symbol 
                    FROM option_contracts 
                    WHERE trade_date = ?
                    ORDER BY symbol
                ''', (trade_date,))
                results = cursor.fetchall()
                return [row[0] for row in results] if results else []
        except Exception as e:
            logging.error("OP: Error getting symbols for date {}: {}".format(trade_date, e))
            return []
    
    def get_historical_oi_for_momentum(self, contract_hash, trade_date, max_days_back):
        """Get historical OI data for momentum calculations
        
        Args:
            contract_hash: Contract identifier
            trade_date: Current trade date
            max_days_back: Maximum number of days to look back
            
        Returns:
            Dictionary keyed by days_back with OI values
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Calculate date range for lookback
                trade_date_obj = datetime.strptime(trade_date, '%Y-%m-%d')
                earliest_date = trade_date_obj - timedelta(days=max_days_back + 5)  # Buffer for weekends
                
                cursor.execute('''
                    SELECT trade_date, open_interest
                    FROM option_contracts
                    WHERE contract_hash = ?
                      AND trade_date >= ?
                      AND trade_date < ?
                    ORDER BY trade_date DESC
                ''', (contract_hash, earliest_date.strftime('%Y-%m-%d'), trade_date))

                # Build historical data dictionary using ROW-BASED lookback (trading days)
                # Row position = trading days ago (your time series vision)
                rows = cursor.fetchall()
                historical_data = {}

                # Map row positions to trading days back
                # rows[0] = 1 trading day ago, rows[4] = 5 trading days ago, etc.
                if len(rows) >= 1:
                    historical_data[1] = rows[0][1]  # 1 trading day ago
                if len(rows) >= 2:
                    historical_data[2] = rows[1][1]  # For oi_momentum_5d averaging
                if len(rows) >= 3:
                    historical_data[3] = rows[2][1]
                if len(rows) >= 4:
                    historical_data[4] = rows[3][1]
                if len(rows) >= 5:
                    historical_data[5] = rows[4][1]  # 5 trading days ago
                if len(rows) >= 10:
                    historical_data[10] = rows[9][1]  # 10 trading days ago

                return historical_data
                
        except Exception as e:
            logging.error("OP: Error getting historical OI for {}: {}".format(contract_hash, e))
            return {}
    
    # Methods for analyzer to update analysis fields
    # NOTE: update_interest_flags method removed Oct 20, 2025 - Gap from Maximum filter deprecated
    def update_position_tracking_batch(self, position_updates):
        """Update position tracking data for multiple contracts
        
        Args:
            position_updates: List of position tracking update dictionaries
            
        Returns:
            int: Number of contracts updated successfully
        """
        if not position_updates:
            return 0
        
        def _batch_update_operation(conn):
            cursor = conn.cursor()

            update_sql = '''
                UPDATE option_contracts SET
                    build_pattern = ?
                WHERE contract_hash = ? AND trade_date = ?
            '''

            update_data = []
            for update in position_updates:
                update_data.append((
                    update.get('build_pattern'),
                    update.get('contract_hash'),
                    update.get('trade_date')
                ))
            
            cursor.executemany(update_sql, update_data)
            return cursor.rowcount
        
        result = self._execute_with_retry(_batch_update_operation)
        if result is not False:
            logging.debug("OP: Updated position tracking for {} contracts".format(result))
            return result
        else:
            logging.error("OP: Failed to update position tracking batch")
            return 0
    
    def update_momentum_metrics_batch(self, momentum_updates):
        """Batch update momentum metrics for multiple contracts
        
        Args:
            momentum_updates: List of dictionaries with momentum data
            
        Returns:
            int: Number of records updated successfully
        """
        if not momentum_updates:
            return 0
        
        def _batch_update_operation(conn):
            cursor = conn.cursor()
            
            update_sql = '''
                UPDATE option_contracts SET
                    oi_change_1d = ?, oi_change_5d = ?, oi_change_10d = ?,
                    oi_change_pct_1d = ?, oi_change_pct_5d = ?, oi_change_pct_10d = ?,
                    oi_momentum_5d = ?
                WHERE contract_hash = ? AND trade_date = ?
            '''

            prepared_updates = []
            for update in momentum_updates:
                prepared_updates.append((
                    update.get('oi_change_1d'),
                    update.get('oi_change_5d'),
                    update.get('oi_change_10d'),
                    update.get('oi_change_pct_1d'),
                    update.get('oi_change_pct_5d'),
                    update.get('oi_change_pct_10d'),
                    update.get('oi_momentum_5d'),
                    update.get('contract_hash'),
                    update.get('trade_date')
                ))
            
            cursor.executemany(update_sql, prepared_updates)
            return cursor.rowcount
        
        result = self._execute_with_retry(_batch_update_operation)
        if result is not False:
            logging.debug("OP: Updated momentum metrics for {} contracts".format(result))
            return result
        else:
            logging.error("OP: Failed to update momentum metrics")
            return 0
    
    # NOTE: get_interesting_strikes_for_date method removed Oct 20, 2025 - Gap from Maximum filter deprecated

    def cleanup_old_data(self, days_to_keep=None):
        """Remove old OI records per retention policy
        
        Args:
            days_to_keep: Override default retention period
            
        Returns:
            int: Number of records deleted, -1 on failure
        """
        retention_days = days_to_keep or self.retention_days
        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime('%Y-%m-%d')
        
        def _cleanup_operation(conn):
            cursor = conn.cursor()
            
            # Count records to be deleted
            cursor.execute('SELECT COUNT(*) FROM option_contracts WHERE trade_date < ?', (cutoff_date,))
            count_to_delete = cursor.fetchone()[0]
            
            if count_to_delete == 0:
                logging.info("OP: No old records to cleanup (retention: {} days)".format(retention_days))
                return 0
            
            # Delete old records - FIXED: use trade_date consistently
            cursor.execute('DELETE FROM option_contracts WHERE trade_date < ?', (cutoff_date,))
            deleted_count = cursor.rowcount
            
            # Vacuum to reclaim space
            cursor.execute('VACUUM')
            
            logging.info("OP: Cleanup completed: {} records deleted (older than {} days)".format(
                deleted_count, retention_days))
            return deleted_count
        
        return self._execute_with_retry(_cleanup_operation)
    
    # Symbol Summary Methods for Rollup Feature
    def insert_symbol_summaries(self, summaries_list):
        """Bulk insert symbol summary records into option_symbol_summary table
        
        Args:
            summaries_list: List of dictionaries with symbol summary data
        
        Returns:
            int: Number of records actually inserted
        """
        if not summaries_list:
            logging.debug("OP: No symbol summaries provided for insertion")
            return 0
        
        def _insert_summaries_operation(conn):
            cursor = conn.cursor()
            
            insert_sql = '''
                INSERT OR REPLACE INTO option_symbol_summary (
                    symbol, trade_date, total_open_interest, total_call_oi, total_put_oi,
                    put_call_ratio, oi_balance_text, top_call_strike, top_call_expiration,
                    top_call_oi, top_call_pct_of_total, top_call_display,
                    top_put_strike, top_put_expiration, top_put_oi, top_put_pct_of_total,
                    top_put_display,
                    building_contracts_count, unwinding_contracts_count,
                    oi_0_7_days, oi_8_21_days, oi_22_35_days, oi_36_60_days,
                    oi_0_7_days_percent, oi_8_21_days_percent, oi_22_35_days_percent, oi_36_60_days_percent,
                    call_oi_0_7_days, call_oi_8_21_days, call_oi_22_35_days, call_oi_36_60_days,
                    call_oi_0_7_days_percent, call_oi_8_21_days_percent, call_oi_22_35_days_percent, call_oi_36_60_days_percent,
                    put_oi_0_7_days, put_oi_8_21_days, put_oi_22_35_days, put_oi_36_60_days,
                    put_oi_0_7_days_percent, put_oi_8_21_days_percent, put_oi_22_35_days_percent, put_oi_36_60_days_percent,
                    max_pain_by_friday, analysis_timestamp,
                    close_price, option_volume, call_volume, put_volume, volume_put_call_ratio,
                    call_iv_avg, put_iv_avg, iv_skew, call_iv_weighted, put_iv_weighted, symbol_iv_percentile_30d,
                    iv_front_month, iv_30dte, iv_45dte, iv_60dte,
                    total_delta_exposure, call_delta_exposure, put_delta_exposure, net_delta_exposure,
                    total_gamma_exposure, max_gamma_strike, total_theta_exposure,
                    total_vega_exposure, call_vega_exposure, put_vega_exposure, net_vega_exposure,
                    deep_itm_call_oi, itm_call_oi, atm_call_oi, otm_call_oi, deep_otm_call_oi,
                    deep_itm_put_oi, itm_put_oi, atm_put_oi, otm_put_oi, deep_otm_put_oi,
                    deep_itm_call_pct, itm_call_pct, atm_call_pct, otm_call_pct, deep_otm_call_pct,
                    deep_itm_put_pct, itm_put_pct, atm_put_pct, otm_put_pct, deep_otm_put_pct,
                    avg_bid_ask_spread_pct, contracts_with_data,
                    rv_5d, rv_10d
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''


            
            prepared_data = []
            for summary in summaries_list:
                # Apply decimal formatting safety net to ensure compliance
                summary = clean_database_row(summary)

                prepared_data.append((
                    summary.get('symbol'),
                    summary.get('trade_date'),
                    summary.get('total_open_interest', 0),
                    summary.get('total_call_oi', 0),
                    summary.get('total_put_oi', 0),
                    summary.get('put_call_ratio'),
                    summary.get('oi_balance_text'),
                    summary.get('top_call_strike'),
                    summary.get('top_call_expiration'),
                    summary.get('top_call_oi'),
                    summary.get('top_call_pct_of_total'),
                    summary.get('top_call_display'),
                    summary.get('top_put_strike'),
                    summary.get('top_put_expiration'),
                    summary.get('top_put_oi'),
                    summary.get('top_put_pct_of_total'),
                    summary.get('top_put_display'),
                    summary.get('building_contracts_count', 0),
                    summary.get('unwinding_contracts_count', 0),
                    # Time horizon metrics - combined
                    summary.get('oi_0_7_days', 0),
                    summary.get('oi_8_21_days', 0),
                    summary.get('oi_22_35_days', 0),
                    summary.get('oi_36_60_days', 0),
                    summary.get('oi_0_7_days_percent', 0.0),
                    summary.get('oi_8_21_days_percent', 0.0),
                    summary.get('oi_22_35_days_percent', 0.0),
                    summary.get('oi_36_60_days_percent', 0.0),
                    # Time horizon metrics - calls
                    summary.get('call_oi_0_7_days', 0),
                    summary.get('call_oi_8_21_days', 0),
                    summary.get('call_oi_22_35_days', 0),
                    summary.get('call_oi_36_60_days', 0),
                    summary.get('call_oi_0_7_days_percent', 0.0),
                    summary.get('call_oi_8_21_days_percent', 0.0),
                    summary.get('call_oi_22_35_days_percent', 0.0),
                    summary.get('call_oi_36_60_days_percent', 0.0),
                    # Time horizon metrics - puts
                    summary.get('put_oi_0_7_days', 0),
                    summary.get('put_oi_8_21_days', 0),
                    summary.get('put_oi_22_35_days', 0),
                    summary.get('put_oi_36_60_days', 0),
                    summary.get('put_oi_0_7_days_percent', 0.0),
                    summary.get('put_oi_8_21_days_percent', 0.0),
                    summary.get('put_oi_22_35_days_percent', 0.0),
                    summary.get('put_oi_36_60_days_percent', 0.0),
                    # Max pain metric
                    summary.get('max_pain_by_friday'),
                    # Processing metadata
                    summary.get('analysis_timestamp'),
                    # Stock data
                    summary.get('close_price'),
                    # Volume metrics
                    summary.get('option_volume', 0),
                    summary.get('call_volume', 0),
                    summary.get('put_volume', 0),
                    summary.get('volume_put_call_ratio'),
                    # IV metrics
                    summary.get('call_iv_avg'),
                    summary.get('put_iv_avg'),
                    summary.get('iv_skew'),
                    summary.get('call_iv_weighted'),
                    summary.get('put_iv_weighted'),
                    summary.get('symbol_iv_percentile_30d'),
                    # IV by DTE buckets
                    summary.get('iv_front_month'),
                    summary.get('iv_30dte'),
                    summary.get('iv_45dte'),
                    summary.get('iv_60dte'),
                    # Delta exposure
                    summary.get('total_delta_exposure'),
                    summary.get('call_delta_exposure'),
                    summary.get('put_delta_exposure'),
                    summary.get('net_delta_exposure'),
                    # Gamma exposure
                    summary.get('total_gamma_exposure'),
                    summary.get('max_gamma_strike'),
                    # Theta exposure
                    summary.get('total_theta_exposure'),
                    # Vega exposure
                    summary.get('total_vega_exposure'),
                    summary.get('call_vega_exposure'),
                    summary.get('put_vega_exposure'),
                    summary.get('net_vega_exposure'),
                    # Moneyness distribution - Call OI
                    summary.get('deep_itm_call_oi', 0),
                    summary.get('itm_call_oi', 0),
                    summary.get('atm_call_oi', 0),
                    summary.get('otm_call_oi', 0),
                    summary.get('deep_otm_call_oi', 0),
                    # Moneyness distribution - Put OI
                    summary.get('deep_itm_put_oi', 0),
                    summary.get('itm_put_oi', 0),
                    summary.get('atm_put_oi', 0),
                    summary.get('otm_put_oi', 0),
                    summary.get('deep_otm_put_oi', 0),
                    # Moneyness distribution - Call percentages
                    summary.get('deep_itm_call_pct'),
                    summary.get('itm_call_pct'),
                    summary.get('atm_call_pct'),
                    summary.get('otm_call_pct'),
                    summary.get('deep_otm_call_pct'),
                    # Moneyness distribution - Put percentages
                    summary.get('deep_itm_put_pct'),
                    summary.get('itm_put_pct'),
                    summary.get('atm_put_pct'),
                    summary.get('otm_put_pct'),
                    summary.get('deep_otm_put_pct'),
                    # Quality metrics
                    summary.get('avg_bid_ask_spread_pct'),
                    summary.get('contracts_with_data', 0),
                    # Realized volatility (for z-score dip detection)
                    summary.get('rv_5d'),
                    summary.get('rv_10d')
                ))
            
            cursor.executemany(insert_sql, prepared_data)
            return cursor.rowcount
        
        result = self._execute_with_retry(_insert_summaries_operation)
        if result is not False:
            return result
        else:
            logging.error("OP: Failed to insert symbol summaries")
            return 0
    
    def get_symbol_summary(self, symbol, trade_date):
        """Retrieve specific symbol summary for given symbol and date
        
        Args:
            symbol: Stock ticker symbol
            trade_date: Trading date in YYYY-MM-DD format
        
        Returns:
            dict: Symbol summary data or None if not found
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM option_symbol_summary 
                    WHERE symbol = ? AND trade_date = ?
                ''', (symbol.upper(), trade_date))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logging.error("OP: Error getting symbol summary for {} on {}: {}".format(symbol, trade_date, e))
            return None
    
    def get_latest_symbol_summary(self, symbol):
        """Get latest symbol summary for a given symbol
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            dict: Latest symbol summary data or None if not found
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM option_symbol_summary 
                    WHERE symbol = ? 
                    ORDER BY trade_date DESC 
                    LIMIT 1
                ''', (symbol.upper(),))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logging.error("OP: Error getting latest symbol summary for {}: {}".format(symbol, e))
            return None
    
    # Helper methods for calculations
    def _get_previous_oi_data(self, cursor, contract_hash, trade_date):
        """Get previous trading day's OI data for delta calculations"""
        cursor.execute('''
            SELECT open_interest
            FROM option_contracts
            WHERE contract_hash = ? AND trade_date < ?
            ORDER BY trade_date DESC LIMIT 1
        ''', (contract_hash, trade_date))

        result = cursor.fetchone()
        if result:
            return {'prev_oi': result[0]}
        return {'prev_oi': None}

    def _get_historical_data(self, cursor, contract_hash, trade_date, days_back=20):
        """Get historical data for time series calculations

        Args:
            cursor: Database cursor
            contract_hash: Contract identifier
            trade_date: Current trade date
            days_back: Number of days to look back

        Returns:
            list: List of historical records ordered by date (oldest first)
        """
        cursor.execute('''
            SELECT trade_date, volume, iv,
                   delta, gamma, theta, vega, last_price,
                   open_interest
            FROM option_contracts
            WHERE contract_hash = ? AND trade_date < ?
            ORDER BY trade_date DESC
            LIMIT ?
        ''', (contract_hash, trade_date, days_back))

        results = cursor.fetchall()
        # Convert to list of dictionaries and reverse to get chronological order
        historical_data = []
        for row in reversed(results):
            historical_data.append({
                'trade_date': row[0],
                'volume': row[1] or 0,
                'iv': row[2] or 0.0,
                'delta': row[3] or 0.0,
                'gamma': row[4] or 0.0,
                'theta': row[5] or 0.0,
                'vega': row[6] or 0.0,
                'last_price': row[7] or 0.0,
                'open_interest': row[8] or 0
            })

        return historical_data

    def _calculate_time_series_metrics(self, cursor, contract_hash, trade_date, current_data):
        """Calculate all time series metrics for volume, IV, and Greeks

        Args:
            cursor: Database cursor
            contract_hash: Contract identifier
            trade_date: Current trade date
            current_data: Current contract data dictionary

        Returns:
            dict: Dictionary with all calculated time series metrics
        """
        metrics = {}

        # Get historical data for calculations
        historical_data = self._get_historical_data(cursor, contract_hash, trade_date, days_back=20)

        if not historical_data:
            # Return zeros for all metrics if no historical data
            return self._get_default_time_series_metrics()

        # Current values
        current_volume = current_data.get('volume', 0)
        current_iv = current_data.get('iv', 0.0)
        current_delta = current_data.get('delta', 0.0)
        current_gamma = current_data.get('gamma', 0.0)
        current_theta = current_data.get('theta', 0.0)
        current_vega = current_data.get('vega', 0.0)

        # VOLUME CALCULATIONS
        volumes = [row['volume'] for row in historical_data if row['volume'] is not None]
        if volumes:
            # 5-day and 20-day averages
            metrics['volume_avg_5d'] = format_score(sum(volumes[-5:]) / min(5, len(volumes)) if len(volumes) > 0 else 0.0)
            metrics['volume_avg_20d'] = format_score(sum(volumes) / len(volumes) if len(volumes) > 0 else 0.0)

            # Volume ratios (current vs averages) - Fixed to handle near-zero division
            MIN_VOLUME_FOR_RATIO = 10.0  # Minimum average volume to calculate meaningful ratios
            MAX_VOLUME_RATIO = 100.0     # Cap extreme ratios

            # 5-day ratio calculation
            if current_volume == 0:
                metrics['volume_ratio_5d'] = format_ratio(0.0)  # Zero volume = zero ratio
            elif metrics['volume_avg_5d'] >= MIN_VOLUME_FOR_RATIO:
                raw_ratio = current_volume / metrics['volume_avg_5d']
                capped_ratio = min(raw_ratio, MAX_VOLUME_RATIO)
                metrics['volume_ratio_5d'] = format_ratio(capped_ratio)
            else:
                metrics['volume_ratio_5d'] = None  # Insufficient baseline data

            # 20-day ratio calculation
            if current_volume == 0:
                metrics['volume_ratio_20d'] = format_ratio(0.0)  # Zero volume = zero ratio
            elif metrics['volume_avg_20d'] >= MIN_VOLUME_FOR_RATIO:
                raw_ratio = current_volume / metrics['volume_avg_20d']
                capped_ratio = min(raw_ratio, MAX_VOLUME_RATIO)
                metrics['volume_ratio_20d'] = format_ratio(capped_ratio)
            else:
                metrics['volume_ratio_20d'] = None  # Insufficient baseline data

            # Volume percentile rank (20-day) - require 10-day minimum for meaningful percentile
            if len(volumes) >= 10:
                metrics['volume_percentile_rank_20d'] = format_percentage(self._calculate_percentile_rank(current_volume, volumes))
            else:
                metrics['volume_percentile_rank_20d'] = None  # Insufficient data for meaningful percentile

            # Volume changes (absolute differences)
            prev_1d_volume = historical_data[-1]['volume'] if len(historical_data) >= 1 else 0
            prev_5d_volume = historical_data[-5]['volume'] if len(historical_data) >= 5 else 0

            metrics['volume_change_1d'] = current_volume - prev_1d_volume
            metrics['volume_change_5d'] = current_volume - prev_5d_volume

            # Volume ratio acceleration (ratio change over time)
            if len(historical_data) >= 1:
                # Calculate yesterday's 5d ratio for comparison
                yesterday_data = historical_data[-1]
                yesterday_volume = yesterday_data['volume']

                # Get historical volumes for yesterday's 5d average calculation
                if len(historical_data) >= 6:  # Need 6 days to calculate yesterday's 5d average
                    yesterday_5d_volumes = volumes[-6:-1]  # Skip today, get previous 5 days from yesterday's perspective
                    yesterday_volume_avg_5d = sum(yesterday_5d_volumes) / len(yesterday_5d_volumes) if yesterday_5d_volumes else 1.0

                    # Calculate ratio change only if today's ratio is valid (not None)
                    if yesterday_volume_avg_5d > 0 and metrics['volume_ratio_5d'] is not None:
                        yesterday_volume_ratio_5d = yesterday_volume / yesterday_volume_avg_5d
                        metrics['volume_ratio_5d_change_1d'] = metrics['volume_ratio_5d'] - yesterday_volume_ratio_5d
                    else:
                        metrics['volume_ratio_5d_change_1d'] = 0.0
                else:
                    metrics['volume_ratio_5d_change_1d'] = 0.0
            else:
                metrics['volume_ratio_5d_change_1d'] = 0.0

        else:
            metrics['volume_avg_5d'] = format_score(0.0)
            metrics['volume_avg_20d'] = format_score(0.0)
            metrics['volume_ratio_5d'] = None  # No historical data available
            metrics['volume_ratio_20d'] = None  # No historical data available
            metrics['volume_percentile_rank_20d'] = format_percentage(0.0)
            metrics['volume_change_1d'] = 0
            metrics['volume_change_5d'] = 0
            metrics['volume_ratio_5d_change_1d'] = format_ratio(0.0)

        # IMPLIED VOLATILITY CALCULATIONS
        ivs = [row['iv'] for row in historical_data if row['iv'] is not None]
        if ivs and len(historical_data) >= 1:
            # Changes (1d, 5d, 20d)
            prev_1d = historical_data[-1]['iv'] if len(historical_data) >= 1 else 0.0
            prev_5d = historical_data[-5]['iv'] if len(historical_data) >= 5 else 0.0
            prev_20d = historical_data[0]['iv'] if len(historical_data) >= 20 else 0.0

            metrics['iv_change_1d'] = current_iv - prev_1d
            metrics['iv_change_5d'] = current_iv - prev_5d
            metrics['iv_change_20d'] = current_iv - prev_20d

            # Percentage changes
            metrics['iv_change_pct_1d'] = format_percentage((metrics['iv_change_1d'] / prev_1d * 100) if prev_1d != 0 else 0.0)
            metrics['iv_change_pct_5d'] = format_percentage((metrics['iv_change_5d'] / prev_5d * 100) if prev_5d != 0 else 0.0)
            metrics['iv_change_pct_20d'] = format_percentage((metrics['iv_change_20d'] / prev_20d * 100) if prev_20d != 0 else 0.0)

            # Averages
            metrics['iv_avg_5d'] = format_greek(sum(ivs[-5:]) / min(5, len(ivs)) if len(ivs) > 0 else 0.0)
            metrics['iv_avg_20d'] = format_greek(sum(ivs) / len(ivs) if len(ivs) > 0 else 0.0)

            # Percentiles - require 10-day minimum for meaningful percentile
            if len(ivs) >= 10:
                metrics['iv_percentile_20day'] = format_percentage(self._calculate_percentile_rank(current_iv, ivs))
                metrics['iv_percentile_rank_20d'] = metrics['iv_percentile_20day']  # Alias
            else:
                metrics['iv_percentile_20day'] = None  # Insufficient data for meaningful percentile
                metrics['iv_percentile_rank_20d'] = None  # Alias

            # Momentum (rate of change)
            metrics['iv_momentum_1d'] = metrics['iv_change_1d']
            if len(historical_data) >= 5 and metrics['iv_avg_5d'] != 0:
                metrics['iv_momentum_5d'] = format_greek((current_iv - metrics['iv_avg_5d']) / metrics['iv_avg_5d'] * 100)
            else:
                metrics['iv_momentum_5d'] = format_greek(0.0)
        else:
            # Default IV metrics
            for key in ['iv_change_1d', 'iv_change_5d', 'iv_change_20d', 'iv_change_pct_1d',
                       'iv_change_pct_5d', 'iv_change_pct_20d', 'iv_avg_5d', 'iv_avg_20d',
                       'iv_percentile_20day', 'iv_percentile_rank_20d', 'iv_momentum_1d', 'iv_momentum_5d']:
                metrics[key] = 0.0

        # GREEKS CALCULATIONS
        if len(historical_data) >= 1:
            prev_1d_data = historical_data[-1]
            prev_5d_data = historical_data[-5] if len(historical_data) >= 5 else historical_data[0]

            # DELTA calculations
            metrics['delta_change_1d'] = current_delta - prev_1d_data['delta']
            metrics['delta_change_5d'] = current_delta - prev_5d_data['delta']

            deltas = [row['delta'] for row in historical_data if row['delta'] is not None]
            if deltas:
                delta_5d_avg = sum(deltas[-5:]) / min(5, len(deltas))
                metrics['delta_momentum'] = (current_delta - delta_5d_avg) / max(abs(delta_5d_avg), 0.01) * 100
            else:
                metrics['delta_momentum'] = 0.0

            # Delta acceleration (2nd derivative)
            if len(historical_data) >= 2:
                prev_2d_data = historical_data[-2]
                yesterday_change = prev_1d_data['delta'] - prev_2d_data['delta']
                today_change = current_delta - prev_1d_data['delta']
                metrics['delta_acceleration'] = today_change - yesterday_change
            else:
                metrics['delta_acceleration'] = 0.0

            # GAMMA calculations
            metrics['gamma_change_1d'] = current_gamma - prev_1d_data['gamma']
            metrics['gamma_change_5d'] = current_gamma - prev_5d_data['gamma']

            gammas = [row['gamma'] for row in historical_data if row['gamma'] is not None]
            if gammas:
                gamma_5d_avg = sum(gammas[-5:]) / min(5, len(gammas))
                metrics['gamma_momentum'] = (current_gamma - gamma_5d_avg) / max(abs(gamma_5d_avg), 0.01) * 100
            else:
                metrics['gamma_momentum'] = 0.0

            # THETA calculations
            metrics['theta_change_1d'] = current_theta - prev_1d_data['theta']
            metrics['theta_change_5d'] = current_theta - prev_5d_data['theta']

            thetas = [row['theta'] for row in historical_data if row['theta'] is not None]
            if thetas:
                # 5-day rolling average of theta values
                theta_5d_avg = sum(thetas[-5:]) / min(5, len(thetas))
                metrics['theta_avg_5d'] = theta_5d_avg
                metrics['theta_momentum'] = (current_theta - theta_5d_avg) / max(abs(theta_5d_avg), 0.01) * 100

                # Calculate daily changes for the last 5 periods to get average of daily changes
                theta_daily_changes = []
                for i in range(1, min(6, len(thetas) + 1)):  # Look back up to 5 days
                    if i < len(thetas):
                        daily_change = thetas[-i] - thetas[-i-1] if (len(thetas) - i - 1) >= 0 else 0
                        theta_daily_changes.append(daily_change)

                # Add today's change to the list
                theta_daily_changes.append(current_theta - prev_1d_data['theta'])

                # Average of the daily changes
                if theta_daily_changes:
                    metrics['theta_daily_change_avg_5d'] = sum(theta_daily_changes) / len(theta_daily_changes)
                else:
                    metrics['theta_daily_change_avg_5d'] = 0.0
            else:
                metrics['theta_avg_5d'] = 0.0
                metrics['theta_momentum'] = 0.0
                metrics['theta_daily_change_avg_5d'] = 0.0

            # VEGA calculations
            metrics['vega_change_1d'] = current_vega - prev_1d_data['vega']
            metrics['vega_change_5d'] = current_vega - prev_5d_data['vega']
        else:
            # Default Greeks metrics
            for key in ['delta_change_1d', 'delta_change_5d', 'delta_momentum', 'delta_acceleration',
                       'gamma_change_1d', 'gamma_change_5d', 'gamma_momentum',
                       'theta_change_1d', 'theta_change_5d', 'theta_momentum', 'theta_avg_5d', 'theta_daily_change_avg_5d',
                       'vega_change_1d', 'vega_change_5d']:
                metrics[key] = 0.0

        # OI MOMENTUM CALCULATIONS (Row-based time series)
        # Now runs for ALL contracts, not just interesting strikes
        current_oi = current_data.get('open_interest', 0)

        if len(historical_data) >= 1:
            # Extract historical OI values using row-based lookback
            prev_1d_oi = historical_data[-1]['open_interest'] if len(historical_data) >= 1 else 0
            prev_5d_oi = historical_data[-5]['open_interest'] if len(historical_data) >= 5 else 0
            prev_10d_oi = historical_data[-10]['open_interest'] if len(historical_data) >= 10 else 0

            # Calculate absolute changes
            metrics['oi_change_1d'] = current_oi - prev_1d_oi if len(historical_data) >= 1 else None
            metrics['oi_change_5d'] = current_oi - prev_5d_oi if len(historical_data) >= 5 else None
            metrics['oi_change_10d'] = current_oi - prev_10d_oi if len(historical_data) >= 10 else None

            # Calculate percentage changes
            if len(historical_data) >= 1 and prev_1d_oi > 0:
                metrics['oi_change_pct_1d'] = round(((current_oi - prev_1d_oi) / prev_1d_oi) * 100, 2)
            else:
                metrics['oi_change_pct_1d'] = None

            if len(historical_data) >= 5 and prev_5d_oi > 0:
                metrics['oi_change_pct_5d'] = round(((current_oi - prev_5d_oi) / prev_5d_oi) * 100, 2)
            else:
                metrics['oi_change_pct_5d'] = None

            if len(historical_data) >= 10 and prev_10d_oi > 0:
                metrics['oi_change_pct_10d'] = round(((current_oi - prev_10d_oi) / prev_10d_oi) * 100, 2)
            else:
                metrics['oi_change_pct_10d'] = None

            # Calculate 5-day averaged momentum (smoothed trend indicator)
            if len(historical_data) >= 4:
                # Collect up to 5 days of historical OI values
                historical_oi_values = []
                for i in range(min(5, len(historical_data))):
                    historical_oi_values.append(historical_data[-(i+1)]['open_interest'])

                # Calculate 5-day average
                avg_5d_oi = sum(historical_oi_values) / len(historical_oi_values)

                if avg_5d_oi > 0:
                    metrics['oi_momentum_5d'] = round(((current_oi - avg_5d_oi) / avg_5d_oi) * 100, 2)
                else:
                    metrics['oi_momentum_5d'] = None
            else:
                metrics['oi_momentum_5d'] = None
        else:
            # No historical data - set all OI momentum metrics to None
            metrics['oi_change_1d'] = None
            metrics['oi_change_5d'] = None
            metrics['oi_change_10d'] = None
            metrics['oi_change_pct_1d'] = None
            metrics['oi_change_pct_5d'] = None
            metrics['oi_change_pct_10d'] = None
            metrics['oi_momentum_5d'] = None

        # BUILD PATTERN CALCULATION (simple logic based on OI change)
        # Only calculate for positions with meaningful OI (>= 100)
        if current_oi >= 100 and metrics.get('oi_change_1d') is not None:
            oi_change_1d = metrics['oi_change_1d']
            if oi_change_1d > (current_oi * 0.20):
                build_pattern = "sudden"
            elif oi_change_1d > 0:
                build_pattern = "gradual"
            elif oi_change_1d < -(current_oi * 0.20):
                build_pattern = "unwinding"
            else:
                build_pattern = "stable"
        else:
            build_pattern = None

        metrics['build_pattern'] = build_pattern

        return metrics

    def _calculate_percentile_rank(self, current_value, historical_values):
        """Calculate percentile rank of current value within historical values"""
        if not historical_values or current_value is None:
            return 0.0

        below_count = sum(1 for val in historical_values if val < current_value)
        return (below_count / len(historical_values)) * 100

    def _get_default_time_series_metrics(self):
        """Return dictionary with all time series metrics set to default values"""
        return {
            # Volume metrics
            'volume_avg_5d': 0.0,
            'volume_avg_20d': 0.0,
            'volume_ratio_5d': None,  # Use None for invalid ratios
            'volume_ratio_20d': None,  # Use None for invalid ratios
            'volume_percentile_rank_20d': 0.0,
            'volume_change_1d': 0,
            'volume_change_5d': 0,
            'volume_ratio_5d_change_1d': 0.0,

            # IV metrics
            'iv_change_1d': 0.0,
            'iv_change_5d': 0.0,
            'iv_change_20d': 0.0,
            'iv_change_pct_1d': 0.0,
            'iv_change_pct_5d': 0.0,
            'iv_change_pct_20d': 0.0,
            'iv_avg_5d': 0.0,
            'iv_avg_20d': 0.0,
            'iv_percentile_20day': 0.0,
            'iv_percentile_rank_20d': 0.0,
            'iv_momentum_1d': 0.0,
            'iv_momentum_5d': 0.0,

            # Greeks metrics
            'delta_change_1d': 0.0,
            'delta_change_5d': 0.0,
            'delta_momentum': 0.0,
            'delta_acceleration': 0.0,
            'gamma_change_1d': 0.0,
            'gamma_change_5d': 0.0,
            'gamma_momentum': 0.0,
            'theta_change_1d': 0.0,
            'theta_change_5d': 0.0,
            'theta_momentum': 0.0,
            'theta_avg_5d': 0.0,
            'theta_daily_change_avg_5d': 0.0,
            'vega_change_1d': 0.0,
            'vega_change_5d': 0.0
        }

    def _determine_oi_direction(self, oi_change, oi_change_pct):
        """Determine if OI is building, unwinding, or stable"""
        if oi_change_pct > 10:
            return 'BUILDING'
        elif oi_change_pct < -10:
            return 'UNWINDING'
        else:
            return 'STABLE'
    
    def _calculate_moneyness(self, strike, underlying_price, option_type):
        """Calculate option moneyness using Flow Monitor's ±1% ATM threshold

        Args:
            strike: Strike price
            underlying_price: Current stock price
            option_type: 'CALL' or 'PUT'

        Returns:
            str: 'ITM', 'ATM', 'OTM', or 'UNK' if data missing
        """
        if not strike or not underlying_price or underlying_price == 0:
            return 'UNK'

        option_type_upper = option_type.upper()

        if option_type_upper == 'CALL':
            if strike < underlying_price * 0.99:
                return 'ITM'
            elif strike > underlying_price * 1.01:
                return 'OTM'
            else:
                return 'ATM'
        else:  # PUT
            if strike > underlying_price * 1.01:
                return 'ITM'
            elif strike < underlying_price * 0.99:
                return 'OTM'
            else:
                return 'ATM'

    def get_contract_yesterday_status(self, contract_hash, trade_date):
        """Get yesterday's status for a contract for position age tracking

        Args:
            contract_hash: Contract identifier
            trade_date: Current trade date

        Returns:
            dict: Yesterday's contract data or None
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get the previous trading day's data
                cursor.execute('''
                    SELECT build_pattern
                    FROM option_contracts
                    WHERE contract_hash = ?
                      AND trade_date < ?
                    ORDER BY trade_date DESC
                    LIMIT 1
                ''', (contract_hash, trade_date))

                row = cursor.fetchone()
                if row:
                    return {'build_pattern': row[0]}
                return None

        except Exception as e:
            logging.error("OP: Error getting yesterday status for {}: {}".format(contract_hash, e))
            return None

    def query_db(self, query, params=None):
        """Execute a query with optional parameters and return results

        Args:
            query: SQL query string
            params: Query parameters tuple or list (optional)

        Returns:
            list: Query results as list of dictionaries (for compatibility with rollup code)
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                # Convert rows to dictionaries for compatibility
                columns = [col[0] for col in cursor.description] if cursor.description else []
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))

                return results

        except Exception as e:
            logging.error("OP: Query error: {}".format(e))
            return []

    def query_with_params(self, query, params=()):
        """Alias for query_db() to match FlowMonitorStorage interface

        This allows alert resolver and other cross-strategy code to use
        a consistent query method name across different storage classes.

        Args:
            query: SQL query string
            params: Query parameters tuple (optional)

        Returns:
            list: Query results as list of dictionaries
        """
        return self.query_db(query, params)

# Quick Test
if __name__ == "__main__":
    # Test storage initialization
    logging.basicConfig(level=logging.INFO)
    
    # Mock config for testing
    class MockConfig:
        def __init__(self):
            self.database_path = r'E:\options_scanner\data\datalake.db'
        
        def get_storage_params(self):
            return {'retention_days': 365}
    
    try:
        config = MockConfig()
        storage = OIDStorage(config)
        print("✅ OID Storage initialized successfully")
        print("   Database path: {}".format(storage.database_path))
        
        # Test database connection
        conn = storage.get_connection()
        print("✅ Database connection successful")
        conn.close()
        
        print("✅ All storage tests passed")
        
    except Exception as e:
        print("❌ Storage test failed: {}".format(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)