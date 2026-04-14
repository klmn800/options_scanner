# Flow Monitor Strategy Guide

**Purpose:** Auto-fix reference for Flow Monitor errors
**Updated:** November 1, 2025

---

## Overview

Flow Monitor detects unusual options activity through continuous scanning during market hours (9:15 AM - 5:00 PM ET).

**Key Concept:** Scans run every 20 minutes, storing all contracts in `flow_options_scans` table. Contracts meeting significance thresholds trigger alerts stored in `flow_alerts` table.

---

## Architecture

**Entry Point:** `strategies/flow_monitor/fm_main.py`

**Core Components:**
1. `fm_collector.py` - API calls to Tradier, data collection
2. `fm_analyzer.py` - Z-scoring against baselines
3. `fm_alerts.py` - Alert generation
4. `fm_storage.py` - Database operations + **self-monitoring**
5. `fm_symbol_rollup.py` - End-of-day summaries

**Data Flow:**
```
Tradier API
↓
fm_collector.py (fetch options data)
↓
fm_analyzer.py (calculate significance scores)
↓
fm_storage.py (store to flow_options_scans)
↓
fm_alerts.py (generate alerts if threshold met)
↓
fm_storage.py (store to flow_alerts)
```

---

## Database Tables

**Writes:**
- `flow_options_scans` (24.5M rows) - Every contract from every scan
- `flow_alerts` (468 rows) - Contracts meeting alert thresholds
- `flow_symbol_summary` (1.9K rows) - Daily symbol summaries (evening)

**Reads:**
- `symbol_baselines` (730 rows) - Statistical baselines for Z-scoring
- `symbol_metadata` (740 rows) - Symbol universe, sectors

---

## Self-Monitoring

**Location:** `strategies/flow_monitor/fm_storage.py` (after storing scan results)

**Check Logic:**
```python
# After successful storage to flow_options_scans
# Query: When was last alert generated?
last_alert_time = query("SELECT MAX(alert_timestamp) FROM flow_alerts")

# Calculate time since last alert
time_since_alert = now() - last_alert_time

# If market open AND no alerts in 2+ hours → CRITICAL ERROR
if market_is_open() and time_since_alert > timedelta(hours=2):
    trigger_auto_fix(error_type='no_alerts_2_hours', context={...})
```

**Why this matters:** Alerts should generate regularly during market hours. If none appear for 2+ hours, something is broken (baseline missing, threshold wrong, database writes failing, etc.).

---

## Common Errors

### 1. Duplicate Contract Hash

**Error:** `UNIQUE constraint failed: flow_options_scans.contract_hash, flow_options_scans.scan_timestamp`

**Causes:**
- Tradier API returning duplicate contracts in response
- Threading race condition (same contract processed twice)
- Batch data not deduplicated before INSERT

**Fix Approach:**
1. Add deduplication in `fm_collector.py` at API response level
2. Add deduplication in `fm_storage.py` before batch INSERT
3. Log duplicate occurrences for pattern detection

**Files to check:**
- `strategies/flow_monitor/fm_collector.py` (line ~200-300)
- `strategies/flow_monitor/fm_storage.py` (line ~100-150)

---

### 2. No Alerts Generated (2+ hours)

**Error:** Auto-fix triggered with context "no_alerts_2_hours"

**Possible Causes:**
1. Baseline data missing from `symbol_baselines` table
2. Significance threshold too high (no contracts meet it)
3. Z-score calculation error in `fm_analyzer.py`
4. Database writes succeeding but alerts not being created

**Investigation Steps:**
1. Check if baselines exist:
   ```sql
   SELECT COUNT(*) FROM symbol_baselines WHERE symbol IN (
       SELECT DISTINCT symbol FROM flow_options_scans
       WHERE trade_date = '2025-11-01'
   );
   ```
2. Check significance scores:
   ```sql
   SELECT MAX(significance_score), AVG(significance_score)
   FROM flow_options_scans
   WHERE trade_date = '2025-11-01' AND scan_timestamp > '2025-11-01 09:00:00';
   ```
3. Check alert threshold configuration:
   - `strategies/flow_monitor/fm_analyzer.py` → ALERT_SCORE_THRESHOLD (3.5 as of v2, April 2026)
   - `config.json` → flow_monitor.min_significance_score

**Fix Approach:**
- If baselines missing → Run `fm_baseline_generator.py`
- If threshold too high → Adjust in `fm_analyzer.py` (ALERT_SCORE_THRESHOLD)
- If calculation error → Fix in `fm_analyzer.py`

---

### 3. Database Locked

**Error:** `OperationalError: database is locked`

**Cause:** Querying `datalake.db` during collection window (Flow Monitor uses primary DB for writes)

