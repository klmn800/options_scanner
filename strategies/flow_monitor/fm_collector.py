#!/usr/bin/env python3
"""
Flow Monitor Collector (fm_collector.py)
----------------------------------------
Phase 1: Collection Foundation - Minimal viable end-to-end options data collector.
Collects options data for analysis by subsequent files in the Flow Monitor module.

Features:
- Single collection run (--test mode with MAG7)
- Market hours checking - only collect during 9:30 AM - 4:00 PM ET, M-F
- Scan timestamp tracking - generate once per collection run
- Flow-optimized collection (7-45 DTE, ITM 20% to OTM 20%)
- Direct config loading and database operations (embedded)
- Simple console logging without complex progress tracking

Author: Ben (with assistance from Claude)
Date: 2025-06-26
"""

import os
import sys
import json
import logging
import argparse
import traceback
import sqlite3
import signal
import time
import threading
from strategies.flow_monitor.fm_config import FMConfig, shutdown_event
from strategies.flow_monitor.fm_storage import FlowMonitorStorage
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from tools.log_utils import beautiful_log


# Constants for MAG7 test mode and flow optimization
MAG7_SYMBOLS = ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA', 'SPY', 'QQQ']

FLOW_OPTIMIZED_CONFIG = {
    'etf_min_dte': 8,        # ETFs start at 8 DTE
    'stock_min_dte': 0,      # Stocks start at 0 DTE
    'max_dte': 60,
    'strike_range_pct': {
        'itm_max': 0.20,  # 20% ITM
        'otm_max': 0.20   # 20% OTM
    }
}

def generate_contract_hash(symbol, strike, expiration_date, option_type):
    """
    Generate standardized contract hash for unique identification
    
    Args:
        symbol: Ticker symbol (e.g., 'AAPL')
        strike: Strike price (e.g., 150.0)
        expiration_date: Expiration date string (e.g., '2025-08-15')
        option_type: 'CALL' or 'PUT'
    
    Returns:
        str: Contract hash in format 'SYMBOL|STRIKE|EXPIRATION|TYPE'
    """
    try:
        # Standardize inputs
        symbol_clean = str(symbol).upper().strip()
        strike_clean = float(strike)
        expiration_clean = str(expiration_date).strip()
        option_type_clean = str(option_type).upper().strip()
        
        # Create hash using pipe delimiter
        contract_hash = "{}|{}|{}|{}".format(
            symbol_clean, strike_clean, expiration_clean, option_type_clean
        )
        
        return contract_hash
        
    except Exception as e:
        logging.error("Error generating contract hash for {}/{}/{}/{}: {}".format(
            symbol, strike, expiration_date, option_type, e))
        return None

