# System Map — Options Scanner

Quick-reference orientation guide for myself. Updated as understanding deepens.

## What This System Does

Multi-strategy options scanner that:
1. **Collects** options data on 820 symbols (388 intraday via FM, all 820 daily via OP)
2. **Analyzes** flow for unusual activity (volume surprise, premium size)
3. **Alerts** when activity crosses thresholds (significance score 3.5+)
4. **Tracks** earnings signals (underpriced straddles based on historical vs implied moves)
5. **Evaluates** alert outcomes (max profit at 1/3/7/14/30 days via flow_options_scans)

## Who Uses It

**Ben** — sole user. Buys options (long only, never sells), swing trades (days to weeks), 25% profit target, trades on Robinhood. Portfolio and position sizes have grown significantly — now trades symbols up to ~$160. `docs/trading-style.md` is outdated (still says $4K / <$300 / <$60). Adjust mental model accordingly.

## Daily Lifecycle

1. 6:35 AM — Morning OP (all 820 symbols), Earnings Intel, Metadata, Sync, Views
2. 9:15 AM — FM starts (388 symbols, ~15 min cycles, ~38-40 cycles/day)
3. 5:00 PM — Evening OP, Airline Play, Sync
4. Evening — Backup, Autofix review, Daily Evaluation
5. Fridays — Weekly backup, FM baseline, Earnings refresh, Sector archive

## Key Data Points (as of 2026-04-18)

| Metric | Value |
|--------|-------|
| Total flow alerts | 3,183 |
| With 7d profitability | 1,838 (58%) |
| Avg max 7d profit (all) | 73% (median ~44%) |
| Avg max 7d profit (April) | 115% |
| Win rate >=25% in 7d (all) | 68% |
| Win rate >=25% in 7d (April) | 79% |
| FM cycles/day | 38-40 (full day) |
| OP symbols collected | 816-819/day |
| Daily alert volume (April avg) | ~16/day |
| HIGH alerts/day (April avg) | ~3/day |
| Earnings events tracked | 64,389 |
| Earnings moves calculated | 21,836 |
| BUY/STRONG BUY upcoming | 15 (4 stale data, 1 suspect) |
| Earnings events with outcomes | 11 (BUY 3/3, STR BUY 1/3, WATCH 1/5) |

## Key Databases

- **datalake.db** (production) → **datalake_query.db** (analysis, synced 2x/day)
- **performance.db** — operational metrics (16 tables)
- **sector_archive/*.db** — historical data by sector (18+ archive files)

## Scoring System Evolution

- **v1** (Sept 2025 – Mar 2026): threshold 6.0, premium + volume surprise
- **v2** (Apr 2026): threshold 3.5, removed smart money (was double-counted), HIGH 5.0+
- **v3** (design phase): two-tier scoring — fundamental + actionability bonus (V/OI, DTE, price, IV, multi-leg)

## Alert Output (What Ben Sees)

### At Alert Time (Console)
Per alert, one line: Symbol [cap] $strike type (DTE) | Vol: X (Yx) | OI: X | V/OI: X | Last: $X | Underlying: $X | IV: X% | IVP: X | Score: X | Flow: X% | Reason

**Stored but NOT shown:** delta, gamma, theta, vega, bid/ask, concentration_score, neighbor_avg_oi, oi_ratio, moneyness, premium_value

### Next-Day Resolution (Pre-Market)
3-line per contract: header (resolution state, score, IVP) + alert-day data + today data (OI delta, IV change)

### Earnings Watchlist (Console Table)
12 columns: Sym, Days, Time, Signal, Undr%, HistMv, StrdMv, IV%, IVΔ5d, Price, OI Bal, Vol Bal
**NOT shown:** data freshness, straddle confidence, signal performance history

### End-of-Day Report (Console)
4 sections: Market Summary (SPX/VIX/sectors), Flow Activity (top symbols, alert counts), Earnings Outlook (upcoming signals), System Performance (FM stats, sync, news API)

## Morning View TUI (9 Screens)

1. **My Watchlist** — user curated, stale detection, trigger badges
2. **Symbol Discovery** — confluence scoring (0-5), direction bias, auto-filters watchlist symbols
3. **Earnings Calendar** — 90-day grid, signal color-coded
4. **Earnings Browser** — list view with filters (price ≤$60, min OI)
5. **Symbol Detail Hub** — overview + 5 sub-screens
6. **OI Distribution** — strike concentration, P/C ratio, Greeks exposure, max pain
7. **OI Timing** — Smart money positioning, build history (PREDICTIVE vs CHASING is flawed per brainstorm)
8. **Capital Planner** — position tracking, scenario calculator integration
9. **Flow Alerts** — recent alerts, filterable

**Status:** "Hasn't been used recently" (big-to-do-list). Modernization (6.6) is prerequisite for pipeline features.

## Alert Evaluation System

- Runs post-market each day as FM post-market Task 4
- Queries `flow_options_scans` for contract price history
- Calculates `(best_price_in_window - alert_price) / alert_price * 100`
- Alert price: tries `premium_value / (volume * 100)`, fallback to midpoint/last/bid
- Best price: MAX of midpoint across all scans in timeframe window
- 58% coverage is structural — only FM-scanned contracts have intraday data
- All alerts stay `evaluation_status = 'active'` until expired or 30-day window exceeded
- Quality score formula is known broken (comment in code: "BROKEN - NEEDS COMPLETE REDESIGN")

## Earnings Pipeline Timing

- `earnings_upcoming` — maintained daily by `ei_moves_upcoming.py` (Phase 1.2). Updates signals, straddle moves, underpricing each morning.
- `earnings_events` — populated by `ei_collector.py` on Fridays (Phase 5.2). Events from this week won't appear until Friday.
- `earnings_moves` — computed by `ei_post_earnings_calc.py` from `earnings_events` + `earnings_snapshots`. Depends on events existing.
- **Result:** 1-6 day lag between earnings occurring and earnings_moves being computed.

## Known Data Quality Issues (as of Session 003)

1. **Stale straddle → false STRONG BUY signals** (CRITICAL): 4/15 BUY/STRONG BUY signals from stale data (5-16 days). See `observations/004_straddle_false_signals.md`.
2. **0-DTE IV → inflated expected_move_pct** (LOW): 29% of events have impossible values. Signal system isolated. See `observations/002_expected_move_data_quality.md`.
3. **Scoring predicts reliability, not magnitude** (IMPORTANT): Not a bug but a design property. See `observations/001_scoring_vs_performance.md`.
4. **Decision Gap** (DESIGN): System excels at discovery, thin on decision support. Greeks hidden, data freshness invisible, no signal performance feedback. See `observations/006_decision_gap_analysis.md`.

## Potentially Unused Features

| Table/Feature | Rows | Code Files | Status |
|---------------|------|-----------|--------|
| social_posts | 0 | social_poster.py, fm_social_notifier.py | Never activated |
| symbol_ai_council | 0 | morning_view/ai_council.py | Never populated |
| Agent system | 106 total | fm_agent.py, agent_tools.py | Barely used |
| option_contracts_corrupt_20260407 | ? | Recovery artifact | Should delete |
| Morning View TUI | 9 screens | morning_view/ | Not used recently |

---

*Last updated: Session 003, 2026-04-18*
