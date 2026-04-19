#!/usr/bin/env python3
"""
Flow Monitor Storage (fm_storage.py)
-----------------------------------
Minimal storage layer for Flow Monitor operations.
Manages both datalake.db and fm_alerts.db with simple operations.

Handles:
- Option contract storage with scan_timestamp
- Alert database creation and management
- Basic retry logic for database locking
- EST/DST-aware timestamp handling
- Consistent decimal formatting (2-4 decimal places max)

No abstractions - direct SQL operations for reliability.

Author: Ben (with assistance from Claude)
Date: 2025-06-26
Updated: 2025-07-20 with updated flow_alerts schema
Updated: 2025-09-24 with decimal formatting utility
"""

import sqlite3
import logging
import time
from tools.decimal_formatter import clean_database_row, format_price, format_greek, format_ratio, format_score
from tools.autofix import handle_error
import os
from pathlib import Path
import sys
from datetime import timedelta

# Debug the path calculation
def get_project_root():
    """Get the root directory of the project"""
    current_file = os.path.abspath(__file__)    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

project_root = get_project_root()
tools_dir = os.path.join(project_root, 'tools')

if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

# Now try the import
from timezone_utils import eastern_isoformat

class FlowMonitorStorage:
    def __init__(self, config):
        """Initialize storage with database path"""
        self.datalake_path = config.database_path
        logging.debug("FlowMonitorStorage initialized with datalake: {}".format(self.datalake_path))
        self._ensure_schema()
        
    def _ensure_schema(self):
        """Add columns that may not exist yet (idempotent migrations)."""
        migrations = [
            "ALTER TABLE flow_alerts ADD COLUMN iv_percentile_30d REAL",
            "ALTER TABLE flow_alerts ADD COLUMN roll_detected BOOLEAN DEFAULT 0",
            "ALTER TABLE flow_alerts ADD COLUMN roll_counterpart_details TEXT",
        ]
        try:
            conn = sqlite3.connect(self.datalake_path)
            for sql in migrations:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # Column already exists
            conn.commit()
            conn.close()
        except Exception as e:
            logging.debug("Schema migration check: {}".format(e))

    def get_connection(self):
        """Return database connection with WAL mode and tuned page cache

        Returns:
            sqlite3.Connection with WAL mode enabled and performance PRAGMAs
        """
        conn = sqlite3.connect(self.datalake_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
        conn.execute('PRAGMA cache_size=-256000')       # 256MB page cache (default 8MB starves 11GB DB with 5 indexes)
        conn.execute('PRAGMA wal_autocheckpoint=0')      # Disable auto-checkpoint; explicit checkpoint after writes handles it
        conn.execute('PRAGMA synchronous=NORMAL')        # Safe in WAL mode, reduces fsync (scan data is re-collectable)
        return conn

    
    def _execute_with_retry(self, operation, max_retries=5):
        """Execute database operation with retry logic for locking

        Args:
            operation: Function that takes a connection and returns result
            max_retries: Maximum number of retry attempts (default 5 for agent contention)

        Returns:
            Operation result or False on failure
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    return operation(conn)

            except sqlite3.OperationalError as e:
                last_error = e
                if "database is locked" in str(e).lower():
                    # Increased backoff to handle agent tracker contention during bulk inserts
                    # Pattern: 1s, 2s, 4s, 8s, 16s (total ~31s, works with 30s busy_timeout)
                    wait_time = 1.0 * (2 ** attempt)
                    logging.warning("Database locked, retrying in {}s (attempt {}/{})".format(
                        wait_time, attempt + 1, max_retries))
                    time.sleep(wait_time)
                    continue
                else:
                    logging.error("Database error: {}".format(e))
                    return False
            except sqlite3.DatabaseError as e:
                error_msg = str(e).lower()
                if "malformed" in error_msg or "corrupt" in error_msg:
                    logging.critical("FM: DATABASE CORRUPTION DETECTED: {}".format(e))
                    logging.critical("FM: Emergency stop. Run: python data/health/repair_option_contracts.py")
                    handle_error(
                        error_type='fm_database_corruption',
                        context={
                            'exception_type': type(e).__name__,
                            'error_message': str(e),
                            'database_path': str(self.db_path)
                        },
                        severity='CRITICAL'
                    )
                    # handle_error calls sys.exit(1) — never reaches here
                logging.error("Database error in operation: {}".format(e))
                return False
            except Exception as e:
                logging.error("Unexpected error in database operation: {}".format(e))
                return False

        logging.error("Database operation failed after {} retries: {}".format(max_retries, last_error))
        return False
    
    def store_option_contracts(self, contracts_data, scan_timestamp):
        """Store option contracts with scan_timestamp

        Args:
            contracts_data: List of contract dictionaries
            scan_timestamp: ISO timestamp string for this scan

        Returns:
            bool: True if successful, False otherwise
        """
        if not contracts_data:
            logging.warning("No contracts data to store")
            return True

        # DIAGNOSTIC: Deduplicate batch data before insertion
        original_count = len(contracts_data)
        seen_hashes = set()
        deduplicated_data = []
        duplicates_found = []

        for contract in contracts_data:
            contract_hash = contract.get('contract_hash')
            if not contract_hash:
                logging.warning("Contract missing contract_hash, skipping: {}".format(contract))
                continue

            if contract_hash in seen_hashes:
                # Track duplicate for logging
                duplicates_found.append({
                    'hash': contract_hash,
                    'symbol': contract.get('symbol'),
                    'strike': contract.get('strike'),
                    'expiration': contract.get('expiration_date'),
                    'type': contract.get('option_type')
                })
            else:
                seen_hashes.add(contract_hash)
                deduplicated_data.append(contract)

        if duplicates_found:
            # BATCHFIX 2026-01-14: Changed from ERROR to WARNING since duplicates are
            # successfully handled (deduplicated before DB insert). This is an upstream
            # API data quality issue (Tradier returning duplicate contracts for some symbols
            # like MMC), not a system failure. No autofix trigger needed since the system
            # handles this gracefully - data integrity is preserved.
            logging.warning("⚠️ Deduplicated {} duplicate contracts from API response before DB insert".format(len(duplicates_found)))
            logging.debug("Duplicate details (first 10): {}".format(duplicates_found[:10]))
        else:
            logging.debug("No duplicates found in batch - proceeding with {} contracts".format(len(deduplicated_data)))

        # Use deduplicated data for insertion
        contracts_data = deduplicated_data

        def _store_operation(conn):
            cursor = conn.cursor()
            
            # Insert contracts with scan_timestamp and time-series metrics
            insert_sql = '''
                INSERT INTO flow_options_scans (
                    contract_hash,
                    scan_timestamp,
                    trade_date,
                    symbol,
                    strike,
                    expiration_date,
                    option_type,
                    moneyness,
                    dte,
                    open_interest,
                    bid,
                    ask,
                    volume,
                    volume_change,
                    volume_change_pct,
                    underlying_price,
                    underlying_change,
                    underlying_change_pct,
                    last_price,
                    price_change,
                    price_change_pct,
                    option_leverage,
                    iv,
                    iv_change,
                    iv_change_pct,
                    delta,
                    gamma,
                    theta,
                    vega,
                    premium_value,
                    flow_percentage,
                    volume_surprise_factor,
                    significance_score,
                    alert_threshold_met,
                    alert_reason,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            # Get current EST timestamp for created_at
            from timezone_utils import eastern_isoformat
            current_time = eastern_isoformat()
            
            # Prepare batch data for executemany()
            # DEBUG: timing breakpoints to diagnose variable storage duration
            _t_prep_start = time.time()
            batch_values = []
            for contract in contracts_data:
                try:
                    # Apply decimal formatting safety net to ensure compliance
                    contract = clean_database_row(contract)
                    values = (
                        contract.get('contract_hash'),                   # 1
                        scan_timestamp,                                  # 2
                        contract.get('trade_date'),                      # 3
                        contract.get('symbol'),                          # 4
                        contract.get('strike') or 0.0,                   # 5
                        contract.get('expiration_date'),                 # 6
                        contract.get('option_type'),                     # 7
                        contract.get('moneyness'),                       # 8
                        contract.get('days_to_expiration') or 0,         # 9 → dte
                        contract.get('open_interest', 0),                # 10
                        format_price(contract.get('bid') or 0.0),        # 11
                        format_price(contract.get('ask') or 0.0),        # 12
                        contract.get('volume', 0),                       # 13
                        contract.get('volume_change'),                   # 14 - NEW time-series
                        contract.get('volume_change_pct'),               # 15 - NEW time-series
                        format_price(contract.get('underlying_price') or 0.0), # 16
                        contract.get('underlying_change'),               # 17 - NEW time-series
                        contract.get('underlying_change_pct'),           # 18 - NEW time-series
                        format_price(contract.get('last_price') or 0.0), # 19
                        contract.get('price_change'),                    # 20 - NEW time-series
                        contract.get('price_change_pct'),                # 21 - NEW time-series
                        contract.get('option_leverage'),                 # 22 - NEW time-series
                        format_greek(contract.get('implied_volatility') or 0.0), # 23 → iv
                        contract.get('iv_change'),                       # 24 - NEW time-series
                        contract.get('iv_change_pct'),                   # 25 - NEW time-series
                        format_greek(contract.get('delta') or 0.0),      # 26
                        format_greek(contract.get('gamma') or 0.0),      # 27
                        format_greek(contract.get('theta') or 0.0),      # 28
                        format_greek(contract.get('vega') or 0.0),       # 29
                        contract.get('premium_value'),                   # 30
                        contract.get('flow_percentage'),                 # 31
                        contract.get('volume_surprise_factor'),          # 32
                        contract.get('significance_score'),              # 33
                        contract.get('alert_threshold_met'),             # 34
                        contract.get('alert_reason'),                    # 35
                        current_time                                     # 36 - created_at
                    )
                    batch_values.append(values)

                except Exception as e:
                    logging.warning("Skipping contract for {} {}: {}".format(
                        contract.get('symbol', 'UNKNOWN'),
                        contract.get('strike', 'UNKNOWN'),
                        e))
                    logging.debug("Contract data causing error: {}".format(contract))
                    continue
            _t_prep = time.time() - _t_prep_start

            # PERFORMANCE FIX: Use executemany() for batch insert
            # DEBUG: timing the INSERT separately from commit
            _t_insert_start = time.time()
            cursor.executemany(insert_sql, batch_values)
            records_inserted = cursor.rowcount
            _t_insert = time.time() - _t_insert_start

            _t_commit_start = time.time()
            conn.commit()
            _t_commit = time.time() - _t_commit_start

            logging.debug("Stored {} option contracts with scan_timestamp: {} (batch operation)".format(
                records_inserted, scan_timestamp))
            # DEBUG: DB write phase breakdown — remove/suppress when diagnosis complete
            logging.info("DEBUG DB Write: prep={:.1f}s, insert={:.1f}s, commit={:.1f}s ({:,} rows)".format(
                _t_prep, _t_insert, _t_commit, records_inserted))
            return True

        # Execute storage operation
        result = self._execute_with_retry(_store_operation)

        # WAL checkpoint after successful write to prevent bloat
        # This creates a clean break before analysis/alert phases
        if result:
            try:
                _t_wal_start = time.time()
                with self.get_connection() as conn:
                    wal_result = conn.execute('PRAGMA wal_checkpoint(RESTART)').fetchone()
                _t_wal = time.time() - _t_wal_start
                busy, wal_pages, checkpointed = wal_result if wal_result else (None, None, None)
                # DEBUG: WAL checkpoint diagnostics — remove/suppress when diagnosis complete
                # busy: 0=success, 1=couldn't get lock (WAL keeps growing!)
                # pages: total WAL size in pages. Growing = problem. Stable ~2000 = healthy.
                # checkpointed: pages merged back to DB. Should equal pages. 0 = nothing merged.
                wal_status = "OK" if busy == 0 and wal_pages == checkpointed else "BLOCKED" if busy == 1 else "PARTIAL"
                logging.info("DEBUG WAL checkpoint: {:.1f}s | {} | busy={}, pages={}, checkpointed={}".format(
                    _t_wal, wal_status, busy, wal_pages, checkpointed))
            except Exception as e:
                logging.warning("WAL checkpoint failed (non-critical): {}".format(e))

        return result

    def save_alert(self, alert_data):
        """Save alert to flow_alerts table with complete contract data
        
        Args:
            alert_data: Dictionary with complete alert and contract information
            
        Returns:
            bool: True if successful, False otherwise
        """
        def _save_operation(conn):
            cursor = conn.cursor()
            
            insert_sql = '''
                INSERT INTO flow_alerts (
                    alert_timestamp, scan_timestamp, trade_date, symbol, strike,
                    expiration_date, option_type, volume, open_interest,
                    last_price, underlying_price, iv, delta, gamma, theta, vega,
                    dte, moneyness, premium_value,
                    flow_percentage, volume_surprise_factor, significance_score,
                    alert_reason, alert_level,
                    max_prof_1d_pct, max_prof_3d_pct, max_prof_7d_pct, max_prof_14d_pct, max_prof_30d_pct,
                    days_to_max_prof, peak_hour_est,
                    max_loss_1d_pct, max_loss_3d_pct, max_loss_7d_pct, max_loss_14d_pct, max_loss_30d_pct,
                    days_to_max_loss, evaluation_status, final_quality_score, last_evaluated_date,
                    contract_hash, scan_interval_seconds,
                    iv_percentile_30d,
                    roll_detected, roll_counterpart_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            # Clean all decimal values using our formatter
            cleaned_data = clean_database_row(alert_data)

            values = (
                cleaned_data.get('alert_timestamp'),
                cleaned_data.get('scan_timestamp'),
                cleaned_data.get('trade_date'),
                cleaned_data.get('symbol'),
                cleaned_data.get('strike'),
                cleaned_data.get('expiration_date'),
                cleaned_data.get('option_type'),
                cleaned_data.get('volume'),
                cleaned_data.get('open_interest'),
                cleaned_data.get('last_price'),
                cleaned_data.get('underlying_price'),
                cleaned_data.get('implied_volatility'),  # Maps to iv
                cleaned_data.get('delta'),
                cleaned_data.get('gamma'),
                cleaned_data.get('theta'),
                cleaned_data.get('vega'),
                cleaned_data.get('days_to_expiration'),  # Maps to dte
                cleaned_data.get('moneyness'),
                cleaned_data.get('premium_value'),
                cleaned_data.get('flow_percentage'),
                cleaned_data.get('volume_surprise_factor'),
                cleaned_data.get('significance_score'),
                cleaned_data.get('alert_reason'),
                cleaned_data.get('alert_level', 'MEDIUM'),
                cleaned_data.get('max_profit_1day'),  # Maps to max_prof_1d_pct
                cleaned_data.get('max_profit_3day'),  # Maps to max_prof_3d_pct
                cleaned_data.get('max_profit_7day'),  # Maps to max_prof_7d_pct
                cleaned_data.get('max_profit_14day'),  # Maps to max_prof_14d_pct
                cleaned_data.get('max_profit_30day'),  # Maps to max_prof_30d_pct
                cleaned_data.get('days_to_max_gain'),  # Maps to days_to_max_prof
                cleaned_data.get('peak_hour_est'),
                cleaned_data.get('max_loss_1day'),  # Maps to max_loss_1d_pct
                cleaned_data.get('max_loss_3day'),  # Maps to max_loss_3d_pct
                cleaned_data.get('max_loss_7day'),  # Maps to max_loss_7d_pct
                cleaned_data.get('max_loss_14day'),  # Maps to max_loss_14d_pct
                cleaned_data.get('max_loss_30day'),  # Maps to max_loss_30d_pct
                cleaned_data.get('days_to_max_loss'),
                cleaned_data.get('evaluation_status'),
                cleaned_data.get('final_quality_score'),
                cleaned_data.get('last_evaluated_date'),
                # Generate contract hash: SYMBOL|STRIKE|EXPIRATION|TYPE
                "{}|{}|{}|{}".format(
                    alert_data.get('symbol', ''),
                    alert_data.get('strike', ''),
                    alert_data.get('expiration_date', ''),
                    alert_data.get('option_type', '').upper()
                ),
                cleaned_data.get('scan_interval_seconds'),
                cleaned_data.get('iv_percentile_30d'),
                cleaned_data.get('roll_detected', 0),
                cleaned_data.get('roll_counterpart_details')
            )
            
            cursor.execute(insert_sql, values)
            conn.commit()
            
            logging.debug("Complete alert saved for {} {} with score {:.2f}".format(
                alert_data.get('symbol'),
                alert_data.get('strike'),
                alert_data.get('significance_score')
            ))
            return True
        
        return self._execute_with_retry(_save_operation)
    
    def get_recent_alerts(self, hours_back=4):
        """Get recent alerts from flow_alerts table for deduplication
        
        Args:
            hours_back: Number of hours to look back for recent alerts
            
        Returns:
            list: List of recent alert dictionaries with required fields
        """
        try:
            from timezone_utils import now_eastern
            from datetime import timedelta
            
            # Calculate cutoff time
            cutoff_time = now_eastern() - timedelta(hours=hours_back)
            cutoff_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S')
            
            query = '''
                SELECT 
                    symbol,
                    strike,
                    expiration_date,
                    option_type,
                    volume,
                    significance_score,
                    alert_timestamp
                FROM flow_alerts
                WHERE datetime(alert_timestamp) >= datetime(?)
                ORDER BY alert_timestamp DESC
            '''
            
            results = self.query_with_params(query, (cutoff_str,))
            
            logging.debug("Found {} recent alerts within {} hours".format(len(results), hours_back))
            return results
            
        except Exception as e:
            logging.error("Error getting recent alerts: {}".format(e))
            return []  # Return empty list on error to be safe
    
    def query_with_params(self, query, params=()):
        """Execute SELECT query and return results as list of dictionaries
        
        Args:
            query: SQL SELECT query string
            params: Query parameters tuple
            
        Returns:
            list: List of dictionaries with column names as keys
        """
        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except sqlite3.Error as e:
            logging.error("Query failed: {} | Error: {}".format(query[:100], e))
            return []

    def batch_update(self, query, params_list):
        """Execute batch UPDATE operation
        
        Args:
            query: SQL UPDATE query string with placeholders
            params_list: List of parameter tuples for batch execution
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not params_list:
            logging.warning("No parameters provided for batch update")
            return True
        
        def _batch_operation(conn):
            cursor = conn.cursor()
            
            # Debug: Log the query and first parameter set
            logging.debug("Executing batch update query: {}".format(query))
            logging.debug("First parameter set: {}".format(params_list[0] if params_list else "None"))
            logging.debug("Total parameter sets: {}".format(len(params_list)))
            
            # Try a single update first to test the query
            try:
                cursor.execute(query, params_list[0])
                logging.debug("Single test update successful")
            except sqlite3.Error as e:
                logging.error("Single test update failed: {}".format(e))
                raise e
            
            # If single update works, try batch update
            cursor.executemany(query, params_list)
            rows_affected = cursor.rowcount
            conn.commit()
            
            logging.debug("Batch update completed: {} rows affected".format(rows_affected))
            return True

        return self._execute_with_retry(_batch_operation)

        def _batch_operation(conn):
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            rows_affected = cursor.rowcount
            conn.commit()

            logging.debug("Batch update completed: {} rows affected".format(rows_affected))
            return True

        return self._execute_with_retry(_batch_operation)

    def get_latest_scan_timestamp(self):
        """Get the most recent scan timestamp from flow_options_scans

        Returns:
            str: Latest scan timestamp or None if no scans found
        """
        query = '''
            SELECT scan_timestamp
            FROM flow_options_scans
            WHERE scan_timestamp IS NOT NULL AND scan_timestamp != ''
            ORDER BY scan_timestamp DESC
            LIMIT 1
        '''
        
        results = self.query_with_params(query)
        if results:
            return results[0]['scan_timestamp']
        return None

    def get_top_contracts_by_score(self, scan_timestamp, limit=10):
        """Get top contracts by significance score for testing

        Args:
            scan_timestamp: Scan timestamp to query
            limit: Maximum number of contracts to return

        Returns:
            list: List of top-scoring contract dictionaries
        """
        query = '''
            SELECT symbol, strike, option_type, volume, significance_score,
                   premium_value, volume_surprise_factor, alert_reason
            FROM flow_options_scans
            WHERE scan_timestamp = ?
                AND significance_score IS NOT NULL
            ORDER BY significance_score DESC, volume DESC
            LIMIT ?
        '''
        
        return self.query_with_params(query, (scan_timestamp, limit))

    """
    Add these methods to your existing fm_storage.py file
    These are the methods that fm_evaluator.py expects but aren't implemented yet
    """

    def get_active_alerts_for_evaluation(self, cutoff_hours=4):
        """Get alerts that need evaluation (older than cutoff_hours, within tracking window)"""
        try:
            from timezone_utils import now_eastern
            from datetime import timedelta
            
            cutoff_time = now_eastern() - timedelta(hours=cutoff_hours)
            window_start = now_eastern() - timedelta(days=30)  # 30-day tracking window
            
            query = '''
                SELECT * FROM flow_alerts 
                WHERE datetime(alert_timestamp) < ?
                AND datetime(alert_timestamp) > ?
                AND (evaluation_status IS NULL OR evaluation_status = 'active')
                AND datetime(expiration_date) > datetime('now')
                ORDER BY alert_timestamp ASC
            '''
            
            # Convert timezone-aware datetimes to strings for SQLite comparison
            params = (cutoff_time.strftime('%Y-%m-%d %H:%M:%S'), window_start.strftime('%Y-%m-%d %H:%M:%S'))
            return self.query_with_params(query, params)
            
        except Exception as e:
            logging.error("Error getting alerts for evaluation: {}".format(e))
            return []

    def update_alert_performance(self, alert_id, performance_data):
        """Update performance metrics for specific alert"""
        try:
            if not performance_data:
                return False
            
            hours_elapsed = performance_data['hours_elapsed']
            gain_pct = performance_data['performance_pct']
            
            # SQLite doesn't have GREATEST, so we need to use MAX with CASE statements
            updates = []
            params = []
            
            if hours_elapsed <= 1 and gain_pct > 0:
                updates.append("max_profit_1hr = MAX(COALESCE(max_profit_1hr, 0), ?)")
                params.append(gain_pct)
            
            if hours_elapsed <= 4 and gain_pct > 0:
                updates.append("max_profit_4hr = MAX(COALESCE(max_profit_4hr, 0), ?)")
                params.append(gain_pct)
            
            if hours_elapsed <= 24 and gain_pct > 0:
                updates.append("max_profit_1day = MAX(COALESCE(max_profit_1day, 0), ?)")
                params.append(gain_pct)
            
            if hours_elapsed <= 72 and gain_pct > 0:
                updates.append("max_profit_3day = MAX(COALESCE(max_profit_3day, 0), ?)")
                params.append(gain_pct)
            
            if hours_elapsed <= 168 and gain_pct > 0:  # 7 days
                updates.append("max_profit_7day = MAX(COALESCE(max_profit_7day, 0), ?)")
                params.append(gain_pct)
            
            if hours_elapsed <= 720 and gain_pct > 0:  # 30 days
                updates.append("max_profit_30day = MAX(COALESCE(max_profit_30day, 0), ?)")
                params.append(gain_pct)
            
            if not updates:
                return True  # No updates needed
            
            # Always update last_evaluated_date
            from timezone_utils import eastern_isoformat
            updates.append("last_evaluated_date = ?")
            params.append(eastern_isoformat())
            
            params.append(alert_id)  # For WHERE clause
            
            sql = "UPDATE flow_alerts SET {} WHERE id = ?".format(", ".join(updates))
            
            return self._execute_with_retry(lambda conn: conn.execute(sql, params))
            
        except Exception as e:
            logging.error("Error updating performance for alert {}: {}".format(alert_id, e))
            return False

    def mark_alert_evaluation_complete(self, alert_id, final_metrics, completion_reason):
        """Mark alert evaluation as complete with final scores"""
        try:
            from timezone_utils import eastern_isoformat
            
            def update_operation(conn):
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE flow_alerts 
                    SET evaluation_status = 'completed',
                        final_quality_score = ?,
                        last_evaluated_date = ?
                    WHERE id = ?
                ''', (
                    final_metrics.get('quality_score', 0),
                    eastern_isoformat(),
                    alert_id
                ))
                return cursor.rowcount > 0
            
            return self._execute_with_retry(update_operation)
            
        except Exception as e:
            logging.error("Error marking alert {} complete: {}".format(alert_id, e))
            return False

    def create_contract_tracking(self, alert):
        """Create tracking record for alert's contract (if not exists)"""
        try:
            from timezone_utils import eastern_isoformat
            
            def create_operation(conn):
                cursor = conn.cursor()
                
                # Check if tracking already exists
                cursor.execute('SELECT id FROM alert_contract_tracking WHERE alert_id = ?', (alert['id'],))
                if cursor.fetchone():
                    return True  # Already exists
                
                # Create new tracking record
                cursor.execute('''
                    INSERT INTO alert_contract_tracking 
                    (alert_id, symbol, strike, expiration_date, option_type,
                     tracking_start_date, alert_timestamp, scan_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    alert['id'],
                    alert['symbol'],
                    alert['strike'],
                    alert['expiration_date'],
                    alert['option_type'],
                    eastern_isoformat(),
                    alert['alert_timestamp'],
                    alert.get('scan_timestamp', eastern_isoformat())
                ))
                
                return True
            
            return self._execute_with_retry(create_operation)
            
        except Exception as e:
            logging.error("Error creating tracking for alert {}: {}".format(alert.get('id', 'UNKNOWN'), e))
            return False

    def update_contract_tracking(self, alert_id, success=True):
        """Update contract tracking statistics"""
        try:
            from timezone_utils import eastern_isoformat
            
            def update_operation(conn):
                cursor = conn.cursor()
                
                if success:
                    cursor.execute('''
                        UPDATE alert_contract_tracking 
                        SET successful_collections = successful_collections + 1,
                            last_price_update = ?
                        WHERE alert_id = ?
                    ''', (eastern_isoformat(), alert_id))
                else:
                    cursor.execute('''
                        UPDATE alert_contract_tracking 
                        SET failed_collections = failed_collections + 1
                        WHERE alert_id = ?
                    ''', (alert_id,))
                
                return cursor.rowcount > 0
            
            return self._execute_with_retry(update_operation)
            
        except Exception as e:
            logging.error("Error updating tracking for alert {}: {}".format(alert_id, e))
            return False

# Quick Test
if __name__ == "__main__":
    # Test storage initialization
    logging.basicConfig(level=logging.INFO)
    
    # Mock config for testing
    class MockConfig:
        def __init__(self):
            self.database_path = r'd:\options_scanner\data\datalake.db'
    
    try:
        config = MockConfig()
        storage = FlowMonitorStorage(config)
        print("✅ Storage initialized successfully")
        print("   Datalake path: {}".format(storage.datalake_path))
        
        # Test database connection
        datalake_conn = storage.get_connection()
        print("✅ Database connection successful")
        datalake_conn.close()
        
        # Test recent alerts retrieval from flow_alerts table
        recent = storage.get_recent_alerts(24)
        print("✅ Recent alerts query successful ({} alerts found in flow_alerts table)".format(len(recent)))
        
        # Test latest scan timestamp
        latest_scan = storage.get_latest_scan_timestamp()
        if latest_scan:
            print("✅ Latest scan timestamp: {}".format(latest_scan))
        else:
            print("ℹ️  No scan timestamps found (database may be empty)")
        
    except Exception as e:
        print("❌ Storage test failed: {}".format(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)
