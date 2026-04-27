#!/usr/bin/env python3
"""
Advisor-Specific Data Gathering

Each advisor type gets specialized data from their focus tables.
Includes schema documentation so AI understands the data structure.

Author: Ben
Date: 2025-10-09
"""

import os
import sys
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from morning_view.tui_data import get_data

# ========== Schema Documentation ==========

SCHEMA_DOCS = {
    'news_symbol_sentiment': """
    NEWS & SENTIMENT DATA SCHEMA:
    - article_date: When news was published
    - relevance_score: How relevant to symbol (0-1, higher = more relevant)
    - symbol_sentiment_score: Sentiment polarity (-1 to +1, negative to positive)
    - symbol_sentiment_label: Categorical sentiment (Bearish, Neutral, Bullish, etc.)
    - topics_collected: Main topics/themes in article
    """,

    'flow_alerts': """
    OPTIONS FLOW ALERTS SCHEMA:
    - significance_score: Alert importance (6-10, higher = more significant)
    - flow_percentage: % of daily volume in this contract
    - volume_surprise_factor: Current volume vs historical average
    - premium_value: Dollar value of position
    - moneyness: ITM/ATM/OTM status
    - dte: Days to expiration
    - max_prof_*d_pct: Maximum profit achieved over N days (if tracked)
    - final_quality_score: Retrospective evaluation of alert quality
    - alert_reason: Why this triggered (unusual_volume, sweep, block_trade, etc.)
    """,

    'option_contracts': """
    DAILY OPEN INTEREST TRACKING SCHEMA:
    - open_interest: Current open interest for contract
    - oi_change: Daily change in open interest
    - oi_momentum_5d: 5-day OI momentum rate
    - oi_build_start_date: When OI buildup began
    - delta/gamma/theta/vega: Greeks for risk assessment
    - iv_percentile_20day: IV relative to 20-day range (0-100)
    - close_price: Current option price
    - underlying_price: Stock price
    - dte: DTE remaining
    - moneyness: ITM/ATM/OTM status
    """,

    'earnings_upcoming': """
    EARNINGS CALENDAR SCHEMA:
    - earnings_date: Date of earnings report
    - earnings_days_ahead: Days until earnings
    - straddle_expected_move_pct: Implied move from ATM straddle pricing
    - historical_avg_move_pct: Average historical earnings move
    - move_difference_pct: Gap between expected and historical
    - earnings_time: Before market open (BMO) or After close (AMC)
    - earnings_play_signal: BUY_VOLATILITY or SELL_VOLATILITY
    """,

    'option_contracts': """
    DAILY OPEN INTEREST CHANGES SCHEMA:
    - net_oi_change: Net change in OI (calls - puts)
    - oi_momentum_score: Rate of OI change over time
    - smart_money_timing: PREDICTIVE (positioned before move) vs CHASING (after move)
    - positioning_type: Type of positioning detected
    """
}

# ========== General Analyst (Morning Views Core) ==========

def gather_general_data(symbol: str) -> Dict:
    """Gather core morning views data for General Analyst

    Focus: Morning views summary, basic OI metrics, market context

    Args:
        symbol: Stock symbol

    Returns:
        dict: Data dictionary for prompt building
    """
    data = get_data()

    return {
        'overview': data.get_symbol_overview(symbol),
        'oi_timing': data.get_oi_timing(symbol, limit=10),
        'oi_distribution': data.get_oi_distribution(symbol),
        'market_context': data.get_market_context(),
        'schema_context': "",  # No additional schema needed
        'additional_data': {}
    }


# ========== Advanced Detective (Deep Dive) ==========

