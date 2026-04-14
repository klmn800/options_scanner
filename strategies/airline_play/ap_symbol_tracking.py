#!/usr/bin/env python3
"""
Airline Play - Symbol-Level Tracking
Extract and aggregate daily symbol-level metrics for airline stocks.

Purpose: Populate airline_symbol_tracking table with data from:
- historical_prices (price/volume)
- option_symbol_summary (OI aggregations)
- option_symbol_summary (IV metrics)
- earnings_calendar (earnings proximity)
- news_symbol_sentiment (sentiment scores)
- flow_alerts (alert counts)

Author: Ben & Claude
Date: 2025-10-01
"""

import sqlite3
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sys

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.symbols_klmn800 import get_specialty_list
from tools.decimal_formatter import clean_database_row
from tools.timezone_utils import now_eastern
from tools.autofix import queue_error

# Configure logging with UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_database_path() -> Path:
    """Get path to datalake.db"""
    return PROJECT_ROOT / 'data' / 'datalake.db'


def get_connection() -> sqlite3.Connection:
    """Get database connection"""
    db_path = get_database_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


def get_airline_symbols() -> List[str]:
    """Get list of airline symbols to track"""
    return get_specialty_list('airline_play')


def extract_price_volume_data(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Dict[str, Any]:
    """
    Extract price and volume data from historical_prices table.

    Returns dict with: close_price, high_price, low_price, price_change_percent, volume
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            close_price,
            high_price,
            low_price,
            change_percent as price_change_percent,
            volume
        FROM historical_prices
        WHERE symbol = ? AND trade_date = ?
    """, (symbol, trade_date))

    row = cursor.fetchone()
    if row:
        return dict(row)
    else:
        logger.warning(f"   └─ {symbol}: No historical_prices data for {trade_date}")
        return {}


def extract_oi_summary_data(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Dict[str, Any]:
    """
    Extract open interest summary data from option_symbol_summary table.

    Returns dict with OI totals, ratios, and time distributions.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            total_open_interest,
            total_call_oi,
            total_put_oi,
            put_call_ratio,
            oi_balance_text,
            oi_0_7_days,
            oi_8_21_days,
            oi_22_35_days,
            oi_36_60_days,
            oi_0_7_days_percent,
            oi_8_21_days_percent,
            oi_22_35_days_percent,
            oi_36_60_days_percent,
            call_oi_0_7_days,
            call_oi_8_21_days,
            call_oi_22_35_days,
            call_oi_36_60_days,
            call_oi_0_7_days_percent,
            call_oi_8_21_days_percent,
            call_oi_22_35_days_percent,
            call_oi_36_60_days_percent,
            put_oi_0_7_days,
            put_oi_8_21_days,
            put_oi_22_35_days,
            put_oi_36_60_days,
            put_oi_0_7_days_percent,
            put_oi_8_21_days_percent,
            put_oi_22_35_days_percent,
            put_oi_36_60_days_percent
        FROM option_symbol_summary
        WHERE symbol = ? AND trade_date = ?
    """, (symbol, trade_date))

    row = cursor.fetchone()
    if row:
        return dict(row)
    else:
        logger.warning(f"   └─ {symbol}: No option_symbol_summary data for {trade_date}")
        return {}


def extract_iv_metrics(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Dict[str, Any]:
    """
    Extract implied volatility metrics from option_symbol_summary table.

    Returns dict with IV values and percentiles by DTE bucket.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            iv_front_month,
            iv_30dte,
            iv_45dte,
            iv_60dte,
            symbol_iv_percentile_30d as iv_percentile_30d
        FROM option_symbol_summary
        WHERE symbol = ? AND trade_date = ?
    """, (symbol, trade_date))

    row = cursor.fetchone()
    if row:
        return dict(row)
    else:
        logger.warning(f"   └─ {symbol}: No option_symbol_summary data for {trade_date}")
        return {}


def calculate_earnings_proximity(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Dict[str, Any]:
    """
    Calculate earnings proximity from earnings_upcoming table.

    Returns dict with: earnings_date, earnings_days_ahead
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            earnings_date,
            julianday(earnings_date) - julianday(?) as earnings_days_ahead
        FROM earnings_upcoming
        WHERE symbol = ?
        AND earnings_date >= ?
        ORDER BY earnings_date ASC
        LIMIT 1
    """, (trade_date, symbol, trade_date))

    row = cursor.fetchone()
    if row:
        return {
            'earnings_date': row['earnings_date'],
            'earnings_days_ahead': int(row['earnings_days_ahead']) if row['earnings_days_ahead'] else None
        }
    else:
        # No upcoming earnings found
        return {
            'earnings_date': None,
            'earnings_days_ahead': None
        }


