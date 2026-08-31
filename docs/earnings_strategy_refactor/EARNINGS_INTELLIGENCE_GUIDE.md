# Earnings Intelligence System — User Guide

**Last updated:** 2026-02-26
**Status:** Production (PRDs 0003, 0008, 0009, 0010 complete)

---

## What It Does

The Earnings Intelligence (EI) system tracks upcoming earnings across the KLMN 800 universe, identifies underpriced options plays, monitors price/IV moves post-earnings, and maintains a curated watchlist of actionable opportunities.

## Where It Runs in the Orchestrator

EI runs as **Step 1.2** in the morning pre-market phase (`python main.py`):

```
Phase 1 — Pre-Market (6:35 AM ET)
  1.1  Morning Option Pipeline
  1.2  Earnings Intelligence  <-- HERE (daily pipeline, 6 sub-steps)
  1.3  Metadata Refresh
  1.4  Pre-Market Sync
  1.5  Morning Views

Phase 2 — Flow Monitor (9:15 AM - 5:00 PM)
Phase 3 — Evening (5:00 PM+)
  3.1  Evening Option Pipeline
  3.3  Final Sync

Phase 5 — Friday Only
  Weekly Refresh (fetch upcoming, archive past, cleanup)
```

### Two Operational Modes

| Mode | When | What It Does |
|------|------|-------------|
| **Daily Pipeline** | Every trading day, Step 1.2 | 6 sub-steps (see below) |
| **Weekly Refresh** | Fridays, Phase 5 | Fetch earnings from Finnhub/YFinance, archive past events, cleanup |

## Daily Pipeline (6 Sub-Steps)

Run via `python main.py` (automatic) or `python main.py --earnings-intel` (manual):

```
[1/6] Snapshot Collection    — Captures IV/price at T-7 through T+3 for active events
[2/6] Post-Earnings Calc     — Computes price moves, IV crush, move-vs-expected at T+3
[3/6] Expected Moves Update  — Calculates expected moves + play signals for upcoming earnings
[4/6] Earnings Watchlist      — Populates/updates the investor-facing watchlist table
[5/6] News Enrichment        — Fetches news sentiment for watchlist symbols (Alpha Vantage)
[6/6] Arbitrage Scanner      — Identifies IV arbitrage opportunities across sectors
```

## The Earnings Watchlist

The `earnings_watchlist` table is the primary output — a curated list of upcoming earnings plays.

### Entry Criteria

A symbol appears on the watchlist when ALL of these are true:
- Signal is WATCH, BUY, or STRONG BUY
- Earnings date is within 14 calendar days
- Total open interest >= 4,000 contracts

### Signal Thresholds

Based on `relative_underpricing_pct` — how much the market is underpricing the stock's typical earnings move:

| Signal | Threshold | Meaning |
|--------|-----------|---------|
| AVOID | < 0% | Market expects MORE than historical avg |
| NEUTRAL | 0-15% | Roughly fair |
| WATCH | 15-30% | Modestly underpriced |
| BUY | 30-50% | Significantly underpriced |
| STRONG BUY | > 50% | Market is deeply underpricing this move |

Formula: `relative_underpricing_pct = (historical_avg_move - expected_move) / expected_move * 100`

### Watchlist Lifecycle

```
UPCOMING  →  TODAY  →  T+1  →  T+2  →  T+3  →  (deleted at T+4)
                                         ↑
                              Enriched with actual_move_pct,
                              iv_crush_severity from earnings_moves
```

### Console Output

When the pipeline runs, the orchestrator displays a table:

```
 Sym    Status   Price   Days  Time  Signal      IV%    Undr%  ExpMv  Sentiment
 PDD    UPCOMING 102.50   20   amc   STRONG BUY  0.62   93.7%  10.1%  --
 OKTA   UPCOMING  85.30    6   amc   BUY         0.48   39.4%  10.9%  --
 MRVL   UPCOMING  92.10    7   amc   WATCH       0.35   16.2%  11.8%  --
```

## Data Sources

| Source | Data | Frequency | API Cost |
|--------|------|-----------|----------|
| **Finnhub** | Earnings dates, BMO/AMC timing, EPS/revenue estimates | Weekly (Fridays) | 3 API calls / 60 per min free |
| **YFinance** | Earnings dates (fallback for Finnhub gaps) | Weekly (Fridays) | ~460 calls, 0.1s throttle |
| **Tradier** | Options chains, IV, Greeks | Daily (via Option Pipeline) | Existing allocation |
| **Alpha Vantage** | News sentiment for watchlist symbols | Daily, up to 25/day | 25 calls/day free tier |

