#!/usr/bin/env python3
"""
Market Daily Summary Collection
================================
Evening-only market data collection using Tradier API.

Data Sources:
- Tradier: SPY/VIX/sector ETFs OHLCV + indices (1 bulk API call)
- Tradier: KLMN 800 universe for market breadth calculations (~32 batched API calls)
  (Migrated from FMP on 2025-11-19 after free tier deprecation)

Features:
- Complete daily market summary with VIX-based regime classification
- Market breadth metrics (advance/decline, new highs/lows)
- Evening execution (post-market close)
- Clean schema with trade_date as primary key

Target Table:
- market_daily_summary: Daily market context with regime classification

Author: Ben (with assistance from Claude)
Date: 2025-09-30
Last Updated: 2025-11-19 (FMP → Tradier migration)
"""

import sqlite3
import logging
import sys
import json
import argparse
import requests
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from tools.timezone_utils import now_eastern, eastern_date_string, eastern_isoformat
    from tools.decimal_formatter import clean_database_row, format_percentage, format_price, format_ratio
    from core.tradier_api import TradierDataClient
    from core.symbols_klmn800 import get_specialty_list
except ImportError as e:
    print("Error importing required modules: {}".format(e))
    print("Ensure required modules are in tools/ and core/ directories.")
    sys.exit(1)


