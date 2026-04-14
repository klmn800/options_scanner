#!/usr/bin/env python3
"""
Tradier Symbol Metadata Collector (symbol_metadata.py)
------------------------------------------------------
Populates symbol_metadata table using Tradier's beta fundamentals + quotes endpoints.

Features:
- Bulk endpoints: ALL ~750 symbols in ~60 seconds
- Fundamentals: sector, industry (Morningstar codes), market cap
- Quotes: company_name, avg_volume, is_etf detection
- Beta: 60-day calculation from historical_prices (covariance with SPY)
- Comprehensive autofix integration at 6 failure points
- UPDATE-first pattern to preserve archive_db column

Author: Ben (with assistance from Claude)
Date: 2026-02-05
"""

import os
import sys
import json
import sqlite3
import requests
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure stdout for UTF-8 (required for Unicode symbols on Windows)
sys.stdout.reconfigure(encoding='utf-8')

from tools.autofix import queue_error

# =============================================================================
# Morningstar Code Mappings (from discovery run 2026-02-05)
# =============================================================================

MORNINGSTAR_SECTOR_MAP = {
    101: 'Basic Materials',
    102: 'Consumer Cyclical',
    103: 'Financial Services',
    104: 'Real Estate',
    205: 'Consumer Defensive',
    206: 'Healthcare',
    207: 'Utilities',
    308: 'Communication Services',
    309: 'Energy',
    310: 'Industrials',
    311: 'Technology',
}

MORNINGSTAR_INDUSTRY_MAP = {
    # Basic Materials (101)
    10110010: 'Agricultural Inputs',
    10120010: 'Construction Materials',
    10130010: 'Chemicals',
    10130020: 'Specialty Chemicals',
    10150010: 'Aluminum',
    10150020: 'Copper',
    10150030: 'Rare Earth Materials',
    10150040: 'Gold',
    10160020: 'Steel',

    # Consumer Cyclical (102)
    10200010: 'Auto - Dealerships',
    10200020: 'Auto - Manufacturers',
    10200030: 'Auto Parts',
    10200040: 'Auto - Recreational Vehicles',
    10220010: 'Furnishings, Fixtures & Appliances',
    10230010: 'Residential Construction',
    10240020: 'Apparel - Manufacturers',
    10240030: 'Apparel - Footwear & Accessories',
    10250010: 'Packaging & Containers',
    10260010: 'Personal Products & Services',
    10270010: 'Restaurants',
    10280010: 'Apparel - Retail',
    10280020: 'Department Stores',
    10280030: 'Home Improvement',
    10280040: 'Luxury Goods',
    10280050: 'Internet Retail',
    10280060: 'Specialty Retail',
    10290010: 'Gambling, Resorts & Casinos',
    10290020: 'Leisure',
    10290030: 'Travel Lodging',
    10290040: 'Gambling, Resorts & Casinos',
    10290050: 'Travel Services',

    # Financial Services (103)
    10310010: 'Asset Management',
    10320010: 'Banks - Diversified',
    10320020: 'Banks - Regional',
    10320030: 'Financial - Mortgages',
    10330010: 'Financial - Capital Markets',
    10330020: 'Financial - Data & Stock Exchanges',
    10340010: 'Insurance - Life',
    10340020: 'Insurance - Property & Casualty',
    10340030: 'Insurance - Diversified',
    10340040: 'Insurance - Specialty',
    10340050: 'Insurance - Brokers',
    10340060: 'Insurance - Reinsurance',
    10360010: 'Credit Services',

    # Real Estate (104)
    10410020: 'Real Estate Services',
    10420010: 'REIT - Healthcare Facilities',
    10420020: 'REIT - Hotel & Motel',
    10420030: 'REIT - Industrial',
    10420040: 'REIT - Office',
    10420050: 'REIT - Residential',
    10420060: 'REIT - Retail',
    10420070: 'REIT - Mortgage',
    10420080: 'REIT - Specialty',
    10420090: 'REIT - Specialty',

    # Consumer Defensive (205)
    20510010: 'Beverages - Alcoholic',
    20510020: 'Beverages - Wineries & Distilleries',
    20520010: 'Beverages - Non-Alcoholic',
    20525010: 'Food Confectioners',
    20525020: 'Farm Products',
    20525030: 'Household & Personal Products',
    20525040: 'Packaged Foods',
    20550010: 'Discount Stores',
    20550020: 'Food Distribution',
    20550030: 'Grocery Stores',
    20560010: 'Tobacco',

    # Healthcare (206)
    20610010: 'Biotechnology',
    20620010: 'Drug Manufacturers - General',
    20620020: 'Drug Manufacturers - Specialty',
    20630010: 'Healthcare Plans',
    20645010: 'Medical - Care Facilities',
    20645030: 'Medical - Healthcare Information',
    20650010: 'Medical Devices',
    20650020: 'Medical Instruments & Supplies',
    20660010: 'Diagnostics & Research',
    20670010: 'Medical Distribution',

    # Utilities (207)
    20710010: 'Utilities - Independent Power Producers',
    20710020: 'Renewable Utilities',
    20720010: 'Utilities - Regulated Water',
    20720020: 'Utilities - Regulated Electric',
    20720030: 'Utilities - Regulated Gas',
    20720040: 'Diversified Utilities',

    # Communication Services (308)
    30810010: 'Telecom Services',
    30820010: 'Advertising Agencies',
    30820040: 'Entertainment',
    30830010: 'Internet Content & Information',
    30830020: 'Electronic Gaming & Multimedia',

    # Energy (309)
    30910020: 'Oil & Gas E&P',
    30910030: 'Oil & Gas Integrated',
    30910040: 'Oil & Gas Midstream',
    30910050: 'Oil & Gas Refining & Marketing',
    30910060: 'Oil & Gas Equipment & Services',
    30920020: 'Uranium',

    # Industrials (310)
    31010010: 'Aerospace & Defense',
    31020010: 'Specialty Business Services',
    31020020: 'Consulting Services',
    31020030: 'Rental & Leasing Services',
    31020040: 'Security & Protection Services',
    31020050: 'Staffing & Employment Services',
    31030010: 'Conglomerates',
    31040010: 'Engineering & Construction',
    31040030: 'Building Products & Equipment',
    31050010: 'Farm & Heavy Construction Machinery',
    31060010: 'Industrial - Distribution',
    31070020: 'Specialty Industrial Machinery',
    31070030: 'Industrial Materials',
    31070040: 'Industrial - Pollution & Treatment',
    31070050: 'Manufacturing - Tools & Accessories',
    31070060: 'Electrical Equipment & Parts',
    31080020: 'Airlines',
    31080030: 'Railroads',
    31080050: 'Trucking',
    31080060: 'Integrated Freight & Logistics',
    31090010: 'Waste Management',

    # Technology (311)
    31110010: 'Information Technology Services',
    31110020: 'Software - Application',
    31110030: 'Software - Infrastructure',
    31120010: 'Communication Equipment',
    31120020: 'Computer Hardware',
    31120030: 'Consumer Electronics',
    31120040: 'Electronic Components',
    31120060: 'Hardware, Equipment & Parts',
    31130010: 'Semiconductor Equipment & Materials',
    31130020: 'Semiconductors',
    31130030: 'Solar',
}