class FMCollector:
    """Flow Monitor data collector - embedded config and storage operations"""
    
    def __init__(self, config_path=None):
        """Initialize collector with new modular config and storage"""
        self.config_manager = FMConfig(config_path)
        self.storage = FlowMonitorStorage(self.config_manager)
        self.tradier_client = self.config_manager.tradier_client
        
        # Memory buffer for collected data - COMMENT OUT ALL OF THESE
        # self.contract_buffer = []
        # self.buffer_lock = threading.Lock()
        # self.max_buffer_size = 500000
        # self.last_flush_attempt = None
        # self.flush_interval_minutes = 3

        # Background flushing - COMMENT OUT THESE TOO
        # self.flush_thread = None
        # self.shutdown_event = threading.Event()

        # Track symbols missing from quotes each cycle (consumed by fm_main.py)
        self.last_missing_symbols = []
        # Track symbols that had quotes but failed options collection
        self.last_failed_options_symbols = []
        # Track structured error details per cycle (consumed by FMSessionStats)
        self.last_error_details = []
        # Track DB storage duration per cycle (consumed by fm_main.py for perf breakdown)
        self.last_storage_elapsed = 0.0
        # Track per-cycle stats for performance database (consumed by FMSessionStats)
        self.last_contracts_collected = 0
        self.last_symbols_with_data = 0

        logging.debug("FM Collector initialized with modular config and storage")
    
    def _get_project_root(self):
        """Get the root directory of the project (from strategies/Flow Monitor -> project root)"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up two levels: strategies/Flow Monitor -> strategies -> project root
        return os.path.dirname(os.path.dirname(script_dir))
    
    def is_market_open(self):
        """Check if market is currently open (9:30 AM - 4:00 PM ET, M-F)"""
        try:
            from market_hours import is_market_open
            return is_market_open()
        except ImportError:
            # Fallback: simple time-based check
            now = now_eastern()
            if now.weekday() >= 5:  # Weekend
                return False
            
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            
            return market_open <= now <= market_close
    
    def run_once(self, symbols, closing_scan=False, pre_open_scan=False):
        """Run single collection cycle

        Args:
            symbols: List of symbols to collect
            closing_scan: If True, bypass is_market_open() check (used for EOD closing scan)
            pre_open_scan: If True, bypass is_market_open() check (used for 9:15 AM pre-open snapshot)
        """

        # Generate scan timestamp ONCE for this entire collection run
        scan_timestamp = eastern_isoformat()

        if closing_scan:
            label = " (closing scan)"
        elif pre_open_scan:
            label = " (pre-open scan)"
        else:
            label = ""
        beautiful_log("Starting FM Collector{}".format(label), 'info')
        beautiful_log("Scan timestamp: {}".format(scan_timestamp), 'info')

        # Check market hours (skip for closing/pre-open scans — caller already validated timing)
        if not closing_scan and not pre_open_scan:
            if self.is_market_open():
                logging.debug("Market is OPEN")
            else:
                logging.info("Market is CLOSED")
                return False

        logging.debug("Collecting data for {} symbols".format(len(symbols)))
        
        # Collect market data with scan timestamp
        result = self._collect_market_data(symbols, scan_timestamp)

        if result:
            logging.debug("Collection complete (internal)")
            return scan_timestamp  # Return the timestamp, not just success!
        else:
            logging.info("Collection failed")
            return False

    def run_once_forced(self, symbols):
        """Run single collection cycle regardless of market hours (for testing)"""
        # Generate scan timestamp ONCE for this entire collection run
        scan_timestamp = eastern_isoformat()

        logging.info("Starting FM Collector (FORCED)")
        logging.info("Scan timestamp: {}".format(scan_timestamp))
        logging.info("Market hours check BYPASSED")
        logging.info("Collecting data for {} symbols".format(len(symbols)))
        
        # Collect market data with scan timestamp
        result = self._collect_market_data(symbols, scan_timestamp)
        
        if result:
            logging.info("Collection complete")
            return scan_timestamp  # Return the timestamp, not just success!
        else:
            logging.info("Collection failed")
            return False
    
    def _collect_market_data(self, symbols, scan_timestamp):
        """Collect underlying prices and options data for symbols"""
        try:
            # Collect underlying prices first - one quote per symbol
            quotes_data = self._collect_quotes_batch(symbols)
            if not quotes_data:
                logging.warning("No quotes data collected - options collection may have incomplete underlying prices")

            # Identify symbols that will be skipped due to missing/invalid quotes
            quotes_with_price = set()
            if quotes_data:
                for sym, quote in quotes_data.items():
                    last = quote.get('last')
                    if last and last > 0:
                        quotes_with_price.add(sym)

            self.last_missing_symbols = sorted(set(symbols) - quotes_with_price)
            if self.last_missing_symbols:
                logging.warning("{} symbols missing quotes: {}".format(
                    len(self.last_missing_symbols),
                    ", ".join(self.last_missing_symbols)))

            # Collect options data using the quotes for underlying prices
            result = self._collect_options_data(symbols, scan_timestamp, quotes_data)

            # AUTOFIX INTEGRATION: Verify data was actually stored
            if result:  # result is scan_timestamp if successful
                # Check if any contracts were actually stored
                try:
                    verify_query = "SELECT COUNT(*) as contract_count FROM flow_options_scans WHERE scan_timestamp = ?"
                    verify_result = self.storage.query_with_params(verify_query, (scan_timestamp,))
                    contracts_stored = verify_result[0]['contract_count'] if verify_result else 0

                    # Silent failure: collection succeeded but no data in database
                    if contracts_stored == 0 and len(symbols) > 0:
                        from tools.autofix import handle_error
                        handle_error(
                            error_type='fm_collection_zero_alerts',
                            context={
                                'symbols_attempted': len(symbols),
                                'scan_timestamp': scan_timestamp,
                                'contracts_stored': contracts_stored,
                                'quotes_collected': len(quotes_data) if quotes_data else 0,
                                'trade_date': eastern_date_string(),
                                'location': 'collector',
                                'main_py_pid': os.getppid()
                            },
                            severity='CRITICAL'
                        )
                        # Never reached - handle_error exits with sys.exit(1)
                except Exception as verify_error:
                    logging.error("Error verifying contract storage: {}".format(verify_error))
                    # Don't crash on verification error - return success

            return result  # This is now the scan_timestamp, not a boolean!

        except Exception as e:
            logging.error("Error during market data collection: " + str(e))
            return False
    
    def _collect_quotes_batch(self, symbols):
        """Collect underlying prices using existing TradierDataClient (with automatic caching)"""
        try:
            # Use existing client with automatic caching - one call per batch
            beautiful_log("Fetching underlying prices for {} symbols".format(len(symbols)), 'info')
            quotes_data = self.tradier_client.get_quotes(symbols)

            if quotes_data:
                beautiful_log("Prices received for {} symbols".format(len(quotes_data)), 'success')
                return quotes_data
            else:
                logging.warning("No quotes data returned from API")
                return {}
            
        except Exception as e:
            logging.error("Error collecting quotes: " + str(e))
            return {}
    
    def _collect_options_data(self, symbols, scan_timestamp, quotes_data):
        """Collect options data for symbols and store with scan timestamp"""
        total_contracts = 0
        successful_symbols = 0
        self.last_error_details = []  # Reset per-cycle error details

        # DIAGNOSTIC: Check for duplicate symbols in input list
        unique_symbols = len(set(symbols))
        if unique_symbols != len(symbols):
            duplicate_symbols = [s for s in set(symbols) if symbols.count(s) > 1]
            logging.warning("⚠️ DUPLICATE SYMBOLS IN INPUT LIST: {} total, {} unique, duplicates: {}".format(
                len(symbols), unique_symbols, duplicate_symbols[:10]))
        else:
            beautiful_log("Symbol list validated: {} unique, no duplicates".format(len(symbols)), 'success')

        print("")  # Visual breathing room before per-symbol heartbeat

        # Create quotes lookup for underlying prices
        quotes_lookup = {}
        if quotes_data:
            for symbol, quote in quotes_data.items():
                if 'last' in quote:
                    quotes_lookup[symbol] = quote['last']

        symbols_with_options = set()  # Track which symbols returned options data

        try:
            # Process symbols individually or in parallel based on count
            if len(symbols) > 20:
                # Parallel processing for large symbol sets
                with ThreadPoolExecutor(max_workers=2) as executor:
                    future_to_symbol = {
                        executor.submit(self._collect_single_symbol_options, symbol, quotes_lookup, scan_timestamp): symbol
                        for symbol in symbols
                    }
                    
                    all_options_data = []
                    for future in as_completed(future_to_symbol):
                        symbol = future_to_symbol[future]
                        
                        if shutdown_event.is_set():
                            logging.info("Shutdown requested during options collection")
                            break
                        
                        try:
                            options_data = future.result()
                            if options_data:
                                all_options_data.extend(options_data)
                                total_contracts += len(options_data)
                                successful_symbols += 1
                                symbols_with_options.add(symbol)
                                logging.info("Option chains collected for {} - {} contracts".format(symbol, len(options_data)))
                            else:
                                logging.info("Option chains collected for {} - no data".format(symbol))
                        except Exception as e:
                            error_type = type(e).__name__
                            logging.error("Failed to collect options for {}: {} - {}".format(symbol, error_type, str(e)))
                            # Enhanced console error visibility + structured capture
                            error_str = str(e).lower()
                            if "timeout" in error_str:
                                logging.warning("{} - TIMEOUT ERROR".format(symbol))
                                err_category = 'timeout'
                            elif "429" in str(e) or "rate limit" in error_str:
                                logging.warning("{} - RATE LIMIT HIT".format(symbol))
                                err_category = 'rate_limit'
                            elif "connection" in error_str:
                                logging.warning("{} - CONNECTION ERROR".format(symbol))
                                err_category = 'connection'
                            else:
                                logging.warning("{} - ERROR: {} - {}".format(symbol, error_type, str(e)[:50]))
                                err_category = 'other'
                            self.last_error_details.append({
                                'symbol': symbol, 'type': err_category, 'message': str(e)[:200]
                            })
            else:
                # Sequential processing for small symbol sets
                all_options_data = []
                for symbol in symbols:
                    if shutdown_event.is_set():
                        logging.info("Shutdown requested during options collection")
                        break

                    try:
                        options_data = self._collect_single_symbol_options(symbol, quotes_lookup, scan_timestamp)
                        if options_data:
                            all_options_data.extend(options_data)
                            total_contracts += len(options_data)
                            successful_symbols += 1
                            symbols_with_options.add(symbol)
                            logging.info("Option chains collected for {} - {} contracts".format(symbol, len(options_data)))
                        else:
                            logging.info("Option chains collected for {} - no data".format(symbol))
                    except Exception as e:
                        error_type = type(e).__name__
                        logging.error("Failed to collect options for {}: {} - {}".format(symbol, error_type, str(e)))
                        # Enhanced console error visibility + structured capture
                        error_str = str(e).lower()
                        if "timeout" in error_str:
                            logging.warning("{} - TIMEOUT ERROR".format(symbol))
                            err_category = 'timeout'
                        elif "429" in str(e) or "rate limit" in error_str:
                            logging.warning("{} - RATE LIMIT HIT".format(symbol))
                            err_category = 'rate_limit'
                        elif "connection" in error_str:
                            logging.warning("{} - CONNECTION ERROR".format(symbol))
                            err_category = 'connection'
                        else:
                            logging.warning("{} - ERROR: {} - {}".format(symbol, error_type, str(e)[:50]))
                            err_category = 'other'
                        self.last_error_details.append({
                            'symbol': symbol, 'type': err_category, 'message': str(e)[:200]
                        })

            # Identify symbols that had quotes but failed options collection
            self.last_failed_options_symbols = sorted(set(quotes_lookup.keys()) - symbols_with_options)
            if self.last_failed_options_symbols:
                logging.warning("{} symbols had quotes but returned no options: {}".format(
                    len(self.last_failed_options_symbols),
                    ", ".join(self.last_failed_options_symbols)))

            # Store all collected options data with scan timestamp
            if all_options_data:
                # DIAGNOSTIC: Check for duplicates in collected batch data
                # BATCHFIX 2026-01-14: Changed from ERROR to WARNING since duplicates are
                # successfully deduplicated in fm_storage.py before DB insert. This is an
                # upstream API data quality issue, not a system failure.
                contract_hashes = [c.get('contract_hash') for c in all_options_data if c.get('contract_hash')]
                unique_hashes = len(set(contract_hashes))
                if unique_hashes != len(contract_hashes):
                    duplicate_count = len(contract_hashes) - unique_hashes
                    logging.warning("⚠️ API returned {} duplicate contracts in batch (will be deduplicated before DB insert)".format(
                        duplicate_count))

                    # Find which contracts/symbols are duplicated
                    from collections import Counter
                    hash_counts = Counter(contract_hashes)
                    duplicated_hashes = {h: count for h, count in hash_counts.items() if count > 1}
                    # Extract symbol names from hashes (format: SYMBOL|STRIKE|EXPIRATION|TYPE)
                    dup_symbols = Counter(h.split('|')[0] for h in duplicated_hashes)
                    logging.warning("  Duplicate source symbols: {} (top 5 hashes: {})".format(
                        dict(dup_symbols.most_common(5)),
                        list(duplicated_hashes.items())[:5]))
                else:
                    beautiful_log("Batch validated: {:,} contracts, no duplicates".format(len(contract_hashes)), 'success')

                # Store to database
                storage_start = time.time()
                success = self._store_options(all_options_data, scan_timestamp)
                self.last_storage_elapsed = time.time() - storage_start
                if not success:
                    logging.error("Failed to store options data")
                    return False

                beautiful_log("Stored {:,} contracts in {:.1f}s (scan: {})".format(
                    total_contracts, self.last_storage_elapsed, scan_timestamp), 'success')

                # Expose per-cycle stats for FMSessionStats
                self.last_contracts_collected = total_contracts
                self.last_symbols_with_data = successful_symbols

                return scan_timestamp
                
            else:
                logging.warning("No options data collected from any symbols")
                self.last_contracts_collected = 0
                self.last_symbols_with_data = 0
                return False

        except Exception as e:
            logging.error("Error during options data collection: {}".format(e))
            self.last_contracts_collected = 0
            self.last_symbols_with_data = 0
            return False
    
           
    def _collect_single_symbol_options(self, symbol, quotes_lookup, scan_timestamp):
        """Collect options data for a single symbol with flow optimization"""
        try:
            underlying_price = quotes_lookup.get(symbol, 0)
            if underlying_price <= 0:
                logging.warning("No valid underlying price for {} - skipping".format(symbol))
                return []

            # Initialize the list to collect all contracts
            all_contracts = []

            # Get option expirations
            expirations = self.tradier_client.get_option_expirations(symbol)
            if not expirations or 'date' not in expirations:
                logging.warning("No expirations for {}: response={}".format(symbol, repr(expirations)[:200]))
                return []
            
            exp_dates = expirations['date']
            if not isinstance(exp_dates, list):
                exp_dates = [exp_dates]
            
            # Filter expirations by DTE range
            filtered_expirations = self._filter_expirations_by_dte(exp_dates, symbol)

            # Use all expirations within DTE range (no arbitrary count limit)
            target_expirations = filtered_expirations

            if not target_expirations:
                return []

            # DIAGNOSTIC: Check for duplicates in target_expirations before processing
            if len(target_expirations) != len(set(target_expirations)):
                duplicates = [exp for exp in set(target_expirations) if target_expirations.count(exp) > 1]
                logging.error("🔴 DUPLICATE EXPIRATIONS IN target_expirations for {}: {}".format(symbol, duplicates))
                logging.error("🔴 Full target_expirations list: {}".format(target_expirations))

            # Calculate days to expiration helper
            from datetime import datetime
            from timezone_utils import now_eastern
            today = now_eastern().date()

            # Collect options for each expiration
            for expiration in target_expirations:
                logging.debug("Fetching option chain for {} expiring {}".format(symbol, expiration))
                options_data = self.tradier_client.get_option_chain(symbol, expiration)

                if not options_data:
                    continue

                # Handle different possible API response formats
                # (Tradier returns varying structures depending on symbol/endpoint)
                if isinstance(options_data, list):
                    options_list = options_data
                elif 'options' in options_data:
                    options_list = options_data.get('options', {}).get('option', [])
                elif 'option' in options_data:
                    options_list = options_data.get('option', [])
                else:
                    options_list = []

                if options_list:
                    if not isinstance(options_list, list):
                        options_list = [options_list]
                    
                    # Filter to flow-relevant strikes (also removes adjusted options)
                    filtered_options = self._filter_options_for_flow(options_list, underlying_price, symbol)
                    
                    if filtered_options:
                        # Create contract dictionaries for storage
                        for option in filtered_options:
                            # Smart filtering based on moneyness and positioning
                            volume = option.get('volume', 0)
                            open_interest = option.get('open_interest', 0)
                            strike = option.get('strike', 0)

                            # Apply data-driven filter: remove zero-volume contracts that are
                            # >10% from underlying price AND have <50 open interest
                            if volume == 0 and strike and underlying_price:
                                distance_from_underlying = abs(strike - underlying_price) / underlying_price
                                
                                # Get filter config with defaults
                                config_filters = self.config_manager.config.get('flow_monitor', {}).get('collection_filters', {})
                                max_distance = config_filters.get('max_distance_from_underlying', 0.10)
                                min_oi_distant = config_filters.get('min_oi_for_distant_strikes', 50)
                                
                                # Remove if far from money AND low open interest
                                if distance_from_underlying > max_distance and open_interest < min_oi_distant:
                                    continue
                                
                            # Calculate days to expiration
                            exp_date = datetime.strptime(option.get('expiration_date'), '%Y-%m-%d').date()
                            days_to_exp = (exp_date - today).days
                            
                            # Calculate moneyness
                            strike = option.get('strike')
                            moneyness = None
                            if strike and underlying_price:
                                if option.get('option_type') == 'call':
                                    if strike < underlying_price * 0.99:
                                        moneyness = 'ITM'
                                    elif strike > underlying_price * 1.01:
                                        moneyness = 'OTM'
                                    else:
                                        moneyness = 'ATM'
                                else:  # put
                                    if strike > underlying_price * 1.01:
                                        moneyness = 'ITM'
                                    elif strike < underlying_price * 0.99:
                                        moneyness = 'OTM'
                                    else:
                                        moneyness = 'ATM'
                            
                            # Generate contract hash for unique identification
                            contract_hash = generate_contract_hash(
                                symbol, 
                                option.get('strike'), 
                                option.get('expiration_date'), 
                                option.get('option_type')
                            )
                            
                            contract = {
                                'symbol': symbol,
                                'trade_date': eastern_date_string(),
                                'underlying_price': underlying_price,
                                'strike': option.get('strike'),
                                'expiration_date': option.get('expiration_date'),
                                'option_type': option.get('option_type'),
                                'contract_hash': contract_hash,
                                'volume': option.get('volume', 0),
                                'open_interest': option.get('open_interest', 0),
                                'bid': option.get('bid', 0.0),
                                'ask': option.get('ask', 0.0),
                                'last_price': option.get('last', 0.0),
                                'implied_volatility': (option.get('greeks') or {}).get('smv_vol', 0.0),
                                'delta': (option.get('greeks') or {}).get('delta', 0.0),
                                'gamma': (option.get('greeks') or {}).get('gamma', 0.0),
                                'theta': (option.get('greeks') or {}).get('theta', 0.0),
                                'vega': (option.get('greeks') or {}).get('vega', 0.0),
                                'days_to_expiration': days_to_exp,
                                'moneyness': moneyness
                            }
                            
                            # Log warning if hash generation failed
                            if not contract_hash:
                                logging.warning("Failed to generate contract hash for {}/{}/{}/{}".format(
                                    symbol, option.get('strike'), option.get('expiration_date'), option.get('option_type')))

                            all_contracts.append(contract)
                    
                        total_contracts = len(filtered_options)
                        stored_contracts = len(all_contracts)
                        if total_contracts > 0:
                            logging.debug("Stored {} of {} contracts for {} ({:.1%} with activity)".format(
                                stored_contracts, total_contracts, symbol, 
                                stored_contracts / total_contracts
                            ))
            return all_contracts
            
        except Exception as e:
            logging.error("Error collecting options for {}: {}".format(symbol, e))
            return []
    
    def _filter_expirations_by_dte(self, exp_dates, symbol):
        """Filter expirations to DTE range with symbol-specific logic"""
        today = now_eastern().date()
        filtered = []

        # DIAGNOSTIC: Check input for duplicates BEFORE filtering
        if len(exp_dates) != len(set(exp_dates)):
            input_duplicates = [exp for exp in set(exp_dates) if exp_dates.count(exp) > 1]
            logging.warning("⚠️ INPUT exp_dates for {} has {} duplicates: {}".format(
                symbol, len(exp_dates) - len(set(exp_dates)), input_duplicates[:5]))

        # Symbol-specific DTE ranges
        if symbol in ['SPY', 'QQQ', 'IWM']:
            min_dte = FLOW_OPTIMIZED_CONFIG['etf_min_dte']  # 8 days
            max_dte = 30
        elif symbol.startswith('XL'):  # Sector ETFs
            min_dte = FLOW_OPTIMIZED_CONFIG['stock_min_dte']  # 0 days
            max_dte = 45
        else:  # Individual stocks
            min_dte = FLOW_OPTIMIZED_CONFIG['stock_min_dte']  # 0 days
            max_dte = FLOW_OPTIMIZED_CONFIG['max_dte']  # 60 days

        for exp_str in exp_dates:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                dte = (exp_date - today).days

                if min_dte <= dte <= max_dte:
                    filtered.append(exp_str)

            except ValueError:
                continue

        # DIAGNOSTIC: Check filtered list BEFORE deduplication
        if len(filtered) != len(set(filtered)):
            pre_dedup_duplicates = [exp for exp in set(filtered) if filtered.count(exp) > 1]
            logging.warning("⚠️ PRE-DEDUP filtered list for {} has {} duplicates: {}".format(
                symbol, len(filtered) - len(set(filtered)), pre_dedup_duplicates[:5]))

        # AUTO-FIX: Deduplicate expiration dates to prevent duplicate API calls
        # Tradier API occasionally returns duplicate expiration dates
        if filtered:
            original_count = len(filtered)
            filtered = list(dict.fromkeys(filtered))  # Preserves order, removes duplicates
            if len(filtered) < original_count:
                logging.warning("⚠️ POST-DEDUP Removed {} duplicate expiration dates for {} from API response".format(
                    original_count - len(filtered), symbol))

        return filtered
    
    def _filter_options_for_flow(self, options_list, underlying_price, symbol=None):
        """Filter options to flow-relevant strikes (±20% of underlying price)

        Also filters out adjusted options (e.g. BDX1, GME1) that result from
        corporate actions. These have different deliverables and confuse flow analysis.
        """
        if not options_list or underlying_price <= 0:
            return []

        # Calculate strike range (±20%)
        itm_threshold = underlying_price * 0.80  # 20% below current price
        otm_threshold = underlying_price * 1.20  # 20% above current price

        filtered_options = []
        adjusted_skipped = 0
        for option in options_list:
            # Skip None entries from API
            if option is None:
                continue

            try:
                # Skip adjusted options (root_symbol doesn't match ticker)
                # e.g. BDX1, CMCS1, GME1 from spinoffs/splits have different deliverables
                if symbol:
                    root = option.get('root_symbol', '')
                    if root and root != symbol:
                        adjusted_skipped += 1
                        continue

                strike = float(option.get('strike', 0))

                # Keep options within ±20% range
                if itm_threshold <= strike <= otm_threshold:
                    filtered_options.append(option)

            except (ValueError, TypeError, AttributeError):
                continue  # Skip options with invalid strike data or None values

        if adjusted_skipped > 0:
            logging.debug("Filtered {} adjusted option contracts for {} (non-standard root_symbol)".format(
                adjusted_skipped, symbol))

        return filtered_options
    
    def _store_options(self, options_data, scan_timestamp):
        """Store options data using new storage module"""
        if not options_data:
            logging.warning("No options data to store")
            return True
        
        success = self.storage.store_option_contracts(options_data, scan_timestamp)
        return success

    def store_contracts_with_buffer(self, contracts, scan_timestamp):
        """Store contracts in memory buffer with specific scan timestamp"""
        if not contracts:
            return
        
        with self.buffer_lock:
            # Store contracts with their scan timestamp
            for contract in contracts:
                contract['scan_timestamp'] = scan_timestamp
            
            self.contract_buffer.extend(contracts)
            
            if len(self.contract_buffer) > self.max_buffer_size:
                logging.warning("Buffer size limit reached ({}), forcing flush attempt".format(self.max_buffer_size))
                self._attempt_buffer_flush(scan_timestamp)
            
            logging.debug("Added {} contracts to buffer, total buffered: {}".format(
                len(contracts), len(self.contract_buffer)))

    def start_background_flushing(self):
        """Start background thread that periodically tries to flush buffer to database"""
        if self.flush_thread and self.flush_thread.is_alive():
            return
        
        self.flush_thread = threading.Thread(target=self._background_flush_loop, daemon=True)
        self.flush_thread.start()
        logging.info("Background database flushing started")
    
    def _background_flush_loop(self):
        """Background thread that attempts to flush buffer every few minutes"""
        while not self.shutdown_event.is_set():
            try:
                if self.shutdown_event.wait(timeout=self.flush_interval_minutes * 60):
                    break
                
                self._attempt_buffer_flush()
                
            except Exception as e:
                logging.error("Background flush error: {}".format(e))
    
    def _attempt_buffer_flush(self, scan_timestamp=None):
        # Use provided timestamp or fall back to current time
        if scan_timestamp is None:
            scan_timestamp = eastern_isoformat()
        if not self.contract_buffer:
            return
        
        with self.buffer_lock:
            buffer_size = len(self.contract_buffer)
            
            if buffer_size == 0:
                return
            
            try:
                self.storage.store_option_contracts(self.contract_buffer, scan_timestamp)
                
                self.contract_buffer.clear()
                logging.info("Successfully flushed {} contracts from buffer to database".format(buffer_size))
                self.last_flush_attempt = datetime.now()
                
            except Exception as e:
                if "database is locked" in str(e).lower():
                    logging.debug("Database still locked, keeping {} contracts in buffer".format(buffer_size))
                else:
                    logging.error("Database error during flush: {}".format(e))
    
    def get_buffer_status(self):
        """Get current buffer statistics"""
        with self.buffer_lock:
            return {
                'contracts_buffered': len(self.contract_buffer),
                'last_flush_attempt': self.last_flush_attempt,
                'estimated_memory_mb': len(self.contract_buffer) * 0.002
            }        

    def shutdown_gracefully(self):
        """Shutdown with final buffer flush attempt"""
        logging.info("Graceful shutdown initiated")
        
        self.shutdown_event.set()
        
        if self.flush_thread and self.flush_thread.is_alive():
            self.flush_thread.join(timeout=30)
        
        buffer_status = self.get_buffer_status()
        if buffer_status['contracts_buffered'] > 0:
            logging.info("Attempting final flush of {} buffered contracts".format(
                buffer_status['contracts_buffered']))
            self._attempt_buffer_flush()
            
            final_status = self.get_buffer_status()
            if final_status['contracts_buffered'] > 0:
                logging.warning("Shutdown with {} contracts still in buffer - will be lost".format(
                    final_status['contracts_buffered']))          
                        
def wait_for_enter():
    """Wait for user to press Enter before continuing"""
    input("\nPress Enter to continue...")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Flow Monitor Data Collector")
    
    parser.add_argument('--test', action='store_true',
                        help='Test mode with MAG7 symbols')
    parser.add_argument('--mag7', action='store_true',
                        help='Use MAG7 symbols (same as --test)')
    parser.add_argument('--force', action='store_true',
                        help='Force collection even when market is closed')
    parser.add_argument('--config', 
                        help='Path to config.json file')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')
    
    return parser.parse_args()


def setup_logging(debug=False):
    """Set up logging"""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Suppress the duplicate Tradier API logs
    # Get the actual module name from the import
    tradier_logger = logging.getLogger('__main__')  # If tradier_api.py is run as main
    tradier_logger.setLevel(logging.WARNING)
    
    # Also try the module name directly
    logging.getLogger('tradier_api').setLevel(logging.WARNING)
    
    # If it's imported from core, try that path too
    logging.getLogger('core.tradier_api').setLevel(logging.WARNING)

def get_symbols_klmn800():
    """Get FM scan universe from core directory (curated subset of KLMN 800)"""
    try:
        from symbols_klmn800 import get_specialty_list
        return get_specialty_list('fm_scan')
    except ImportError:
        logging.warning("Could not import symbols_klmn800 from core directory, using MAG7 as fallback")
        return MAG7_SYMBOLS


def main():
    """Main entry point"""
    print("Flow Monitor Collector - Phase 1")
    print("Minimal viable end-to-end options data collector")
    
    # Wait for user confirmation
    wait_for_enter()
    
    try:
        args = parse_arguments()
        setup_logging(args.debug)
        
        collector = FMCollector(args.config)
        
        if args.test or args.mag7:
            symbols = MAG7_SYMBOLS
            logging.info("Using MAG7 test symbols: " + str(len(symbols)) + " symbols")
        else:
            symbols = get_symbols_klmn800()
            logging.info("Using KLMN 800 symbols: " + str(len(symbols)) + " symbols")
        
        if args.force:
            success = collector.run_once_forced(symbols)
        else:
            success = collector.run_once(symbols)
        
        if success:
            print("\n✅ Collection completed successfully!")
        else:
            print("\n❌ Collection failed or was skipped")

    except KeyboardInterrupt:
        logging.warning("Operation cancelled by user")
        if 'collector' in locals():
            collector.shutdown_gracefully()
        print("\nOperation cancelled by user. Exiting...")
    except Exception as e:
        logging.error("An error occurred: " + str(e))
        if 'collector' in locals():
            collector.shutdown_gracefully()
        print("\n❌ An error occurred: " + str(e))
        traceback.print_exc()
    
    # Always wait before closing
    wait_for_enter()


if __name__ == "__main__":
    main()