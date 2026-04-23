#!/usr/bin/env python3
"""
Flow Monitor Alert Evaluator (fm_evaluator.py)
---------------------------------------------
Core evaluation engine that tracks alert performance to build learning feedback loop.
Transforms Flow Monitor from detection system into learning system.

Key Functions:
- Track alert outcomes over 30-day windows
- Calculate performance metrics and quality scores  
- Mini-collector for post-alert contract pricing
- Failure analysis for systematic improvement
- Generate reports for system optimization

Author: Ben (with assistance from Claude)
Date: 2025-07-06
"""

import os
import sys
import sqlite3
import logging
import time
import math
import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from tools.timezone_utils import eastern_isoformat, eastern_date_string, now_eastern, get_eastern_timezone
from tools.decimal_formatter import format_percentage
from strategies.flow_monitor.fm_storage import FlowMonitorStorage
from strategies.flow_monitor.fm_config import FMConfig


class AlertEvaluator:
    """Main evaluator class for tracking alert performance"""
    
    def __init__(self, config_path=None):
        """Initialize evaluator with config and database connections"""
        self.config = FMConfig(config_path)
        self.storage = FlowMonitorStorage(self.config)
        
        # Evaluation parameters from config
        eval_config = self.config.flow_monitor_config.get('evaluation', {})
        self.tracking_window_days = eval_config.get('tracking_window_days', 30)
        self.min_move_threshold = eval_config.get('min_move_threshold', 0.20)
        self.evaluation_frequency_hours = eval_config.get('evaluation_frequency_hours', 24)
        self.data_staleness_hours = eval_config.get('data_staleness_hours', 0.5)  # 30 minutes - much shorter for real-time evaluation
        
        # Quality scoring weights
        score_weights = eval_config.get('quality_score_weights', {})
        self.direction_weight = score_weights.get('direction_weight', 0.25)
        self.magnitude_weight = score_weights.get('magnitude_weight', 0.35) 
        self.timing_weight = score_weights.get('timing_weight', 0.25)
        self.risk_weight = score_weights.get('risk_weight', 0.15)
        
        # Stats tracking
        self.stats = {
            'alerts_evaluated': 0,
            'new_peaks_found': 0,
            'alerts_completed': 0,
            'tracking_records_created': 0,
            'mini_collections_successful': 0,
            'mini_collections_failed': 0,
            'errors': 0
        }
        
        # Verify schema requirements
        self._verify_schema()
        
        logging.info("Alert Evaluator initialized with {}-day tracking window".format(self.tracking_window_days))

    def _verify_schema(self):
        """Check if required columns exist, log warning if not"""
        logging.debug("Verifying database schema...")
        try:
            with sqlite3.connect(self.storage.datalake_path) as conn:
                cursor = conn.cursor()

                # Check for performance tracking columns in flow_alerts
                cursor.execute("PRAGMA table_info(flow_alerts)")
                columns = [row[1] for row in cursor.fetchall()]

                required_columns = [
                    'max_prof_1d_pct', 'max_prof_3d_pct', 'max_prof_7d_pct',
                    'max_prof_30d_pct', 'evaluation_status', 'final_quality_score'
                ]

                missing_columns = [col for col in required_columns if col not in columns]

                if missing_columns:
                    logging.warning("Missing required columns in flow_alerts: {}".format(missing_columns))
                    logging.warning("Please run schema updates before evaluation")
                else:
                    logging.debug("Schema verification passed - all required columns present")

                # Check for required tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alert_contract_tracking'")
                if not cursor.fetchone():
                    logging.warning("alert_contract_tracking table missing - mini-collector disabled")
                else:
                    logging.debug("All required tables present")

                # Recreate view if it has the old expiration_date filter (survivorship bias fix)
                cursor.execute("SELECT sql FROM sqlite_master WHERE type='view' AND name='active_alerts_for_evaluation'")
                view_row = cursor.fetchone()
                if view_row and 'expiration_date' in (view_row[0] or ''):
                    logging.info("Dropping old active_alerts_for_evaluation view (removing expiration_date filter)")
                    cursor.execute("DROP VIEW active_alerts_for_evaluation")
                    conn.commit()
                    view_row = None

                # Create required views if they don't exist
                if not view_row:
                    logging.debug("Creating active_alerts_for_evaluation view...")
                    cursor.execute('''
                        CREATE VIEW active_alerts_for_evaluation AS
                        SELECT fa.*
                        FROM flow_alerts fa
                        INNER JOIN (
                            SELECT contract_hash, MIN(alert_timestamp) as first_alert
                            FROM flow_alerts
                            WHERE (evaluation_status IS NULL OR evaluation_status = 'active')
                              AND datetime(alert_timestamp) > datetime('now', '-30 days')
                            GROUP BY contract_hash
                        ) first_alerts
                        ON fa.contract_hash = first_alerts.contract_hash
                        AND fa.alert_timestamp = first_alerts.first_alert
                        WHERE (fa.evaluation_status IS NULL OR fa.evaluation_status = 'active')
                    ''')
                    conn.commit()
                    logging.debug("Created active_alerts_for_evaluation view")
                else:
                    logging.debug("active_alerts_for_evaluation view exists")

        except Exception as e:
            logging.error("Schema verification failed: {}".format(e))
    
    def run_evaluation(self):
        """Main evaluation loop - typically called nightly"""
        start_time = time.time()
        logging.debug("FLOW MONITOR ALERT EVALUATION")
        logging.debug("Starting evaluation run at {}".format(now_eastern().strftime("%Y-%m-%d %H:%M:%S EST")))

        try:
            # Get alerts that need evaluation
            logging.debug("Fetching alerts for evaluation...")
            query_start = time.time()
            alerts = self.get_active_alerts_for_evaluation()
            query_elapsed = time.time() - query_start
            logging.debug("Alert query completed in {:.2f} seconds".format(query_elapsed))

            if not alerts:
                logging.info("No alerts found for evaluation")
                return True

            logging.info("Found {} alerts to evaluate".format(len(alerts)))

            # Process alerts in batches for memory efficiency
            batch_size = 50
            total_processed = 0
            total_batches = (len(alerts) + batch_size - 1) // batch_size

            logging.debug("Processing alerts in {} batches of {} alerts each...".format(total_batches, batch_size))

            for i in range(0, len(alerts), batch_size):
                batch = alerts[i:i + batch_size]
                batch_num = (i // batch_size) + 1

                logging.debug("Batch {}/{}: alerts {}-{} ({} alerts)".format(
                    batch_num, total_batches, i + 1,
                    min(i + batch_size, len(alerts)), len(batch)
                ))
                batch_start_time = time.time()
                
                for alert in batch:
                    try:
                        self.stats['alerts_evaluated'] += 1
                        alert_id = alert['id']
                        alert_start_time = time.time()
                        
                        # Progress logging every 50 alerts
                        if total_processed > 0 and total_processed % 50 == 0:
                            percentage = (total_processed / len(alerts)) * 100
                            logging.info("Progress: {}/{} alerts processed ({:.1f}%)".format(total_processed, len(alerts), percentage))

                        # Log individual alert processing (debug only — batch progress shown above)
                        logging.debug("Processing alert {} (symbol: {}, {})".format(
                            alert_id, alert.get('symbol'), alert.get('expiration_date')))
                        
                        # Create contract tracking if needed
                        tracking_start = time.time()
                        self.create_contract_tracking(alert)
                        tracking_elapsed = time.time() - tracking_start
                        logging.debug("Contract tracking created in {:.3f}s".format(tracking_elapsed))
                        
                        # Get best performance for each timeframe
                        timeframes = [1, 4, 24, 72, 168, 336, 720]  # 1hr, 4hr, 1day, 3day, 7day, 14day, 30day
                        timeframe_gains = {}

                        logging.debug("Calculating timeframe performance for alert {}".format(alert_id))
                        timeframe_start = time.time()

                        for hours in timeframes:
                            tf_start = time.time()
                            performance_data = self.get_timeframe_performance_data(alert, hours)
                            tf_elapsed = time.time() - tf_start

                            if tf_elapsed > 10.0:  # Log slow queries
                                logging.warning("Slow timeframe query: {}h took {:.2f}s for alert {}".format(hours, tf_elapsed, alert_id))
                            
                            if performance_data:
                                # Calculate gain for this timeframe
                                alert_option_price = self._get_alert_option_price(alert)
                                if alert_option_price:
                                    gain_pct = (performance_data['best_option_price'] - alert_option_price) / alert_option_price * 100
                                    timeframe_gains[hours] = gain_pct
                                    logging.debug("Alert {} timeframe {}h: {:.1f}% gain ({:.3f}s)".format(alert_id, hours, gain_pct, tf_elapsed))
                                else:
                                    logging.debug("No alert option price for timeframe {}h".format(hours))
                            else:
                                logging.debug("No performance data for timeframe {}h".format(hours))
                        
                        timeframe_total_elapsed = time.time() - timeframe_start
                        if timeframe_total_elapsed > 10.0:
                            logging.warning("Slow alert timeframe processing: {:.2f}s for alert {}".format(timeframe_total_elapsed, alert_id))
                        else:
                            logging.debug("All timeframes completed in {:.2f}s for alert {}".format(timeframe_total_elapsed, alert_id))
                        
                        # Update all timeframe performance at once
                        if timeframe_gains:
                            self.update_all_timeframe_performance(alert_id, timeframe_gains)
                        
                        # Check if evaluation should be completed
                        should_complete, completion_reason = self.should_complete_evaluation(alert, timeframe_gains)
                        
                        if should_complete:
                            # Calculate final quality score
                            quality_score = self.evaluate_alert_quality(alert, timeframe_gains)
                            final_metrics = {'quality_score': quality_score}
                            
                            # Mark as complete
                            logging.debug("Completing alert {} - {} (quality score: {:.1f})".format(
                                alert_id, completion_reason, quality_score))
                            self.mark_alert_evaluation_complete(alert_id, final_metrics, completion_reason)
                        
                        total_processed += 1
                        
                        # Log individual alert completion
                        alert_total_elapsed = time.time() - alert_start_time
                        if alert_total_elapsed > 30.0:  # Log slow alerts
                            logging.warning("Slow alert processing: alert {} took {:.2f}s".format(alert_id, alert_total_elapsed))
                        else:
                            logging.debug("Alert {} completed in {:.2f}s".format(alert_id, alert_total_elapsed))
                        
                    except Exception as e:
                        logging.error("Error evaluating alert {}: {}".format(alert.get('id', 'UNKNOWN'), e))
                        logging.exception("Full traceback for alert error:")
                        self.stats['errors'] += 1
                        continue
                
                # Log batch completion
                batch_elapsed = time.time() - batch_start_time
                logging.info("Batch {}/{} completed in {:.2f}s".format(batch_num, total_batches, batch_elapsed))
            
            # Generate summary
            total_time = time.time() - start_time
            logging.info("Evaluated {} alerts, {} completed, {} errors ({:.1f}s)".format(
                self.stats['alerts_evaluated'], self.stats['alerts_completed'],
                self.stats['errors'], total_time))
            self._log_evaluation_summary(total_time)
            
            return True
            
        except Exception as e:
            logging.error("Evaluation run failed: {}".format(e))
            return False
    
    def get_active_alerts_for_evaluation(self, cutoff_hours=0.5):
        """Get alerts that need evaluation (older than cutoff_hours, within tracking window)"""
        try:
            cutoff_time = now_eastern() - timedelta(hours=cutoff_hours)
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Use the deduplicated view directly
                cursor.execute('''
                    SELECT * FROM active_alerts_for_evaluation
                    WHERE datetime(alert_timestamp) < ?
                    ORDER BY alert_timestamp ASC
                ''', (cutoff_time.isoformat(),))
                
                alerts = [dict(row) for row in cursor.fetchall()]
                logging.debug("Database query returned {} unique contracts for evaluation".format(len(alerts)))
                return alerts
                
        except Exception as e:
            logging.error("Error getting alerts for evaluation: {}".format(e))
            return []
            
    def should_complete_evaluation(self, alert, timeframe_gains):
        """Determine if alert tracking should end"""
        try:
            # Check if option expired
            expiration_date = datetime.fromisoformat(alert['expiration_date'])
            # Make expiration timezone-aware for comparison
            if expiration_date.tzinfo is None:
                expiration_date = expiration_date.replace(tzinfo=get_eastern_timezone())
            
            if now_eastern().date() >= expiration_date.date():
                return True, 'expired'
            
            # Check if tracking window exceeded (30 days max)
            alert_time = datetime.fromisoformat(alert['alert_timestamp'])
            # Make alert_time timezone-aware for comparison
            if alert_time.tzinfo is None:
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            days_elapsed = (now_eastern() - alert_time).days
            if days_elapsed >= self.tracking_window_days:
                return True, 'window_exceeded'
            
            # Check for data collection failures
            if not timeframe_gains:
                # Allow a few failures before giving up
                return False, 'data_issue'
            
            return False, 'active'
            
        except Exception as e:
            logging.error("Error checking completion for alert {}: {}".format(alert.get('id', 'unknown'), e))
            return True, 'error'
    
    def mark_alert_evaluation_complete(self, alert_id, final_metrics, completion_reason):
        """Mark alert evaluation as complete with final scores and failure analysis"""
        try:
            with sqlite3.connect(self.storage.datalake_path) as conn:
                cursor = conn.cursor()
                
                # Get the complete alert data for failure analysis
                cursor.execute('SELECT * FROM flow_alerts WHERE id = ?', (alert_id,))
                alert_row = cursor.fetchone()
                
                if not alert_row:
                    logging.error("Alert {} not found for completion".format(alert_id))
                    return False
                
                # Convert to dict for easier access
                alert_columns = [desc[0] for desc in cursor.description]
                alert = dict(zip(alert_columns, alert_row))
                
                # Calculate quality score if not provided
                quality_score = final_metrics.get('quality_score')
                if quality_score is None:
                    quality_score = self.evaluate_alert_quality(alert, None)
                    final_metrics['quality_score'] = quality_score
                
                # Calculate days to max gain and peak hour
                days_to_max, peak_hour = self.calculate_days_to_max_gain(alert)
                
                # Calculate days to max loss and trough hour  
                days_to_loss, trough_hour = self.calculate_days_to_max_loss(alert)
                
                # Update alert status and quality score
                cursor.execute('''
                    UPDATE flow_alerts 
                    SET evaluation_status = 'completed',
                        final_quality_score = ?,
                        days_to_max_prof = ?,
                        peak_hour_est = ?,
                        days_to_max_loss = ?,
                        last_evaluated_date = ?
                    WHERE id = ?
                ''', (
                    quality_score,
                    days_to_max,
                    peak_hour,
                    days_to_loss,
                    self._get_current_timestamp(),  # This now uses Eastern Time
                    alert_id
                ))
                
                # Track low-quality alerts for stats
                if quality_score < 3.0:
                    self.stats['failures_detected'] = self.stats.get('failures_detected', 0) + 1
                    logging.debug("Alert {} has low quality score ({:.1f})".format(
                        alert_id, quality_score))
                
                conn.commit()
                self.stats['alerts_completed'] += 1
                
                logging.info("Completed evaluation for alert {} (reason: {}, score: {:.1f})".format(
                    alert_id, completion_reason, quality_score))
                
                return True
                
        except Exception as e:
            logging.error("Error marking alert {} complete: {}".format(alert_id, e))
            return False

    def calculate_performance_metrics(self, alert, current_data):
        """Calculate current performance metrics for alert"""
        try:
            if not current_data:
                return None
            
            # Calculate option price changes (primary method)
            alert_option_price = self._get_alert_option_price(alert)
            current_option_price = self._get_current_option_price(current_data)
            
            if alert_option_price and current_option_price and alert_option_price > 0:
                # Option-based performance (most accurate)
                performance_pct = (current_option_price - alert_option_price) / alert_option_price * 100
                
                logging.debug("Option performance for {} {} {}: alert_price={:.2f}, current_price={:.2f}, perf={:.1f}%".format(
                    alert['symbol'], alert['strike'], alert['option_type'], 
                    alert_option_price, current_option_price, performance_pct))
            else:
                # Fallback: Underlying-based approximation
                performance_pct = self._calculate_underlying_performance(alert, current_data)
                logging.info("Using underlying performance fallback for {} {} {}: {:.1f}% (option pricing unavailable)".format(
                    alert['symbol'], alert['strike'], alert['option_type'], performance_pct))
            
            # Calculate time elapsed - FIX: Handle timezone properly
            alert_time_str = alert['alert_timestamp']
            # Parse as timezone-naive, then make timezone-aware
            alert_time = datetime.strptime(alert_time_str, '%Y-%m-%d %H:%M:%S')
            alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            current_time = now_eastern()
            hours_elapsed = (current_time - alert_time).total_seconds() / 3600
            days_elapsed = hours_elapsed / 24
            
            return {
                'performance_pct': performance_pct,
                'hours_elapsed': hours_elapsed,
                'days_elapsed': days_elapsed,
                'option_price': current_option_price,
                'underlying_price': current_data.get('underlying_price', 0),
                'volume': current_data.get('volume', 0)
            }
            
        except Exception as e:
            logging.error("Error calculating performance for alert {}: {}".format(alert.get('id', 'UNKNOWN'), e))
            return None

    def evaluate_alert_quality(self, alert, final_performance_data):
        """Calculate final quality score (0-10 scale) using multi-component algorithm

        TODO: THIS SCORING FORMULA IS BROKEN - NEEDS COMPLETE REDESIGN
        Current issues:
        - Can score 32+ when max should be 10 (always hits cap for decent winners)
        - All profitable alerts get 9-10, losers get 0 (no discrimination)
        - Component weights * 10 multiplication is wrong (3*0.25*10 = 7.5 max, not 3 max)
        - Timing component doesn't properly measure swing trade quality
        - Need to spend time figuring out proper scoring methodology

        For now: Leaving as-is since it's not hurting anything, just not very useful.
        """
        try:
            score = 0.0
            
            # Get best performance across all timeframes
            max_gains = [
                alert.get('max_profit_1hr', 0) or 0,
                alert.get('max_profit_4hr', 0) or 0,
                alert.get('max_prof_1d_pct', 0) or 0,
                alert.get('max_prof_3d_pct', 0) or 0,
                alert.get('max_prof_7d_pct', 0) or 0,
                alert.get('max_prof_14d_pct', 0) or 0,
                alert.get('max_prof_30d_pct', 0) or 0
            ]
            
            # Get worst loss across all timeframes
            max_losses = [
                alert.get('max_loss_1hr', 0) or 0,
                alert.get('max_loss_4hr', 0) or 0,
                alert.get('max_loss_1d_pct', 0) or 0,
                alert.get('max_loss_3d_pct', 0) or 0,
                alert.get('max_loss_7d_pct', 0) or 0,
                alert.get('max_loss_14d_pct', 0) or 0,
                alert.get('max_loss_30d_pct', 0) or 0
            ]
            
            max_gain = max(max_gains) if max_gains else 0
            max_loss = min(max_losses) if max_losses else 0  # Most negative value
            
            # Component 1: Direction Correctness (3 points max)
            if max_gain > 0:
                direction_score = 3.0  # Any profit gets full points
            else:
                direction_score = 0.0
            
            # Component 2: Magnitude of Move (4 points max)
            magnitude_score = 0.0
            if max_gain > 10:
                magnitude_score += 1.0
            if max_gain > 25:
                magnitude_score += 1.0  
            if max_gain > 50:
                magnitude_score += 1.0
            if max_gain > 100:
                magnitude_score += 1.0
            
            # Component 3: Timing Quality (3 points max)
            timing_score = 0.0
            
            # Calculate days to peak
            alert_time = datetime.fromisoformat(alert['alert_timestamp'])
            # Make alert_time timezone-aware for comparison
            if alert_time.tzinfo is None:
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            days_elapsed = (now_eastern() - alert_time).days
            
            # Favor sustained moves over quick pops for swing trading
            gains_1hr = alert.get('max_profit_1hr', 0) or 0
            gains_1day = alert.get('max_prof_1d_pct', 0) or 0
            gains_7day = alert.get('max_prof_7d_pct', 0) or 0
            
            if gains_1hr > 0 and gains_1day > gains_1hr:
                timing_score += 1.0  # Momentum continued beyond 1hr
                
            if gains_7day > 20 and days_elapsed <= 7:
                timing_score += 1.0  # Good move in reasonable timeframe
                
            if max_gain > 30 and days_elapsed <= 14:
                timing_score += 1.0  # Strong timing - big move quickly
            
            # Component 4: Risk Management / Profit-Loss Ratio (2 points max) 
            risk_score = 0.0
            
            if max_gain > 0:  # Only score risk if there was profit potential
                if max_loss == 0:  # No losses recorded
                    risk_score = 1.0  # Good - no downside captured
                else:
                    # Calculate profit-to-loss ratio
                    profit_loss_ratio = abs(max_gain / max_loss) if max_loss < 0 else float('inf')
                    
                    if profit_loss_ratio >= 3.0:  # 3:1 or better risk/reward
                        risk_score = 2.0
                    elif profit_loss_ratio >= 2.0:  # 2:1 risk/reward  
                        risk_score = 1.5
                    elif profit_loss_ratio >= 1.0:  # At least broke even or better
                        risk_score = 1.0
                    else:  # Loss exceeded gains
                        risk_score = 0.0
            
            # Combine components with weights 
            total_score = (
                direction_score * self.direction_weight * 10 +
                magnitude_score * self.magnitude_weight * 10 +
                timing_score * self.timing_weight * 10 +
                risk_score * self.risk_weight * 10
            )
            
            final_score = min(10.0, max(0.0, total_score))
            
            logging.debug("Quality score for alert {}: direction={:.1f}, magnitude={:.1f}, timing={:.1f}, risk={:.1f}, final={:.1f}".format(
                alert.get('id', 'UNKNOWN'), direction_score, magnitude_score, timing_score, risk_score, final_score))
            
            return final_score
            
        except Exception as e:
            logging.error("Error evaluating quality for alert {}: {}".format(alert.get('id', 'UNKNOWN'), e))
            return 0.0

    def update_alert_performance(self, alert_id, performance_data):
        """Update performance metrics for specific alert"""
        try:
            if not performance_data:
                return False
            
            hours_elapsed = performance_data['hours_elapsed']
            gain_pct = performance_data['performance_pct']

            # Apply decimal formatting (2 decimals for percentages)
            gain_pct_formatted = format_percentage(gain_pct)

            # Determine which timeframes to update (profit if positive, loss if negative)
            updates = {}

            if hours_elapsed <= 1:
                if gain_pct_formatted > 0:
                    updates['max_profit_1hr'] = 'MAX(COALESCE(max_profit_1hr, 0), ?)'
                elif gain_pct_formatted < 0:
                    updates['max_loss_1hr'] = 'MIN(COALESCE(max_loss_1hr, 0), ?)'
            
            if hours_elapsed <= 4:
                if gain_pct_formatted > 0:
                    updates['max_profit_4hr'] = 'MAX(COALESCE(max_profit_4hr, 0), ?)'
                elif gain_pct_formatted < 0:
                    updates['max_loss_4hr'] = 'MIN(COALESCE(max_loss_4hr, 0), ?)'

            if hours_elapsed <= 24:
                if gain_pct_formatted > 0:
                    updates['max_prof_1d_pct'] = 'MAX(COALESCE(max_prof_1d_pct, 0), ?)'
                elif gain_pct_formatted < 0:
                    updates['max_loss_1d_pct'] = 'MIN(COALESCE(max_loss_1d_pct, 0), ?)'

            if hours_elapsed <= 72:
                if gain_pct_formatted > 0:
                    updates['max_prof_3d_pct'] = 'MAX(COALESCE(max_prof_3d_pct, 0), ?)'
                elif gain_pct_formatted < 0:
                    updates['max_loss_3d_pct'] = 'MIN(COALESCE(max_loss_3d_pct, 0), ?)'

            if hours_elapsed <= 168:  # 7 days
                if gain_pct_formatted > 0:
                    updates['max_prof_7d_pct'] = 'MAX(COALESCE(max_prof_7d_pct, 0), ?)'
                elif gain_pct_formatted < 0:
                    updates['max_loss_7d_pct'] = 'MIN(COALESCE(max_loss_7d_pct, 0), ?)'

            if hours_elapsed <= 336:  # 14 days
                if gain_pct_formatted > 0:
                    updates['max_prof_14d_pct'] = 'MAX(COALESCE(max_prof_14d_pct, 0), ?)'
                elif gain_pct_formatted < 0:
                    updates['max_loss_14d_pct'] = 'MIN(COALESCE(max_loss_14d_pct, 0), ?)'

            if hours_elapsed <= 720:  # 30 days
                if gain_pct_formatted > 0:
                    updates['max_prof_30d_pct'] = 'MAX(COALESCE(max_prof_30d_pct, 0), ?)'
                elif gain_pct_formatted < 0:
                    updates['max_loss_30d_pct'] = 'MIN(COALESCE(max_loss_30d_pct, 0), ?)'
            
            if not updates:
                return True  # No updates needed
            
            # Build dynamic SQL
            set_clauses = []
            params = []

            for column, expression in updates.items():
                set_clauses.append("{} = {}".format(column, expression))
                params.append(gain_pct_formatted)
            
            # Always update last_evaluated_date
            set_clauses.append("last_evaluated_date = ?")
            params.append(eastern_isoformat())
            
            params.append(alert_id)  # For WHERE clause
            
            sql = "UPDATE flow_alerts SET {} WHERE id = ?".format(", ".join(set_clauses))
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                
                if cursor.rowcount > 0:
                    conn.commit()
                    self.stats['new_peaks_found'] += 1
                    logging.debug("Updated performance for alert {}: {:.1f}% gain".format(alert_id, gain_pct))
                    return True
                
            return False
            
        except Exception as e:
            logging.error("Error updating performance for alert {}: {}".format(alert_id, e))
            return False

    def analyze_peak_progression_patterns(self, alert):
        """Analyze when the alert peaked for trader guidance"""
        try:
            gains = {
                '1hr': alert.get('max_profit_1hr', 0) or 0,
                '4hr': alert.get('max_profit_4hr', 0) or 0,
                '1day': alert.get('max_prof_1d_pct', 0) or 0,
                '3day': alert.get('max_prof_3d_pct', 0) or 0,
                '7day': alert.get('max_prof_7d_pct', 0) or 0,
                '14day': alert.get('max_prof_14d_pct', 0) or 0,
                '30day': alert.get('max_prof_30d_pct', 0) or 0
            }
            
            # Find peak timeframe
            max_gain = max(gains.values())
            peak_timeframes = [tf for tf, gain in gains.items() if gain == max_gain]
            
            # Classify the peak timing
            peak_classification = self._classify_peak_timing(peak_timeframes[0], max_gain)
            
            # Calculate progression characteristics
            progression_analysis = {
                'peak_timeframe': peak_timeframes[0],
                'peak_value': max_gain,
                'classification': peak_classification,
                'momentum_profile': self._analyze_momentum_profile(gains),
                'trader_guidance': self._generate_trader_guidance(peak_classification, max_gain)
            }
            
            return progression_analysis
            
        except Exception as e:
            logging.error("Error analyzing peak progression: {}".format(e))
            return None

    def _classify_peak_timing(self, peak_timeframe, peak_value):
        """Classify the type of peak timing"""
        if peak_timeframe in ['1hr', '4hr']:
            if peak_value > 50:
                return 'momentum_explosion'  # Quick big move
            else:
                return 'quick_scalp'  # Fast but modest
        elif peak_timeframe in ['1day', '3day']:
            return 'swing_opportunity'  # Classic swing trade
        elif peak_timeframe in ['7day', '14day']:
            return 'position_build'  # Longer development
        else:
            return 'delayed_realization'  # Very late peak

    def _analyze_momentum_profile(self, gains):
        """Analyze how momentum developed over time"""
        timeframes = ['1hr', '4hr', '1day', '3day', '7day', '14day', '30day']
        
        # Calculate momentum characteristics
        early_momentum = gains['1hr'] if gains['1hr'] > 0 else 0
        sustained_momentum = gains['7day'] / gains['1hr'] if gains['1hr'] > 0 else 0
        
        if sustained_momentum > 1.5:
            return 'accelerating'  # Momentum building
        elif sustained_momentum > 0.8:
            return 'sustained'  # Steady growth
        elif sustained_momentum > 0.5:
            return 'fading'  # Losing steam
        else:
            return 'collapsed'  # Major fade

    def _generate_trader_guidance(self, classification, peak_value):
        """Generate actionable guidance for traders based on peak analysis"""
        guidance_map = {
            'momentum_explosion': "Quick high-conviction entries needed - momentum plays peak fast",
            'quick_scalp': "Scalp opportunity - take profits within hours, don't hold",
            'swing_opportunity': "Classic swing setup - hold 1-3 days for optimal exit",
            'position_build': "Institution building position - trend following strategy",
            'delayed_realization': "Flow was early - consider longer timeframes for similar alerts"
        }
        
        base_guidance = guidance_map.get(classification, "Pattern unclear - manual review needed")
        
        if peak_value > 100:
            return base_guidance + " | HIGH CONVICTION - {}% peak achieved".format(int(peak_value))
        elif peak_value > 25:
            return base_guidance + " | MODERATE - {}% peak".format(int(peak_value))
        else:
            return base_guidance + " | LOW REWARD - {}% peak".format(int(peak_value))

    def _detect_peak_timing_patterns(self, lookback_days, min_count):
        """Detect patterns in when alerts achieve their peaks - KEY for trader guidance"""
        try:
            patterns = []
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                cursor = conn.cursor()
                
                # Analyze when successful alerts (>25% gains) peaked
                cursor.execute('''
                    SELECT 
                        fa.id,
                        fa.symbol,
                        fa.max_profit_1hr,
                        fa.max_profit_4hr, 
                        fa.max_prof_1d_pct,
                        fa.max_prof_3d_pct,
                        fa.max_prof_7d_pct,
                        fa.max_prof_14d_pct,
                        fa.max_prof_30d_pct
                    FROM flow_alerts fa
                    WHERE fa.evaluation_status = 'completed'
                    AND datetime(fa.last_evaluated_date) > datetime('now', '-{} days')
                    AND (fa.max_prof_30d_pct > 25 OR fa.max_prof_7d_pct > 25)
                    ORDER BY fa.max_prof_30d_pct DESC
                '''.format(lookback_days))
                
                successful_alerts = cursor.fetchall()
                
                if len(successful_alerts) < min_count:
                    return []
                
                # Analyze peak timing distribution
                peak_timing_analysis = self._analyze_peak_distribution(successful_alerts)
                
                # Create patterns based on timing clusters
                for timing_pattern in peak_timing_analysis:
                    if timing_pattern['count'] >= min_count:
                        patterns.append({
                            'pattern_type': 'peak_timing_cluster',
                            'occurrence_count': timing_pattern['count'],
                            'peak_timeframe': timing_pattern['timeframe'],
                            'avg_peak_value': timing_pattern['avg_peak'],
                            'description': '{} alerts peaked at {} timeframe (avg: {:.1f}%)'.format(
                                timing_pattern['count'], timing_pattern['timeframe'], timing_pattern['avg_peak']),
                            'recommendation': 'Consider {} strategy for similar alerts'.format(
                                timing_pattern['strategy_recommendation'])
                        })
                
                return patterns
                
        except Exception as e:
            logging.error("Error detecting peak timing patterns: {}".format(e))
            return []
            
    def _analyze_peak_distribution(self, successful_alerts):
        """Analyze when successful alerts achieved their peaks"""
        timeframes = ['1hr', '4hr', '1day', '3day', '7day', '14day', '30day']
        timing_clusters = {}
        
        for alert in successful_alerts:
            # Find which timeframe had the peak
            gains = [
                alert[2] or 0,  # max_profit_1hr
                alert[3] or 0,  # max_profit_4hr  
                alert[4] or 0,  # max_prof_1d_pct
                alert[5] or 0,  # max_prof_3d_pct
                alert[6] or 0,  # max_prof_7d_pct
                alert[7] or 0,  # max_prof_14d_pct
                alert[8] or 0   # max_prof_30d_pct
            ]
            
            max_gain = max(gains)
            if max_gain > 0:
                peak_index = gains.index(max_gain)
                peak_timeframe = timeframes[peak_index]
                
                if peak_timeframe not in timing_clusters:
                    timing_clusters[peak_timeframe] = {'peaks': [], 'count': 0}
                
                timing_clusters[peak_timeframe]['peaks'].append(max_gain)
                timing_clusters[peak_timeframe]['count'] += 1
        
        # Calculate averages and add strategy recommendations
        results = []
        strategy_map = {
            '1hr': 'momentum_scalping',
            '4hr': 'intraday_swing', 
            '1day': 'overnight_hold',
            '3day': 'short_swing',
            '7day': 'weekly_swing',
            '14day': 'position_trading',
            '30day': 'trend_following'
        }
        
        for timeframe, data in timing_clusters.items():
            if data['count'] > 0:
                avg_peak = sum(data['peaks']) / len(data['peaks'])
                results.append({
                    'timeframe': timeframe,
                    'count': data['count'],
                    'avg_peak': avg_peak,
                    'strategy_recommendation': strategy_map.get(timeframe, 'custom_strategy')
                })
        
        return results
    
    def create_contract_tracking(self, alert):
        """Create tracking record for alert's contract (if not exists)"""
        try:
            with sqlite3.connect(self.storage.datalake_path) as conn:
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
                    alert['scan_timestamp']
                ))
                
                conn.commit()
                self.stats['tracking_records_created'] += 1
                return True
                
        except Exception as e:
            logging.error("Error creating tracking for alert {}: {}".format(alert.get('id', 'UNKNOWN'), e))
            return False

    def update_contract_tracking(self, alert_id, success=True):
        """Update contract tracking statistics"""
        try:
            with sqlite3.connect(self.storage.datalake_path) as conn:
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
                
                conn.commit()
                return True
                
        except Exception as e:
            logging.error("Error updating tracking for alert {}: {}".format(alert_id, e))
            return False

    def get_current_contract_data(self, alert):
        """Get current pricing data for alert's contract - database first, API fallback"""
        try:
            symbol = alert.get('symbol')
            strike = alert.get('strike')
            expiration = alert.get('expiration_date')
            option_type = alert.get('option_type')
            
            if not all([symbol, strike, expiration, option_type]):
                logging.warning("Missing contract details for alert {}: {} {} {} {}".format(
                    alert.get('id'), symbol, strike, expiration, option_type))
                return None
            
            # Try database first (main collector data)
            current_data = self._fetch_contract_from_database(alert)
            
            if current_data:
                logging.debug("Found current contract data in database for {} {} {}".format(
                    symbol, strike, option_type))
                return current_data
            
            # Fallback to API (mini-collector)
            logging.debug("Database miss - using mini-collector for {} {} {}".format(
                symbol, strike, option_type))
            return self._fetch_contract_from_api(alert)
            
        except Exception as e:
            logging.error("Error getting current contract data for alert {}: {}".format(
                alert.get('id', 'UNKNOWN'), e))
            return None

    def _fetch_contract_from_database(self, alert):
        """Fetch contract from latest scan in database"""
        try:
            symbol = alert.get('symbol')
            strike = float(alert.get('strike'))
            expiration = alert.get('expiration_date')
            option_type = alert.get('option_type')
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get most recent contract data from main collector
                cursor.execute('''
                    SELECT * FROM flow_options_scans 
                    WHERE symbol = ? 
                    AND ABS(strike - ?) < 0.01 
                    AND expiration_date = ? 
                    AND option_type = ?
                    ORDER BY scan_timestamp DESC 
                    LIMIT 1
                ''', (symbol, strike, expiration, option_type))
                
                row = cursor.fetchone()
                
                if row:
                    # Convert to dict and calculate current price
                    contract_data = dict(row)
                    
                    # Get underlying price if available
                    cursor.execute('''
                        SELECT underlying_price FROM flow_options_scans
                        WHERE symbol = ? 
                        AND scan_timestamp = ?
                        LIMIT 1
                    ''', (symbol, contract_data['scan_timestamp']))
                    
                    underlying_row = cursor.fetchone()
                    if underlying_row:
                        contract_data['underlying_price'] = underlying_row[0]
                    
                    logging.debug("Found contract in database: {} {} {} (scan: {})".format(
                        symbol, strike, option_type, contract_data.get('scan_timestamp')))
                    
                    return contract_data
                
                logging.debug("Contract not found in database: {} {} {}".format(
                    symbol, strike, option_type))
                return None
                
        except Exception as e:
            logging.error("Error fetching contract from database: {}".format(e))
            return None

    def get_timeframe_performance_data(self, alert, timeframe_hours):
        """Get best performance data for specific timeframe"""
        try:
            symbol = alert.get('symbol')
            strike = float(alert.get('strike'))
            expiration = alert.get('expiration_date')
            option_type = alert.get('option_type')
            alert_timestamp = alert.get('alert_timestamp')
            
            if not all([symbol, strike, expiration, option_type, alert_timestamp]):
                logging.debug("Missing required alert data for timeframe query: symbol={}, strike={}, exp={}, type={}, timestamp={}".format(
                    symbol, strike, expiration, option_type, bool(alert_timestamp)))
                return None
            
            # Calculate time window
            alert_time = datetime.fromisoformat(alert_timestamp)
            if alert_time.tzinfo is None:
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            end_time = alert_time + timedelta(hours=timeframe_hours)
            current_time = now_eastern()
            
            # Don't look beyond current time
            if end_time > current_time:
                end_time = current_time
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Log the query parameters for debugging
                logging.debug("Timeframe query: {}h for {} {} {} {} from {} to {}".format(
                    timeframe_hours, symbol, strike, expiration, option_type, 
                    alert_time.isoformat(), end_time.isoformat()))
                
                query_start = time.time()
                
                # Get best option price within timeframe
                cursor.execute('''
                    SELECT 
                        MAX(CASE 
                            WHEN (bid + ask) / 2 > 0 THEN (bid + ask) / 2 
                            WHEN last_price > 0 THEN last_price 
                            ELSE bid 
                        END) as best_option_price,
                        MAX(underlying_price) as max_underlying_price
                    FROM flow_options_scans 
                    WHERE symbol = ? 
                    AND ABS(strike - ?) < 0.01 
                    AND expiration_date = ? 
                    AND option_type = ?
                    AND datetime(scan_timestamp) >= ?
                    AND datetime(scan_timestamp) <= ?
                ''', (symbol, strike, expiration, option_type, 
                      alert_time.isoformat(), end_time.isoformat()))
                
                query_elapsed = time.time() - query_start
                if query_elapsed > 10.0:  # Log slow DB queries
                    logging.warning("Slow DB query: {:.2f}s for timeframe {}h, alert {} ({} {} {})".format(
                        query_elapsed, timeframe_hours, alert.get('id'), symbol, strike, expiration))
                
                row = cursor.fetchone()
                
                if row and row[0]:
                    return {
                        'best_option_price': float(row[0]),
                        'max_underlying_price': float(row[1] or 0),
                        'timeframe_hours': timeframe_hours
                    }
                
                return None
                
        except Exception as e:
            logging.error("Error getting timeframe data for {} {} {} ({}h): {}".format(
                symbol, strike, option_type, timeframe_hours, e))
            return None

    def update_all_timeframe_performance(self, alert_id, timeframe_gains):
        """Update all timeframe performance metrics at once"""
        try:
            if not timeframe_gains:
                return False
            
            updates = []
            params = []
            
            # Map timeframe hours to column names for profit and loss
            profit_timeframe_map = {
                1: 'max_profit_1hr',
                4: 'max_profit_4hr', 
                24: 'max_prof_1d_pct',
                72: 'max_prof_3d_pct',
                168: 'max_prof_7d_pct',
                336: 'max_prof_14d_pct',
                720: 'max_prof_30d_pct'
            }
            
            loss_timeframe_map = {
                1: 'max_loss_1hr',
                4: 'max_loss_4hr', 
                24: 'max_loss_1d_pct',
                72: 'max_loss_3d_pct',
                168: 'max_loss_7d_pct',
                336: 'max_loss_14d_pct',
                720: 'max_loss_30d_pct'
            }
            
            for hours, gain_pct in timeframe_gains.items():
                if hours in profit_timeframe_map:
                    if gain_pct > 0:
                        column = profit_timeframe_map[hours]
                        updates.append("{} = MAX(COALESCE({}, 0), ?)".format(column, column))
                        params.append(gain_pct)
                    else:
                        # gain_pct <= 0: confirmed loser for this timeframe.
                        # Write 0.0 to profit column so NULL means "not yet evaluated"
                        # rather than "evaluated, was a loser" (survivorship bias fix).
                        column = profit_timeframe_map[hours]
                        updates.append("{} = COALESCE({}, 0)".format(column, column))
                    if gain_pct < 0 and hours in loss_timeframe_map:
                        column = loss_timeframe_map[hours]
                        updates.append("{} = MIN(COALESCE({}, 0), ?)".format(column, column))
                        params.append(gain_pct)
            
            if not updates:
                return True  # No timeframe data to update
            
            # Always update last_evaluated_date
            updates.append("last_evaluated_date = ?")
            params.append(eastern_isoformat())
            
            params.append(alert_id)  # For WHERE clause
            
            sql = "UPDATE flow_alerts SET {} WHERE id = ?".format(", ".join(updates))
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                
                if cursor.rowcount > 0:
                    conn.commit()
                    self.stats['new_peaks_found'] += len([g for g in timeframe_gains.values() if g > 0])
                    logging.debug("Updated performance for alert {}: {} timeframes".format(
                        alert_id, len(timeframe_gains)))
                    return True
                
            return False
            
        except Exception as e:
            logging.error("Error updating all timeframe performance for alert {}: {}".format(alert_id, e))
            return False

    def _get_alert_option_price(self, alert):
        """Extract option price at time of alert"""
        try:
            # Try premium_value first (total dollar value)
            if alert.get('premium_value') and alert.get('volume'):
                premium_value = alert['premium_value']
                volume = alert['volume']
                # Prevent division by zero
                if volume and volume > 0:
                    return premium_value / (volume * 100)  # Convert back to per-contract price
            
            # Fallback: try to reconstruct from alert data if available
            bid = alert.get('bid', 0) or 0
            ask = alert.get('ask', 0) or 0
            last = alert.get('last_price', 0) or 0
            
            # Use midpoint if available
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
            elif last > 0:
                return last
            elif bid > 0:
                return bid
            
            return None
            
        except Exception as e:
            logging.error("Error getting alert option price: {}".format(e))
            return None

    def _get_current_option_price(self, current_data):
        """Extract current option price from contract data"""
        try:
            bid = current_data.get('bid', 0) or 0
            ask = current_data.get('ask', 0) or 0
            last_price = current_data.get('last_price', 0) or 0
            
            # Use midpoint if both bid and ask available
            if bid > 0 and ask > 0:
                return (bid + ask) / 2
            elif last_price > 0:
                return last_price
            elif bid > 0:
                return bid
            elif ask > 0:
                return ask
            
            return None
            
        except Exception as e:
            logging.error("Error getting current option price: {}".format(e))
            return None

    def _calculate_underlying_performance(self, alert, current_data):
        """Calculate performance based on underlying price movement (fallback)"""
        try:
            alert_underlying = alert.get('underlying_price', 0) or 0
            current_underlying = current_data.get('underlying_price', 0) or 0
            option_type = alert.get('option_type', '').upper()
            
            if not all([alert_underlying, current_underlying, option_type]):
                return 0.0
            
            # Calculate underlying percentage change
            underlying_change_pct = (current_underlying - alert_underlying) / alert_underlying * 100
            
            # Approximate option performance based on underlying movement
            if option_type == 'CALL':
                # CALL: Profit when underlying goes UP
                performance_pct = underlying_change_pct * 2  # Rough approximation
            elif option_type == 'PUT':
                # PUT: Profit when underlying goes DOWN
                performance_pct = -underlying_change_pct * 2  # Rough approximation
            else:
                performance_pct = 0.0
            
            return performance_pct
            
        except Exception as e:
            logging.error("Error calculating underlying performance: {}".format(e))
            return 0.0

    def _fetch_contract_from_api(self, alert):
        """Fetch contract via API using mini-collector approach"""
        try:
            symbol = alert.get('symbol')
            strike = float(alert.get('strike'))
            expiration = alert.get('expiration_date')
            option_type = alert.get('option_type')
            
            # Use existing Tradier client from config
            if not hasattr(self.config, 'tradier_client'):
                logging.warning("No Tradier client available for mini-collector")
                self.stats['mini_collections_failed'] = self.stats.get('mini_collections_failed', 0) + 1
                return None
            
            tradier_client = self.config.tradier_client
            
            # Get option chain for this expiration
            chain_data = tradier_client.get_option_chain(symbol, expiration)
            
            if not chain_data or 'option' not in chain_data:
                logging.debug("No option chain data for {} {}".format(symbol, expiration))
                self.stats['mini_collections_failed'] = self.stats.get('mini_collections_failed', 0) + 1
                return None
            
            options_list = chain_data['option']
            if not isinstance(options_list, list):
                options_list = [options_list]
            
            # Find our specific contract
            for option in options_list:
                option_strike = float(option.get('strike', 0))
                option_type_api = option.get('option_type', '')
                
                # Match strike (within 0.01) and option type
                if (abs(option_strike - strike) < 0.01 and 
                    option_type_api.lower() == option_type.lower()):
                    
                    self.stats['mini_collections_successful'] = self.stats.get('mini_collections_successful', 0) + 1
                    
                    # Convert to our contract format
                    contract_data = {
                        'symbol': symbol,
                        'strike': strike,
                        'expiration_date': expiration,
                        'option_type': option_type,
                        'bid': float(option.get('bid', 0.0)),
                        'ask': float(option.get('ask', 0.0)),
                        'last_price': float(option.get('last', 0.0)),
                        'volume': int(option.get('volume', 0)),
                        'open_interest': int(option.get('open_interest', 0)),
                        'underlying_price': float(option.get('underlying_price', 0.0)),
                        'implied_volatility': float(option.get('implied_volatility', 0.0)),
                        'delta': float(option.get('delta', 0.0)),
                        'source': 'mini_collector_api'
                    }
                    
                    logging.debug("Mini-collector found contract: {} {} {} (bid: {}, ask: {})".format(
                        symbol, strike, option_type, contract_data['bid'], contract_data['ask']))
                    
                    return contract_data
            
            # Contract not found in option chain
            logging.debug("Contract {} {} {} not found in option chain".format(
                symbol, strike, option_type))
            self.stats['mini_collections_failed'] = self.stats.get('mini_collections_failed', 0) + 1
            return None
            
        except Exception as e:
            logging.error("Error in mini-collector API fetch for {} {} {}: {}".format(
                symbol, strike, option_type, e))
            self.stats['mini_collections_failed'] = self.stats.get('mini_collections_failed', 0) + 1
            return None

    def add_market_hours_analysis(self, alert_timestamp):
        """Future enhancement: Analyze if alert occurred during pre/post market vs regular hours"""
        try:
            # Parse timestamp and ensure it's in Eastern Time
            if isinstance(alert_timestamp, str):
                alert_time = datetime.fromisoformat(alert_timestamp.replace('Z', ''))
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            else:
                alert_time = alert_timestamp
                if alert_time.tzinfo is None:
                    alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            hour = alert_time.hour
            
            # Market hours analysis (Eastern Time)
            if 4 <= hour < 9:
                return 'pre_market'
            elif 9 <= hour < 16:
                return 'regular_hours'
            elif 16 <= hour < 20:
                return 'after_hours'
            else:
                return 'overnight'
                
        except Exception as e:
            logging.error("Error analyzing market hours: {}".format(e))
            return 'unknown'        

    def _get_current_timestamp(self):
        """Get current timestamp in Eastern Time ISO format"""
        return eastern_isoformat()

    def _calculate_days_elapsed(self, alert_timestamp):
        """Calculate days elapsed since alert using Eastern Time"""
        try:
            if isinstance(alert_timestamp, str):
                # Parse as timezone-naive, then make timezone-aware in Eastern
                alert_time = datetime.fromisoformat(alert_timestamp.replace('Z', ''))
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            else:
                alert_time = alert_timestamp
                if alert_time.tzinfo is None:
                    alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            current_time = now_eastern()
            return (current_time - alert_time).days
            
        except Exception as e:
            logging.error("Error calculating days elapsed: {}".format(e))
            return 0

    def _format_hour_readable(self, hour):
        """Convert 24-hour format to readable time"""
        if hour == 0:
            return "12:00 AM"
        elif hour < 12:
            return "{}:00 AM".format(hour)
        elif hour == 12:
            return "12:00 PM"
        else:
            return "{}:00 PM".format(hour - 12)

    def calculate_days_to_max_gain(self, alert):
        """Find the exact calendar day when this contract achieved its highest price
        
        Args:
            alert: Alert dictionary with contract details
            
        Returns:
            tuple: (days_to_peak: int, peak_hour: int) or (None, None)
        """
        try:
            # Extract contract details
            symbol = alert.get('symbol')
            strike = alert.get('strike')
            expiration = alert.get('expiration_date')
            option_type = alert.get('option_type')
            alert_timestamp = alert.get('alert_timestamp')
            
            if not all([symbol, strike, expiration, option_type, alert_timestamp]):
                logging.debug("Missing contract details for days_to_max_prof calculation")
                return None, None
            
            # Parse alert time
            alert_time = datetime.fromisoformat(alert_timestamp)
            if alert_time.tzinfo is None:
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Find all price data for this contract after the alert
                cursor.execute('''
                    SELECT 
                        scan_timestamp,
                        COALESCE(
                            CASE WHEN (bid + ask) / 2 > 0 THEN (bid + ask) / 2 END,
                            CASE WHEN last_price > 0 THEN last_price END,
                            bid,
                            ask
                        ) as option_price
                    FROM flow_options_scans 
                    WHERE symbol = ? 
                    AND ABS(strike - ?) < 0.01 
                    AND expiration_date = ? 
                    AND option_type = ?
                    AND datetime(scan_timestamp) >= datetime(?)
                    AND option_price > 0
                    ORDER BY scan_timestamp ASC
                ''', (symbol, float(strike), expiration, option_type, alert_timestamp))
                
                price_data = cursor.fetchall()
                
                if not price_data:
                    logging.debug("No price data found for {} {} {} after alert".format(
                        symbol, strike, option_type))
                    return None, None
                
                # Find the scan with highest price
                max_price = 0
                peak_timestamp = None
                
                for row in price_data:
                    price = float(row['option_price'])
                    if price > max_price:
                        max_price = price
                        peak_timestamp = row['scan_timestamp']
                
                if not peak_timestamp:
                    return None, None
                
                # Calculate calendar days from alert to peak
                peak_time = datetime.fromisoformat(peak_timestamp)
                if peak_time.tzinfo is None:
                    peak_time = peak_time.replace(tzinfo=get_eastern_timezone())
                
                # Calculate calendar days (same day = 0, next day = 1, etc.)
                alert_date = alert_time.date()
                peak_date = peak_time.date()
                days_to_peak = (peak_date - alert_date).days
                
                # Extract peak hour in Eastern Time
                peak_hour = peak_time.hour
                
                logging.debug("Alert {} max price ${:.2f} reached after {} days at hour {} on {}".format(
                    alert.get('id'), max_price, days_to_peak, peak_hour, peak_timestamp[:10]))
                
                return days_to_peak, peak_hour
                
        except Exception as e:
            logging.error("Error calculating days to max gain for alert {}: {}".format(
                alert.get('id'), e))
            return None, None

    def calculate_days_to_max_loss(self, alert):
        """Find the exact calendar day when this contract achieved its lowest price
        
        Args:
            alert: Alert dictionary with contract details
            
        Returns:
            tuple: (days_to_trough: int, trough_hour: int) or (None, None)
        """
        try:
            # Extract contract details
            symbol = alert.get('symbol')
            strike = alert.get('strike')
            expiration = alert.get('expiration_date')
            option_type = alert.get('option_type')
            alert_timestamp = alert.get('alert_timestamp')
            
            if not all([symbol, strike, expiration, option_type, alert_timestamp]):
                logging.debug("Missing contract details for days_to_max_loss calculation")
                return None, None
            
            # Parse alert time
            alert_time = datetime.fromisoformat(alert_timestamp)
            if alert_time.tzinfo is None:
                alert_time = alert_time.replace(tzinfo=get_eastern_timezone())
            
            with sqlite3.connect(self.storage.datalake_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Find all price data for this contract after the alert
                cursor.execute('''
                    SELECT 
                        scan_timestamp,
                        COALESCE(
                            CASE WHEN (bid + ask) / 2 > 0 THEN (bid + ask) / 2 END,
                            CASE WHEN last_price > 0 THEN last_price END,
                            bid,
                            ask
                        ) as option_price
                    FROM flow_options_scans 
                    WHERE symbol = ? 
                    AND ABS(strike - ?) < 0.01 
                    AND expiration_date = ? 
                    AND option_type = ?
                    AND datetime(scan_timestamp) >= datetime(?)
                    AND option_price > 0
                    ORDER BY scan_timestamp ASC
                ''', (symbol, float(strike), expiration, option_type, alert_timestamp))
                
                price_data = cursor.fetchall()
                
                if not price_data:
                    logging.debug("No price data found for {} {} {} after alert".format(
                        symbol, strike, option_type))
                    return None, None
                
                # Find the scan with lowest price
                min_price = float('inf')
                trough_timestamp = None
                
                for row in price_data:
                    price = float(row['option_price'])
                    if price < min_price:
                        min_price = price
                        trough_timestamp = row['scan_timestamp']
                
                if not trough_timestamp or min_price == float('inf'):
                    return None, None
                
                # Calculate calendar days from alert to trough
                trough_time = datetime.fromisoformat(trough_timestamp)
                if trough_time.tzinfo is None:
                    trough_time = trough_time.replace(tzinfo=get_eastern_timezone())
                
                # Calculate calendar days (same day = 0, next day = 1, etc.)
                alert_date = alert_time.date()
                trough_date = trough_time.date()
                days_to_trough = (trough_date - alert_date).days
                
                # Extract trough hour in Eastern Time
                trough_hour = trough_time.hour
                
                logging.debug("Alert {} min price ${:.2f} reached after {} days at hour {} on {}".format(
                    alert.get('id'), min_price, days_to_trough, trough_hour, trough_timestamp[:10]))
                
                return days_to_trough, trough_hour
                
        except Exception as e:
            logging.error("Error calculating days to max loss for alert {}: {}".format(
                alert.get('id'), e))
            return None, None

    def _log_evaluation_summary(self, runtime_seconds):
        """Generate human-readable summary of evaluation run (debug-level detail)"""
        logging.debug("ALERT EVALUATION SUMMARY")
        logging.debug("Runtime: {:.1f} seconds".format(runtime_seconds))
        logging.debug("Alerts evaluated: {}".format(self.stats['alerts_evaluated']))
        logging.debug("New performance peaks: {}".format(self.stats['new_peaks_found']))
        logging.debug("Alerts completed: {}".format(self.stats['alerts_completed']))
        logging.debug("Tracking records created: {}".format(self.stats['tracking_records_created']))
        logging.debug("Errors: {}".format(self.stats['errors']))

        # Only show mini-collector stats if it was actually used
        total_collections = self.stats['mini_collections_successful'] + self.stats['mini_collections_failed']
        if total_collections > 0:
            logging.debug("API contract fallback: {} successful, {} failed".format(
                self.stats['mini_collections_successful'], self.stats['mini_collections_failed']))
            success_rate = self.stats['mini_collections_successful'] / total_collections * 100
            logging.debug("API fallback success rate: {:.1f}%".format(success_rate))

        # Calculate efficiency metrics
        if self.stats['alerts_evaluated'] > 0:
            avg_time = runtime_seconds / self.stats['alerts_evaluated']
            logging.debug("Average time per alert: {:.2f} seconds".format(avg_time))


def wait_for_enter():
    """Wait for user to press Enter before continuing"""
    input("\nPress Enter to continue...")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Flow Monitor Alert Evaluator')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--test-mode', action='store_true', help='Run in test mode with small batch')
    parser.add_argument('--force-complete', action='store_true', help='Force complete old alerts for testing')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    return parser.parse_args()


