#!/usr/bin/env python3
"""
Flow Monitor Backfill Evaluator (fm_backfill_evaluator.py)
---------------------------------------------------------
Backfill historical alert performance data by evaluating completed/expired alerts.
Designed for batch processing without real-time constraints.

Reuses evaluation logic from fm_evaluator.py but removes:
- Time cutoffs (evaluates any age alerts)  
- Real-time tracking and mini-collector logic
- Ongoing state management

Usage:
python fm_backfill_evaluator.py --all                    # All alerts
python fm_backfill_evaluator.py --active-only            # Active alerts only (540)
python fm_backfill_evaluator.py --completed-only         # Completed alerts only
python fm_backfill_evaluator.py --symbols NVDA           # Test on specific symbols
python fm_backfill_evaluator.py --force                  # Recalculate existing data

Author: Ben (with assistance from Claude) 
Date: 2025-09-02
"""

import os
import sys
import argparse
import sqlite3
import logging
import time
from datetime import datetime, timedelta

# Add project paths
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

# Add tools and core directories
tools_dir = os.path.join(project_root, 'tools')
core_dir = os.path.join(project_root, 'core') 
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)
if core_dir not in sys.path:
    sys.path.insert(0, core_dir)

from timezone_utils import now_eastern, eastern_isoformat
from strategies.flow_monitor.fm_storage import FlowMonitorStorage


class SimpleConfig:
    """Simple config object for storage initialization"""
    def __init__(self):
        self.database_path = os.path.join(project_root, 'data', 'datalake.db')


