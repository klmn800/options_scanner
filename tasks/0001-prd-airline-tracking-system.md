# PRD: Airline Play Tracking System

**Document ID:** 0001
**Feature Name:** Airline Play Tracking System
**Author:** Ben & Claude
**Date Created:** 2025-10-01
**Status:** Draft → Approved
**Target Release:** Phase 1 - Core Tracking Infrastructure

---

## Executive Summary

Build a dedicated tracking system for airline industry options data by extracting and isolating relevant information from the main KLMN 800 universe into focused airline-specific tables. This creates a foundation for analyzing volatility patterns in airline stocks (particularly the observed "lock-step" behavior in DAL/UAL/AAL) without the noise of the broader market.

---

## Problem Statement

### Current State
- Airline options data exists scattered across general-purpose tables (`oi_daily`, `oi_symbol_summary`, `historical_prices`, etc.) mixed with 700+ other symbols
- No convenient way to analyze airline-specific patterns without complex queries filtering through massive datasets
- Observed "lock-step" volatility pattern in primary airlines (DAL/UAL/AAL) cannot be easily studied or validated

### Desired State
- Dedicated `airline_symbol_tracking` table with daily symbol-level metrics for 7 airline tickers
- Dedicated `airline_options_tracking` table with contract-level data for ATM/near-money options (±10% strike range, ≤60 DTE)
- Automated evening pipeline that extracts airline data from existing tables into airline-specific tables
- Clean isolation enabling focused analysis, backtesting, and future pattern detection

---

## Goals & Success Criteria

### Primary Goal
**Automate daily population of airline tracking tables with complete data from existing sources.**

### Success Metrics
✅ **Tables populate successfully every evening** after OID pipeline and historical backfill complete
✅ **Data completeness**: All 7 symbols tracked daily (gaps acceptable for historical data, not for new data)
✅ **Processing time**: Airline tracking phase completes in <5 minutes
✅ **Error visibility**: Missing data or failures logged clearly without stopping the overall pipeline
✅ **Backfill capability**: Historical data from 2025-08-08 can be loaded via separate backfill script

### Non-Goals (Out of Scope for Phase 1)
❌ Pattern detection or correlation analysis (lock-step behavior validation)
❌ Backtesting framework for airline volatility strategies
❌ Integration with Chrome extension or flow alerts
❌ Real-time intraday tracking
❌ Automated trading signals based on airline data
❌ Expansion to other industries (hotels, cruise lines, etc.)

---

## User Personas

### Primary User: Ben (Trader/System Owner)
- **Need:** Isolated dataset to analyze airline option patterns without filtering through 700+ symbols
- **Use Case:** Evening review of airline positions, identify interesting setups, prepare for next trading day
- **Pain Point:** Too much noise in general tables; hard to spot airline-specific trends quickly

### Secondary User: Daily Analysis Module (Automated System)
- **Need:** Clean airline data feed for future integration with daily_analysis pipelines
- **Use Case:** Eventually consume airline tracking data for AI-driven insights (Oracle integration)
- **Pain Point:** TBD - integration points not yet defined

---

## Feature Requirements

### 1. Database Schema (Already Defined)

#### Table: `airline_symbol_tracking`
**Purpose:** Daily symbol-level metrics for airline stocks
**Primary Key:** (symbol, trade_date)
**Source Tables:** historical_prices, oi_symbol_summary, options_symbol_summary, earnings_calendar, news_symbol_sentiment, flow_alerts

**Key Fields:**
- Price/volume data from `historical_prices`
- OI aggregations and time distributions from `oi_symbol_summary`
- IV metrics by DTE (front_month, 30/45/60 DTE) from `options_symbol_summary`
- Earnings proximity from `earnings_calendar`
- Sentiment scores from `news_symbol_sentiment`
- Flow alert counts and recency from `flow_alerts`

#### Table: `airline_options_tracking`
**Purpose:** Contract-level tracking for airline options (ATM/near-money focus)
**Primary Key:** (contract_hash, trade_date)
**Source Table:** `oi_daily` (primary), `earnings_calendar` (supplemental)

**Filtering Logic:**
- ±10% strike range from current underlying price (recalculated daily)
- Days to expiration ≤ 60 (matches current OID collector range)
- All fields already available in `oi_daily` (volume, OI, Greeks, IV tracking, momentum indicators)

