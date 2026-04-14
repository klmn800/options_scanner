# Earnings Intelligence Strategy Guide

**Purpose:** Auto-fix reference for Earnings Intel errors
**Updated:** November 1, 2025

---

## Overview

Earnings Intelligence tracks earnings events with IV/price snapshots (T-7 to T+3 around earnings), historical move analysis, and sector sympathy arbitrage opportunities.

**Key Concept:** Captures IV term structure before earnings to compare against historical moves, identifies mispriced IV, and finds sector sympathy plays.

---

## Architecture

**Entry Point:** `strategies/earnings_intel/ei_main.py`

**Core Components:**
1. `ei_collector.py` - Weekly earnings fetch from Finnhub (per-symbol, ~726 stocks). Called directly by `main_runners.py`, not through `ei_main.py`.
2. `ei_snapshot_collector.py` - Daily IV/price snapshots (T-7 to T+3)
3. `ei_post_earnings_calc.py` - Calculate actual moves after earnings
4. `ei_arbitrage_scanner.py` - Find IV arbitrage opportunities
5. `ei_moves_upcoming.py` - Update expected moves and signals daily
6. `ei_watchlist.py` - Populate actionable earnings watchlist

**Deprecated:** `ei_fetch_upcoming.py` (old Finnhub bulk + YFinance fallback, replaced 2026-02-27)

**Data Flow:**
```
Finnhub API (per-symbol, weekly)
↓
ei_collector.py (upsert to earnings_upcoming)
↓
ei_snapshot_collector.py (daily snapshots to earnings_snapshots)
↓
Earnings report happens
↓
ei_post_earnings_calc.py (calculate moves to earnings_moves)
↓
ei_arbitrage_scanner.py (find opportunities in earnings_sector_effects)
```

---

## Database Tables

**Writes:**
- `earnings_events` - Event archive with trading journal (notes, tags, sentiment)
- `earnings_snapshots` - IV/price time series (T-7 to T+3)
- `earnings_moves` - Historical price moves and IV changes
- `earnings_sector_effects` - Sector sympathy and arbitrage opportunities

**Reads:**
- `option_symbol_summary` - **Primary IV source** (iv_front_month, iv_30dte, etc.)
- `historical_prices` - Price data for move calculations
- `symbol_metadata` - Sector/industry classifications

---

## Schedule

**Weekly Refresh (Sundays):**
- Fetch upcoming earnings calendar
- Archive completed events
- Cleanup expired snapshots

**Daily Pipeline (5:00 PM):**
- Take IV/price snapshots for upcoming earnings (T-7 to T+0)
- Calculate moves for completed earnings (T+1 to T+3)
- Update earnings_moves table

**Morning Scan (6:30 AM):**
- Scan for IV arbitrage opportunities
- Identify sector sympathy plays
- Generate alerts for mispriced IV

---

## Common Errors

### 1. Missing IV Data in Snapshots

**Error:** earnings_snapshots has NULL values for iv_front_month, iv_30dte, etc.

**Cause:** option_symbol_summary doesn't have IV data for symbol on snapshot_date

**Investigation:**
1. Check if Option Pipeline ran successfully:
   ```sql
   SELECT COUNT(*) FROM option_symbol_summary
   WHERE symbol = 'AAPL' AND trade_date = '2025-11-01';
   ```
2. Check if IV values are NULL in source:
   ```sql
   SELECT iv_front_month, iv_30dte FROM option_symbol_summary
   WHERE symbol = 'AAPL' AND trade_date = '2025-11-01';
   ```

**Fix Approach:**
- If option_symbol_summary missing → Option Pipeline didn't run, trigger collection
- If IV NULL in source → Symbol has no options or liquidity too low
- If widespread → Check Option Pipeline health

---

### 2. No Arbitrage Opportunities Found

**Error:** ei_arbitrage_scanner.py completes but finds 0 opportunities

**Not always an error:** Market may be efficiently priced, or no earnings this week

**Investigation:**
1. Check if earnings events exist:
   ```sql
   SELECT COUNT(*) FROM earnings_upcoming
   WHERE report_date BETWEEN CURRENT_DATE AND DATE(CURRENT_DATE, '+7 days');
   ```
2. Check if snapshots captured:
   ```sql
   SELECT COUNT(*) FROM earnings_snapshots
   WHERE snapshot_date = CURRENT_DATE;
   ```
3. Check historical moves data:
   ```sql
   SELECT COUNT(*) FROM earnings_moves;
   ```

**Fix if missing data:**
- No upcoming earnings → Normal, wait for next week
- No snapshots → Run `ei_snapshot_collector.py`
- No historical moves → Run `ei_moves_historical.py` to backfill

---

### 3. Snapshot Timing Issues

**Error:** Snapshots captured at wrong time relative to earnings

**Cause:** Report timing (before/after market) not handled correctly