### Finnhub Coverage (as of 2026-02-26)

- 189/728 symbols have BMO/AMC timing (26%)
- 284 symbols have EPS estimates
- 283 symbols have revenue estimates
- Remaining symbols show "Unknown" timing (YFinance doesn't provide it)

## Key Tables

| Table | Purpose | Size |
|-------|---------|------|
| `earnings_upcoming` | Active earnings calendar (PK=symbol) | ~728 rows |
| `earnings_watchlist` | Curated plays with signals (PK=symbol) | 10-20 rows typically |
| `earnings_events` | Historical archive of past earnings | ~177 rows (rest in sector archives) |
| `earnings_moves` | Post-earnings price/IV metrics | ~9,324 rows |
| `earnings_snapshots` | Daily IV/price time series around earnings | Accumulating (started 2026-02-25) |
| `earnings_sector_effects` | Peer sympathy and IV arbitrage | Currently empty |

## CLI Commands

```bash
# Full daily pipeline (what the orchestrator runs)
python main.py --earnings-intel

# Standalone components
python strategies/earnings_intel/ei_main.py --all               # Auto-detect mode
python strategies/earnings_intel/ei_main.py --daily-pipeline     # Daily 6-step pipeline
python strategies/earnings_intel/ei_main.py --weekly-refresh     # Friday: fetch/archive/cleanup

# One-off tools
python strategies/earnings_intel/ei_fetch_upcoming.py --no-interaction   # Just fetch earnings dates
python strategies/earnings_intel/ei_backfill_price_moves.py --dry-run    # Preview backfill
python strategies/earnings_intel/ei_backfill_metrics.py --dry-run        # Preview IV backfill
```

## Querying the Data

```sql
-- What's on the watchlist right now?
SELECT symbol, earnings_date, earnings_time, earnings_play_signal,
       relative_underpricing_pct, expected_move_pct
FROM earnings_watchlist
ORDER BY relative_underpricing_pct DESC;

-- Upcoming earnings with signals
SELECT symbol, earnings_date, earnings_time, earnings_play_signal,
       relative_underpricing_pct, eps_estimate
FROM earnings_upcoming
WHERE earnings_play_signal IN ('WATCH', 'BUY', 'STRONG BUY')
ORDER BY earnings_date;

-- How accurate were STRONG BUY signals historically?
SELECT em.symbol, em.earnings_date,
       ROUND(em.move_1day_pct, 2) as actual_1d,
       ROUND(em.expected_move_pct, 2) as expected,
       ROUND(em.move_vs_expected_pct, 1) as vs_expected_pct,
       em.iv_crush_severity
FROM earnings_moves em
JOIN earnings_events ee ON em.event_id = ee.event_id
WHERE ee.earnings_play_signal = 'STRONG BUY'
ORDER BY em.earnings_date DESC;

-- BMO vs AMC: do stocks move more after-hours or pre-market?
SELECT earnings_time,
       COUNT(*) as cnt,
       ROUND(AVG(ABS(move_1day_pct)), 2) as avg_abs_move
FROM earnings_moves em
JOIN earnings_upcoming eu ON em.symbol = eu.symbol
WHERE eu.earnings_time IN ('bmo', 'amc')
GROUP BY earnings_time;
```

Use `python tools/direct_db_query.py --sql "..."` to run these against the query database.

## Flow Watchlist Integration

The Flow Monitor's daily watchlist (`flow_watchlist_daily`) is enriched with two EI columns:
- `earnings_play_signal` — The signal at time of watchlist entry
- `relative_underpricing_pct` — How underpriced the stock's earnings move is

These are set once at creation time and not updated on re-scan.

## Related Documentation

- **Manual Operations:** `strategies/earnings_intel/docs/MANUAL_OPERATIONS.md` — Trading journal, SQL queries
- **Straddle Playbook:** `strategies/earnings_intel/docs/EARNINGS_STRADDLE_PLAYBOOK.md` — Trading strategy
- **Signal Calibration:** CLAUDE.md "Earnings Signal Recalibration" section — Threshold rationale
- **Performance DB:** `docs/performance_tracking_enhancement/performance_db_schema.md` — `ei_pipeline_performance` table
- **Refactor Plan:** `docs/_local/earnings_strategy_refactor/REFACTOR_PLAN.md` — Design decisions and research