class BackfillEvaluator:
    """Backfill alert performance evaluation without real-time constraints"""
    
    def __init__(self, symbols=None, force_recalc=False):
        """Initialize backfill evaluator
        
        Args:
            symbols: List of symbols to filter (None for all)
            force_recalc: Recalculate even if data exists
        """
        self.symbols = symbols if symbols else []
        self.force_recalc = force_recalc
        
        # Initialize storage with simple config
        config = SimpleConfig()
        self.storage = FlowMonitorStorage(config)
        
        # Setup logging
        self._setup_logging()
        
        # Statistics
        self.stats = {
            'alerts_found': 0,
            'alerts_processed': 0,
            'alerts_updated': 0,
            'alerts_skipped': 0,
            'errors': 0,
            'start_time': time.time()
        }
        
        print("\n" + "="*70)
        print("FLOW MONITOR BACKFILL EVALUATOR")
        print("="*70)
        print("Database: {}".format(self.storage.datalake_path))
        if self.symbols:
            print("Symbols filter: {}".format(", ".join(self.symbols)))
        print("Force recalculation: {}".format("Yes" if self.force_recalc else "No"))
        print("Started: {}".format(now_eastern().strftime("%Y-%m-%d %H:%M:%S EST")))
        print("="*70)
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_dir = os.path.join(project_root, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'fm_backfill_{}.log'.format(
            now_eastern().strftime("%Y-%m-%d_%H-%M")))
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
    
    def get_alerts_for_backfill(self, status_filter=None):
        """Get alerts that need backfill evaluation
        
        Args:
            status_filter: 'active', 'completed', or None for both
        """
        try:
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Build query with filters
                conditions = []
                params = []
                
                # Status filter
                if status_filter == 'active':
                    conditions.append("evaluation_status = 'active'")
                elif status_filter == 'completed':
                    conditions.append("evaluation_status = 'completed'")
                else:
                    conditions.append("evaluation_status IN ('active', 'completed')")
                
                # Symbol filter
                if self.symbols:
                    placeholders = ','.join('?' * len(self.symbols))
                    conditions.append("symbol IN ({})".format(placeholders))
                    params.extend(self.symbols)
                
                # Only expired contracts (can evaluate fully)
                conditions.append("datetime(expiration_date) < datetime('now')")
                
                # Force recalc or missing data filter
                if not self.force_recalc:
                    conditions.append("(max_prof_1d_pct IS NULL OR max_prof_14d_pct IS NULL OR days_to_max_prof IS NULL)")
                
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                
                query = """
                    SELECT * FROM flow_alerts
                    {}
                    ORDER BY alert_timestamp ASC
                """.format(where_clause)
                
                cursor.execute(query, params)
                alerts = [dict(row) for row in cursor.fetchall()]
                
                print("Found {} alerts for backfill evaluation".format(len(alerts)))
                self.stats['alerts_found'] = len(alerts)
                
                return alerts
                
        except Exception as e:
            self.logger.error("Error getting alerts for backfill: {}".format(e))
            return []
    
    def get_timeframe_performance_data(self, alert, hours_window):
        """Get best option price within timeframe window - adapted from fm_evaluator.py"""
        try:
            contract_hash = "{}|{}|{}|{}".format(
                alert['symbol'],
                alert['strike'],
                alert['expiration_date'],
                alert['option_type'].upper()
            )
            
            # Calculate time window
            alert_time = datetime.fromisoformat(alert['alert_timestamp'])
            end_time = alert_time + timedelta(hours=hours_window)
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get price data within window
                cursor.execute('''
                    SELECT MAX(last_price) as best_price, 
                           COUNT(*) as data_points,
                           datetime(scan_timestamp) as best_timestamp
                    FROM flow_options_scans
                    WHERE contract_hash = ?
                      AND datetime(scan_timestamp) >= datetime(?)
                      AND datetime(scan_timestamp) <= datetime(?)
                      AND last_price IS NOT NULL
                      AND last_price > 0
                ''', (contract_hash, alert['alert_timestamp'], end_time.isoformat()))
                
                row = cursor.fetchone()
                if row and row['best_price']:
                    return {
                        'best_option_price': row['best_price'],
                        'data_points': row['data_points'],
                        'best_timestamp': row['best_timestamp']
                    }
                
                return None
                
        except Exception as e:
            self.logger.debug("Error getting timeframe data for alert {}: {}".format(alert.get('id'), e))
            return None
    
    def calculate_days_to_max_gain(self, alert):
        """Calculate days to maximum gain - adapted from fm_evaluator.py"""
        try:
            contract_hash = "{}|{}|{}|{}".format(
                alert['symbol'],
                alert['strike'], 
                alert['expiration_date'],
                alert['option_type'].upper()
            )
            
            alert_time = datetime.fromisoformat(alert['alert_timestamp'])
            alert_option_price = self._get_alert_option_price(alert)
            
            if not alert_option_price:
                return None, None
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Find highest price and when it occurred
                cursor.execute('''
                    SELECT last_price, scan_timestamp,
                           datetime(scan_timestamp) as scan_dt
                    FROM flow_options_scans
                    WHERE contract_hash = ?
                      AND datetime(scan_timestamp) >= datetime(?)
                      AND last_price IS NOT NULL
                      AND last_price > ?
                    ORDER BY last_price DESC
                    LIMIT 1
                ''', (contract_hash, alert['alert_timestamp'], alert_option_price))
                
                peak_row = cursor.fetchone()
                if not peak_row:
                    return 0, None  # No gains found
                
                # Calculate days difference
                peak_time = datetime.fromisoformat(peak_row['scan_timestamp'])
                days_diff = (peak_time - alert_time).total_seconds() / 86400.0
                
                # Round to full calendar days
                days_to_max = max(0, round(days_diff))
                
                # Get hour of day for peak (EST)
                peak_hour_est = peak_time.hour
                
                return days_to_max, peak_hour_est
                
        except Exception as e:
            self.logger.debug("Error calculating days to max gain for alert {}: {}".format(alert.get('id'), e))
            return None, None
    
    def _get_alert_option_price(self, alert):
        """Get the option price at alert time"""
        try:
            # Use last_price from alert if available
            if alert.get('last_price') and alert['last_price'] > 0:
                return alert['last_price']
            
            # Use bid/ask midpoint as fallback
            if alert.get('bid') and alert.get('ask'):
                return (alert['bid'] + alert['ask']) / 2
            
            # Use ask price as final fallback
            if alert.get('ask') and alert['ask'] > 0:
                return alert['ask']
            
            return None
            
        except Exception:
            return None
    
    def update_alert_performance(self, alert_id, timeframe_gains, days_to_max_prof, peak_hour_est):
        """Update alert with calculated performance metrics"""
        try:
            with sqlite3.connect(self.storage.datalake_path) as conn:
                cursor = conn.cursor()
                
                # Map timeframes to database columns
                timeframe_map = {
                    1: 'max_profit_1hr',
                    4: 'max_profit_4hr', 
                    24: 'max_prof_1d_pct',
                    72: 'max_prof_3d_pct',
                    168: 'max_prof_7d_pct',
                    336: 'max_prof_14d_pct',
                    720: 'max_prof_30d_pct'
                }
                
                # Build update query
                updates = []
                params = []
                
                # Add timeframe gains
                for hours, gain_pct in timeframe_gains.items():
                    if hours in timeframe_map:
                        column = timeframe_map[hours]
                        updates.append("{} = ?".format(column))
                        params.append(gain_pct)
                
                # Add days to max gain
                if days_to_max_prof is not None:
                    updates.append("days_to_max_prof = ?")
                    params.append(days_to_max_prof)
                
                # Add peak hour EST
                if peak_hour_est is not None:
                    updates.append("peak_hour_est = ?")
                    params.append(peak_hour_est)
                
                # Update last evaluated timestamp
                updates.append("last_evaluated_date = ?")
                params.append(eastern_isoformat())
                
                if updates:
                    params.append(alert_id)
                    cursor.execute('''
                        UPDATE flow_alerts
                        SET {}
                        WHERE id = ?
                    '''.format(", ".join(updates)), params)
                    
                    if cursor.rowcount > 0:
                        conn.commit()
                        return True
                
                return False
                
        except Exception as e:
            self.logger.error("Error updating alert {}: {}".format(alert_id, e))
            return False
    
    def process_alert(self, alert):
        """Process single alert for backfill evaluation"""
        try:
            alert_id = alert['id']
            symbol = alert['symbol']
            
            # Check if we should skip (not forcing and has data)
            if not self.force_recalc:
                if (alert.get('max_prof_1d_pct') is not None and 
                    alert.get('max_prof_14d_pct') is not None and
                    alert.get('days_to_max_prof') is not None):
                    self.stats['alerts_skipped'] += 1
                    return True
            
            # Calculate performance for each timeframe
            timeframes = [1, 4, 24, 72, 168, 336, 720]  # 1hr to 30day
            timeframe_gains = {}
            
            alert_option_price = self._get_alert_option_price(alert)
            if not alert_option_price:
                self.logger.warning("No option price available for alert {} ({})".format(alert_id, symbol))
                self.stats['alerts_skipped'] += 1
                return False
            
            # Get performance for each timeframe
            for hours in timeframes:
                performance_data = self.get_timeframe_performance_data(alert, hours)
                if performance_data:
                    gain_pct = ((performance_data['best_option_price'] - alert_option_price) / alert_option_price) * 100
                    timeframe_gains[hours] = gain_pct
            
            # Calculate days to max gain and peak hour
            days_to_max_prof, peak_hour_est = self.calculate_days_to_max_gain(alert)
            
            # Update database
            if timeframe_gains or days_to_max_prof is not None:
                success = self.update_alert_performance(alert_id, timeframe_gains, days_to_max_prof, peak_hour_est)
                if success:
                    self.stats['alerts_updated'] += 1
                    self.logger.debug("Updated alert {} ({}) - gains: {}, days_to_max: {}".format(
                        alert_id, symbol, len(timeframe_gains), days_to_max_prof))
                else:
                    self.stats['errors'] += 1
            else:
                self.logger.warning("No performance data found for alert {} ({})".format(alert_id, symbol))
                self.stats['alerts_skipped'] += 1
            
            self.stats['alerts_processed'] += 1
            return True
            
        except Exception as e:
            self.logger.error("Error processing alert {}: {}".format(alert.get('id'), e))
            self.stats['errors'] += 1
            return False
    
    def _check_indexes(self):
        """Check and create necessary database indexes for performance"""
        try:
            with sqlite3.connect(self.storage.datalake_path) as conn:
                cursor = conn.cursor()
                
                # Check if contract_hash index exists on option_contracts
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='index' AND tbl_name='flow_options_scans' AND name='idx_oc_contract_hash_scan'
                """)

                if not cursor.fetchone():
                    print("Creating index on flow_options_scans.contract_hash for better performance...")
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_oc_contract_hash_scan
                        ON flow_options_scans(contract_hash, scan_timestamp)
                    """)
                    conn.commit()
                    print("Index created successfully")
                else:
                    print("Database indexes verified")
                    
        except Exception as e:
            self.logger.warning("Index check failed: {}".format(e))
    
    def run_backfill(self, status_filter=None):
        """Run backfill evaluation on specified alerts"""
        print("\nStarting backfill evaluation...")
        
        # Check for database indexes for performance
        self._check_indexes()
        
        # Get alerts to process
        alerts = self.get_alerts_for_backfill(status_filter)
        if not alerts:
            print("No alerts found for backfill - nothing to do!")
            return True
        
        total_alerts = len(alerts)
        batch_size = 50
        
        print("Processing {} alerts in batches of {}...".format(total_alerts, batch_size))
        
        # Process in batches
        for i in range(0, total_alerts, batch_size):
            batch = alerts[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_alerts + batch_size - 1) // batch_size
            
            print("\n--- BATCH {}/{} ---".format(batch_num, total_batches))
            print("Processing alerts {}-{} ({} in batch)".format(
                i + 1, min(i + batch_size, total_alerts), len(batch)))
            
            for j, alert in enumerate(batch):
                # Progress indicator
                overall_progress = i + j + 1
                if overall_progress % 25 == 0 or overall_progress == total_alerts:
                    pct = (overall_progress / total_alerts) * 100
                    print("  Progress: {}/{} alerts ({:.1f}%)".format(overall_progress, total_alerts, pct))
                
                # Process alert with progress output
                print("    Processing {} alert {} ({}|{}|{})".format(
                    alert['symbol'], alert['id'], alert['strike'], 
                    alert['expiration_date'], alert['option_type']))
                self.process_alert(alert)
        
        # Final summary
        self._print_summary()
        return True
    
    def _print_summary(self):
        """Print backfill summary statistics"""
        elapsed = time.time() - self.stats['start_time']
        
        print("\n" + "="*70)
        print("BACKFILL EVALUATION SUMMARY")
        print("="*70)
        print("Duration: {:.1f} minutes".format(elapsed / 60))
        print("Alerts found: {:,}".format(self.stats['alerts_found']))
        print("Alerts processed: {:,}".format(self.stats['alerts_processed']))
        print("Alerts updated: {:,}".format(self.stats['alerts_updated']))
        print("Alerts skipped: {:,}".format(self.stats['alerts_skipped']))
        print("Errors: {:,}".format(self.stats['errors']))
        
        if self.stats['alerts_processed'] > 0 and elapsed > 0:
            rate = self.stats['alerts_processed'] / elapsed
            print("Processing rate: {:.1f} alerts/second".format(rate))
        
        print("="*70)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Flow Monitor Backfill Evaluator')
    parser.add_argument('--all', action='store_true',
                       help='Process all alerts (both active and completed)')
    parser.add_argument('--active-only', action='store_true', 
                       help='Process only active alerts')
    parser.add_argument('--completed-only', action='store_true',
                       help='Process only completed alerts')
    parser.add_argument('--symbols', type=str,
                       help='Comma-separated list of symbols to process (e.g., NVDA,TSLA)')
    parser.add_argument('--force', action='store_true',
                       help='Recalculate data even if it already exists')
    
    args = parser.parse_args()
    
    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',')]
    
    # Determine status filter
    status_filter = None
    if args.active_only:
        status_filter = 'active'
    elif args.completed_only:
        status_filter = 'completed'
    # args.all or no specific filter = process both (status_filter stays None)
    
    try:
        evaluator = BackfillEvaluator(symbols=symbols, force_recalc=args.force)
        success = evaluator.run_backfill(status_filter)
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n\nBackfill interrupted by user")
        return 130
    except Exception as e:
        print("\nFATAL ERROR: {}".format(e))
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())