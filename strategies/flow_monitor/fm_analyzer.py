#!/usr/bin/env python3
"""
Flow Monitor Statistical Analyzer (fm_analyzer.py)
--------------------------------------------------
Phase 2: Unified Institutional Flow Detection Algorithm
Implements the validated algorithm from Phase 1 historical analysis for real-time scanning.

Algorithm Components:
1. Premium Filtering - Market cap aware thresholds ($150K-$400K based on symbol size)
2. Volume Surprise Calculation - Market-aware baseline estimation with institutional psychology
3. Unified Scoring - Combine premium (0-6) + volume surprise (0-4) into 0-10 scale

v2 (2026-04): Smart money score removed — provided no discriminating signal and was double-counted.
See research/alert_no_smart_money.py for analysis. Threshold lowered from 6.0 to 3.5.

Processes contracts from scan_timestamp and updates with significance_score.

Author: Ben (with assistance from Claude)
Date: 2025-06-28 (Phase 2 - Unified Algorithm Implementation)
"""

import logging
import sys
import math
import time
import os
from pathlib import Path
from collections import defaultdict
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string
from tools.decimal_formatter import clean_database_row

def safe_gt(val, threshold):
    """Safely compare if val > threshold, treating None as always False"""
    return isinstance(val, (int, float)) and val > threshold

