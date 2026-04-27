#!/usr/bin/env python3
"""
Flow Monitor Alerts (fm_alerts.py)
----------------------------------
Phase 4: Simple alert dispatcher for Flow Monitor operations.
Processes pre-analyzed contracts flagged by fm_analyzer and sends notifications.

Features:
- Query contracts where alert_threshold_met = TRUE
- Deduplication with configurable window (default 4 hours)
- Console and email digest notifications
- Save alerts to flow_alerts table

Author: Ben (with assistance from Claude)
Date: 2025-06-29
"""

import json
import logging
import sys
import smtplib
import os
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string
from strategies.flow_monitor.fm_config import FMConfig, shutdown_event
from strategies.flow_monitor.fm_storage import FlowMonitorStorage
from tools.log_utils import beautiful_log

# Temporarily disable analyst context
ANALYST_CONTEXT_AVAILABLE = False
# try:
#     # Import analyst context from data directory
#     data_dir = os.path.join(get_project_root(), 'data')
#     if data_dir not in sys.path:
#         sys.path.insert(0, data_dir)
#     
#     from analyst_context import get_analyst_context
#     ANALYST_CONTEXT_AVAILABLE = True
# except ImportError:
#     ANALYST_CONTEXT_AVAILABLE = False
#     logging.warning("Analyst context engine not available - alerts will not include analyst context")
    

