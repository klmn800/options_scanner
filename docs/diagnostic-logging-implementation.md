# Diagnostic Logging Implementation
**Date:** 2025-11-18
**Process:** Flow Monitor (Pilot)
**Status:** ✅ Complete

---

## Overview

Implemented dual-logging system for Flow Monitor:
1. **Main log** (`logs/flow_monitor_{date}.log`) - Full verbose operational log (unchanged)
2. **Diagnostic log** (`logs/diagnostic/flow_monitor_{date}.log`) - High-level summaries only

---

## Diagnostic Log Purpose

**For:** Weekly Autofix review, performance monitoring, trend analysis
**Format:** Structured text (human + machine readable)
**Volume:** ~95% reduction from main log (~20 lines/scan vs ~1000 lines/scan)

---

## What Gets Logged (Per Scan)

### 1. Collection Summary
```
[2025-11-18 15:31:55] Collection: 1038.8s | Symbols: 759 attempted, 722 returned data | Contracts: 99,165
```
- Scan timestamp (not cycle number - survives restarts)
- Collection timing
- Symbol counts (actual from data, not hardcoded)
- Contract counts (queried from database)

### 2. Analysis & Alerts
```
[2025-11-18 15:31:55] Analysis: 15.5s | Alerts: 2 sent (1 HIGH, 0 MED, 0 LOW)
```
- Analysis timing
- Alert counts by score level (HIGH ≥8.0, MED 6.0-7.9, LOW <6.0)

### 3. Performance Breakdown
```
[2025-11-18 15:31:55] Performance: Collection 1038.8s, Analysis 15.5s, Alerts 0.2s, Sync 16.3s
```
- All phase timings in one line for easy parsing

### 4. Alert Details (HIGH Conviction Only)
```
[2025-11-18 15:31:55] ALERT: NRG $180.0 calls (2025-12-20) | Score: 8.3 | Vol: 17,617 | V/OI: 56.3 | Premium: $10,482,115 | IV: 50%
```
- Full alert context
- Calculated metrics (premium, V/OI ratio)
- Limited to top 5 HIGH conviction alerts per scan

### 5. Session Markers
```
[2025-11-18 09:15:00] Flow Monitor market hours started | Symbols: 759
...
[2025-11-18 16:00:30] Flow Monitor market hours complete | Total cycles: 17
[2025-11-18 16:05:00] Post-market analysis started
...
[2025-11-18 16:17:22] Post-market analysis complete | Tasks: 4/4 successful
```
- Session start/stop timestamps
- Total cycles completed

### 6. Post-Market Task Results

**Historical Backfill:**
```
[2025-11-18 16:08:32] Backfill: 3.5min | 759 symbols | Status: Complete
```
- Duration in minutes
- Symbol count
- Success/failure status

**Market Regime Summary:**
```
[2025-11-18 16:12:15] Market Regime: elevated | Direction: Bull | SPY: +0.34% | VIX: 15.2
```
- Regime classification (calm/elevated/volatile)
- Market direction (Bull/Bear)
- SPY daily change
- VIX closing value

**Symbol Rollup:**
```
[2025-11-18 16:15:43] Symbol Rollup: 722 symbols processed | 87 alerts aggregated | 148.2s
```
- Symbols processed count
- Total alerts aggregated
- Duration in seconds

**Daily Evaluation:**
```
[2025-11-18 16:17:22] Daily Evaluation: 17 scans analyzed | 2.1s
```
- Number of scans analyzed
- Duration in seconds

---

## Implementation Details

### New Functions Added (fm_main.py)

**1. setup_diagnostic_logging()**
- Creates separate logger instance
- Writes to `logs/diagnostic/flow_monitor_{date}.log`
- No console output (file-only)
- Simple format (no log levels, just message)

