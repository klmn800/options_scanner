# Autofix Integration Audit
**Date**: 2025-11-14
**Status**: In Progress

---

## Overview

This document tracks all critical failure points in the system and their autofix integration status.

**Legend**:
- ✅ **INTEGRATED** - Has autofix error handling
- 🟡 **PARTIAL** - Some errors handled, gaps remain
- ❌ **MISSING** - No autofix integration
- ⚠️ **CRITICAL** - High priority for autonomous maintenance

---

## Data Collection Scripts

### ✅ Flow Monitor (strategies/flow_monitor/)
**Status**: INTEGRATED (CRITICAL severity)

**Files**:
- `fm_collector.py` - Line 197-211

**Triggers**:
- `fm_collection_zero_alerts` - Zero contracts stored despite collection
- `fm_duplicate_contracts` - Duplicate contract hashes detected

**Severity**: CRITICAL (immediate spawn)

---

### ✅ Option Pipeline (strategies/option_pipeline/)
**Status**: INTEGRATED (mixed severity)

**Files**:
- `op_main.py` - Multiple integration points

**Triggers**:
- `op_collection_zero_contracts` - Line 325-340 (CRITICAL)
- `op_collection_failed` - Line 366-381 (CRITICAL)
- `op_collection_unexpected_error` - Line 396-409 (CRITICAL)
- `op_rollup_failed` - Line 600-611 (ERROR)
- `op_timing_failed` - Line 673-683 (ERROR)

**Severity**: CRITICAL for collection, ERROR for analysis/rollup

---

### 🟡 Earnings Intelligence (strategies/earnings_intel/)
**Status**: PARTIAL

**Files**:
- `ei_main.py` - Multiple handlers

**Integrated Triggers**:
- `earnings_fetch_failed` - Line 237-242 (ERROR)
- `earnings_archive_failed` - Line 278-284 (CRITICAL - schema errors)
- `earnings_cleanup_failed` - Line 307-313 (ERROR)
- `earnings_snapshot_collection_failed` - Line 385-391 (ERROR)
- `earnings_post_calc_failed` - Line 404-410 (ERROR)
- `earnings_expected_moves_failed` - Line 425-431 (ERROR)
- `earnings_scanner_failed` - Line 512-518 (ERROR)
- `earnings_weekly_refresh_unexpected` - Line 335-341 (CRITICAL)
- `earnings_daily_pipeline_unexpected` - Line 456-462 (CRITICAL)
- `earnings_morning_scan_unexpected` - Line 538-544 (CRITICAL)
- `earnings_main_fatal` - Line 796-802 (CRITICAL)

**Missing Coverage**:
- Individual component failures within ei_snapshot_collector.py
- Individual component failures within ei_post_earnings_calc.py
- Individual component failures within ei_arbitrage_scanner.py

**Priority**: Medium - orchestrator has good coverage, component internals could use more

---

### ✅ Tradier Historical Backfill (data/)
**Status**: INTEGRATED (migrated from FMP on 2025-11-17)

**Files**:
- `tradier_historical_backfill.py` - Line 298-312

**Triggers**:
- `tradier_backfill_high_failure_rate` - Triggers if:
  - >15% symbol failure rate

**Severity**: ERROR (batch mode)

**Context Provided**:
- Failed symbol count and failure rate
- HTTP 403 count
- API calls made
- Records successfully updated
- Sample of failed symbols (first 20)

---

### ❌ YFinance Historical Backfill (data/)
**Status**: MISSING

**Files**:
- `yfinance_historical_backfill.py`

**Known Failure Points**:
- API timeouts
- Rate limiting
- Invalid symbols
- Network errors
- Data parsing failures

**Priority**: ⚠️ **HIGH** - Used for price data fallback

**Recommended Integration**:
```python
# After backfill completes
if failed_symbols and (len(failed_symbols) > 50 or failure_rate > 0.15):
    queue_error(
        error_type='yfinance_backfill_high_failure_rate',
        context={...},
        severity='ERROR'
    )
```

---

### ❌ YFinance Earnings Historical (data/)
**Status**: MISSING

**Files**:
- `yfinance_earnings_historical.py`

**Known Failure Points**:
- API failures
- Missing earnings data
- Date parsing errors
- Symbol lookup failures

**Priority**: Medium - Used for historical earnings backfill

**Recommended Integration**:
```python
# After backfill completes
if errors_occurred or data_quality_issues:
    queue_error(
        error_type='yfinance_earnings_backfill_failed',
        context={...},
        severity='ERROR'
    )
```

---

### ❌ FMP Symbol Metadata (data/)
**Status**: MISSING

**Files**:
- `fmp_symbol_metadata.py`

**Known Failure Points**:
- API failures (403, 429)
- Sector/industry missing
- Market cap missing
- Company name lookup failures

**Priority**: Medium - Used for sector routing and analysis

**Recommended Integration**:
```python
# After metadata collection
if failed_symbols or critical_fields_missing:
    queue_error(
        error_type='fmp_metadata_collection_failed',
        context={...},
        severity='ERROR'
    )
```

---

### ❌ News Sentiment (tools/)
**Status**: MISSING

**Files**:
- `tools/news_sentiment.py` (replaced `av_news_symbol.py` and `strategies/news_collector/` as of Feb 2026)