### 2. Symbol Universe

**Tracked Symbols (7 total):**
- **Primary (lock-step pattern):** DAL, UAL, AAL
- **Secondary (related but less correlated):** LUV, JBLU, ALK
- **ETF:** JETS

**Implementation:** Add `AIRLINE_PLAY_SYMBOLS` list to `core/symbols_klmn800.py` as a distinct chunk within the KLMN 800 universe (don't create separate universe).

### 3. Pipeline Scripts

#### `ap_symbol_tracking.py`
**Function:** Extract and aggregate symbol-level data
**Writes To:** `airline_symbol_tracking` table
**Processing:**
- Loop through 7 airline symbols
- Pull latest data from each source table for current trade_date
- Apply decimal formatting per policy (prices=2, Greeks/IV=4, ratios=4, scores=2)
- Insert/update rows with ON CONFLICT handling

#### `ap_options_tracking.py`
**Function:** Filter and copy contract-level data
**Writes To:** `airline_options_tracking` table
**Processing:**
- For each airline symbol, get current underlying price
- Calculate ±10% strike range
- Query `oi_daily` for contracts matching: symbol, strike range, DTE ≤ 60, trade_date
- Copy contract data with earnings proximity calculation
- Insert/update with ON CONFLICT handling

#### `ap_backfill.py` (Separate Utility)
**Function:** One-time historical data load
**Date Range:** 2025-08-08 (earliest complete `oi_daily` data) through yesterday
**Execution:** Manual invocation, not part of nightly pipeline
**Behavior:**
- Iterate through each date in range
- Run same logic as daily scripts for that date
- Log progress and gaps (JETS missing after 8/22, UAL not until 9/3, etc.)
- Graceful handling of incomplete data (populate what exists, log what's missing)

### 4. Orchestration in `main.py`

**New Flag:** `--airline-play`

**Execution Order:**
```
Evening Pipeline:
1. OID Evening (oid_analyzer.py) → updates oi_daily, oi_symbol_summary
2. Historical Backfill → updates historical_prices
3. → AIRLINE PLAY PHASE ← (NEW)
   3a. ap_symbol_tracking.py
   3b. ap_options_tracking.py
4. Daily Analysis → daily_analysis_* tables
```

**Progress Logging Requirements:**
- Timestamp at start: "Starting Airline Play tracking at 18:45:32 ET..."
- Per-symbol progress: "Processing DAL... 45 contracts tracked"
- Summary stats: "Airline tracking complete: 7 symbols, 287 contracts, 4.2 seconds"
- Error visibility: "WARNING: JETS options data unavailable for 2025-10-01"

**Error Handling:**
- ❌ **Don't stop pipeline** if airline tracking fails
- ✅ **Log errors clearly** with symbol/table/reason details
- ✅ **Continue to next symbol** if one fails
- ✅ **Fail loudly** but gracefully (log ERROR level, don't raise unhandled exceptions)

### 5. Data Quality & Completeness

**Acceptable Gaps (Historical):**
- JETS: no `oi_daily` after 2025-08-22
- UAL: no `oi_daily` before 2025-09-03
- JBLU: only 16 days in `oi_daily` vs 70 in other tables

**Future Data Expectations:**
- Going forward (post-backfill), expect complete daily coverage
- If a symbol has no options data, log warning but continue processing
- Populate symbol-level tracking even if options tracking is incomplete (better than nothing)

**Metadata Fields:**
- `analysis_timestamp`: When extraction ran
- `last_updated_timestamp`: When row was last modified

### 6. Strike Range Drift Handling

**Daily Recalculation:**
- Each evening, recalculate ±10% strike range based on current `underlying_price`
- Example: DAL at $50 → track $45-$55 strikes today, but if tomorrow it's $52 → track $46.80-$57.20
- **Result:** Contracts naturally drift in/out of tracking as prices move
- **Intentional Design:** Focus stays on ATM/near-money; no need to track deep OTM contracts indefinitely

**Historical Continuity:**
- A contract tracked yesterday may not be tracked today if it drifted outside ±10%
- This is acceptable - we're not tracking individual contract lifecycles, we're tracking the ATM region over time

---

## Technical Design

### Data Flow Diagram
```
┌─────────────────────────────────────────────────────────────┐
│ Existing Tables (Updated by OID/FM/Historical Pipelines)   │
├─────────────────────────────────────────────────────────────┤
│ oi_daily                                                    │
│ oi_symbol_summary                                           │
│ historical_prices                                           │
│ options_symbol_summary                                      │
│ earnings_calendar                                           │
│ news_symbol_sentiment                                       │
│ flow_alerts                                                 │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  AIRLINE PLAY EXTRACTION PHASE    │
    │  (Runs after OID/Historical)      │
    ├───────────────────────────────────┤
    │  1. ap_symbol_tracking.py         │
    │     └─> airline_symbol_tracking   │
    │                                   │
    │  2. ap_options_tracking.py        │
    │     └─> airline_options_tracking  │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  Daily Analysis Module            │
    │  (Future integration TBD)         │
    └───────────────────────────────────┘
```

### Field Mapping Examples

#### Symbol Tracking Example (DAL on 2025-10-01)
```python
{
  'symbol': 'DAL',
  'trade_date': '2025-10-01',
  'close_price': 49.85,  # from historical_prices
  'volume': 8_234_567,  # from historical_prices
  'total_open_interest': 387_294,  # from oi_symbol_summary
  'put_call_ratio': 1.23,  # from oi_symbol_summary
  'iv_front_month': 0.3245,  # from options_symbol_summary
  'iv_30dte': 0.2987,  # from options_symbol_summary
  'earnings_days_ahead': 12,  # calculated from earnings_calendar
  'news_sentiment_score_avg': 0.15,  # from news_symbol_sentiment
  'active_alerts_count': 3,  # COUNT from flow_alerts WHERE symbol='DAL' AND active=1
  'days_since_most_recent_alert': 2,  # calculated from flow_alerts
  'analysis_timestamp': '2025-10-01 18:47:23'
}
```

#### Options Tracking Example (DAL $50 Call)
```python
{
  'contract_hash': 'DAL|50.0|2025-11-15|CALL',
  'trade_date': '2025-10-01',
  'symbol': 'DAL',
  'strike': 50.0,
  'expiration_date': '2025-11-15',
  'option_type': 'CALL',
  'underlying_price': 49.85,  # from oi_daily
  'days_to_expiration': 45,  # from oi_daily
  'open_interest': 12_345,  # from oi_daily
  'volume': 1_234,  # from oi_daily
  'implied_volatility': 0.3156,  # from oi_daily
  'delta': 0.4823,  # from oi_daily
  'oi_change_5d': 2_345,  # from oi_daily
  'oi_momentum_5d': 0.2341,  # from oi_daily
  'days_to_earnings': 12,  # calculated from earnings_calendar
  'last_updated_timestamp': '2025-10-01 18:48:11'
}
```

---

## Implementation Phases

### Phase 1: Core Infrastructure (This PRD)
- ✅ Database schema already exists (`airline_tracking_schema.sql`)
- 🔨 Create `ap_symbol_tracking.py`
- 🔨 Create `ap_options_tracking.py`
- 🔨 Create `ap_backfill.py`
- 🔨 Add `AIRLINE_PLAY_SYMBOLS` to `symbols_klmn800.py`
- 🔨 Integrate `--airline-play` flag into `main.py` orchestration
- 🔨 Backfill historical data from 2025-08-08

### Phase 2: Daily Analysis Integration (Future)
- Define how `daily_analysis` module consumes airline tracking data
- Determine which airline-specific insights to generate
- Create bridge between airline tables and Oracle AI queries

### Phase 3: Pattern Detection & Backtesting (Future)
- Implement lock-step correlation analysis (DAL/UAL/AAL)
- Build backtesting framework for airline volatility plays
- Validate observed patterns with statistical rigor

### Phase 4: Expansion & Automation (Future)
- Extend to other correlated industries (hotels, cruise lines)
- Automated pattern-based alerts
- Integration with Chrome extension for airline-specific overlays

---

## Dependencies

### Existing Systems (Required)
- ✅ `oi_daily` table populated by OID collector/analyzer
- ✅ `oi_symbol_summary` table populated by OID symbol rollup
- ✅ `historical_prices` table populated by FMP historical backfill
- ✅ `options_symbol_summary` table populated by Flow Monitor symbol rollup
- ✅ `earnings_calendar` table populated by earnings collector
- ✅ `news_symbol_sentiment` table populated by news collector
- ✅ `flow_alerts` table populated by Flow Monitor analyzer

### External Dependencies
- None (all data sources already exist internally)

### Blocking Issues
- None identified

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| JETS ETF options data stops updating | Medium | Medium | Log warning, continue tracking other 6 symbols. JETS is supplemental (ETF vs individual stock). |
| OID pipeline failure means no oi_daily updates | High | Low | Airline tracking should fail gracefully with clear error. Don't block daily_analysis from running. |
| ±10% strike range captures too few contracts | Medium | Low | Range is adjustable. If needed, expand to ±15% or ±20% in future iteration. |
| 60 DTE limit misses longer-term setups | Low | Medium | Current collector already set at 60 DTE. Extending requires upstream OID changes (out of scope). |
| Historical backfill takes too long | Low | Low | 55 days of data, 7 symbols = ~385 symbol-days. Should complete in <5 minutes. |

---

## Open Questions

### Resolved
- ✅ Should we create a separate symbol universe? **No, add chunk to KLMN 800**
- ✅ What strike range? **±10% from current price**
- ✅ Backfill strategy? **Separate manual script, start from 2025-08-08**
- ✅ Handle missing data? **Populate what exists, log gaps, fail gracefully**

### Deferred (Future PRDs)
- How will daily_analysis consume airline tracking data?
- What correlation metrics should we calculate?
- Should we track pattern breaks (when lock-step fails)?
- Expansion to other industries?

---

## Success Validation

### Definition of Done (Phase 1)
✅ Both airline tracking tables exist and have indexes
✅ `ap_symbol_tracking.py` successfully extracts symbol data for all 7 airlines
✅ `ap_options_tracking.py` successfully filters options within ±10%/60 DTE
✅ `ap_backfill.py` loads historical data from 2025-08-08
✅ `--airline-play` flag integrated into `main.py` orchestration
✅ Pipeline runs evening after evening without manual intervention
✅ Errors logged clearly without stopping the overall process
✅ `AIRLINE_PLAY_SYMBOLS` exists in `symbols_klmn800.py`

### Acceptance Testing
1. **Fresh Run Test:** Drop both tables, run `ap_backfill.py`, verify 55 days of data loaded
2. **Daily Run Test:** Run `main.py --airline-play`, verify today's data populates correctly
3. **Drift Test:** Manually adjust DAL price, verify ±10% strike range recalculates properly
4. **Failure Test:** Temporarily break `oi_daily` access, verify graceful failure with clear logs
5. **Gap Test:** Verify JETS and UAL gaps logged but don't stop processing

---

## Appendix

### Data Coverage Summary (As of 2025-10-01)
```
Symbol | historical_prices | oi_daily       | options_symbol_summary
-------|-------------------|----------------|----------------------
DAL    | 2021-01-04+      | 2025-08-08+    | 2025-06-24+ (70 days)
UAL    | 2021-01-04+      | 2025-09-03+    | 2025-06-24+ (70 days)
AAL    | 2021-01-04+      | 2025-08-08+    | 2025-06-24+ (70 days)
LUV    | 2021-01-04+      | 2025-08-08+    | 2025-06-24+ (70 days)
JBLU   | 2021-01-04+      | 2025-08-13+    | 2025-09-19+ (7 days)
ALK    | 2021-01-04+      | 2025-08-18+    | 2025-06-24+ (70 days)
JETS   | N/A              | 2025-08-08-22  | N/A (just added)
```

### Decimal Precision Policy Reference
- **Prices** (strike, bid, ask, last_price, underlying_price, close_price): 2 decimals
- **Percentages** (price_change_percent, oi_change_pct, gap_from_max_pct): 2 decimals
- **Greeks & IV** (delta, gamma, theta, vega, implied_volatility): 4 decimals
- **Ratios & Multipliers** (oi_ratio, concentration_ratio, volume_ratio_5d): 4 decimals
- **Scores & Factors** (significance_score, quality_score, volume_surge_factor): 2 decimals

---

## Approval

**Author:** Ben & Claude
**Reviewers:** Ben (System Owner)
**Status:** Ready for Task Generation
**Next Step:** Use `/generate-tasks` to break down into implementation tasks
