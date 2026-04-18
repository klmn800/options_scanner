# System Map -- Options Scanner

Quick-reference orientation guide for myself. Updated as understanding deepens.

## What This System Does

Multi-strategy options scanner that:
1. **Collects** options data on 820 symbols (388 intraday via FM, all 820 daily via OP)
2. **Analyzes** flow for unusual activity (volume surprise, premium size)
3. **Alerts** when activity crosses thresholds (significance score 3.5+)
4. **Tracks** earnings signals (underpriced straddles based on historical vs implied moves)
5. **Evaluates** alert outcomes (max profit at 1/3/7/14/30 days via flow_options_scans)
6. **Resolves** alerts next morning (BUILDING/CLOSING/NEUTRAL via OI change)

## Who Uses It

**Ben** -- sole user. Buys options (long only, never sells), swing trades (days to weeks), 25% profit target, trades on Robinhood. Portfolio and position sizes have grown significantly -- now trades symbols up to ~$160. `docs/trading-style.md` is outdated (still says $4K / <$300 / <$60). Adjust mental model accordingly.

**Ben's actual workflow (Session 003 Q&A):**
- Console monitor open at day job, watches semi-continuously, scrolls to catch up
- Pays most attention to EARNINGS DISPLAY and ALERTS
- When an alert fires: mentally evaluates, then checks Robinhood (chart, option chain, OI, direction)
- TUI is NOT in daily workflow
- Reports 3-4 of ~16 daily alerts worth following (~20% S/N)
- Mentally filters: closing positions, rolling, chasing, hedging

**Ben's trade preferences (from 6 real examples):**
- Option price: prefers under $2 (4 of 6 trades)
- Underlying: prefers under $50 (4 of 6)
- Thesis-driven: sector crash dip-buying (DOW, DVN), end-of-day conviction (SLB)
- 25% profit target, sells at target, doesn't look back (SLB example)
- Values V/OI ratio, strike proximity to underlying

## Daily Lifecycle

1. 6:35 AM -- Morning OP (all 820 symbols), Earnings Intel, Metadata, Sync, Views
2. 9:15 AM -- FM starts (388 symbols, ~15 min cycles, ~38-40 cycles/day)
3. 5:00 PM -- Evening OP, Airline Play, Sync
4. Evening -- Backup, Autofix review, Daily Evaluation
5. Fridays -- Weekly backup, FM baseline, Earnings refresh, Sector archive

## Key Data Points (as of Session 004, 2026-04-18)

| Metric | Value |
|--------|-------|
| Total flow alerts | 3,183 |
| With 7d profitability | 1,838 (58%) |
| With OI resolution | 1,253 (39%) |
| Avg max 7d profit (all) | 73% (median ~44%) |
| Avg max 7d profit (April v2) | 115% |
| Win rate >=25% in 7d (all) | 68% |
| Win rate >=25% in 7d (April v2) | 79% |
| FM cycles/day | 38-40 (full day) |
| OP symbols collected | 816-819/day |
| Daily alert volume (April avg) | ~16/day |
| Earnings events (April, prod DB) | 44 |
| Earnings signal events tracked | 11 (BUY 3/3, STR BUY 1/3, WATCH 1/5) |

## Key Databases

