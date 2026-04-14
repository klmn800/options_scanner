#!/usr/bin/env python3
"""
Tradier API Client (tradier_api.py) - Enhanced with Market Infrastructure
------------------------------------------------------------------------
Pure Tradier API interface with rate limiting, caching, and market timing intelligence.
Enhanced with market calendar, market clock, and symbol discovery capabilities.

NEW FEATURES (Part 7):
- Market Calendar: Trading days, holidays, market hours
- Market Clock: Real-time market status (open/closed/pre/post)
- Options Strikes: Available strike prices for enhanced analysis
- Symbol Search: Company name lookup and discovery
- Enhanced Error Handling: Production-grade reliability

Features:
- Authenticates with Tradier API using access token
- Respects API rate limits using throttling
- Fetches market data (quotes, options chains, expirations)
- Market infrastructure intelligence (calendar, clock, strikes)
- Symbol discovery and validation capabilities
- Basic local caching to minimize API calls
- Handles API errors gracefully with retries
- Clean interface for other modules to use

Author: Ben (with assistance from Claude)
Date: 2025-05-26 (Enhanced: 2025-05-29)
"""

import os
import sys
import json
import time
import logging
import requests
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string

# Rate limit constants (per minute)
MARKET_DATA_RATE_LIMIT = 120
STANDARD_DATA_RATE_LIMIT = 120
TRADING_RATE_LIMIT = 60