class FMAlerts:
    def __init__(self, config, storage):
        """Initialize alert processor with config and storage

        Args:
            config: FMConfig instance
            storage: FlowMonitorStorage instance
        """
        self.config = config
        self.storage = storage

        # Get alert configuration
        self.channels = self.config.flow_monitor_config.get('alert_channels', {'console': True, 'email': False})
        self.email_config = self.config.config.get('notifications', {}).get('email', {})

        # Statistics tracking
        self.stats = {
            'candidates_found': 0,
            'alerts_sent': 0,
            'console_sent': 0,
            'email_sent': 0,
            'save_failures': 0,
            'social_queued': 0,
            'etf_filtered': 0,
            'delta_filtered': 0
        }

        # Social posting integration (lazy load)
        self._social_notifier = None
        self._social_enabled = self.config.config.get('social_posting', {}).get('enabled', False)

        logging.debug("FM Alerts initialized with delta-based volume surge detection")
        self._ensure_analyst_context_column()
        self._ensure_scan_interval_column()
    
    def process_alerts(self, scan_timestamp, test_mode=False, scan_contracts=None):
        """Main entry point - process alerts for a specific scan

        Args:
            scan_timestamp: ISO timestamp string for scan to process
            test_mode: Whether this is a test run
            scan_contracts: Optional list of all contract dicts from the current scan
                           (used by roll detection to find counterpart legs)

        Returns:
            dict: Statistics summary
        """
        logging.info("Processing alerts for scan: {}".format(scan_timestamp))

        # Store scan contracts for roll detection
        self._scan_contracts = scan_contracts

        # Reset stats for this run
        self.stats = {key: 0 for key in self.stats}

        try:
            # Step 1: Get alert candidates
            candidates = self._get_alert_candidates(scan_timestamp)
            self.stats['candidates_found'] = len(candidates)

            if not candidates:
                logging.debug("No alert candidates found for scan")
                return self.stats

            # Step 2: Apply filters (ETF + delta)
            passed_candidates = []
            failed_candidates = []

            for candidate in candidates:
                symbol = candidate.get('symbol')
                delta = candidate.get('delta')
                is_etf = candidate.get('is_etf')

                # Filter 1: ETF check
                if is_etf == 1:
                    candidate['filter_reason'] = 'etf'
                    failed_candidates.append(candidate)
                    self.stats['etf_filtered'] += 1
                    continue

                # Filter 2: Delta check
                if delta is None:
                    candidate['filter_reason'] = 'delta_null'
                    failed_candidates.append(candidate)
                    self.stats['delta_filtered'] += 1
                elif abs(delta) < 0.25 or abs(delta) > 0.75:
                    candidate['filter_reason'] = 'delta_range'
                    failed_candidates.append(candidate)
                    self.stats['delta_filtered'] += 1
                else:
                    # Passed all filters
                    passed_candidates.append(candidate)

            logging.info("Filters applied: {} passed, {} filtered ({} ETFs, {} delta)".format(
                len(passed_candidates), len(failed_candidates),
                self.stats['etf_filtered'], self.stats['delta_filtered']))

            # Step 3: Update filtered candidates in flow_options_scans with filter reason
            if failed_candidates:
                self._update_filtered_contracts(failed_candidates, scan_timestamp)

            # Step 4: Process alerts that passed delta filter
            if not passed_candidates:
                logging.info("No alerts passed delta filter")
                return self.stats

            unique_alerts = passed_candidates
            logging.debug("Processing {} unique alerts after delta filter".format(len(unique_alerts)))

            # Step 4b: Roll detection — tag alerts that are part of position rolls
            roll_config = self.config.get_roll_detection_config()
            if roll_config.get('enabled', True) and self._scan_contracts:
                rolls_found = 0
                for alert in unique_alerts:
                    roll_detected, counterpart_details = self._detect_roll(
                        alert, self._scan_contracts, roll_config)
                    alert['roll_detected'] = roll_detected
                    alert['roll_counterpart_details'] = counterpart_details
                    if roll_detected:
                        rolls_found += 1
                if rolls_found:
                    logging.info("Roll detection: {} of {} alerts tagged as possible rolls".format(
                        rolls_found, len(unique_alerts)))
            else:
                if not self._scan_contracts:
                    logging.debug("Roll detection skipped: no scan contracts available")
                for alert in unique_alerts:
                    alert['roll_detected'] = False
                    alert['roll_counterpart_details'] = None

            # Step 5: Compute scan interval (once per cycle, shared across all alerts)
            scan_interval_seconds = self._compute_scan_interval(scan_timestamp)
            if scan_interval_seconds is not None:
                logging.info("Scan interval: {}s ({:.1f} min)".format(
                    scan_interval_seconds, scan_interval_seconds / 60))

            # Step 6: Format and send notifications
            self._send_notifications(unique_alerts, scan_timestamp)

            # Step 7: Save alerts to database
            self._save_alerts(unique_alerts, scan_timestamp, test_mode=test_mode, scan_interval_seconds=scan_interval_seconds)

            # Log summary
            self._log_alert_summary()

            return self.stats

        except Exception as e:
            logging.error("Error processing alerts: {}".format(e))
            return self.stats
    
    def _get_alert_candidates(self, scan_timestamp):
        """Get contracts flagged for alerts by fm_analyzer
        
        Args:
            scan_timestamp: Scan timestamp to query
            
        Returns:
            list: List of contract dictionaries ready for alerting
        """
        query = '''
            SELECT
                oc.symbol,
                oc.strike,
                oc.expiration_date,
                oc.option_type,
                oc.volume,
                oc.open_interest,
                oc.last_price,
                oc.underlying_price,
                oc.iv as implied_volatility,
                oc.delta,
                oc.gamma,
                oc.theta,
                oc.vega,
                oc.dte as days_to_expiration,
                oc.moneyness,
                oc.premium_value,
                oc.flow_percentage,
                oc.significance_score,
                oc.alert_reason,
                oc.bid,
                oc.ask,
                oc.scan_timestamp,
                oc.trade_date,
                oc.volume_surprise_factor,
                oc.created_at,
                sb.volume_total_daily as normal_daily_volume,
                sm.market_cap_category,
                sm.is_etf,
                oss.symbol_iv_percentile_30d as iv_percentile_30d
            FROM flow_options_scans oc
            LEFT JOIN symbol_baselines sb ON oc.symbol = sb.symbol
            LEFT JOIN symbol_metadata sm ON oc.symbol = sm.symbol
            LEFT JOIN option_symbol_summary oss
                ON oc.symbol = oss.symbol
                AND oss.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
            WHERE oc.scan_timestamp = ?
                AND oc.significance_score >= 3.5
                AND oc.dte >= 7
            ORDER BY oc.significance_score DESC, oc.volume DESC
            LIMIT 100
        '''
        
        candidates = self.storage.query_with_params(query, (scan_timestamp,))
        
        logging.info("Found {} alert candidates from scan".format(len(candidates)))
        return candidates

    def _update_filtered_contracts(self, filtered_candidates, scan_timestamp):
        """Update flow_options_scans with filter reason for contracts that failed filters

        Args:
            filtered_candidates: List of contracts that failed filters (ETF or delta)
            scan_timestamp: Scan timestamp for correlation
        """
        if not filtered_candidates:
            return

        logging.debug("Updating {} filtered contracts with filter reasons".format(len(filtered_candidates)))

        for contract in filtered_candidates:
            try:
                filter_reason = contract.get('filter_reason')
                delta = contract.get('delta')
                symbol = contract.get('symbol')
                base_reason = contract.get('alert_reason', '')

                # Build filter note based on reason
                if filter_reason == 'etf':
                    filter_note = " | FILTERED: ETF (macro signal, not individual stock)"
                elif filter_reason == 'delta_null':
                    filter_note = " | FILTERED: delta=NULL"
                elif filter_reason == 'delta_range':
                    if abs(delta) < 0.25:
                        filter_note = " | FILTERED: delta={:.2f} (too far OTM/protective hedge)".format(delta)
                    elif abs(delta) > 0.75:
                        filter_note = " | FILTERED: delta={:.2f} (too deep ITM/synthetic stock)".format(delta)
                    else:
                        continue  # Shouldn't happen
                else:
                    continue  # Unknown filter reason

                updated_reason = base_reason + filter_note

                # Update flow_options_scans with enhanced alert_reason
                update_query = '''
                    UPDATE flow_options_scans
                    SET alert_reason = ?
                    WHERE scan_timestamp = ?
                      AND symbol = ?
                      AND strike = ?
                      AND expiration_date = ?
                      AND option_type = ?
                '''

                with self.storage.get_connection() as conn:
                    conn.execute(update_query, (
                        updated_reason,
                        scan_timestamp,
                        contract.get('symbol'),
                        contract.get('strike'),
                        contract.get('expiration_date'),
                        contract.get('option_type')
                    ))
                    conn.commit()

                logging.debug("Updated filtered contract: {} ${} {} (delta={})".format(
                    contract.get('symbol'), contract.get('strike'),
                    contract.get('option_type'), delta))

            except Exception as e:
                logging.error("Error updating filtered contract {}: {}".format(
                    contract.get('symbol', 'UNKNOWN'), e))
                continue

    def _get_alert_level(self, significance_score):
        """Determine alert level from significance score
        
        Args:
            significance_score: Numeric score from analyzer
            
        Returns:
            str: 'HIGH', 'MEDIUM', or 'LOW'
        """
        if not significance_score:
            return 'MEDIUM'  # Safe default

        # v2 thresholds (2026-04). Previously: HIGH >= 8.0, MEDIUM >= 6.0
        if significance_score >= 5.0:
            return 'HIGH'
        elif significance_score >= 3.5:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def _send_notifications(self, alerts, scan_timestamp):
        """Send notifications via configured channels
        
        Args:
            alerts: List of unique alert dictionaries
        """
        if not alerts:
            return
        
        # Console notifications (always enabled for development visibility)
        if self.channels.get('console', True):
            self._send_console_alerts(alerts)
            self.stats['console_sent'] = len(alerts)
        
        # Email notifications (if configured)
        email_enabled = (self.channels.get('email', False) and 
                        self.email_config.get('enabled', False))
        
        if email_enabled:
            try:
                self._send_email_digest(alerts, scan_timestamp)
                self.stats['email_sent'] = 1  # One digest email sent
            except Exception as e:
                logging.error("Failed to send email digest: {}".format(e))
        
        self.stats['alerts_sent'] = len(alerts)
    
    def _send_console_alerts(self, alerts):
        """Send alerts to console output, grouped by priority
        
        Args:
            alerts: List of alert dictionaries
        """
        # Group alerts by level
        high_alerts = [a for a in alerts if self._get_alert_level(a.get('significance_score')) == 'HIGH']
        medium_alerts = [a for a in alerts if self._get_alert_level(a.get('significance_score')) == 'MEDIUM']
        low_alerts = [a for a in alerts if self._get_alert_level(a.get('significance_score')) == 'LOW']
        
        print("")
        beautiful_log("\U0001f6a8 FLOW MONITOR ALERTS", level='warning')
        logging.info("Scoring v2: premium + volume surprise (smart money removed 2026-04)")
        print("")

        # High priority alerts first
        if high_alerts:
            logging.info("🔴 HIGH CONVICTION ALERTS (Score 5.0+)")
            for alert in high_alerts:
                logging.info(self._format_console_alert(alert))
            print("")

        # Medium priority alerts
        if medium_alerts:
            logging.info("🟡 MEDIUM ALERTS (Score 3.5-4.9)")
            for alert in medium_alerts:
                logging.info(self._format_console_alert(alert))
            print("")

        # Low priority alerts (rare, but handle gracefully)
        if low_alerts:
            logging.info("⚪ LOW PRIORITY ALERTS")
            for alert in low_alerts:
                logging.info(self._format_console_alert(alert))
            print("")

        logging.info("\U0001f4ca SUMMARY: {} alerts saved ({} HIGH, {} MEDIUM, {} LOW) to flow_alerts".format(
            len(alerts), len(high_alerts), len(medium_alerts), len(low_alerts)))
    
    def _detect_roll(self, alert, scan_contracts, config):
        """Detect if an alert is part of a position roll (closing one strike, opening another).

        Searches the current scan's contract data for a counterpart leg with matching
        volume and divergent V/OI. See PRD 0014 for full algorithm specification.

        Args:
            alert: Alert candidate dict with keys: symbol, strike, option_type,
                   expiration_date, volume, open_interest
            scan_contracts: List of all contract dicts from the current scan
            config: Roll detection config dict from get_roll_detection_config()

        Returns:
            tuple: (roll_detected: bool, counterpart_details: dict or None)
        """
        alert_symbol = alert.get('symbol')
        alert_type = alert.get('option_type')
        alert_strike = alert.get('strike')
        alert_exp = alert.get('expiration_date')
        alert_volume = alert.get('volume', 0)
        alert_oi = alert.get('open_interest', 0)

        if not alert_symbol or not alert_volume or alert_volume <= 0:
            return (False, None)

        # Parse alert expiration for cross-expiration comparison
        try:
            alert_exp_date = datetime.strptime(alert_exp, '%Y-%m-%d')
        except (ValueError, TypeError):
            logging.debug("Roll detection: cannot parse expiration '{}' for {}".format(alert_exp, alert_symbol))
            return (False, None)

        exp_window = config.get('expiration_window_days', 30)
        vol_threshold = config.get('vol_match_threshold', 0.85)
        voi_threshold = config.get('voi_closing_threshold', 1.5)

        best_match = None
        best_vol_ratio = 0.0

        for contract in scan_contracts:
            # Filter: same symbol
            if contract.get('symbol') != alert_symbol:
                continue
            # Filter: same option type
            c_type = contract.get('option_type')
            if c_type != alert_type:
                continue
            # Filter: different strike
            c_strike = contract.get('strike')
            if c_strike == alert_strike:
                continue
            # Filter: volume > 0
            c_volume = contract.get('volume', 0)
            if not c_volume or c_volume <= 0:
                continue

            # Pre-filter: volume within 50-200% range
            vol_min = min(alert_volume, c_volume)
            vol_max = max(alert_volume, c_volume)
            if vol_min / vol_max < 0.50:
                continue

            # Filter: expiration within window
            c_exp = contract.get('expiration_date')
            try:
                c_exp_date = datetime.strptime(c_exp, '%Y-%m-%d')
            except (ValueError, TypeError):
                continue
            if abs((c_exp_date - alert_exp_date).days) > exp_window:
                continue

            # Scoring
            vol_match_ratio = vol_min / vol_max
            if vol_match_ratio < vol_threshold:
                continue

            # V/OI check — at least one leg must have V/OI < threshold
            c_oi = contract.get('open_interest', 0)
            voi_alert = alert_volume / max(alert_oi, 1)
            voi_counterpart = c_volume / max(c_oi, 1)

            if min(voi_alert, voi_counterpart) >= voi_threshold:
                continue

            # This contract qualifies — check if it's the best match
            if vol_match_ratio > best_vol_ratio or (
                vol_match_ratio == best_vol_ratio and best_match is not None and
                voi_counterpart < best_match['_voi_counterpart']
            ):
                best_vol_ratio = vol_match_ratio
                best_match = {
                    'counterpart_strike': float(c_strike),
                    'counterpart_expiration': c_exp,
                    'vol_match_ratio': round(vol_match_ratio, 2),
                    'alert_voi': round(voi_alert, 2),
                    'counterpart_voi': round(voi_counterpart, 2),
                    'role': 'opening' if voi_alert >= voi_counterpart else 'closing',
                    '_voi_counterpart': voi_counterpart,  # internal, stripped before return
                }

        if best_match:
            # Remove internal key before returning
            best_match.pop('_voi_counterpart', None)
            return (True, best_match)

        return (False, None)

    def _format_console_alert(self, alert):
        """Format single alert for console display

        Args:
            alert: Alert dictionary

        Returns:
            str: Formatted alert string
        """
        symbol = alert.get('symbol', 'N/A')
        strike = alert.get('strike', 0)
        option_type = alert.get('option_type', 'N/A')
        volume = alert.get('volume', 0)
        oi = alert.get('open_interest', 0)
        last_price = alert.get('last_price', 0)
        underlying_price = alert.get('underlying_price', 0)
        iv = alert.get('implied_volatility', 0)
        ivp = alert.get('iv_percentile_30d')
        score = alert.get('significance_score', 0)
        flow_pct = alert.get('flow_percentage', 0)
        dte = alert.get('days_to_expiration', 0)
        volume_surprise = alert.get('volume_surprise_factor', 0)
        market_cap = alert.get('market_cap_category', 'unknown')

        # Calculate volume/OI ratio
        vol_oi_ratio = volume / max(oi, 1)

        # Format volume with context
        if volume_surprise > 0:
            vol_context = "{:,} ({:.1f}x)".format(volume, volume_surprise)
        else:
            vol_context = "{:,}".format(volume)

        # Format IV as percentage
        iv_pct = iv * 100 if iv else 0

        # Format IV percentile
        ivp_str = "{:.0f}".format(ivp) if ivp is not None else "--"

        # Create alert line with pricing data - FIX: Handle None market_cap
        market_cap_display = (market_cap[:3].upper()
                             if market_cap and market_cap != 'unknown'
                             else 'UNK')

        # Build roll tag if detected
        roll_tag = ""
        if alert.get('roll_detected') and alert.get('roll_counterpart_details'):
            rd = alert['roll_counterpart_details']
            c_strike = rd.get('counterpart_strike', '?')
            c_strike_str = "${:.0f}".format(c_strike) if isinstance(c_strike, (int, float)) and c_strike == int(c_strike) else "${}".format(c_strike)
            role = rd.get('role', 'opening')
            c_exp = rd.get('counterpart_expiration', '')
            alert_exp = alert.get('expiration_date', '')

            # Determine if cross-expiration
            exp_suffix = ""
            if c_exp and alert_exp and c_exp != alert_exp:
                try:
                    exp_dt = datetime.strptime(c_exp, '%Y-%m-%d')
                    exp_suffix = " {}".format(exp_dt.strftime('%m/%d'))
                except (ValueError, TypeError):
                    pass

            if role == 'closing':
                roll_tag = " [ROLL? closing -> {}{}]".format(c_strike_str, exp_suffix)
            else:
                roll_tag = " [ROLL? from {}{}]".format(c_strike_str, exp_suffix)

        alert_line = "{} [{}]{} ${} {}s ({}d) | Vol: {} | OI: {:,} | V/OI: {:.1f} | Last: ${:.2f} | Underlying: ${:.2f} | IV: {:.0f}% | IVP: {} | Score: {:.1f} | Flow: {:.1f}%".format(
            symbol,
            market_cap_display,
            roll_tag,
            strike,
            option_type,
            dte,
            vol_context,
            oi,
            vol_oi_ratio,
            last_price,
            underlying_price,
            iv_pct,
            ivp_str,
            score,
            flow_pct
        )
        
        # Add alert reason if available (no truncation — full scoring breakdown is valuable)
        reason = alert.get('alert_reason', '')
        if reason:
            alert_line += " | {}".format(reason)
        
        return alert_line
    
    def _send_email_digest(self, alerts, scan_timestamp):
        """Send HTML digest email with all alerts
        
        Args:
            alerts: List of alert dictionaries
        """
        if not alerts:
            return
            
        try:
            # Sort alerts by score (highest first)
            sorted_alerts = sorted(alerts, key=lambda x: x.get('significance_score', 0), reverse=True)
            
            # Create HTML table
            html_content = self._create_html_digest(sorted_alerts)
            
            # Prepare email
            msg = MIMEMultipart('alternative')
            # Parse scan_timestamp string to extract readable date/time
            try:
                # Handle the format: "2025-06-30 11:06:47 -0400"
                if ' -' in scan_timestamp or ' +' in scan_timestamp:
                    # Split off timezone part
                    time_part = scan_timestamp.split(' -')[0].split(' +')[0]
                else:
                    time_part = scan_timestamp
                
                # Extract just the time portion (HH:MM)
                date_time = time_part.split(' ')
                if len(date_time) >= 2:
                    date_str = date_time[0]  # 2025-06-30
                    time_str = date_time[1][:5]  # 11:06 (just HH:MM)
                    subject_time = "{} {}".format(date_str, time_str)
                else:
                    subject_time = scan_timestamp[:16]  # Fallback
                    
            except Exception:
                subject_time = scan_timestamp[:16]  # Safe fallback if parsing fails

            msg['Subject'] = "Flow Monitor Alert Digest - {} Alerts @ {}".format(
                len(alerts), subject_time)
            msg['From'] = self.email_config.get('username')
            msg['To'] = self.email_config.get('to_email')
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.email_config.get('smtp_server'), self.email_config.get('smtp_port')) as server:
                server.starttls()
                server.login(self.email_config.get('username'), self.email_config.get('password'))
                server.send_message(msg)
            
            logging.info("Email digest sent successfully to {}".format(self.email_config.get('to_email')))
            
        except Exception as e:
            logging.error("Failed to send email digest: {}".format(e))
            raise
    
    def _create_html_digest(self, alerts):
        """Create HTML table for email digest
        
        Args:
            alerts: List of sorted alert dictionaries
            
        Returns:
            str: HTML content for email body
        """
        current_time = now_eastern().strftime('%Y-%m-%d %H:%M:%S ET')
        
        html_parts = [
            '<html><body>',
            '<h2>Flow Monitor Alert Digest</h2>',
            '<p>Generated: {}</p>'.format(current_time),
            '<p>Total Alerts: {}</p>'.format(len(alerts)),
            '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">',
            '<thead>',
            '<tr style="background-color: #f0f0f0;">',
            '<th>Symbol</th>',
            '<th>Strike</th>',
            '<th>Type</th>',
            '<th>DTE</th>',
            '<th>Volume</th>',
            '<th>OI</th>',
            '<th>V/OI</th>',
            '<th>Last</th>',
            '<th>Underlying</th>',
            '<th>IV</th>',
            '<th>IVP</th>',
            '<th>Score</th>',
            '<th>Flow %</th>',
            '<th>Level</th>',
            '<th>Reason</th>',
            '</tr>',
            '</thead>',
            '<tbody>'
        ]
        
        # Add rows for each alert
        for alert in alerts:
            level = self._get_alert_level(alert.get('significance_score'))
            
            # Color coding for alert levels
            if level == 'HIGH':
                row_style = 'background-color: #ffe0e0;'  # Light red
            elif level == 'MEDIUM':
                row_style = 'background-color: #fff9e0;'  # Light yellow
            else:
                row_style = ''
            
            # Calculate derived values
            oi = alert.get('open_interest', 0)
            vol_oi_ratio = alert.get('volume', 0) / max(oi, 1)
            last_price = alert.get('last_price', 0)
            underlying_price = alert.get('underlying_price', 0)
            iv = alert.get('implied_volatility', 0)
            iv_pct = iv * 100 if iv else 0
            ivp = alert.get('iv_percentile_30d')

            row = '<tr style="{}">'.format(row_style)
            row += '<td>{}</td>'.format(alert.get('symbol', ''))
            row += '<td>${}</td>'.format(alert.get('strike', ''))
            row += '<td>{}</td>'.format(alert.get('option_type', ''))
            row += '<td>{}</td>'.format(alert.get('days_to_expiration', ''))
            row += '<td>{:,}</td>'.format(alert.get('volume', 0))
            row += '<td>{:,}</td>'.format(oi)
            row += '<td>{:.1f}</td>'.format(vol_oi_ratio)
            row += '<td>${:.2f}</td>'.format(last_price)
            row += '<td>${:.2f}</td>'.format(underlying_price)
            row += '<td>{:.0f}%</td>'.format(iv_pct)
            row += '<td>{}</td>'.format("{:.0f}".format(ivp) if ivp is not None else "--")
            row += '<td>{:.1f}</td>'.format(alert.get('significance_score', 0))
            row += '<td>{:.1f}%</td>'.format(alert.get('flow_percentage', 0))
            row += '<td>{}</td>'.format(level)
            
            # Add truncated alert reason
            reason = alert.get('alert_reason', '')
            if len(reason) > 40:
                reason = reason[:37] + "..."
            row += '<td style="font-size: 11px;">{}</td>'.format(reason)
            row += '</tr>'
            
            html_parts.append(row)
        
        html_parts.extend([
            '</tbody>',
            '</table>',
            '<p><em>This is an automated alert from the Flow Monitor system.</em></p>',
            '</body></html>'
        ])
        
        return '\n'.join(html_parts)
    
    def _ensure_analyst_context_column(self):
        """Ensure analyst_context column exists in flow_alerts table"""
        try:
            # Check if column exists and add if needed
            query = "PRAGMA table_info(flow_alerts)"
            columns_info = self.storage.query_with_params(query, ())
            columns = [row['name'] for row in columns_info]
            
            if 'analyst_context' not in columns:
                alter_query = "ALTER TABLE flow_alerts ADD COLUMN analyst_context TEXT"
                with self.storage.get_connection() as conn:
                    conn.execute(alter_query)
                    conn.commit()
                logging.info("Added analyst_context column to flow_alerts table")
                
        except Exception as e:
            logging.warning("Error ensuring analyst_context column: {}".format(e))
            
    def _ensure_scan_interval_column(self):
        """Ensure scan_interval_seconds column exists in flow_alerts table"""
        try:
            query = "PRAGMA table_info(flow_alerts)"
            columns_info = self.storage.query_with_params(query, ())
            columns = [row['name'] for row in columns_info]

            if 'scan_interval_seconds' not in columns:
                alter_query = "ALTER TABLE flow_alerts ADD COLUMN scan_interval_seconds INTEGER"
                with self.storage.get_connection() as conn:
                    conn.execute(alter_query)
                    conn.commit()
                logging.info("Added scan_interval_seconds column to flow_alerts table")

        except Exception as e:
            logging.warning("Error ensuring scan_interval_seconds column: {}".format(e))

    def _compute_scan_interval(self, scan_timestamp):
        """Compute seconds elapsed since the previous scan on the same trade date

        Args:
            scan_timestamp: Current scan timestamp ("YYYY-MM-DD HH:MM:SS" from eastern_isoformat())

        Returns:
            int or None: Seconds since previous scan, or None if first scan of day
        """
        try:
            from datetime import datetime

            # Get trade_date from scan_timestamp (first 10 chars = "YYYY-MM-DD")
            trade_date = scan_timestamp[:10]

            # Find previous scan timestamp (same pattern as fm_analyzer._get_previous_scan_data)
            prev_scan_query = '''
                SELECT scan_timestamp
                FROM flow_options_scans
                WHERE trade_date = ?
                  AND scan_timestamp < ?
                ORDER BY scan_timestamp DESC
                LIMIT 1
            '''
            prev_scan_result = self.storage.query_with_params(prev_scan_query, (trade_date, scan_timestamp))

            if not prev_scan_result:
                logging.debug("No previous scan found - first scan of day, no interval to compute")
                return None

            prev_scan_timestamp = prev_scan_result[0]['scan_timestamp']

            # Both timestamps are "YYYY-MM-DD HH:MM:SS" format from eastern_isoformat()
            current_dt = datetime.strptime(scan_timestamp[:19], '%Y-%m-%d %H:%M:%S')
            prev_dt = datetime.strptime(prev_scan_timestamp[:19], '%Y-%m-%d %H:%M:%S')

            interval_seconds = int((current_dt - prev_dt).total_seconds())

            if interval_seconds < 0:
                logging.warning("Negative scan interval computed ({}s), returning None".format(interval_seconds))
                return None

            logging.debug("Scan interval: {}s ({:.1f} min) since previous scan".format(
                interval_seconds, interval_seconds / 60))

            return interval_seconds

        except Exception as e:
            logging.warning("Error computing scan interval: {}".format(e))
            return None

    def _save_alerts(self, alerts, scan_timestamp, test_mode=False, scan_interval_seconds=None):
        """Save alerts to flow_alerts table with complete contract data

        Args:
            alerts: List of alert dictionaries
            scan_timestamp: Scan timestamp for correlation
            test_mode: Whether this is a test run
            scan_interval_seconds: Seconds since previous scan (None if first scan of day)
        """
        if not alerts:
            return
        
        logging.debug("Saving {} alerts to flow_alerts table".format(len(alerts)))
        
        current_time = eastern_isoformat()
        
        # Determine notification methods used
        notification_methods = []
        if self.channels.get('console', True):
            notification_methods.append('console')
        if (self.channels.get('email', False) and 
            self.email_config.get('enabled', False)):
            notification_methods.append('email')
        
        methods_str = ','.join(notification_methods)
        
        # Save each alert individually with error handling
        for alert in alerts:
            try:
                # Get analyst context for this symbol (existing code)
                analyst_context = ""
                if ANALYST_CONTEXT_AVAILABLE:
                    try:
                        analyst_context = get_analyst_context(alert.get('symbol'))
                        if analyst_context:
                            logging.debug("Analyst context for {}: {}".format(alert.get('symbol'), analyst_context))
                    except Exception as e:
                        logging.warning("Failed to get analyst context for {}: {}".format(alert.get('symbol'), e))
                
                # Enhance alert reason with delta and analyst context
                base_reason = alert.get('alert_reason', '')
                delta = alert.get('delta')

                # Add delta to alert reason
                if delta is not None:
                    delta_note = " | delta={:.2f}".format(delta)
                    base_reason = base_reason + delta_note

                if test_mode and 'TEST MODE' not in base_reason:
                    base_reason = "TEST MODE - " + base_reason

                enhanced_reason = base_reason

                # Prepend roll tag to reason if detected
                if alert.get('roll_detected') and alert.get('roll_counterpart_details'):
                    rd = alert['roll_counterpart_details']
                    roll_strike = rd.get('counterpart_strike', '?')
                    # Format: v2|ROLL?$170|score:... or v2|ROLL?$170 04/17|score:...
                    roll_tag = "ROLL?${}".format(int(roll_strike) if roll_strike == int(roll_strike) else roll_strike)
                    c_exp = rd.get('counterpart_expiration', '')
                    alert_exp = alert.get('expiration_date', '')
                    if c_exp and alert_exp and c_exp != alert_exp:
                        try:
                            exp_dt = datetime.strptime(c_exp, '%Y-%m-%d')
                            roll_tag += " {}/{}".format(exp_dt.strftime('%m'), exp_dt.strftime('%d'))
                        except (ValueError, TypeError):
                            pass
                    # Insert after v2| prefix
                    if enhanced_reason.startswith('v2|'):
                        enhanced_reason = "v2|{}|{}".format(roll_tag, enhanced_reason[3:])
                    else:
                        enhanced_reason = "{}|{}".format(roll_tag, enhanced_reason)

                if analyst_context:
                    enhanced_reason += " + {}".format(analyst_context)

                # Prepare COMPLETE alert record with all contract data
                alert_record = {
                    # Alert Identity
                    'alert_timestamp': current_time,
                    'scan_timestamp': scan_timestamp,
                    
                    # Core Contract Data (NEW - complete flow_options_scans snapshot)
                    'trade_date': eastern_date_string(),
                    'symbol': alert.get('symbol'),
                    'strike': alert.get('strike'),
                    'expiration_date': alert.get('expiration_date'),
                    'option_type': alert.get('option_type'),
                    'volume': alert.get('volume'),
                    'open_interest': alert.get('open_interest'),
                    'bid': alert.get('bid'),
                    'ask': alert.get('ask'),
                    'last_price': alert.get('last_price'),
                    'underlying_price': alert.get('underlying_price'),
                    'implied_volatility': alert.get('implied_volatility'),
                    'delta': alert.get('delta'),
                    'gamma': alert.get('gamma'),
                    'theta': alert.get('theta'),
                    'vega': alert.get('vega'),
                    'days_to_expiration': alert.get('days_to_expiration'),
                    'moneyness': alert.get('moneyness'),
                    'premium_value': alert.get('premium_value'),
                    'flow_percentage': alert.get('flow_percentage'),
                    'concentration_score': alert.get('concentration_score'),
                    'neighbor_avg_oi': alert.get('neighbor_avg_oi'),
                    'oi_ratio': alert.get('oi_ratio'),
                    'volume_surprise_factor': alert.get('volume_surprise_factor'),
                    
                    # Alert-Specific Analysis
                    'significance_score': alert.get('significance_score'),
                    'alert_reason': enhanced_reason,
                    'alert_level': self._get_alert_level(alert.get('significance_score')),
                    'alert_reason_json': None,
                    
                    # Context Data
                    'earnings_days_ahead': None,
                    
                    # Evaluation Fields (initialize as NULL - fm_evaluator will fill these later)
                    'max_profit_1hr': None,
                    'max_profit_4hr': None,
                    'max_profit_1day': None,
                    'max_profit_3day': None,
                    'max_profit_7day': None,
                    'max_profit_14day': None,
                    'max_profit_30day': None,
                    'days_to_max_gain': None,
                    'evaluation_status': 'active',
                    'final_quality_score': None,
                    'last_evaluated_date': None,
                    'signal_quality_score': None,
                    'user_action': None,
                    'user_pnl': None,
                    
                    # Scan timing
                    'scan_interval_seconds': scan_interval_seconds,

                    # IV context
                    'iv_percentile_30d': alert.get('iv_percentile_30d'),

                    # Roll detection
                    'roll_detected': 1 if alert.get('roll_detected') else 0,
                    'roll_counterpart_details': json.dumps(alert['roll_counterpart_details']) if alert.get('roll_counterpart_details') else None,

                    # Metadata
                    'alert_sent': True,
                    'notification_methods': methods_str
                }
                
                # Save to database using the updated save_alert method
                success = self.storage.save_alert(alert_record)

                if not success:
                    self.stats['save_failures'] += 1
                    logging.error("Failed to save alert for {} ${} {}".format(
                        alert.get('symbol'), alert.get('strike'), alert.get('option_type')
                    ))
                else:
                    logging.info("Complete alert saved for {} {} with score {:.2f}".format(
                        alert.get('symbol'), alert.get('strike'),
                        alert.get('significance_score', 0)
                    ))

                    # Check if alert should be queued for social posting
                    if self._social_enabled:
                        self._check_social_posting(alert_record)
                    
            except Exception as e:
                self.stats['save_failures'] += 1
                logging.error("Error saving alert for {} ${} {}: {}".format(
                    alert.get('symbol', 'UNKNOWN'), 
                    alert.get('strike', 'UNKNOWN'), 
                    alert.get('option_type', 'UNKNOWN'), 
                    e
                ))
                continue
        
        successful_saves = len(alerts) - self.stats['save_failures']
        logging.info("Alert persistence complete: {} saved, {} failures".format(
            successful_saves, self.stats['save_failures']))
    
    def _check_social_posting(self, alert_record):
        """Check if alert should be queued for social posting

        Args:
            alert_record: Alert dictionary that was just saved
        """
        try:
            # Lazy load social notifier
            if not self._social_notifier:
                import json
                with open(self.config.config_path, 'r') as f:
                    full_config = json.load(f)

                from strategies.flow_monitor.fm_social_notifier import FMSocialNotifier
                self._social_notifier = FMSocialNotifier(full_config, self.storage)

            # Get the alert ID from database (just saved)
            query = '''
                SELECT id FROM flow_alerts
                WHERE symbol = ? AND strike = ? AND expiration_date = ?
                    AND option_type = ? AND alert_timestamp = ?
                ORDER BY id DESC LIMIT 1
            '''

            result = self.storage.query_with_params(query, (
                alert_record['symbol'],
                alert_record['strike'],
                alert_record['expiration_date'],
                alert_record['option_type'],
                alert_record['alert_timestamp']
            ))

            if not result:
                logging.warning("Could not find alert ID for social posting check")
                return

            alert_id = result[0]['id']

            # Check with social notifier
            check_result = self._social_notifier.check_alert(alert_id)

            if check_result.get('queued'):
                self.stats['social_queued'] += 1

        except Exception as e:
            logging.error("Social posting check failed: {}".format(e))
            # Don't fail the whole alert process if social posting fails
            pass

    def _log_alert_summary(self):
        """Log summary of alert processing results (debug only — kept lines handle user-facing output)"""
        logging.debug("")
        logging.debug("ALERT PROCESSING SUMMARY")
        logging.debug("Candidates found: {}".format(self.stats['candidates_found']))
        logging.debug("Filters applied: {} ETFs, {} delta".format(
            self.stats.get('etf_filtered', 0),
            self.stats.get('delta_filtered', 0)
        ))
        logging.debug("Alerts saved: {}".format(self.stats['alerts_sent']))
        logging.debug("Console notifications: {}".format(self.stats['console_sent']))
        logging.debug("Email notifications: {}".format(self.stats['email_sent']))
        logging.debug("Database saves: {} successful, {} failed".format(
            self.stats['alerts_sent'] - self.stats['save_failures'],
            self.stats['save_failures']
        ))

        if self._social_enabled and self.stats.get('social_queued', 0) > 0:
            logging.debug("Social posting: {} alerts queued".format(self.stats['social_queued']))

        if self.stats['save_failures'] > 0:
            logging.warning("Database save failures detected - check error logs")

    def generate_daily_summary(self, trade_date=None):
        """Generate end-of-day alert summary to reduce notification noise
        
        Args:
            trade_date: Date to summarize (defaults to today)
            
        Returns:
            dict: Summary statistics and top alerts
        """
        if not trade_date:
            trade_date = eastern_date_string()
        
        # Get all alerts for the day grouped by symbol
        query = '''
            SELECT symbol, COUNT(*) as alert_count,
                   MAX(significance_score) as max_score,
                   SUM(volume) as total_volume,
                   SUM(premium_value) as total_premium,
                   MAX(alert_level) as highest_level,
                   GROUP_CONCAT(DISTINCT alert_reason, '; ') as reasons
            FROM flow_alerts 
            WHERE DATE(alert_timestamp) = ?
            GROUP BY symbol
            ORDER BY max_score DESC, total_premium DESC
            LIMIT 20
        '''
        
        daily_alerts = self.storage.query_with_params(query, (trade_date,))
        
        # Get overall stats
        total_query = '''
            SELECT COUNT(*) as total_alerts,
                   COUNT(DISTINCT symbol) as unique_symbols,
                   SUM(premium_value) as total_premium,
                   AVG(significance_score) as avg_score,
                   COUNT(CASE WHEN alert_level = 'HIGH' THEN 1 END) as high_alerts,
                   COUNT(CASE WHEN alert_level = 'MEDIUM' THEN 1 END) as medium_alerts,
                   COUNT(CASE WHEN alert_level = 'LOW' THEN 1 END) as low_alerts
            FROM flow_alerts 
            WHERE DATE(alert_timestamp) = ?
        '''
        
        totals = self.storage.query_with_params(total_query, (trade_date,))
        total_stats = totals[0] if totals else {}
        
        summary = {
            'trade_date': trade_date,
            'total_alerts': total_stats.get('total_alerts', 0),
            'unique_symbols': total_stats.get('unique_symbols', 0),
            'total_premium': total_stats.get('total_premium', 0) or 0,
            'avg_score': total_stats.get('avg_score', 0) or 0,
            'high_alerts': total_stats.get('high_alerts', 0),
            'medium_alerts': total_stats.get('medium_alerts', 0),
            'low_alerts': total_stats.get('low_alerts', 0),
            'top_symbols': daily_alerts[:15]  # Top 15 symbols by score/premium
        }
        
        return summary

    def send_daily_summary_email(self, trade_date=None):
        """DEPRECATED: Daily summary now handled by fm_summary_orchestrator.py
        
        This method has been disabled to prevent multiple daily summaries.
        Enhanced summaries are now generated by FMAlertSummary in fm_summary_orchestrator.py
        
        Args:
            trade_date: Date to summarize (defaults to today)
            
        Returns:
            bool: Always returns True to maintain compatibility
        """
        logging.warning("send_daily_summary_email() called on FMAlerts class but DISABLED")
        logging.warning("Daily summaries now only run from fm_summary_orchestrator.py")
        logging.warning("This prevents multiple summary emails per day")
        return True  # Return success to avoid breaking calling code

    def _create_daily_summary_html(self, summary):
        """Create HTML content for daily summary email
        
        Args:
            summary: Summary dictionary from generate_daily_summary
            
        Returns:
            str: HTML content for email body
        """
        current_time = now_eastern().strftime('%Y-%m-%d %H:%M:%S ET')
        total_premium_str = "${:,.0f}".format(summary['total_premium'])
        
        html_parts = [
            '<html><body>',
            '<h2>Flow Monitor Daily Summary</h2>',
            '<p><strong>Date:</strong> {}</p>'.format(summary['trade_date']),
            '<p><strong>Generated:</strong> {}</p>'.format(current_time),
            '<br>',
            '<h3>Daily Statistics</h3>',
            '<ul>',
            '<li><strong>Total Alerts:</strong> {}</li>'.format(summary['total_alerts']),
            '<li><strong>Unique Symbols:</strong> {}</li>'.format(summary['unique_symbols']),
            '<li><strong>Total Premium:</strong> {}</li>'.format(total_premium_str),
            '<li><strong>Average Score:</strong> {:.1f}</li>'.format(summary['avg_score']),
            '<li><strong>High Priority:</strong> {}</li>'.format(summary['high_alerts']),
            '<li><strong>Medium Priority:</strong> {}</li>'.format(summary['medium_alerts']),
            '<li><strong>Low Priority:</strong> {}</li>'.format(summary['low_alerts']),
            '</ul>',
            '<br>',
            '<h3>Top Symbols by Significance</h3>',
            '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">',
            '<thead>',
            '<tr style="background-color: #f0f0f0;">',
            '<th>Symbol</th>',
            '<th>Alert Count</th>',
            '<th>Max Score</th>',
            '<th>Total Volume</th>',
            '<th>Total Premium</th>',
            '<th>Highest Level</th>',
            '<th>Primary Reasons</th>',
            '</tr>',
            '</thead>',
            '<tbody>'
        ]
        
        # Add rows for each top symbol
        for symbol_data in summary['top_symbols']:
            premium = symbol_data.get('total_premium', 0) or 0
            if premium >= 1000000:
                premium_str = "${:.1f}M".format(premium / 1000000)
            elif premium >= 1000:
                premium_str = "${:.0f}K".format(premium / 1000)
            else:
                premium_str = "${:.0f}".format(premium)
            
            # Color coding for highest alert level
            level = symbol_data.get('highest_level', 'MEDIUM')
            if level == 'HIGH':
                row_style = 'background-color: #ffe0e0;'  # Light red
            elif level == 'MEDIUM':
                row_style = 'background-color: #fff9e0;'  # Light yellow
            else:
                row_style = ''
            
            # Truncate reasons for display
            reasons = symbol_data.get('reasons', '')
            if len(reasons) > 80:
                reasons = reasons[:77] + "..."
            
            row = '<tr style="{}">'.format(row_style)
            row += '<td><strong>{}</strong></td>'.format(symbol_data.get('symbol', ''))
            row += '<td>{}</td>'.format(symbol_data.get('alert_count', 0))
            row += '<td>{:.1f}</td>'.format(symbol_data.get('max_score', 0))
            row += '<td>{:,}</td>'.format(symbol_data.get('total_volume', 0))
            row += '<td>{}</td>'.format(premium_str)
            row += '<td>{}</td>'.format(level)
            row += '<td style="font-size: 11px;">{}</td>'.format(reasons)
            row += '</tr>'
            
            html_parts.append(row)
        
        html_parts.extend([
            '</tbody>',
            '</table>',
            '<br>',
            '<p><em>This daily summary consolidates all Flow Monitor alerts for {}.</em></p>'.format(summary['trade_date']),
            '<p><em>Individual real-time alerts were sent throughout the trading day.</em></p>',
            '</body></html>'
        ])
        
        return '\n'.join(html_parts)