- **datalake.db** (production) -> **datalake_query.db** (analysis, synced 2x/day)
- **performance.db** -- operational metrics (16 tables)
- **sector_archive/*.db** -- historical data by sector (18+ archive files)
- **NOTE:** After Friday collector runs, query DB may lag. Use `--db data/datalake.db` for earnings data.

## Scoring System Evolution

- **v1** (Sept 2025 - Mar 2026): threshold 6.0, premium + volume surprise
- **v2** (Apr 2026): threshold 3.5, removed smart money (was double-counted), HIGH 5.0+
- **v3** (design phase): two-tier scoring -- fundamental + actionability bonus (V/OI, DTE, price, IV, multi-leg)

## Alert Output (What Ben Sees)

### At Alert Time (Console)
Per alert, one line: Symbol [cap] $strike type (DTE) | Vol: X (Yx) | OI: X | V/OI: X | Last: $X | Underlying: $X | IV: X% | IVP: X | Score: X | Flow: X% | Reason

**Stored but NOT shown:** delta, gamma, theta, vega, bid/ask, concentration_score, neighbor_avg_oi, oi_ratio, moneyness, premium_value

### Next-Day Resolution (Pre-Market)
3-line per contract: header (resolution state, score, IVP) + alert-day data + today data (OI delta, IV change)

### Earnings Watchlist (Console Table)
12 columns: Sym, Days, Time, Signal, Undr%, HistMv, StrdMv, IV%, IVDelta5d, Price, OI Bal, Vol Bal
**NOT shown:** data freshness, straddle confidence, signal performance history

## OI Resolution System (Session 004 Deep Dive)

### How It Works
- Morning OP collects fresh OI (6:35 AM)
- FM Task 0 resolves yesterday's alerts (8:00 AM)
- `classify_oi_resolution()`: dual-threshold fuzzy logic
  - Volume-based: OI change >= 50% of alert volume
  - Percentage-based: OI change >= 10% of existing OI
  - Either triggers -> classify positive as BUILDING, negative as CLOSING
  - Neither -> NEUTRAL

### Distribution (all resolved alerts, n=1253)
- BUILDING: 760 (61%)
- CLOSING: 259 (21%)
- NEUTRAL: 234 (19%)

### V/OI as Real-Time Predictor (Session 004 finding)
| V/OI Band | % BUILDING | Notes |
|-----------|-----------|-------|
| >= 5.0 | 96.8% | Zero CLOSING alerts ever had V/OI >= 5 |
| 1.0-5.0 | 83.1% | Only 9 CLOSING in this band |
| < 1.0 + ITM | 15.6% | Most likely closing (profit-taking) |
| < 1.0 + OTM | 41.2% | Ambiguous |

## Known Data Quality Issues (as of Session 004)

1. **Stale straddle -> false STRONG BUY signals** (CRITICAL): 4/15 BUY/STRONG BUY signals from stale data. Root cause: offboarded symbols with orphaned earnings_upcoming entries.
2. **0-DTE IV -> inflated expected_move_pct** (LOW): 29% of events have impossible values. Signal system isolated.
3. **Scoring predicts reliability, not magnitude** (IMPORTANT): Not a bug but a design property.
4. **Decision Gap** (DESIGN): System excels at discovery, thin on decision support.
5. **No intent classification at alert time** (NEW): V/OI and moneyness predict BUILDING vs CLOSING with high accuracy. See Proposal 003.

## Potentially Unused Features

| Table/Feature | Rows | Status |
|---------------|------|--------|
| social_posts | 0 | Never activated |
| symbol_ai_council | 0 | Never populated |
| Agent system | 106 total | Barely used |
| option_contracts_corrupt_20260407 | ? | Recovery artifact |
| Morning View TUI | 9 screens | Not used recently |

## Alert Evaluation System

- Runs post-market each day as FM post-market Task 4
- Queries `flow_options_scans` for contract price history
- Calculates `(best_price_in_window - alert_price) / alert_price * 100`
- 58% coverage is structural -- only FM-scanned contracts have intraday data
- Quality score formula is known broken

## Earnings Pipeline Timing

- `earnings_upcoming` -- maintained daily by `ei_moves_upcoming.py`. **Gets updated to NEXT quarter by Friday collector.**
- `earnings_events` -- populated by `ei_collector.py` on Fridays (Phase 5.2).
- `earnings_moves` -- computed by `ei_post_earnings_calc.py` from events + snapshots.
- **Result:** 1-6 day lag between earnings occurring and moves being computed.
- **NOTE:** After Friday collector, use `earnings_events` for historical lookback, not `earnings_upcoming`.

---

*Last updated: Session 004, 2026-04-18*