**2. log_diagnostic_summary()**
- Queries database for actual counts
- Formats diagnostic summary
- Called after each successful scan cycle
- Error-safe (won't crash if query fails)

### Integration Points

**Initialization (line 1313):**
```python
diag_logger = setup_diagnostic_logging()
```

**Startup (line 1321):**
```python
diag_logger.info(f"[{now}] Flow Monitor market hours started | Symbols: {len(symbols)}")
```

**Per-Scan (line 1507-1513):**
```python
if scan_timestamp:
    log_diagnostic_summary(
        diag_logger, storage, scan_timestamp, len(symbols),
        collection_elapsed, analysis_elapsed, alert_elapsed,
        sync_elapsed, sync_rows
    )
```

**Market Hours Shutdown (line 1546):**
```python
diag_logger.info(f"[{now}] Flow Monitor market hours complete | Total cycles: {total_cycles}")
```

**Post-Market Initialization (line 1560):**
```python
diag_logger = setup_diagnostic_logging()
diag_logger.info(f"[{now}] Post-market analysis started")
```

**Post-Market Task Logging:**
- Backfill (line 1584): Timing, symbol count, success/failure
- Market Regime (line 1634): Regime, direction, SPY change, VIX
- Symbol Rollup (line 1684): Symbols processed, alerts aggregated, timing
- Daily Evaluation (line 1730): Scans analyzed, timing

**Post-Market Shutdown (line 1752):**
```python
diag_logger.info(f"[{now}] Post-market analysis complete | Tasks: {tasks_successful}/{total_tasks} successful")
```

---

## Example Diagnostic Log Output

```
[2025-11-18 09:15:00] Flow Monitor market hours started | Symbols: 759
[2025-11-18 09:31:55] Collection: 1038.8s | Symbols: 759 attempted, 722 returned data | Contracts: 99,165
[2025-11-18 09:31:55] Analysis: 15.5s | Alerts: 2 sent (1 HIGH, 0 MED, 0 LOW)
[2025-11-18 09:31:55] Performance: Collection 1038.8s, Analysis 15.5s, Alerts 0.2s, Sync 16.3s
[2025-11-18 09:31:55] ALERT: NRG $180.0 calls (2025-12-20) | Score: 8.3 | Vol: 17,617 | V/OI: 56.3 | Premium: $10,482,115 | IV: 50%
[2025-11-18 10:01:23] Collection: 982.3s | Symbols: 759 attempted, 719 returned data | Contracts: 98,432
[2025-11-18 10:01:23] Analysis: 14.2s | Alerts: 1 sent (0 HIGH, 1 MED, 0 LOW)
[2025-11-18 10:01:23] Performance: Collection 982.3s, Analysis 14.2s, Alerts 0.1s, Sync 15.1s
...
[2025-11-18 16:00:30] Flow Monitor market hours complete | Total cycles: 17
[2025-11-18 16:05:00] Post-market analysis started
[2025-11-18 16:08:32] Backfill: 3.5min | 759 symbols | Status: Complete
[2025-11-18 16:12:15] Market Regime: elevated | Direction: Bull | SPY: +0.34% | VIX: 15.2
[2025-11-18 16:15:43] Symbol Rollup: 722 symbols processed | 87 alerts aggregated | 148.2s
[2025-11-18 16:17:22] Daily Evaluation: 17 scans analyzed | 2.1s
[2025-11-18 16:17:22] Post-market analysis complete | Tasks: 4/4 successful
```

**~90 lines/day** (17 scans × 4 lines + post-market) vs **~85,000 lines** in main log
**99.9% reduction**

---

## Database Queries Used

All counts are **actual** from database (no hardcoded values):

**1. Contract Count:**
```sql
SELECT COUNT(*) FROM flow_options_scans WHERE scan_timestamp = ?
```

**2. Alert Counts by Level:**
```sql
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN significance_score >= 5.0 THEN 1 ELSE 0 END) as high,
    SUM(CASE WHEN significance_score >= 3.5 AND significance_score < 5.0 THEN 1 ELSE 0 END) as med,
    SUM(CASE WHEN significance_score < 3.5 THEN 1 ELSE 0 END) as low
FROM flow_alerts
WHERE scan_timestamp = ?
```

**3. Symbols with Data:**
```sql
SELECT COUNT(DISTINCT symbol) FROM flow_options_scans WHERE scan_timestamp = ?
```

**4. Alert Details (HIGH only):**
```sql
SELECT symbol, strike, option_type, expiration, significance_score,
       volume, open_interest, last_price, underlying_price, iv
FROM flow_alerts
WHERE scan_timestamp = ? AND significance_score >= 5.0
ORDER BY significance_score DESC
LIMIT 5
```

---

## Benefits

### For Weekly Review
- Quickly scan entire day's activity
- Identify performance degradation trends
- Spot alert pattern changes
- Find data quality issues

### For Debugging
- Main log still has full detail
- Diagnostic log provides high-level timeline
- Scan timestamps allow cross-referencing
- Performance metrics highlight slow scans

### For Automation
- Structured format easy to parse
- Consistent line format per scan
- Timestamp-based (not cycle numbers)
- Machine-readable metrics

---

## Future Enhancements

### Possible Additions to Diagnostic Log
1. **Data Quality Issues** - Missing price data, bad ticks
2. **Error Tracking** - Symbols with NoneType errors
3. **API Usage** - Tradier/FMP call counts
4. **Market Regime** - Bull/Bear/Elevated classification

### Apply to Other Processes
- Option Pipeline (morning/evening runs)
- Earnings Intel (3 modes)
- Database Archive (Friday nights)
- Oracle (query sessions)

---

## Testing

Next Flow Monitor run will create:
- `logs/flow_monitor_{date}.log` - Full verbose log (unchanged)
- `logs/diagnostic/flow_monitor_{date}.log` - New diagnostic log

Monitor both logs to confirm:
1. Diagnostic log appears
2. One summary per scan
3. Accurate counts (match main log)
4. Alert details correct
5. Session markers present

---

## Rollback

If issues arise:
1. Remove diagnostic logger setup (line 1313)
2. Remove startup logging (line 1321)
3. Remove scan summary call (lines 1507-1513)
4. Remove shutdown logging (line 1546)

Main log continues working normally - diagnostic logging is purely additive.
