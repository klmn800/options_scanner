# System Map — Options Scanner

Quick-reference orientation guide for myself. Updated as understanding deepens.

## What This System Does

Multi-strategy options scanner that:
1. **Collects** options data on 820 symbols (388 intraday via FM, all 820 daily via OP)
2. **Analyzes** flow for unusual activity (volume surprise, premium size)
3. **Alerts** when activity crosses thresholds (significance score 3.5+)
4. **Tracks** earnings signals (underpriced straddles based on historical vs implied moves)
5. **Evaluates** alert outcomes (max profit at 1/3/7/14/30 days)

## Who Uses It

**Ben** — sole user. $4K portfolio, <$300/position, buys options (never sells), swing trades (days to weeks), primarily <$60 stocks, 25% profit target, trades on Robinhood.

## Daily Lifecycle

1. 6:35 AM — Morning OP (all 820 symbols), Earnings Intel, Metadata, Sync, Views
2. 9:15 AM — FM starts (388 symbols, ~15 min cycles, ~38-40 cycles/day)
3. 5:00 PM — Evening OP, Airline Play, Sync
4. Evening — Backup, Autofix review
5. Fridays — Weekly backup, FM baseline, Earnings refresh, Sector archive

## Key Data Points (as of 2026-04-17)

| Metric | Value |
|--------|-------|
| Total flow alerts | 3,183 |
| With 7d profitability | 1,838 (58%) |
| Avg max 7d profit | 73% (median ~44%) |
| Win rate (>=25% in 7d) | 68% |
| FM cycles/day | 38-40 (full day) |
| OP symbols collected | 816-819/day |
| Earnings events tracked | 64,389 |
| Earnings moves calculated | 21,919 |
| BUY/STRONG BUY upcoming | 16 (within 45 days) |

## Key Databases

- **datalake.db** (production) → **datalake_query.db** (analysis, synced 2x/day)
- **performance.db** — operational metrics (16 tables)
- **sector_archive/*.db** — historical data by sector (18+ archive files)

## Scoring System Evolution

- **v1** (Sept 2025 – Mar 2026): threshold 6.0, premium + volume surprise
- **v2** (Apr 2026): threshold 3.5, removed smart money (was double-counted), HIGH 5.0+
- **v3** (design phase): two-tier scoring — fundamental + actionability bonus (V/OI, DTE, price, IV, multi-leg)

## Important Recent Changes

- SSD migration (Apr 10): 9x archive speedup, sync times 10-25s
- 6Q recency weighting (Apr 13): earnings signal now uses recent 6 quarters, not all-time
- Intraday signal tracking (Apr 17): FM recomputes straddle underpricing hourly
- Symbol lifecycle CLI (Apr 16): `symbol_lifecycle.py` for add/offboard/restore/review

---

*Last updated: Session 001, 2026-04-17*
