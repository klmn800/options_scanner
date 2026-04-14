# Earnings Intelligence Strategy

Tracks earnings events across the KLMN 800 universe, captures IV/price evolution around earnings dates, calculates actual post-earnings moves, manages an investor-facing earnings watchlist, and scans for sector sympathy arbitrage opportunities where peer stocks have cheap IV relative to the reporting company.

**Entry point:** `ei_main.py` (daily pipeline), `ei_collector.py` (weekly refresh)

---

## Two Operational Modes

Earnings Intelligence runs two distinct modes at different times in the orchestrator schedule.

### 1. Weekly Refresh (Fridays, Phase 5 Step 5.2) -- ~13 minutes

Called directly by `main_runners.py` via `EarningsCollector` (bypasses `ei_main.py`).

| Step | What happens | Key detail |
|------|-------------|------------|
| Archive Past Events | SQL: `INSERT OR IGNORE INTO earnings_events` from `earnings_upcoming` where `earnings_date < today` | Promotes completed earnings to permanent archive (preserves 7 signal columns: play signal, underpricing, expected/historical moves, estimates) |
| Cleanup | `DELETE FROM earnings_upcoming WHERE earnings_date < today - 7 days` | Keeps working table lean |
| Fetch Upcoming | `ei_collector.py` calls Finnhub per-symbol for ~726 stocks (ETFs excluded) | 60 req/min rate limit, ~13 min. Batch upsert, calendar fields only (preserves analysis columns via ON CONFLICT) |

**Error handling:** All three steps are ERROR severity (batch mode, non-blocking). Autofix queued if >10% of symbols fail to fetch.

### 2. Daily Pipeline (6:35 AM Pre-Market, Phase 1 Step 1.2) -- ~10-15 minutes

Called by `main_runners.py::run_earnings_intelligence()` which invokes `ei_main.py::run_daily_pipeline()`.

| Sub-step | Module | What happens |
|----------|--------|-------------|
| 1/6 Snapshot Collection | `ei_snapshot_collector.py` | Captures end-of-day OHLC, IV, OI, and volume for earnings in the T-7 to T+5 window (calendar days, covers weekends). Records primary symbol + top 4 industry peers. "Yesterday alignment": each morning captures the previous complete trading day's data from `historical_prices` (OHLC + stock volume) and `option_symbol_summary` (IV, OI, option volume). |
| 2/6 Post-Earnings Calc | `ei_post_earnings_calc.py` | For events at T+3: calculates 1d/2d/3d/5d price moves with BMO/AMC-aware baseline, OHLC-based pre/post earnings peak detection and swing analysis, IV buildup/collapse/crush severity, expected move from straddle snapshots, sector sympathy effects for peers. Writes outcome summary back to `earnings_events`. |
| 3/6 Expected Moves Update | `ei_moves_upcoming.py` | Recalculates expected moves for all upcoming earnings using latest IV. Updates signals and alerts on `earnings_upcoming`. |
| 4/6 Watchlist Population | `ei_watchlist.py` | Filters to actionable earnings plays (WATCH/BUY/STRONG BUY + <=14 calendar days + OI>=4000). Manages `earnings_watchlist` lifecycle (UPCOMING->TODAY->T+1->T+2->T+3->deleted at T+4). Returns created_symbols list for news enrichment. |
| 5/6 News Enrichment | `tools/news_sentiment.py` | Alpha Vantage sentiment for new watchlist entries and T-1 symbols. Budget-aware (25 calls/day). Updates `earnings_watchlist.news_sentiment_*` columns. |
| 6/6 Arbitrage Scan | `ei_arbitrage_scanner.py` | **Currently disabled** -- accumulating historical correlation data. When enabled: finds peers with cheap IV relative to today's earnings reporters, writes to `earnings_sector_effects`. |

All six sub-steps are ERROR severity on failure (batch mode, non-blocking). Pipeline success = True if the pipeline itself didn't crash, even if individual sub-steps failed.

---

## Component Map

