# Earnings Date Accuracy Investigation

**Date:** 2026-03-05
**Status:** Investigation complete, implementation pending

## Problem

Finnhub earnings dates in `earnings_upcoming` are frequently wrong. Spotted by comparing against Robinhood.

## Validation (34 near-term symbols, next 30 days)

### Three-way comparison: Robinhood vs Finnhub vs yfinance

| Source | Accuracy vs RH | Notes |
|--------|---------------|-------|
| **Finnhub** | 17/34 (50%) | Wrong on verified dates too (13/23 = 57%) |
| **yfinance** | 27/34 (79%) | **100% on RH-verified dates** (23/23) |

### Key finding: yfinance misses correlate with RH `verified=false`

- RH verified=YES (23 symbols): yfinance 23/23 = **100%**
- RH verified=no (11 symbols): yfinance 4/11 = 36%

When the company has confirmed the date, yfinance always has it right. Disagreements only happen on unconfirmed dates where everyone is guessing.

### Finnhub known issues

- [GitHub #528](https://github.com/finnhubio/Finnhub-API/issues/528): Dates wrong, no corrections applied
- [GitHub #437](https://github.com/finnhubio/Finnhub-API/issues/437): Year field mismatches
- Evidence in our own data: WOLF date changed from correct (2/4) to wrong (2/6) via backfill

## What each source provides

| Field | Finnhub | yfinance | Action |
|-------|---------|----------|--------|
| Date | Unreliable | Reliable (confirmed) | **Use yfinance** |
| Timing (bmo/amc) | Yes (`hour` field) | **Not available** | **Keep Finnhub for this only** |
| EPS estimate | `epsEstimate` | `Earnings Average` + High/Low | Use yfinance (richer) |
| Revenue estimate | `revenueEstimate` | `Revenue Average` + High/Low | Use yfinance (richer) |
| Quarter/Year | No | No | Not needed |

## yfinance limitations

- For symbols 60+ days out, `Ticker.calendar` returns the most recent PAST earnings date, not the next one
- Our system only needs accurate dates within ~30 days, so this is acceptable
- Finnhub can remain the fallback for far-out dates where yfinance is stale

## Implementation plan

**File:** `strategies/earnings_intel/ei_collector.py` (Friday Phase 5, Step 5.2)

### Changes needed:

1. **Primary date source: yfinance**
   - For each symbol, call `yf.Ticker(sym).calendar`
   - Extract `Earnings Date[0]`, `Earnings Average`, `Revenue Average`
   - Also extract High/Low ranges if we want them later

2. **Timing source: Finnhub (unchanged)**
   - Still call `self.api.get_earnings_calendar()` per symbol
   - Only use the `hour` field (bmo/amc/dmh)

3. **Date resolution logic:**
   - If yfinance has a future date → use it (high confidence)
   - If yfinance date is in the past (stale) → fall back to Finnhub date
   - Store a `date_source` field so we can track which source was used

4. **Performance consideration:**
   - yfinance `Ticker.calendar` makes HTTP requests to Yahoo Finance
   - 742 symbols at ~0.5s each = ~6 minutes
   - Current Finnhub loop already takes ~12 minutes (rate limited at 60/min)
   - Could run yfinance and Finnhub in parallel or interleaved

5. **New optional column:** `date_verified` or `date_confidence`
   - Not from RH's verified field (can't access programmatically)
   - But could flag: "both sources agree" vs "yfinance only" vs "finnhub fallback"

## Validation scripts

- `research/earnings_3way_compare.py` — Python comparison script
- `research/rh_earnings_validation.js` — Browser console script for RH API
