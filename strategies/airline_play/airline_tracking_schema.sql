-- ============================================================================
-- AIRLINE TRACKING DATABASE SCHEMAS
-- ============================================================================
-- Purpose: Dedicated tracking for airline volatility pattern (AAL, UAL, DAL)
-- Author: Ben & Claude
-- Date: 2025-10-01
-- ============================================================================

-- ============================================================================
-- TABLE: airline_symbol_tracking
-- ============================================================================
-- Source tables: oi_symbol_summary, historical_prices, options_symbol_summary,
--                earnings_calendar, news_symbol_sentiment
-- Purpose: Daily symbol-level metrics for airline pattern monitoring
-- ============================================================================

CREATE TABLE IF NOT EXISTS airline_symbol_tracking (
    -- Primary Keys
    symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,

    -- Price & Volume Data
    -- Source: historical_prices
    close_price REAL,
    high_price REAL,
    low_price REAL,
    price_change_percent REAL,
    volume REAL,

    -- Open Interest Summary
    -- Source: oi_symbol_summary
    total_open_interest INTEGER,
    total_call_oi INTEGER,
    total_put_oi INTEGER,
    put_call_ratio REAL,
    oi_balance_text TEXT,

    -- OI Time Distribution
    -- Source: oi_symbol_summary
    oi_0_7_days REAL,
    oi_8_21_days REAL,
    oi_22_35_days REAL,
    oi_36_60_days REAL,
    oi_0_7_days_percent REAL,
    oi_8_21_days_percent REAL,
    oi_22_35_days_percent REAL,
    oi_36_60_days_percent REAL,

    -- Call OI Time Distribution
    -- Source: oi_symbol_summary
    call_oi_0_7_days REAL,
    call_oi_8_21_days REAL,
    call_oi_22_35_days REAL,
    call_oi_36_60_days REAL,
    call_oi_0_7_days_percent REAL,
    call_oi_8_21_days_percent REAL,
    call_oi_22_35_days_percent REAL,
    call_oi_36_60_days_percent REAL,

    -- Put OI Time Distribution
    -- Source: oi_symbol_summary
    put_oi_0_7_days REAL,
    put_oi_8_21_days REAL,
    put_oi_22_35_days REAL,
    put_oi_36_60_days REAL,
    put_oi_0_7_days_percent REAL,
    put_oi_8_21_days_percent REAL,
    put_oi_22_35_days_percent REAL,
    put_oi_36_60_days_percent REAL,

    -- Implied Volatility by DTE
    -- Source: options_symbol_summary (verify - wherever daily_analysis gets these)
    iv_front_month REAL,
    iv_30dte REAL,
    iv_45dte REAL,
    iv_60dte REAL,
    iv_percentile_front_month REAL,
    iv_percentile_30dte REAL,
    iv_percentile_45dte REAL,
    iv_percentile_60dte REAL,
    iv_percentile_30d REAL,

    -- Earnings
    -- Source: earnings_calendar
    earnings_date DATE,
    earnings_days_ahead INTEGER,

    -- News Sentiment
    -- Source: news_symbol_sentiment
    news_sentiment_score_avg REAL,
    news_sentiment TEXT,
    news_article_count INTEGER,

    -- Flow Alert Integration
    -- Source: calculated from flow_alerts
    active_alerts_count INTEGER,
    days_since_most_recent_alert INTEGER,

    -- Metadata
    analysis_timestamp TEXT,
    last_updated_timestamp TEXT,

    PRIMARY KEY (symbol, trade_date)
);

-- Indexes for airline_symbol_tracking
CREATE INDEX IF NOT EXISTS idx_airline_symbol_trade_date ON airline_symbol_tracking(trade_date);
CREATE INDEX IF NOT EXISTS idx_airline_symbol_latest ON airline_symbol_tracking(symbol, trade_date DESC);


-- ============================================================================
-- TABLE: airline_options_tracking
-- ============================================================================
-- Source tables: oi_daily, earnings_calendar
-- Purpose: Contract-level tracking for airline options
-- Note: All fields now available in oi_daily as of 2025-10-01
-- ============================================================================