def gather_detective_data(symbol: str) -> Dict:
    """Gather deep analysis data for Advanced Detective

    Focus: Morning views + flow alerts + tracked contracts + historical OI

    Args:
        symbol: Stock symbol

    Returns:
        dict: Data dictionary for prompt building
    """
    data = get_data()
    base_data = gather_general_data(symbol)

    # Get database connection
    config_path = Path(__file__).parent / 'config.json'
    import json
    with open(config_path, 'r') as f:
        config = json.load(f)

    db_path = Path(__file__).parent.parent / config['database']['path']
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get flow alerts for this symbol (last 30 days)
    cursor.execute("""
        SELECT trade_date, strike, option_type, expiration_date,
               significance_score, flow_percentage, volume_surprise_factor,
               premium_value, moneyness, dte,
               max_prof_7d_pct, max_prof_14d_pct,
               final_quality_score, alert_reason
        FROM flow_alerts
        WHERE symbol = ?
          AND trade_date >= date('now', '-30 days')
        ORDER BY trade_date DESC, significance_score DESC
        LIMIT 20
    """, (symbol,))

    flow_alerts = [dict(row) for row in cursor.fetchall()]

    # Get tracked contracts from option_contracts joined with flow alerts
    cursor.execute("""
        SELECT oi.trade_date, oi.strike, oi.option_type, oi.expiration_date,
               oi.delta, oi.iv_percentile_20day,
               oi.oi_momentum_5d as oi_momentum_contract_specific,
               oi.last_price, oi.underlying_price,
               fa.first_alert_date,
               fa.first_alert_price,
               CASE
                   WHEN fa.first_alert_price IS NOT NULL AND oi.last_price IS NOT NULL
                   THEN ROUND((oi.last_price - fa.first_alert_price) / fa.first_alert_price * 100, 2)
                   ELSE NULL
               END as price_change_since_alert_percent,
               CAST(julianday(oi.trade_date) - julianday(fa.first_alert_date) AS INTEGER) as days_tracked
        FROM option_contracts oi
        LEFT JOIN (
            SELECT symbol, strike, expiration_date, option_type,
                   MIN(trade_date) as first_alert_date,
                   AVG(underlying_price) as first_alert_price
            FROM flow_alerts
            WHERE symbol = ?
              AND trade_date >= date('now', '-30 days')
            GROUP BY symbol, strike, expiration_date, option_type
        ) fa ON oi.symbol = fa.symbol
            AND oi.strike = fa.strike
            AND oi.expiration_date = fa.expiration_date
            AND oi.option_type = fa.option_type
        WHERE oi.symbol = ?
          AND oi.trade_date = (SELECT MAX(trade_date) FROM option_contracts WHERE symbol = ?)
          AND fa.first_alert_date IS NOT NULL
        ORDER BY ABS(COALESCE(price_change_since_alert_percent, 0)) DESC
        LIMIT 15
    """, (symbol, symbol, symbol))

    tracked_contracts = [dict(row) for row in cursor.fetchall()]

    # Get available option chain summary (to prevent hallucinations)
    cursor.execute("""
        SELECT DISTINCT expiration_date
        FROM option_contracts
        WHERE symbol = ?
          AND trade_date = (SELECT MAX(trade_date) FROM option_contracts WHERE symbol = ?)
        ORDER BY expiration_date
    """, (symbol, symbol))

    available_expirations = [row['expiration_date'] for row in cursor.fetchall()]

    # Get actively traded strikes per expiration
    cursor.execute("""
        SELECT expiration_date,
               GROUP_CONCAT(DISTINCT CAST(strike AS INTEGER)) as strikes
        FROM option_contracts
        WHERE symbol = ?
          AND trade_date = (SELECT MAX(trade_date) FROM option_contracts WHERE symbol = ?)
        GROUP BY expiration_date
        ORDER BY expiration_date
    """, (symbol, symbol))

    option_chain_summary = [dict(row) for row in cursor.fetchall()]

    conn.close()

    base_data['additional_data'] = {
        'flow_alerts': flow_alerts,
        'tracked_contracts': tracked_contracts,
        'available_expirations': available_expirations,
        'option_chain_summary': option_chain_summary
    }

    base_data['schema_context'] = (
        SCHEMA_DOCS['flow_alerts'] + "\n\n" +
        SCHEMA_DOCS['option_contracts']
    )

    return base_data


# ========== Risk Analyst (Position & Timing) ==========