# Batch sizes
FUNDAMENTALS_BATCH_SIZE = 10
QUOTES_BATCH_SIZE = 100


# =============================================================================
# Configuration & Setup
# =============================================================================

def load_config():
    """Load configuration from project root"""
    config_path = os.path.join(project_root, 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error("Failed to load config: {}".format(e))
        return None


def get_klmn_800_symbols():
    """Get KLMN 800 symbols from symbols_klmn800.py"""
    try:
        from core.symbols_klmn800 import get_specialty_list
        return get_specialty_list('klmn_800')
    except ImportError:
        logging.error("Could not import symbols_klmn800 from core directory")
        return []


def get_database_path():
    """Get path to datalake.db"""
    return os.path.join(project_root, 'data', 'datalake.db')


# =============================================================================
# Category Functions (reused from av_symbol_metadata.py)
# =============================================================================

def categorize_market_cap(market_cap):
    """Categorize market cap into standard buckets"""
    if not market_cap or market_cap <= 0:
        return 'unknown'

    if market_cap >= 200_000_000_000:  # $200B+
        return 'mega_cap'
    elif market_cap >= 10_000_000_000:  # $10B - $200B
        return 'large_cap'
    elif market_cap >= 2_000_000_000:   # $2B - $10B
        return 'mid_cap'
    else:  # Under $2B
        return 'small_cap'


def categorize_liquidity_tier(avg_volume):
    """Categorize liquidity tier based on average volume"""
    if not avg_volume or avg_volume <= 0:
        return 'N/A'

    if avg_volume >= 10_000_000:
        return 'ultra_liquid'
    elif avg_volume >= 1_000_000:
        return 'high'
    elif avg_volume >= 100_000:
        return 'moderate'
    else:
        return 'thin'


def detect_etf(company_name, symbol, quote_type=None):
    """Detect if symbol is an ETF based on name, symbol patterns, and quote type

    Args:
        company_name: Company description from quotes
        symbol: Stock symbol
        quote_type: Quote type from Tradier ('etf', 'stock', etc.)

    Returns:
        bool: True if ETF
    """
    # Check quote type first (most reliable)
    if quote_type and quote_type.lower() == 'etf':
        return True

    if not company_name:
        company_name = ""

    # ETF indicators in company name
    etf_indicators = ['etf', 'fund', 'trust', 'spdr', 'ishares', 'vanguard', 'invesco', 'proshares']
    name_lower = company_name.lower()

    # Known ETF symbols in KLMN 800
    known_etfs = ['SPY', 'QQQ', 'IWM', 'VTI', 'TLT', 'XLF', 'XLE', 'XLK', 'XLI', 'XLV',
                  'XLP', 'XLU', 'GLD', 'SLV', 'USO', 'EEM', 'EFA', 'HYG', 'LQD', 'JETS',
                  'XBI', 'ARKK', 'XLB', 'XLC', 'XLY', 'XLRE', 'SMH', 'SOXX', 'DIA', 'VNQ',
                  'KRE', 'OIH', 'XOP', 'NLR', 'KWEB', 'FXI',
                  'VIX']  # Index - not tradeable, collected for market regime

    if symbol in known_etfs:
        return True

    if any(indicator in name_lower for indicator in etf_indicators):
        return True

    return False


# =============================================================================
# API Functions
# =============================================================================

def fetch_quotes_batch(symbols, token):
    """Fetch quotes for a batch of symbols using Tradier quotes endpoint

    Args:
        symbols: List of symbols (up to 100)
        token: Tradier API token

    Returns:
        dict: {symbol: quote_data} or empty dict on failure
    """
    url = "https://api.tradier.com/v1/markets/quotes"
    headers = {
        "Authorization": "Bearer {}".format(token),
        "Accept": "application/json"
    }
    params = {"symbols": ",".join(symbols)}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code != 200:
            logging.error("Quotes API HTTP {}: {}".format(response.status_code, response.text[:200]))
            queue_error('metadata_tradier_api_error', context={
                'endpoint': 'quotes',
                'status_code': response.status_code,
                'batch_symbols': symbols[:5],
                'error_message': response.text[:200]
            }, severity='ERROR')
            return {}

        data = response.json()
        quotes = data.get('quotes', {})

        results = {}

        # Handle single quote vs list
        quote_data = quotes.get('quote', [])
        if isinstance(quote_data, dict):
            quote_data = [quote_data]

        for quote in quote_data:
            if isinstance(quote, dict) and 'symbol' in quote:
                results[quote['symbol']] = quote

        return results

    except requests.exceptions.Timeout:
        logging.error("Quotes API timeout for batch: {}...".format(symbols[:3]))
        queue_error('metadata_tradier_api_error', context={
            'endpoint': 'quotes',
            'error_message': 'Timeout',
            'batch_symbols': symbols[:5]
        }, severity='ERROR')
        return {}
    except Exception as e:
        logging.error("Quotes API error: {}".format(e))
        queue_error('metadata_tradier_api_error', context={
            'endpoint': 'quotes',
            'error_message': str(e),
            'batch_symbols': symbols[:5]
        }, severity='ERROR')
        return {}


def fetch_fundamentals_batch(symbols, token):
    """Fetch fundamentals for a batch of symbols using Tradier beta endpoint

    Args:
        symbols: List of symbols (max 10 recommended)
        token: Tradier API token

    Returns:
        dict: {symbol: parsed_fundamentals} or empty dict on failure
    """
    url = "https://api.tradier.com/beta/markets/fundamentals/company"
    headers = {
        "Authorization": "Bearer {}".format(token),
        "Accept": "application/json"
    }
    params = {"symbols": ",".join(symbols)}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        # Check for endpoint removal
        if response.status_code == 404:
            logging.critical("Fundamentals beta endpoint returned 404 - may have been removed!")
            queue_error('metadata_fundamentals_endpoint_removed', context={
                'url': url,
                'status_code': 404,
                'action_needed': 'Check Tradier API docs for replacement endpoint'
            }, severity='CRITICAL')
            return {}

        if response.status_code != 200:
            logging.error("Fundamentals API HTTP {}: {}".format(response.status_code, response.text[:200]))
            queue_error('metadata_tradier_api_error', context={
                'endpoint': 'fundamentals',
                'status_code': response.status_code,
                'batch_symbols': symbols[:5],
                'error_message': response.text[:200]
            }, severity='ERROR')
            return {}

        data = response.json()

        # Parse the nested response structure
        results = {}
        items = data if isinstance(data, list) else data.get('data', [])

        for item in items:
            if not isinstance(item, dict):
                continue

            # Symbol might be at root level or in request field
            symbol = item.get('symbol') or item.get('request')
            if not symbol:
                continue

            # Results is a list of tables
            item_results = item.get('results', [])
            parsed = {}

            for table in item_results:
                if not isinstance(table, dict):
                    continue

                tables = table.get('tables', {})
                if not tables:
                    continue

                # Extract asset_classification (sector/industry codes)
                asset_class = tables.get('asset_classification')
                if asset_class:
                    parsed['asset_classification'] = asset_class

                # Extract share_class_profile (market cap)
                share_profile = tables.get('share_class_profile')
                if share_profile:
                    parsed['share_class_profile'] = share_profile

                # Extract company_profile
                company_profile = tables.get('company_profile')
                if company_profile:
                    parsed['company_profile'] = company_profile

            if parsed:
                results[symbol] = parsed

        return results

    except requests.exceptions.Timeout:
        logging.error("Fundamentals API timeout for batch: {}...".format(symbols[:3]))
        return {}
    except Exception as e:
        logging.error("Fundamentals API error: {}".format(e))
        return {}


def calculate_beta(db_path, symbol, lookback=60):
    """Calculate beta from historical_prices using covariance method

    Beta = Cov(symbol, SPY) / Var(SPY)

    Args:
        db_path: Path to database
        symbol: Stock symbol
        lookback: Number of days for calculation (default 60)

    Returns:
        float or None: Beta value (4 decimal places) or None if insufficient data
    """
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()

            # Get daily returns for symbol and SPY
            # Using (close - prev_close) / prev_close for returns
            query = '''
                WITH symbol_prices AS (
                    SELECT trade_date, close_price,
                           LAG(close_price) OVER (ORDER BY trade_date) as prev_close
                    FROM historical_prices
                    WHERE symbol = ?
                    ORDER BY trade_date DESC
                    LIMIT ?
                ),
                spy_prices AS (
                    SELECT trade_date, close_price,
                           LAG(close_price) OVER (ORDER BY trade_date) as prev_close
                    FROM historical_prices
                    WHERE symbol = 'SPY'
                    ORDER BY trade_date DESC
                    LIMIT ?
                ),
                returns AS (
                    SELECT
                        s.trade_date,
                        (s.close_price - s.prev_close) / NULLIF(s.prev_close, 0) as symbol_return,
                        (m.close_price - m.prev_close) / NULLIF(m.prev_close, 0) as spy_return
                    FROM symbol_prices s
                    JOIN spy_prices m ON s.trade_date = m.trade_date
                    WHERE s.prev_close IS NOT NULL
                      AND m.prev_close IS NOT NULL
                      AND s.prev_close > 0
                      AND m.prev_close > 0
                )
                SELECT
                    AVG(symbol_return * spy_return) - AVG(symbol_return) * AVG(spy_return) as covariance,
                    AVG(spy_return * spy_return) - AVG(spy_return) * AVG(spy_return) as spy_variance,
                    COUNT(*) as data_points
                FROM returns
            '''

            cursor.execute(query, (symbol, lookback + 1, lookback + 1))
            row = cursor.fetchone()

            if row and row[2] and row[2] >= 20:  # Need at least 20 data points
                covariance = row[0]
                spy_variance = row[1]

                if covariance is not None and spy_variance and spy_variance > 0:
                    beta = covariance / spy_variance
                    return round(beta, 4)

            return None

    except Exception as e:
        logging.debug("Beta calculation failed for {}: {}".format(symbol, e))
        return None


def check_spy_data(db_path, min_points=30):
    """Check if SPY has sufficient historical data for beta calculation

    Args:
        db_path: Path to database
        min_points: Minimum required data points (default 30)

    Returns:
        tuple: (has_sufficient_data: bool, data_point_count: int)
    """
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM historical_prices
                WHERE symbol = 'SPY'
                  AND trade_date >= date('now', '-90 days')
            ''')
            count = cursor.fetchone()[0]
            return (count >= min_points, count)
    except Exception as e:
        logging.error("Failed to check SPY data: {}".format(e))
        return (False, 0)


# =============================================================================
# Database Functions (reused from av_symbol_metadata.py)
# =============================================================================

def ensure_table_schema(db_path):
    """Ensure symbol_metadata table has all required columns"""
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()

            # Get current columns
            cursor.execute("PRAGMA table_info(symbol_metadata)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            # Column definitions: name -> SQL type
            column_definitions = {
                'industry': 'TEXT',
                'is_etf': 'BOOLEAN DEFAULT FALSE',
                'beta': 'REAL',
                'financial_health_grade': 'TEXT',
                'growth_grade': 'TEXT',
                'profitability_grade': 'TEXT',
                'week_52_high': 'REAL',
                'week_52_low': 'REAL',
                'employee_count': 'INTEGER',
                'market_cap': 'INTEGER',
                'avg_volume': 'INTEGER',
            }

            # Add missing columns
            for column, col_type in column_definitions.items():
                if column not in existing_columns:
                    cursor.execute('ALTER TABLE symbol_metadata ADD COLUMN {} {}'.format(column, col_type))
                    logging.info("Added column: {}".format(column))

            conn.commit()

    except Exception as e:
        logging.error("Error ensuring table schema: {}".format(e))


def insert_metadata_records(db_path, metadata_records):
    """Insert metadata records into symbol_metadata table

    IMPORTANT: Uses UPDATE to preserve archive_db column values.
    Falls back to INSERT for new symbols only.
    """
    successful = 0
    failed = 0

    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()

            for record in metadata_records:
                try:
                    # First try UPDATE to preserve archive_db
                    cursor.execute('''
                        UPDATE symbol_metadata
                        SET company_name = ?,
                            sector = ?,
                            industry = ?,
                            market_cap_category = ?,
                            liquidity_tier = ?,
                            is_etf = ?,
                            beta = ?,
                            options_available = ?,
                            updated_at = ?,
                            financial_health_grade = ?,
                            growth_grade = ?,
                            profitability_grade = ?,
                            week_52_high = ?,
                            week_52_low = ?,
                            employee_count = ?,
                            market_cap = ?,
                            avg_volume = ?
                        WHERE symbol = ?
                    ''', (
                        record['company_name'],
                        record['sector'],
                        record['industry'],
                        record['market_cap_category'],
                        record['liquidity_tier'],
                        record['is_etf'],
                        record['beta'],
                        record['options_available'],
                        record['updated_at'],
                        record.get('financial_health_grade'),
                        record.get('growth_grade'),
                        record.get('profitability_grade'),
                        record.get('week_52_high'),
                        record.get('week_52_low'),
                        record.get('employee_count'),
                        record.get('market_cap'),
                        record.get('avg_volume'),
                        record['symbol']
                    ))

                    # If no rows updated, symbol doesn't exist - INSERT it
                    if cursor.rowcount == 0:
                        cursor.execute('''
                            INSERT INTO symbol_metadata
                            (symbol, company_name, sector, industry, market_cap_category,
                             liquidity_tier, is_etf, beta, options_available, updated_at,
                             financial_health_grade, growth_grade, profitability_grade,
                             week_52_high, week_52_low, employee_count, market_cap, avg_volume)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            record['symbol'],
                            record['company_name'],
                            record['sector'],
                            record['industry'],
                            record['market_cap_category'],
                            record['liquidity_tier'],
                            record['is_etf'],
                            record['beta'],
                            record['options_available'],
                            record['updated_at'],
                            record.get('financial_health_grade'),
                            record.get('growth_grade'),
                            record.get('profitability_grade'),
                            record.get('week_52_high'),
                            record.get('week_52_low'),
                            record.get('employee_count'),
                            record.get('market_cap'),
                            record.get('avg_volume')
                        ))

                    successful += 1

                except sqlite3.Error as e:
                    logging.error("Database error for {}: {}".format(record['symbol'], e))
                    failed += 1

            conn.commit()
            logging.info("Database operations complete: {} successful, {} failed".format(successful, failed))

    except Exception as e:
        logging.error("Database connection error: {}".format(e))
        queue_error('metadata_db_write_failed', context={
            'successful': successful,
            'failed': failed,
            'error': str(e)
        }, severity='CRITICAL')
        return 0, len(metadata_records)

    return successful, failed