class RateLimiter:
    """Manages API request timing to stay within rate limits"""
    
    def __init__(self, requests_per_minute):
        self.requests_per_minute = requests_per_minute
        self.interval = 60 / requests_per_minute  # seconds between requests
        self.last_request_time = 0
    
    def wait_if_needed(self):
        """Wait if necessary to comply with rate limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.interval:
            sleep_time = self.interval - time_since_last
            logging.debug(f"Rate limiting: Waiting {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()


class BasicCache:
    """Simple file-based caching for API responses"""
    
    def __init__(self, cache_dir):
        """Initialize the cache with directory path"""
        self.cache_dir = Path(cache_dir)
        self.quotes_dir = self.cache_dir / 'quotes'
        self.options_dir = self.cache_dir / 'options_chains'
        self.historical_dir = self.cache_dir / 'historical'

        # Create cache directories
        for directory in [self.quotes_dir, self.options_dir, self.historical_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Auto-purge stale files on startup
        self.purge_stale_files()
    
    def purge_stale_files(self, max_age_hours=24):
        """Delete cache files older than max_age_hours. Runs automatically on init."""
        cutoff = time.time() - (max_age_hours * 3600)
        purged = 0
        for directory in [self.quotes_dir, self.options_dir, self.historical_dir]:
            if not directory.exists():
                continue
            for f in directory.iterdir():
                if f.is_file() and f.suffix == '.json':
                    try:
                        if f.stat().st_mtime < cutoff:
                            f.unlink()
                            purged += 1
                    except OSError:
                        pass
        if purged > 0:
            logging.debug(f"Cache cleanup: purged {purged} stale files (>{max_age_hours}h old)")

    def get_cache_path(self, data_type, symbol, suffix=None):
            """Get file path for cached data"""
            if data_type == 'quotes':
                return self.quotes_dir / f"{symbol}.json"
            elif data_type == 'options':
                if suffix:  # Use expiration date as suffix
                    return self.options_dir / f"{symbol}_{suffix}.json"
                else:
                    return self.options_dir / f"{symbol}.json"
            elif data_type == 'expirations':
                return self.options_dir / f"{symbol}_expirations.json"
            elif data_type == 'historical':
                if suffix:  # Use interval as suffix
                    return self.historical_dir / f"{symbol}_{suffix}.json"
                else:
                    return self.historical_dir / f"{symbol}_daily.json"
            elif data_type == 'company_info':
                return self.cache_dir / f"{symbol}_info.json"
            elif data_type == 'market_sentiment':
                if suffix:
                    return self.cache_dir / f"{symbol}_{suffix}.json"
                else:
                    return self.cache_dir / f"{symbol}_sentiment.json"
            elif data_type == 'market_status':
                return self.cache_dir / f"market_status_{symbol}.json"
            elif data_type == 'market_calendar':
                return self.cache_dir / f"market_calendar_{symbol}.json"
            elif data_type == 'symbol_search':
                return self.cache_dir / f"symbol_search_{symbol}.json"
            elif data_type == 'symbol_validation':
                return self.cache_dir / f"symbol_validation_{symbol}.json"
            else:
                # Fallback for unknown types
                return self.cache_dir / f"{data_type}_{symbol}.json"
    
    def is_cache_valid(self, cache_path, max_age_seconds):
        """Check if cached data is still valid"""
        if not cache_path.exists():
            return False
        
        file_age = time.time() - cache_path.stat().st_mtime
        return file_age < max_age_seconds
    
    def save_to_cache(self, data_type, symbol, data, suffix=None):
        """Save data to cache file"""
        cache_path = self.get_cache_path(data_type, symbol, suffix)
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': time.time(),
                    'data': data
                }, f)
            logging.debug(f"Cached {data_type} data for {symbol}")
            return True
        except Exception as e:
            logging.error(f"Failed to cache {data_type} data for {symbol}: {e}")
            return False
    
    def load_from_cache(self, data_type, symbol, max_age_seconds, suffix=None):
        """Load data from cache if valid"""
        cache_path = self.get_cache_path(data_type, symbol, suffix)
        
        if self.is_cache_valid(cache_path, max_age_seconds):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                logging.debug(f"Loaded {data_type} data for {symbol} from cache")
                return cached['data']
            except Exception as e:
                logging.error(f"Failed to load {data_type} cache for {symbol}: {e}")
        
        return None


class TradierAPI:
    """Core Tradier API client with rate limiting and error handling"""
    
    def __init__(self, token, sandbox=False):
        """Initialize the API client with authentication token"""
        self.token = token
        self.sandbox = sandbox
        
        # Set API endpoints based on environment
        if sandbox:
            self.base_url = "https://sandbox.tradier.com/v1"
        else:
            self.base_url = "https://api.tradier.com/v1"
        
        # Set up rate limiters for different API categories
        self.market_data_limiter = RateLimiter(MARKET_DATA_RATE_LIMIT)
        self.standard_data_limiter = RateLimiter(STANDARD_DATA_RATE_LIMIT)
        self.trading_limiter = RateLimiter(TRADING_RATE_LIMIT)
        
        # Request tracking
        self.total_requests = 0
        self.requests_by_endpoint = {}
        self.requests_by_method = {'GET': 0, 'POST': 0}
        
        # Set up session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json'
        })
    
    def _handle_response(self, response):
        """Process API response and handle errors"""
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            logging.warning(f"Rate limit exceeded. Waiting {retry_after} seconds.")
            time.sleep(retry_after)
            return None
        else:
            logging.error(f"API error for {response.url}: {response.status_code} - {response.text[:200]}")
            return None
    
    def _make_request(self, method, endpoint, limiter, params=None, data=None):
        """Make an API request with rate limiting and error handling"""
        url = f"{self.base_url}/{endpoint}"
        
        # Track the request BEFORE making it
        self.total_requests += 1
        self.requests_by_method[method.upper()] += 1
        
        # Extract endpoint name for tracking
        endpoint_name = endpoint.split('/')[-1]  # Get last part of endpoint
        self.requests_by_endpoint[endpoint_name] = self.requests_by_endpoint.get(endpoint_name, 0) + 1
        
        # Apply rate limiting
        limiter.wait_if_needed()
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params)
            elif method.upper() == 'POST':
                response = self.session.post(url, params=params, data=data)
            else:
                logging.error(f"Unsupported HTTP method: {method}")
                return None
            
            return self._handle_response(response)
        
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
            return None
    
    def test_connection(self):
        """Test API connection and authentication"""
        try:
            response = self._make_request('GET', 'user/profile', self.standard_data_limiter)
            return response is not None
        except Exception as e:
            logging.error(f"Connection test failed: {e}")
            return False
    
    # Market Data Endpoints
    
    def get_quotes(self, symbols):
        """Get quotes for one or more symbols"""
        if isinstance(symbols, list):
            symbols = ','.join(symbols)
        
        endpoint = "markets/quotes"
        params = {'symbols': symbols}
        
        return self._make_request('GET', endpoint, self.market_data_limiter, params)
    
    def get_option_chains(self, symbol, expiration=None):
        """Get option chain for a symbol and expiration date"""
        endpoint = "markets/options/chains"
        
        params = {
            'symbol': symbol,
            'greeks': 'true'
        }
        
        if expiration:
            params['expiration'] = expiration
        
        return self._make_request('GET', endpoint, self.market_data_limiter, params)
    
    def get_option_expirations(self, symbol):
        """Get available option expiration dates for a symbol"""
        endpoint = "markets/options/expirations"
        params = {'symbol': symbol}
        
        return self._make_request('GET', endpoint, self.market_data_limiter, params)
    
    def get_historical_quotes(self, symbol, interval='daily', start_date=None, end_date=None):
        """Get historical price data for a symbol"""
        endpoint = "markets/history"
        params = {
            'symbol': symbol,
            'interval': interval
        }
        
        if start_date:
            params['start'] = start_date
        
        if end_date:
            params['end'] = end_date
        
        return self._make_request('GET', endpoint, self.market_data_limiter, params)
    
    def get_company_info(self, symbol):
        """Get company information for a symbol"""
        endpoint = f"markets/lookup"
        params = {'q': symbol, 'types': 'stock'}
        
        return self._make_request('GET', endpoint, self.standard_data_limiter, params)

    def get_options_lookup(self, symbol):
        """Get all available option symbols for an underlying"""
        endpoint = "markets/options/lookup"
        params = {'underlying': symbol}
        
        return self._make_request('GET', endpoint, self.market_data_limiter, params)

    # Market Infrastructure Endpoints (NEW - Part 7)
    
    def get_market_calendar(self, month=None, year=None):
        """Get market calendar with trading days and holidays
        
        Args:
            month: Month number (1-12), defaults to current month
            year: Year (YYYY), defaults to current year
            
        Returns:
            Dict with calendar data including trading days and holidays
        """
        endpoint = "markets/calendar"
        params = {}
        
        if month:
            params['month'] = month
        if year:
            params['year'] = year
            
        return self._make_request('GET', endpoint, self.standard_data_limiter, params)
    
    def get_market_clock(self):
        """Get real-time market status and session information
        
        Returns:
            Dict with current market status (open/closed/pre-market/after-hours)
        """
        endpoint = "markets/clock"
        return self._make_request('GET', endpoint, self.market_data_limiter)
    
    def get_option_strikes(self, symbol, expiration):
        """Get available strike prices for a symbol and expiration
        
        Args:
            symbol: Underlying symbol
            expiration: Expiration date (YYYY-MM-DD)
            
        Returns:
            Dict with available strike prices
        """
        endpoint = "markets/options/strikes"
        params = {
            'symbol': symbol,
            'expiration': expiration
        }
        
        return self._make_request('GET', endpoint, self.market_data_limiter, params)
    
    def search_companies(self, query, types=None):
        """Search companies by name
        
        Args:
            query: Company name or partial name to search
            types: Optional list of security types ('stock', 'etf', etc.)
            
        Returns:
            Dict with search results
        """
        endpoint = "markets/search"
        params = {'q': query}
        
        if types:
            if isinstance(types, list):
                params['types'] = ','.join(types)
            else:
                params['types'] = types
                
        return self._make_request('GET', endpoint, self.standard_data_limiter, params)
    
    def get_symbol_lookup(self, query, exchanges=None):
        """Advanced symbol validation and lookup
        
        Args:
            query: Symbol or company name to lookup
            exchanges: Optional list of exchanges to filter by
            
        Returns:
            Dict with symbol lookup results
        """
        endpoint = "markets/lookup"
        params = {'q': query}
        
        if exchanges:
            if isinstance(exchanges, list):
                params['exchanges'] = ','.join(exchanges)
            else:
                params['exchanges'] = exchanges
                
        return self._make_request('GET', endpoint, self.standard_data_limiter, params)


class TradierDataClient:
    """High-level client that combines API calls with caching"""
    
    def __init__(self, config, cache_dir):
        """Initialize with config and cache directory"""
        self.config = config
        self.token = config['tradier']['api_key']
        self.base_url = "https://api.tradier.com"
        self.cache = BasicCache(cache_dir)
        
        # Initialize API client
        token = self.config.get('tradier', {}).get('api_key')
        if not token:
            raise ValueError("Tradier API key not found in configuration")
        
        sandbox = self.config.get('tradier', {}).get('sandbox', False)
        self.api = TradierAPI(token, sandbox)
    
    def test_connection(self):
        """Test connection to Tradier API"""
        return self.api.test_connection()
    
    def get_quotes(self, symbols, max_age_seconds=30):
        """Get quotes for symbols with caching"""
        if isinstance(symbols, str):
            symbols = [symbols]
        
        results = {}
        symbols_to_fetch = []
        
        # Try loading from cache first
        for symbol in symbols:
            cached_data = self.cache.load_from_cache('quotes', symbol, max_age_seconds)
            if cached_data:
                results[symbol] = cached_data
            else:
                symbols_to_fetch.append(symbol)
        
        # Fetch any symbols not in cache
        if symbols_to_fetch:
            logging.debug(f"Fetching quotes for {len(symbols_to_fetch)} symbols")
            
            # Split into batches of 25 to avoid URL length limits
            batch_size = 25
            for i in range(0, len(symbols_to_fetch), batch_size):
                batch = symbols_to_fetch[i:i+batch_size]
                response = self.api.get_quotes(batch)
                
                if response and 'quotes' in response:
                    quotes = response['quotes']
                    
                    # Handle single quote response
                    if 'quote' in quotes and not isinstance(quotes['quote'], list):
                        quote = quotes['quote']
                        symbol = quote['symbol']
                        results[symbol] = quote
                        self.cache.save_to_cache('quotes', symbol, quote)
                    
                    # Handle multiple quotes
                    elif 'quote' in quotes and isinstance(quotes['quote'], list):
                        for quote in quotes['quote']:
                            symbol = quote['symbol']
                            results[symbol] = quote
                            self.cache.save_to_cache('quotes', symbol, quote)
        
        return results
    
    def get_option_expirations(self, symbol, max_age_seconds=57600):
        """Get option expiration dates for a symbol with caching"""
        cached_data = self.cache.load_from_cache('expirations', symbol, max_age_seconds)
        
        if cached_data:
            return cached_data
        
        logging.info(f"Fetching option expirations for {symbol}")
        response = self.api.get_option_expirations(symbol)
        
        if response and 'expirations' in response:
            expirations = response['expirations']
            self.cache.save_to_cache('expirations', symbol, expirations)
            return expirations
        
        return None
    
    def get_option_chain(self, symbol, expiration=None, max_age_seconds=300):
        """Get option chain for a symbol and expiration with caching"""
        # If no expiration provided, get the nearest one
        if not expiration:
            expirations = self.get_option_expirations(symbol)
            if expirations and 'date' in expirations and len(expirations['date']) > 0:
                if isinstance(expirations['date'], list):
                    expiration = expirations['date'][0]
                else:
                    expiration = expirations['date']
            else:
                logging.error(f"No option expirations found for {symbol}")
                return None
        
        # Check cache
        cached_data = self.cache.load_from_cache('options', symbol, max_age_seconds, expiration)
        
        if cached_data:
            return cached_data

        # Note: Logging moved to caller (fm_collector.py) to avoid duplicate log entries
        response = self.api.get_option_chains(symbol, expiration)
        
        if response and 'options' in response:
            options = response['options']
            self.cache.save_to_cache('options', symbol, options, expiration)
            return options
        
        return None

    def get_contract_greeks(self, symbol, strike, expiration, option_type):
        """Fetch current Greeks for a single option contract.

        Fetches the full chain (cached 5min) and filters to the matching
        contract by strike and option_type.

        Args:
            symbol: Stock symbol (e.g. 'TOST')
            strike: Strike price (float, e.g. 30.0)
            expiration: Expiration date string 'YYYY-MM-DD'
            option_type: 'CALL' or 'PUT'

        Returns:
            dict with delta, gamma, theta, vega, iv, bid, ask, last_price,
            underlying_price — or None if not found.
        """
        chain_data = self.get_option_chain(symbol, expiration)
        if not chain_data:
            return None

        # Normalize chain to list of option dicts
        if isinstance(chain_data, list):
            options = chain_data
        elif isinstance(chain_data, dict) and 'option' in chain_data:
            options = chain_data['option']
            if isinstance(options, dict):
                options = [options]
        else:
            return None

        # Filter to matching strike + type
        strike = float(strike)
        option_type = option_type.upper()
        for opt in options:
            opt_strike = float(opt.get('strike', 0))
            opt_type = (opt.get('option_type') or '').upper()
            if abs(opt_strike - strike) < 0.01 and opt_type == option_type:
                greeks = opt.get('greeks') or {}

                # Fetch underlying stock price via quote API
                # (chain 'underlying' field is the symbol name, not the price)
                underlying_price = 0.0
                quote_data = self.get_quotes(symbol)
                if quote_data and symbol in quote_data:
                    q = quote_data[symbol]
                    underlying_price = float(q.get('last', 0.0) or 0.0)

                return {
                    'delta': greeks.get('delta', 0.0) or 0.0,
                    'gamma': greeks.get('gamma', 0.0) or 0.0,
                    'vega': greeks.get('vega', 0.0) or 0.0,
                    'theta': greeks.get('theta', 0.0) or 0.0,
                    'iv': greeks.get('smv_vol', 0.0) or 0.0,
                    'bid': opt.get('bid', 0.0) or 0.0,
                    'ask': opt.get('ask', 0.0) or 0.0,
                    'last_price': opt.get('last', 0.0) or 0.0,
                    'underlying_price': underlying_price,
                }

        return None

    def get_historical_data(self, symbol, interval='daily', days=30, max_age_seconds=3600*4):
        """Get historical price data with caching"""
        end_date = now_eastern().strftime('%Y-%m-%d')
        start_date = (now_eastern() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        cached_data = self.cache.load_from_cache('historical', symbol, max_age_seconds, interval)
        
        if cached_data:
            return cached_data
        
        logging.info(f"Fetching {interval} historical data for {symbol} from {start_date} to {end_date}")
        response = self.api.get_historical_quotes(symbol, interval, start_date, end_date)
        
        if response and 'history' in response:
            history = response['history']
            self.cache.save_to_cache('historical', symbol, history, interval)
            return history
        
        return None
    
    def get_company_info(self, symbol, max_age_seconds=3600*24):
        """Get company information with caching"""
        cached_data = self.cache.load_from_cache('company_info', symbol, max_age_seconds)
        
        if cached_data:
            return cached_data
        
        logging.info(f"Fetching company info for {symbol}")
        response = self.api.get_company_info(symbol)
        
        if response:
            self.cache.save_to_cache('company_info', symbol, response)
            return response
        
        return None

    def get_options_lookup(self, symbol, max_age_seconds=3600):
        """Get all available option symbols for an underlying with caching"""
        cache_suffix = "lookup_all"
        
        cached_data = self.cache.load_from_cache('options', symbol, max_age_seconds, cache_suffix)
        
        if cached_data:
            return cached_data
        
        logging.info(f"Fetching option symbols lookup for {symbol}")
        response = self.api.get_options_lookup(symbol)
        
        if response and 'symbols' in response:
            symbols_list = response['symbols']  # This is a list
            
            # Extract the options from the first (and usually only) symbol group
            if symbols_list and len(symbols_list) > 0:
                symbol_group = symbols_list[0]  # Get first group
                if 'options' in symbol_group:
                    options_list = symbol_group['options']  # Extract the actual options list
                    
                    # Return in the format our code expects
                    result = {
                        'symbol': options_list,
                        'rootSymbol': symbol_group.get('rootSymbol', symbol),
                        'optionCount': len(options_list)
                    }
                    
                    self.cache.save_to_cache('options', symbol, result, cache_suffix)
                    return result
        
        return None
    
    def search_options_by_criteria(self, symbol, criteria=None, max_age_seconds=300):
        """Search options by volume/activity criteria using option chains"""
        # Get all expirations for the symbol
        expirations = self.get_option_expirations(symbol)
        if not expirations or 'date' not in expirations:
            return None
        
        exp_dates = expirations['date']
        if not isinstance(exp_dates, list):
            exp_dates = [exp_dates]
        
        # Filter for nearby expirations (within 60 days)
        from datetime import datetime, timedelta
        cutoff_date = now_eastern() + timedelta(days=60)
        
        filtered_options = []
        
        # Search through each expiration
        for expiration in exp_dates[:5]:  # Limit to first 5 expirations to avoid too many API calls
            try:
                exp_date = datetime.strptime(expiration, '%Y-%m-%d')
                if exp_date > cutoff_date:
                    continue
                    
                # Get option chain for this expiration
                options_data = self.get_option_chain(symbol, expiration, max_age_seconds)
                
                if options_data and 'option' in options_data:
                    options_list = options_data['option']
                    if not isinstance(options_list, list):
                        options_list = [options_list]
                    
                    # Apply criteria filters
                    for option in options_list:
                        if self._meets_criteria(option, criteria):
                            filtered_options.append(option)
                            
            except (ValueError, TypeError) as e:
                logging.debug(f"Error processing expiration {expiration}: {e}")
                continue
        
        return filtered_options
    
    def _meets_criteria(self, option, criteria):
        """Check if an option meets the specified criteria"""
        if not criteria:
            return True
        
        try:
            volume = option.get('volume', 0) or 0
            open_interest = option.get('open_interest', 0) or 0
            option_type = option.get('option_type', '').lower()
            
            # Check minimum volume
            if 'min_volume' in criteria and volume < criteria['min_volume']:
                return False
            
            # Check minimum open interest
            if 'min_oi' in criteria and open_interest < criteria['min_oi']:
                return False
            
            # Check option type
            if 'option_type' in criteria:
                required_type = criteria['option_type'].lower()
                if required_type and option_type != required_type:
                    return False
            
            return True
            
        except Exception as e:
            logging.debug(f"Error checking criteria for option: {e}")
            return False
    
    def get_individual_option_quotes(self, option_symbols, max_age_seconds=60):
        """Get detailed quotes for specific option symbols with caching"""
        if isinstance(option_symbols, str):
            option_symbols = [option_symbols]
        
        results = {}
        symbols_to_fetch = []
        
        # Try loading from cache first
        for option_symbol in option_symbols:
            cached_data = self.cache.load_from_cache('quotes', option_symbol, max_age_seconds)
            if cached_data:
                results[option_symbol] = cached_data
            else:
                symbols_to_fetch.append(option_symbol)
        
        # Fetch any symbols not in cache
        if symbols_to_fetch:
            logging.info(f"Fetching individual option quotes for {len(symbols_to_fetch)} options")
            
            # Split into batches of 25 to avoid URL length limits
            batch_size = 25
            for i in range(0, len(symbols_to_fetch), batch_size):
                batch = symbols_to_fetch[i:i+batch_size]
                response = self.api.get_quotes(batch)
                
                if response and 'quotes' in response:
                    quotes = response['quotes']
                    
                    # Handle single quote response
                    if 'quote' in quotes and not isinstance(quotes['quote'], list):
                        quote = quotes['quote']
                        symbol = quote['symbol']
                        results[symbol] = quote
                        self.cache.save_to_cache('quotes', symbol, quote)
                    
                    # Handle multiple quotes
                    elif 'quote' in quotes and isinstance(quotes['quote'], list):
                        for quote in quotes['quote']:
                            symbol = quote['symbol']
                            results[symbol] = quote
                            self.cache.save_to_cache('quotes', symbol, quote)
        
        return results

    def get_fundamentals(self, symbol):
        """Fetch fundamental data for a symbol using Tradier's /markets/fundamentals/company endpoint."""
        import requests

        url = f"{self.base_url}/v1/markets/fundamentals/company"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
        params = {"symbols": symbol}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code != 200:
                return None
            data = response.json()
            return data.get("results", {}).get(symbol, {})
        except Exception as e:
            print(f"[!] Error fetching fundamentals for {symbol}: {e}")
            return None

     
    def get_market_options_sentiment(self, symbols=None, max_age_seconds=300):
        """
        Get market-wide options sentiment data by analyzing key market indicators
        
        Args:
            symbols: List of symbols to analyze (defaults to major market indicators)
            max_age_seconds: Cache age limit
            
        Returns:
            Dict with sentiment indicators including put/call ratios, VIX data, etc.
        """
        # Default symbols for market sentiment analysis
        if symbols is None:
            symbols = [
                'SPY',   # S&P 500 ETF
                'QQQ',   # NASDAQ ETF  
                'IWM',   # Russell 2000 ETF
                'VIX',   # Volatility Index
                'GLD',   # Gold ETF
                'TLT'    # Treasury ETF
            ]
        
        # Check cache first
        cache_key = "market_sentiment_" + "_".join(sorted(symbols))
        cached_data = self.cache.load_from_cache('market_sentiment', cache_key, max_age_seconds, suffix="summary")
        
        if cached_data:
            return cached_data
        
        logging.info(f"Calculating market options sentiment for {len(symbols)} symbols")
        
        sentiment_data = {
            'timestamp': eastern_isoformat(),
            'symbols_analyzed': symbols,
            'market_indicators': {},
            'sentiment_summary': {},
            'put_call_analysis': {}
        }
        
        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0
        
        # Analyze each symbol
        for symbol in symbols:
            try:
                symbol_data = self._analyze_symbol_sentiment(symbol, max_age_seconds)
                if symbol_data:
                    sentiment_data['market_indicators'][symbol] = symbol_data
                    
                    # Aggregate totals
                    total_call_volume += symbol_data.get('call_volume', 0)
                    total_put_volume += symbol_data.get('put_volume', 0)
                    total_call_oi += symbol_data.get('call_open_interest', 0)
                    total_put_oi += symbol_data.get('put_open_interest', 0)
                    
            except Exception as e:
                logging.warning(f"Error analyzing sentiment for {symbol}: {e}")
                continue
        
        # Calculate aggregate sentiment metrics
        sentiment_data['put_call_analysis'] = {
            'total_call_volume': total_call_volume,
            'total_put_volume': total_put_volume,
            'total_call_oi': total_call_oi,
            'total_put_oi': total_put_oi,
            'volume_put_call_ratio': total_put_volume / max(total_call_volume, 1),
            'oi_put_call_ratio': total_put_oi / max(total_call_oi, 1)
        }
        
        # Generate sentiment summary
        sentiment_data['sentiment_summary'] = self._generate_sentiment_summary(sentiment_data)
        
        # Cache the results
        self.cache.save_to_cache('market_sentiment', cache_key, sentiment_data, suffix="summary")
        
        return sentiment_data
    
    def _analyze_symbol_sentiment(self, symbol, max_age_seconds):
        """Analyze options sentiment for a single symbol"""
        try:
            # Get recent expirations (next 30 days)
            expirations = self.get_option_expirations(symbol)
            if not expirations or 'date' not in expirations:
                return None
            
            exp_dates = expirations['date']
            if not isinstance(exp_dates, list):
                exp_dates = [exp_dates]
            
            # Filter for nearby expirations
            from datetime import datetime, timedelta
            cutoff_date = now_eastern() + timedelta(days=30)
            
            call_volume = 0
            put_volume = 0
            call_oi = 0
            put_oi = 0
            total_options = 0
            
            # Analyze first 3 expirations to avoid too many API calls
            for expiration in exp_dates[:3]:
                try:
                    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
                    if exp_date > cutoff_date:
                        continue
                    
                    # Get option chain
                    options_data = self.get_option_chain(symbol, expiration, max_age_seconds)
                    
                    if options_data and 'option' in options_data:
                        options_list = options_data['option']
                        if not isinstance(options_list, list):
                            options_list = [options_list]
                        
                        for option in options_list:
                            total_options += 1
                            option_type = option.get('option_type', '').lower()
                            volume = option.get('volume', 0) or 0
                            oi = option.get('open_interest', 0) or 0
                            
                            if option_type == 'call':
                                call_volume += volume
                                call_oi += oi
                            elif option_type == 'put':
                                put_volume += volume
                                put_oi += oi
                
                except (ValueError, TypeError) as e:
                    logging.debug(f"Error processing expiration {expiration} for {symbol}: {e}")
                    continue
            
            # Calculate ratios and return data
            return {
                'symbol': symbol,
                'call_volume': call_volume,
                'put_volume': put_volume,
                'call_open_interest': call_oi,
                'put_open_interest': put_oi,
                'total_volume': call_volume + put_volume,
                'total_open_interest': call_oi + put_oi,
                'volume_put_call_ratio': put_volume / max(call_volume, 1),
                'oi_put_call_ratio': put_oi / max(call_oi, 1),
                'total_options_analyzed': total_options
            }
            
        except Exception as e:
            logging.error(f"Error in symbol sentiment analysis for {symbol}: {e}")
            return None
    
    def _generate_sentiment_summary(self, sentiment_data):
        """Generate human-readable sentiment summary"""
        pc_analysis = sentiment_data['put_call_analysis']
        volume_pc_ratio = pc_analysis.get('volume_put_call_ratio', 0)
        oi_pc_ratio = pc_analysis.get('oi_put_call_ratio', 0)
        
        summary = {
            'overall_sentiment': 'neutral',
            'confidence': 'medium',
            'key_indicators': [],
            'notable_observations': []
        }
        
        # Analyze volume-based sentiment
        if volume_pc_ratio > 1.2:
            summary['overall_sentiment'] = 'bearish'
            summary['key_indicators'].append(f"High put/call volume ratio: {volume_pc_ratio:.2f}")
        elif volume_pc_ratio < 0.7:
            summary['overall_sentiment'] = 'bullish'
            summary['key_indicators'].append(f"Low put/call volume ratio: {volume_pc_ratio:.2f}")
        else:
            summary['key_indicators'].append(f"Neutral put/call volume ratio: {volume_pc_ratio:.2f}")
        
        # Analyze open interest sentiment
        if oi_pc_ratio > 1.1:
            summary['notable_observations'].append("Put open interest dominance suggests defensive positioning")
        elif oi_pc_ratio < 0.8:
            summary['notable_observations'].append("Call open interest dominance suggests bullish positioning")
        
        # Check for VIX levels if available
        if 'VIX' in sentiment_data['market_indicators']:
            vix_data = sentiment_data['market_indicators']['VIX']
            vix_volume = vix_data.get('total_volume', 0)
            if vix_volume > 1000:
                summary['notable_observations'].append("High VIX options volume indicates volatility concerns")
        
        # Set confidence based on data quality
        total_symbols = len(sentiment_data['market_indicators'])
        if total_symbols >= 4:
            summary['confidence'] = 'high'
        elif total_symbols >= 2:
            summary['confidence'] = 'medium'
        else:
            summary['confidence'] = 'low'
        
        return summary

    def get_enhanced_greeks(self, symbol, expiration=None, max_age_seconds=300):
        """
        Get comprehensive Greeks data with enhanced analysis for risk management
        
        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            expiration: Specific expiration date (if None, gets nearest expiration)
            max_age_seconds: Cache age limit
            
        Returns:
            Dict with enhanced Greeks analysis including risk metrics and hedging ratios
        """
        # Get option chain with Greeks
        options_data = self.get_option_chain(symbol, expiration, max_age_seconds)
        
        if not options_data or 'option' not in options_data:
            logging.warning(f"No options data found for {symbol} expiration {expiration}")
            return None
        
        options_list = options_data['option']
        if not isinstance(options_list, list):
            options_list = [options_list]
        
        # Get current underlying price for moneyness calculations
        quotes = self.get_quotes(symbol)
        if not quotes or symbol not in quotes:
            logging.warning(f"Could not get current price for {symbol}")
            underlying_price = None
        else:
            underlying_price = quotes[symbol].get('last', 0)
        
        logging.info(f"Analyzing Greeks for {len(options_list)} {symbol} options")
        
        enhanced_data = {
            'symbol': symbol,
            'expiration': expiration,
            'underlying_price': underlying_price,
            'timestamp': eastern_isoformat(),
            'total_options': len(options_list),
            'options_with_greeks': 0,
            'call_greeks_summary': {},
            'put_greeks_summary': {},
            'risk_metrics': {},
            'hedging_analysis': {},
            'detailed_options': []
        }
        
        call_options = []
        put_options = []
        
        # Process each option and extract Greeks
        for option in options_list:
            try:
                enhanced_option = self._process_option_greeks(option, underlying_price)
                if enhanced_option and enhanced_option.get('has_greeks'):
                    enhanced_data['options_with_greeks'] += 1
                    enhanced_data['detailed_options'].append(enhanced_option)
                    
                    if enhanced_option['option_type'] == 'call':
                        call_options.append(enhanced_option)
                    else:
                        put_options.append(enhanced_option)
                        
            except Exception as e:
                logging.debug(f"Error processing option {option.get('symbol', 'unknown')}: {e}")
                continue
        
        # Calculate aggregated Greeks summaries
        enhanced_data['call_greeks_summary'] = self._calculate_greeks_summary(call_options, 'call')
        enhanced_data['put_greeks_summary'] = self._calculate_greeks_summary(put_options, 'put')
        
        # Calculate risk metrics
        enhanced_data['risk_metrics'] = self._calculate_risk_metrics(call_options + put_options, underlying_price)
        
        # Generate hedging analysis
        enhanced_data['hedging_analysis'] = self._generate_hedging_analysis(enhanced_data)
        
        return enhanced_data
    
    def _process_option_greeks(self, option, underlying_price):
        """Process individual option Greeks and calculate enhanced metrics"""
        try:
            greeks = option.get('greeks', {})
            if not greeks:
                return {'has_greeks': False}
            
            strike = option.get('strike', 0)
            option_type = option.get('option_type', '').lower()
            last_price = option.get('last', 0) or 0
            volume = option.get('volume', 0) or 0
            open_interest = option.get('open_interest', 0) or 0
            
            # Extract Greeks
            delta = greeks.get('delta', 0) or 0
            gamma = greeks.get('gamma', 0) or 0
            theta = greeks.get('theta', 0) or 0
            vega = greeks.get('vega', 0) or 0
            rho = greeks.get('rho', 0) or 0
            
            # Calculate moneyness if we have underlying price
            moneyness = 0
            distance_from_money = 0
            if underlying_price and strike:
                if option_type == 'call':
                    moneyness = (underlying_price - strike) / strike * 100
                else:  # put
                    moneyness = (strike - underlying_price) / strike * 100
                distance_from_money = abs(underlying_price - strike)
            
            # Calculate risk-adjusted metrics
            gamma_risk = abs(gamma * underlying_price * underlying_price * 0.01)  # 1% move risk
            theta_decay_daily = theta  # Theta is already per day
            vega_risk = abs(vega * 0.01)  # 1 vol point risk
            
            # Liquidity assessment
            liquidity_score = self._calculate_liquidity_score(volume, open_interest, last_price)
            
            return {
                'has_greeks': True,
                'symbol': option.get('symbol', ''),
                'option_type': option_type,
                'strike': strike,
                'last_price': last_price,
                'volume': volume,
                'open_interest': open_interest,
                'moneyness': moneyness,
                'distance_from_money': distance_from_money,
                'greeks': {
                    'delta': delta,
                    'gamma': gamma,
                    'theta': theta,
                    'vega': vega,
                    'rho': rho
                },
                'risk_metrics': {
                    'gamma_risk_1pct': gamma_risk,
                    'theta_decay_daily': theta_decay_daily,
                    'vega_risk_1vol': vega_risk,
                    'liquidity_score': liquidity_score
                }
            }
            
        except Exception as e:
            logging.debug(f"Error processing option Greeks: {e}")
            return {'has_greeks': False}
    
    def _calculate_liquidity_score(self, volume, open_interest, price):
        """Calculate a liquidity score from 0-10 based on volume, OI, and price"""
        try:
            # Base score from volume and open interest
            volume_score = min(volume / 100, 5)  # Max 5 points for volume >= 100
            oi_score = min(open_interest / 500, 3)  # Max 3 points for OI >= 500
            
            # Bonus points for higher price (usually more liquid)
            price_bonus = min(price / 10, 2)  # Max 2 points for price >= $10
            
            total_score = volume_score + oi_score + price_bonus
            return min(total_score, 10)  # Cap at 10
            
        except Exception:
            return 0
    
    def _calculate_greeks_summary(self, options_list, option_type):
        """Calculate summary statistics for Greeks"""
        if not options_list:
            return {}
        
        try:
            # Aggregate Greeks
            total_delta = sum(opt['greeks']['delta'] for opt in options_list)
            total_gamma = sum(opt['greeks']['gamma'] for opt in options_list)
            total_theta = sum(opt['greeks']['theta'] for opt in options_list)
            total_vega = sum(opt['greeks']['vega'] for opt in options_list)
            
            # Volume-weighted averages
            total_volume = sum(opt['volume'] for opt in options_list)
            if total_volume > 0:
                vol_weighted_delta = sum(opt['greeks']['delta'] * opt['volume'] for opt in options_list) / total_volume
                vol_weighted_gamma = sum(opt['greeks']['gamma'] * opt['volume'] for opt in options_list) / total_volume
            else:
                vol_weighted_delta = 0
                vol_weighted_gamma = 0
            
            # Find extremes
            max_gamma_option = max(options_list, key=lambda x: abs(x['greeks']['gamma']))
            max_theta_option = max(options_list, key=lambda x: abs(x['greeks']['theta']))
            
            return {
                'option_type': option_type,
                'total_options': len(options_list),
                'total_volume': total_volume,
                'aggregate_greeks': {
                    'total_delta': total_delta,
                    'total_gamma': total_gamma,
                    'total_theta': total_theta,
                    'total_vega': total_vega
                },
                'volume_weighted_greeks': {
                    'delta': vol_weighted_delta,
                    'gamma': vol_weighted_gamma
                },
                'risk_concentrations': {
                    'max_gamma_strike': max_gamma_option['strike'],
                    'max_gamma_value': max_gamma_option['greeks']['gamma'],
                    'max_theta_strike': max_theta_option['strike'],
                    'max_theta_value': max_theta_option['greeks']['theta']
                }
            }
            
        except Exception as e:
            logging.error(f"Error calculating Greeks summary: {e}")
            return {}
    
    def _calculate_risk_metrics(self, all_options, underlying_price):
        """Calculate portfolio-level risk metrics"""
        if not all_options or not underlying_price:
            return {}
        
        try:
            # Calculate aggregate exposures
            total_delta_exposure = sum(opt['greeks']['delta'] * opt['volume'] for opt in all_options)
            total_gamma_exposure = sum(opt['greeks']['gamma'] * opt['volume'] for opt in all_options)
            total_theta_exposure = sum(opt['greeks']['theta'] * opt['volume'] for opt in all_options)
            total_vega_exposure = sum(opt['greeks']['vega'] * opt['volume'] for opt in all_options)
            
            # Calculate risk scenarios
            underlying_move_1pct = underlying_price * 0.01
            delta_pnl_1pct = total_delta_exposure * underlying_move_1pct
            gamma_pnl_1pct = 0.5 * total_gamma_exposure * (underlying_move_1pct ** 2)
            
            # Time decay risk (1 day)
            time_decay_1day = total_theta_exposure
            
            # Volatility risk (1 vol point)
            vol_risk_1pt = total_vega_exposure * 0.01
            
            return {
                'total_exposures': {
                    'delta': total_delta_exposure,
                    'gamma': total_gamma_exposure,
                    'theta': total_theta_exposure,
                    'vega': total_vega_exposure
                },
                'risk_scenarios': {
                    'underlying_move_1pct': underlying_move_1pct,
                    'delta_pnl_1pct_move': delta_pnl_1pct,
                    'gamma_pnl_1pct_move': gamma_pnl_1pct,
                    'total_pnl_1pct_move': delta_pnl_1pct + gamma_pnl_1pct,
                    'time_decay_1day': time_decay_1day,
                    'vol_risk_1pt': vol_risk_1pt
                }
            }
            
        except Exception as e:
            logging.error(f"Error calculating risk metrics: {e}")
            return {}
    
    def _generate_hedging_analysis(self, enhanced_data):
        """Generate hedging recommendations and analysis"""
        try:
            risk_metrics = enhanced_data.get('risk_metrics', {})
            call_summary = enhanced_data.get('call_greeks_summary', {})
            put_summary = enhanced_data.get('put_greeks_summary', {})
            
            if not risk_metrics:
                return {}
            
            total_exposures = risk_metrics.get('total_exposures', {})
            risk_scenarios = risk_metrics.get('risk_scenarios', {})
            
            hedging_analysis = {
                'delta_neutrality': {},
                'gamma_risk_assessment': {},
                'time_decay_impact': {},
                'volatility_sensitivity': {},
                'hedging_recommendations': []
            }
            
            # Delta neutrality analysis
            total_delta = total_exposures.get('delta', 0)
            if abs(total_delta) > 100:
                hedging_analysis['delta_neutrality'] = {
                    'status': 'high_exposure',
                    'net_delta': total_delta,
                    'hedge_shares_needed': -total_delta,
                    'hedge_cost_estimate': abs(total_delta) * enhanced_data.get('underlying_price', 0)
                }
            else:
                hedging_analysis['delta_neutrality'] = {
                    'status': 'manageable',
                    'net_delta': total_delta
                }
            
            # Gamma risk assessment
            total_gamma = total_exposures.get('gamma', 0)
            gamma_pnl_1pct = risk_scenarios.get('gamma_pnl_1pct_move', 0)
            
            if abs(gamma_pnl_1pct) > 1000:  # $1000 gamma risk
                hedging_analysis['gamma_risk_assessment'] = {
                    'status': 'high_risk',
                    'gamma_pnl_1pct': gamma_pnl_1pct,
                    'recommendation': 'Consider gamma hedging or position sizing reduction'
                }
            else:
                hedging_analysis['gamma_risk_assessment'] = {
                    'status': 'acceptable',
                    'gamma_pnl_1pct': gamma_pnl_1pct
                }
            
            # Generate recommendations
            recommendations = []
            
            if abs(total_delta) > 500:
                recommendations.append(f"High delta exposure ({total_delta:.0f}): Consider hedging with underlying")
            
            if abs(total_exposures.get('theta', 0)) > 500:
                recommendations.append("High time decay exposure: Monitor position sizing and time to expiration")
            
            if abs(total_exposures.get('vega', 0)) > 1000:
                recommendations.append("High volatility sensitivity: Consider volatility hedging strategies")
            
            hedging_analysis['hedging_recommendations'] = recommendations
            
            return hedging_analysis
            
        except Exception as e:
            logging.error(f"Error generating hedging analysis: {e}")
            return {}

    # Market Infrastructure Methods (NEW - Part 7)
    
    def get_market_status(self, max_age_seconds=60):
        """Get current market status with intelligent caching
        
        Args:
            max_age_seconds: Cache age limit (default 60s for real-time status)
            
        Returns:
            Dict with market status, session info, and trading state
        """
        # Check cache first for market clock data
        cached_data = self.cache.load_from_cache('market_status', 'current', max_age_seconds)
        
        if cached_data:
            return cached_data
        
        logging.info("Fetching current market status")
        response = self.api.get_market_clock()
        
        if response:
            # Enhance the response with additional calculated fields
            enhanced_status = dict(response)
            
            # Add convenience fields
            if 'state' in response:
                enhanced_status['is_open'] = response['state'].lower() == 'open'
                enhanced_status['is_closed'] = response['state'].lower() == 'closed'
                enhanced_status['is_premarket'] = response['state'].lower() == 'premarket'
                enhanced_status['is_postmarket'] = response['state'].lower() == 'postmarket'
            
            # Add timestamp
            enhanced_status['retrieved_at'] = eastern_isoformat()
            
            # Cache the enhanced response
            self.cache.save_to_cache('market_status', 'current', enhanced_status)
            return enhanced_status
        
        return None
    
    def is_market_open(self):
        """Simple boolean check if market is currently open
        
        Returns:
            bool: True if market is open, False otherwise
        """
        status = self.get_market_status()
        if status:
            return status.get('is_open', False)
        return False
    
    def get_trading_calendar(self, months_ahead=3, max_age_seconds=3600*24):
        """Get upcoming trading days and holidays
        
        Args:
            months_ahead: Number of months to look ahead
            max_age_seconds: Cache age limit (default 24 hours)
            
        Returns:
            Dict with trading calendar data
        """
        # Check cache first
        cache_key = f"calendar_{months_ahead}m"
        cached_data = self.cache.load_from_cache('market_calendar', cache_key, max_age_seconds)
        
        if cached_data:
            return cached_data

        logging.debug(f"Fetching trading calendar for next {months_ahead} months")
        
        # Get calendar data for current and future months
        calendar_data = {'months': {}, 'holidays': [], 'trading_days': []}
        current_date = now_eastern()
        
        for i in range(months_ahead + 1):  # Include current month
            target_date = current_date + timedelta(days=30*i)
            month = target_date.month
            year = target_date.year
            
            try:
                response = self.api.get_market_calendar(month, year)
                
                if response:
                    month_key = f"{year}-{month:02d}"
                    calendar_data['months'][month_key] = response
                    
                    # Handle different possible response structures
                    calendar_info = response
                    if 'calendar' in response:
                        calendar_info = response['calendar']
                    
                    # Extract holidays and trading days if they exist
                    if isinstance(calendar_info, dict) and 'days' in calendar_info:
                        days_data = calendar_info['days']
                        if isinstance(days_data, dict) and 'day' in days_data:
                            # Handle wrapped day structure
                            day_list = days_data['day']
                            if not isinstance(day_list, list):
                                day_list = [day_list]
                        elif isinstance(days_data, list):
                            # Handle direct list structure
                            day_list = days_data
                        else:
                            day_list = []
                        
                        for day_info in day_list:
                            if isinstance(day_info, dict):
                                date_str = day_info.get('date')
                                if date_str:
                                    status = day_info.get('status', 'unknown')
                                    if status == 'closed':
                                        calendar_data['holidays'].append({
                                            'date': date_str,
                                            'description': day_info.get('description', 'Market Holiday')
                                        })
                                    elif status == 'open':
                                        calendar_data['trading_days'].append(date_str)
                                        
            except Exception as e:
                logging.warning(f"Error fetching calendar for {year}-{month:02d}: {e}")
                continue
        
        # Add summary information
        calendar_data['summary'] = {
            'months_covered': months_ahead + 1,
            'total_holidays': len(calendar_data['holidays']),
            'total_trading_days': len(calendar_data['trading_days']),
            'generated_at': eastern_isoformat()
        }
        
        # Cache the results
        self.cache.save_to_cache('market_calendar', cache_key, calendar_data)
        return calendar_data
    
    def get_option_strikes_list(self, symbol, expiration, max_age_seconds=1800):
        """Get available option strikes with caching
        
        Args:
            symbol: Underlying symbol
            expiration: Expiration date (YYYY-MM-DD)
            max_age_seconds: Cache age limit (default 30 minutes)
            
        Returns:
            List of available strike prices
        """
        cache_suffix = f"strikes_{expiration}"
        cached_data = self.cache.load_from_cache('options', symbol, max_age_seconds, cache_suffix)
        
        if cached_data:
            return cached_data
        
        logging.info(f"Fetching option strikes for {symbol} expiring {expiration}")
        response = self.api.get_option_strikes(symbol, expiration)
        
        if response and 'strikes' in response:
            strikes_data = response['strikes']
            
            # Extract strike prices into a simple list
            if 'strike' in strikes_data:
                strikes_list = strikes_data['strike']
                if not isinstance(strikes_list, list):
                    strikes_list = [strikes_list]
                
                # Convert to float and sort
                strikes_list = sorted([float(strike) for strike in strikes_list])
                
                # Cache the results
                self.cache.save_to_cache('options', symbol, strikes_list, cache_suffix)
                return strikes_list
        
        return []
    
    def search_symbols_by_name(self, company_name, max_age_seconds=3600*24*7):
        """Search for symbols by company name
        
        Args:
            company_name: Company name to search for
            max_age_seconds: Cache age limit (default 7 days)
            
        Returns:
            List of matching symbols with company information
        """
        # Normalize the search query for caching
        cache_key = company_name.lower().replace(' ', '_')
        cached_data = self.cache.load_from_cache('symbol_search', cache_key, max_age_seconds)
        
        if cached_data:
            return cached_data
        
        logging.info(f"Searching for symbols matching '{company_name}'")
        response = self.api.search_companies(company_name)
        
        search_results = []
        
        if response and 'securities' in response:
            securities = response['securities']
            
            if 'security' in securities:
                security_list = securities['security']
                if not isinstance(security_list, list):
                    security_list = [security_list]
                
                for security in security_list:
                    search_results.append({
                        'symbol': security.get('symbol'),
                        'description': security.get('description'),
                        'exchange': security.get('exchange'),
                        'type': security.get('type')
                    })
        
        # Cache the results
        self.cache.save_to_cache('symbol_search', cache_key, search_results)
        return search_results
    
    def validate_symbol(self, symbol, max_age_seconds=3600*24):
        """Validate a symbol and get detailed information
        
        Args:
            symbol: Symbol to validate
            max_age_seconds: Cache age limit (default 24 hours)
            
        Returns:
            Dict with symbol validation results and details
        """
        cached_data = self.cache.load_from_cache('symbol_validation', symbol, max_age_seconds)
        
        if cached_data:
            return cached_data
        
        logging.info(f"Validating symbol {symbol}")
        response = self.api.get_symbol_lookup(symbol)
        
        validation_result = {
            'symbol': symbol,
            'is_valid': False,
            'details': None,
            'alternatives': []
        }
        
        if response and 'securities' in response:
            securities = response['securities']
            
            if 'security' in securities:
                security_list = securities['security']
                if not isinstance(security_list, list):
                    security_list = [security_list]
                
                # Look for exact match first
                for security in security_list:
                    if security.get('symbol', '').upper() == symbol.upper():
                        validation_result['is_valid'] = True
                        validation_result['details'] = {
                            'symbol': security.get('symbol'),
                            'description': security.get('description'),
                            'exchange': security.get('exchange'),
                            'type': security.get('type')
                        }
                        break
                
                # If no exact match, add alternatives
                if not validation_result['is_valid']:
                    for security in security_list:
                        validation_result['alternatives'].append({
                            'symbol': security.get('symbol'),
                            'description': security.get('description'),
                            'similarity_reason': 'partial_match'
                        })
        
        # Cache the results
        self.cache.save_to_cache('symbol_validation', symbol, validation_result)
        return validation_result