| File | Purpose |
|------|---------|
| `ei_main.py` | Orchestrator -- `run_daily_pipeline()` (6 sub-steps), `run_morning_scan()` (standalone arbitrage, currently unused), `run_all_mode()` (auto-detect) |
| `ei_collector.py` | Standalone weekly earnings collector -- Finnhub per-symbol fetch for ~726 stocks. Called directly by `main_runners.py`, not through `ei_main.py`. |
| `ei_watchlist.py` | Earnings watchlist manager -- `populate_watchlist()` with ON CONFLICT upsert, lifecycle management, T+3 enrichment from `earnings_moves` |
| `ei_snapshot_collector.py` | Collects end-of-day OHLC/IV/volume snapshots for earnings in T-7 to T+5 window. "Yesterday alignment" — captures previous complete trading day's data. `--backfill` flag to repair old NULL-price rows. |
| `ei_post_earnings_calc.py` | Calculates actual moves (BMO/AMC-aware baseline, OHLC peaks, swing analysis), IV changes, expected vs actual move at T+3. Sector effects for peers. Writes outcome summary to `earnings_events`. CLI: `--recalculate`, `--backfill-outcomes`. |
| `ei_moves_upcoming.py` | Updates expected moves, relative underpricing, signals, and alert flags on `earnings_upcoming` |
| `ei_arbitrage_scanner.py` | Sector sympathy IV arbitrage scanner (implementation complete, disabled in production pending data accumulation) |
| `ei_backfill_metrics.py` | One-time backfill: populates iv_collapse_pct, expected_move_pct, move_vs_expected_pct for historical rows |
| `ei_health_reporter.py` | Health reporting for all modes (writes to `logs/`) |

---

## How It Gets Called

`main_runners.py` imports and calls the mode functions directly (in-process, not subprocess):

```python
from strategies.earnings_intel.ei_main import run_daily_pipeline
from strategies.earnings_intel.ei_collector import EarningsCollector
```

### Schedule

| Mode | Method in main_runners.py | When | Trigger |
|------|--------------------------|------|---------|
| Daily Pipeline | `run_earnings_intelligence()` | 6:35 AM ET daily (Step 1.2) | Pre-market, after morning OP |
| Weekly Refresh | `run_earnings_weekly_refresh()` | Fridays (Step 5.2) | Before sector archive |

### Error Handling

| Mode | Failure severity | What happens |
|------|-----------------|-------------|
| Weekly Refresh (fetch) | ERROR | Queued for batch review, pipeline continues |
| Weekly Refresh (archive) | CRITICAL | Autofix spawns, indicates schema issue |
| Daily Pipeline (any sub-step) | ERROR | Queued for batch review, pipeline continues |

---

## Database Tables

### Tables Written

| Table | Written by | Primary key | What |
|-------|-----------|-------------|------|
| `earnings_upcoming` | Weekly refresh (upsert), daily moves update (signals) | `symbol` | Working table: next 90 days with expected moves, relative underpricing, signals, alerts |
| `earnings_events` | Weekly refresh (archive), post-earnings calc (outcome write-back) | `(symbol, earnings_date)` | Permanent archive of all past earnings events with 7 preserved signal columns, trading journal fields, and denormalized outcome columns (`actual_move_1day_pct`, `actual_max_move_pct`, `move_vs_expected_pct`, `iv_collapse_pct`, `outcome_updated_at`) |
| `earnings_watchlist` | Daily pipeline sub-step 4 | `symbol` | Investor-facing watchlist: 24 columns, UPCOMING->TODAY->T+1->T+2->T+3->deleted lifecycle. Enriched with news sentiment and T+3 actual moves. |
| `earnings_snapshots` | Daily snapshot collector | `(symbol, earnings_date, snapshot_date)` | End-of-day OHLC, IV, OI, volume time series for T-7 to T+5 window (primary + peers). Columns: `open_price`, `high_price`, `low_price`, `close_price`, `volume` (stock), `option_volume`, `iv_30dte`, `iv_front_month`, `iv_45dte`, `total_open_interest`, `put_call_ratio`, `straddle_expected_move_pct` (captures daily straddle value from `earnings_upcoming` for time series). Uses `INSERT OR REPLACE` so corrected data overwrites stale rows. |
| `earnings_moves` | Daily post-earnings calc | `(event_id, symbol)` | Calculated price moves (1d/2d/3d/5d) with BMO/AMC-aware baseline (`pre_earnings_close`), OHLC-based pre/post earnings peaks and swing analysis, IV changes, crush severity, expected move from straddle snapshots (`expected_move_entry_pct` at T-7, `expected_move_final_pct` at T-1), move vs expected. ~9,900 rows. |
| `earnings_sector_effects` | Arbitrage scanner (disabled), daily post-earnings calc | `(primary_event_id, peer_symbol)` | Pre-earnings: arbitrage opportunities with IV discount and quality scores. Post-earnings: sector sympathy with actual moves and correlation strength. |
| `industry_peer_mappings` | One-time setup (now in Deprecated/) | `(symbol, industry)` | 742 symbols mapped to 124 industries, with `is_industry_leader` flags |

