-- Industry Peer Mappings Table Schema
-- Defines relationships between stocks in same industry for sector sympathy analysis
-- Leader identification based on earliest earnings date (changeable manually)
-- Part of: Earnings Intelligence System
-- Author: Ben (with Claude)
-- Date: 2025-10-09

CREATE TABLE IF NOT EXISTS industry_peer_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    industry TEXT NOT NULL,              -- From symbol_metadata.industry
    symbol TEXT NOT NULL,

    -- Peer Relationship
    is_industry_leader BOOLEAN DEFAULT FALSE,  -- Manually set or auto-detected (earliest earnings)
    peer_type TEXT,                      -- 'leader', 'major_peer', 'minor_peer'
    weight REAL DEFAULT 1.0,             -- Importance weight (4 decimals, 0.0 to 1.0)
                                         -- 1.0 = primary peer, 0.5 = secondary, 0.25 = tertiary

    -- Status
    is_active BOOLEAN DEFAULT TRUE,      -- Can disable without deleting

    -- Metadata
    notes TEXT,                          -- Manual notes about why this peer matters
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(industry, symbol)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_peer_mappings_industry ON industry_peer_mappings(industry);
CREATE INDEX IF NOT EXISTS idx_peer_mappings_symbol ON industry_peer_mappings(symbol);
CREATE INDEX IF NOT EXISTS idx_peer_mappings_leader ON industry_peer_mappings(is_industry_leader);
CREATE INDEX IF NOT EXISTS idx_peer_mappings_active ON industry_peer_mappings(is_active);

-- English Translation:
-- "Who are the peers in each industry, and who's the leader whose earnings move the others?"
--
-- Design Philosophy:
-- - Use INDUSTRY column (not sector) for tighter peer groupings
-- - Leader = earliest earnings reporter in industry (or manually set)
-- - Weight allows prioritizing most correlated peers over time
-- - Can group large industries first, refine later
--
-- Initial Population:
-- - Auto-populate from symbol_metadata.industry
-- - Mark leaders by earliest upcoming earnings_date
-- - Ben can manually adjust leader flags and weights
--
-- Example:
-- Industry: "Airlines"
-- - DAL: is_leader=TRUE, weight=1.0, peer_type='leader'
-- - AAL: is_leader=FALSE, weight=1.0, peer_type='major_peer'
-- - UAL: is_leader=FALSE, weight=0.9, peer_type='major_peer'
-- - LUV: is_leader=FALSE, weight=0.8, peer_type='major_peer'
-- - SAVE: is_leader=FALSE, weight=0.5, peer_type='minor_peer'
--
-- Usage:
-- SELECT symbol FROM industry_peer_mappings
-- WHERE industry = 'Airlines' AND is_active = TRUE
-- ORDER BY weight DESC;
