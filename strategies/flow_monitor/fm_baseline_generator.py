#!/usr/bin/env python3
"""
Flow Monitor Baseline Generator (fm_baseline_generator.py)
---------------------------------------------------------
Calculates rolling option volume baselines from historical data.
Replaces stock volume baselines with option-specific statistics using robust median/MAD approach.

Key Features:
- 7-day rolling window for baseline calculations
- Median of log1p(volume) instead of mean for robustness
- MAD (Median Absolute Deviation) * 1.4826 for standard deviation equivalent
- Separate vol/oi ratio statistics
- Updates symbol_baselines table with option-specific values

Technical Notes:
- Uses log1p() transformation to handle zero volumes
- MAD multiplier 1.4826 makes it equivalent to standard deviation for normal distributions
- Handles legacy data (created_at) and new data (scan_timestamp) automatically
- Groups by symbol and aggregates across all contracts daily

Author: Ben (with assistance from Claude)
Date: 2025-06-27
"""

import os
import sys
import logging
import sqlite3
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import math
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string
from tools.decimal_formatter import clean_database_row, format_ratio, format_score
from core.symbols_klmn800 import get_specialty_list

# MAG7 symbols for testing
MAG7_SYMBOLS = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA']

class OptionBaselineGenerator:
    """Generates option volume baselines using robust statistics"""
    
    def __init__(self, db_path=None):
        """Initialize baseline generator with database path"""
        if db_path is None:
            # Default to project structure
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.path.join(project_root, 'data', 'datalake.db')
        
        self.db_path = db_path
        self.mad_multiplier = 1.4826  # Makes MAD equivalent to std dev for normal distribution
        
        logging.info("Option Baseline Generator initialized")
        logging.info("Database: {}".format(self.db_path))
    
    def generate_baselines(self, symbols=None, lookback_days=7, test_mode=False):
        """Generate option volume baselines for specified symbols
        
        Args:
            symbols: List of symbols to process from KLMN 800 list 
            lookback_days: Number of days to look back for baseline calculation
            test_mode: If True, only process MAG7 symbols and show detailed output
            
        Returns:
            dict: Results summary with processed symbols and statistics
        """
        if symbols is None:
            symbols = MAG7_SYMBOLS if test_mode else get_specialty_list('fm_scan')

        if test_mode:
            logging.info("TEST MODE: Processing MAG7 symbols only")
            symbols = MAG7_SYMBOLS
        
        logging.info("Generating option baselines for {} symbols ({} day window)".format(
            len(symbols), lookback_days))
        
        results = {
            'symbols_processed': 0,
            'baselines_created': 0,
            'baselines_updated': 0,
            'errors': [],
            'before_after_samples': []
        }
        
        # Calculate date range
        end_date = eastern_date_string()
        start_date = (now_eastern() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        
        logging.info("Baseline calculation period: {} to {}".format(start_date, end_date))
        
        for symbol in symbols:
            try:
                baseline_data = self._calculate_symbol_baseline(symbol, start_date, end_date)
                
                if baseline_data:
                    # Store before values for comparison
                    before_values = self._get_current_baseline(symbol) if test_mode else None
                    
                    success = self._store_symbol_baseline(symbol, baseline_data)
                    
                    if success:
                        results['symbols_processed'] += 1
                        if baseline_data.get('is_new_baseline'):
                            results['baselines_created'] += 1
                        else:
                            results['baselines_updated'] += 1
                        
                        # Store before/after for test mode
                        if test_mode and before_values:
                            after_values = self._get_current_baseline(symbol)
                            results['before_after_samples'].append({
                                'symbol': symbol,
                                'before': before_values,
                                'after': after_values,
                                'sample_size': baseline_data['sample_size']
                            })
                    
                else:
                    logging.warning("No data available for {} in {} day window".format(
                        symbol, lookback_days))
                    
            except Exception as e:
                error_msg = "Failed to process {}: {}".format(symbol, str(e))
                logging.error(error_msg)
                results['errors'].append(error_msg)
        
        # Show results summary only in test/CLI mode (orchestrator owns completion display)
        if test_mode:
            self._show_results_summary(results, test_mode)

        results['success'] = results['symbols_processed'] > 0
        return results
    
    def _get_all_symbols(self):
        """Get all symbols from flow_options_scans for full baseline generation"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT symbol
                    FROM flow_options_scans
                    ORDER BY symbol
                ''')
                symbols = [row[0] for row in cursor.fetchall()]
                logging.info("Found {} unique symbols in flow_options_scans".format(len(symbols)))
                return symbols
        except Exception as e:
            logging.error("Failed to get symbols list: {}".format(e))
            return []
    
    def _calculate_symbol_baseline(self, symbol, start_date, end_date):
        """Calculate baseline statistics for a single symbol
        
        Args:
            symbol: Symbol to calculate baseline for
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            dict: Baseline statistics or None if insufficient data
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Query historical options data - aggregate by trade_date for daily totals
                cursor.execute('''
                    SELECT
                        trade_date,
                        SUM(volume) as daily_volume,
                        SUM(open_interest) as daily_oi,
                        COUNT(*) as contract_count
                    FROM flow_options_scans
                    WHERE symbol = ?
                        AND trade_date >= ?
                        AND trade_date <= ?
                        AND (
                            (scan_timestamp IS NOT NULL AND scan_timestamp != '') OR
                            (created_at IS NOT NULL AND created_at != '')
                        )
                    GROUP BY trade_date
                    HAVING daily_volume > 0
                    ORDER BY trade_date
                ''', (symbol, start_date, end_date))
                
                daily_data = cursor.fetchall()
                
                if len(daily_data) < 3:  # Need at least 3 days for meaningful statistics
                    logging.debug("Insufficient data for {}: only {} days found".format(
                        symbol, len(daily_data)))
                    return None
                
                # Extract daily volumes and vol/oi ratios
                daily_volumes = []
                vol_oi_ratios = []
                daily_totals = []  # NEW: Store raw daily totals for % calculations
                
                for trade_date, daily_volume, daily_oi, contract_count in daily_data:
                    # Store raw daily total for percentage calculations
                    daily_totals.append(float(daily_volume))
                    
                    # Log transform volumes (handles zeros gracefully)
                    log_volume = math.log1p(float(daily_volume))
                    daily_volumes.append(log_volume)
                    
                    # Calculate vol/oi ratio for this day
                    if daily_oi > 0:
                        vol_oi_ratio = format_ratio(float(daily_volume) / float(daily_oi))
                        vol_oi_ratios.append(vol_oi_ratio)
                
                # Calculate robust statistics using median and MAD
                volume_median = statistics.median(daily_volumes)
                volume_mad = self._calculate_mad(daily_volumes) * self.mad_multiplier
                
                # NEW: Calculate median daily total for percentage baseline
                volume_total_daily = statistics.median(daily_totals)
                
                # Vol/OI ratio statistics (if we have ratios)
                if vol_oi_ratios:
                    vol_oi_median = statistics.median(vol_oi_ratios)
                    vol_oi_mad = self._calculate_mad(vol_oi_ratios) * self.mad_multiplier
                else:
                    # Default values if no OI data
                    vol_oi_median = 1.0
                    vol_oi_mad = 0.3
                
                baseline_data = {
                    'volume_median': volume_median,          # Store in log space (for future z-scores)
                    'volume_mad': volume_mad,                # Store in log space (for future z-scores)
                    'volume_total_daily': volume_total_daily, # NEW: Store in linear space (for % calcs)
                    'vol_oi_median': vol_oi_median,         # Store in linear space
                    'vol_oi_mad': vol_oi_mad,               # Store in linear space
                    'sample_size': len(daily_data),
                    'lookback_window': 7,  # Fixed for this implementation
                    'is_new_baseline': False  # Will be updated in _store_symbol_baseline
                }
                
                logging.debug("Calculated baseline for {}: {} days, daily_total={:.0f}, vol_median={:.3f} (log)".format(
                    symbol, len(daily_data), volume_total_daily, volume_median))
                
                return baseline_data
                
        except Exception as e:
            logging.error("Failed to calculate baseline for {}: {}".format(symbol, e))
            return None
    
    def _calculate_mad(self, values):
        """Calculate Median Absolute Deviation
        
        Args:
            values: List of numeric values
            
        Returns:
            float: MAD value
        """
        if not values:
            return 0.0
        
        median = statistics.median(values)
        absolute_deviations = [abs(x - median) for x in values]
        return statistics.median(absolute_deviations)
    
    def _get_current_baseline(self, symbol):
        """Get current baseline values for comparison"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT volume_mean, volume_std, vol_oi_mean, vol_oi_std, sample_size
                    FROM symbol_baselines
                    WHERE symbol = ?
                ''', (symbol,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'volume_mean': result[0],
                        'volume_std': result[1], 
                        'vol_oi_mean': result[2],
                        'vol_oi_std': result[3],
                        'sample_size': result[4]
                    }
                return None
        except Exception as e:
            logging.error("Failed to get current baseline for {}: {}".format(symbol, e))
            return None
    
    def _store_symbol_baseline(self, symbol, baseline_data):
        """Store baseline data in symbol_baselines table
        
        Args:
            symbol: Symbol to store baseline for
            baseline_data: Dictionary with baseline statistics
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if we need to add the new column first
                cursor.execute("PRAGMA table_info(symbol_baselines)")
                columns = [col[1] for col in cursor.fetchall()]
                
                if 'volume_total_daily' not in columns:
                    logging.info("Adding volume_total_daily column to symbol_baselines table")
                    cursor.execute('ALTER TABLE symbol_baselines ADD COLUMN volume_total_daily REAL')
                
                # Check if baseline exists
                cursor.execute('SELECT symbol FROM symbol_baselines WHERE symbol = ?', (symbol,))
                exists = cursor.fetchone() is not None
                
                baseline_data['is_new_baseline'] = not exists

                # Apply decimal formatting to all numeric values
                baseline_data = clean_database_row(baseline_data)

                # Store baseline - REMOVED: market_cap_category, lookback_window, volatility_coefficient
                cursor.execute('''
                    INSERT OR REPLACE INTO symbol_baselines
                    (symbol, volume_mean, volume_std, vol_oi_mean, vol_oi_std,
                     volume_total_daily, sample_size, last_updated, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    baseline_data['volume_median'],     # Log-space median stored as 'mean'
                    baseline_data['volume_mad'],        # Log-space MAD stored as 'std'
                    baseline_data['vol_oi_median'],     # Linear space
                    baseline_data['vol_oi_mad'],        # Linear space
                    baseline_data['volume_total_daily'], # Linear space daily total
                    baseline_data['sample_size'],
                    eastern_isoformat(),
                    eastern_isoformat() if not exists else None  # Only update created_at for new records
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logging.error("Failed to store baseline for {}: {}".format(symbol, e))
            return False
       
    def _show_results_summary(self, results, test_mode):
        """Display results summary"""
        logging.info("\n" + "="*60)
        logging.info("OPTION BASELINE GENERATION RESULTS")
        logging.info("="*60)
        logging.info("Symbols processed: {}".format(results['symbols_processed']))
        logging.info("New baselines created: {}".format(results['baselines_created']))
        logging.info("Existing baselines updated: {}".format(results['baselines_updated']))
        
        if results['errors']:
            logging.warning("Errors encountered: {}".format(len(results['errors'])))
            for error in results['errors'][:3]:  # Show first 3 errors
                logging.warning("  {}".format(error))
        
        # Show before/after comparison for test mode
        if test_mode and results['before_after_samples']:
            logging.info("\nBEFORE/AFTER COMPARISON (showing scale correction):")
            logging.info("-" * 60)
            
            for sample in results['before_after_samples'][:3]:  # Show first 3
                symbol = sample['symbol']
                before = sample['before']
                after = sample['after']
                
                logging.info("Symbol: {}".format(symbol))
                if before:
                    # Convert log values back for display
                    before_vol_linear = math.expm1(before['volume_mean']) if before['volume_mean'] else 0
                    after_vol_linear = math.expm1(after['volume_mean']) if after['volume_mean'] else 0
                    
                    logging.info("  BEFORE: Vol={:.0f} (std={:.2f}), Vol/OI={:.2f} (std={:.2f}), n={}".format(
                        before_vol_linear, before['volume_std'] or 0,
                        before['vol_oi_mean'] or 0, before['vol_oi_std'] or 0,
                        before['sample_size'] or 0))
                    logging.info("  AFTER:  Vol={:.0f} (mad={:.2f}), Vol/OI={:.2f} (mad={:.2f}), n={}".format(
                        after_vol_linear, after['volume_std'] or 0,
                        after['vol_oi_mean'] or 0, after['vol_oi_std'] or 0,
                        sample['sample_size']))
                    
                    # Show scale difference
                    if before_vol_linear > 0 and after_vol_linear > 0:
                        scale_ratio = before_vol_linear / after_vol_linear
                        logging.info("  SCALE CORRECTION: {:.1f}x reduction (stock vs option volumes)".format(scale_ratio))
                else:
                    logging.info("  NEW BASELINE (no previous data)")
                logging.info("")


def main():
    """Main function with CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate option volume baselines')
    parser.add_argument('--test', action='store_true', 
                       help='Test mode: process MAG7 symbols only with detailed output')
    parser.add_argument('--symbols', nargs='+', 
                       help='Specific symbols to process (space-separated)')
    parser.add_argument('--lookback', type=int, default=7,
                       help='Lookback window in days (default: 7)')
    parser.add_argument('--db-path', 
                       help='Path to database file (optional)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    try:
        generator = OptionBaselineGenerator(args.db_path)
        
        symbols = None
        if args.symbols:
            symbols = args.symbols
        
        results = generator.generate_baselines(
            symbols=symbols,
            lookback_days=args.lookback,
            test_mode=args.test
        )
        
        # Exit with appropriate code
        if results['errors']:
            logging.warning("Completed with {} errors".format(len(results['errors'])))
            return 1
        else:
            logging.info("Baseline generation completed successfully")
            return 0
            
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130
    except Exception as e:
        logging.error("Unexpected error: {}".format(e))
        return 1


if __name__ == '__main__':
    exit(main())