def main():
    """Main function for standalone testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Flow Monitor Alert Processor')
    parser.add_argument('--scan-timestamp',
                       help='Specific scan timestamp to process alerts for')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: process latest scan and show results')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    parser.add_argument('--daily-summary', action='store_true',
                       help='Generate and send daily summary email')
    parser.add_argument('--summary-date', 
                       help='Date for daily summary (YYYY-MM-DD, defaults to today)')                   
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    try:
        # Initialize components
        config_manager = FMConfig()
        storage = FlowMonitorStorage(config_manager)
        alerts_processor = FMAlerts(config_manager, storage)
        
        # Determine scan timestamp
        scan_timestamp = args.scan_timestamp
        if not scan_timestamp:
            # Get latest scan timestamp from database
            latest_scan = storage.get_latest_scan_timestamp()
            if latest_scan:
                scan_timestamp = latest_scan
                logging.info("Using latest scan timestamp: {}".format(scan_timestamp))
            else:
                logging.error("No scan timestamp provided and no scans found in database")
                return 1
        
        # Show scan age for awareness
        try:
            from datetime import datetime
            scan_dt = datetime.fromisoformat(scan_timestamp.replace(' ', 'T'))
            now_dt = datetime.fromisoformat(eastern_isoformat().replace(' ', 'T'))
            age_minutes = (now_dt - scan_dt).total_seconds() / 60
            
            if age_minutes > 60:
                logging.warning("Processing alerts from {:.1f} minutes ago".format(age_minutes))
            else:
                logging.info("Processing recent scan ({:.1f} minutes old)".format(age_minutes))
        except:
            pass  # Not critical
        
        # Process alerts
        results = alerts_processor.process_alerts(scan_timestamp)
        
        if args.test:
            logging.info("Testing mode - showing alert processing results:")
            logging.info("Candidates: {}, Sent: {}".format(
                results['candidates_found'],
                results['alerts_sent']
            ))
        
        # Handle daily summary if requested
        if args.daily_summary:
            logging.info("Generating daily summary...")
            summary_date = args.summary_date if args.summary_date else None
            success = alerts_processor.send_daily_summary_email(summary_date)
            if success:
                logging.info("Daily summary sent successfully")
            else:
                logging.error("Failed to send daily summary")
                return 1
                
        # Return success/failure code
        if results['save_failures'] > 0:
            logging.warning("Alert processing completed with {} save failures".format(
                results['save_failures']))
            return 1
        else:
            logging.info("Alert processing completed successfully")
            return 0
            
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130
    except Exception as e:
        logging.error("Alert processing failed: {}".format(e))
        return 1


if __name__ == '__main__':
    exit(main())