-- Earnings Snapshots Table Schema
-- Time-series capture of IV and price evolution around earnings events
-- Shows the "movie" not just the "ending" - captures buildup and collapse
-- Part of: Earnings Intelligence System
-- Author: Ben (with Claude)
-- Date: 2025-10-09

CREATE TABLE IF NOT EXISTS earnings_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES earnings_events(event_id),
    symbol TEXT NOT NULL,                -- Can differ from event symbol (peer snapshots)
    snapshot_date DATE NOT NULL,
    days_from_earnings INTEGER,          -- -7 to +3 (negative = before, positive = after)
    snapshot_type TEXT,                  -- 'pre_earnings', 'earnings_day', 'post_earnings'

    -- Price Data (from historical_prices)
    close_price REAL,                    -- 2 decimals
    volume INTEGER,

    -- IV Data (from oi_symbol_summary or options_symbol_summary)
    iv_30dte REAL,                       -- 4 decimals (0.2500 = 25%)
    iv_front_month REAL,                 -- 4 decimals
    iv_45dte REAL,                       -- 4 decimals

    -- Open Interest Data
    total_open_interest INTEGER,
    put_call_ratio REAL,                 -- 4 decimals

    -- Context Flags
    is_primary_symbol BOOLEAN,           -- TRUE for primary company reporting earnings
                                         -- FALSE for peer/industry snapshot

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(event_id, symbol, snapshot_date)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_snapshots_event ON earnings_snapshots(event_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_symbol ON earnings_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_date ON earnings_snapshots(symbol, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_snapshots_days_from ON earnings_snapshots(days_from_earnings);
CREATE INDEX IF NOT EXISTS idx_snapshots_type ON earnings_snapshots(snapshot_type);

-- English Translation:
-- "How did IV and price evolve in the days around this earnings?
--  Not just for the company reporting, but for its industry peers too."
--
-- Snapshot Timeline:
-- - 7 days before earnings (days_from_earnings = -7 to -1)
-- - Earnings day (days_from_earnings = 0)
-- - 3 days after earnings (days_from_earnings = +1 to +3)
--
-- Data Flow:
-- - Collected daily by ei_snapshot_collector.py for upcoming earnings
-- - For each upcoming earnings in next 7 days:
--   - Capture snapshot for primary symbol
--   - Capture snapshots for all industry peers
-- - Source data from oi_symbol_summary/options_symbol_summary and historical_prices
--
-- Example:
-- DAL earnings on 2025-10-15:
-- - Snapshot: DAL, 2025-10-08, days=-7, iv_30dte=0.4500, is_primary=TRUE, type='pre_earnings'
-- - Snapshot: AAL, 2025-10-08, days=-7, iv_30dte=0.3200, is_primary=FALSE, type='pre_earnings'
-- - Snapshot: DAL, 2025-10-14, days=-1, iv_30dte=0.6500, is_primary=TRUE, type='pre_earnings'
-- - Snapshot: AAL, 2025-10-14, days=-1, iv_30dte=0.3400, is_primary=FALSE, type='pre_earnings'
--
-- The Insight: DAL's IV pumped 20 points, AAL's only moved 2 points,
--              yet AAL will likely move when DAL reports.
