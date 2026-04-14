"""
Decimal formatting utility for consistent precision across the options scanner system.

This module provides standardized decimal formatting to prevent excessive precision
in database storage and logging. All numeric values should use these formatters
before database insertion or display.

Decimal Policy:
- Prices: 2 decimal places (e.g., 123.45)
- Percentages: 2 decimal places (e.g., 12.34%)
- Greeks (delta, gamma, theta, vega): 4 decimal places (e.g., 0.1234)
- Ratios and multipliers: 4 decimal places (e.g., 1.2345)
- Scores and factors: 2 decimal places (e.g., 8.21)
- Volume/OI related: 2 decimal places for ratios, integers for counts
"""

def format_price(value):
    """
    Format price values to 2 decimal places.
    Used for: strike, bid, ask, last_price, underlying_price, etc.

    Args:
        value: Numeric value to format

    Returns:
        float: Value rounded to 2 decimal places, or None if input is None/invalid
    """
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (ValueError, TypeError):
        return None

def format_percentage(value):
    """
    Format percentage values to 2 decimal places.
    Used for: price_change_percent, flow_percentage, etc.

    Args:
        value: Numeric value to format (as decimal, not percentage)

    Returns:
        float: Value rounded to 2 decimal places, or None if input is None/invalid
    """
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (ValueError, TypeError):
        return None

def format_greek(value):
    """
    Format Greek values to 4 decimal places.
    Used for: delta, gamma, theta, vega, implied_volatility

    Args:
        value: Numeric value to format

    Returns:
        float: Value rounded to 4 decimal places, or None if input is None/invalid
    """
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (ValueError, TypeError):
        return None

def format_ratio(value):
    """
    Format ratio/multiplier values to 4 decimal places.
    Used for: oi_ratio, volume_ratio_5d, volume_ratio_20d, etc.

    Args:
        value: Numeric value to format

    Returns:
        float: Value rounded to 4 decimal places, or None if input is None/invalid
    """
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (ValueError, TypeError):
        return None

def format_score(value):
    """
    Format score values to 2 decimal places.
    Used for: significance_score, quality_score, mathematical_opportunity_score, etc.

    Args:
        value: Numeric value to format

    Returns:
        float: Value rounded to 2 decimal places, or None if input is None/invalid
    """
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (ValueError, TypeError):
        return None