def extract_news_sentiment(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Dict[str, Any]:
    """
    Extract news sentiment from news_symbol_sentiment table.

    Returns dict with: news_sentiment_score_avg, news_sentiment, news_article_count
    """
    cursor = conn.cursor()
    # Get sentiment for the trade_date (articles from that day)
    cursor.execute("""
        SELECT
            AVG(symbol_sentiment_score) as news_sentiment_score_avg,
            COUNT(*) as news_article_count
        FROM news_symbol_sentiment
        WHERE symbol = ? AND article_date = ?
    """, (symbol, trade_date))

    row = cursor.fetchone()
    if row and row['news_article_count'] > 0:
        score_avg = row['news_sentiment_score_avg']

        # Classify sentiment based on score
        if score_avg is None:
            sentiment = 'Neutral'
        elif score_avg >= 0.35:
            sentiment = 'Bullish'
        elif score_avg >= 0.15:
            sentiment = 'Somewhat-Bullish'
        elif score_avg <= -0.35:
            sentiment = 'Bearish'
        elif score_avg <= -0.15:
            sentiment = 'Somewhat-Bearish'
        else:
            sentiment = 'Neutral'

        return {
            'news_sentiment_score_avg': score_avg,
            'news_sentiment': sentiment,
            'news_article_count': row['news_article_count']
        }
    else:
        # No news articles found for this date
        return {
            'news_sentiment_score_avg': None,
            'news_sentiment': None,
            'news_article_count': 0
        }


def calculate_alert_metrics(conn: sqlite3.Connection, symbol: str, trade_date: str) -> Dict[str, Any]:
    """
    Calculate flow alert metrics from flow_alerts table.

    Returns dict with: active_alerts_count, days_since_most_recent_alert
    """
    cursor = conn.cursor()

    # Count active alerts (not expired yet as of trade_date)
    cursor.execute("""
        SELECT COUNT(*) as active_count
        FROM flow_alerts
        WHERE symbol = ?
        AND date(alert_timestamp) <= ?
        AND date(expiration_date) >= ?
    """, (symbol, trade_date, trade_date))

    active_count = cursor.fetchone()['active_count']

    # Find most recent alert before or on trade_date
    cursor.execute("""
        SELECT
            date(alert_timestamp) as alert_date,
            julianday(?) - julianday(date(alert_timestamp)) as days_ago
        FROM flow_alerts
        WHERE symbol = ?
        AND date(alert_timestamp) <= ?
        ORDER BY alert_timestamp DESC
        LIMIT 1
    """, (trade_date, symbol, trade_date))

    recent_alert = cursor.fetchone()
    if recent_alert and recent_alert['days_ago'] is not None:
        days_since = int(recent_alert['days_ago'])
    else:
        days_since = None

    return {
        'active_alerts_count': active_count,
        'days_since_most_recent_alert': days_since
    }


def aggregate_symbol_row(symbol: str, trade_date: str,
                         price_data: Dict, oi_data: Dict, iv_data: Dict,
                         earnings_data: Dict, news_data: Dict, alert_data: Dict) -> Dict[str, Any]:
    """
    Combine all data sources into a single row for insertion.
    """
    row = {
        'symbol': symbol,
        'trade_date': trade_date,
        'analysis_timestamp': now_eastern().isoformat(),
        'last_updated_timestamp': now_eastern().isoformat()
    }

    # Merge all data dictionaries
    row.update(price_data)
    row.update(oi_data)
    row.update(iv_data)
    row.update(earnings_data)
    row.update(news_data)
    row.update(alert_data)

    return row


def insert_or_update(conn: sqlite3.Connection, row: Dict[str, Any]) -> int:
    """
    Insert or update row in airline_symbol_tracking table.

    Returns: number of rows affected
    """
    # Apply decimal formatting
    cleaned_row = clean_database_row(row)

    # Build column names and placeholders
    columns = list(cleaned_row.keys())
    placeholders = [f":{col}" for col in columns]

    # Build UPDATE clause (exclude primary keys)
    update_cols = [col for col in columns if col not in ('symbol', 'trade_date')]
    update_clause = ', '.join([f"{col} = excluded.{col}" for col in update_cols])

    sql = f"""
        INSERT INTO airline_symbol_tracking ({', '.join(columns)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT(symbol, trade_date) DO UPDATE SET
            {update_clause},
            last_updated_timestamp = datetime('now')
    """

    cursor = conn.cursor()
    cursor.execute(sql, cleaned_row)
    return cursor.rowcount


def process_symbol(conn: sqlite3.Connection, symbol: str, trade_date: str) -> bool:
    """
    Process a single symbol for the given trade date.

    Returns: True if successful, False if error occurred
    """
    try:
        # Extract data from all sources
        price_data = extract_price_volume_data(conn, symbol, trade_date)
        oi_data = extract_oi_summary_data(conn, symbol, trade_date)
        iv_data = extract_iv_metrics(conn, symbol, trade_date)
        earnings_data = calculate_earnings_proximity(conn, symbol, trade_date)
        news_data = extract_news_sentiment(conn, symbol, trade_date)
        alert_data = calculate_alert_metrics(conn, symbol, trade_date)

        # Check if we have at least price data (minimum requirement)
        if not price_data:
            logger.warning(f"   └─ {symbol}: Skipping - no price data available")
            return False

        # Aggregate into single row
        row = aggregate_symbol_row(
            symbol, trade_date,
            price_data, oi_data, iv_data,
            earnings_data, news_data, alert_data
        )

        # Insert/update
        rows_affected = insert_or_update(conn, row)

        logger.info(f"   └─ {symbol}: Tracking updated ({rows_affected} row)")
        return True

    except Exception as e:
        logger.error(f"Airline symbol tracking failed for {symbol}: {e}")
        queue_error(
            error_type='airline_symbol_tracking_failed',
            context={
                'symbol': symbol,
                'trade_date': trade_date,
                'error': str(e),
                'exception_type': type(e).__name__
            },
            severity='ERROR'
        )
        return False


def run_symbol_tracking(trade_date: Optional[str] = None, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Main function to run symbol-level tracking for airline stocks.

    Args:
        trade_date: Date to process (YYYY-MM-DD). Defaults to yesterday.
        symbols: List of symbols to process. Defaults to all airline symbols.

    Returns:
        Dict with summary statistics
    """
    # Default to yesterday if not specified
    if trade_date is None:
        yesterday = now_eastern().date() - timedelta(days=1)
        trade_date = yesterday.strftime('%Y-%m-%d')

    # Default to all airline symbols if not specified
    if symbols is None:
        symbols = get_airline_symbols()

    logger.info(f"🛫 AIRLINE TRACKING: Starting symbol extraction for {trade_date}")
    logger.info(f"   └─ Processing {len(symbols)} airline symbols")

    start_time = datetime.now()
    conn = get_connection()

    # Process each symbol
    successful = 0
    failed = 0

    for symbol in symbols:
        if process_symbol(conn, symbol, trade_date):
            successful += 1
        else:
            failed += 1

    # Commit all changes
    conn.commit()
    conn.close()

    elapsed = (datetime.now() - start_time).total_seconds()

    logger.info(f"🛫 AIRLINE TRACKING: Complete - {successful} successful, {failed} failed, {elapsed:.1f}s")

    return {
        'trade_date': trade_date,
        'symbols_processed': successful,
        'symbols_failed': failed,
        'elapsed_seconds': elapsed
    }


def main():
    """Command-line interface"""
    parser = argparse.ArgumentParser(description='Airline Play - Symbol-Level Tracking')
    parser.add_argument('--date', type=str, help='Trade date (YYYY-MM-DD). Defaults to yesterday.')
    parser.add_argument('--symbol', type=str, help='Single symbol to process (for testing)')

    args = parser.parse_args()

    # Parse symbol list
    symbols = [args.symbol.upper()] if args.symbol else None

    # Run tracking
    result = run_symbol_tracking(trade_date=args.date, symbols=symbols)

    # Exit with appropriate code
    if result['symbols_failed'] > 0:
        sys.exit(1)  # Indicate some failures occurred
    else:
        sys.exit(0)  # All successful


if __name__ == '__main__':
    main()