### Tables Read

| Table | Used by | Purpose |
|-------|---------|---------|
| `option_symbol_summary` | Snapshot collector, moves update, post-earnings calc | IV metrics (front month, 30/45/60 DTE), total open interest, option volume, close price |
| `option_contracts` | Moves update (straddle calc) | ATM call/put prices for straddle expected move |
| `historical_prices` | Snapshot collector, post-earnings calc, moves update | OHLC + stock volume for snapshots; close prices for actual move calculation |
| `industry_peer_mappings` | Arbitrage scanner, snapshot collector | Peer relationships for sympathy analysis |
| `news_symbol_sentiment` | Watchlist (backfill missing sentiment) | Per-symbol news sentiment data |

### Key Behaviors

- **`earnings_upcoming`** uses `symbol` as primary key -- one row per symbol, not per event. Refreshed weekly, updated daily.
- **`earnings_events`** is append-only via `INSERT OR IGNORE`. Includes trading journal columns (`notes`, `tags`, `note_type`, `sentiment`) for manual annotation and denormalized outcome columns (`actual_move_1day_pct`, `actual_max_move_pct`, `move_vs_expected_pct`, `iv_collapse_pct`) written back by `ei_post_earnings_calc.py` at T+3. See `docs/MANUAL_OPERATIONS.md` for SQL examples.
- **`earnings_watchlist`** is refreshed daily during pipeline sub-step 4. Entry criteria: WATCH/BUY/STRONG BUY signal + <=14 calendar days to earnings + total OI >= 4000. At T+3, rows are enriched with actual price moves from `earnings_moves`. Rows deleted at T+4.
- **`earnings_snapshots`** populates during active earnings windows when the daily pipeline runs. Zero rows is normal during quiet earnings weeks with no events in the T-7 to T+5 window. Uses "yesterday alignment": each morning captures the previous complete trading day's data so all fields (OHLC, IV, OI, volume) are from the same end-of-day snapshot. Window query UNIONs `earnings_upcoming` (pre-earnings) with `earnings_events` (post-earnings archive) to ensure post-earnings snapshots continue even after `ei_collector` updates the upcoming date to next quarter.
- **`earnings_sector_effects`** receives pre-earnings rows from the arbitrage scanner (with `primary_move_pct = NULL`) and post-earnings rows from the daily pipeline (with actual move data). Pre-earnings rows are idempotent -- re-running the scanner on the same day replaces them.
- **`earnings_moves`** has ~9,900 rows (backfilled from historical data). New rows added at T+3 for each earnings event. Uses BMO/AMC-aware baseline from `earnings_events.earnings_time`.

For full column definitions: `python tools/direct_db_query.py --schema <table_name>`

---

## Earnings Alerts and Signals

The `ei_moves_upcoming.py` module calculates signals and alerts on the `earnings_upcoming` table daily.

### Expected Move Calculation

Two methods, straddle is primary:

1. **Straddle method** (primary): `(ATM Call + ATM Put) * 0.85 / Stock Price * 100` -- uses actual options prices from `option_contracts` for the first expiration after earnings. The 0.85 is an industry-standard slippage/spread discount.
2. **IV method** (fallback): `IV * sqrt(Days to Earnings / 365) * 100` -- uses `iv_front_month` from `option_symbol_summary`

### Relative Underpricing (Primary Signal Metric)

*Added 2026-02-10. Replaces absolute move_difference_pct for signal classification.*

`relative_underpricing_pct = (historical_avg_move - expected_move) / expected_move * 100`

**What it answers:** "By what % is the market underpricing this stock's typical earnings move?"

- A 3% absolute diff on a 10% expected move = **30% relative underpricing** (interesting!)
- A 3% absolute diff on a 50% expected move = **6% relative underpricing** (meh)