**Known Failure Points**:
- Alpha Vantage API quota exhaustion (25 calls/day, single key)
- IP-level rate limiting (API returns rate-limit messages despite budget remaining)
- Network timeouts
- JSON parsing errors

**Priority**: Low - News is supplementary data, runs inline with Flow Monitor

**Recommended Integration**:
```python
# After news sentiment fetch
if api_quota_exhausted or high_failure_rate:
    queue_error(
        error_type='news_sentiment_fetch_failed',
        context={...},
        severity='ERROR'
    )
```

---

### ❌ Market Daily Summary (data/)
**Status**: MISSING

**Files**:
- `market_daily_summary.py`

**Known Failure Points**:
- SPY/QQQ/IWM data missing
- VIX data missing
- Database write failures
- Calculation errors (ATR, regime detection)

**Priority**: ⚠️ **HIGH** - Critical for market context

**Recommended Integration**:
```python
# After summary calculation
if critical_data_missing or calculation_failed:
    queue_error(
        error_type='market_summary_calculation_failed',
        context={...},
        severity='CRITICAL'  # Market context is critical
    )
```

---

### ❌ Database Backup (data/health/)
**Status**: MISSING

**Files**:
- `db_backup.py`

**Known Failure Points**:
- Disk space exhausted
- Backup corruption
- Sync failures
- File permission errors

**Priority**: ⚠️ **CRITICAL** - Data protection

**Recommended Integration**:
```python
# After backup/sync
if backup_failed or sync_failed or corruption_detected:
    queue_error(
        error_type='database_backup_failed',
        context={...},
        severity='CRITICAL'  # Data loss risk
    )
```

---

### ❌ Database Archive (data/health/)
**Status**: MISSING

**Files**:
- `db_archive_sector.py`

**Known Failure Points**:
- Archive file corruption
- Disk space exhausted
- Sector routing failures
- Data integrity issues

**Priority**: ⚠️ **HIGH** - Archive failures = data loss

**Recommended Integration**:
```python
# After archive operation
if archive_failed or integrity_check_failed:
    queue_error(
        error_type='database_archive_failed',
        context={...},
        severity='CRITICAL'  # Archive failures = permanent data loss
    )
```

---

## System Operations (main.py)

### 🟡 Main Orchestrator
**Status**: PARTIAL

**Files**:
- `main.py`

**Integrated Triggers**:
- Pipeline-level failures have autofix in component files
- Top-level orchestrator catches some errors

**Missing Coverage**:
- Database connection failures
- Scheduler failures
- Endless loop crashes
- Memory exhaustion
- Market calendar failures

**Priority**: ⚠️ **HIGH** - Core system stability

**Recommended Integration**:
```python
# In main daily sequence error handler
except Exception as e:
    queue_error(
        error_type='orchestrator_daily_sequence_failed',
        context={...},
        severity='CRITICAL'
    )
```

---

## Summary Statistics

**Total Scripts Audited**: 15

**Integration Status**:
- ✅ Fully Integrated: 3 (Flow Monitor, Option Pipeline, Tradier Historical Backfill)
- 🟡 Partially Integrated: 2 (Earnings Intel, Main.py)
- ❌ Missing Integration: 10

**Priority Breakdown**:
- ⚠️ CRITICAL Priority: 4 scripts
  - Market Daily Summary
  - Database Backup
  - Database Archive
  - Main Orchestrator gaps

- High Priority: 1 script
  - YFinance Historical Backfill

- Medium Priority: 3 scripts
  - YFinance Earnings Historical
  - FMP Symbol Metadata
  - Earnings Intel component internals

- Low Priority: 1 script
  - Alpha Vantage News

---

## Next Steps

### Immediate (This Week)
1. ✅ FMP Historical Backfill - COMPLETED 2025-11-14
2. Market Daily Summary - Critical for context
3. Database Backup - Critical for safety
4. Database Archive - Critical for data integrity

### Short Term (This Month)
5. YFinance Historical Backfill - Fallback coverage
6. Main Orchestrator gaps - System stability
7. FMP Symbol Metadata - Sector routing

### Medium Term (This Quarter)
8. YFinance Earnings Historical - Data completeness
9. Earnings Intel component internals - Deeper coverage
10. Alpha Vantage News - Supplementary data

---

## Integration Pattern Template

```python
# At end of collection/processing function:

# Track failures during processing
failed_items = []
error_counts = {'timeout': 0, 'forbidden': 0, 'other': 0}

# ... processing loop ...

# After processing completes
if failed_items:
    failure_rate = len(failed_items) / total_items

    # Define thresholds
    should_alert = (
        error_counts['forbidden'] >= 5 or  # API auth issues
        failure_rate > 0.15 or              # >15% failure rate
        len(failed_items) > 50              # Absolute count threshold
    )

    if should_alert:
        from tools.autofix import queue_error
        queue_error(
            error_type='component_name_failure_type',
            context={
                'failed_count': len(failed_items),
                'total_count': total_items,
                'failure_rate': round(failure_rate, 3),
                'error_breakdown': error_counts,
                'failed_sample': failed_items[:20]  # First 20 for debugging
            },
            severity='ERROR'  # or 'CRITICAL' if immediate action needed
        )
```

---

**Last Updated**: 2026-02-07
**Next Review**: Ongoing — update when new modules are added or integrations completed
