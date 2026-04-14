#!/usr/bin/env python3
"""
OID Symbol Rollup (oid_symbol_rollup.py)
----------------------------------------
Aggregates contract-level OI data into symbol-level summaries.
Processes all KLMN 800 symbols daily and generates display-ready metrics.

Features:
- Batch processing for memory efficiency
- Put/call ratio analysis with display text generation
- Top concentration strike identification for calls and puts
- Activity count tracking (interesting, building, unwinding)
- Edge case handling for symbols with no/limited options data
- Comprehensive statistics tracking and progress logging

Author: Ben (with assistance from Claude)
Date: 2025-08-17
Version: 1.0
"""

import logging
import time
import math
from collections import defaultdict
from datetime import datetime
from tools.timezone_utils import now_eastern, eastern_isoformat
from tools.decimal_formatter import clean_database_row, format_ratio, format_percentage, format_price
from tools.log_utils import beautiful_log
from core.symbols_klmn800 import get_specialty_list
from strategies.option_pipeline.op_config import OIDConfig


class OIDSymbolRollup:
    """Aggregates contract-level OI data into symbol-level summaries"""
    
    def __init__(self, storage):
        """Initialize rollup processor with OID storage instance
        
        Args:
            storage: OIDStorage instance for database operations
        """
        self.storage = storage
        self.stats = {
            'total_symbols': 0,
            'symbols_processed': 0,
            'symbols_with_data': 0,
            'symbols_skipped_no_data': 0,
            'summaries_created': 0,
            'processing_time_per_batch': [],
            'total_processing_duration': 0,
            'errors_encountered': 0,
            'failed_symbols': []
        }
        
        # Get batch size from configuration
        try:
            config = OIDConfig()
            collection_params = config.get_collection_params()
            self.batch_size = collection_params.get('rollup_batch_size', 100)
        except Exception as e:
            logging.warning("OP Rollup: Could not load config, using default batch size: {}".format(e))
            self.batch_size = 100
        
        logging.debug("OP Rollup: Initialized for symbol aggregation with batch size {}".format(self.batch_size))
    
    def process_symbols(self, trade_date, symbol_filter=None):
        """Process all symbols and generate aggregated summaries
        
        Args:
            trade_date: Date string (YYYY-MM-DD) to process
            symbol_filter: Optional single symbol or list of symbols to process (for testing)
            
        Returns:
            dict: Processing statistics and results
        """
        start_time = time.time()

        try:
            # Get symbols to process
            if symbol_filter:
                if isinstance(symbol_filter, str):
                    all_symbols = [symbol_filter]
                    logging.debug("   Processing single symbol: {}".format(symbol_filter))
                else:
                    all_symbols = list(symbol_filter)
                    logging.debug("   Processing {} symbols (filtered mode)".format(len(all_symbols)))
            else:
                all_symbols = get_specialty_list('klmn_800')
                logging.debug("   Processing {} symbols (KLMN 800 universe)".format(len(all_symbols)))

            self.stats['total_symbols'] = len(all_symbols)

            logging.debug("   Batch size: {} symbols".format(self.batch_size))
            
            # Process symbols in batches
            symbol_summaries = []
            batch_start_idx = 0
            
            while batch_start_idx < len(all_symbols):
                batch_end_idx = min(batch_start_idx + self.batch_size, len(all_symbols))
                batch_symbols = all_symbols[batch_start_idx:batch_end_idx]
                
                batch_start_time = time.time()
                batch_summaries = self._process_symbol_batch(batch_symbols, trade_date)
                batch_time = time.time() - batch_start_time
                
                self.stats['processing_time_per_batch'].append(batch_time)
                symbol_summaries.extend(batch_summaries)
                
                # Log progress every 100 symbols
                if (batch_end_idx % 100) == 0 or batch_end_idx == len(all_symbols):
                    self._log_batch_progress(batch_end_idx, len(all_symbols), batch_time)
                
                batch_start_idx = batch_end_idx
            
            # Bulk insert all summaries
            if symbol_summaries:
                records_inserted = self.storage.insert_symbol_summaries(symbol_summaries)
                if records_inserted > 0:
                    self.stats['summaries_created'] = records_inserted
                else:
                    logging.warning("OP Rollup: No records were inserted (likely duplicates)")
            else:
                logging.warning("OP Rollup: No symbol summaries were created")
            
            # Calculate final statistics
            self.stats['total_processing_duration'] = time.time() - start_time
            self._log_completion_stats(trade_date, self.stats['total_processing_duration'])
            
            return self.stats
            
        except Exception as e:
            logging.error("OP Rollup: Critical error in symbol processing: {}".format(e))
            self.stats['errors_encountered'] += 1
            raise
    
    def _process_symbol_batch(self, symbols, trade_date):
        """Process a batch of symbols and return their summaries
        
        Args:
            symbols: List of symbol strings to process
            trade_date: Date string for processing
            
        Returns:
            list: List of summary dictionaries ready for database insertion
        """
        batch_summaries = []
        
        for symbol in symbols:
            try:
                summary = self._process_single_symbol(symbol, trade_date)
                if summary:
                    batch_summaries.append(summary)
                    self.stats['symbols_with_data'] += 1
                else:
                    self.stats['symbols_skipped_no_data'] += 1
                
                self.stats['symbols_processed'] += 1
                
            except Exception as e:
                logging.error("OP Rollup: Error processing symbol {}: {}".format(symbol, e))
                self.stats['errors_encountered'] += 1
                self.stats['failed_symbols'].append(symbol)
                self.stats['symbols_processed'] += 1
        
        return batch_summaries
    
    def _process_single_symbol(self, symbol, trade_date):
        """Process a single symbol and generate its summary
        
        Args:
            symbol: Symbol string to process
            trade_date: Date string for processing
            
        Returns:
            dict: Summary dictionary or None if no data
        """
        start_time = time.time()
        
        # Query all contracts for this symbol and date
        contracts = self._get_symbol_contracts(symbol, trade_date)
        
        if not contracts:
            # Skip gracefully - no options data for this symbol
            return None
        
        # Calculate core OI metrics
        oi_metrics = self._calculate_oi_metrics(contracts)
        
        # Find top concentration strikes
        concentration_metrics = self._calculate_concentration_metrics(contracts, oi_metrics['total_call_oi'], oi_metrics['total_put_oi'])
        
        # Count activity patterns
        activity_metrics = self._calculate_activity_metrics(contracts)

        # Calculate time horizon metrics
        time_horizon_metrics = self._calculate_time_horizon_metrics(contracts, trade_date)

        # Calculate max pain for nearest expiration
        max_pain = self._calculate_max_pain(contracts, trade_date)

        # NEW CALCULATIONS - Get close price for moneyness calculations
        close_price = None
        if contracts:
            # Try to get underlying_price from any contract
            for contract in contracts:
                close_price = contract.get('underlying_price')
                if close_price:
                    break

        # Calculate new summary metrics
        volume_metrics = self._calculate_volume_metrics(contracts)
        iv_metrics = self._calculate_iv_metrics(contracts, symbol, trade_date)
        iv_by_dte_metrics = self._calculate_iv_by_dte(contracts, symbol, trade_date)
        greeks_metrics = self._calculate_greeks_exposure(contracts)
        moneyness_metrics = self._calculate_moneyness_distribution(contracts, close_price) if close_price else {}
        quality_metrics = self._calculate_quality_metrics(contracts)

        # Generate display text
        display_text = self._generate_display_text(oi_metrics['put_call_ratio'])

        # Combine all metrics into summary with explicit type conversion
        summary = {
            'symbol': symbol,
            'trade_date': trade_date,
            'total_open_interest': int(oi_metrics['total_open_interest']),
            'total_call_oi': int(oi_metrics['total_call_oi']),
            'total_put_oi': int(oi_metrics['total_put_oi']),
            'put_call_ratio': oi_metrics['put_call_ratio'],  # Can be None
            'oi_balance_text': display_text
        }
        
        # Add concentration metrics with explicit NULL handling for integers
        summary.update({
            'top_call_strike': concentration_metrics['top_call_strike'],  # Can be None
            'top_call_expiration': concentration_metrics['top_call_expiration'],  # Can be None
            'top_call_oi': self._safe_int(concentration_metrics['top_call_oi']),
            'top_call_pct_of_total': concentration_metrics['top_call_pct_of_total'],  # New column name
            'top_call_display': concentration_metrics['top_call_display'],  # Can be None
            'top_put_strike': concentration_metrics['top_put_strike'],  # Can be None
            'top_put_expiration': concentration_metrics['top_put_expiration'],  # Can be None
            'top_put_oi': self._safe_int(concentration_metrics['top_put_oi']),
            'top_put_pct_of_total': concentration_metrics['top_put_pct_of_total'],  # New column name
            'top_put_display': concentration_metrics['top_put_display']  # Can be None
        })

        # Add activity metrics with safe integer conversion
        summary.update({
            'building_contracts_count': self._safe_int(activity_metrics['building_contracts_count']),
            'unwinding_contracts_count': self._safe_int(activity_metrics['unwinding_contracts_count'])
        })

        # Add time horizon metrics
        summary.update(time_horizon_metrics)

        # Add max pain metric
        summary['max_pain_by_friday'] = max_pain

        # Add new metrics - stock data and volume
        summary['close_price'] = close_price
        summary.update(volume_metrics)

        # Add IV metrics
        summary.update(iv_metrics)
        summary.update(iv_by_dte_metrics)

        # Add Greeks exposure metrics
        summary.update(greeks_metrics)

        # Add realized volatility metrics (for z-score dip detection)
        rv_metrics = self._calculate_realized_volatility(symbol, trade_date)
        summary.update(rv_metrics)

        # Add moneyness distribution metrics
        summary.update(moneyness_metrics)

        # Add quality metrics
        summary.update(quality_metrics)

        # Add processing metadata
        summary.update({
            'analysis_timestamp': eastern_isoformat()
        })

        # Apply decimal formatting to all numeric values
        summary = clean_database_row(summary)

        return summary    
        
    def _safe_int(self, value):
        """Safely convert value to integer or return None for database NULL
        
        Args:
            value: Value to convert (can be None, string, or number)
            
        Returns:
            int or None: Integer value or None for NULL database insertion
        """
        if value is None:
            return None
        if value == '':
            return None
        try:
            # Handle string representations of floats/integers
            if isinstance(value, str):
                # Remove any whitespace and check for empty
                value = value.strip()
                if not value:
                    return None
            return int(float(value))
        except (ValueError, TypeError):
            logging.warning("OP Rollup: Could not convert '{}' to integer, returning None".format(value))
            return None

    def _ensure_int(self, value):
        """Ensure value is an integer, converting if needed
        
        Args:
            value: Value to convert to integer
            
        Returns:
            int: Integer value (0 if conversion fails)
        """
        if value is None:
            return 0
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0    
            
    def _get_symbol_contracts(self, symbol, trade_date):
        """Query all contracts for a symbol on a given date

        Args:
            symbol: Symbol to query
            trade_date: Date string to query

        Returns:
            list: List of contract dictionaries
        """
        try:
            # Select directly from option_contracts (bid/ask spread calculation removed - legacy feature)
            query = """
                SELECT
                    contract_hash, symbol, strike, expiration_date, option_type,
                    open_interest, oi_change_1d, oi_change_pct_1d, oi_momentum_5d,
                    build_pattern, building_unwinding,
                    underlying_price, delta, gamma, theta, vega, iv, volume
                FROM option_contracts
                WHERE symbol = ?
                AND trade_date = ?
                ORDER BY option_type, expiration_date, strike
            """

            results = self.storage.query_db(query, (symbol, trade_date))
            return results if results else []

        except Exception as e:
            logging.error("OP Rollup: Error querying contracts for {}: {}".format(symbol, e))
            return []
    
    def _calculate_oi_metrics(self, contracts):
        """Calculate core open interest metrics
        
        Args:
            contracts: List of contract dictionaries
            
        Returns:
            dict: Core OI metrics (total_oi, call_oi, put_oi, ratio)
        """
        total_oi = 0
        call_oi = 0
        put_oi = 0
        
        for contract in contracts:
            oi = contract.get('open_interest', 0) or 0
            total_oi += oi
            
            if contract.get('option_type') == 'CALL':
                call_oi += oi
            elif contract.get('option_type') == 'PUT':
                put_oi += oi
        
        # Calculate put/call ratio (industry standard: puts/calls)
        put_call_ratio = None
        if call_oi > 0:
            put_call_ratio = format_ratio(put_oi / call_oi)
        
        return {
            'total_open_interest': total_oi,
            'total_call_oi': call_oi,
            'total_put_oi': put_oi,
            'put_call_ratio': put_call_ratio
        }

    def _calculate_time_horizon_metrics(self, contracts, trade_date):
        """Calculate OI distribution across time horizons

        Args:
            contracts: List of contract dictionaries
            trade_date: Trade date string for DTE calculation

        Returns:
            dict: Time horizon metrics with all 24 columns
        """
        # Initialize buckets for time horizons
        buckets = {
            '0_7': {'total': 0, 'call': 0, 'put': 0},
            '8_21': {'total': 0, 'call': 0, 'put': 0},
            '22_35': {'total': 0, 'call': 0, 'put': 0},
            '36_60': {'total': 0, 'call': 0, 'put': 0}
        }

        total_oi = 0
        total_call_oi = 0
        total_put_oi = 0

        try:
            # Process each contract
            for contract in contracts:
                # Calculate days to expiration
                days_to_exp = self._calculate_dte(contract.get('expiration_date', ''), trade_date)

                # Determine time bucket
                if days_to_exp <= 7:
                    bucket = '0_7'
                elif days_to_exp <= 21:
                    bucket = '8_21'
                elif days_to_exp <= 35:
                    bucket = '22_35'
                elif days_to_exp <= 60:
                    bucket = '36_60'
                else:
                    continue  # Skip contracts > 60 days since we don't collect them

                # Get open interest
                oi = contract.get('open_interest', 0) or 0
                option_type = contract.get('option_type', '').upper()

                # Add to appropriate bucket
                buckets[bucket]['total'] += oi
                total_oi += oi

                if option_type == 'CALL':
                    buckets[bucket]['call'] += oi
                    total_call_oi += oi
                elif option_type == 'PUT':
                    buckets[bucket]['put'] += oi
                    total_put_oi += oi

            # Calculate results with percentages
            results = {}

            # Combined metrics
            for bucket in ['0_7', '8_21', '22_35', '36_60']:
                bucket_name = '{}_days'.format(bucket)
                results['oi_{}'.format(bucket_name)] = buckets[bucket]['total']
                results['oi_{}_percent'.format(bucket_name)] = format_percentage(
                    (buckets[bucket]['total'] / total_oi * 100) if total_oi > 0 else 0.0
                )

                # Call metrics
                results['call_oi_{}'.format(bucket_name)] = buckets[bucket]['call']
                results['call_oi_{}_percent'.format(bucket_name)] = format_percentage(
                    (buckets[bucket]['call'] / total_call_oi * 100) if total_call_oi > 0 else 0.0
                )

                # Put metrics
                results['put_oi_{}'.format(bucket_name)] = buckets[bucket]['put']
                results['put_oi_{}_percent'.format(bucket_name)] = format_percentage(
                    (buckets[bucket]['put'] / total_put_oi * 100) if total_put_oi > 0 else 0.0
                )

            return results

        except Exception as e:
            logging.error("OP Rollup: Error calculating time horizon metrics: {}".format(e))
            # Return all zeros on error with proper formatting
            return {
                'oi_0_7_days': 0, 'oi_8_21_days': 0, 'oi_22_35_days': 0, 'oi_36_60_days': 0,
                'oi_0_7_days_percent': format_percentage(0.0), 'oi_8_21_days_percent': format_percentage(0.0), 'oi_22_35_days_percent': format_percentage(0.0), 'oi_36_60_days_percent': format_percentage(0.0),
                'call_oi_0_7_days': 0, 'call_oi_8_21_days': 0, 'call_oi_22_35_days': 0, 'call_oi_36_60_days': 0,
                'call_oi_0_7_days_percent': format_percentage(0.0), 'call_oi_8_21_days_percent': format_percentage(0.0), 'call_oi_22_35_days_percent': format_percentage(0.0), 'call_oi_36_60_days_percent': format_percentage(0.0),
                'put_oi_0_7_days': 0, 'put_oi_8_21_days': 0, 'put_oi_22_35_days': 0, 'put_oi_36_60_days': 0,
                'put_oi_0_7_days_percent': format_percentage(0.0), 'put_oi_8_21_days_percent': format_percentage(0.0), 'put_oi_22_35_days_percent': format_percentage(0.0), 'put_oi_36_60_days_percent': format_percentage(0.0)
            }

    def _calculate_concentration_metrics(self, contracts, total_call_oi, total_put_oi):
        """Calculate concentration metrics for top call and put strikes

        Args:
            contracts: List of contract dictionaries
            total_call_oi: Total call open interest for percentage calculations
            total_put_oi: Total put open interest for percentage calculations

        Returns:
            dict: Concentration metrics for database storage
        """
        metrics = {
            'top_call_strike': None,
            'top_call_expiration': None,
            'top_call_oi': None,
            'top_call_pct_of_total': None,
            'top_call_display': None,
            'top_put_strike': None,
            'top_put_expiration': None,
            'top_put_oi': None,
            'top_put_pct_of_total': None,
            'top_put_display': None
        }

        # Debug: Check input contracts
        logging.debug("OP Rollup: Processing {} total contracts".format(len(contracts)))

        # Separate contracts by type (no is_interesting filter - just top 5 by OI)
        all_calls = []
        all_puts = []

        for contract in contracts:
            if contract.get('option_type') == 'CALL':
                all_calls.append(contract)
            elif contract.get('option_type') == 'PUT':
                all_puts.append(contract)

        # Debug: Check separation and uniqueness
        call_hashes_all = [c.get('contract_hash') for c in all_calls]
        unique_call_hashes = set(call_hashes_all)
        logging.debug("OP Rollup: Found {} calls ({} unique), {} puts".format(
            len(all_calls), len(unique_call_hashes), len(all_puts)))

        if len(unique_call_hashes) < len(all_calls):
            logging.warning("OP Rollup: DUPLICATE REFERENCES in all_calls before sorting! {} total, {} unique".format(
                len(all_calls), len(unique_call_hashes)))
            # Log first 10 hashes to see pattern
            logging.debug("First 10 call hashes: {}".format(call_hashes_all[:10]))

        # Find top 5 calls and format display
        if all_calls:
            # Get top 5 by OI
            top_5_calls = sorted(all_calls,
                                key=lambda x: x.get('open_interest', 0),
                                reverse=True)[:5]

            # Debug: Check top 5 uniqueness
            call_hashes = [c.get('contract_hash') for c in top_5_calls]
            unique_hashes = set(call_hashes)
            logging.debug("OP Rollup: Top 5 calls - {} contracts, {} unique hashes".format(
                len(top_5_calls), len(unique_hashes)))
            if len(unique_hashes) < len(top_5_calls):
                logging.warning("OP Rollup: DUPLICATE CONTRACTS DETECTED in top_5_calls! Hashes: {}".format(call_hashes))

            # Store top 1 metrics for backward compatibility
            top_call = top_5_calls[0]
            call_oi = top_call.get('open_interest', 0)
            call_pct = format_percentage((call_oi / total_call_oi * 100) if total_call_oi > 0 else 0.0)

            metrics.update({
                'top_call_strike': top_call.get('strike'),
                'top_call_expiration': top_call.get('expiration_date'),
                'top_call_oi': call_oi,
                'top_call_pct_of_total': call_pct,
                'top_call_display': self._format_top_5_strikes(top_5_calls)
            })
            logging.debug("OP Rollup: Top {} calls formatted for display".format(len(top_5_calls)))
        else:
            logging.debug("OP Rollup: No calls found")

        # Find top 5 puts and format display
        if all_puts:
            # Get top 5 by OI
            top_5_puts = sorted(all_puts,
                               key=lambda x: x.get('open_interest', 0),
                               reverse=True)[:5]

            # Debug: Check top 5 uniqueness
            put_hashes = [p.get('contract_hash') for p in top_5_puts]
            unique_hashes = set(put_hashes)
            logging.debug("OP Rollup: Top 5 puts - {} contracts, {} unique hashes".format(
                len(top_5_puts), len(unique_hashes)))
            if len(unique_hashes) < len(top_5_puts):
                logging.warning("OP Rollup: DUPLICATE CONTRACTS DETECTED in top_5_puts! Hashes: {}".format(put_hashes))

            # Store top 1 metrics for backward compatibility
            top_put = top_5_puts[0]
            put_oi = top_put.get('open_interest', 0)
            put_pct = format_percentage((put_oi / total_put_oi * 100) if total_put_oi > 0 else 0.0)

            metrics.update({
                'top_put_strike': top_put.get('strike'),
                'top_put_expiration': top_put.get('expiration_date'),
                'top_put_oi': put_oi,
                'top_put_pct_of_total': put_pct,
                'top_put_display': self._format_top_5_strikes(top_5_puts)
            })
            logging.debug("OP Rollup: Top {} puts formatted for display".format(len(top_5_puts)))
        else:
            logging.debug("OP Rollup: No puts found")

        logging.debug("OP Rollup: Concentration analysis complete")

        return metrics

    def _format_top_5_strikes(self, top_contracts):
        """Format top 5 strikes for Morning Views display

        Format: "$10 (10/3) OI 54,322 | $11 (10/3) OI 20,255 | ..."
        Sorted by expiration date ASC, then strike ASC for grouped display

        Args:
            top_contracts: List of up to 5 contract dicts (already sorted by OI desc)

        Returns:
            str: Formatted display string
        """
        if not top_contracts:
            return None

        # Sort by expiration date, then strike (for grouped display)
        sorted_strikes = sorted(top_contracts,
                               key=lambda x: (x.get('expiration_date', ''), x.get('strike', 0)))

        # Format: "$10 (10/3) OI 54,322"
        display_parts = []
        for contract in sorted_strikes:
            strike = contract.get('strike', 0)
            exp_date = contract.get('expiration_date', '')
            oi = contract.get('open_interest', 0)

            # Extract M/D from YYYY-MM-DD
            exp_display = exp_date[5:] if len(exp_date) >= 10 else exp_date  # "10-03" format
            exp_display = exp_display.replace('-', '/')  # "10/03" format

            display_parts.append("${} ({}) OI {:,}".format(strike, exp_display, oi))

        return " | ".join(display_parts)
    
    def _format_concentration_display(self, contract, percentage, type_text):
        """Format concentration display string
        
        Args:
            contract: Contract dictionary with strike, type, expiration, OI
            percentage: Pre-calculated percentage of total call/put OI
            type_text: 'calls' or 'puts' for display
            
        Returns:
            str: Formatted display string like "$175 Call 9/19 (15,847 contracts, 18.2% of calls)"
        """
        try:
            strike = contract.get('strike')
            option_type = contract.get('option_type', '').title()
            expiration = contract.get('expiration_date', '')
            oi = contract.get('open_interest', 0)
            
            # Format expiration as M/D
            if expiration and len(expiration) >= 10:  # YYYY-MM-DD format
                try:
                    exp_parts = expiration.split('-')
                    if len(exp_parts) >= 3:
                        month = int(exp_parts[1])
                        day = int(exp_parts[2])
                        exp_display = "{}/{}".format(month, day)
                    else:
                        exp_display = expiration
                except:
                    exp_display = expiration
            else:
                exp_display = expiration
            
            return "${} {} {} ({:,} contracts, {:.1f}% of {})".format(
                strike, option_type, exp_display, oi, percentage, type_text
            )
            
        except Exception as e:
            logging.error("OP Rollup: Error formatting concentration display: {}".format(e))
            return "Display format error"
    
    def _calculate_activity_metrics(self, contracts):
        """Calculate activity count metrics

        Args:
            contracts: List of contract dictionaries

        Returns:
            dict: Activity metrics (building, unwinding counts)
        """
        building_count = 0
        unwinding_count = 0

        for contract in contracts:
            # Count building/unwinding based on 5-day momentum
            momentum_5d = contract.get('oi_momentum_5d')
            if momentum_5d is not None:
                if momentum_5d > 0:
                    building_count += 1
                elif momentum_5d < 0:
                    unwinding_count += 1

        return {
            'building_contracts_count': building_count,
            'unwinding_contracts_count': unwinding_count
        }
    
    def _calculate_max_pain(self, contracts, trade_date):
        """Calculate max pain strike for the nearest expiration date

        Args:
            contracts: List of contract dictionaries for the symbol
            trade_date: Current trade date string (YYYY-MM-DD)

        Returns:
            float or None: Max pain strike price, or None if no valid options
        """
        try:
            # Find the nearest expiration date (typically Friday or Thursday for holidays)
            expirations = set()
            for contract in contracts:
                exp_date = contract.get('expiration_date')
                if exp_date and exp_date >= trade_date:
                    expirations.add(exp_date)

            if not expirations:
                logging.debug("OP Rollup: No future expirations found for max pain calculation")
                return None

            # Use the nearest expiration (usually this week's Friday)
            nearest_expiry = min(expirations)

            # Filter contracts for the nearest expiration
            expiry_contracts = []
            for contract in contracts:
                if contract.get('expiration_date') == nearest_expiry:
                    oi = contract.get('open_interest', 0)
                    if oi > 0:  # Only include contracts with open interest
                        expiry_contracts.append(contract)

            if not expiry_contracts:
                logging.debug("OP Rollup: No contracts with OI found for expiration {}".format(nearest_expiry))
                return None

            # Get unique strikes to test as potential closing prices
            strikes = sorted(set(float(c['strike']) for c in expiry_contracts if c.get('strike') is not None))

            if not strikes:
                logging.debug("OP Rollup: No valid strikes found for max pain calculation")
                return None

            min_pain = float('inf')
            max_pain_strike = None

            # Test each strike as potential closing price
            for test_strike in strikes:
                total_value = 0

                # Calculate intrinsic value of all options at this test price
                for contract in expiry_contracts:
                    strike = float(contract['strike'])
                    oi = contract.get('open_interest', 0)
                    option_type = contract.get('option_type', '').upper()

                    if option_type == 'CALL':
                        # Call intrinsic value = max(0, test_price - strike)
                        intrinsic = max(0, test_strike - strike) * oi
                    elif option_type == 'PUT':
                        # Put intrinsic value = max(0, strike - test_price)
                        intrinsic = max(0, strike - test_strike) * oi
                    else:
                        continue  # Skip unknown option types

                    total_value += intrinsic

                # Find strike where total intrinsic value is minimized
                if total_value < min_pain:
                    min_pain = total_value
                    max_pain_strike = test_strike

            logging.debug("OP Rollup: Max pain calculated - ${} (total value: ${:,.0f}) for expiration {}".format(
                max_pain_strike, min_pain, nearest_expiry))

            return format_price(max_pain_strike)

        except Exception as e:
            logging.error("OP Rollup: Error calculating max pain: {}".format(e))
            return None

    def _generate_display_text(self, put_call_ratio):
        """Generate display text based on put/call ratio thresholds

        Args:
            put_call_ratio: Put/call ratio (puts/calls) or None

        Returns:
            str: Display text describing the bias
        """
        if put_call_ratio is None:
            return "No Call Data"

        # Put/call ratio thresholds (puts/calls)
        if put_call_ratio < 0.5:
            return "Clear Call Bias"
        elif put_call_ratio < 0.77:
            return "Heavy Call"
        elif put_call_ratio <= 1.3:
            return "Balanced"
        elif put_call_ratio <= 1.9:
            return "Leans Put"
        elif put_call_ratio <= 2.5:
            return "Heavy Put"
        else:
            return "Clear Put Bias"

    def _calculate_moneyness_category(self, strike, underlying_price, option_type):
        """Calculate detailed moneyness category using ±20% boundaries

        Args:
            strike: Strike price
            underlying_price: Current stock price
            option_type: 'CALL' or 'PUT'

        Returns:
            str: 'DEEP_ITM', 'ITM', 'ATM', 'OTM', 'DEEP_OTM', or 'UNK'
        """
        if not strike or not underlying_price or underlying_price == 0:
            return 'UNK'

        option_type_upper = option_type.upper()

        if option_type_upper == 'CALL':
            # For calls: lower strike = ITM, higher strike = OTM
            if strike < underlying_price * 0.80:
                return 'DEEP_ITM'
            elif strike < underlying_price * 0.99:
                return 'ITM'
            elif strike <= underlying_price * 1.01:
                return 'ATM'
            elif strike <= underlying_price * 1.20:
                return 'OTM'
            else:
                return 'DEEP_OTM'
        else:  # PUT
            # For puts: higher strike = ITM, lower strike = OTM
            if strike > underlying_price * 1.20:
                return 'DEEP_ITM'
            elif strike > underlying_price * 1.01:
                return 'ITM'
            elif strike >= underlying_price * 0.99:
                return 'ATM'
            elif strike >= underlying_price * 0.80:
                return 'OTM'
            else:
                return 'DEEP_OTM'

    def _calculate_volume_metrics(self, contracts):
        """Calculate volume-based metrics from contracts

        Args:
            contracts: List of contract dictionaries

        Returns:
            dict: Volume metrics (option_volume, call_volume, put_volume, volume_put_call_ratio)
        """
        option_volume = 0
        call_volume = 0
        put_volume = 0

        for contract in contracts:
            volume = contract.get('volume', 0) or 0
            option_volume += volume

            if contract.get('option_type', '').upper() == 'CALL':
                call_volume += volume
            else:
                put_volume += volume

        # Calculate volume-based put/call ratio
        volume_put_call_ratio = None
        if call_volume > 0:
            volume_put_call_ratio = format_ratio(put_volume / call_volume)

        return {
            'option_volume': option_volume,
            'call_volume': call_volume,
            'put_volume': put_volume,
            'volume_put_call_ratio': volume_put_call_ratio
        }

    def _calculate_iv_percentile_30d(self, symbol, trade_date, current_avg_iv):
        """Calculate 30-day IV percentile for symbol

        Args:
            symbol: Stock symbol
            trade_date: Current trade date
            current_avg_iv: Today's average IV across all contracts

        Returns:
            float: Percentile (0-100) or None if insufficient history
        """
        if current_avg_iv is None:
            return None

        # Get historical symbol-level average IVs for past 30 days
        query = """
            SELECT trade_date, AVG(iv) as avg_iv
            FROM option_contracts
            WHERE symbol = ?
            AND trade_date < ?
            AND trade_date >= date(?, '-30 days')
            AND iv IS NOT NULL
            GROUP BY trade_date
            ORDER BY trade_date DESC
        """

        historical_ivs = self.storage.query_db(query, (symbol, trade_date, trade_date))

        if not historical_ivs or len(historical_ivs) < 20:
            # Need at least 20 days of history for meaningful percentile
            return None

        # Extract IV values
        iv_values = [row['avg_iv'] for row in historical_ivs]

        # Calculate percentile rank
        below_count = sum(1 for iv in iv_values if iv < current_avg_iv)
        percentile = (below_count / len(iv_values)) * 100

        return format_percentage(percentile)

    def _calculate_iv_by_dte(self, contracts, symbol, trade_date):
        """Calculate IV metrics bucketed by DTE ranges

        Args:
            contracts: List of contract dictionaries
            symbol: Stock symbol (for percentile calculation)
            trade_date: Current trade date (for percentile calculation)

        Returns:
            dict: IV metrics by DTE bucket with percentiles
        """
        from tools.decimal_formatter import format_greek

        # Initialize buckets
        # Front month: 0-21 DTE, 30dte: 22-35, 45dte: 36-50, 60dte: 51-70
        buckets = {
            'front_month': {'ivs': [], 'min_dte': 0, 'max_dte': 21},
            '30dte': {'ivs': [], 'min_dte': 22, 'max_dte': 35},
            '45dte': {'ivs': [], 'min_dte': 36, 'max_dte': 50},
            '60dte': {'ivs': [], 'min_dte': 51, 'max_dte': 70}
        }

        # Collect IVs by bucket
        for contract in contracts:
            iv = contract.get('iv')
            if iv is None or iv == 0:
                continue

            dte = self._calculate_dte(contract.get('expiration_date', ''), trade_date)

            # Assign to bucket
            for bucket_name, bucket_data in buckets.items():
                if bucket_data['min_dte'] <= dte <= bucket_data['max_dte']:
                    bucket_data['ivs'].append(iv)
                    break

        # Calculate averages
        results = {}

        for bucket_name, bucket_data in buckets.items():
            ivs = bucket_data['ivs']

            # Calculate average IV for this bucket
            avg_iv = format_greek(sum(ivs) / len(ivs)) if ivs else None
            results[f'iv_{bucket_name}'] = avg_iv

        return results

    def _calculate_realized_volatility(self, symbol, trade_date):
        """Calculate realized volatility metrics from historical prices

        Used for volatility-normalized dip detection in Flow Monitor watchlist.

        Args:
            symbol: Stock symbol
            trade_date: Trade date (YYYY-MM-DD)

        Returns:
            dict: {'rv_5d': float, 'rv_10d': float} or None values if insufficient data

        Database Reads:
            - historical_prices (close_price time series)
        """
        try:
            from tools.realized_volatility import calculate_rv_metrics
            return calculate_rv_metrics(
                self.storage,
                symbol,
                trade_date,
                lookback_periods=[5, 10]
            )
        except Exception as e:
            logging.warning("OP Rollup: RV calculation failed for {}: {}".format(symbol, e))
            return {'rv_5d': None, 'rv_10d': None}

    def _calculate_iv_metrics(self, contracts, symbol=None, trade_date=None):
        """Calculate implied volatility summary metrics

        Args:
            contracts: List of contract dictionaries
            symbol: Stock symbol (optional, for percentile calculation)
            trade_date: Trade date (optional, for percentile calculation)

        Returns:
            dict: IV metrics (call_iv_avg, put_iv_avg, iv_skew, weighted IVs, percentile)
        """
        from tools.decimal_formatter import format_greek

        call_ivs = []
        put_ivs = []
        call_iv_oi_products = []
        put_iv_oi_products = []
        call_total_oi = 0
        put_total_oi = 0

        for contract in contracts:
            iv = contract.get('iv')
            if iv is None or iv == 0:
                continue

            oi = contract.get('open_interest', 0) or 0
            option_type = contract.get('option_type', '').upper()

            if option_type == 'CALL':
                call_ivs.append(iv)
                call_iv_oi_products.append(iv * oi)
                call_total_oi += oi
            else:
                put_ivs.append(iv)
                put_iv_oi_products.append(iv * oi)
                put_total_oi += oi

        # Calculate averages
        call_iv_avg = format_greek(sum(call_ivs) / len(call_ivs)) if call_ivs else None
        put_iv_avg = format_greek(sum(put_ivs) / len(put_ivs)) if put_ivs else None

        # Calculate IV skew (put IV - call IV)
        iv_skew = None
        if call_iv_avg is not None and put_iv_avg is not None:
            iv_skew = format_greek(put_iv_avg - call_iv_avg)

        # Calculate OI-weighted IVs
        call_iv_weighted = None
        if call_total_oi > 0:
            call_iv_weighted = format_greek(sum(call_iv_oi_products) / call_total_oi)

        put_iv_weighted = None
        if put_total_oi > 0:
            put_iv_weighted = format_greek(sum(put_iv_oi_products) / put_total_oi)

        # Calculate symbol-level average IV for percentile calculation
        all_ivs = call_ivs + put_ivs
        symbol_avg_iv = sum(all_ivs) / len(all_ivs) if all_ivs else None

        # Calculate 30-day percentile
        symbol_iv_percentile_30d = None
        if symbol is not None and trade_date is not None and symbol_avg_iv is not None:
            symbol_iv_percentile_30d = self._calculate_iv_percentile_30d(
                symbol, trade_date, symbol_avg_iv
            )

        return {
            'call_iv_avg': call_iv_avg,
            'put_iv_avg': put_iv_avg,
            'iv_skew': iv_skew,
            'call_iv_weighted': call_iv_weighted,
            'put_iv_weighted': put_iv_weighted,
            'symbol_iv_percentile_30d': symbol_iv_percentile_30d
        }

    def _calculate_greeks_exposure(self, contracts):
        """Calculate Greeks-based exposure metrics

        Args:
            contracts: List of contract dictionaries

        Returns:
            dict: Greeks exposure metrics (delta, gamma, theta, vega exposures)
        """
        from tools.decimal_formatter import format_greek

        # Delta exposure tracking
        total_delta_exp = 0.0
        call_delta_exp = 0.0
        put_delta_exp = 0.0

        # Gamma exposure tracking
        total_gamma_exp = 0.0
        gamma_by_strike = {}  # track gamma exposure per strike

        # Theta exposure tracking
        total_theta_exp = 0.0

        # Vega exposure tracking
        total_vega_exp = 0.0
        call_vega_exp = 0.0
        put_vega_exp = 0.0

        for contract in contracts:
            oi = contract.get('open_interest', 0) or 0
            if oi == 0:
                continue

            option_type = contract.get('option_type', '').upper()

            # Delta exposure (delta × OI × 100 shares per contract)
            delta = contract.get('delta', 0) or 0
            delta_exposure = delta * oi * 100
            total_delta_exp += delta_exposure
            if option_type == 'CALL':
                call_delta_exp += delta_exposure
            else:
                put_delta_exp += delta_exposure

            # Gamma exposure (gamma × OI × 100)
            gamma = contract.get('gamma', 0) or 0
            gamma_exposure = gamma * oi * 100
            total_gamma_exp += gamma_exposure

            # Track gamma by strike for max gamma calculation
            strike = contract.get('strike')
            if strike:
                if strike not in gamma_by_strike:
                    gamma_by_strike[strike] = 0
                gamma_by_strike[strike] += gamma_exposure

            # Theta exposure (theta × OI × 100)
            theta = contract.get('theta', 0) or 0
            total_theta_exp += theta * oi * 100

            # Vega exposure (vega × OI × 100)
            vega = contract.get('vega', 0) or 0
            vega_exposure = vega * oi * 100
            total_vega_exp += vega_exposure
            if option_type == 'CALL':
                call_vega_exp += vega_exposure
            else:
                put_vega_exp += vega_exposure

        # Find strike with max gamma exposure
        max_gamma_strike = None
        if gamma_by_strike:
            max_gamma_strike = format_price(max(gamma_by_strike.items(), key=lambda x: abs(x[1]))[0])

        # Calculate net exposures
        net_delta_exp = format_greek(call_delta_exp + put_delta_exp)  # Puts have negative delta, so sum gives net
        net_vega_exp = format_greek(call_vega_exp - put_vega_exp)

        return {
            'total_delta_exposure': format_greek(total_delta_exp),
            'call_delta_exposure': format_greek(call_delta_exp),
            'put_delta_exposure': format_greek(put_delta_exp),
            'net_delta_exposure': net_delta_exp,
            'total_gamma_exposure': format_greek(total_gamma_exp),
            'max_gamma_strike': max_gamma_strike,
            'total_theta_exposure': format_greek(total_theta_exp),
            'total_vega_exposure': format_greek(total_vega_exp),
            'call_vega_exposure': format_greek(call_vega_exp),
            'put_vega_exposure': format_greek(put_vega_exp),
            'net_vega_exposure': net_vega_exp
        }

    def _calculate_moneyness_distribution(self, contracts, close_price):
        """Calculate moneyness distribution across all contracts

        Args:
            contracts: List of contract dictionaries
            close_price: Current stock price

        Returns:
            dict: Moneyness distribution (OI and percentages by category)
        """
        # Initialize counters
        deep_itm_call_oi = 0
        itm_call_oi = 0
        atm_call_oi = 0
        otm_call_oi = 0
        deep_otm_call_oi = 0

        deep_itm_put_oi = 0
        itm_put_oi = 0
        atm_put_oi = 0
        otm_put_oi = 0
        deep_otm_put_oi = 0

        total_call_oi = 0
        total_put_oi = 0

        for contract in contracts:
            oi = contract.get('open_interest', 0) or 0
            if oi == 0:
                continue

            strike = contract.get('strike')
            option_type = contract.get('option_type', '').upper()

            # Get moneyness category
            moneyness = contract.get('moneyness') or self._calculate_moneyness_category(
                strike, close_price, option_type
            )

            # Accumulate by category
            if option_type == 'CALL':
                total_call_oi += oi
                if moneyness == 'DEEP_ITM':
                    deep_itm_call_oi += oi
                elif moneyness == 'ITM':
                    itm_call_oi += oi
                elif moneyness == 'ATM':
                    atm_call_oi += oi
                elif moneyness == 'OTM':
                    otm_call_oi += oi
                elif moneyness == 'DEEP_OTM':
                    deep_otm_call_oi += oi
            else:  # PUT
                total_put_oi += oi
                if moneyness == 'DEEP_ITM':
                    deep_itm_put_oi += oi
                elif moneyness == 'ITM':
                    itm_put_oi += oi
                elif moneyness == 'ATM':
                    atm_put_oi += oi
                elif moneyness == 'OTM':
                    otm_put_oi += oi
                elif moneyness == 'DEEP_OTM':
                    deep_otm_put_oi += oi

        # Calculate percentages
        deep_itm_call_pct = format_percentage((deep_itm_call_oi / total_call_oi * 100) if total_call_oi > 0 else 0)
        itm_call_pct = format_percentage((itm_call_oi / total_call_oi * 100) if total_call_oi > 0 else 0)
        atm_call_pct = format_percentage((atm_call_oi / total_call_oi * 100) if total_call_oi > 0 else 0)
        otm_call_pct = format_percentage((otm_call_oi / total_call_oi * 100) if total_call_oi > 0 else 0)
        deep_otm_call_pct = format_percentage((deep_otm_call_oi / total_call_oi * 100) if total_call_oi > 0 else 0)

        deep_itm_put_pct = format_percentage((deep_itm_put_oi / total_put_oi * 100) if total_put_oi > 0 else 0)
        itm_put_pct = format_percentage((itm_put_oi / total_put_oi * 100) if total_put_oi > 0 else 0)
        atm_put_pct = format_percentage((atm_put_oi / total_put_oi * 100) if total_put_oi > 0 else 0)
        otm_put_pct = format_percentage((otm_put_oi / total_put_oi * 100) if total_put_oi > 0 else 0)
        deep_otm_put_pct = format_percentage((deep_otm_put_oi / total_put_oi * 100) if total_put_oi > 0 else 0)

        return {
            # Call OI by moneyness
            'deep_itm_call_oi': deep_itm_call_oi,
            'itm_call_oi': itm_call_oi,
            'atm_call_oi': atm_call_oi,
            'otm_call_oi': otm_call_oi,
            'deep_otm_call_oi': deep_otm_call_oi,
            # Put OI by moneyness
            'deep_itm_put_oi': deep_itm_put_oi,
            'itm_put_oi': itm_put_oi,
            'atm_put_oi': atm_put_oi,
            'otm_put_oi': otm_put_oi,
            'deep_otm_put_oi': deep_otm_put_oi,
            # Call percentages
            'deep_itm_call_pct': deep_itm_call_pct,
            'itm_call_pct': itm_call_pct,
            'atm_call_pct': atm_call_pct,
            'otm_call_pct': otm_call_pct,
            'deep_otm_call_pct': deep_otm_call_pct,
            # Put percentages
            'deep_itm_put_pct': deep_itm_put_pct,
            'itm_put_pct': itm_put_pct,
            'atm_put_pct': atm_put_pct,
            'otm_put_pct': otm_put_pct,
            'deep_otm_put_pct': deep_otm_put_pct
        }

    def _calculate_quality_metrics(self, contracts):
        """Calculate average bid-ask spread from option_contracts

        Args:
            contracts: List of contract dictionaries

        Returns:
            dict: Quality metrics (avg_bid_ask_spread_pct)
        """
        from tools.decimal_formatter import format_percentage

        spreads = [c.get('bid_ask_spread_pct') for c in contracts
                   if c.get('bid_ask_spread_pct') is not None and c.get('bid_ask_spread_pct') > 0]

        avg_bid_ask_spread_pct = None
        if spreads:
            avg_bid_ask_spread_pct = format_percentage(sum(spreads) / len(spreads))

        return {'avg_bid_ask_spread_pct': avg_bid_ask_spread_pct}

    def _bulk_insert_summaries(self, summaries):
        """Bulk insert symbol summaries into database
        
        Args:
            summaries: List of summary dictionaries
            
        Returns:
            bool: Success status
        """
        try:
            # Use storage method for bulk insert
            success = self.storage.insert_symbol_summaries(summaries)
            return success
            
        except Exception as e:
            logging.error("OP Rollup: Bulk insert failed: {}".format(e))
            return False
    
    def _calculate_dte(self, expiration_date_str, trade_date_str):
        """Calculate days to expiration from date strings

        Args:
            expiration_date_str: Expiration date in YYYY-MM-DD format
            trade_date_str: Trade date in YYYY-MM-DD format

        Returns:
            int: Days to expiration (0 if same day, negative if expired)
        """
        try:
            exp_date = datetime.strptime(expiration_date_str, '%Y-%m-%d').date()
            trade_date_obj = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
            return (exp_date - trade_date_obj).days
        except (ValueError, TypeError) as e:
            logging.warning("OP Rollup: Error calculating DTE for {} - {}: {}".format(
                expiration_date_str, trade_date_str, e))
            return 0

    def _log_batch_progress(self, processed, total, batch_time):
        """Log progress for current batch

        Args:
            processed: Number of symbols processed so far
            total: Total symbols to process
            batch_time: Time taken for current batch
        """
        progress_pct = (processed / total) * 100

        avg_batch_time = sum(self.stats['processing_time_per_batch']) / len(self.stats['processing_time_per_batch'])
        remaining_batches = math.ceil((total - processed) / self.batch_size)
        eta_seconds = remaining_batches * avg_batch_time

        logging.info("   Progress: {}/{} symbols ({:.1f}%) - batch: {:.2f}s, ETA: {:.1f}s".format(
            processed, total, progress_pct, batch_time, eta_seconds))
    
    def _log_completion_stats(self, trade_date, total_time):
        """Log completion statistics

        Args:
            trade_date: Date that was processed
            total_time: Total processing time in seconds
        """
        # Single summary line at INFO level
        beautiful_log("OP Rollup complete: {} symbols, {} with data, {} errors".format(
            self.stats['symbols_processed'],
            self.stats['symbols_with_data'],
            self.stats['errors_encountered']), 'success')

        # Detailed stats demoted to DEBUG
        logging.debug("Total symbols: {}".format(self.stats['total_symbols']))
        logging.debug("Symbols processed: {}".format(self.stats['symbols_processed']))
        logging.debug("Symbols with data: {}".format(self.stats['symbols_with_data']))
        logging.debug("Symbols skipped (no data): {}".format(self.stats['symbols_skipped_no_data']))
        logging.debug("Summaries created: {}".format(self.stats['summaries_created']))
        logging.debug("Errors encountered: {}".format(self.stats['errors_encountered']))
        logging.debug("Total processing time: {:.2f} seconds".format(total_time))

        if self.stats['symbols_processed'] > 0:
            avg_time = total_time / self.stats['symbols_processed']
            logging.debug("Average time per symbol: {:.3f} seconds".format(avg_time))

        if self.stats['failed_symbols']:
            logging.warning("Failed symbols: {}".format(self.stats['failed_symbols'][:10]))
        
    def _safe_int(self, value):
        """Convert value to integer or None for SQLite compatibility
        
        Args:
            value: Value to convert (could be None, string, float, etc.)
            
        Returns:
            int or None: Integer value or None if conversion fails/value is None
        """
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
        
if __name__ == '__main__':
    import argparse
    import sys
    from pathlib import Path
    from datetime import datetime

    # Add project root to path for imports
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    parser = argparse.ArgumentParser(description='Run OID Symbol Rollup')
    parser.add_argument('--date', type=str, default=None, help='Date to process (YYYY-MM-DD), defaults to today')
    parser.add_argument('--symbol', type=str, default=None, help='Process single symbol (for testing)')
    args = parser.parse_args()

    # Parse date
    if args.date:
        try:
            trade_date_str = args.date
            trade_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            print(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            exit(1)
    else:
        trade_date = datetime.now().date()
        trade_date_str = trade_date.strftime('%Y-%m-%d')

    # Initialize rollup (use absolute imports now that sys.path is fixed)
    from strategies.option_pipeline.op_config import OIDConfig
    from strategies.option_pipeline.op_storage import OIDStorage
    config = OIDConfig()
    storage = OIDStorage(config)
    rollup = OIDSymbolRollup(storage)

    # Run rollup
    symbol_filter = args.symbol if args.symbol else None
    stats = rollup.process_symbols(trade_date_str, symbol_filter=symbol_filter)

    exit(0 if stats['summaries_created'] > 0 else 1)