Same absolute number, totally different opportunities. The old system treated them identically.

**Note:** The straddle expected move in the denominator already includes the 0.85 multiplier, making relative underpricing values slightly higher than raw straddle prices would produce. This is intentional -- we're comparing against the tradeable expected move.

### Move Difference (Legacy, Still Stored)

`move_difference_pct = historical_avg_move - expected_move`

This absolute metric is still calculated and stored in `earnings_upcoming` for backward compatibility. It's no longer used for signal classification.

### Signal Thresholds

Signals are now based on **relative underpricing**, not absolute move difference. Thresholds are configurable via `config.json`.

| Signal | Relative Underpricing | Meaning |
|--------|----------------------|---------|
| STRONG BUY | >= 50% | Market is 50%+ too cheap on this stock's earnings move |
| BUY | 30-50% | Market is 30-50% too cheap |
| WATCH | 15-30% | Market is 15-30% too cheap -- worth paying attention |
| NEUTRAL | 0-15% | Slight underpricing, no clear edge |
| AVOID | < 0% | Market overprices historical move -- options are expensive |
| UNKNOWN | N/A | Insufficient data to classify |

**Threshold status:** These thresholds are provisional (set 2026-02-10). After accumulating 100+ events with `move_vs_expected_pct` data (~early March 2026), validate whether these thresholds predict profitable trades and adjust accordingly.

### Alert Trigger Criteria

An `earnings_alert = TRUE` is set when BOTH conditions are met:
- `relative_underpricing_pct >= 15.0` (configurable via `config.json` `earnings_play.alert_underpricing_threshold`)
- `total_open_interest >= 4000` (configurable via `config.json` `earnings_play.min_open_interest`)

Alerts are aligned with the WATCH threshold -- if the system thinks it's worth watching, you hear about it. The OI threshold filters out illiquid names where the signal might be accurate but unactionable.

### Post-Earnings Metrics (earnings_moves table)

`ei_post_earnings_calc.py` computes these fields for each event at T+3:

**BMO/AMC-Aware Baseline:**
- **BMO/Unknown:** baseline = T(-1) close (day before earnings)
- **AMC:** baseline = T0 close (earnings day close, which is pre-reaction)
- Reads `earnings_events.earnings_time` to determine which

**Price Moves (relative to baseline):**

| Field | What | Notes |
|-------|------|-------|
| `pre_earnings_close` | Baseline price | BMO: T(-1) close, AMC: T0 close |
| `move_1day_pct` through `move_5day_pct` | Close-to-close vs baseline | Day numbering relative to post_start (T0 for BMO, T+1 for AMC) |
| `move_direction` | `up` or `down` | From `move_1day_pct` sign |
| `max_intraday_move_pct` | Biggest post-earnings reaction | max(abs(peak_up), abs(peak_down)) from OHLC |

**OHLC Peak Analysis:**

| Field | Window | What |
|-------|--------|------|
| `pre_earnings_peak_up_pct`, `_day` | T-7 to pre-earnings boundary | Highest high vs baseline |
| `pre_earnings_peak_down_pct`, `_day` | T-7 to pre-earnings boundary | Lowest low vs baseline |
| `pre_earnings_swing_pct` | Same | peak_up + peak_down (signed: positive = up-dominant) |
| `post_earnings_peak_up_pct`, `_day` | Post-earnings to T+5 | Highest high vs baseline |
| `post_earnings_peak_down_pct`, `_day` | Post-earnings to T+5 | Lowest low vs baseline |
| `post_earnings_swing_pct` | Same | peak_up + peak_down (signed) |
| `total_swing_pct` | T-7 to T+5 | Full window swing |

**IV Metrics:**

| Field | Formula | Source |
|-------|---------|--------|
| `iv_buildup_pct` | (IV_T-1 - IV_T-7) / IV_T-7 * 100 | `earnings_snapshots` → `option_symbol_summary` fallback |
| `iv_collapse_pct` | (IV_after - IV_before) / IV_before * 100 | Same |
| `iv_recovery_pct` | (IV_T+3 - IV_T+1) / IV_T+1 * 100 | Same |
| `iv_crush_severity` | severe (>65%), high (50-65%), normal (40-50%), mild (25-40%), minimal (<25%) | Based on abs(iv_collapse_pct) |

