-- Earnings Moves Table Schema
-- Calculated metrics for actual price moves and IV changes after earnings
-- Derived from snapshots and historical_prices - can be regenerated anytime
-- Part of: Earnings Intelligence System
-- Author: Ben (with Claude)
-- Date: 2025-10-09

CREATE TABLE IF NOT EXISTS earnings_moves (
    move_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES earnings_events(event_id),
    symbol TEXT NOT NULL,

    -- Price Moves (calculated from historical_prices)
    -- All percentages: 2 decimals
    move_1day_pct REAL,                  -- Close to close (T-1 to T+0)
    move_2day_pct REAL,                  -- Close to close (T-1 to T+1)
    move_3day_pct REAL,                  -- Close to close (T-1 to T+2)
    move_5day_pct REAL,                  -- Close to close (T-1 to T+4)

    max_intraday_move_pct REAL,          -- Biggest intraday move in T+0 to T+2 window
    move_direction TEXT,                 -- 'UP', 'DOWN', 'FLAT' (abs < 1%)

    -- IV Changes (calculated from earnings_snapshots)
    -- All percentages: 2 decimals
    iv_buildup_pct REAL,                 -- IV change from T-7 to T-1
    iv_collapse_pct REAL,                -- IV change from T-1 to T+1
    iv_recovery_pct REAL,                -- IV change from T+1 to T+3

    iv_crush_severity TEXT,              -- 'Mild' (<20%), 'Moderate' (20-40%), 'Severe' (>40%)

    -- Price vs Expectation
    expected_move_pct REAL,              -- From straddle calculation (2 decimals)
    move_vs_expected_pct REAL,           -- Actual move vs expected (2 decimals)

    -- Metadata
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(event_id, symbol)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_moves_event ON earnings_moves(event_id);
CREATE INDEX IF NOT EXISTS idx_moves_symbol ON earnings_moves(symbol);
CREATE INDEX IF NOT EXISTS idx_moves_direction ON earnings_moves(move_direction);
CREATE INDEX IF NOT EXISTS idx_moves_crush_severity ON earnings_moves(iv_crush_severity);

-- English Translation:
-- "What actually happened? How much did the stock move?
--  How much did IV pump up beforehand and collapse after?"
--
-- Key Metrics:
-- - move_1day_pct: The classic "earnings move" (close to close)
-- - max_intraday_move_pct: Captures big pops (like AAL +11% example)
-- - iv_buildup_pct: How much IV increased leading into earnings
-- - iv_collapse_pct: Post-earnings IV crush
--
-- Data Flow:
-- - Calculated 1-5 days after earnings by ei_post_earnings_calc.py
-- - Queries earnings_snapshots for IV data
-- - Queries historical_prices for price moves
-- - Can be deleted and recalculated anytime (derived data)
--
-- Example:
-- AAPL earnings on 2025-10-15:
-- - move_1day_pct: +5.23
-- - move_3day_pct: +7.15
-- - iv_buildup_pct: +18.50 (IV went from 25% to 43.5%)
-- - iv_collapse_pct: -35.20 (IV dropped from 43.5% to 28.2%)
-- - iv_crush_severity: 'Moderate'