def format_database_values(data_dict, column_types=None):
    """
    Format all numeric values in a dictionary according to their column types.

    Args:
        data_dict (dict): Dictionary of column names and values
        column_types (dict): Optional mapping of column names to format types
                           If not provided, uses intelligent defaults based on column names

    Returns:
        dict: Dictionary with formatted values
    """
    if not data_dict:
        return data_dict

    # Columns that should NOT be formatted (integers, strings, dates)
    skip_formatting = {
        'volume', 'open_interest', 'days_to_expiration', 'earnings_days_ahead',
        'symbol', 'option_type', 'trade_date', 'expiration', 'expiration_date', 'alert_timestamp',
        'scan_timestamp', 'moneyness', 'alert_reason', 'alert_level', 'contract_hash',
        'narrative', 'flow_classification', 'close_reason', 'user_notes', 'status',
        'sector', 'earnings_date', 'trigger_type', 'update_reason', 'action_type', 'reasoning',
        'created_at', 'updated_at', 'last_updated_timestamp', 'evaluation_status', 'alert_threshold_met',
        'alert_sent', 'user_action', 'notification_methods', 'analyst_context',
        'days_to_max_gain', 'days_to_max_loss', 'peak_hour_est', 'oi_change',
        'oi_change_1d', 'oi_change_5d', 'oi_change_10d', 'volume_change_1d',
        'volume_change_5d', 'days_from_52week_high', 'days_from_52week_low',
        'consecutive_vwap_trend_days', 'total_call_volume', 'total_put_volume',
        'total_call_oi', 'total_put_oi', 'earnings_days_ahead', 'has_upcoming_catalyst',
        'catalyst_description', 'sector', 'industry', 'market_cap_category', 'is_etf',
        'portfolio_position', 'max_pain_pressure', 'news_sentiment', 'news_article_count',
        'news_sentiment_label', 'news_sentiment_sector_rank', 'news_topics', 'claude_symbol_analysis',
        'flow_alert_history', 'technical_levels', 'direction_bias', 'conviction_level',
        'dominant_time_bucket', 'oi_time_distribution', 'news_sentiment_distribution',
        'alert_reason_json', 'building_unwinding', 'interesting_reason', 'build_pattern',
        'symbol_exp_type_hash', 'last_evaluated_date', 'earnings_date', 'earnings_play_signal',
        'stdev_confidence', 'regime_classification', 'market_regime', 'market_direction', 'primary_signal',
        # Display strings and formatted text fields
        'top_call_display', 'top_put_display', 'oi_balance_text', 'analysis_timestamp',
        'top_call_hash', 'top_put_hash', 'top_call_expiration', 'top_put_expiration',
        'processing_duration_ms',
        # OI timing context fields (v_oi_timing_context view)
        'oi_build_start_date', 'positioning_type', 'oi_build_days_since', 'dte', 'current_price',
        # v_option_comparison view fields (flags/counts)
        'in_gamma_zone',
        # Earnings Intelligence System fields (text/timestamp fields)
        'move_direction', 'iv_crush_severity', 'arbitrage_quality', 'snapshot_type',
        'snapshot_date', 'is_primary_symbol', 'earnings_time', 'source', 'is_backfilled', 'note_type', 'sentiment', 'tags',
        'notes', 'peer_type', 'calculated_at'
    }

    # Add quarterly date fields to skip list
    for year in range(2021, 2026):
        for quarter in range(1, 5):
            skip_formatting.add(f'q_{year}_{quarter}_date')

    # Default column type mappings based on common naming patterns
    default_types = {
        # Prices
        'strike': 'price',
        'bid': 'price',
        'ask': 'price',
        'last_price': 'price',
        'underlying_price': 'price',
        'close_price': 'price',
        'high_price': 'price',
        'low_price': 'price',
        'vwap': 'price',
        'max_pain_by_friday': 'price',
        'oi_build_start_price': 'price',
        'breakeven_price': 'price',

        # Percentages
        'price_change_percent': 'percentage',
        'price_diff_pct': 'percentage',  # Watchlist price change
        'flow_percentage': 'percentage',
        'oi_change_pct': 'percentage',
        'oi_change_pct_1d': 'percentage',
        'oi_change_pct_5d': 'percentage',
        'oi_change_pct_10d': 'percentage',
        'pct_from_20d_high': 'percentage',
        'pct_from_20d_low': 'percentage',
        'price_vs_vwap_percent': 'percentage',
        'oi_bias_percent': 'percentage',
        'current_vs_max_pain_pct': 'percentage',
        'oi_build_price_move_pct': 'percentage',
        'breakeven_move_pct': 'percentage',

        # Greeks and IV
        'delta': 'greek',
        'gamma': 'greek',
        'theta': 'greek',
        'vega': 'greek',
        'implied_volatility': 'greek',
        'IV': 'greek',  # Alias for implied_volatility in views
        'delta_change_1d': 'greek',
        'delta_change_5d': 'greek',
        'delta_momentum': 'greek',
        'delta_acceleration': 'greek',
        'gamma_change_1d': 'greek',
        'gamma_change_5d': 'greek',
        'gamma_momentum': 'greek',
        'theta_change_1d': 'greek',
        'theta_change_5d': 'greek',
        'theta_momentum': 'greek',
        'theta_avg_5d': 'greek',
        'theta_daily_change_avg_5d': 'greek',
        'vega_change_1d': 'greek',
        'vega_change_5d': 'greek',
        'iv_change_1d': 'greek',
        'iv_change_5d': 'greek',
        'iv_change_20d': 'greek',
        'iv_change_pct_1d': 'greek',
        'iv_change_pct_5d': 'greek',
        'iv_change_pct_20d': 'greek',
        'iv_avg_5d': 'greek',
        'iv_avg_20d': 'greek',
        'iv_percentile_20day': 'greek',
        'iv_percentile_rank_20d': 'greek',
        'iv_percentile_30d': 'greek',
        'iv_momentum_1d': 'greek',
        'iv_momentum_5d': 'greek',

        # Realized Volatility (z-score dip detection system)
        'rv_5d': 'greek',   # 5-day realized volatility, annualized
        'rv_10d': 'greek',  # 10-day realized volatility, annualized

        # Ratios
        'oi_ratio': 'ratio',
        'neighbor_avg_oi': 'ratio',
        'volume_surprise_factor': 'ratio',
        'put_call_volume_ratio': 'ratio',
        'put_call_oi_ratio': 'ratio',
        'volume_vs_20d_avg': 'ratio',
        'volume_surge_factor': 'ratio',
        'volume_ratio_5d': 'ratio',
        'volume_ratio_20d': 'ratio',
        'volume_percentile_rank_20d': 'ratio',
        'volume_ratio_5d_change_1d': 'ratio',
        'volume_avg_5d': 'ratio',
        'volume_avg_20d': 'ratio',
        'oi_momentum_5d': 'ratio',
        'vwap_trend_5d': 'ratio',
        'short_vs_long_bias': 'ratio',
        'oi_0_7_days_percent': 'ratio',
        'oi_8_21_days_percent': 'ratio',
        'oi_22_35_days_percent': 'ratio',
        'oi_36_60_days_percent': 'ratio',
        'oi_0_7_put_call_ratio': 'ratio',
        'oi_8_21_put_call_ratio': 'ratio',
        'oi_22_35_put_call_ratio': 'ratio',
        'oi_36_60_put_call_ratio': 'ratio',
        # v_option_comparison efficiency metrics
        'delta_per_dollar': 'ratio',
        'theta_decay_dollars': 'ratio',
        'vega_dollars_per_iv_point': 'ratio',
        'intrinsic_value': 'price',
        'extrinsic_value': 'price',

        # Scores
        'significance_score': 'score',
        'concentration_score': 'score',
        'final_quality_score': 'score',
        'signal_quality_score': 'score',
        'z_score': 'score',  # Z-score for dip detection
        'dip_threshold_used': 'score',  # Threshold that triggered dip
        'user_pnl': 'score',
        'news_sentiment_avg': 'score',
        'news_sentiment_change': 'score',
        'news_relevance_avg': 'score',
        'news_sentiment_vs_market_avg': 'score',
        'news_sentiment_vs_sector_avg': 'score',
        'news_sentiment_relative_rank': 'score',
        # News collection specific scores
        'overall_sentiment_score': 'score',
        'symbol_sentiment_score': 'score',
        'relevance_score': 'score',

        # Profit/Loss tracking
        'max_profit_1hr': 'price',
        'max_profit_4hr': 'price',
        'max_profit_1day': 'price',
        'max_profit_3day': 'price',
        'max_profit_7day': 'price',
        'max_profit_14day': 'price',
        'max_profit_30day': 'price',
        'max_loss_1hr': 'price',
        'max_loss_4hr': 'price',
        'max_loss_1day': 'price',
        'max_loss_3day': 'price',
        'max_loss_7day': 'price',
        'max_loss_14day': 'price',
        'max_loss_30day': 'price',
        'premium_value': 'price',
    }

    # Use provided column_types or fall back to defaults
    types_mapping = column_types or default_types

    formatted_data = {}
    for key, value in data_dict.items():
        if value is None:
            formatted_data[key] = value
            continue

        # Skip formatting for non-numeric columns
        if key in skip_formatting:
            formatted_data[key] = value
            continue

        # Determine format type
        format_type = types_mapping.get(key, 'score')  # Default to score format

        # Apply appropriate formatting
        if format_type == 'price':
            formatted_data[key] = format_price(value)
        elif format_type == 'percentage':
            formatted_data[key] = format_percentage(value)
        elif format_type == 'greek':
            formatted_data[key] = format_greek(value)
        elif format_type == 'ratio':
            formatted_data[key] = format_ratio(value)
        elif format_type == 'score':
            formatted_data[key] = format_score(value)
        else:
            # For unknown types, leave as-is if not numeric, otherwise apply score formatting
            try:
                # Only format if it's actually a number
                numeric_value = float(value)
                formatted_data[key] = format_score(value)
            except (ValueError, TypeError):
                # Leave non-numeric values unchanged
                formatted_data[key] = value

    return formatted_data

# Convenience function for common use cases
def clean_database_row(row_data):
    """
    Clean a database row dictionary using intelligent column name detection.

    Args:
        row_data (dict): Dictionary representing a database row

    Returns:
        dict: Cleaned row with properly formatted decimal values
    """
    return format_database_values(row_data)