# =============================================================================
# Discovery Mode
# =============================================================================

def discover_morningstar_codes(symbols, token):
    """Discovery mode: collect all unique Morningstar codes from API

    Args:
        symbols: List of symbols to scan
        token: Tradier API token

    Prints Python-pasteable mapping dictionaries
    """
    from collections import defaultdict

    print("=" * 70)
    print("MORNINGSTAR CODE DISCOVERY")
    print("=" * 70)
    print("Discovering all unique Morningstar sector/industry codes from Tradier")
    print("")
    print("Total symbols: {}".format(len(symbols)))
    print("")

    # Track discovered codes
    sector_codes = defaultdict(list)
    industry_codes = defaultdict(list)

    batch_size = FUNDAMENTALS_BATCH_SIZE
    total_batches = (len(symbols) + batch_size - 1) // batch_size
    success_count = 0
    fail_count = 0

    print("Fetching fundamentals in {} batches of {}...".format(total_batches, batch_size))
    print("")

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        batch_num = (i // batch_size) + 1

        print("  Batch {}/{}: {}...".format(batch_num, total_batches, batch[0]), end=" ")

        results = fetch_fundamentals_batch(batch, token)

        batch_success = 0
        for symbol in batch:
            if symbol in results:
                data = results[symbol]
                asset_class = data.get('asset_classification', {})

                sector_code = asset_class.get('morningstar_sector_code')
                industry_code = asset_class.get('morningstar_industry_code')

                if sector_code:
                    if len(sector_codes[sector_code]) < 3:
                        sector_codes[sector_code].append(symbol)

                if industry_code:
                    if len(industry_codes[industry_code]) < 3:
                        industry_codes[industry_code].append(symbol)

                batch_success += 1
                success_count += 1
            else:
                fail_count += 1

        print("{}/{} symbols".format(batch_success, len(batch)))
        time.sleep(0.5)

    print("")
    print("=" * 70)
    print("DISCOVERY RESULTS")
    print("=" * 70)
    print("Successful: {}".format(success_count))
    print("Failed: {}".format(fail_count))
    print("")

    print("MORNINGSTAR_SECTOR_MAP = {")
    for code in sorted(sector_codes.keys()):
        examples = sector_codes[code]
        print("    {}: 'TODO',  # Examples: {}".format(code, ', '.join(examples)))
    print("}")
    print("")

    print("MORNINGSTAR_INDUSTRY_MAP = {")
    for code in sorted(industry_codes.keys()):
        examples = industry_codes[code]
        print("    {}: 'TODO',  # Examples: {}".format(code, ', '.join(examples)))
    print("}")
    print("")

    print("Total unique sector codes: {}".format(len(sector_codes)))
    print("Total unique industry codes: {}".format(len(industry_codes)))


# =============================================================================
# Main Collection
# =============================================================================

def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Tradier Symbol Metadata Collector')
    parser.add_argument('--no-interaction', action='store_true',
                       help='Run without user input prompts (for automated execution)')
    parser.add_argument('--symbols', type=str,
                       help='Comma-separated list of symbols (e.g., "AAPL,MSFT,NVDA")')
    parser.add_argument('--discover-codes', action='store_true',
                       help='Discovery mode: print all Morningstar codes found')
    args = parser.parse_args()

    print("Tradier Symbol Metadata Collector")
    print("=" * 50)
    print("Fetches company metadata using Tradier Fundamentals + Quotes APIs")
    print("Sources: Morningstar sector/industry, market cap, avg volume, beta")

    # Wait for user confirmation
    if not args.no_interaction:
        input("\nPress Enter to begin collection...")

    # Set up logging
    log_dir = Path(__file__).parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'symbol_metadata_collector.log'

    # Split formatters: short for console, full for log file
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler]
    )

    try:
        # Load configuration
        config = load_config()
        if not config:
            logging.error("Failed to load configuration")
            return 1

        tradier_token = config.get('tradier', {}).get('api_key')
        if not tradier_token:
            logging.error("Tradier API key not found in config")
            return 1

        logging.info("Configuration loaded")

        # Get symbols
        if args.symbols:
            symbols = [s.strip().upper() for s in args.symbols.split(',')]
            logging.info("Using {} symbols from command line: {}".format(
                len(symbols), ', '.join(symbols[:5]) + ('...' if len(symbols) > 5 else '')))
        else:
            symbols = get_klmn_800_symbols()
            if not symbols:
                logging.error("Failed to load KLMN 800 symbols")
                return 1
            logging.info("Loaded {} KLMN symbols".format(len(symbols)))

        # Discovery mode
        if args.discover_codes:
            discover_morningstar_codes(symbols, tradier_token)
            return 0

        # Get database path
        db_path = get_database_path()

        # Ensure database schema is up to date
        ensure_table_schema(db_path)
        logging.info("Database schema verified")

        print("")
        logging.info("Collection pipeline starting...")
        logging.info("  Total symbols: {}".format(len(symbols)))
        logging.info("  Estimated time: ~60 seconds")

        # Track unmapped codes
        unmapped_codes = set()
        affected_symbols = []

        # =================================================================
        # Part 1: Fetch quotes (company_name, avg_volume, is_etf)
        # =================================================================
        logging.info("Part 1: Fetching quotes...")
        quotes_data = {}
        quotes_errors = []

        for i in range(0, len(symbols), QUOTES_BATCH_SIZE):
            batch = symbols[i:i+QUOTES_BATCH_SIZE]
            batch_num = (i // QUOTES_BATCH_SIZE) + 1
            total_batches = (len(symbols) + QUOTES_BATCH_SIZE - 1) // QUOTES_BATCH_SIZE

            results = fetch_quotes_batch(batch, tradier_token)
            quotes_data.update(results)

            success = len([s for s in batch if s in results])
            logging.info("  Batch {}/{}: {} symbols... {}/{} OK".format(batch_num, total_batches, len(batch), success, len(batch)))

            for symbol in batch:
                if symbol not in results:
                    quotes_errors.append(symbol)

            time.sleep(0.3)

        logging.info("  Quotes complete: {}/{} symbols".format(len(quotes_data), len(symbols)))

        # =================================================================
        # Part 2: Fetch fundamentals (sector, industry, market_cap)
        # =================================================================
        print("")
        logging.info("Part 2: Fetching fundamentals...")
        fundamentals_data = {}
        fundamentals_errors = []

        for i in range(0, len(symbols), FUNDAMENTALS_BATCH_SIZE):
            batch = symbols[i:i+FUNDAMENTALS_BATCH_SIZE]
            batch_num = (i // FUNDAMENTALS_BATCH_SIZE) + 1
            total_batches = (len(symbols) + FUNDAMENTALS_BATCH_SIZE - 1) // FUNDAMENTALS_BATCH_SIZE

            results = fetch_fundamentals_batch(batch, tradier_token)

            # Retry failed batches once
            if not results:
                time.sleep(2)
                results = fetch_fundamentals_batch(batch, tradier_token)

            fundamentals_data.update(results)

            success = len([s for s in batch if s in results])
            # Report every 10 batches (100 symbols) to match quotes rhythm
            if batch_num % 10 == 0 or batch_num == total_batches:
                symbols_done = min(batch_num * FUNDAMENTALS_BATCH_SIZE, len(symbols))
                logging.info("  Progress: {}/{} symbols... {}/{} OK".format(
                    symbols_done, len(symbols), len(fundamentals_data), symbols_done))

            for symbol in batch:
                if symbol not in results:
                    fundamentals_errors.append(symbol)

            time.sleep(0.5)

        logging.info("  Fundamentals complete: {}/{} symbols".format(len(fundamentals_data), len(symbols)))

        # =================================================================
        # Part 3: Calculate beta from historical_prices
        # =================================================================
        print("")
        logging.info("Part 3: Calculating beta from historical prices...")

        # Check SPY data availability
        spy_ok, spy_count = check_spy_data(db_path, min_points=30)

        if not spy_ok:
            logging.info("  Insufficient SPY data ({} points) - skipping beta calculations".format(spy_count))
            queue_error('metadata_beta_calculation_skipped', context={
                'reason': 'Insufficient SPY data',
                'spy_datapoints': spy_count,
                'required': 30
            }, severity='WARNING')
            beta_data = {}
        else:
            logging.info("  SPY has {} data points - calculating betas...".format(spy_count))
            beta_data = {}
            beta_success = 0

            for i, symbol in enumerate(symbols):
                beta = calculate_beta(db_path, symbol, lookback=60)
                if beta is not None:
                    beta_data[symbol] = beta
                    beta_success += 1

                if (i + 1) % 100 == 0:
                    logging.info("  Progress: {}/{} symbols... {}/{} OK".format(i + 1, len(symbols), beta_success, i + 1))

            logging.info("  Beta complete: {}/{} symbols".format(beta_success, len(symbols)))

        # =================================================================
        # Part 4: Build metadata records
        # =================================================================
        print("")
        logging.info("Part 4: Building metadata records...")
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        metadata_records = []

        for symbol in symbols:
            quote = quotes_data.get(symbol, {})
            fundamentals = fundamentals_data.get(symbol, {})
            asset_class = fundamentals.get('asset_classification', {})
            share_profile = fundamentals.get('share_class_profile', {})
            company_profile = fundamentals.get('company_profile', {})

            # Company name from quotes
            company_name = quote.get('description', 'N/A')

            # Sector from Morningstar code
            sector_code = asset_class.get('morningstar_sector_code')
            sector = MORNINGSTAR_SECTOR_MAP.get(sector_code, 'N/A')

            # Industry from Morningstar code
            industry_code = asset_class.get('morningstar_industry_code')
            industry = MORNINGSTAR_INDUSTRY_MAP.get(industry_code, 'N/A')

            # Track unmapped codes
            if industry_code and industry == 'N/A':
                unmapped_codes.add(industry_code)
                affected_symbols.append(symbol)

            # Market cap from fundamentals (raw value)
            market_cap = share_profile.get('market_cap', 0)
            if market_cap is None:
                market_cap = 0

            # Average volume from quotes (raw value)
            avg_volume = quote.get('average_volume', 0)
            if avg_volume is None:
                avg_volume = 0

            # ETF detection
            quote_type = quote.get('type', '')
            is_etf = detect_etf(company_name, symbol, quote_type)

            # Beta from calculation
            beta = beta_data.get(symbol)

            # Categories (derived)
            market_cap_category = categorize_market_cap(market_cap)
            liquidity_tier = categorize_liquidity_tier(avg_volume)

            # Morningstar grades from fundamentals
            financial_health_grade = asset_class.get('financial_health_grade')
            growth_grade = asset_class.get('growth_grade')
            profitability_grade = asset_class.get('profitability_grade')

            # 52-week range from quotes
            week_52_high = quote.get('week_52_high')
            week_52_low = quote.get('week_52_low')

            # Employee count from company profile
            employee_count = company_profile.get('total_employee_number')

            metadata_records.append({
                'symbol': symbol,
                'company_name': company_name,
                'sector': sector,
                'industry': industry,
                'market_cap_category': market_cap_category,
                'liquidity_tier': liquidity_tier,
                'is_etf': is_etf,
                'beta': beta,
                'options_available': True,
                'updated_at': current_time,
                # New fields
                'financial_health_grade': financial_health_grade,
                'growth_grade': growth_grade,
                'profitability_grade': profitability_grade,
                'week_52_high': week_52_high,
                'week_52_low': week_52_low,
                'employee_count': employee_count,
                'market_cap': market_cap,
                'avg_volume': avg_volume
            })

        logging.info("  Built {} metadata records".format(len(metadata_records)))

        # Report unmapped codes
        if unmapped_codes:
            logging.warning("Unmapped Morningstar industry codes: {}".format(sorted(unmapped_codes)))
            queue_error('metadata_unmapped_industry_codes', context={
                'unmapped_codes': sorted(unmapped_codes),
                'symbols_affected': affected_symbols[:10],
                'action_needed': 'Add codes to MORNINGSTAR_INDUSTRY_MAP'
            }, severity='ERROR')

        # =================================================================
        # Part 5: Insert to database
        # =================================================================
        print("")
        logging.info("Part 5: Writing to database...")
        successful, failed = insert_metadata_records(db_path, metadata_records)

        logging.info("  Database write: {} successful, {} failed".format(successful, failed))

        # Check for total failure
        total_attempted = len(symbols)
        total_failed = len(quotes_errors) + len(fundamentals_errors) + failed
        failure_rate = total_failed / total_attempted if total_attempted > 0 else 0

        if failure_rate > 0.20:
            logging.error("High failure rate: {:.1%}".format(failure_rate))
            queue_error('metadata_collection_total_failure', context={
                'symbols_attempted': total_attempted,
                'symbols_failed': total_failed,
                'failure_rate': round(failure_rate, 3),
                'quotes_errors': len(quotes_errors),
                'fundamentals_errors': len(fundamentals_errors),
                'db_errors': failed,
                'sample_errors': (quotes_errors + fundamentals_errors)[:5]
            }, severity='CRITICAL')

        # =================================================================
        # Summary
        # =================================================================
        print("\n" + "=" * 50)
        print("COLLECTION SUMMARY")
        print("=" * 50)
        logging.info("  Symbols processed: {}".format(len(symbols)))
        logging.info("  Quotes fetched: {}".format(len(quotes_data)))
        logging.info("  Fundamentals fetched: {}".format(len(fundamentals_data)))
        logging.info("  Betas calculated: {}".format(len(beta_data)))
        logging.info("  Database writes: {} successful, {} failed".format(successful, failed))
        if unmapped_codes:
            logging.info("  Unmapped industry codes: {}".format(len(unmapped_codes)))
        print("")
        logging.info("  Database: {}".format(db_path))
        logging.info("  Log file: {}".format(log_file))

        # Show failed symbols so operator can investigate
        if quotes_errors or fundamentals_errors:
            logging.info("Failed symbols:")
            if quotes_errors:
                logging.info("  Quotes failed ({}): {}".format(
                    len(quotes_errors), ", ".join(sorted(quotes_errors))))
            if fundamentals_errors:
                logging.info("  Fundamentals failed ({}): {}".format(
                    len(fundamentals_errors), ", ".join(sorted(fundamentals_errors))))
        return 0

    except KeyboardInterrupt:
        print("\nCollection cancelled by user")
        return 130
    except Exception as e:
        logging.error("Collection failed: {}".format(e))
        import traceback
        logging.error(traceback.format_exc())
        queue_error('metadata_collection_fatal_error', context={
            'exception_type': type(e).__name__,
            'error_message': str(e)
        }, severity='ERROR')
        return 1

    finally:
        if not args.no_interaction:
            input("\nPress Enter to exit...")


if __name__ == "__main__":
    exit(main())
