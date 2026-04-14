-- Earnings Sector Effects Table Schema
-- Captures sector sympathy movements - when leader's earnings moves peer stocks
-- Identifies IV arbitrage opportunities in mispriced peer options
-- Part of: Earnings Intelligence System
-- Author: Ben (with Claude)
-- Date: 2025-10-09

CREATE TABLE IF NOT EXISTS earnings_sector_effects (
    effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_event_id INTEGER NOT NULL REFERENCES earnings_events(event_id),
    primary_symbol TEXT NOT NULL,        -- The company reporting earnings (e.g., DAL)
    peer_symbol TEXT NOT NULL,           -- The correlated stock (e.g., AAL)
    industry TEXT,                       -- From industry_peer_mappings

    -- IV Arbitrage Signal (the edge)
    primary_iv_buildup_pct REAL,         -- Primary's IV change T-7 to T-1 (2 decimals)
    peer_iv_buildup_pct REAL,            -- Peer's IV change T-7 to T-1 (2 decimals)
    iv_arbitrage_delta REAL,             -- Difference (peer - primary) (2 decimals)
                                         -- Negative = peer was cheaper (opportunity!)

    -- Move Correlation
    primary_move_pct REAL,               -- Primary's actual move on earnings day (2 decimals)
    peer_move_pct REAL,                  -- Peer's sympathetic move on same day (2 decimals)

    -- CORRELATION METRICS (ANALYSTS: Always check sample_size with correlation_strength!)
    correlation_strength REAL,           -- 0.0 to 1.0 (4 decimals) - How closely peer tracks primary
    sample_size INTEGER,                 -- How many historical earnings used for correlation
                                         -- CRITICAL: <5 = warming up, 5-10 = moderate, >10 = high confidence
                                         -- Low sample_size + high correlation = anecdotal, not reliable!

    -- Expected vs Actual
    expected_peer_move_pct REAL,         -- Predicted peer move based on historical correlation (2 decimals)
    actual_vs_expected_diff REAL,        -- How accurate was prediction? (2 decimals)

    -- Opportunity Assessment
    arbitrage_quality TEXT,              -- 'High', 'Medium', 'Low'
                                         -- High = big IV discount + strong historical correlation

    -- Metadata
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(primary_event_id, peer_symbol)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sector_effects_primary ON earnings_sector_effects(primary_symbol);
CREATE INDEX IF NOT EXISTS idx_sector_effects_peer ON earnings_sector_effects(peer_symbol);
CREATE INDEX IF NOT EXISTS idx_sector_effects_industry ON earnings_sector_effects(industry);
CREATE INDEX IF NOT EXISTS idx_sector_effects_quality ON earnings_sector_effects(arbitrage_quality);
CREATE INDEX IF NOT EXISTS idx_sector_effects_event ON earnings_sector_effects(primary_event_id);

-- English Translation:
-- "When DAL reports earnings, which peers move? Which peers had cheap IV beforehand?
--  That's the opportunity."
--
-- The Arbitrage Setup:
-- 1. DAL has earnings coming up
-- 2. DAL's IV pumps from 35% to 55% (+20 points)
-- 3. AAL's IV only goes 30% to 35% (+5 points)
-- 4. iv_arbitrage_delta = -15 points (AAL is 15 points cheaper)
-- 5. Historically, AAL moves 0.85x what DAL moves (correlation_strength = 0.85)
-- 6. DAL moves +8% on earnings
-- 7. AAL moves +6% on same day
-- 8. arbitrage_quality = 'High' (cheap IV + strong correlation + significant move)
--
-- Data Flow:
-- - Calculated after earnings for all industry peers
-- - Queries earnings_snapshots for IV evolution
-- - Queries earnings_moves for actual moves
-- - Uses industry_peer_mappings to identify peers
-- - Requires multiple historical events to calculate correlation (sample_size)
--
-- Warming Up Period:
-- - First few events: correlation_strength may be NULL or low confidence
-- - After 5+ events: correlation becomes meaningful
-- - sample_size tracks statistical confidence
--
-- Example Output:
-- Primary: DAL earnings on 2025-10-15
-- Peer: AAL
-- - primary_iv_buildup_pct: +25.00
-- - peer_iv_buildup_pct: +5.00
-- - iv_arbitrage_delta: -20.00 (AAL was 20 points cheaper!)
-- - primary_move_pct: +8.00
-- - peer_move_pct: +6.00
-- - correlation_strength: 0.85 (strong)
-- - sample_size: 12 (high confidence)
-- - arbitrage_quality: 'High'
--
-- → Opportunity: AAL options were underpriced, could have bought AAL calls cheap