**Fix:** Change query to use `datalake_query.db` instead

**Files to check:**
- Any analysis scripts or queries in FM evaluation system

---

### 4. API Rate Limit

**Error:** `429 Too Many Requests` from Tradier API

**Cause:** Too many API calls in short period

**Investigation:**
- Check batch size in `fm_collector.py`
- Check retry logic (are we retrying failures too aggressively?)
- Check account limits (should be 120 requests/minute)

**Fix Approach:**
- Reduce batch size (process fewer symbols per batch)
- Add sleep between batches
- Implement exponential backoff for retries

---

### 5. Missing Greeks/IV

**Error:** Alerts generated but Greeks columns are NULL

**Cause:** Tradier doesn't always return Greeks for all contracts (far OTM, low volume)

**Not an error:** This is expected behavior. Some contracts legitimately don't have Greeks.

**No fix needed:** Queries should handle NULL Greeks gracefully with `WHERE delta IS NOT NULL`

---

## Configuration

**File:** `strategies/flow_monitor/fm_config.py`

**Key Settings:**
- `SIGNIFICANCE_THRESHOLD` - Score required to trigger alert (default: ~3.0)
- `SCAN_INTERVAL_MINUTES` - How often to scan (default: 20)
- `STRIKE_RANGE_PCT` - How far OTM/ITM to scan (default: 0.20 = ±20%)
- `MIN_VOLUME` - Minimum volume to consider (default: varies)

**Baseline Settings:**
- Location: `symbol_baselines` table
- Generated by: `fm_baseline_generator.py`
- Update frequency: Weekly (Sundays)

---

## Data Deduplication

**Critical Pattern:** Always deduplicate before database INSERT

**Example (from fm_storage.py):**
```python
# Deduplicate by contract_hash before INSERT
seen_hashes = set()
deduplicated_data = []

for contract in contracts_data:
    hash_key = contract['contract_hash']
    if hash_key not in seen_hashes:
        seen_hashes.add(hash_key)
        deduplicated_data.append(contract)
    else:
        duplicates_found.append(contract)  # Log for diagnostics

# Use deduplicated data for INSERT
insert_batch(deduplicated_data)

# If duplicates found, trigger auto-fix to investigate root cause
if duplicates_found:
    trigger_auto_fix('duplicate_contracts', {
        'count': len(duplicates_found),
        'examples': duplicates_found[:5]
    })
```

---

## Scan Cycle Timing

**Normal Operation:**
```
9:15 AM - Daemon starts
9:20 AM - First scan completes
9:40 AM - Second scan completes
10:00 AM - Third scan completes
... (every 20 minutes)
4:00 PM - Market close, continues scanning
5:00 PM - Daemon stops, switches to rollup mode
5:30 PM - Symbol rollup complete
```

**What to expect:**
- 20+ scans per day
- Each scan: 800 symbols, ~10,000-15,000 contracts
- Alerts: ~5-15 per day (varies by market conditions)
- Total rows inserted: ~200,000-300,000 per day in flow_options_scans

---

## Critical Files

**Self-Monitoring:**
- `strategies/flow_monitor/fm_storage.py` (line ~116+ for auto-fix trigger)

**Data Collection:**
- `strategies/flow_monitor/fm_collector.py` (API calls, deduplication)

**Analysis:**
- `strategies/flow_monitor/fm_analyzer.py` (Z-scoring, significance calculation)

**Alert Generation:**
- `strategies/flow_monitor/fm_alerts.py` (threshold checking, alert creation)

**Configuration:**
- `strategies/flow_monitor/fm_config.py` (all tunable parameters)

---

## Safe Modifications

**Safe to edit:**
- Threshold values in `fm_config.py`
- Deduplication logic in `fm_storage.py` and `fm_collector.py`
- Logging levels and messages
- Error handling and retry logic

**Risky (investigate first):**
- Z-score calculation in `fm_analyzer.py`
- SQL queries in `fm_storage.py`
- Threading/concurrency logic
- API request construction in `fm_collector.py`

**Never modify:**
- Database schema
- Core library imports
- Main daemon control flow (without thorough testing)

---

## Testing

**Manual test:**
```bash
cd strategies/flow_monitor
python fm_main.py --start-daemon --no-interaction
```

**Verify:**
- Scans complete without errors
- Data appears in `flow_options_scans` table
- Alerts generated if unusual activity exists
- No duplicate errors in logs

**Test deduplication:**
- Check logs for "deduplicated X contracts" messages
- Should be 0 duplicates in normal operation
- If >0, investigate root cause

---

*For full system architecture, see `autofix/reference/system_architecture.md`*
*For database schema, see `data/datalake_schema_2026-01-01.md`*