def gather_risk_data(symbol: str) -> Dict:
    """Gather risk assessment data for Risk Analyst

    Focus: Flow alerts, tracked contracts, greeks, earnings timing

    Args:
        symbol: Stock symbol

    Returns:
        dict: Data dictionary for prompt building
    """
    data = get_data()
    base_data = gather_general_data(symbol)

    # Get database connection
    config_path = Path(__file__).parent / 'config.json'
    import json
    with open(config_path, 'r') as f:
        config = json.load(f)

    db_path = Path(__file__).parent.parent / config['database']['path']
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get recent high-quality flow alerts
    cursor.execute("""
        SELECT trade_date, strike, option_type, expiration_date,
               underlying_price, dte, moneyness,
               significance_score, premium_value, flow_percentage,
               max_prof_7d_pct, max_prof_14d_pct,
               final_quality_score
        FROM flow_alerts
        WHERE symbol = ?
          AND trade_date >= date('now', '-14 days')
          AND significance_score >= 7.0
        ORDER BY trade_date DESC, significance_score DESC
        LIMIT 10
    """, (symbol,))

    high_quality_alerts = [dict(row) for row in cursor.fetchall()]

    # Get contracts from v_option_comparison with calculated risk metrics
    cursor.execute("""
        SELECT symbol, trade_date, strike, option_type, expiration_date,
               dte, moneyness, last_price, underlying_price,
               delta, gamma, theta, vega, IV, iv_percentile,
               open_interest, volume,
               breakeven_price, breakeven_move_pct,
               delta_per_dollar, theta_decay_dollars,
               intrinsic_value, extrinsic_value,
               required_move_to_strike_pct, time_advantage_ratio
        FROM v_option_comparison
        WHERE symbol = ?
          AND trade_date = (SELECT MAX(trade_date) FROM option_contracts WHERE symbol = ?)
        ORDER BY trade_date DESC
        LIMIT 20
    """, (symbol, symbol))

    risk_contracts = [dict(row) for row in cursor.fetchall()]

    # Get earnings timing
    cursor.execute("""
        SELECT earnings_date, earnings_days_ahead,
               straddle_expected_move_pct, historical_avg_move_pct,
               move_difference_pct, earnings_time,
               earnings_play_signal
        FROM earnings_upcoming
        WHERE symbol = ?
    """, (symbol,))

    earnings = cursor.fetchone()
    earnings_info = dict(earnings) if earnings else None

    conn.close()

    base_data['additional_data'] = {
        'high_quality_alerts': high_quality_alerts,
        'risk_contracts': risk_contracts,
        'earnings_info': earnings_info
    }

    base_data['schema_context'] = (
        SCHEMA_DOCS['flow_alerts'] + "\n\n" +
        SCHEMA_DOCS['option_contracts'] + "\n\n" +
        SCHEMA_DOCS['earnings_upcoming']
    )

    return base_data


# ========== Catalyst Hunter (News & Events) ==========

def gather_catalyst_data(symbol: str) -> Dict:
    """Gather catalyst data for Catalyst Hunter

    Focus: News sentiment, earnings, sector dynamics, market narratives
    NO access to: OI data, flow alerts, options contracts

    Args:
        symbol: Stock symbol

    Returns:
        dict: Data dictionary for prompt building
    """
    data = get_data()

    # Get database connection
    config_path = Path(__file__).parent / 'config.json'
    import json
    with open(config_path, 'r') as f:
        config = json.load(f)

    db_path = Path(__file__).parent.parent / config['database']['path']
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get market context (regime/direction only, no OI data)
    market_ctx = data.get_market_context()

    # Get recent news sentiment
    cursor.execute("""
        SELECT article_date, article_url,
               relevance_score, symbol_sentiment_score,
               symbol_sentiment_label, topics_collected
        FROM news_symbol_sentiment
        WHERE symbol = ?
          AND article_date >= date('now', '-14 days')
        ORDER BY article_date DESC, relevance_score DESC
        LIMIT 20
    """, (symbol,))

    news_sentiment = [dict(row) for row in cursor.fetchall()]

    # Get recent news articles (headlines + summaries)
    cursor.execute("""
        SELECT article_date, title, summary, source,
               overall_sentiment_score, overall_sentiment_label
        FROM news_articles
        WHERE symbols_mentioned LIKE ?
          AND article_date >= date('now', '-14 days')
        ORDER BY article_date DESC
        LIMIT 15
    """, (f'%{symbol}%',))

    news_articles = [dict(row) for row in cursor.fetchall()]

    # Get earnings info
    cursor.execute("""
        SELECT earnings_date, earnings_days_ahead,
               straddle_expected_move_pct, historical_avg_move_pct,
               move_difference_pct, earnings_time,
               earnings_play_signal
        FROM earnings_upcoming
        WHERE symbol = ?
    """, (symbol,))

    earnings = cursor.fetchone()
    earnings_info = dict(earnings) if earnings else None

    # Get symbol metadata (sector, industry)
    cursor.execute("""
        SELECT sector, industry, market_cap_category,
               liquidity_tier
        FROM symbol_metadata
        WHERE symbol = ?
    """, (symbol,))

    metadata = cursor.fetchone()
    metadata_info = dict(metadata) if metadata else None

    # Get market regime context
    cursor.execute("""
        SELECT trade_date, regime_classification, market_direction,
               spy_close, spy_change_percent,
               vix_close, vix_change_percent
        FROM market_daily_summary
        ORDER BY trade_date DESC
        LIMIT 5
    """)

    market_regime = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        'overview': None,  # No OI overview for Catalyst Hunter
        'oi_timing': None,  # No OI data
        'oi_distribution': None,  # No OI data
        'market_context': market_ctx,
        'schema_context': SCHEMA_DOCS['news_symbol_sentiment'] + "\n\n" + SCHEMA_DOCS['earnings_upcoming'],
        'additional_data': {
            'news_sentiment': news_sentiment,
            'news_articles': news_articles,
            'earnings_info': earnings_info,
            'metadata': metadata_info,
            'market_regime': market_regime
        }
    }