**Expected Move:**

| Field | Source | Purpose |
|-------|--------|---------|
| `expected_move_entry_pct` | Earliest straddle value in snapshots (T-7) | When the trade opportunity existed |
| `expected_move_final_pct` | Latest pre-earnings straddle value (T-1/T0) | Market's last prediction |
| `expected_move_pct` | Snapshot straddle → `earnings_upcoming` straddle → IV reconstruction fallback | Best available expected move for comparison |
| `move_vs_expected_pct` | abs(actual_1d_move) / expected_move * 100 | >100 = moved MORE than expected |

**Outcome Write-Back to earnings_events:**

After computing `earnings_moves`, the calculator writes a denormalized summary back to `earnings_events` for at-a-glance historical queries: `actual_move_1day_pct`, `actual_max_move_pct`, `move_vs_expected_pct`, `iv_collapse_pct`, `outcome_updated_at`.

### Standalone Commands

```bash
# Normal daily run (events at T+3)
python strategies/earnings_intel/ei_post_earnings_calc.py --no-interaction

# Recalculate all events in T+3 to T+10 window (overwrites existing)
python strategies/earnings_intel/ei_post_earnings_calc.py --recalculate --no-interaction

# Backfill earnings_events outcome columns from existing earnings_moves
python strategies/earnings_intel/ei_post_earnings_calc.py --backfill-outcomes --no-interaction

# Repair old snapshots with NULL prices
python strategies/earnings_intel/ei_snapshot_collector.py --backfill --no-interaction
```

---

## Sector Archive Integration

The Friday night archive process (`data/health/db_archive_sector.py`) handles earnings data:

| Table | Tier | Retention | Mode | Detail |
|-------|------|-----------|------|--------|
| `earnings_events` | Tier 3 | 90 days | COPY | Copied to sector archives by symbol, then deleted from production after 90 days |

Other earnings tables (`earnings_upcoming`, `earnings_watchlist`, `earnings_snapshots`, `earnings_moves`, `earnings_sector_effects`) are **not** in the archive tiers -- they either stay in production permanently or are small enough not to need archiving.

The `industry_peer_mappings` table is static reference data (742 rows) and is not archived.

---

## Data Sources

| Source | Used by | What for | Limitations |
|--------|---------|---------|-------------|
| **Finnhub** (REST API) | `ei_collector.py` | Upcoming earnings dates, BMO/AMC timing, EPS/revenue estimates | 60 req/min free tier. Per-symbol calls for 97% coverage. Config: `config.json` -> `finnhub` section |
| **Alpha Vantage** (REST API) | Daily pipeline sub-step 5 | News sentiment for watchlist symbols | 25 calls/day. Budget-aware -- skips if exhausted. |
| **`option_symbol_summary`** | Snapshot collector, moves update, post-earnings calc | IV metrics, open interest, option volume | Requires Option Pipeline to have run. Snapshot collector uses previous day's data (yesterday alignment). |
| **`option_contracts`** | Moves update (straddle) | ATM option prices for straddle expected move | Same dependency on Option Pipeline. |
| **`historical_prices`** | Snapshot collector, post-earnings calc, moves update | OHLC + stock volume for snapshots; close prices for actual move calculation | Snapshot collector uses previous day's data (yesterday alignment). |

**Key dependency:** Earnings Intelligence depends heavily on Option Pipeline data. If OP fails to run, snapshot collection and expected move calculations will use stale IV data. The system won't crash -- it'll just produce less accurate numbers.

---

## What "Normal" Looks Like

### Weekly Refresh (Fridays)
- **Earnings fetched**: 700+ symbols found out of ~726 stocks
- **No-data symbols**: ~21 (logged as JSON array in `logs/diagnostic/earnings_collector_*.log`)
- **Events archived**: 20-50 past earnings moved to `earnings_events`
- **Records cleaned**: Similar count to archived
- **Duration**: ~13 minutes (726 per-symbol Finnhub calls at 60/min)
- **Timing coverage**: ~66% BMO/AMC, ~34% Unknown
- **Zero earnings fetched** is a Finnhub API issue -- check API key and rate limits

