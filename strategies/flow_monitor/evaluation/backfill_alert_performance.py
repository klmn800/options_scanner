#!/usr/bin/env python3
"""
Flow Monitor Alert Performance Backfill Script
----------------------------------------------
Calculates missing performance data for historical flow alerts using 
option_contracts data. Uses contract hashes for efficient matching.

Key Functions:
- Backfill max_profit columns for all timeframes
- Calculate final quality scores for completed alerts
- Update evaluation status for historical data
- Batch processing with progress tracking

Usage:
python backfill_alert_performance.py [--dry-run] [--batch-size 500] [--limit 1000]

Author: Ben (with assistance from Claude)
Date: 2025-08-26
"""

import os
import sys
import sqlite3
import logging
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project tools to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
tools_dir = os.path.join(project_root, 'tools')
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from tools.timezone_utils import now_eastern, get_eastern_timezone


class AlertPerformanceBackfill:
    """Backfill historical alert performance data"""
    
    def __init__(self, datalake_path=None, dry_run=False):
        """Initialize backfill processor
        
        Args:
            datalake_path: Path to datalake.db file
            dry_run: If True, don't actually update the database
        """
        self.dry_run = dry_run
        
        if datalake_path:
            self.datalake_path = datalake_path
        else:
            # Default path
            self.datalake_path = os.path.join(project_root, 'data', 'datalake.db')
        
        if not os.path.exists(self.datalake_path):
            raise FileNotFoundError(f"Database not found: {self.datalake_path}")
        
        self.stats = {
            'alerts_processed': 0,
            'alerts_updated': 0,
            'contracts_found': 0,
            'contracts_missing': 0,
            'errors': 0
        }
        
        print(f"Initializing backfill processor...")
        print(f"Database: {self.datalake_path}")
        print(f"Dry run mode: {dry_run}")
    
    def get_alerts_needing_backfill(self, limit=None):
        """Get alerts that need performance data AND/OR Greeks data backfilled
        
        Args:
            limit: Maximum number of alerts to process
            
        Returns:
            List of alert dictionaries
        """
        with sqlite3.connect(self.datalake_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get alerts with missing performance data OR missing Greeks data
            query = '''
                SELECT id, symbol, strike, option_type, expiration_date, 
                       alert_timestamp, scan_timestamp, contract_hash, underlying_price,
                       bid, ask, last_price,
                       delta, gamma, theta, vega, moneyness, premium_value,
                       concentration_score, neighbor_avg_oi, oi_ratio,
                       max_profit_1hr, max_profit_4hr, max_prof_1d_pct,
                       max_prof_3d_pct, max_prof_7d_pct, max_prof_30d_pct
                FROM flow_alerts 
                WHERE max_prof_30d_pct IS NULL 
                   OR delta IS NULL 
                   OR gamma IS NULL 
                   OR theta IS NULL 
                   OR vega IS NULL
                   OR moneyness IS NULL
                   OR premium_value IS NULL
                ORDER BY alert_timestamp DESC
            '''
            
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query)
            alerts = [dict(row) for row in cursor.fetchall()]
            
            print(f"Found {len(alerts)} alerts needing performance and/or Greeks backfill")
            return alerts
    
    def get_option_price_at_time(self, symbol, strike, expiration_date, option_type, target_timestamp):
        """Get option price closest to target timestamp using indexed columns
        
        Args:
            symbol: Stock symbol
            strike: Strike price
            expiration_date: Expiration date
            option_type: Option type (CALL/PUT)
            target_timestamp: Target timestamp to find price for
            
        Returns:
            Dict with price info or None if not found
        """
        with sqlite3.connect(self.datalake_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Use existing indexes for fast lookup - much faster than contract_hash
            cursor.execute('''
                SELECT bid, ask, last_price, underlying_price, scan_timestamp
                FROM flow_options_scans 
                WHERE symbol = ? AND strike = ? AND expiration_date = ? AND option_type = ?
                AND scan_timestamp >= datetime(?, '-2 hours')
                AND scan_timestamp <= datetime(?, '+2 hours')
                ORDER BY ABS(
                    (julianday(scan_timestamp) - julianday(?)) * 24 * 60
                ) ASC
                LIMIT 1
            ''', (symbol, strike, expiration_date, option_type, 
                  target_timestamp, target_timestamp, target_timestamp))
            
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_best_price_in_timeframe(self, symbol, strike, expiration_date, option_type, start_time, end_time):
        """Get best option price within timeframe using indexed columns
        
        Args:
            symbol: Stock symbol
            strike: Strike price  
            expiration_date: Expiration date
            option_type: Option type (CALL/PUT)
            start_time: Start of timeframe
            end_time: End of timeframe
            
        Returns:
            Best price found or None
        """
        with sqlite3.connect(self.datalake_path) as conn:
            cursor = conn.cursor()
            
            # Use existing indexes for fast lookup
            cursor.execute('''
                SELECT MAX(
                    CASE 
                        WHEN last_price > 0 THEN last_price
                        WHEN bid > 0 AND ask > 0 THEN (bid + ask) / 2 
                        ELSE bid 
                    END
                ) as best_price
                FROM flow_options_scans 
                WHERE symbol = ? AND strike = ? AND expiration_date = ? AND option_type = ?
                AND scan_timestamp >= ?
                AND scan_timestamp <= ?
                AND (last_price > 0 OR bid > 0 OR ask > 0)
            ''', (symbol, strike, expiration_date, option_type, start_time, end_time))
            
            result = cursor.fetchone()
            return result[0] if result and result[0] else None
    
    def get_greeks_data_from_contracts(self, contract_hash, scan_timestamp):
        """Get Greeks and options data from option_contracts using contract_hash and scan_timestamp
        
        Args:
            contract_hash: Contract hash identifier
            scan_timestamp: Scan timestamp to match
            
        Returns:
            Dictionary with Greeks and options data or None if not found
        """
        with sqlite3.connect(self.datalake_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Use contract_hash and scan_timestamp for precise matching
            cursor.execute('''
                SELECT delta, gamma, theta, vega, moneyness, premium_value,
                       concentration_score, neighbor_avg_oi, oi_ratio,
                       bid, ask, last_price, underlying_price, implied_volatility
                FROM flow_options_scans 
                WHERE contract_hash = ? AND scan_timestamp = ?
                LIMIT 1
            ''', (contract_hash, scan_timestamp))
            
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def calculate_alert_performance(self, alert):
        """Calculate performance metrics and backfill Greeks data for a single alert
        
        Args:
            alert: Alert dictionary
            
        Returns:
            Dictionary with calculated performance metrics AND Greeks data
        """
        try:
            symbol = alert['symbol']
            strike = alert['strike']
            expiration_date = alert['expiration_date']
            option_type = alert['option_type']
            alert_timestamp = alert['alert_timestamp']
            contract_hash = alert['contract_hash']
            scan_timestamp = alert['scan_timestamp']
            
            # First, try to get Greeks data if missing
            greeks_data = None
            if (alert['delta'] is None or alert['gamma'] is None or 
                alert['theta'] is None or alert['vega'] is None or 
                alert['moneyness'] is None or alert['premium_value'] is None):
                
                print(f"  Getting Greeks data for {contract_hash}")
                greeks_data = self.get_greeks_data_from_contracts(contract_hash, scan_timestamp)
                
                if greeks_data:
                    print(f"  Found Greeks: D={greeks_data.get('delta'):.3f}, G={greeks_data.get('gamma'):.3f}")
                else:
                    print(f"  No Greeks data found for {contract_hash} at {scan_timestamp}")
            
            # Parse alert timestamp for performance calculation
            alert_time = datetime.fromisoformat(alert_timestamp)
            if alert_time.tzinfo is None:
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            # Get alert option price (baseline) - try Greeks data first, then fallback to price lookup
            alert_price_data = None
            if greeks_data and greeks_data.get('last_price'):
                alert_price_data = greeks_data
            else:
                alert_price_data = self.get_option_price_at_time(
                    symbol, strike, expiration_date, option_type, alert_timestamp
                )
            
            if not alert_price_data:
                print(f"  No price data found for {symbol} {strike} {option_type} at {alert_timestamp}")
                self.stats['contracts_missing'] += 1
                # Still return Greeks data even if performance calculation fails
                return {'greeks_data': greeks_data} if greeks_data else None
            
            # Calculate baseline price
            if alert_price_data['bid'] and alert_price_data['ask']:
                alert_price = (alert_price_data['bid'] + alert_price_data['ask']) / 2
            elif alert_price_data['last_price']:
                alert_price = alert_price_data['last_price']
            elif alert_price_data['bid']:
                alert_price = alert_price_data['bid']
            else:
                print(f"  No valid price data for {contract_hash}")
                # Still return Greeks data even if performance calculation fails
                return {'greeks_data': greeks_data} if greeks_data else None
            
            if alert_price <= 0:
                print(f"  Invalid alert price {alert_price} for {contract_hash}")
                # Still return Greeks data even if performance calculation fails
                return {'greeks_data': greeks_data} if greeks_data else None
            
            # Calculate performance for different timeframes
            timeframes = [
                ('1hr', 1),
                ('4hr', 4), 
                ('1day', 24),
                ('3day', 72),
                ('7day', 168),
                ('30day', 720)
            ]
            
            performance = {}
            
            for name, hours in timeframes:
                end_time = alert_time + timedelta(hours=hours)
                
                # Don't look beyond current time
                current_time = now_eastern()
                if end_time > current_time:
                    end_time = current_time
                
                best_price = self.get_best_price_in_timeframe(
                    symbol, strike, expiration_date, option_type,
                    alert_time.isoformat(),
                    end_time.isoformat()
                )
                
                if best_price and best_price > 0:
                    gain_pct = (best_price - alert_price) / alert_price * 100
                    performance[f'max_profit_{name}'] = gain_pct
                    
                    print(f"    {name}: {gain_pct:.1f}% (${alert_price:.2f} -> ${best_price:.2f})")
                else:
                    performance[f'max_profit_{name}'] = 0.0
            
            self.stats['contracts_found'] += 1
            
            # Return both performance metrics and Greeks data
            result = {'performance': performance}
            if greeks_data:
                result['greeks_data'] = greeks_data
            
            return result
            
        except Exception as e:
            print(f"  Error calculating performance for alert {alert['id']}: {e}")
            self.stats['errors'] += 1
            return None
    
    def calculate_quality_score(self, alert, performance):
        """Calculate quality score based on performance
        
        Simple scoring based on max gain achieved:
        - Direction: 3 points if any positive gain
        - Magnitude: 1-4 points based on max gain (10%, 25%, 50%, 100%+)
        - Timing: 1-3 points based on how quickly peak was reached
        """
        try:
            if not performance:
                return 0.0
            
            # Get all gains
            gains = [
                performance.get('max_profit_1hr', 0) or 0,
                performance.get('max_profit_4hr', 0) or 0,
                performance.get('max_prof_1d_pct', 0) or 0,
                performance.get('max_prof_3d_pct', 0) or 0,
                performance.get('max_prof_7d_pct', 0) or 0,
                performance.get('max_prof_30d_pct', 0) or 0
            ]
            
            max_gain = max(gains)
            
            # Direction score (3 points max)
            direction_score = 3.0 if max_gain > 0 else 0.0
            
            # Magnitude score (4 points max)
            magnitude_score = 0.0
            if max_gain > 10:
                magnitude_score += 1.0
            if max_gain > 25:
                magnitude_score += 1.0  
            if max_gain > 50:
                magnitude_score += 1.0
            if max_gain > 100:
                magnitude_score += 1.0
            
            # Timing score (3 points max) - favor sustained moves
            timing_score = 0.0
            gains_1hr = gains[0]
            gains_1day = gains[2]
            gains_7day = gains[4]
            
            if gains_1hr > 0 and gains_1day > gains_1hr:
                timing_score += 1.0  # Momentum continued
                
            if gains_7day > 20:
                timing_score += 1.0  # Good sustained move
                
            if max_gain > 30:
                timing_score += 1.0  # Strong overall performance
            
            # Combine with weights (direction=30%, magnitude=40%, timing=30%)
            total_score = (direction_score * 0.3 + magnitude_score * 0.4 + timing_score * 0.3) * 10
            
            return min(10.0, max(0.0, total_score))
            
        except Exception as e:
            print(f"  Error calculating quality score: {e}")
            return 0.0
    
    def update_alert_performance(self, alert_id, performance, quality_score, greeks_data=None):
        """Update alert with calculated performance data and Greeks data
        
        Args:
            alert_id: Alert ID to update
            performance: Performance metrics dictionary
            quality_score: Calculated quality score
            greeks_data: Greeks and options data dictionary
        """
        if self.dry_run:
            update_desc = "performance data"
            if greeks_data:
                update_desc += " and Greeks data"
            print(f"  [DRY RUN] Would update alert {alert_id} with {update_desc}")
            return True
        
        try:
            with sqlite3.connect(self.datalake_path) as conn:
                cursor = conn.cursor()
                
                # Build dynamic UPDATE query based on what data we have
                update_fields = []
                update_values = []
                
                # Always try to update performance data
                if performance:
                    update_fields.extend([
                        'max_profit_1hr = ?',
                        'max_profit_4hr = ?',
                        'max_prof_1d_pct = ?',
                        'max_prof_3d_pct = ?',
                        'max_prof_7d_pct = ?',
                        'max_prof_30d_pct = ?',
                        'final_quality_score = ?',
                        'last_evaluated_date = ?',
                        'evaluation_status = ?'
                    ])
                    update_values.extend([
                        performance.get('max_profit_1hr'),
                        performance.get('max_profit_4hr'),
                        performance.get('max_prof_1d_pct'),
                        performance.get('max_prof_3d_pct'),
                        performance.get('max_prof_7d_pct'),
                        performance.get('max_prof_30d_pct'),
                        quality_score,
                        now_eastern().isoformat(),
                        'completed'
                    ])
                
                # Add Greeks data if available
                if greeks_data:
                    greeks_fields = []
                    greeks_values = []
                    
                    if greeks_data.get('delta') is not None:
                        greeks_fields.append('delta = ?')
                        greeks_values.append(greeks_data['delta'])
                    
                    if greeks_data.get('gamma') is not None:
                        greeks_fields.append('gamma = ?')
                        greeks_values.append(greeks_data['gamma'])
                    
                    if greeks_data.get('theta') is not None:
                        greeks_fields.append('theta = ?')
                        greeks_values.append(greeks_data['theta'])
                    
                    if greeks_data.get('vega') is not None:
                        greeks_fields.append('vega = ?')
                        greeks_values.append(greeks_data['vega'])
                    
                    if greeks_data.get('moneyness') is not None:
                        greeks_fields.append('moneyness = ?')
                        greeks_values.append(greeks_data['moneyness'])
                    
                    if greeks_data.get('premium_value') is not None:
                        greeks_fields.append('premium_value = ?')
                        greeks_values.append(greeks_data['premium_value'])
                    
                    if greeks_data.get('concentration_score') is not None:
                        greeks_fields.append('concentration_score = ?')
                        greeks_values.append(greeks_data['concentration_score'])
                    
                    if greeks_data.get('neighbor_avg_oi') is not None:
                        greeks_fields.append('neighbor_avg_oi = ?')
                        greeks_values.append(greeks_data['neighbor_avg_oi'])
                    
                    if greeks_data.get('oi_ratio') is not None:
                        greeks_fields.append('oi_ratio = ?')
                        greeks_values.append(greeks_data['oi_ratio'])
                    
                    update_fields.extend(greeks_fields)
                    update_values.extend(greeks_values)
                
                if update_fields:
                    query = f'''
                        UPDATE flow_alerts 
                        SET {', '.join(update_fields)}
                        WHERE id = ?
                    '''
                    update_values.append(alert_id)
                    
                    cursor.execute(query, update_values)
                    conn.commit()
                    self.stats['alerts_updated'] += 1
                    return True
                else:
                    print(f"  No data to update for alert {alert_id}")
                    return False
                
        except Exception as e:
            print(f"  Error updating alert {alert_id}: {e}")
            self.stats['errors'] += 1
            return False
    
    def run_backfill(self, batch_size=500, limit=None):
        """Run the backfill process
        
        Args:
            batch_size: Number of alerts to process per batch
            limit: Maximum total alerts to process
        """
        start_time = time.time()
        
        print("\n" + "="*70)
        print("FLOW MONITOR ALERT PERFORMANCE BACKFILL")
        print("="*70)
        
        # Get alerts to process
        alerts = self.get_alerts_needing_backfill(limit)
        
        if not alerts:
            print("No alerts need backfill - all performance data is complete!")
            return True
        
        total_alerts = len(alerts)
        total_batches = (total_alerts + batch_size - 1) // batch_size
        
        print(f"\nProcessing {total_alerts} alerts in {total_batches} batches...")
        
        for i in range(0, total_alerts, batch_size):
            batch = alerts[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            print(f"\n--- BATCH {batch_num}/{total_batches} ---")
            print(f"Processing alerts {i + 1}-{min(i + batch_size, total_alerts)} ({len(batch)} alerts)")
            
            for j, alert in enumerate(batch):
                alert_id = alert['id']
                contract_hash = alert['contract_hash']
                symbol = alert['symbol']
                
                print(f"  Alert {alert_id}: {symbol} {contract_hash}")
                
                # Calculate performance and get Greeks data
                result = self.calculate_alert_performance(alert)
                
                if result:
                    performance = result.get('performance')
                    greeks_data = result.get('greeks_data')
                    quality_score = 0.0
                    
                    # Calculate quality score if we have performance data
                    if performance:
                        quality_score = self.calculate_quality_score(alert, performance)
                        print(f"  -> Quality score: {quality_score:.1f}")
                    
                    # Update database with available data
                    self.update_alert_performance(alert_id, performance, quality_score, greeks_data)
                    
                    # Show what was updated
                    if performance and greeks_data:
                        print(f"  -> Updated: performance + Greeks data")
                    elif performance:
                        print(f"  -> Updated: performance data only")
                    elif greeks_data:
                        print(f"  -> Updated: Greeks data only")
                else:
                    print(f"  -> No data available for backfill")
                
                self.stats['alerts_processed'] += 1
                
                # Progress update every 25 alerts
                if (i + j + 1) % 25 == 0:
                    percentage = ((i + j + 1) / total_alerts) * 100
                    print(f"\n  Progress: {i + j + 1}/{total_alerts} alerts processed ({percentage:.1f}%)")
        
        # Final summary
        elapsed_time = time.time() - start_time
        
        print("\n" + "="*70)
        print("BACKFILL COMPLETE")
        print("="*70)
        print(f"Total runtime: {elapsed_time:.1f} seconds")
        print(f"Alerts processed: {self.stats['alerts_processed']}")
        print(f"Alerts updated: {self.stats['alerts_updated']}")
        print(f"Contracts found: {self.stats['contracts_found']}")
        print(f"Contracts missing: {self.stats['contracts_missing']}")
        print(f"Errors: {self.stats['errors']}")
        
        if self.stats['alerts_processed'] > 0:
            avg_time = elapsed_time / self.stats['alerts_processed']
            print(f"Average time per alert: {avg_time:.2f} seconds")
        
        success_rate = (self.stats['contracts_found'] / self.stats['alerts_processed'] * 100) if self.stats['alerts_processed'] > 0 else 0
        print(f"Success rate: {success_rate:.1f}%")
        
        print("="*70)
        
        return True


def main():
    """Main function for standalone execution"""
    parser = argparse.ArgumentParser(description='Backfill Flow Monitor Alert Performance Data')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--batch-size', type=int, default=500, help='Number of alerts to process per batch')
    parser.add_argument('--limit', type=int, help='Maximum number of alerts to process')
    parser.add_argument('--database', help='Path to datalake.db file')
    
    args = parser.parse_args()
    
    try:
        backfill = AlertPerformanceBackfill(
            datalake_path=args.database,
            dry_run=args.dry_run
        )
        
        success = backfill.run_backfill(
            batch_size=args.batch_size,
            limit=args.limit
        )
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"Backfill failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())