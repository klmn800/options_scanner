#!/usr/bin/env python3
"""
Open Interest Delta Collector 3.0 (oid_collector3.py)
---------------------------------------------------
Streamlined collection engine for Open Interest Delta system.
Evening-optimized bulk collection with configurable symbol universe.

Features:
- Configurable symbol universe (full OID, KLMN 800, custom lists)  
- Bulk quote optimization for API efficiency
- Smart filtering by DTE and strike range
- Concentration ratio analysis
- Beautiful progress logging
- Single symbol test mode

Author: Ben (with assistance from Claude)
Date: 2025-08-20
Version: 3.1 - Fixed API response parsing
Version: 3.2 - Data quality tracking (2026-03-17)
             - New stats: no_contract_symbols, total_options_seen, total_options_filtered
             - collect_symbol_oi returns None on error (not []) so caller can distinguish
               API errors from "no contracts with OI>0"
             - Empty contract results counted as failures (every KLMN symbol has options)
             - OI filter ratio tracked: how many options had OI=0/null vs OI>0
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from tools.autofix import handle_error
from tools.log_utils import beautiful_log

# Import OID modules
from strategies.option_pipeline.op_config import OIDConfig
from strategies.option_pipeline.op_storage import OIDStorage
from core.symbols_klmn800 import get_specialty_list

# Import timezone utilities
def get_project_root():
    """Get the root directory of the project"""
    current_file = os.path.abspath(__file__)    
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
    return project_root

project_root = get_project_root()
tools_dir = os.path.join(project_root, 'tools')

if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)

from timezone_utils import now_eastern, eastern_timestamp_string, eastern_date_string



def generate_contract_hash(symbol, strike, expiration_date, option_type):
    """
    Generate standardized contract hash for unique identification
    Format: SYMBOL|STRIKE|EXPIRATION|TYPE
    
    Args:
        symbol: Ticker symbol (e.g., 'AAPL')
        strike: Strike price (e.g., 182.50)
        expiration_date: Expiration date string (e.g., '2025-08-15')
        option_type: 'CALL' or 'PUT'
    
    Returns:
        str: Contract hash in format 'SYMBOL|STRIKE|EXPIRATION|TYPE'
    """
    try:
        symbol_clean = str(symbol).upper().strip()
        strike_clean = float(strike)
        expiration_clean = str(expiration_date).strip()
        option_type_clean = str(option_type).upper().strip()
        
        contract_hash = "{}|{}|{}|{}".format(
            symbol_clean, strike_clean, expiration_clean, option_type_clean
        )
        
        return contract_hash
        
    except Exception as e:
        logging.error("OP: Error generating contract hash: {}".format(e))
        return None


class OIDCollector:
    """Streamlined Open Interest Delta collection engine"""
    
    def __init__(self, config_path=None):
        """Initialize collector with configuration and storage"""
        self.config_manager = OIDConfig(config_path)
        self.storage = OIDStorage(self.config_manager)
        self.tradier_client = self.config_manager.tradier_client
        
        # Collection parameters from config
        collection_params = self.config_manager.get_collection_params()
        self.max_dte = collection_params.get('max_dte', 56)
        raw_pct = collection_params.get('strike_range_pct') or collection_params.get('strike_range_percent', 0.30)
        self.strike_range_pct = raw_pct / 100.0 if raw_pct > 1 else raw_pct
        self.batch_size = collection_params.get('batch_size', 100)
        self.universe_type = collection_params.get('universe', 'klmn_800')
        
        # Bulk quote optimization settings
        self.bulk_quote_batch_size = 100  # Tradier limit
        self.bulk_quote_cache = {}
        
        # Collection state tracking
        self.collection_stats = {
            'total_symbols': 0,
            'processed_symbols': 0,
            'successful_symbols': 0,
            'failed_symbols': 0,
            'failed_symbol_list': [],
            'total_contracts': 0,
            'api_calls_made': 0,
            'start_time': None,
            'no_contract_symbols': [],       # Symbols where 0 contracts survived OI filter
            'total_options_seen': 0,         # Total options returned by API (before OI filter)
            'total_options_filtered': 0,     # Options discarded due to OI=0 or OI=null
        }
        
        # Data buffers for batch processing
        self.contract_buffer = []
        self.current_scan_timestamp = None
        
        logging.debug("Collector initialized - Universe: {} (~{} symbols)".format(self.universe_type, len(get_specialty_list('klmn_800'))))
    
    def collect_daily_oi(self, single_symbol=None, retry_symbols_list=None):
        """
        Main collection method - clean and focused collection
        
        Args:
            single_symbol: Optional single symbol for testing
            retry_symbols_list: Optional list of specific symbols to retry (evening mode)
            
        Returns:
            bool: True if collection successful
        """
        self.collection_stats['start_time'] = time.time()
        self.current_scan_timestamp = eastern_timestamp_string()
        
        try:
            # Get symbol universe
            if single_symbol:
                symbols_to_collect = [single_symbol]
                beautiful_log("Single symbol mode: {}".format(single_symbol), 'info')
            elif retry_symbols_list:
                symbols_to_collect = retry_symbols_list
                beautiful_log("Evening retry mode: {} failed symbols to retry".format(len(symbols_to_collect)), 'info')
                logging.info("   Retrying: {}".format(', '.join(symbols_to_collect[:10])))
                if len(symbols_to_collect) > 10:
                    logging.info("   ... and {} more".format(len(symbols_to_collect) - 10))
            else:
                symbols_to_collect = self._get_collection_universe()
                beautiful_log("Full universe collection: {} symbols".format(len(symbols_to_collect)), 'info')
            
            self.collection_stats['total_symbols'] = len(symbols_to_collect)
            
            # Process symbols with bulk quote optimization
            for i in range(0, len(symbols_to_collect), self.bulk_quote_batch_size):
                batch_end = min(i + self.bulk_quote_batch_size, len(symbols_to_collect))
                batch_symbols = symbols_to_collect[i:batch_end]
                
                # Fetch bulk quotes for batch
                self._fetch_bulk_quotes(batch_symbols)
                
                # Process each symbol in batch
                for symbol in batch_symbols:
                    symbol_index = symbols_to_collect.index(symbol)
                    self._process_symbol_with_progress(symbol, symbol_index, len(symbols_to_collect))
            
            # CRITICAL: Always flush remaining contracts regardless of buffer size
            if self.contract_buffer:
                logging.info("Flushing final {} contracts to storage...".format(len(self.contract_buffer)))
                self._flush_contract_buffer()
            
            # Log final statistics
            self._log_collection_summary()

            # AUTOFIX INTEGRATION: Verify contracts were actually stored
            if self.collection_stats['total_contracts'] == 0 and self.collection_stats['api_calls_made'] > 0:
                handle_error(
                    error_type='op_collection_zero_contracts',
                    context={
                        'symbols_attempted': self.collection_stats['total_symbols'],
                        'successful_symbols': self.collection_stats['successful_symbols'],
                        'failed_symbols': self.collection_stats['failed_symbols'],
                        'api_calls_made': self.collection_stats['api_calls_made'],
                        'failed_symbol_list': self.collection_stats['failed_symbol_list'][:20],
                        'location': 'collector',
                        'main_py_pid': os.getppid()
                    },
                    severity='CRITICAL'
                )
                # Never reached - handle_error exits

            return True

        except Exception as e:
            logging.error("OP: Collection failed: {}".format(e))
            return False
    
    def _get_collection_universe(self):
        """Get the configured symbol universe for collection"""
        if self.universe_type == 'klmn_800' or self.universe_type == 'full_oid_universe':
            # Use KLMN 800 as the default universe (replacing full OID universe)
            return get_specialty_list('klmn_800')
        else:
            logging.warning("Unknown universe type: {}, using KLMN 800".format(self.universe_type))
            return get_specialty_list('klmn_800')
    
    def _process_symbol_with_progress(self, symbol, index, total):
        """Process single symbol and update progress"""
        try:
            # Collect symbol data
            # Returns: list of contracts (success), [] (no contracts), None (API error)
            contracts = self.collect_symbol_oi(symbol, self.bulk_quote_cache)

            if contracts is None:
                # API error — collect_symbol_oi caught an exception
                self._handle_symbol_error(symbol, Exception("Collection returned None — see previous error log"))
                self.collection_stats['failed_symbols'] += 1
                self.collection_stats['failed_symbol_list'].append(symbol)
            elif contracts:
                # Success — got contracts with OI>0
                self.contract_buffer.extend(contracts)
                self.collection_stats['total_contracts'] += len(contracts)
                self.collection_stats['successful_symbols'] += 1
                logging.debug("Collected {} contracts for {}".format(len(contracts), symbol))

                # Flush buffer if needed
                if len(self.contract_buffer) >= self.batch_size:
                    self._flush_contract_buffer()
            else:
                # Empty list — API worked but no contracts with OI>0
                self.collection_stats['failed_symbols'] += 1
                self.collection_stats['failed_symbol_list'].append(symbol)
                self.collection_stats['no_contract_symbols'].append(symbol)
                logging.debug("No contracts with OI>0 for {} — counted as failure".format(symbol))

            self.collection_stats['processed_symbols'] += 1
            
            # Log progress every 100 symbols (or always for small batches)
            if (index + 1) % 100 == 0 or (index + 1) == total or total < 100:
                self._log_progress(index + 1, total)
                
        except Exception as e:
            self._handle_symbol_error(symbol, e)
            self.collection_stats['failed_symbols'] += 1
            self.collection_stats['failed_symbol_list'].append(symbol)
            self.collection_stats['processed_symbols'] += 1
    
    def collect_symbol_oi(self, symbol, bulk_quotes_cache):
        """
        Collect all options for one symbol
        
        Args:
            symbol: Stock symbol
            bulk_quotes_cache: Pre-fetched quote data
            
        Returns:
            list: Contract data for the symbol
        """
        try:
            # Get stock price from cache or fetch
            if symbol in bulk_quotes_cache:
                quote_data = {symbol: bulk_quotes_cache[symbol]}
            else:
                quote_data = self.tradier_client.get_quotes([symbol])
                self.collection_stats['api_calls_made'] += 1
            
            if not quote_data or symbol not in quote_data:
                logging.debug("No quote data for {}".format(symbol))
                return []
            
            stock_info = quote_data[symbol]
            underlying_price = stock_info.get('last', 0)
            
            if underlying_price <= 0:
                logging.debug("Invalid price for {}: {}".format(symbol, underlying_price))
                return []
            
            # Get option expirations
            expirations_data = self.tradier_client.get_option_expirations(symbol)
            self.collection_stats['api_calls_made'] += 1
            
            if not expirations_data:
                return []
            
            # Extract expiration dates
            if isinstance(expirations_data, dict):
                expirations = expirations_data.get('date', [])
            else:
                expirations = expirations_data
            
            if not expirations:
                logging.debug("No expirations in list for {}".format(symbol))
                return []
            
            # Filter expirations by DTE
            valid_expirations = self._filter_expirations_by_dte(expirations)
            
            all_contracts = []
            total_symbol_oi = 0
            symbol_options_seen = 0  # Per-symbol: total options from API before OI filter

            # First pass: collect all contracts and total OI
            temp_contracts = []
            for expiration in valid_expirations:
                chain_data = self.tradier_client.get_option_chain(symbol, expiration)
                self.collection_stats['api_calls_made'] += 1

                if not chain_data:
                    logging.debug("No chain data for {} {}".format(symbol, expiration))
                    continue

                
                # Handle different possible API response formats
                if isinstance(chain_data, list):
                    # Direct list format (current API response)
                    options = chain_data
                elif 'options' in chain_data:
                    # Nested format: {'options': {'option': [...]}}
                    options = chain_data.get('options', {}).get('option', [])
                elif 'option' in chain_data:
                    # Flat format: {'option': [...]}
                    options = chain_data.get('option', [])
                else:
                    # Unknown format
                    logging.debug("Unknown chain data format for {} {}: {}".format(symbol, expiration, type(chain_data)))
                    options = []
                
                # Handle single option dict vs list of options
                if isinstance(options, dict):
                    options = [options]
                elif not options:
                    logging.debug("Empty options list for {} {}".format(symbol, expiration))
                    continue
                
                # Filter by strike range
                filtered_options = self._filter_strikes_by_range(options, underlying_price)
                logging.debug("Filtered {} options to {} within strike range".format(
                    len(options), len(filtered_options)
                ))
                
                for option in filtered_options:
                    oi = option.get('open_interest', 0) or 0
                    symbol_options_seen += 1
                    self.collection_stats['total_options_seen'] += 1
                    if oi > 0:
                        total_symbol_oi += oi
                        temp_contracts.append((option, expiration))
                    else:
                        self.collection_stats['total_options_filtered'] += 1
            
            logging.debug("Total OI for {}: {:,}".format(symbol, total_symbol_oi))

            if not temp_contracts and symbol_options_seen > 0:
                logging.debug("All {} options for {} filtered out (OI=0 or null)".format(
                    symbol_options_seen, symbol))

            # Second pass: create contracts with concentration ratios
            skipped_count = 0
            for option, expiration in temp_contracts:
                contract = self._create_contract_record(
                    symbol, option, expiration, underlying_price, total_symbol_oi
                )
                if contract:
                    all_contracts.append(contract)
                else:
                    skipped_count += 1

            # Log summary if contracts were skipped due to incomplete data
            if skipped_count > 0:
                logging.debug("Skipped {} contracts for {} due to incomplete API data".format(
                    skipped_count, symbol
                ))

            return all_contracts
            
        except Exception as e:
            logging.error("Error collecting {}: {}".format(symbol, e))
            return None
    
    def _filter_expirations_by_dte(self, expirations):
        """Filter expirations to those within max DTE"""
        today = now_eastern().date()
        valid_expirations = []
        
        for exp_str in expirations:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                dte = (exp_date - today).days
                
                if 0 <= dte <= self.max_dte:
                    valid_expirations.append(exp_str)
                    
            except ValueError:
                continue
        
        return valid_expirations
    
    def _filter_strikes_by_range(self, options, underlying_price):
        """Filter strikes within configured percentage of current price"""
        min_strike = underlying_price * (1 - self.strike_range_pct)
        max_strike = underlying_price * (1 + self.strike_range_pct)

        filtered = []
        for option in options:
            # Skip None values from malformed API responses
            if option is None:
                continue
            strike = float(option.get('strike', 0))
            if min_strike <= strike <= max_strike:
                filtered.append(option)

        return filtered
    
    def _create_contract_record(self, symbol, option, expiration, underlying_price, total_symbol_oi):
        """Create contract record with all required fields"""
        try:
            # Validate option data exists
            if option is None:
                return None

            strike = float(option.get('strike', 0))
            option_type = option.get('option_type', '').upper()
            open_interest = option.get('open_interest', 0) or 0

            # Generate contract hash
            contract_hash = generate_contract_hash(symbol, strike, expiration, option_type)

            # Safely extract Greeks data (handle None response)
            greeks = option.get('greeks') or {}

            return {
                'symbol': symbol,
                'strike': strike,
                'expiration_date': expiration,
                'option_type': option_type,
                'open_interest': open_interest,
                'volume': option.get('volume', 0) or 0,
                'underlying_price': underlying_price,
                'contract_hash': contract_hash,
                'trade_date': eastern_date_string(),
                'scan_timestamp': self.current_scan_timestamp,
                'bid': option.get('bid', 0.0) or 0.0,
                'ask': option.get('ask', 0.0) or 0.0,
                'last_price': option.get('last', 0.0) or 0.0,
                'iv': greeks.get('smv_vol', 0.0) or option.get('implied_volatility', 0.0) or 0.0,
                'delta': greeks.get('delta', 0.0) or 0.0,
                'gamma': greeks.get('gamma', 0.0) or 0.0,
                'theta': greeks.get('theta', 0.0) or 0.0,
                'vega': greeks.get('vega', 0.0) or 0.0
            }

        except Exception as e:
            # Silently skip - API returned incomplete data (common for low-volume contracts)
            logging.debug("Skipped contract for {} exp {} - incomplete data: {}".format(
                symbol, expiration, str(e)
            ))
            return None
    
    def _fetch_bulk_quotes(self, symbols):
        """Fetch quotes for multiple symbols at once"""
        try:
            self.bulk_quote_cache.clear()
            quotes = self.tradier_client.get_quotes(symbols)
            self.collection_stats['api_calls_made'] += 1
            
            if quotes:
                self.bulk_quote_cache.update(quotes)
                
        except Exception as e:
            logging.error("Bulk quote fetch failed: {}".format(e))
            self.bulk_quote_cache.clear()
    
    def _flush_contract_buffer(self):
        """Batch storage operations with memory monitoring"""
        if not self.contract_buffer:
            return
        
        try:
            buffer_size = len(self.contract_buffer)
            
            # Get unique symbols from buffer for display
            symbols_in_buffer = list(set(contract.get('symbol') for contract in self.contract_buffer if contract.get('symbol')))
            symbols_in_buffer.sort()
            
            # Create symbols display string
            if len(symbols_in_buffer) <= 5:
                symbols_display = ', '.join(symbols_in_buffer)
            else:
                symbols_display = '{}, ... +{} more'.format(', '.join(symbols_in_buffer[:5]), len(symbols_in_buffer) - 5)
            
            # Memory usage monitoring for large buffers
            if buffer_size > 5000:
                estimated_memory_kb = buffer_size * 2  # ~2KB per contract estimate
                logging.warning("Large buffer flush: {} contracts (~{:.1f} MB)".format(
                    buffer_size, estimated_memory_kb / 1024))
            
            result = self.storage.bulk_insert_oi_snapshots(self.contract_buffer)
            
            if result > 0:
                beautiful_log("Flushed {} contracts to storage ({})".format(buffer_size, symbols_display), 'success')
                self.contract_buffer.clear()
            else:
                logging.error("Failed to flush contract buffer ({} contracts from {})".format(buffer_size, symbols_display))
                
        except Exception as e:
            logging.error("Error flushing {} contracts: {}".format(len(self.contract_buffer), e))
    
    def _handle_symbol_error(self, symbol, error):
        """Categorize and log symbol errors"""
        error_str = str(error).lower()
        
        if '429' in error_str or 'rate limit' in error_str:
            category = "RATE_LIMITED"
        elif '401' in error_str or '403' in error_str:
            category = "AUTH_FAILURE"
        elif 'timeout' in error_str or 'connection' in error_str:
            category = "NETWORK_ERROR"
        elif '500' in error_str or 'server error' in error_str:
            category = "SERVER_ERROR"
        elif 'not found' in error_str or '404' in error_str:
            category = "NO_DATA"
        else:
            category = "UNKNOWN"
        
        logging.error("Symbol {} failed [{}]: {}".format(symbol, category, error))
    
    def _log_progress(self, current, total):
        """Beautiful progress logging"""
        progress_pct = (current / total) * 100
        elapsed_time = time.time() - self.collection_stats['start_time']
        
        # Calculate ETA
        if current > 0:
            avg_time_per_symbol = elapsed_time / current
            remaining = total - current
            eta_seconds = remaining * avg_time_per_symbol
            eta = datetime.now() + timedelta(seconds=eta_seconds)
            eta_str = eta.strftime('%H:%M:%S')
        else:
            eta_str = "calculating..."
        
        # Format statistics
        success_rate = (self.collection_stats['successful_symbols'] / 
                       max(self.collection_stats['processed_symbols'], 1)) * 100
        
        logging.info(
            "📊 Progress: {:.1f}% ({}/{}) | "
            "Success: {:.1f}% | "
            "Contracts: {:,} | "
            "API Calls: {} | "
            "ETA: {}".format(
                progress_pct, current, total,
                success_rate,
                self.collection_stats['total_contracts'],
                self.collection_stats['api_calls_made'],
                eta_str
            )
        )
    
    def _log_collection_summary(self):
        """Log final collection statistics"""
        total_time = time.time() - self.collection_stats['start_time']
        minutes = total_time / 60
        
        logging.info("Time: {:.1f} minutes".format(minutes))
        logging.info("Symbols Processed: {}".format(self.collection_stats['processed_symbols']))
        logging.info("Successful: {}".format(self.collection_stats['successful_symbols']))
        logging.info("Failed: {}".format(self.collection_stats['failed_symbols']))
        logging.info("Total Contracts: {:,}".format(self.collection_stats['total_contracts']))
        logging.info("API Calls: {}".format(self.collection_stats['api_calls_made']))
        
        if self.collection_stats['failed_symbol_list']:
            logging.info("Failed Symbols: {}".format(
                ', '.join(self.collection_stats['failed_symbol_list'][:20])
            ))
            if len(self.collection_stats['failed_symbol_list']) > 20:
                logging.info("... and {} more".format(
                    len(self.collection_stats['failed_symbol_list']) - 20
                ))

        # Data quality: no-contract symbols
        no_contract = self.collection_stats['no_contract_symbols']
        if no_contract:
            logging.info("No-Contract Symbols: {} ({})".format(
                len(no_contract), ', '.join(no_contract[:15])))
            if len(no_contract) > 15:
                logging.info("   ... and {} more".format(len(no_contract) - 15))

        # Data quality: OI filter ratio
        total_seen = self.collection_stats['total_options_seen']
        total_filtered = self.collection_stats['total_options_filtered']
        if total_seen > 0:
            filter_pct = (total_filtered / total_seen) * 100
            logging.info("OI Filter: {:,} seen, {:,} filtered ({:.1f}%)".format(
                total_seen, total_filtered, filter_pct))


# Test execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='OID Collector 3.0 - Streamlined Collection')
    parser.add_argument('--symbol', type=str, help='Single symbol test mode')
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Run collection
    collector = OIDCollector()
    
    if args.symbol:
        print("\nStarting single symbol collection for {}".format(args.symbol))
        success = collector.collect_daily_oi(single_symbol=args.symbol)
    else:
        print("\nStarting full universe collection...")
        print("This will collect {} symbols.".format(len(get_specialty_list('klmn_800'))))
        response = input("Continue? (y/n): ")
        
        if response.lower() == 'y':
            success = collector.collect_daily_oi()
        else:
            print("Collection cancelled.")
            sys.exit(0)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)