### Daily Pipeline (6:35 AM Pre-Market)
- **Snapshots created**: 0-50 depending on how many earnings are in the T-7 to T+3 window. Zero is normal during quiet earnings weeks.
- **Moves calculated**: 0-10, only for events exactly at T+3. Zero is normal most days.
- **Expected moves updated**: Should update most symbols in `earnings_upcoming` that have IV data. Large numbers (500+) are normal.
- **Watchlist populated**: 5-30 symbols depending on earnings season. Shows signal breakdown (STRONG BUY/BUY/WATCH).
- **News enriched**: 0-25 symbols (budget-limited). Zero is normal if budget exhausted or no new watchlist entries.
- **Arbitrage scan**: Currently disabled (logs "in development" and skips).
- **Duration**: 5-15 minutes

### Log Output

Normal weekly refresh:
```
  [1/3] Archiving past earnings...
  Archived 12 past events to earnings_events
  [2/3] Cleaning up old records...
  Cleaned up 8 records (7+ days past)
  [3/3] Fetching from Finnhub (per-symbol, 726 stocks)...
  50/726 symbols (47 found, 3 no data)
  ...
  726/726 symbols (705 found, 21 no data)
  Timing coverage: 231 bmo, 248 amc, 0 dmh, 226 unknown
```

Normal daily pipeline:
```
-- SNAPSHOT COLLECTION (1/6) -- IV/price snapshots for upcoming earnings --
  Snapshots collected: 12 created

-- POST-EARNINGS CALCULATION (2/6) -- price moves and IV crush for T+3 events --
  Moves calculated: 3

-- EXPECTED MOVES UPDATE (3/6) -- recalculate signals with latest IV --
  (updates logged per-symbol)

-- WATCHLIST POPULATION (4/6) -- filter to actionable earnings plays --
  Watchlist: 15 symbols (3 new, 2 removed)

-- NEWS ENRICHMENT (5/6) -- Alpha Vantage sentiment for watchlist symbols --
  News enriched: 3 symbols (0 skipped)

-- ARBITRAGE SCAN (6/6) -- sector sympathy IV opportunities --
  Status: in development -- accumulating historical correlation data
```

The orchestrator completion box shows signal breakdown and top symbols:
```
+------------------------------------------------------------------+
| EARNINGS INTELLIGENCE COMPLETE                                    |
+------------------------------------------------------------------+
| Moves calculated today: 3                                         |
| Earnings alerts: 12 (8 STRONG BUY, 3 BUY, 1 WATCH)             |
|   Top: NVDA (2d, 52%), GOOG (5d, 35%), MSTR (3d, 28%)          |
| Watchlist: 15 symbols (3 new)                                     |
| Status: Full pipeline successful                                  |
+------------------------------------------------------------------+
```

---

## Troubleshooting

### Weekly refresh fetches 0 earnings
- **Symptom**: 0 found across all symbols
- **Cause**: Finnhub API key issue, rate limiting, or network problem
- **Check**: `python -c "from core.finnhub_api import FinnhubAPI; import json; cfg=json.load(open('config.json')); api=FinnhubAPI(cfg['finnhub']['api_key']); print(api.get_earnings_calendar('2026-03-01','2026-03-07',symbol='AAPL'))"`
- **Diagnostic log**: `logs/diagnostic/earnings_collector_YYYY-MM-DD.log`

### Snapshots always 0
- **Normal if**: No earnings in the T-7 to T+5 window (quiet week)
- **Problem if**: Earnings are happening this week but snapshots are still 0
- **Check**: `python tools/direct_db_query.py --sql "SELECT * FROM earnings_upcoming WHERE earnings_days_ahead BETWEEN 0 AND 7"` -- if rows exist but no snapshots, check that Option Pipeline is populating `option_symbol_summary` and `historical_prices`
- **Backfill**: `python strategies/earnings_intel/ei_snapshot_collector.py --backfill --no-interaction` -- repairs existing snapshots with NULL prices from `historical_prices` + `option_symbol_summary`

### Expected moves all NULL
- **Cause**: Option Pipeline hasn't run, so `option_symbol_summary` and `option_contracts` have no recent data
- **Check**: `python tools/direct_db_query.py --sql "SELECT MAX(trade_date) FROM option_symbol_summary"` -- should be today or yesterday