def test_market_infrastructure(client):
    """Test the new market infrastructure endpoints"""
    print("\n" + "="*60)
    print("TESTING NEW MARKET INFRASTRUCTURE ENDPOINTS")
    print("="*60)
    
    try:
        # Test 1: Market Status
        print("\n1. Testing Market Status...")
        status = client.get_market_status()
        if status:
            print(f"✅ Market Status: {status.get('state', 'unknown')}")
            print(f"   Market Open: {status.get('is_open', False)}")
            print(f"   Session: {status.get('session', 'unknown')}")
        else:
            print("❌ Market status failed")
        
        # Test 2: Is Market Open (simple check)
        print("\n2. Testing Simple Market Check...")
        is_open = client.is_market_open()
        print(f"✅ Is Market Open: {is_open}")
        
        # Test 3: Trading Calendar
        print("\n3. Testing Trading Calendar...")
        try:
            calendar = client.get_trading_calendar(months_ahead=1)
            if calendar:
                summary = calendar.get('summary', {})
                holidays = calendar.get('holidays', [])
                print(f"✅ Trading Calendar Retrieved")
                print(f"   Months covered: {summary.get('months_covered', 0)}")
                print(f"   Total holidays: {summary.get('total_holidays', 0)}")
                print(f"   Total trading days: {summary.get('total_trading_days', 0)}")
                if holidays:
                    print(f"   Next holiday: {holidays[0].get('date')} - {holidays[0].get('description')}")
                else:
                    print("   No holidays found in next month")
            else:
                print("❌ Trading calendar failed - no data returned")
        except Exception as e:
            print(f"❌ Trading calendar error: {e}")
            logging.debug(f"Calendar error details: {traceback.format_exc()}")
            # Continue with other tests
        
        # Test 4: Symbol Search
        print("\n4. Testing Symbol Search...")
        results = client.search_symbols_by_name("Apple")
        if results:
            print(f"✅ Found {len(results)} results for 'Apple'")
            for result in results[:3]:  # Show first 3
                print(f"   {result.get('symbol')}: {result.get('description')}")
        else:
            print("❌ Symbol search failed")
        
        # Test 5: Option Strikes
        print("\n5. Testing Option Strikes...")
        expirations = client.get_option_expirations('SPY')
        if expirations and 'date' in expirations:
            exp_dates = expirations['date']
            if not isinstance(exp_dates, list):
                exp_dates = [exp_dates]
            
            strikes = client.get_option_strikes_list('SPY', exp_dates[0])
            if strikes:
                print(f"✅ Found {len(strikes)} strikes for SPY {exp_dates[0]}")
                print(f"   Strike range: ${min(strikes):.0f} - ${max(strikes):.0f}")
            else:
                print("❌ Option strikes failed")
        else:
            print("❌ Could not get expirations for strikes test")
        
        print("\n" + "="*60)
        print("MARKET INFRASTRUCTURE TESTS COMPLETED!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ Market infrastructure test error: {e}")
        return False


