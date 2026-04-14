# Earnings Intelligence: Manual Operations Guide

This guide covers manual operations for the Earnings Intelligence System.

## Table of Contents
1. [Adding Trading Notes](#adding-trading-notes)
2. [Setting Industry Leaders](#setting-industry-leaders)
3. [Viewing Analysis Results](#viewing-analysis-results)
4. [Data Maintenance](#data-maintenance)

---

## Adding Trading Notes

The `earnings_events` table includes a built-in trading journal with four fields:
- `notes` - Free-form observations and analysis
- `tags` - Comma-separated keywords (e.g., "vanna,iv-crush,surprise")
- `note_type` - Category: "trade", "observation", "pattern", "lesson"
- `sentiment` - Your take: "bullish", "bearish", "neutral"

### Example 1: Recording a Trade Setup

```sql
-- Add notes for NVDA's 2025-02-26 earnings
UPDATE earnings_events
SET notes = 'Considered selling 30DTE straddle based on historical 8% avg move. IV was at 85th percentile (0.62). Decided to wait for IV crush data from snapshots before entering.',
    tags = 'iv-rank-high,volatility-play,waiting',
    note_type = 'observation',
    sentiment = 'neutral'
WHERE symbol = 'NVDA' AND earnings_date = '2025-02-26';
```

### Example 2: Post-Trade Review

```sql
-- Add post-trade analysis for TSLA 2025-04-22
UPDATE earnings_events
SET notes = 'Stock moved 10.2% day-1 (expected ~12%). My short strangle at 25 delta expired worthless. IV crushed from 0.68 to 0.41 (-40%). Winner. Key lesson: TSLA IV crush is consistently severe.',
    tags = 'trade,short-strangle,winner,iv-crush-severe',
    note_type = 'trade',
    sentiment = 'bullish'
WHERE symbol = 'TSLA' AND earnings_date = '2025-04-22';
```

### Example 3: Pattern Recognition

```sql
-- Add pattern observation for AAPL
UPDATE earnings_events
SET notes = 'AAPL shows consistent pattern: small move (<5%) on earnings, then larger move (>7%) in following 3-5 days as market digests guidance. Potential delayed reaction play.',
    tags = 'pattern,delayed-reaction,guidance-sensitive',
    note_type = 'pattern',
    sentiment = 'neutral'
WHERE symbol = 'AAPL' AND earnings_date = '2025-05-01';
```

### Example 4: Sector Sympathy Observation

```sql
-- Add sector sympathy note
UPDATE earnings_events
SET notes = 'NVDA earnings caused sympathy move in AMD (+3.2%) and SMCI (+5.1%). Check sector_effects table for correlation strength. Arbitrage opportunity existed in AMD (cheaper IV).',
    tags = 'sector-sympathy,arbitrage,semiconductors',
    note_type = 'observation',
    sentiment = 'bullish'
WHERE symbol = 'NVDA' AND earnings_date = '2024-08-28';
```

### Bulk Tagging by Pattern

```sql
-- Tag all events with severe IV crush
UPDATE earnings_events
SET tags = COALESCE(tags || ',', '') || 'severe-iv-crush'
WHERE event_id IN (
    SELECT event_id FROM earnings_moves
    WHERE iv_crush_severity = 'severe'
);
```

---

## Setting Industry Leaders

Industry leaders are used to prioritize peers in arbitrage scanning. Set `is_industry_leader = TRUE` for the most important companies in each sector.

### Example 1: Semiconductor Leaders

```sql
-- Set NVDA, AMD, INTC as semiconductor leaders
UPDATE industry_peer_mappings
SET is_industry_leader = TRUE
WHERE industry = 'Semiconductors'
  AND symbol IN ('NVDA', 'AMD', 'INTC');
```

### Example 2: Software Leaders

```sql
-- Set MSFT, GOOGL as software leaders
UPDATE industry_peer_mappings
SET is_industry_leader = TRUE
WHERE industry LIKE 'Software%'
  AND symbol IN ('MSFT', 'GOOGL', 'ORCL', 'CRM');
```

### Example 3: View Current Leaders

```sql
-- See all industry leaders
SELECT industry, symbol
FROM industry_peer_mappings
WHERE is_industry_leader = TRUE
ORDER BY industry, symbol;
```

### Example 4: Count Peers per Industry

```sql
-- See how many peers each industry has
SELECT industry, COUNT(*) as peer_count
FROM industry_peer_mappings
WHERE is_active = TRUE
GROUP BY industry
ORDER BY peer_count DESC
LIMIT 20;
```

---

## Viewing Analysis Results

### Query 1: Today's Arbitrage Opportunities

```sql
-- Find today's arbitrage opportunities (morning scan results)
-- Note: This data comes from ei_arbitrage_scanner.py output
-- The scanner doesn't write to database yet, so check logs
-- Future enhancement: Create arbitrage_opportunities table
```

### Query 2: Historical Price Moves by Symbol

```sql
-- Quick view using denormalized outcome columns on earnings_events
SELECT symbol, earnings_date, earnings_time, earnings_play_signal,
       actual_move_1day_pct, actual_max_move_pct,
       move_vs_expected_pct, iv_collapse_pct
FROM earnings_events
WHERE symbol = 'NVDA' AND actual_move_1day_pct IS NOT NULL
ORDER BY earnings_date DESC;

-- Detailed view with full OHLC peaks and swing analysis
SELECT ee.earnings_date, ee.earnings_time,
       em.pre_earnings_close, em.move_1day_pct, em.move_3day_pct,
       em.post_earnings_peak_up_pct, em.post_earnings_peak_down_pct,
       em.post_earnings_swing_pct, em.total_swing_pct,
       em.expected_move_entry_pct, em.move_vs_expected_pct,
       em.iv_collapse_pct, em.iv_crush_severity
FROM earnings_moves em
JOIN earnings_events ee ON em.event_id = ee.event_id
WHERE em.symbol = 'NVDA'
ORDER BY ee.earnings_date DESC;
```

### Query 3: Sector Sympathy Effects

```sql
-- See how AMD moved on NVDA earnings
SELECT ese.primary_symbol, ese.peer_symbol,
       ese.primary_move_pct, ese.peer_move_pct,
       ese.correlation_strength, ese.arbitrage_quality
FROM earnings_sector_effects ese
WHERE ese.primary_symbol = 'NVDA'
  AND ese.peer_symbol = 'AMD'
ORDER BY ese.calculated_at DESC;
```

### Query 4: IV Buildup and Expected Move Tracking

```sql
-- Track IV buildup and expected move evolution for TSLA earnings
-- Note: snapshots use earnings_date (not event_id) as the key
SELECT snapshot_date, days_from_earnings, iv_30dte,
       close_price, high_price, low_price,
       straddle_expected_move_pct
FROM earnings_snapshots
WHERE earnings_date = '2025-10-23' AND symbol = 'TSLA'
AND is_primary_symbol = TRUE
ORDER BY days_from_earnings;
```

### Query 5: Compare Peer IV vs Primary

```sql
-- Compare NVDA vs peers during earnings window
SELECT symbol, snapshot_date, iv_30dte, is_primary_symbol
FROM earnings_snapshots
WHERE event_id = (
    SELECT event_id FROM earnings_events
    WHERE symbol = 'NVDA' AND earnings_date = '2025-11-20'
)
AND days_from_earnings = -1  -- Day before earnings
ORDER BY is_primary_symbol DESC, iv_30dte DESC;
```

### Query 6: Best/Worst Movers This Year

```sql
-- Top 10 biggest earnings moves in 2025
SELECT ee.symbol, ee.earnings_date, em.move_1day_pct, em.move_direction
FROM earnings_moves em
JOIN earnings_events ee ON em.event_id = ee.event_id
WHERE ee.earnings_date >= '2025-01-01'
ORDER BY ABS(em.move_1day_pct) DESC
LIMIT 10;
```

### Query 7: Trading Journal Review

```sql
-- Review all your trade notes
SELECT ee.symbol, ee.earnings_date, ee.note_type, ee.sentiment,
       ee.tags, ee.notes
FROM earnings_events ee
WHERE ee.notes IS NOT NULL
ORDER BY ee.earnings_date DESC;
```

---

## Data Maintenance

### Clean Up Old Snapshots

```sql
-- Delete snapshots older than 1 year
DELETE FROM earnings_snapshots
WHERE created_at < date('now', '-1 year');
```

### Verify Data Completeness

```sql
-- Check which symbols are missing peer mappings
SELECT DISTINCT ee.symbol
FROM earnings_events ee
LEFT JOIN industry_peer_mappings ipm ON ee.symbol = ipm.symbol
WHERE ipm.symbol IS NULL;
```

### Recalculate Moves

```bash
# Recalculate all events in the T+3 to T+10 window (overwrites existing rows)
python strategies/earnings_intel/ei_post_earnings_calc.py --recalculate --no-interaction

# Backfill earnings_events denormalized outcome columns from existing earnings_moves
python strategies/earnings_intel/ei_post_earnings_calc.py --backfill-outcomes --no-interaction

# Repair old snapshots with NULL OHLC data
python strategies/earnings_intel/ei_snapshot_collector.py --backfill --no-interaction
```

To recalculate a specific event, delete its `earnings_moves` row first:

```sql
DELETE FROM earnings_moves
WHERE event_id = (
    SELECT event_id FROM earnings_events
    WHERE symbol = 'NVDA' AND earnings_date = '2025-02-26'
);
-- Then run the normal daily pipeline or --recalculate
```

---

## Tips and Best Practices

1. **Tag Consistently**: Use consistent tag names (lowercase, hyphenated)
   - Good: `iv-crush`, `sector-sympathy`, `delayed-reaction`
   - Bad: `IV Crush`, `sectorSympathy`, `DELAYED REACTION`

2. **Note Type Usage**:
   - `trade` - Actual positions you entered
   - `observation` - Patterns you noticed but didn't trade
   - `pattern` - Recurring behaviors worth tracking
   - `lesson` - Post-mortem analysis and learning

3. **Sentiment Guidelines**:
   - `bullish` - Moved as expected, profitable, or confirmed thesis
   - `bearish` - Moved against expectation, unprofitable, or invalidated thesis
   - `neutral` - Mixed results or incomplete analysis

4. **Leader Selection**: Choose 2-4 leaders per industry based on:
   - Market cap (larger = more influence)
   - Options liquidity (higher = better arbitrage signal)
   - Earnings timing (earlier = leads sector)

5. **Journal Regularly**: Add notes within 1-2 days while the trade is fresh

---

## Advanced: Custom Queries

### Find IV Arbitrage Winners

```sql
-- Find past arbitrage opportunities that would have worked
SELECT ese.primary_symbol, ese.peer_symbol,
       ese.iv_arbitrage_delta, ese.peer_move_pct,
       ese.correlation_strength, ese.arbitrage_quality
FROM earnings_sector_effects ese
WHERE ese.arbitrage_quality = 'High'
  AND ese.peer_move_pct IS NOT NULL
  AND ABS(ese.peer_move_pct) > 3.0  -- Peer moved >3%
ORDER BY ese.iv_arbitrage_delta DESC
LIMIT 20;
```

### Calculate Your Win Rate

```sql
-- If you tag trades as 'winner' or 'loser'
SELECT
    COUNT(*) as total_trades,
    SUM(CASE WHEN tags LIKE '%winner%' THEN 1 ELSE 0 END) as winners,
    SUM(CASE WHEN tags LIKE '%loser%' THEN 1 ELSE 0 END) as losers,
    ROUND(100.0 * SUM(CASE WHEN tags LIKE '%winner%' THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate_pct
FROM earnings_events
WHERE note_type = 'trade'
  AND (tags LIKE '%winner%' OR tags LIKE '%loser%');
```

---

## Next Steps

1. Start adding notes to recent earnings events
2. Set industry leaders for your focus sectors
3. Run morning scans to find arbitrage opportunities
4. Review historical sector_effects to find reliable patterns
5. Build your own custom queries for your trading style