def setup_logging(debug=False):
    """Set up logging"""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    """Main function for standalone testing"""
    print("Flow Monitor Alert Evaluator")
    print("Track alert performance to build learning feedback loop.")
    print("This will show detailed progress and timing information.")
    
    wait_for_enter()
    
    try:
        # Parse arguments and setup
        args = parse_arguments()
        # Force INFO level logging when running directly to see all progress
        if not args.debug:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            setup_logging(args.debug)
        
        print("Logging level set to: {}".format("DEBUG" if args.debug else "INFO"))
        
        # Initialize evaluator
        evaluator = AlertEvaluator(args.config)
        
        if args.test_mode:
            logging.info("Running in test mode")
        
        # Run evaluation
        success = evaluator.run_evaluation()
        
        if success:
            print("\n Evaluation completed successfully!")
        else:
            print("\n Evaluation failed")
            return 1
            
    except KeyboardInterrupt:
        logging.warning("Operation cancelled by user")
        print("\nOperation cancelled by user. Exiting...")
        return 130
    except Exception as e:
        logging.error("Evaluator failed: {}".format(e))
        print("\n An error occurred: {}".format(e))
        traceback.print_exc()
        return 1
    
    wait_for_enter()
    return 0


if __name__ == '__main__':
    exit(main())
 