# ========== Factory Function ==========

def gather_advisor_data(advisor_name: str, symbol: str) -> Dict:
    """Gather data for specific advisor type

    Args:
        advisor_name: Name of advisor (from advisor_config.json)
        symbol: Stock symbol

    Returns:
        dict: Data dictionary for prompt building

    Raises:
        Exception: If advisor name not recognized
    """
    advisor_functions = {
        'General Analyst': gather_general_data,
        'Advanced Detective': gather_detective_data,
        'Risk Analyst': gather_risk_data,
        'Catalyst Hunter': gather_catalyst_data
    }

    func = advisor_functions.get(advisor_name)
    if not func:
        raise Exception(f"Unknown advisor: {advisor_name}")

    return func(symbol)


# ========== Prompt Building Helpers ==========

def format_flow_alerts(alerts: List[Dict]) -> str:
    """Format flow alerts for prompt"""
    if not alerts:
        return "No recent flow alerts"

    lines = []
    for alert in alerts:
        lines.append(
            f"  - {alert['trade_date']}: ${alert['strike']:.0f} {alert['option_type']} "
            f"exp {alert['expiration_date']} | Sig: {alert['significance_score']:.1f} | "
            f"Flow: {alert['flow_percentage']:.1f}% | Premium: ${alert['premium_value']:,.0f}"
        )

    return "\n".join(lines)


def format_news_sentiment(news: List[Dict]) -> str:
    """Format news sentiment for prompt"""
    if not news:
        return "No recent news"

    lines = []
    for item in news:
        lines.append(
            f"  - {item['article_date']}: {item['symbol_sentiment_label']} "
            f"(score: {item['symbol_sentiment_score']:.2f}, relevance: {item['relevance_score']:.2f}) "
            f"| Topics: {item.get('topics_collected', 'N/A')}"
        )

    return "\n".join(lines)


def format_news_articles(articles: List[Dict]) -> str:
    """Format news articles (headlines + summaries) for prompt"""
    if not articles:
        return "No recent articles"

    lines = []
    for article in articles:
        sentiment = f"{article.get('overall_sentiment_label', 'N/A')} ({article.get('overall_sentiment_score', 0):.2f})"
        lines.append(
            f"  - {article['article_date']} [{article.get('source', 'Unknown')}]: {article.get('title', 'No title')}\n"
            f"    Sentiment: {sentiment}\n"
            f"    Summary: {article.get('summary', 'No summary')[:150]}..."
        )

    return "\n".join(lines)


def format_tracked_contracts(contracts: List[Dict]) -> str:
    """Format tracked contracts for prompt"""
    if not contracts:
        return "No tracked contracts"

    lines = []
    for contract in contracts:
        days_tracked = contract.get('days_tracked', 0) or 0
        pnl = contract.get('price_change_since_alert_percent', 0) or 0
        delta = contract.get('delta', 0) or 0
        iv_pct = contract.get('iv_percentile_20day', 0) or 0

        lines.append(
            f"  - ${contract['strike']:.0f} {contract['option_type']} exp {contract['expiration_date']} | "
            f"Tracked {days_tracked:.0f}d | P/L: {pnl:+.1f}% | "
            f"Delta: {delta:.3f} | IV: {iv_pct:.0f}%ile"
        )

    return "\n".join(lines)


def format_risk_contracts(contracts: List[Dict]) -> str:
    """Format risk contracts from v_option_comparison for prompt"""
    if not contracts:
        return "No risk contracts"

    lines = []
    for contract in contracts:
        delta = contract.get('delta') or 0
        iv = contract.get('IV') or 0
        iv_pct = contract.get('iv_percentile') or 0
        last_price = contract.get('last_price') or 0
        breakeven_move = contract.get('breakeven_move_pct') or 0
        delta_per_dollar = contract.get('delta_per_dollar') or 0
        time_advantage = contract.get('time_advantage_ratio') or 0

        lines.append(
            f"  - ${contract['strike']:.0f} {contract['option_type']} exp {contract['expiration_date']} | "
            f"DTE: {contract['dte']}d | ${last_price:.2f} | "
            f"Delta: {delta:.3f} | IV: {iv:.2f} ({iv_pct:.0f}%ile) | "
            f"Breakeven: {breakeven_move:+.1f}% | $/Delta: {delta_per_dollar:.2f} | "
            f"TimeAdv: {time_advantage:.2f}"
        )

    return "\n".join(lines)
