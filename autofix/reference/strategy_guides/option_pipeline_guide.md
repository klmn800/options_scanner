# Option Pipeline Strategy Guide

**Purpose:** Auto-fix reference for Option Pipeline errors
**Updated:** November 1, 2025
**Formerly Known As:** OI Delta (renamed October 2025)

---

## Overview

Option Pipeline analyzes open interest (OI) changes and patterns through daily morning and evening collection cycles.

**Key Concept:** Collects complete option chains for all symbols, calculates time-series metrics (1d/5d/10d/20d changes), and identifies position building/unwinding patterns.

---

## Architecture

**Entry Point:** `strategies/option_pipeline/op_main.py`

**Core Components:**
1. `op_collector.py` - API calls, OI data collection + **self-monitoring**
2. `op_analyzer.py` - Time-series calculations, delta correlation
3. `op_storage.py` - Database operations
4. `op_symbol_rollup.py` - Symbol-level aggregations

**Data Flow:**
```
Tradier API
↓
op_collector.py (fetch full option chains)
↓
op_analyzer.py (calculate OI changes, IV momentum)
↓
op_storage.py (store to option_contracts)
↓
op_symbol_rollup.py (aggregate to option_symbol_summary)
```

---

## Database Tables

**Writes:**
- `option_contracts` (1.46M rows) - Contract-level OI snapshots with time series
- `option_symbol_summary` (64K rows) - Symbol-level IV/OI/Greek summaries

**Reads:**
- `symbol_metadata` (740 rows) - Symbol universe
- `historical_prices` (176K rows) - Underlying price data

---

## Self-Monitoring

**Location:** `strategies/option_pipeline/op_collector.py` or `op_storage.py` (after collection)

**Check Logic:**
```python
# After collection completes
contracts_collected = len(contracts_data)
api_calls_succeeded = True  # Tradier returned 200 OK

# If API worked but no contracts stored → CRITICAL ERROR
if contracts_collected == 0 and api_calls_succeeded:
    trigger_auto_fix(error_type='no_contracts_stored', context={
        'symbols_attempted': 800,
        'api_status': 'success',
        'collection_phase': 'morning' or 'evening'
    })
```

**Why this matters:** Should collect thousands of contracts per run. Zero contracts means filtering too aggressively, database write failure, or API response format changed.

---

## Schedule

**Morning Phase (6:35 AM - 9:00 AM):**
- Collect OI data for all 800 symbols
- Calculate overnight OI changes
- Store to `option_contracts`
- Run symbol rollup to `option_symbol_summary`

**Evening Phase (5:00 PM onwards):**
- Collect end-of-day OI data
- Calculate intraday OI changes
- Update time-series metrics
- Run symbol rollup

---

## Common Errors

### 1. No Contracts Stored (Silent Failure)

**Error:** Auto-fix triggered with context "no_contracts_stored"

**Possible Causes:**
1. Strike range filtering too aggressive (±20% too narrow?)
2. DTE filtering removing all contracts (min/max DTE config)
3. Database write failing silently
4. API response format changed (missing expected fields)

**Investigation Steps:**
1. Check raw API response:
   ```python
   # Add logging in op_collector.py
   logger.info(f"Raw API response for {symbol}: {len(response)} contracts")
   ```
2. Check filtering logic:
   ```python
   # Add logging after each filter
   logger.info(f"After strike range filter: {len(contracts)} contracts")
   logger.info(f"After DTE filter: {len(contracts)} contracts")
   ```
3. Check database write:
   ```python
   # Add logging in op_storage.py
   logger.info(f"Attempting to insert {len(contracts)} contracts")
   result = insert_batch(contracts)
   logger.info(f"Inserted {result.rowcount} rows")
   ```

**Fix Approach:**
- If filtering too aggressive → Adjust strike range or DTE in `op_config.py`
- If database write failing → Check disk space, permissions
- If API format changed → Update parsing logic in `op_collector.py`

---

### 2. Duplicate Contract Hash

**Error:** `UNIQUE constraint failed: option_contracts.contract_hash, option_contracts.trade_date`

**Causes:**
- Same contract appearing twice in API response
- Collection running twice on same day (morning + evening both trying to insert same trade_date)
- Deduplication not applied before INSERT

**Fix Approach:**
1. Add deduplication in `op_storage.py` before INSERT
2. Verify trade_date logic (morning vs evening should have different dates if past midnight)
3. Log duplicate occurrences

---

### 3. Missing IV Data

**Error:** Many NULL values in `option_symbol_summary.iv_front_month`, `iv_30dte`, etc.

**Cause:** Not enough contracts with valid IV in DTE bucket

**Not always an error:** Some symbols have sparse option chains (low liquidity, limited expirations)

