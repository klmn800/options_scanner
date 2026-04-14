-- Cleanup Script: Drop Old Earnings Tables
-- After successful backfill to new intelligence system
-- Date: 2025-10-10
--
-- Tables being dropped:
-- 1. temp_earnings_raw - Backfilled to earnings_events (26,617 events)
-- 2. earnings_historical - Wide format with pre-calc stats (can regenerate)
--
-- Reason: Consolidate to new intelligence system architecture
-- Data preserved in: earnings_events (26,635 rows, 736 symbols, 1993-2025)

-- Drop temp_earnings_raw (26,635 rows) - Data now in earnings_events
DROP TABLE IF EXISTS temp_earnings_raw;

-- Drop earnings_historical (726 rows) - Stats can be regenerated from earnings_moves
DROP TABLE IF EXISTS earnings_historical;

-- Verification queries
SELECT 'earnings_events' as table_name, COUNT(*) as row_count FROM earnings_events
UNION ALL
SELECT 'earnings_upcoming', COUNT(*) FROM earnings_upcoming
UNION ALL
SELECT 'earnings_snapshots', COUNT(*) FROM earnings_snapshots
UNION ALL
SELECT 'earnings_moves', COUNT(*) FROM earnings_moves
UNION ALL
SELECT 'earnings_sector_effects', COUNT(*) FROM earnings_sector_effects
UNION ALL
SELECT 'industry_peer_mappings', COUNT(*) FROM industry_peer_mappings;