CREATE TABLE IF NOT EXISTS airline_options_tracking (
    -- Primary Keys
    contract_hash TEXT NOT NULL,
    trade_date DATE NOT NULL,

    -- Contract Identifiers
    -- Source: oi_daily
    symbol TEXT NOT NULL,
    strike REAL NOT NULL,
    expiration_date DATE NOT NULL,
    option_type TEXT NOT NULL,

    -- Position & Moneyness
    -- Source: oi_daily
    underlying_price REAL,
    days_to_expiration INTEGER,
    moneyness TEXT,
    last_price REAL,

    -- Volume Metrics
    -- Source: oi_daily
    volume INTEGER,
    volume_avg_5d REAL,
    volume_avg_20d REAL,
    volume_ratio_5d REAL,
    volume_ratio_20d REAL,
    volume_percentile_rank_20d REAL,
    volume_change_1d INTEGER,
    volume_change_5d INTEGER,
    volume_ratio_5d_change_1d REAL,

    -- Open Interest Tracking
    -- Source: oi_daily
    open_interest INTEGER,
    oi_change INTEGER,
    oi_change_pct REAL,
    oi_change_1d INTEGER,
    oi_change_5d INTEGER,
    oi_change_10d INTEGER,
    oi_change_pct_1d REAL,
    oi_change_pct_5d REAL,
    oi_change_pct_10d REAL,
    oi_momentum_5d REAL,

    -- Greeks
    -- Source: oi_daily
    delta REAL,
    delta_change_1d REAL,
    delta_change_5d REAL,
    delta_momentum REAL,
    delta_acceleration REAL,

    gamma REAL,
    gamma_change_1d REAL,
    gamma_change_5d REAL,
    gamma_momentum REAL,

    theta REAL,
    theta_change_1d REAL,
    theta_change_5d REAL,
    theta_momentum REAL,
    theta_avg_5d REAL,
    theta_daily_change_avg_5d REAL,

    vega REAL,
    vega_change_1d REAL,
    vega_change_5d REAL,

    -- Implied Volatility
    -- Source: oi_daily
    implied_volatility REAL,
    iv_change_1d REAL,
    iv_change_5d REAL,
    iv_change_20d REAL,
    iv_change_pct_1d REAL,
    iv_change_pct_5d REAL,
    iv_change_pct_20d REAL,
    iv_avg_5d REAL,
    iv_avg_20d REAL,
    iv_percentile_20day REAL,
    iv_percentile_rank_20d REAL,
    iv_momentum_1d REAL,
    iv_momentum_5d REAL,

    -- Earnings Context
    -- Source: earnings_calendar (calculated similar to daily_analysis)
    days_to_earnings INTEGER,

    -- Analysis Metadata
    -- Source: oi_daily
    symbol_exp_type_hash TEXT,
    created_at TEXT,
    last_updated_timestamp TEXT,

    PRIMARY KEY (contract_hash, trade_date)
);

-- Indexes for airline_options_tracking
CREATE INDEX IF NOT EXISTS idx_airline_options_symbol_date ON airline_options_tracking(symbol, trade_date);
CREATE INDEX IF NOT EXISTS idx_airline_options_expiration ON airline_options_tracking(expiration_date);
CREATE INDEX IF NOT EXISTS idx_airline_options_contract_hash ON airline_options_tracking(contract_hash);
CREATE INDEX IF NOT EXISTS idx_airline_options_dte ON airline_options_tracking(days_to_expiration);


-- ============================================================================
-- DATA SOURCE NOTES
-- ============================================================================

-- Fields to verify source location:
-- ✓ iv_front_month, iv_30dte, etc. - Check options_symbol_summary
-- ✓ volume_ratio_5d_change_1d - Confirmed in oi_daily

-- Confirmed source tables (2025-10-01):
-- ✅ historical_prices: close_price, high_price, low_price, price_change_percent, volume
-- ✅ oi_daily: underlying_price, days_to_expiration, moneyness (plus all OI/volume/Greeks/IV tracking)
-- ✅ oi_symbol_summary: All OI aggregations and time distributions

-- ============================================================================
