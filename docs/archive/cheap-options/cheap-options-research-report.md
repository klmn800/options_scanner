# Cheap Options Scalping Research Report

**Research Period:** Aug 18 - Oct 15, 2025
**Training Period:** Aug 18 - Sept 30, 2025
**Holdout Period:** Oct 1 - Oct 15, 2025 (LOCKED until Phase 6)
**Date Started:** 2025-10-15

---

## Executive Summary

TBD - Will be completed after Phase 7

---

## Phase 1: Define Tradeable Universe

### Objective
Establish broad constraints based on theory and determine which universe (ETFs vs Stocks) has sufficient data for analysis.

### Theory-Driven Constraints
```sql
ask >= 0.03 AND ask <= 0.10    -- Cheap but not worthless
dte >= 15 AND dte <= 60         -- Not too close/far from expiry
bid > 0 AND ask > 0             -- Must be tradeable
vega IS NOT NULL                -- Need greeks data
```

### Universe Definitions

**Universe A: ETF Options**
- Symbols: SPY, QQQ, IWM, DIA, XLF, XLI, XLK, XLE, XLV, XLY, XLP

**Universe B: Stock Options**
- All symbols except Universe A ETFs and VIX

### Results

**Data Source:** `datalake_query.db` → `flow_options_scans` table

**Training Period Coverage:** 24 trading days (Aug 18 - Sept 30, 2025)

| Universe | Total Entries | Unique Contracts | Trading Days |
|----------|--------------|------------------|--------------|
| Universe A (ETFs) | 15,685 | 226 | 21 |
| Universe B (Stocks) | 66,867 | 1,641 | 24 |

**Daily Breakdown of Cheap Options (All Universes):**

| Date | Total Scans | Cheap Options (15-60 DTE, $0.03-0.10) |
|------|-------------|---------------------------------------|
| 2025-08-18 | 126,599 | 311 |
| 2025-08-19 | 18,589 | 50 |
| 2025-08-28 | 93,639 | 278 |
| 2025-08-29 | 247,643 | 877 |
| 2025-09-03 | 123,669 | 678 |
| 2025-09-04 | 206,130 | 618 |
| 2025-09-05 | 323,752 | 1,079 |
| 2025-09-08 | 450,691 | 1,847 |
| 2025-09-09 | 479,965 | 2,096 |
| 2025-09-10 | 286,919 | 1,216 |
| 2025-09-11 | 275,452 | 926 |
| 2025-09-12 | 309,820 | 1,144 |
| 2025-09-15 | 439,853 | 1,988 |
| 2025-09-16 | 528,807 | 2,395 |
| 2025-09-17 | 687,327 | 3,396 |
| 2025-09-18 | 660,666 | 3,775 |
| 2025-09-19 | 675,079 | 4,026 |
| 2025-09-22 | 1,130,872 | 7,261 |
| 2025-09-23 | 945,558 | 6,389 |
| 2025-09-24 | 999,274 | 7,250 |
| 2025-09-25 | 833,150 | 5,301 |
| 2025-09-26 | 1,218,929 | 8,031 |
| 2025-09-29 | 1,311,642 | 11,446 |
| 2025-09-30 | 1,329,483 | 10,174 |
| **TOTAL** | **11,683,508** | **82,552** |

### Decision
**Proceed with Universe B (Stock Options)** - 4.3x more entries and 7.3x more unique contracts than Universe A, providing better statistical power for pattern discovery.

### Notes
- Both universes exceed minimum threshold of 20 entries
- Data gaps in late August (Aug 20-27) due to options scanner startup timing
- Significant increase in cheap options opportunities from early Sept to late Sept (10x growth)
- All data sourced from `flow_options_scans` table which contains comprehensive historical scans

---

## Phase 2: Identify Winners in Training Data

### Objective
TBD

---

## Supporting Queries

### Query 1: Universe A Count (Training Period)
```sql
SELECT
    COUNT(*) as total_entries,
    COUNT(DISTINCT contract_hash) as unique_contracts,
    COUNT(DISTINCT trade_date) as trading_days
FROM flow_options_scans
WHERE trade_date >= '2025-08-18'
    AND trade_date <= '2025-09-30'
    AND ask >= 0.03 AND ask <= 0.10
    AND dte >= 15 AND dte <= 60
    AND bid > 0 AND ask > 0
    AND vega IS NOT NULL
    AND symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLI', 'XLK', 'XLE', 'XLV', 'XLY', 'XLP')
```

**Result:**
```
total_entries | unique_contracts | trading_days
-----------------------------------------------
15685         | 226              | 21
```

### Query 2: Universe B Count (Training Period)
```sql
SELECT
    COUNT(*) as total_entries,
    COUNT(DISTINCT contract_hash) as unique_contracts,
    COUNT(DISTINCT trade_date) as trading_days
FROM flow_options_scans
WHERE trade_date >= '2025-08-18'
    AND trade_date <= '2025-09-30'
    AND ask >= 0.03 AND ask <= 0.10
    AND dte >= 15 AND dte <= 60
    AND bid > 0 AND ask > 0
    AND vega IS NOT NULL
    AND symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLI', 'XLK', 'XLE', 'XLV', 'XLY', 'XLP', 'VIX')
```

**Result:**
```
total_entries | unique_contracts | trading_days
-----------------------------------------------
66867         | 1641             | 24
```

### Query 3: Daily Breakdown
```sql
SELECT
    trade_date,
    COUNT(*) as total,
    COUNT(CASE WHEN ask BETWEEN 0.03 AND 0.10
               AND dte BETWEEN 15 AND 60
               AND bid > 0
               AND vega IS NOT NULL THEN 1 END) as cheap_options
FROM flow_options_scans
WHERE trade_date BETWEEN '2025-08-18' AND '2025-09-30'
GROUP BY trade_date
ORDER BY trade_date
```

**Result:** See Daily Breakdown table in Phase 1 Results section above.

---

## Data Quality Notes

- **Database:** `datalake_query.db` (read-only query database, synced from production)
- **Table:** `flow_options_scans` - comprehensive historical options scans
- **Date Range Verification:** Min date = 2025-08-18, Max date = 2025-10-15, Total days = 35
- **Archive Databases:** Monthly archives exist (`archive_2025_08.db`, etc.) but contain only expired contracts organized by expiration month, not needed for this analysis
- **Holdout Data:** Oct 1-15 data exists but has NOT been queried yet per research protocol
