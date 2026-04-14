-- Earnings Events Table Schema
-- Immutable archive of all earnings events - never delete, only insert
-- Survives data source failures and provides permanent historical record
-- One record per symbol's earnings event; new historical earnings record
-- Part of: Earnings Intelligence System
-- Author: Ben (with Claude)
-- Date: 2025-10-09

CREATE TABLE IF NOT EXISTS earnings_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    earnings_date DATE NOT NULL,

    -- Fiscal period identification
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,              -- 1, 2, 3, or 4

    -- Earnings data
    estimated_eps REAL,                  -- Analyst estimate (2 decimals)
    actual_eps REAL,                     -- Reported actual (2 decimals)
    eps_surprise_pct REAL,               -- (actual - estimate) / |estimate| * 100 (2 decimals)

    -- Timing
    earnings_time TEXT,                  -- 'BMO' (Before Market Open), 'AMC' (After Market Close), 'Unknown'

    -- Metadata
    source TEXT,                         -- 'yfinance', 'manual', 'fmp', 'observed'
    is_backfilled BOOLEAN DEFAULT FALSE, -- TRUE if added retroactively
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Human Insights (Trading Journal)
    notes TEXT,                          -- Your observations, lessons learned, story behind the numbers
    tags TEXT,                           -- Comma-separated: 'sector-sympathy,missed-opportunity,airlines'
    note_type TEXT,                      -- 'trade', 'observation', 'lesson', 'market_context'
    sentiment TEXT,                      -- 'positive', 'negative', 'neutral', 'mixed'

    UNIQUE(symbol, earnings_date)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_earnings_events_symbol ON earnings_events(symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_events_date ON earnings_events(earnings_date);
CREATE INDEX IF NOT EXISTS idx_earnings_events_symbol_date ON earnings_events(symbol, earnings_date);
CREATE INDEX IF NOT EXISTS idx_earnings_events_fiscal ON earnings_events(fiscal_year, fiscal_quarter);

-- English Translation:
-- "What earnings happened and when? This is the permanent record."
--
-- Data Flow:
-- - Populated from earnings_upcoming when earnings passes
-- - Backfilled from historical data where available
-- - Never deleted, only inserted
--
-- Example Usage:
-- INSERT INTO earnings_events (symbol, earnings_date, fiscal_year, fiscal_quarter,
--                               estimated_eps, actual_eps, earnings_time, source)
-- VALUES ('AAPL', '2025-10-15', 2025, 4, 1.25, 1.32, 'AMC', 'yfinance');