def main():
    """Test the enhanced Tradier API client with market infrastructure"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Enhanced Tradier API client")
    parser.add_argument("--config", help="Path to config.json file")
    parser.add_argument("--cache-dir", default="./cache", help="Cache directory")
    parser.add_argument("--symbols", default="SPY,AAPL", help="Symbols to test")
    parser.add_argument("--test-connection", action="store_true", help="Test API connection")
    parser.add_argument("--test-market", action="store_true", help="Test market infrastructure endpoints")
    args = parser.parse_args()
    
    # Load config
    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
    else:
        # Default config for testing
        config = {
            "tradier": {
                "api_key": "REDACTED_TRADIER_KEY",
                "sandbox": False
            }
        }
    
    try:
        client = TradierDataClient(config, args.cache_dir)
        
        if args.test_connection:
            print("Testing Tradier API connection...")
            if client.test_connection():
                print("✅ Connection successful!")
            else:
                print("❌ Connection failed!")
                return
        
        # Test market infrastructure if requested
        if args.test_market:
            success = test_market_infrastructure(client)
            if not success:
                print("❌ Market infrastructure tests failed!")
                return
        
        symbols = args.symbols.split(',')
        print(f"\nTesting quotes for: {', '.join(symbols)}")
        
        quotes = client.get_quotes(symbols)
        for symbol, quote in quotes.items():
            print(f"{symbol}: ${quote['last']:.2f} ({quote['change_percentage']:+.2f}%)")
        
        # Test options
        test_symbol = symbols[0]
        print(f"\nTesting options for {test_symbol}...")
        expirations = client.get_option_expirations(test_symbol)
        
        if expirations and 'date' in expirations:
            exp_dates = expirations['date']
            if not isinstance(exp_dates, list):
                exp_dates = [exp_dates]
            print(f"Found {len(exp_dates)} expiration dates")
            
            # Test option chain for first expiration
            if exp_dates:
                options = client.get_option_chain(test_symbol, exp_dates[0])
                if options and 'option' in options:
                    option_list = options['option']
                    if not isinstance(option_list, list):
                        option_list = [option_list]
                    print(f"Found {len(option_list)} options for {exp_dates[0]}")
        
        print("\n✅ Enhanced Tradier API client test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()