class MarketDailyRegimeSummaryCollector:
    """Market data collector using Tradier API (FMP deprecated Nov 2025)"""
    
    def __init__(self, config_path=None):
        """Initialize collector with configuration"""
        self.config = self._load_config(config_path)
        
        # Initialize Tradier API with cache directory
        cache_dir = Path(__file__).parent.parent / 'cache' / 'tradier'
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.tradier_api = TradierDataClient(self.config, str(cache_dir))
        
        self.fmp_api_key = self.config.get('fmp', {}).get('api_key')
        self.db_path = self._get_database_path()
        self.klmn_symbols = self._get_klmn_800_symbols()
        
        # Market symbols for Tradier bulk call
        self.market_symbols = [
            'SPY', 'VIX', 'QQQ', 'IWM',  # Core indices
            'XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU', 'XLB', 'XLRE',  # Sectors
            'JETS', 'NLR',  # Industry ETFs
            'TLT', 'GLD', 'UUP'  # Additional context
        ]
        
        # VIX regime thresholds (CBOE standards: <15 low, 15-20 normal, 20-30 elevated, >30 panic)
        self.VIX_REGIMES = {
            'low_vol': {'max': 15, 'multiplier': 0.8},
            'normal': {'min': 15, 'max': 20, 'multiplier': 1.0},
            'elevated': {'min': 20, 'max': 30, 'multiplier': 1.2},
            'panic': {'min': 30, 'multiplier': 1.5}
        }
        
        # Trading day thresholds for new highs/lows
        self.NEW_HIGHS_LOWS_PERIOD = 252  # Trading days (~1 year)
        
        # Statistics tracking
        self.stats = {
            'tradier_calls': 0,
            'fmp_calls': 0,
            'symbols_processed': 0,
            'advancing_stocks': 0,
            'declining_stocks': 0,
            'new_highs': 0,
            'new_lows': 0,
            'advancing_volume': 0.0,
            'declining_volume': 0.0,
            'errors': 0
        }
        
        logging.info("Market Daily Regime Summary Collector initialized")
        logging.info("Tradier market symbols: {} | Tradier breadth symbols: {}".format(
            len(self.market_symbols), len(self.klmn_symbols)))
    
    def _load_config(self, config_path=None):
        """Load configuration from JSON file"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config.json'
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            if not config.get('tradier', {}).get('api_key'):
                raise ValueError("Tradier API key not found in config")
            # FMP API key no longer required (deprecated Nov 2025)

            return config
            
        except FileNotFoundError:
            logging.error("Configuration file not found: {}".format(config_path))
            raise
        except json.JSONDecodeError as e:
            logging.error("Invalid JSON in configuration file: {}".format(e))
            raise
        except Exception as e:
            logging.error("Failed to load configuration: {}".format(e))
            raise
    
    def _get_database_path(self):
        """Get path to datalake.db"""
        return r'E:\options_scanner\data\datalake.db'
    
    def _get_klmn_800_symbols(self):
        """Get KLMN 800 symbols for market breadth analysis"""
        try:
            symbols = get_specialty_list('klmn_800')
            
            if not symbols:
                raise ValueError("KLMN 800 symbol list is empty")
            
            if len(symbols) != 815:  # Expected count including ETFs
                logging.warning("Expected 815 KLMN symbols, got {}".format(len(symbols)))
            
            logging.info("Successfully loaded {} KLMN 800 symbols".format(len(symbols)))
            return symbols
            
        except ImportError as e:
            logging.error("Could not import KLMN 800 symbols: {}".format(e))
            raise Exception("Failed to load KLMN 800 symbols - check core directory setup")
        except Exception as e:
            logging.error("Error loading KLMN 800 symbols: {}".format(e))
            raise
    
    def _check_existing_data(self, trade_date):
        """Check if complete market data already exists for date"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM market_daily_summary
                    WHERE trade_date = ?
                    AND spy_close IS NOT NULL
                    AND vix_close IS NOT NULL
                    AND regime_classification IS NOT NULL
                    AND (advancing_stocks > 0 OR declining_stocks > 0)
                """, (trade_date,))

                result = cursor.fetchone()
                exists = result and result[0] > 0

                if exists:
                    logging.info("Complete market data already exists for {}".format(trade_date))
                    return True
                else:
                    logging.info("No complete market data found for {}".format(trade_date))
                    return False

        except Exception as e:
            logging.error("Error checking existing data: {}".format(e))
            return False
    
    def _get_market_quotes_tradier(self):
        """Get market quotes using Tradier API call"""
        try:
            logging.info("Fetching market quotes from Tradier...")
            quotes = self.tradier_api.get_quotes(self.market_symbols, max_age_seconds=60)
            self.stats['tradier_calls'] += 1
            
            if not quotes:
                logging.error("No quotes returned from Tradier")
                return None
            
            # Validate we got data for required symbols
            missing_symbols = []
            for symbol in self.market_symbols:
                if symbol not in quotes:
                    missing_symbols.append(symbol)
            
            if missing_symbols:
                logging.warning("Missing quotes for symbols: {}".format(missing_symbols))
            
            logging.info("Successfully retrieved {} quotes from Tradier".format(len(quotes)))
            return quotes
            
        except Exception as e:
            logging.error("Error fetching Tradier quotes: {}".format(e))
            self.stats['errors'] += 1
            return None
    
    def _get_breadth_data_fmp(self, trade_date):
        """Get market breadth data using Tradier API (FMP deprecated Aug 2025)"""
        try:
            logging.info("Calculating market breadth using Tradier data...")

            # Check if we have sufficient historical data
            if not self._validate_historical_data():
                logging.warning("Insufficient historical data for breadth calculations")
                return {
                    'advancing_stocks': 0,
                    'declining_stocks': 0,
                    'new_highs': 0,
                    'new_lows': 0,
                    'advancing_volume': 0.0,
                    'declining_volume': 0.0
                }

            # Get current day prices for KLMN symbols from Tradier (replaces FMP)
            current_prices = self._get_current_prices_tradier(trade_date)
            if not current_prices:
                logging.error("Failed to get current prices from Tradier")
                return None
            
            # Calculate advance/decline and volume metrics
            breadth_data = self._calculate_breadth_metrics(current_prices, trade_date)
            
            # Calculate new highs/lows
            highs_lows = self._calculate_new_highs_lows(trade_date)
            breadth_data.update(highs_lows)
            
            logging.info("Market breadth calculated: {} advancing, {} declining, {} new highs, {} new lows".format(
                breadth_data['advancing_stocks'], breadth_data['declining_stocks'],
                breadth_data['new_highs'], breadth_data['new_lows']))
            
            return breadth_data
            
        except Exception as e:
            logging.error("Error calculating market breadth: {}".format(e))
            self.stats['errors'] += 1
            return None
    
    def _validate_historical_data(self):
        """Validate that we have sufficient historical data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                recent_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT symbol) as symbol_count,
                           COUNT(*) as total_records,
                           MAX(trade_date) as latest_date
                    FROM historical_prices 
                    WHERE trade_date >= ?
                """, (recent_date,))
                
                result = cursor.fetchone()
                if result:
                    symbol_count, total_records, latest_date = result
                    
                    if symbol_count >= 500:
                        logging.info("Historical data validation passed: {} symbols".format(symbol_count))
                        return True
                    else:
                        logging.warning("Insufficient historical data: {} symbols (need 500+)".format(symbol_count))
                        return False
                else:
                    logging.warning("No historical data found")
                    return False
                    
        except Exception as e:
            logging.error("Error validating historical data: {}".format(e))
            return False
    
    def _get_current_prices_tradier(self, trade_date):
        """Get current day prices from Tradier for breadth calculation

        Replaces deprecated FMP API (free tier ended Aug 2025).
        Uses Tradier's get_quotes() which automatically batches in groups of 25.
        """
        try:
            logging.info("Fetching current prices from Tradier for {} symbols...".format(len(self.klmn_symbols)))

            # Get quotes for all KLMN symbols using Tradier
            # Tradier API client handles batching automatically (25 symbols per call)
            quotes = self.tradier_api.get_quotes(self.klmn_symbols, max_age_seconds=60)
            self.stats['tradier_calls'] += 1  # Track API usage

            if not quotes:
                logging.error("No quotes returned from Tradier for KLMN symbols")
                return None

            # Map Tradier quote format to expected format
            all_prices = {}
            for symbol, quote in quotes.items():
                all_prices[symbol] = {
                    'price': self._safe_float(quote.get('last', 0)),  # Tradier uses 'last' for current price
                    'change': self._safe_float(quote.get('change', 0)),  # Daily price change in dollars
                    'volume': self._safe_float(quote.get('volume', 0))
                }

            logging.info("Retrieved current prices for {} symbols from Tradier".format(len(all_prices)))
            return all_prices

        except Exception as e:
            logging.error("Error getting current prices from Tradier: {}".format(e))
            return None
    
    def _calculate_breadth_metrics(self, current_prices, trade_date):
        """Calculate advance/decline and volume metrics"""
        advancing = 0
        declining = 0
        advancing_volume = 0.0
        declining_volume = 0.0

        for symbol, data in current_prices.items():
            change = data.get('change', 0)
            volume = data.get('volume', 0)

            # Handle None values from _safe_float (symbols with no trading data)
            if change is None:
                change = 0
            if volume is None:
                volume = 0

            if change > 0:
                advancing += 1
                advancing_volume += volume
            elif change < 0:
                declining += 1
                declining_volume += volume
        
        self.stats['advancing_stocks'] = advancing
        self.stats['declining_stocks'] = declining
        self.stats['advancing_volume'] = advancing_volume
        self.stats['declining_volume'] = declining_volume
        
        return {
            'advancing_stocks': advancing,
            'declining_stocks': declining,
            'advancing_volume': advancing_volume,
            'declining_volume': declining_volume
        }
    
    def _calculate_new_highs_lows(self, trade_date):
        """Calculate new 52-week highs and lows"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get 252-day high/low for each symbol - using correct column names
                cursor.execute("""
                    WITH price_ranges AS (
                        SELECT 
                            symbol,
                            MAX(high_price) as period_high,
                            MIN(low_price) as period_low,
                            MAX(CASE WHEN trade_date = ? THEN high_price END) as current_high,
                            MIN(CASE WHEN trade_date = ? THEN low_price END) as current_low
                        FROM historical_prices 
                        WHERE trade_date >= DATE(?, '-252 days')
                        AND trade_date <= ?
                        GROUP BY symbol
                        HAVING current_high IS NOT NULL AND current_low IS NOT NULL
                    )
                    SELECT 
                        SUM(CASE WHEN current_high >= period_high THEN 1 ELSE 0 END) as new_highs,
                        SUM(CASE WHEN current_low <= period_low THEN 1 ELSE 0 END) as new_lows
                    FROM price_ranges
                """, (trade_date, trade_date, trade_date, trade_date))
                
                result = cursor.fetchone()
                if result:
                    new_highs, new_lows = result
                    self.stats['new_highs'] = new_highs or 0
                    self.stats['new_lows'] = new_lows or 0
                    
                    return {
                        'new_highs': new_highs or 0,
                        'new_lows': new_lows or 0
                    }
                else:
                    return {'new_highs': 0, 'new_lows': 0}
                    
        except Exception as e:
            logging.error("Error calculating new highs/lows: {}".format(e))
            return {'new_highs': 0, 'new_lows': 0}
    
    def _calculate_market_direction(self, spy_change, vix_change):
        """Calculate market direction based on SPY and VIX changes"""
        if spy_change > 1.0 and vix_change < -5.0:
            return "Strong Bull"
        elif spy_change > 0.5 and vix_change < 0:
            return "Bull"
        elif spy_change < -1.0 and vix_change > 5.0:
            return "Strong Bear"
        elif spy_change < -0.5 and vix_change > 0:
            return "Bear"
        else:
            return "Neutral"
    
    def _calculate_change_percent(self, current_price, previous_price):
        """Calculate percentage change with safe division"""
        if not previous_price or previous_price == 0:
            return format_percentage(0.0)
        return format_percentage(((current_price - previous_price) / previous_price) * 100)
    
    def _get_previous_day_data(self, trade_date):
        """Get previous trading day data for percentage calculations"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT spy_close, vix_close, qqq_close, iwm_close,
                           xlf_close, xle_close, xlk_close, xlv_close, xli_close,
                           xlp_close, xly_close, xlu_close, xlb_close, xlre_close,
                           jets_close, nlr_close,
                           tlt_close, gld_close, uup_close
                    FROM market_daily_summary
                    WHERE trade_date < ?
                    ORDER BY trade_date DESC
                    LIMIT 1
                """, (trade_date,))

                result = cursor.fetchone()
                if result:
                    return dict(zip([
                        'spy_close', 'vix_close', 'qqq_close', 'iwm_close',
                        'xlf_close', 'xle_close', 'xlk_close', 'xlv_close', 'xli_close',
                        'xlp_close', 'xly_close', 'xlu_close', 'xlb_close', 'xlre_close',
                        'jets_close', 'nlr_close',
                        'tlt_close', 'gld_close', 'uup_close'
                    ], result))
                else:
                    logging.warning("No previous day data found")
                    return None
                    
        except Exception as e:
            logging.error("Error getting previous day data: {}".format(e))
            return None
    
    def _store_market_data(self, quotes, breadth_data, trade_date):
        """Store complete market data in database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get previous day data for percentage calculations
                previous_data = self._get_previous_day_data(trade_date)
                
                # Process market quotes
                market_data = self._process_market_quotes(quotes, previous_data, trade_date)
                
                # Add breadth data
                market_data.update(breadth_data)

                # Add metadata
                market_data['trade_date'] = trade_date
                market_data['created_at'] = eastern_isoformat()

                # Calculate market direction
                spy_change = market_data.get('spy_change_percent', 0)
                vix_change = market_data.get('vix_change_percent', 0)
                market_data['market_direction'] = self._calculate_market_direction(spy_change, vix_change)

                # Calculate VIX regime classification (CBOE standards)
                vix_close = market_data.get('vix_close')
                if vix_close:
                    if vix_close < self.VIX_REGIMES['low_vol']['max']:
                        regime = 'low_vol'
                        multiplier = self.VIX_REGIMES['low_vol']['multiplier']
                    elif vix_close < self.VIX_REGIMES['normal']['max']:
                        regime = 'normal'
                        multiplier = self.VIX_REGIMES['normal']['multiplier']
                    elif vix_close < self.VIX_REGIMES['elevated']['max']:
                        regime = 'elevated'
                        multiplier = self.VIX_REGIMES['elevated']['multiplier']
                    else:
                        regime = 'panic'
                        multiplier = self.VIX_REGIMES['panic']['multiplier']

                    market_data['regime_classification'] = regime
                    market_data['regime_multiplier'] = multiplier
                else:
                    market_data['regime_classification'] = None
                    market_data['regime_multiplier'] = None

                # Delete existing data for this trade_date (replace with fresh data)
                cursor.execute("""
                    DELETE FROM market_daily_summary
                    WHERE trade_date = ?
                """, (trade_date,))

                # Apply decimal formatting to all numeric values
                market_data = clean_database_row(market_data)

                # Insert into database (now includes regime data)
                self._insert_market_summary(cursor, market_data, trade_date)
                
                conn.commit()
                logging.info("Successfully stored market data for {}".format(trade_date))
                return True
                
        except Exception as e:
            logging.error("Error storing market data: {}".format(e))
            return False
    
    def _process_market_quotes(self, quotes, previous_data, trade_date):
        """Process market quotes into database format"""
        processed_data = {'trade_date': trade_date}
        
        # Process SPY (full OHLCV)
        if 'SPY' in quotes:
            spy = quotes['SPY']
            processed_data.update({
                'spy_open': self._safe_float(spy.get('open')),
                'spy_high': self._safe_float(spy.get('high')),
                'spy_low': self._safe_float(spy.get('low')),
                'spy_close': self._safe_float(spy.get('last')),
                'spy_volume': self._safe_float(spy.get('volume')),
                'spy_change_percent': self._calculate_change_percent(
                    spy.get('last'), previous_data.get('spy_close') if previous_data else None
                )
            })
        
        # Process VIX (full OHLCV)
        if 'VIX' in quotes:
            vix = quotes['VIX']
            processed_data.update({
                'vix_open': self._safe_float(vix.get('open')),
                'vix_high': self._safe_float(vix.get('high')),
                'vix_low': self._safe_float(vix.get('low')),
                'vix_close': self._safe_float(vix.get('last')),
                'vix_volume': self._safe_float(vix.get('volume')),
                'vix_change_percent': self._calculate_change_percent(
                    vix.get('last'), previous_data.get('vix_close') if previous_data else None
                )
            })
        
        # Process context symbols (close + change only) - copied exact mapping
        context_symbols = {
            'QQQ': 'qqq', 'IWM': 'iwm', 'XLF': 'xlf', 'XLE': 'xle',
            'XLK': 'xlk', 'XLV': 'xlv', 'XLI': 'xli', 'XLP': 'xlp',
            'XLY': 'xly', 'XLU': 'xlu', 'XLB': 'xlb', 'XLRE': 'xlre',
            'JETS': 'jets', 'NLR': 'nlr',
            'TLT': 'tlt', 'GLD': 'gld', 'UUP': 'uup'
        }
        
        for symbol, prefix in context_symbols.items():
            if symbol in quotes:
                quote = quotes[symbol]
                processed_data.update({
                    '{}_close'.format(prefix): self._safe_float(quote.get('last')),
                    '{}_change_percent'.format(prefix): self._calculate_change_percent(
                        quote.get('last'), previous_data.get('{}_close'.format(prefix)) if previous_data else None
                    )
                })
        
        return processed_data
    
    def _safe_float(self, value, default=0.0):
        """Safely convert value to float with default fallback

        Args:
            value: Value to convert to float
            default: Default value if conversion fails (default: 0.0)

        Returns:
            Float value or default
        """
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default
    
    def _insert_market_summary(self, cursor, market_data, trade_date):
        """Insert market summary data into database with clean schema"""
        insert_sql = """
            INSERT INTO market_daily_summary (
                trade_date, regime_classification, regime_multiplier, market_direction,
                advancing_stocks, declining_stocks, advancing_volume, declining_volume,
                new_highs, new_lows,
                spy_open, spy_high, spy_low, spy_close, spy_volume, spy_change_percent,
                vix_open, vix_high, vix_low, vix_close, vix_volume, vix_change_percent,
                qqq_close, qqq_change_percent, iwm_close, iwm_change_percent,
                xlf_close, xlf_change_percent, xle_close, xle_change_percent,
                xlk_close, xlk_change_percent, xlv_close, xlv_change_percent,
                xli_close, xli_change_percent, xlp_close, xlp_change_percent,
                xly_close, xly_change_percent, xlu_close, xlu_change_percent,
                xlb_close, xlb_change_percent, xlre_close, xlre_change_percent,
                jets_close, jets_change_percent, nlr_close, nlr_change_percent,
                tlt_close, tlt_change_percent, gld_close, gld_change_percent,
                uup_close, uup_change_percent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values = (
            market_data['trade_date'],
            market_data.get('regime_classification'),
            market_data.get('regime_multiplier'),
            market_data.get('market_direction'),
            market_data.get('advancing_stocks', 0),
            market_data.get('declining_stocks', 0),
            market_data.get('advancing_volume', 0.0),
            market_data.get('declining_volume', 0.0),
            market_data.get('new_highs', 0),
            market_data.get('new_lows', 0),
            market_data.get('spy_open'), market_data.get('spy_high'), market_data.get('spy_low'),
            market_data.get('spy_close'), market_data.get('spy_volume'), market_data.get('spy_change_percent'),
            market_data.get('vix_open'), market_data.get('vix_high'), market_data.get('vix_low'),
            market_data.get('vix_close'), market_data.get('vix_volume'), market_data.get('vix_change_percent'),
            market_data.get('qqq_close'), market_data.get('qqq_change_percent'),
            market_data.get('iwm_close'), market_data.get('iwm_change_percent'),
            market_data.get('xlf_close'), market_data.get('xlf_change_percent'),
            market_data.get('xle_close'), market_data.get('xle_change_percent'),
            market_data.get('xlk_close'), market_data.get('xlk_change_percent'),
            market_data.get('xlv_close'), market_data.get('xlv_change_percent'),
            market_data.get('xli_close'), market_data.get('xli_change_percent'),
            market_data.get('xlp_close'), market_data.get('xlp_change_percent'),
            market_data.get('xly_close'), market_data.get('xly_change_percent'),
            market_data.get('xlu_close'), market_data.get('xlu_change_percent'),
            market_data.get('xlb_close'), market_data.get('xlb_change_percent'),
            market_data.get('xlre_close'), market_data.get('xlre_change_percent'),
            market_data.get('jets_close'), market_data.get('jets_change_percent'),
            market_data.get('nlr_close'), market_data.get('nlr_change_percent'),
            market_data.get('tlt_close'), market_data.get('tlt_change_percent'),
            market_data.get('gld_close'), market_data.get('gld_change_percent'),
            market_data.get('uup_close'), market_data.get('uup_change_percent'),
            market_data.get('created_at')
        )

        cursor.execute(insert_sql, values)
    
    
    def collect_market_data(self, trade_date=None):
        """Main collection method"""
        if trade_date is None:
            trade_date = eastern_date_string()
        
        logging.info("Starting market data collection for {}".format(trade_date))
        
        # Check if data already exists
        if self._check_existing_data(trade_date):
            logging.info("Market data already exists for {}".format(trade_date))
            return True
        
        # Get market quotes from Tradier
        quotes = self._get_market_quotes_tradier()
        if not quotes:
            logging.error("Failed to get market quotes from Tradier")
            return False
        
        # Get market breadth data from Tradier
        breadth_data = self._get_breadth_data_fmp(trade_date)
        if breadth_data is None:
            logging.error("Failed to get market breadth data from Tradier")
            return False
        
        # Store combined data
        success = self._store_market_data(quotes, breadth_data, trade_date)
        
        if success:
            self._log_collection_summary()
        
        return success
    
    def _log_collection_summary(self):
        """Log collection statistics"""
        logging.info("Collection Summary:")
        logging.info("  Tradier API calls: {}".format(self.stats['tradier_calls']))
        logging.info("  Market breadth: {} advancing, {} declining".format(
            self.stats['advancing_stocks'], self.stats['declining_stocks']))
        logging.info("  New highs/lows: {} / {}".format(
            self.stats['new_highs'], self.stats['new_lows']))
        logging.info("  Errors: {}".format(self.stats['errors']))


def setup_logging(debug=False):
    """Set up logging configuration with file and console handlers"""
    from pathlib import Path

    level = logging.DEBUG if debug else logging.INFO

    # Ensure logs directory exists
    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Prevent duplicate handlers if setup_logging called multiple times
    if logger.handlers:
        return

    # File handler - daily log file
    log_file = logs_dir / "market_daily_summary_{}.log".format(datetime.now().strftime("%Y-%m-%d"))
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Suppress Tradier API debug logs
    logging.getLogger('core.tradier_api').setLevel(logging.WARNING)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Market Daily Regime Summary Collection")
    parser.add_argument('--no-interaction', action='store_true',
                        help='Run without user interaction (for task scheduler)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--config',
                        help='Path to config.json file')
    
    args = parser.parse_args()
    
    setup_logging(args.debug)
    
    try:
        collector = MarketDailyRegimeSummaryCollector(args.config)
        success = collector.collect_market_data()
        
        if success:
            logging.info("Market data collection completed successfully")
            if not args.no_interaction:
                input("\nPress ENTER to exit...")
        else:
            logging.error("Market data collection failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logging.warning("Collection cancelled by user")
    except Exception as e:
        logging.error("Collection failed: {}".format(e))
        if not args.no_interaction:
            input("\nPress ENTER to exit...")
        sys.exit(1)


if __name__ == '__main__':
    main()