class FMAnalyzer:
    def __init__(self, storage):
        """Initialize analyzer with storage layer
        
        Args:
            storage: FlowMonitorStorage instance
        """
        self.storage = storage
        
        # Enhanced statistics tracking for unified algorithm
        self.analysis_stats = {
            # Keep existing
            'contracts_processed': 0,
            'contracts_updated': 0,
            'missing_baselines': 0,
            'errors': 0,
            
            # Add unified algorithm metrics
            'premium_filtered': 0,      # Failed premium threshold
            'volume_filtered': 0,       # Failed volume surprise  
            'unified_alerts': 0,        # Score >= 3.5 (v2, was 6.0)
            'high_conviction': 0,       # Score >= 5.0 (v2, was 8.0)
            'early_day_fallbacks': 0,   # Times we used baseline due to low daily volume
            'running_total_used': 0,    # Times we used running daily total
            
            # Data quality monitoring (ChatGPT suggestions)
            'missing_price_data': 0,    # All price fields missing/zero
            'bad_tick_data': 0,         # Ask < bid anomalies
            'data_quality_warnings': 0, # General data quality issues
            'exceptional_volume_day': 0    # Times we detected exceptional daily volume
        }
               
        # Premium thresholds by market cap (validated from Phase 1)
        self.PREMIUM_THRESHOLDS = {
            'mega_cap': 400_000,   
            'large_cap': 300_000,  
            'mid_cap': 200_000,
            'small_cap': 150_000
        }
        
        # Algorithm constants (centralized magic numbers)
        self.PREMIUM_BASE_THRESHOLD = 300_000    # Base premium for log scoring
        self.VOLUME_MULTIPLIER_THRESHOLD = 3.0   # 3x normal volume minimum
        self.ALERT_SCORE_THRESHOLD = 3.5         # Minimum score for alerts (v2: was 6.0 pre-April 2026)
        self.HIGH_CONVICTION_THRESHOLD = 5.0     # High conviction threshold (v2: was 8.0, review May 2026)
        self.EARLY_DAY_VOLUME_THRESHOLD = 1000   # Minimum daily volume for running total
        self.INSTITUTIONAL_DELTA_THRESHOLD = 0.85  # Filter deep ITM institutional trades
        
        # Market cap classification lookup (static for KLMN 800)
        self.MARKET_CAP_LOOKUP = self._build_market_cap_lookup()
        
        # Per-cycle timing breakdown (consumed by fm_main.py for perf tracking)
        self.last_query_elapsed = 0.0      # Steps 1-3: DB reads + market regime
        self.last_scoring_elapsed = 0.0    # Step 4: per-contract scoring loop
        self.last_db_write_elapsed = 0.0   # Step 5: batch update to DB

        logging.debug("FM Analyzer initialized with Phase 2 Unified Algorithm")
    
    def _build_market_cap_lookup(self):
        """Build static market cap classification for known symbols"""
        return {
            # Mega Cap (>$200B)
            'AAPL': 'mega_cap', 'MSFT': 'mega_cap', 'NVDA': 'mega_cap', 'GOOGL': 'mega_cap',
            'GOOG': 'mega_cap', 'AMZN': 'mega_cap', 'META': 'mega_cap', 'TSLA': 'mega_cap',
            'BRK.B': 'mega_cap', 'TSM': 'mega_cap', 'LLY': 'mega_cap', 'JPM': 'mega_cap',
            
            # Major ETFs (treat as mega cap due to liquidity)
            'SPY': 'mega_cap', 'QQQ': 'mega_cap', 'IWM': 'mega_cap', 'VTI': 'mega_cap',
            'TLT': 'mega_cap', 'XLF': 'mega_cap', 'XLE': 'mega_cap', 'XLK': 'mega_cap',
            'XLI': 'mega_cap', 'XLV': 'mega_cap', 'XLP': 'mega_cap', 'XLU': 'mega_cap',
            
            # Large Cap ($10B-$200B) - Major S&P 500 constituents
            'V': 'large_cap', 'JNJ': 'large_cap', 'WMT': 'large_cap', 'PG': 'large_cap',
            'UNH': 'large_cap', 'HD': 'large_cap', 'MA': 'large_cap', 'NFLX': 'large_cap',
            'DIS': 'large_cap', 'ADBE': 'large_cap', 'PYPL': 'large_cap', 'INTC': 'large_cap',
            'CMCSA': 'large_cap', 'CSCO': 'large_cap', 'PEP': 'large_cap', 'ABT': 'large_cap',
            'CRM': 'large_cap', 'ACN': 'large_cap', 'TMO': 'large_cap', 'COST': 'large_cap',
            'AVGO': 'large_cap', 'DHR': 'large_cap', 'NEE': 'large_cap', 'LIN': 'large_cap',
            'TXN': 'large_cap', 'HON': 'large_cap', 'QCOM': 'large_cap', 'UPS': 'large_cap',
            'LOW': 'large_cap', 'AMD': 'large_cap', 'IBM': 'large_cap', 'ORCL': 'large_cap',
            'CVX': 'large_cap', 'C': 'large_cap', 'MDT': 'large_cap', 'CAT': 'large_cap'
        }
    
    def _get_market_cap_category(self, symbol, volume_baseline=None):
        """Get market cap category for symbol with fallback logic"""
        if symbol in self.MARKET_CAP_LOOKUP:
            return self.MARKET_CAP_LOOKUP[symbol]
        
        # Fallback to volume-based classification
        # This is a rough approximation based on typical option volume patterns
        if volume_baseline is not None:
            if volume_baseline > 50000:  # Very high volume stocks
                return 'mega_cap'
            elif volume_baseline > 20000:  # High volume stocks  
                return 'large_cap'
            elif volume_baseline > 5000:   # Medium volume stocks
                return 'mid_cap'
                
        return 'small_cap'  # Default for None or low volume
    
    def analyze(self, scan_timestamp, test_mode=False, backfill_mode=False):
        """Analyze contracts from specific scan and update with unified scores
        
        Args:
            scan_timestamp: ISO timestamp string for scan to analyze
            test_mode: If True, lower thresholds for testing and tag alerts
            backfill_mode: If True, analyze all contracts without early filtering
            
        Returns:
            dict: Analysis statistics and results
        """
        mode_desc = "TEST MODE" if test_mode else ("backfill mode" if backfill_mode else "live production mode")
        logging.debug("Starting unified algorithm analysis for scan: {} ({})".format(scan_timestamp, mode_desc))

        # Lower alert threshold if in test mode
        if test_mode:
            self.ALERT_SCORE_THRESHOLD = 1.5  # Test mode (production is 3.5)
            self.HIGH_CONVICTION_THRESHOLD = 3.0  # Test mode (production is 5.0)
            logging.warning("TEST MODE: Lowering alert thresholds for demonstration")
        
        # Reset stats and timers for this analysis
        self.analysis_stats = {key: 0 for key in self.analysis_stats}
        self.last_query_elapsed = 0.0
        self.last_scoring_elapsed = 0.0
        self.last_db_write_elapsed = 0.0

        start_time = time.time()
        
        try:
            # Step 1: Get contracts from this scan with baseline data
            contracts_data = self._get_contracts_with_baselines(scan_timestamp)

            # Store raw scan contracts for downstream use (e.g., roll detection in fm_alerts.py)
            self.last_scan_contracts = contracts_data

            if not contracts_data:
                logging.warning("No contracts found for scan_timestamp: {}".format(scan_timestamp))
                return self.analysis_stats
            
            logging.debug("Retrieved {} contracts for unified analysis".format(len(contracts_data)))
            from tools.log_utils import beautiful_log
            beautiful_log("Analyzing {:,} contracts for significant flow activity".format(len(contracts_data)), 'info')

            # Step 2: Pre-compute all symbol daily totals (performance optimization)
            logging.debug("About to call _get_all_symbol_daily_totals_for_scan...")
            symbol_daily_totals = self._get_all_symbol_daily_totals_for_scan(scan_timestamp)
            logging.debug("_get_all_symbol_daily_totals_for_scan completed, found {} symbols".format(len(symbol_daily_totals)))
            logging.debug("Pre-computed daily totals for {} symbols".format(len(symbol_daily_totals)))

            # Step 2b: Pre-load previous scan data for time-series delta calculation
            # Extract trade_date from scan_timestamp
            if 'T' in scan_timestamp:
                trade_date = scan_timestamp.split('T')[0]
            elif ' ' in scan_timestamp:
                trade_date = scan_timestamp.split(' ')[0]
            else:
                from tools.timezone_utils import eastern_date_string
                trade_date = eastern_date_string()

            # Fetch multiple fields from previous scan for time-series tracking
            fields_to_track = ['volume', 'iv', 'last_price', 'underlying_price']
            previous_scan_data = self._get_previous_scan_data(scan_timestamp, trade_date, fields_to_track)
            logging.debug("Pre-loaded {} previous scan records with {} fields for delta calculation".format(
                len(previous_scan_data), len(fields_to_track)))

            # Step 3: Get current market regime (for potential future use)
            market_regime = self._get_market_regime()
            self.last_query_elapsed = time.time() - start_time
            beautiful_log("Market regime: {}".format(market_regime), 'info')

            # Step 4: Calculate unified scores for all contracts
            scoring_start = time.time()
            updates_data = []
            
            for contract in contracts_data:
                self.analysis_stats['contracts_processed'] += 1
                contract_id = contract.get("id", "UNKNOWN")

                try:
                    # Calculate unified institutional flow score with time-series deltas
                    unified_score, smart_money_score, volume_surprise, alert_reason, deltas = self._calculate_unified_score(
                        contract, symbol_daily_totals, backfill_mode, previous_scan_data
                    )

                    # Track alert categories (using centralized thresholds)
                    if unified_score >= self.HIGH_CONVICTION_THRESHOLD:
                        self.analysis_stats['high_conviction'] += 1
                    if unified_score >= self.ALERT_SCORE_THRESHOLD:
                        self.analysis_stats['unified_alerts'] += 1

                    # Prepare update data for database
                    premium_value = self._calculate_premium(contract)
                    flow_percentage = 0.0
                    if symbol_daily_totals and contract['symbol'] in symbol_daily_totals:
                        daily_total = symbol_daily_totals[contract['symbol']]
                        if daily_total > 0:
                            flow_percentage = (contract['volume'] / daily_total) * 100

                    update_record = {
                        'contract_hash': contract['contract_hash'],
                        'significance_score': unified_score,
                        'volume_surprise_factor': volume_surprise if volume_surprise else 0.0,
                        'alert_reason': alert_reason,
                        'premium_value': premium_value,
                        'flow_percentage': flow_percentage,
                        'alert_threshold_met': unified_score >= self.ALERT_SCORE_THRESHOLD,
                        # Time-series deltas
                        'volume_change': deltas.get('volume_change'),
                        'volume_change_pct': deltas.get('volume_change_pct'),
                        'iv_change': deltas.get('iv_change'),
                        'iv_change_pct': deltas.get('iv_change_pct'),
                        'price_change': deltas.get('price_change'),
                        'price_change_pct': deltas.get('price_change_pct'),
                        'underlying_change': deltas.get('underlying_change'),
                        'underlying_change_pct': deltas.get('underlying_change_pct'),
                        'option_leverage': deltas.get('option_leverage')
                    }
                    # Apply decimal policy formatting before database insertion
                    update_record = clean_database_row(update_record)
                    updates_data.append(update_record)

                except TypeError as e:
                    self.analysis_stats['errors'] += 1
                    logging.error("TypeError while analyzing contract ID {}: {}".format(contract_id, e))
                    for key in ["volume", "open_interest", "delta", "gamma", "theta", "vega"]:
                        val = contract.get(key)
                        logging.debug("  {}: {} (type: {})".format(key, repr(val), type(val)))
                    continue

                except Exception as e:
                    self.analysis_stats['errors'] += 1
                    logging.error("Failed to analyze contract ID {}: {}".format(contract_id, e))
                    continue

            self.last_scoring_elapsed = time.time() - scoring_start

            # Step 5: Batch update contracts (live mode only)
            if updates_data:
                beautiful_log("Writing {:,} score updates to database".format(len(updates_data)), 'info')
                db_write_start = time.time()
                success = self._batch_update_contracts(updates_data, scan_timestamp)
                self.last_db_write_elapsed = time.time() - db_write_start

                if success:
                    self.analysis_stats['contracts_updated'] = len(updates_data)
                    logging.debug("Successfully updated {} contracts".format(len(updates_data)))
                else:
                    logging.error("Failed to update contracts in database")

            # Step 6: Log analysis summary
            total_time = time.time() - start_time
            self._log_analysis_summary(total_time)

            return self.analysis_stats
            
        except Exception as e:
            logging.error("Unified analysis failed for scan {}: {}".format(scan_timestamp, e))
            self.analysis_stats['errors'] += 1
            return self.analysis_stats
    
    def _get_contracts_with_baselines(self, scan_timestamp):
        """Get contracts for analysis with joined baseline data
        
        Args:
            scan_timestamp: Scan timestamp to analyze
            
        Returns:
            list: List of contract dictionaries with baseline data
        """
        query = '''
            SELECT
                ocl.contract_hash,
                ocl.symbol,
                ocl.strike,
                ocl.expiration_date,
                ocl.option_type,
                ocl.volume,
                ocl.open_interest,
                ocl.last_price,
                ocl.bid,
                ocl.ask,
                ocl.underlying_price,
                ocl.iv as implied_volatility,
                ocl.delta,
                ocl.scan_timestamp,
                ocl.trade_date,

                -- Baseline data for volume surprise calculation
                sb.volume_mean,
                sb.volume_std,
                sb.vol_oi_mean,
                sb.vol_oi_std,
                sb.sample_size

            FROM flow_options_scans ocl  -- ocl = legacy alias for backward compatibility
            LEFT JOIN symbol_baselines sb ON ocl.symbol = sb.symbol
            WHERE ocl.scan_timestamp = ?
            ORDER BY ocl.symbol, ocl.volume DESC
        '''
        
        return self.storage.query_with_params(query, (scan_timestamp,))
    
    def _calculate_unified_score(self, contract, symbol_daily_totals=None, backfill_mode=False, previous_scan_data=None):
        """Calculate unified institutional flow score - orchestrator method

        Args:
            contract: Contract data dictionary
            symbol_daily_totals: Pre-computed daily volume totals
            backfill_mode: Whether in backfill mode (skips filters)
            previous_scan_data: Dict of {contract_hash: {field: value}} from previous scan
        """
        # Component 1: Premium calculation
        premium_value = self._calculate_premium(contract)

        # Track filtering but don't return early
        passes_premium_filter = self._passes_premium_filter(contract, premium_value)
        if not passes_premium_filter:
            self.analysis_stats['premium_filtered'] += 1

        # Component 2: Calculate ALL time-series deltas (volume, IV, price, underlying, leverage)
        deltas = self._calculate_time_series_deltas(contract, previous_scan_data)

        # Extract values for existing logic
        # Use volume_change if available (subsequent scan), otherwise use absolute volume (first scan)
        is_first_scan = deltas.get('is_first_scan', True)
        if is_first_scan:
            volume_delta = contract.get('volume', 0)  # First scan: use absolute volume
        else:
            volume_delta = deltas.get('volume_change', 0)  # Subsequent scan: use delta (even if 0)

        # Debug logging for volume surge tracking
        if deltas.get('volume_change') and deltas['volume_change'] > 1000:
            logging.debug("Volume surge tracking: {} - surge: {:+,}".format(
                contract.get('contract_hash'), deltas['volume_change']))

        # Component 3: Volume surprise calculation using volume surge (or absolute volume if first scan)
        volume_surprise = self._calculate_volume_surprise(contract, symbol_daily_totals, volume_delta, is_first_scan)        
        
        # Track filtering but don't return early
        passes_volume_filter = volume_surprise is not None and volume_surprise >= self.VOLUME_MULTIPLIER_THRESHOLD
        if not passes_volume_filter:
            self.analysis_stats['volume_filtered'] += 1
            if volume_surprise is None:
                volume_surprise = 0.0  # Default for calculation
        
        # v2 (2026-04): Smart money removed — provided no discriminating signal (58% scored 1.3,
        # 87% scored 1.1-1.3). Was also double-counted (here + inside _calculate_flow_score).
        # See research/alert_no_smart_money.py, research/alert_premium_vs_wins.py for analysis.

        # Calculate score from premium + volume surprise only
        symbol = contract.get('symbol', '')
        volume_baseline = contract.get('volume_mean')
        base_score = self._calculate_flow_score(premium_value, volume_surprise, contract, symbol, volume_baseline)
                
        # Apply hard filters - return early if not passed (unless backfill mode)
        surge_info_str = "first_scan" if is_first_scan else "vol_surge={:+,}".format(int(volume_delta))

        if not passes_premium_filter and not backfill_mode:
            return 0.0, 0.0, 0.0, "premium_filtered (${:.0f} < threshold, {})".format(premium_value, surge_info_str), deltas

        if not passes_volume_filter and not backfill_mode:
            return 0.0, 0.0, volume_surprise or 0.0, "volume_filtered ({:.1f}x < {:.1f}x, {})".format(
                volume_surprise or 0.0, self.VOLUME_MULTIPLIER_THRESHOLD, surge_info_str), deltas        
        
        unified_score = min(10.0, max(0.0, base_score))  # Ensure bounds        
        
        # Generate alert reason with filter status
        filter_status = []
        if not passes_premium_filter:
            filter_status.append("low_premium")
        if not passes_volume_filter:
            filter_status.append("low_volume")
        
        calculation_method = "running_total" if symbol_daily_totals and contract['symbol'] in symbol_daily_totals else "baseline_est"

        # Build alert reason with volume surge information
        # Build time-series metrics string for alert_reason
        if is_first_scan:
            surge_info = "first_scan"
        else:
            surge_parts = []
            if deltas.get('volume_change'):
                surge_parts.append("vol:{:+,}".format(int(deltas['volume_change'])))
            if deltas.get('iv_change_pct') is not None:
                surge_parts.append("IV:{:+.1f}%".format(deltas['iv_change_pct']))
            if deltas.get('price_change_pct') is not None:
                surge_parts.append("price:{:+.1f}%".format(deltas['price_change_pct']))
            if deltas.get('option_leverage') is not None:
                surge_parts.append("leverage:{:.1f}x".format(deltas['option_leverage']))
            surge_info = ", ".join(surge_parts) if surge_parts else "no_change"

        if filter_status:
            alert_reason = "v2| score: {:.1f} (prem=${:.0f}, vol={:.1f}x, {}, method={}, filtered: {})".format(
                unified_score, premium_value, volume_surprise, surge_info, calculation_method, ",".join(filter_status)
            )
        else:
            alert_reason = "v2| score: {:.1f} (prem=${:.0f}, vol={:.1f}x, {}, method={})".format(
                unified_score, premium_value, volume_surprise, surge_info, calculation_method
            )

        # Return 0.0 in smart_money slot for backward compat (tuple position 1)
        return unified_score, 0.0, volume_surprise, alert_reason, deltas
    
    def _calculate_premium(self, contract):
        """Calculate total premium value (direct transfer from historical analyzer)
        
        Args:
            contract: Contract data dictionary
            
        Returns:
            float: Premium value in dollars
        """
        try:
            volume = contract.get('volume', 0)
            bid = contract.get('bid', 0)
            ask = contract.get('ask', 0)
            last_price = contract.get('last_price', 0)
            symbol = contract.get('symbol', 'UNKNOWN')
            
            # Validate inputs - handle None values
            if volume is None or volume <= 0:
                return 0.0
            
            # Data quality check: detect bad tick data (ask < bid)
            if bid > 0 and ask > 0 and ask < bid:
                logging.warning("Bad tick data detected: {} ask={:.2f} < bid={:.2f}".format(symbol, ask, bid))
                self.analysis_stats['bad_tick_data'] += 1
                self.analysis_stats['data_quality_warnings'] += 1
                # Use last_price as fallback if available
                if last_price > 0:
                    mid_price = last_price
                else:
                    return 0.0  # No reliable pricing data
            
            # Enhanced bid/ask validation with fallback to last_price (handle None values)
            elif bid and bid > 0 and ask and ask > 0:
                mid_price = (bid + ask) / 2
            elif ask and ask > 0:  # Allow cases where bid is 0 but ask exists
                mid_price = ask * 0.95  # Slightly below ask as estimate
            elif last_price and last_price > 0:  # Fallback to last traded price
                mid_price = last_price
            else:
                # Data quality alert: all price data missing
                logging.warning("Missing all price data for {} - upstream data issue? volume={}".format(symbol, volume))
                self.analysis_stats['missing_price_data'] += 1
                self.analysis_stats['data_quality_warnings'] += 1
                return 0.0  # No valid pricing data
            
            return volume * mid_price * 100  # Contract multiplier = 100
            
        except Exception as e:
            logging.debug("Error calculating premium for {}: {}".format(contract.get('symbol', 'UNKNOWN'), e))
            return 0.0
    
    def _passes_premium_filter(self, contract, premium_value):
        """Check if contract passes premium threshold for its market cap
        
        Args:
            contract: Contract data dictionary
            premium_value: Calculated premium value
            
        Returns:
            bool: True if passes filter, False otherwise
        """
        if premium_value is None or premium_value <= 0:
            return False
            
        # Get market cap category and threshold
        symbol = contract['symbol']
        market_cap_category = self._get_market_cap_category(symbol, contract.get('volume_mean'))
        threshold = self.PREMIUM_THRESHOLDS[market_cap_category]
        
        return premium_value >= threshold
    
    def _calculate_volume_surprise(self, contract, symbol_daily_totals=None, volume_to_analyze=None, is_first_scan=True):
        """Calculate volume surprise using market-aware baseline estimation
        Enhanced with delta-based surge detection for position building alerts

        Args:
            contract: Contract data dictionary
            symbol_daily_totals: Pre-computed daily totals (performance optimization)
            volume_to_analyze: Volume delta (if subsequent scan) or absolute volume (if first scan)
            is_first_scan: Whether this is the first scan of the day for this contract

        Returns:
            float: Volume surprise factor or None if insufficient data
        """
        try:
            symbol = contract['symbol']
            volume_mean = contract.get('volume_mean')  # Log-space baseline

            # Use provided volume_to_analyze (delta or absolute), fallback to contract volume
            if volume_to_analyze is None:
                volume_to_analyze = contract.get('volume', 0)

            if volume_to_analyze is None or volume_to_analyze <= 0:
                return None
                
            if not volume_mean or volume_mean <= 0:
                self.analysis_stats['missing_baselines'] += 1
                return None
            
            # Try pre-computed daily total first (performance optimization)
            running_daily_total = None
            if symbol_daily_totals and symbol in symbol_daily_totals:
                running_daily_total = symbol_daily_totals[symbol]
            
            # Early day threshold: if daily total is very small, fall back to baseline
            # This addresses the Phase 1 developer's concern about early day instability
            early_day_threshold = self.EARLY_DAY_VOLUME_THRESHOLD
            
            if running_daily_total and running_daily_total > early_day_threshold:
                # Check if this is an exceptional volume day (institutional activity)
                actual_baseline_daily = self._safe_exp(volume_mean)
                daily_surprise_ratio = running_daily_total / max(actual_baseline_daily, 1)
                
                if daily_surprise_ratio > 3.0:
                    # Exceptional volume day - use baseline method for better institutional detection
                    self.analysis_stats['exceptional_volume_day'] = self.analysis_stats.get('exceptional_volume_day', 0) + 1
                    contracts_per_day_estimate = self._estimate_contracts_per_day(symbol, volume_mean)
                    typical_contract_volume = actual_baseline_daily / contracts_per_day_estimate
                    typical_contract_volume = max(typical_contract_volume, 500)  # Floor
                    volume_surprise = volume_to_analyze / typical_contract_volume

                    scan_type = "first_scan" if is_first_scan else "delta"
                    logging.debug("Volume surprise for {}: exceptional_day method ({}), {}x daily, baseline={:.0f}, typical={:.0f}, vol={:.0f}, surprise={:.1f}x".format(
                        symbol, scan_type, daily_surprise_ratio, actual_baseline_daily, typical_contract_volume, volume_to_analyze, volume_surprise))
                else:
                    # Normal volume day - use running total method
                    self.analysis_stats['running_total_used'] += 1
                    contracts_per_day = self._estimate_contracts_per_day(symbol, volume_mean)
                    contracts_per_day = max(1, contracts_per_day)
                    typical_contract_volume = running_daily_total / contracts_per_day
                    typical_contract_volume = max(typical_contract_volume, 500)  # Floor
                    volume_surprise = volume_to_analyze / typical_contract_volume

                    scan_type = "first_scan" if is_first_scan else "delta"
                    logging.debug("Volume surprise for {}: running_total method ({}), daily={:.0f}, typical={:.0f}, vol={:.0f}, surprise={:.1f}x".format(
                        symbol, scan_type, running_daily_total, typical_contract_volume, volume_to_analyze, volume_surprise))
            else:
                # Fallback: The Arbiter's market-aware baseline estimation
                if running_daily_total and running_daily_total <= early_day_threshold:
                    self.analysis_stats['early_day_fallbacks'] += 1
                
                actual_baseline_daily = self._safe_exp(volume_mean)
                
                # Adjust baseline by symbol characteristics (from Phase 1 validation)
                if symbol in ['SPY', 'QQQ', 'IWM', 'XLF', 'XLE', 'XLK', 'XLI']:  # Ultra-liquid ETFs
                    contracts_per_day_estimate = 500  # Many strikes trade actively
                elif actual_baseline_daily > 100_000:  # High volume names (NVDA, AAPL, TSLA)
                    contracts_per_day_estimate = 200   
                elif actual_baseline_daily > 20_000:   # Medium volume (most MAG7)
                    contracts_per_day_estimate = 100   
                else:  # Lower volume names
                    contracts_per_day_estimate = 50
                    
                # Typical contract gets 1/N of daily volume
                typical_contract_volume = actual_baseline_daily / contracts_per_day_estimate
                typical_contract_volume = max(typical_contract_volume, 500)  # Floor
                volume_surprise = volume_to_analyze / typical_contract_volume

                fallback_reason = "early_day" if running_daily_total and running_daily_total <= early_day_threshold else "no_daily_total"
                scan_type = "first_scan" if is_first_scan else "delta"
                logging.debug("Volume surprise for {}: baseline_est method ({}, {}), baseline={:.0f}, typical={:.0f}, vol={:.0f}, surprise={:.1f}x".format(
                    symbol, fallback_reason, scan_type, actual_baseline_daily, typical_contract_volume, volume_to_analyze, volume_surprise))
            
            return volume_surprise
            
        except Exception as e:
            logging.debug("Error calculating volume surprise for {}: {}".format(contract.get('symbol', 'UNKNOWN'), e))
            return None
    
    def _estimate_contracts_per_day(self, symbol, volume_mean):
        """Estimate number of contracts per day for symbol (helper for running total calculation)"""
        actual_baseline_daily = self._safe_exp(volume_mean)

        if symbol in ['SPY', 'QQQ', 'IWM', 'XLF', 'XLE', 'XLK', 'XLI']:  # Ultra-liquid ETFs
            return 500
        elif actual_baseline_daily > 100_000:  # High volume names
            return 200
        elif actual_baseline_daily > 20_000:   # Medium volume
            return 100
        else:  # Lower volume names
            return 50

    def _get_previous_scan_volumes(self, scan_timestamp, trade_date):
        """Get volume from previous scan for delta calculation - OPTIMIZED batch approach

        Args:
            scan_timestamp: Current scan timestamp
            trade_date: Current trade date

        Returns:
            dict: {contract_hash: volume} for all contracts from previous scan
        """
        try:
            # Step 1: Find the previous scan timestamp (fast query)
            prev_scan_query = '''
                SELECT scan_timestamp
                FROM flow_options_scans
                WHERE trade_date = ?
                  AND scan_timestamp < ?
                ORDER BY scan_timestamp DESC
                LIMIT 1
            '''

            prev_scan_result = self.storage.query_with_params(prev_scan_query, (trade_date, scan_timestamp))

            if not prev_scan_result or len(prev_scan_result) == 0:
                # First scan of the day - no previous volumes
                logging.debug("No previous scan found for {} - first scan of day".format(scan_timestamp))
                return {}

            prev_scan_timestamp = prev_scan_result[0]['scan_timestamp']
            logging.debug("Previous scan timestamp: {}".format(prev_scan_timestamp))

            # Step 2: Load ALL contract volumes from previous scan (batch operation)
            volumes_query = '''
                SELECT contract_hash, volume
                FROM flow_options_scans
                WHERE trade_date = ?
                  AND scan_timestamp = ?
                  AND volume > 0
            '''

            results = self.storage.query_with_params(volumes_query, (trade_date, prev_scan_timestamp))

            # Step 3: Build lookup dictionary for O(1) access
            previous_volumes = {}
            for row in results:
                contract_hash = row['contract_hash']
                volume = row['volume']
                if contract_hash and volume is not None:
                    previous_volumes[contract_hash] = float(volume)

            logging.debug("Loaded {} previous scan volumes for delta calculation".format(len(previous_volumes)))
            return previous_volumes

        except Exception as e:
            logging.error("Error getting previous scan volumes: {}".format(e))
            return {}

    def _get_previous_scan_data(self, scan_timestamp, trade_date, fields):
        """
        GENERIC METHOD: Get any fields from previous scan for intraday time-series delta calculation

        This replaces the specialized _get_previous_scan_volumes() with a flexible version
        that can fetch ANY columns we want to track over time (volume, IV, price, underlying, etc.)

        Args:
            scan_timestamp (str): Current scan timestamp (e.g., '2025-09-26 10:30:00')
            trade_date (str): Current trade date (e.g., '2025-09-26')
            fields (list): Column names to retrieve (e.g., ['volume', 'iv', 'last_price', 'underlying_price'])

        Returns:
            dict: Nested dictionary for O(1) lookup:
                {
                    'NVDA|180.0|2025-10-17|CALL': {
                        'volume': 2682,
                        'iv': 0.359,
                        'last_price': 5.25,
                        'underlying_price': 125.50
                    },
                    ...
                }

        Example Usage:
            prev_data = self._get_previous_scan_data(
                scan_timestamp='2025-09-26 10:30:00',
                trade_date='2025-09-26',
                fields=['volume', 'iv', 'last_price', 'underlying_price']
            )

            if contract_hash in prev_data:
                prev = prev_data[contract_hash]
                volume_delta = current_volume - prev['volume']
                iv_change = current_iv - prev['iv']
        """
        try:
            # STEP 1: Find the previous scan timestamp
            prev_scan_query = '''
                SELECT scan_timestamp
                FROM flow_options_scans
                WHERE trade_date = ?
                  AND scan_timestamp < ?
                ORDER BY scan_timestamp DESC
                LIMIT 1
            '''

            prev_scan_result = self.storage.query_with_params(prev_scan_query, (trade_date, scan_timestamp))

            if not prev_scan_result or len(prev_scan_result) == 0:
                logging.debug("No previous scan found for {} - first scan of day".format(scan_timestamp))
                return {}

            prev_scan_timestamp = prev_scan_result[0]['scan_timestamp']
            logging.debug("Previous scan timestamp: {}".format(prev_scan_timestamp))

            # STEP 2: Build dynamic SQL query for requested fields
            # Always include contract_hash (our lookup key)
            fields_to_select = ['contract_hash'] + fields
            select_clause = ', '.join(fields_to_select)

            data_query = '''
                SELECT {fields}
                FROM flow_options_scans
                WHERE trade_date = ?
                  AND scan_timestamp = ?
            '''.format(fields=select_clause)

            # STEP 3: Execute query and fetch all previous scan data
            results = self.storage.query_with_params(data_query, (trade_date, prev_scan_timestamp))

            # STEP 4: Build nested dictionary for fast lookup
            previous_data = {}
            for row in results:
                contract_hash = row['contract_hash']

                if not contract_hash:
                    continue

                # Create nested dict with all requested field values
                previous_data[contract_hash] = {}
                for field in fields:
                    value = row.get(field)
                    if value is not None:
                        # Convert numeric values to float for consistency
                        previous_data[contract_hash][field] = float(value) if isinstance(value, (int, float)) else value

            logging.debug("Loaded {} previous scan records with {} fields for delta calculation".format(
                len(previous_data), len(fields)))

            return previous_data

        except Exception as e:
            logging.error("Error getting previous scan data: {}".format(e))
            return {}

    def _get_all_symbol_daily_totals_for_scan(self, scan_timestamp):
        """Get cumulative volume totals - OPTIMIZED for performance"""
        try:
            # Extract date from scan timestamp  
            if 'T' in scan_timestamp:
                trade_date = scan_timestamp.split('T')[0]
            elif ' ' in scan_timestamp:
                trade_date = scan_timestamp.split(' ')[0]
            else:
                from timezone_utils import eastern_date_string
                trade_date = eastern_date_string()
            
            # OPTIMIZED query - removed DATE() function that was causing the hang
            query = '''
                SELECT symbol, SUM(volume) as total_volume
                FROM flow_options_scans
                WHERE trade_date = ?
                AND scan_timestamp <= ?
                AND volume > 0
                GROUP BY symbol
                HAVING total_volume > 0
            '''
            
            results = self.storage.query_with_params(query, (trade_date, scan_timestamp))
            
            # Convert to dictionary for fast lookup
            daily_totals = {}
            for row in results:
                if row['total_volume'] is not None and row['total_volume'] > 0:
                    daily_totals[row['symbol']] = float(row['total_volume'])
                    
            logging.debug("Pre-computed daily totals for {} symbols using optimized query".format(len(daily_totals)))
            return daily_totals
            
        except Exception as e:
            logging.error("Error getting symbol daily totals for scan: {}".format(e))
            return {}
            
    def _calculate_flow_score(self, premium_value, volume_surprise, contract=None, symbol=None, volume_baseline=None):
        """Calculate flow score from premium + volume surprise.

        v2 (2026-04): Smart money removed. Score = premium (0-6) + volume surprise (0-4).
        Previously smart money (0-2) was added here AND in _calculate_unified_score (double-count bug).

        Args:
            premium_value: Premium value in dollars
            volume_surprise: Volume surprise factor
            contract: Contract data (unused after v2, kept for signature compat)
            symbol: Symbol for market cap lookup
            volume_baseline: Volume baseline for market cap heuristic

        Returns:
            float: Flow score (0-10 scale)
        """
        try:
            # Premium score (0-6 points, log scale)
            if not premium_value or premium_value < 1e-6:
                premium_score = 0.0
            else:
                try:
                    market_cap_category = self._get_market_cap_category(symbol, volume_baseline)
                    threshold = self.PREMIUM_THRESHOLDS[market_cap_category]
                    premium_log = math.log10(premium_value / threshold)
                    premium_score = min(6.0, premium_log * 2.0)
                except (ValueError, OverflowError) as e:
                    logging.warning("log10 failed for premium_value={}: {}".format(premium_value, e))
                    premium_score = 0.0

            # Volume surprise score (0-4 points, exponential scaling for extremes)
            if volume_surprise >= 25.0:  # Extreme outliers get exponential scaling
                surprise_score = min(4.0, 2.0 + math.log10(volume_surprise / 25.0) * 2.0)
            elif volume_surprise >= 10.0:  # High surprise gets linear scaling
                surprise_score = min(3.0, 1.5 + (volume_surprise - 10.0) / 15.0 * 1.5)
            else:  # Normal range (unchanged)
                surprise_score = min(2.0, (volume_surprise - 3.0) / 2.0 + 1.0)
            surprise_score = max(0.0, surprise_score)

            total_score = premium_score + surprise_score
            return min(10.0, total_score)
            
        except Exception as e:
            logging.debug("Error calculating flow score: {}".format(e))
            return 0.0
    
    def _safe_exp(self, x):
        """Safely compute exp(x) with overflow protection"""
        try:
            if x is None or x > 100:  # ~math.exp(100) = 2.7e43
                logging.warning("Skipping exp(x) due to large input: x={}".format(x))
                return 0
            return math.exp(x)
        except (OverflowError, ValueError) as e:
            logging.warning("math.exp() failed for x={}: {}".format(x, e))
            return 0
            
    # --- SMART MONEY SCORE: REMOVED 2026-04 (v2 scoring) ---
    # Provided no discriminating signal: 58% of alerts scored 1.3, 87% scored 1.1-1.3.
    # Only spread tightness remained active (time-of-day removed, vol/OI disabled).
    # Was double-counted: computed in both _calculate_unified_score() and _calculate_flow_score().
    # Analysis: research/alert_no_smart_money.py, research/alert_premium_vs_wins.py
    # To restore: uncomment this method and add its return value to base_score in
    # _calculate_unified_score() (line ~387). Update thresholds accordingly.
    #
    # def _calculate_smart_money_score(self, contract):
    #     """Calculate smart money behavior score (0-2 points)
    #     Based on timing, execution quality, and position building patterns
    #     """
    #     try:
    #         quality_score = 1.0
    #         symbol = contract.get('symbol', 'UNKNOWN')
    #
    #         # 1. TIME OF DAY ANALYSIS - REMOVED (no time-based penalties)
    #         pass
    #
    #         # 2. EXECUTION QUALITY (bid/ask behavior) with bad tick data protection
    #         bid = contract.get('bid', 0)
    #         ask = contract.get('ask', 0)
    #         last_price = contract.get('last_price', 0)
    #
    #         if bid and bid > 0 and ask and ask > 0 and ask < bid:
    #             self.analysis_stats['bad_tick_data'] += 1
    #             self.analysis_stats['data_quality_warnings'] += 1
    #             pass
    #         elif bid and bid > 0 and ask and ask > 0:
    #             mid_price = (bid + ask) / 2
    #             if mid_price > 0:
    #                 spread_pct = (ask - bid) / mid_price
    #                 if spread_pct < 0.05:
    #                     quality_score *= 1.2
    #                 elif spread_pct > 0.20:
    #                     quality_score *= 0.7
    #                 if last_price and last_price > 0 and abs(last_price - mid_price) / mid_price < 0.02:
    #                     quality_score *= 1.1
    #         elif bid == 0 and ask == 0 and last_price == 0:
    #             self.analysis_stats['missing_price_data'] += 1
    #             self.analysis_stats['data_quality_warnings'] += 1
    #
    #         # 3. VOLUME/OI RATIO - DISABLED
    #         pass
    #
    #         return min(2.0, max(0.0, quality_score))
    #     except Exception as e:
    #         return 1.0
    # --- END SMART MONEY SCORE ---

    def _calculate_time_series_deltas(self, contract, previous_scan_data):
        """
        Calculate all intraday time-series changes (volume, IV, price, underlying)

        This method compares current contract values to previous scan values to detect:
        - Volume surges (position building)
        - IV changes (buy vs sell pressure)
        - Price momentum (contract strength)
        - Underlying movement (market context)
        - Option leverage (unusual option behavior independent of stock)

        Args:
            contract (dict): Current contract data
            previous_scan_data (dict): Nested dict from _get_previous_scan_data()
                {contract_hash: {field: value, ...}}

        Returns:
            dict: Delta values for all tracked metrics:
                {
                    'volume_change': int or None,
                    'volume_change_pct': float or None,
                    'iv_change': float or None,
                    'iv_change_pct': float or None,
                    'price_change': float or None,
                    'price_change_pct': float or None,
                    'underlying_change': float or None,
                    'underlying_change_pct': float or None,
                    'option_leverage': float or None,
                    'is_first_scan': bool
                }
        """
        # Initialize all deltas as None (indicates no previous data)
        deltas = {
            'volume_change': None,
            'volume_change_pct': None,
            'iv_change': None,
            'iv_change_pct': None,
            'price_change': None,
            'price_change_pct': None,
            'underlying_change': None,
            'underlying_change_pct': None,
            'option_leverage': None,
            'is_first_scan': True
        }

        # Extract contract hash for lookup
        contract_hash = contract.get('contract_hash')

        # Check if previous scan data exists for this contract
        if not previous_scan_data or not contract_hash or contract_hash not in previous_scan_data:
            return deltas

        # Get previous scan values
        prev = previous_scan_data[contract_hash]
        deltas['is_first_scan'] = False

        # VOLUME DELTA
        if 'volume' in prev:
            current_vol = contract.get('volume', 0)
            prev_vol = prev['volume']
            deltas['volume_change'] = current_vol - prev_vol

            if prev_vol > 0:
                deltas['volume_change_pct'] = (deltas['volume_change'] / prev_vol) * 100

        # IMPLIED VOLATILITY DELTA
        # Database column name is 'iv' (mapped from 'implied_volatility' in collector)
        if 'iv' in prev and prev['iv'] > 0:
            current_iv = contract.get('implied_volatility', 0)  # Contract dict uses 'implied_volatility'
            prev_iv = prev['iv']  # Database uses 'iv'
            deltas['iv_change'] = current_iv - prev_iv
            deltas['iv_change_pct'] = (deltas['iv_change'] / prev_iv) * 100

        # OPTION PRICE DELTA
        if 'last_price' in prev and prev['last_price'] > 0:
            current_price = contract.get('last_price', 0)
            prev_price = prev['last_price']
            deltas['price_change'] = current_price - prev_price
            deltas['price_change_pct'] = (deltas['price_change'] / prev_price) * 100

        # UNDERLYING PRICE DELTA
        # (Redundant across all contracts for this symbol, but enables leverage calculation)
        if 'underlying_price' in prev and prev['underlying_price'] > 0:
            current_underlying = contract.get('underlying_price', 0)
            prev_underlying = prev['underlying_price']
            deltas['underlying_change'] = current_underlying - prev_underlying
            deltas['underlying_change_pct'] = (deltas['underlying_change'] / prev_underlying) * 100

        # OPTION LEVERAGE (Derived Metric)
        # Measures how much option moved relative to underlying
        # Values: 1.0 = normal delta behavior, 5.0 = strong, 20.0+ = extreme/unusual
        if deltas['price_change_pct'] is not None and deltas['underlying_change_pct'] is not None:
            if deltas['underlying_change_pct'] != 0:
                deltas['option_leverage'] = deltas['price_change_pct'] / deltas['underlying_change_pct']
            # else: underlying didn't move, leverage is undefined (stays None)

        return deltas

    def _get_market_regime(self):
        """Get current market regime with improved date filtering
        
        Returns:
            str: Market regime classification
        """
        try:
            # Get recent market regime (within last 7 days to avoid stale data)
            query = '''
                SELECT regime_classification, trade_date
                FROM market_daily_summary
                WHERE trade_date >= date('now', '-7 days')
                AND regime_classification IS NOT NULL
                ORDER BY trade_date DESC
                LIMIT 1
            '''
            result = self.storage.query_with_params(query, ())
            
            if result and len(result) > 0:
                regime = result[0]['regime_classification']
                logging.debug("Using market regime '{}' from date {}".format(
                    regime, result[0].get('trade_date', 'unknown')))
                return regime
            else:
                logging.warning("No recent market regime data found, using 'normal'")
                return 'normal'  # Default regime
                
        except Exception as e:
            logging.warning("Failed to get market regime: {}, using 'normal'".format(e))
            return 'normal'
    
    def _batch_update_contracts(self, updates_data, scan_timestamp):
        """Batch update contracts with calculated unified scores
        
        Args:
            updates_data: List of update dictionaries
            scan_timestamp: Scan timestamp to verify updates
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not updates_data:
            logging.warning("No updates to apply")
            return True
        
        # Build parameterized update query for unified algorithm fields and time-series deltas
        update_query = '''
            UPDATE flow_options_scans
            SET significance_score = ?,
                volume_surprise_factor = ?,
                alert_reason = ?,
                premium_value = ?,
                flow_percentage = ?,
                alert_threshold_met = ?,
                volume_change = ?,
                volume_change_pct = ?,
                underlying_change = ?,
                underlying_change_pct = ?,
                price_change = ?,
                price_change_pct = ?,
                option_leverage = ?,
                iv_change = ?,
                iv_change_pct = ?
            WHERE contract_hash = ? AND scan_timestamp = ?
        '''

        # Prepare batch update parameters
        update_params = []
        current_time = eastern_isoformat()

        for update in updates_data:
            params = (
                update['significance_score'],         # Unified score (0-10)
                update['volume_surprise_factor'],     # Volume surprise multiplier
                update['alert_reason'],              # Human-readable explanation
                update['premium_value'],             # Premium value in dollars
                update['flow_percentage'],           # Percentage of daily volume
                update.get('alert_threshold_met', False),  # Boolean: score >= threshold
                update.get('volume_change'),         # Time-series: volume delta
                update.get('volume_change_pct'),     # Time-series: volume % change
                update.get('underlying_change'),     # Time-series: stock price delta
                update.get('underlying_change_pct'), # Time-series: stock % change
                update.get('price_change'),          # Time-series: option price delta
                update.get('price_change_pct'),      # Time-series: option % change
                update.get('option_leverage'),       # Time-series: leverage ratio
                update.get('iv_change'),             # Time-series: IV delta
                update.get('iv_change_pct'),         # Time-series: IV % change
                update['contract_hash'],             # WHERE: composite PK part 1
                scan_timestamp                       # WHERE: composite PK part 2
            )
            update_params.append(params)
        
        # Execute batch update
        return self.storage.batch_update(update_query, update_params)
    
    def _should_alert_with_market_cap_filter(self, contract, unified_score):
        """Determine if contract should trigger alert considering market cap context
        
        Args:
            contract: Contract dictionary with symbol, volume, etc.
            unified_score: Calculated significance score
            
        Returns:
            bool: Whether this contract should trigger an alert
        """
        # Base threshold check
        if unified_score < self.ALERT_SCORE_THRESHOLD:
            return False
        
        # Filter out institutional noise - deep ITM options
        delta = contract.get('delta', 0)
        if delta is not None and abs(delta) > self.INSTITUTIONAL_DELTA_THRESHOLD:
            logging.debug("Institutional noise filtered - {} delta {:.2f} (threshold {:.2f})".format(
                contract.get('symbol'), abs(delta), self.INSTITUTIONAL_DELTA_THRESHOLD))
            return False
        
        symbol = contract.get('symbol', '')
        volume = contract.get('volume', 0)
        
        # Get market cap category from symbol metadata
        market_cap_category = self._get_market_cap_category(symbol, volume)
        
        # Market cap specific volume thresholds to reduce mega-cap noise
        if market_cap_category == 'mega_cap':
            # Mega caps need higher volume to be interesting
            min_volume_threshold = 15000
            min_score_boost = 0.5  # Require slightly higher scores
            
            if volume is None or volume < min_volume_threshold:
                logging.debug("Mega-cap {} volume {} below threshold {} - suppressing alert".format(
                    symbol, volume, min_volume_threshold))
                return False
                
            # Require higher scores for mega caps
            if unified_score < (self.ALERT_SCORE_THRESHOLD + min_score_boost):
                logging.debug("Mega-cap {} score {:.1f} below boosted threshold {:.1f} - suppressing alert".format(
                    symbol, unified_score, self.ALERT_SCORE_THRESHOLD + min_score_boost))
                return False
        
        elif market_cap_category == 'large_cap':
            # Large caps need moderate volume
            min_volume_threshold = 8000
            
            if volume is None or volume < min_volume_threshold:
                logging.debug("Large-cap {} volume {} below threshold {} - suppressing alert".format(
                    symbol, volume, min_volume_threshold))
                return False
        
        # Mid-cap and small-cap get normal thresholds (more sensitive)
        # This makes mid-cap 5K volume alerts more likely to fire than mega-cap 5K volume
        
        return True
           
    def _log_analysis_summary(self, total_time):
        """Log summary of unified analysis results with performance metrics"""
        stats = self.analysis_stats
        total_contracts = stats['contracts_processed']

        # Console stats block (kept lines)
        logging.info("Contracts updated: {:,}".format(stats['contracts_updated']))
        logging.info("Missing baselines: {}".format(stats['missing_baselines']))

        # Data quality monitoring summary (only show non-zero items)
        if stats['data_quality_warnings'] > 0:
            logging.warning("Data quality issues detected:")
            if stats['missing_price_data'] > 0:
                logging.warning("  Missing price data: {}".format(stats['missing_price_data']))
            if stats['bad_tick_data'] > 0:
                logging.warning("  Bad tick data (ask < bid): {}".format(stats['bad_tick_data']))

        # Premium/volume filters with passed counts
        premium_passed = total_contracts - stats['premium_filtered']
        volume_passed = total_contracts - stats['volume_filtered']
        logging.info("Premium filter: {} passed ({:,} filtered)".format(premium_passed, stats['premium_filtered']))
        logging.info("Volume filter: {} passed ({:,} filtered)".format(volume_passed, stats['volume_filtered']))

        logging.info("High conviction alerts (5.0+): {}".format(stats['high_conviction']))
        logging.info("Unified alerts (3.5+): {}".format(stats['unified_alerts']))
        logging.info("Total analysis time: {:.1f}s (Query: {:.1f}s + Scoring: {:.1f}s + DB Write: {:.1f}s)".format(
            total_time, self.last_query_elapsed, self.last_scoring_elapsed, self.last_db_write_elapsed))

        if stats['errors'] > 0:
            logging.warning("Errors encountered: {}".format(stats['errors']))

        total_significant = stats['high_conviction'] + stats['unified_alerts']
        if total_significant > 0:
            logging.info("Total significant flows detected: {}".format(total_significant))

        # Internal algorithm diagnostics (text log only)
        logging.debug("Enhanced statistics: early_day_fallbacks={}, running_total_used={}".format(
            stats['early_day_fallbacks'], stats['running_total_used']))
        logging.debug("Contracts processed: {}".format(stats['contracts_processed']))


def main():
    """Main function for standalone testing"""
    import argparse
    
    # Import FlowMonitorStorage for testing
    try:
        from strategies.flow_monitor.fm_storage import FlowMonitorStorage
        from strategies.flow_monitor.fm_config import FMConfig
    except ImportError as e:
        logging.error("Cannot import required modules: {}".format(e))
        return 1
    
    parser = argparse.ArgumentParser(description='Flow Monitor Unified Algorithm Analyzer')
    parser.add_argument('--test', action='store_true',
                       help='Test mode: analyze latest scan and show results')
    parser.add_argument('--scan-timestamp',
                       help='Specific scan timestamp to analyze (ISO format)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    parser.add_argument('--backfill', action='store_true',
                       help='Backfill mode: analyze all contracts without filtering')                       
    
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
        analyzer = FMAnalyzer(storage)
        
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
        
        # Run unified analysis (backfill or live mode)
        results = analyzer.analyze(scan_timestamp, backfill_mode=args.backfill)
               
        if args.test:
            # Show top results for testing
            logging.info("\nTesting mode - showing top significant contracts:")
            
            # Show from database (live mode)
            top_contracts = storage.get_top_contracts_by_score(scan_timestamp, limit=10)
            
            if top_contracts:
                logging.info("-" * 80)
                for i, contract in enumerate(top_contracts, 1):
                    smart_money = contract.get('flow_percentage', 0)  # Smart money score stored here
                    logging.info("{}. {} {} {} | Vol: {} | Score: {:.2f} | Smart: {:.2f}".format(
                        i, contract['symbol'], contract['strike'], contract['option_type'],
                        contract['volume'], contract.get('significance_score', 0),
                        smart_money
                    ))
            else:
                logging.info("No significant contracts found")
        
        # Return success/failure code
        if results['errors'] > 0:
            logging.warning("Analysis completed with {} errors".format(results['errors']))
            return 1
        else:
            mode_str = "Unified"
            logging.info("{} analysis completed successfully".format(mode_str))
            return 0
            
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130
    except Exception as e:
        logging.error("Analysis failed: {}".format(e))
        return 1


if __name__ == '__main__':
    exit(main())