**Investigation:**
- Check how many contracts have non-NULL IV:
  ```sql
  SELECT symbol, COUNT(*) as contracts_with_iv
  FROM option_contracts
  WHERE trade_date = '2025-11-01' AND iv IS NOT NULL
  GROUP BY symbol
  HAVING contracts_with_iv < 10;
  ```

**Fix if widespread:**
- Widen DTE buckets in `op_symbol_rollup.py`
- Lower minimum IV threshold

---

### 4. Database Locked

**Error:** `OperationalError: database is locked` during morning collection

**Cause:** Querying `datalake.db` while Option Pipeline is writing to it

**Fix:** Use `datalake_query.db` for all analysis queries. Only Option Pipeline should write to primary DB during collection windows (6:30-8:00 AM, 4:30-6:00 PM).

---

## Configuration

**File:** `strategies/option_pipeline/op_config.py`

**Key Settings:**
- `STRIKE_RANGE_PCT` - How far OTM/ITM to collect (default: 0.20 = ±20%)
- `MIN_DTE` - Minimum days to expiration (default: 0)
- `MAX_DTE` - Maximum days to expiration (default: 60-90)
- `MIN_OPEN_INTEREST` - Filter low-OI contracts (default: varies)

**DTE Buckets for IV calculation:**
- Front month: 7-21 DTE
- 30 DTE: 22-35 DTE
- 45 DTE: 36-50 DTE
- 60 DTE: 51-70 DTE

---

## Historical Data Note

**Strike Range Changed 2025-09-18:**
- **Before:** ±50% from underlying price
- **After:** ±20% from underlying price (aligned with Flow Monitor)

**Implication:** Data in `option_contracts` before 2025-09-18 has wider strike range coverage. Queries comparing historical periods should account for this.

---

## Time-Series Calculations

**Option Pipeline calculates:**
- OI changes: 1d, 5d, 10d, 20d
- IV changes: 1d, 5d, 20d
- Volume ratios: vs 5d average, vs 20d average
- Greek momentum: delta/gamma/theta/vega changes
- Build patterns: sudden vs gradual position building

**Data Requirements:**
- Needs at least 5 days of history for 5d calculations
- Needs at least 10 days for 10d calculations
- Needs at least 20 days for 20d calculations

**Fresh Installation:**
- First 20 days will have incomplete time-series
- Normal after 20 trading days of collection

---

## Primary IV Source

**As of October 16, 2025:** `option_symbol_summary` is the primary IV source for:
- Earnings Intel strategy (IV tracking)
- Airline Play strategy
- Morning View TUI
- Any analysis needing symbol-level IV

**Why:** Universal coverage (all 800 symbols daily), bucketed by DTE for term structure.

---

## Critical Files

**Self-Monitoring:**
- `strategies/option_pipeline/op_collector.py` (after collection completes)

**Data Collection:**
- `strategies/option_pipeline/op_collector.py` (API calls, filtering)

**Analysis:**
- `strategies/option_pipeline/op_analyzer.py` (time-series calculations)

**Storage:**
- `strategies/option_pipeline/op_storage.py` (database writes)

**Aggregation:**
- `strategies/option_pipeline/op_symbol_rollup.py` (symbol-level summaries)

**Configuration:**
- `strategies/option_pipeline/op_config.py` (all parameters)

---

## Safe Modifications

**Safe to edit:**
- Strike range and DTE limits in `op_config.py`
- Filtering thresholds (minimum OI, minimum volume)
- Logging levels and messages
- Deduplication logic

**Risky (investigate first):**
- Time-series calculation logic in `op_analyzer.py`
- SQL queries in `op_storage.py`
- DTE bucket definitions
- IV aggregation logic in `op_symbol_rollup.py`

**Never modify:**
- Database schema
- Primary key definitions
- Core calculation formulas without validation

---

## Testing

**Manual test (morning):**
```bash
cd strategies/option_pipeline
python op_main.py --no-interaction
```

**Verify:**
- Contracts stored to `option_contracts` (check row count)
- Symbol summaries created in `option_symbol_summary`
- IV values populated for major symbols (SPY, AAPL, NVDA)
- No duplicate errors in logs

**Expected row counts per run:**
- option_contracts: ~8,000-12,000 new rows
- option_symbol_summary: 800 new rows (one per symbol)

---

## Migration Notes (October 2025)

**Directory renamed:** `oi_delta` → `option_pipeline`
**Files renamed:** `oid_*.py` → `op_*.py` (7 files)
**Tables renamed:**
- `oi_daily` → `option_contracts`
- `oi_symbol_summary` → `option_symbol_summary`

**Columns renamed:**
- `implied_volatility` → `iv`
- `days_to_expiration` → `dte`

**Code references:** All updated. If you see `oid_*` references, they're outdated.

---

*For full system architecture, see `autofix/reference/system_architecture.md`*
*For database schema, see `data/datalake_schema_2026-01-01.md`*