### Watchlist empty during earnings season
- **Normal if**: No symbols meet all three criteria (signal >= WATCH + <=14 days + OI >= 4000)
- **Check signals**: `python tools/direct_db_query.py --sql "SELECT symbol, earnings_play_signal, relative_underpricing_pct, total_open_interest FROM earnings_upcoming WHERE earnings_days_ahead <= 14 ORDER BY relative_underpricing_pct DESC LIMIT 20"`
- **Check OI**: Symbols with WATCH+ signal but OI < 4000 won't appear on watchlist

### Archive failure during weekly refresh (CRITICAL)
- **Symptom**: `earnings_archive_failed` with `CRITICAL` severity
- **Cause**: Schema mismatch between `earnings_upcoming` and `earnings_events` columns
- **Impact**: Past events not promoted to permanent archive. Autofix will attempt to resolve.

---

## Configuration

No dedicated config file. Settings come from `config.json` (project root):

```json
{
  "earnings_play": {
    "move_difference_threshold": -2.0,
    "min_open_interest": 4000,
    "alert_underpricing_threshold": 15.0,
    "signal_thresholds": {
      "watch": 15.0,
      "buy": 30.0,
      "strong_buy": 50.0
    }
  },
  "finnhub": {
    "api_key": "...",
    "base_url": "https://finnhub.io/api/v1",
    "rate_limit_per_minute": 60
  }
}
```

| Key | Default | What |
|-----|---------|------|
| `earnings_play.move_difference_threshold` | -2.0 | Legacy: absolute move diff threshold (kept for backward compat) |
| `earnings_play.min_open_interest` | 4000 | Minimum total OI for alert and watchlist entry |
| `earnings_play.alert_underpricing_threshold` | 15.0 | Minimum relative underpricing % to trigger alert (aligned with WATCH) |
| `earnings_play.signal_thresholds.watch` | 15.0 | NEUTRAL/WATCH boundary |
| `earnings_play.signal_thresholds.buy` | 30.0 | WATCH/BUY boundary |
| `earnings_play.signal_thresholds.strong_buy` | 50.0 | BUY/STRONG BUY boundary |
| `finnhub.rate_limit_per_minute` | 60 | Finnhub API rate limit for weekly collector |

If the `earnings_play` section is missing, defaults are used.

---

## Running Standalone

```bash
# Weekly refresh (archive, cleanup, Finnhub fetch) -- standalone
python strategies/earnings_intel/ei_collector.py

# Daily pipeline (snapshots, post-calc, expected moves, watchlist, news, arbitrage)
python strategies/earnings_intel/ei_main.py --daily-pipeline --no-interaction

# Morning arbitrage scan (standalone, currently disabled in daily pipeline)
python strategies/earnings_intel/ei_main.py --morning-scan --no-interaction

# Auto-detect mode (weekly refresh if Sunday + daily pipeline)
python strategies/earnings_intel/ei_main.py --all --no-interaction

# Post-earnings calc: recalculate all events in T+3 to T+10 window
python strategies/earnings_intel/ei_post_earnings_calc.py --recalculate --no-interaction

# Post-earnings calc: backfill earnings_events outcome columns
python strategies/earnings_intel/ei_post_earnings_calc.py --backfill-outcomes --no-interaction

# Snapshot collector: repair old snapshots with NULL prices
python strategies/earnings_intel/ei_snapshot_collector.py --backfill --no-interaction
```

In production, always run via `main.py` which handles timing and coordination.

---

## Related Documentation

- **Earnings straddle playbook**: `docs/EARNINGS_STRADDLE_PLAYBOOK.md` -- trade setup guide
- **Trading journal & SQL recipes**: `docs/MANUAL_OPERATIONS.md` -- how to add trading notes, set industry leaders, query results
- **Migration scripts**: `migrations/README.md` -- database schema creation (idempotent, safe to re-run)
- **System orchestration**: `main.py`, `main_runners.py` -- how EI gets called
- **Master database schema**: `data/datalake_schema_2026-01-01.md`
- **Historical design docs** (archived): `Deprecated/EARNINGS_INTELLIGENCE_SYSTEM_PRD.md`, `Deprecated/EARNINGS_INTEL_WORKFLOW.md`
- **Project overview**: `CLAUDE.md` (root) -- full system architecture