**Investigation:**
- Check `earnings_upcoming.when_time` column (BMO vs AMC)
- Verify T-7 to T+3 calculation accounts for market open/close

**Fix:**
- Adjust snapshot timing logic in `ei_snapshot_collector.py`
- Account for weekend/holiday gaps

---

### 4. Sector Sympathy Not Detected

**Error:** earnings_sector_effects table empty or missing expected plays

**Cause:** Peer mapping data missing or sector correlation logic broken

**Investigation:**
1. Check peer mappings:
   ```sql
   SELECT COUNT(*) FROM industry_peer_mappings;
   ```
2. Check sector definitions:
   ```sql
   SELECT DISTINCT sector FROM symbol_metadata;
   ```

**Fix:**
- If peer mappings empty → Run `ei_populate_peer_mappings.py`
- If sector definitions wrong → Update symbol_metadata

---

## Configuration

**File:** `strategies/earnings_intel/ei_config.py` (if exists) or embedded in scripts

**Key Settings:**
- Snapshot window: T-7 to T+3 (days around earnings)
- IV buckets: front_month, 30dte, 45dte, 60dte
- Arbitrage threshold: How much IV mispricing to flag
- Sector correlation threshold: How correlated for sympathy play

---

## IV Source Migration (October 16, 2025)

**Previous Source:** Deprecated `options_symbol_summary` table

**Current Source:** `option_symbol_summary` table (from Option Pipeline)

**Why migrated:** Unified IV source, better DTE bucketing, universal coverage (all 800 symbols)

**Columns used:**
- `iv_front_month` - 7-21 DTE (front month)
- `iv_30dte` - 22-35 DTE
- `iv_45dte` - 36-50 DTE
- `iv_60dte` - 51-70 DTE

**Code impact:** All queries updated to reference new table. If you see `options_symbol_summary` (plural), it's outdated.

---

## Trading Journal Integration

**Table:** `earnings_events`

**Columns:**
- `notes` - Trading notes, analysis, outcomes
- `tags` - Categories (earnings_beat, guidance_miss, etc.)
- `sentiment` - Bullish/Bearish/Neutral
- `actual_move_pct` - Calculated move after earnings
- `iv_crush_pct` - IV change after earnings

**Purpose:** Manual tracking of trades, outcomes, lessons learned

**Access:** See `MANUAL_OPERATIONS.md` in earnings_intel directory

---

## Critical Files

**Calendar Management:**
- `strategies/earnings_intel/ei_fetch_upcoming.py`

**Snapshot Collection:**
- `strategies/earnings_intel/ei_snapshot_collector.py` (uses option_symbol_summary)

**Move Calculations:**
- `strategies/earnings_intel/ei_post_earnings_calc.py`

**Arbitrage Detection:**
- `strategies/earnings_intel/ei_arbitrage_scanner.py`

**Historical Data:**
- `strategies/earnings_intel/ei_moves_historical.py`

---

## Safe Modifications

**Safe to edit:**
- Snapshot timing logic (T-7 to T+3 window)
- Arbitrage threshold values
- Sector correlation thresholds
- Trading journal notes/tags

**Risky (investigate first):**
- IV calculation formulas
- Move calculation logic
- Peer mapping algorithms
- Database queries

**Never modify:**
- Database schema
- Core earnings date logic
- Historical moves archive

---

## Testing

**Manual test (snapshot collection):**
```bash
cd strategies/earnings_intel
python ei_snapshot_collector.py --no-interaction
```

**Verify:**
- Snapshots created for upcoming earnings
- IV values populated from option_symbol_summary
- Price data from historical_prices

**Manual test (arbitrage scan):**
```bash
python ei_arbitrage_scanner.py --no-interaction
```

**Verify:**
- Opportunities detected (if earnings this week)
- Sector effects calculated
- Results stored to earnings_sector_effects

---

## Dependencies

**Required for operation:**
1. Option Pipeline must run daily (for IV data in option_symbol_summary)
2. Historical prices must be current (for move calculations)
3. Earnings calendar must be fetched weekly (for upcoming events)

**Broken dependencies:**
- If Option Pipeline doesn't run → No IV data → Snapshots incomplete
- If historical prices stale → Move calculations wrong
- If earnings calendar outdated → Missing events

---

## Data Flow Dependencies

```
earnings_upcoming (calendar)
↓
earnings_snapshots (daily IV/price tracking)
↓
Earnings report happens
↓
earnings_moves (historical moves database)
↓
earnings_sector_effects (arbitrage opportunities)
```

**Each step depends on previous:** If calendar missing, snapshots won't capture. If snapshots missing, moves can't calculate.

---

*For full system architecture, see `autofix/reference/system_architecture.md`*
*For database schema, see `data/datalake_schema_2026-01-01.md`*
*For manual operations, see `strategies/earnings_intel/MANUAL_OPERATIONS.md`*
