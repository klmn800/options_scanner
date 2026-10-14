# Earnings Intelligence System — Technical Guide

**System:** Options Scanner — Earnings Intelligence Strategy
**Location:** `strategies/earnings_intel/`
**Authors:** Ben and Claude
**Last updated:** 2026-10-14
**Status:** Production. Daily pipeline is 8 sub-steps (plus a 3.5 backfill). Earnings dates are yfinance-primary with a confirmation layer (`date_confirmed`) maintained by the Earnings Researcher agent. Signal thresholds are still the provisional 2026-02-10 values — outcome data now exists to calibrate them, but no recalibration has been done.

> Code references below name functions rather than line numbers, because line numbers drift. Figures marked "as of 2026-10-14" were measured from `datalake_query.db` on that date.

---

## 1. System Purpose & Philosophy

The Earnings Intelligence (EI) system identifies **mispriced options around earnings events** by comparing what the market expects a stock to move versus what it has recently moved. When the market underprices a stock's recent earnings moves, EI flags the opportunity.

EI operates on a **proactive** model: it scans the entire KLMN universe and surfaces opportunities *before* earnings, rather than reacting to flow or price signals after the fact. This distinguishes it from the Flow Monitor, which is reactive — detecting unusual options activity as it happens.

The system produces two investor-facing outputs:

1. **`earnings_upcoming`** — the full universe of upcoming earnings with expected moves, signals, timing, and date-confirmation state. Signals recalculated daily; calendar refreshed daily for near-term dates (lite refresh) and weekly for the full universe.
2. **`earnings_watchlist`** — a filtered, enriched view of the best opportunities. Only stocks meeting the signal threshold and liquidity gate enter. This is the "action list."

And one outcome record:

3. **`earnings_events` + `earnings_moves`** — every past event with the signal it carried, what actually happened, and whether a straddle would have paid (Section 9).

Design principles:
- **Morning-first**: The pipeline runs as Step 1.2 in the daily orchestrator, before market open.
- **Fail gracefully**: Each sub-step runs in its own `try/except`. A failure in news enrichment does not block watchlist population. The pipeline's top-level `success` is True unless the pipeline itself crashes.
- **Trusted dates**: yfinance is the primary date source; Finnhub supplies BMO/AMC timing and fallback dates. Dates that have been verified are locked with `date_confirmed = 1` and are never overwritten automatically.
- **No fake data**: Every metric is measured from actual database state. If a calculation can't be performed, the column is NULL — never estimated.

---

## 2. Data Sources & External APIs

### yfinance (Primary Date Source + Estimates)
- **Usage:** Per-symbol `Ticker(symbol).calendar` calls, wrapped in a 5-second thread-pool timeout (yfinance uses `curl_cffi`, so the HTTP timeout can't be set directly). Stdout/stderr are suppressed during the call.
- **Provides:** next `earnings_date`, `eps_estimate` ("Earnings Average"), `revenue_estimate` ("Revenue Average").
- **Stale guard:** A returned date in the past is treated as "no data" (yfinance returns last quarter's date for symbols whose next report is far out).
- **Why primary:** On date conflicts, yfinance has proven more reliable than Finnhub (rewire on 2026-03-05; "yfinance wins" rule 2026-03-23).

### Finnhub (Timing + Fallback Dates)
- **Endpoint:** `GET /calendar/earnings` (per-symbol, 90 days ahead)
- **Rate limit:** 60 requests/minute (free tier), enforced by the client's rate limiter.
- **Provides:** `hour` → `earnings_time` (bmo/amc/dmh), fallback `date`, `epsEstimate`, `revenueEstimate`.
- **Used for dates only** when a symbol is new to `earnings_upcoming` and yfinance has no date.
- **Config:** `config.json` → `finnhub` section. **Client:** `core/finnhub_api.py` (`FinnhubAPI`).

### Tradier (Options & IV Data — via Option Pipeline)
- **Not called directly by EI.** EI reads `option_symbol_summary` and `option_contracts`, which the Option Pipeline populates from Tradier.
- **Data consumed:** `iv_front_month`, `iv_30dte`, `iv_45dte`, `total_call_oi`, `total_put_oi`, `total_open_interest`, `symbol_iv_percentile_30d`, `oi_balance_text`, `volume_put_call_ratio`, ATM call/put `last_price` from `option_contracts`, and closes/OHLC from `historical_prices`.

### Alpha Vantage (News Sentiment)
- **Rate limit:** 25 calls/day (single API key, shared with Flow Monitor).
- **Usage:** Enriches new and T-1 watchlist entries with relevance-weighted sentiment.
- **Budget exhaustion is not an error** — the pipeline continues; unenriched symbols may still pick up sentiment from articles Flow Monitor already collected (Section 6, news backfill).

---

## 3. Pipeline Architecture

EI runs in two modes. The daily pipeline lives in `ei_main.py`; the weekly refresh is a separate class in `ei_collector.py` called directly by the orchestrator.

### Daily Pipeline (`ei_main.run_daily_pipeline()`)

Runs as **Step 1.2** of the morning orchestrator (before market open).

| # | Sub-step | Function | What It Does |
|---|----------|----------|--------------|
| 1 | Lite Earnings Refresh | `ei_lite_refresh.run_lite_refresh()` | Re-checks dates/timing for **unconfirmed** symbols reporting within 21 days, flags disputes, and may spawn the Earnings Researcher agent. See Section 4. |
| 2 | Snapshot Collection | `SnapshotCollector.collect_daily_snapshots()` | Captures the previous trading day's OHLC, IV, OI, volume, and current straddle expected move for symbols in the T-7…T+5 window, plus up to 4 industry peers. Writes `earnings_snapshots`. |
| 3 | Archive Past Earnings | inline SQL in `ei_main.py` | `INSERT OR IGNORE` past-dated `earnings_upcoming` rows into `earnings_events`, carrying the signal columns. Runs **daily** (since 2026-04-22) so post-earnings calc can find events promptly. |
| 3.5 | event_id Backfill | inline SQL in `ei_main.py` | Sets `earnings_snapshots.event_id` where NULL by matching `earnings_events` on symbol and earnings date ±3 days (SA Proposal 029). Idempotent. |
| 4 | Post-Earnings Calculation | `PostEarningsCalculator.calculate_post_earnings_metrics()` | For events 3–10 days past: price moves, peaks/swings, IV crush, move-vs-expected. Writes `earnings_moves`, `earnings_sector_effects`, and outcome columns on `earnings_events`. Then refreshes derived columns for touched symbols. See Section 9. |
| 5 | Expected Moves Update | `ei_moves_upcoming.update_expected_moves()` | For every `earnings_upcoming` row dated today or later: recalculates straddle expected move, recent-6Q historical average, relative underpricing, signal, and alert flag. |
| 6 | Watchlist Population | `ei_watchlist.populate_watchlist()` | Cleans up expired rows, upserts qualifying + existing symbols, enriches with flow-alert counts and existing news sentiment. |
| 7 | News Enrichment | inline in `ei_main.py` | Alpha Vantage sentiment for watchlist symbols that are new today or at T-1, skipping symbols already fetched today. |
| 8 | Arbitrage Scan | *disabled* | The `ArbitrageScanner` call is commented out in `ei_main.py`; the sub-step logs "in development" and reports success with `skipped=True`. The standalone `--morning-scan` mode still runs the scanner. |

**Dependencies:** Sub-step 7 needs sub-step 6 (it enriches watchlist rows). Sub-step 4 depends on sub-step 3 having archived the event. Sub-step 5 must run before 6 for the watchlist to see fresh signals. Otherwise the steps are independent, and a failure in one does not stop the others.

**Ordering detail:** Snapshots (2) run before the archive (3), so pre-earnings snapshot rows are written with a NULL `event_id`; the 3.5 backfill fills them once the event lands in `earnings_events`.

### Weekly Refresh (`ei_collector.EarningsCollector.collect_weekly_earnings()`)

Runs as **Step 5.3** on Fridays via `main_runners.run_earnings_weekly_refresh()`. Three steps:

1. **Archive past earnings** → `earnings_events` (same SQL as daily sub-step 3; normally a no-op now that the daily pipeline archives).
2. **Cleanup** — deletes `earnings_upcoming` rows more than 7 days past their earnings date.
3. **Fetch + upsert** — for every non-ETF symbol in the KLMN universe (DB-backed list via `get_specialty_list('klmn_800')`):
   - **Confirmed rows (`date_confirmed = 1`) are skipped** — never written. Instead, yfinance is probed and any divergence from the stored date on a future event is logged to `performance.db.earnings_date_disputes` with `dispute_reason = 'confirmed_row_diverged'` (SA Proposal 021, passive drift detection).
   - **Existing unconfirmed rows:** if yfinance returns a valid future date that differs from the stored date, the stored date is **updated** (`yfinance_updated`). If yfinance has no date or agrees, the stored date is preserved; a Finnhub-only disagreement is logged but not acted on.
   - **New symbols:** yfinance date if present, else Finnhub date.
   - Estimates prefer yfinance, falling back to Finnhub. `earnings_time` comes from Finnhub.
   - Upsert: `ON CONFLICT(symbol) DO UPDATE` sets `earnings_date`; `earnings_time` uses `COALESCE(NULLIF(excluded, 'Unknown'), existing)` so known timing is never downgraded to "Unknown"; estimates use `COALESCE` to keep prior values.
   - Every symbol's source comparison is written to `performance.db.earnings_date_sources`.

> The orchestrator's mission box for this step still says "Finnhub per-symbol" for step 3. The code is yfinance-primary as described above.

### Return Dict Contract

Both modes return structured dicts consumed by the orchestrator and `tools/performance_writer.py`:
- Common: `success`, `duration_seconds`, `errors`, `sub_tasks` (per-step `success`, `duration_seconds`, and metrics).
- Daily top-level: `snapshots_created`, `moves_calculated`, `alerts_triggered`, `alert_details`, `watchlist_count`, `watchlist_new`, `watchlist_symbols`, `watchlist_breakdown`, `signals_updated`, `news_enriched`, `arb_opportunities`.
- Daily `sub_tasks` keys: `lite_refresh`, `snapshots`, `archive`, `calculations`, `expected_moves`, `watchlist`, `news_enrichment`, `arbitrage`.
- Weekly: `earnings_found`, `events_archived`, `records_cleaned`, `upcoming_count`, `no_data_count`, `timing_breakdown`, `date_source_counts`; `sub_tasks` keys `archive`, `cleanup`, `fetch`.

---

## 4. Earnings Date Confirmation

Getting the date right matters more than anything else: a signal on the wrong date is worthless. Since April 2026, dates have three layers of protection.

### Confirmation columns (`earnings_upcoming`)
- `date_confirmed` (INTEGER, default 0), `date_confirmed_by` (`ben` / `agent`), `date_confirmed_at`.
- Added idempotently by `ei_lite_refresh._ensure_confirmation_schema()`.
- Written **only** by `tools/earnings_confirm.py` (used by Ben and by the Earnings Researcher agent). Safety rules in that tool: `--date` and `--by` are required; a row confirmed by `ben` can only be modified with `--by ben`.
- As of 2026-10-14: 159 confirmed rows, all `confirmed_by = agent`.

### Lite refresh (daily sub-step 1)
For each **unconfirmed** row dated today through today+21:
1. Fetch yfinance date and Finnhub date/timing.
2. If yfinance differs from the stored date → update `earnings_date` (guarded by `date_confirmed = 0`).
3. If Finnhub has timing and the stored timing is `Unknown` → update `earnings_time`.
4. For **future** events only, flag a dispute:
   - `unknown_time` — effective timing still Unknown.
   - `date_disagreement` — yfinance and Finnhub differ by 2–45 days (a gap over 45 days is treated as Finnhub showing next quarter, not a disagreement), **or** yfinance moved the stored date by more than 3 days.
   - `both` — unknown timing *and* a yfinance/Finnhub disagreement.
5. Disputes are written to `performance.db.earnings_date_disputes` (`resolution = 'unresolved'`).

### Earnings Researcher spawn
After the loop, the lite refresh spawns the Earnings Researcher agent (fire-and-forget, visible console window via a temp `.bat`) when **either** there are disputes **or** any unconfirmed row is due within `SPAWN_HORIZON_DAYS = 14`. The second condition was added 2026-09-24 so that zero-dispute mornings no longer skip the agent's backlog. Spawning is skipped if the agent is disabled in `config.json` (`tools/agent_toggle.is_agent_enabled`) or not installed. The agent workspace is private; see `agents/README.md`.

### Dispute table (`performance.db.earnings_date_disputes`)
- **PK:** `(trade_date, symbol)`. Canonical DDL lives in `performance_writer.ensure_schema()`, which both writers call first so the table self-heals after a DB rebuild.
- `dispute_reason`: `date_disagreement`, `unknown_time`, `both`, `confirmed_row_diverged`.
- `resolution`: `unresolved`, `confirmed_ben`, `confirmed_agent`, `skipped`; plus `resolved_date`, `resolved_time`, `resolved_at`, `research_url`, `notes`.

---

## 5. Signal Classification System

### The Core Metric: Relative Underpricing

```
relative_underpricing_pct = (historical_avg_move_pct - straddle_expected_move_pct) / straddle_expected_move_pct * 100
```

- **`historical_avg_move_pct`** is the average absolute 1-day move over the symbol's **most recent 6 quarters** in `earnings_moves` (since 2026-04-13; configurable via `earnings_play.recent_quarters`). The all-time average is stored alongside as `historical_avg_move_alltime_pct`, with `historical_quarters_used` recording how many quarters went into the recent average. If fewer than 6 exist, all available quarters are used.
- **`straddle_expected_move_pct`** is the only denominator. The IV-based fallback and the `expected_move_pct` column were removed from `earnings_upcoming`, `earnings_events`, and `earnings_watchlist` on 2026-04-26 (SA Proposal 017). The fallback had produced false STRONG BUYs when front-month IV came from an expiration *before* earnings. If the straddle can't be computed, the signal is `UNKNOWN`.
- `move_difference_pct` (absolute difference) is still computed and stored for backward compatibility but does not drive signals.

### Straddle Expected Move

`ei_moves_upcoming.get_straddle_expected_move()`:
1. Latest close from `historical_prices`.
2. First expiration on or after the earnings date in `option_contracts` (latest `trade_date`).
3. ATM strike = strike closest to the close; needs both CALL and PUT with `last_price > 0`.
4. `(call + put) × 0.85 / close × 100`.

The **0.85 multiplier** is described in the code (`get_straddle_expected_move`, `determine_earnings_play_signal`) as an industry-standard haircut for spread and execution cost. That rationale has not been independently verified. Its effects are measurable, though:

- **It alone produces a WATCH signal.** A stock whose recent average move exactly equals the raw straddle scores (1/0.85 − 1) = **+17.6%** relative underpricing, which is above the 15% WATCH threshold.
- **About half of actionable signals depend on it.** Across the 1,511 events with outcomes as of 2026-10-14, recomputing without the haircut cuts WATCH-or-better signals from 216 to 107, and STRONG BUY from 68 to 34.
- **Outcome labels inherit it.** `straddle_outcome` compares the actual move to the haircut figure, so PROFIT (≥110%) corresponds to only 93.5% of the raw straddle, and FLAT (≥95%) to 80.75%. Measured against the raw straddle, PROFIT labels drop from 379 to 289.

The straddle and the historical average are also not quite like-for-like. The straddle is priced at `last_price` (not the bid/ask midpoint), on the first expiration on or after earnings, which can be weeks out and so carries non-earnings time value. The historical average is a 1-day move. Any threshold calibration should treat the multiplier as a parameter to test, not a given.

On the UPDATE, `straddle_expected_move_pct = COALESCE(new, existing)`: if today's straddle can't be built (thin chain), the last good value is kept.

**Coverage:** The Option Pipeline collects contracts about 2 months out, so symbols with distant earnings have no post-earnings expiration yet and stay `UNKNOWN`. Coverage is good inside the 14-day watchlist window.

### Scope

Only rows with `earnings_date >= today` are recalculated. Past-due rows are left for archiving and never recalculated, because near-expiry straddles produce absurd underpricing values.

### Signal Tiers

`ei_moves_upcoming.determine_earnings_play_signal()`:

| Signal | Relative Underpricing | Meaning |
|--------|----------------------|---------|
| **AVOID** | < 0% | Market prices a bigger move than the recent history. |
| **NEUTRAL** | 0% to < 15% | Slight underpricing, not enough to act on. |
| **WATCH** | 15% to < 30% | Meaningful underpricing. |
| **BUY** | 30% to < 50% | Significant underpricing. |
| **STRONG BUY** | ≥ 50% | Substantial underpricing. |
| **UNKNOWN** | N/A | No straddle or no history. |

Thresholds: `config.json` → `earnings_play.signal_thresholds` (`watch` 15, `buy` 30, `strong_buy` 50 — unchanged since 2026-02-10).

### Alert Gate

`ei_moves_upcoming.should_trigger_earnings_alert()` sets `earnings_upcoming.earnings_alert = 1` when:
- `relative_underpricing_pct >= earnings_play.alert_underpricing_threshold` (15), **and**
- `total_open_interest >= earnings_play.min_open_interest` (4,000), read from `option_symbol_summary.total_open_interest` on the latest trade date.

Alerts are counted and listed (top 5 by underpricing) in the orchestrator's completion box, and the flag is read by Morning View (`morning_view/tui_data.py`, `morning_views.py`). EI itself sends no email for them.

---

## 6. The Earnings Watchlist

### Schema (21 columns)

Created by `ei_watchlist._create_table()`:

```sql
CREATE TABLE earnings_watchlist (
    symbol TEXT PRIMARY KEY,
    status TEXT NOT NULL,              -- UPCOMING, TODAY, T+1, T+2, T+3
    current_price REAL,                -- option_symbol_summary.close_price (latest trade_date)
    days_to_earnings INTEGER NOT NULL, -- positive = future, 0 = today, negative = past
    earnings_date TEXT NOT NULL,
    earnings_time TEXT,                -- bmo, amc, dmh, Unknown
    earnings_play_signal TEXT,
    iv_percentile_30d REAL,            -- symbol_iv_percentile_30d (falls back to prior day if NULL)
    relative_underpricing_pct REAL,
    historical_avg_move_pct REAL,      -- recent-6Q average
    straddle_expected_move_pct REAL,
    oi_balance_text TEXT,              -- from option_symbol_summary
    vol_balance_text TEXT,             -- derived from volume_put_call_ratio (see below)
    iv_front_month_change_5d REAL,     -- % change in iv_front_month vs 5 trading days ago (IV ramp)
    alert_count_5d INTEGER,            -- flow_symbol_summary.alert_count_5d
    news_sentiment_label TEXT,
    news_sentiment_score REAL,         -- relevance-weighted, -1 to +1
    news_article_count INTEGER,
    first_appeared_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_updated TEXT NOT NULL
)
```

Changes since February 2026: `expected_move_pct` dropped (SA P017). The T+3 outcome columns (`actual_move_pct`, `move_direction`, `iv_collapse_pct`, `iv_crush_severity`) were removed in the 2026-04-14 audit; outcomes now live on `earnings_events` (Section 9). `vol_balance_text` and `iv_front_month_change_5d` were added 2026-04-14.

**`vol_balance_text`** thresholds on `volume_put_call_ratio`: < 0.5 "Clear Call Vol", < 0.77 "Heavy Call Vol", ≤ 1.3 "Balanced Vol", ≤ 1.9 "Heavy Put Vol", else "Clear Put Vol". Because the morning OP run writes today's summary row before there is any volume, a NULL ratio falls back to the previous trading day.

### Entry Criteria

A new symbol enters when ALL of:
1. `earnings_play_signal` IN ('WATCH', 'BUY', 'STRONG BUY')
2. `earnings_date` between today and today+14 (calendar days)
3. `total_call_oi + total_put_oi >= 4,000` on the latest `option_symbol_summary` trade date

Once on the list, a symbol is refreshed daily **regardless of signal** — a downgrade updates the column but does not remove the row. If its `earnings_upcoming` row is gone (archived), the stored `earnings_date` is kept and the signal columns go NULL.

### Status Lifecycle & Cleanup

```
UPCOMING ──→ TODAY ──→ T+1 ──→ T+2 ──→ T+3 ──→ (deleted at T+4)
```

`_cleanup_expired()` runs first each day and deletes rows that are **4+ days past** earnings **or more than 14 days out**. The second rule catches symbols whose date was pushed back beyond the window.

### Upsert & Enrichment Ownership

- **INSERT** writes all 21 columns (enrichment columns NULL).
- **ON CONFLICT UPDATE** refreshes status, price, dates, timing, signal and analytics columns. `iv_percentile_30d` uses `COALESCE` to keep the prior value. It deliberately **does not** touch `alert_count_5d` or the three `news_*` columns, so yesterday's enrichment survives until overwritten.
- `first_appeared_date` / `created_at` are set *after* `clean_database_row()` (the formatter nullifies date-like strings) and are never updated on conflict.
- **Flow enrichment** — `alert_count_5d` from `flow_symbol_summary` (latest trade date).
- **News backfill** — for rows with NULL `news_sentiment_score`, aggregates the last 3 days of `news_symbol_sentiment` (often collected by Flow Monitor). Uses the same relevance weighting as `tools/news_sentiment.py`, and the label is a distribution like `Bull 3/Neutral 1`.
- **News enrichment (sub-step 7)** — fresh Alpha Vantage fetch for new and T-1 symbols, overwriting the three news columns.

As of 2026-10-14: 19 rows.

---

## 7. IV Crush Severity Scale

`iv_collapse_pct = (post_iv - pre_iv) / pre_iv * 100` (negative when IV drops). Classification uses the absolute value:

| Tier | \|IV Collapse\| | Interpretation |
|------|-------------|----------------|
| **severe** | > 65% | Exceptionally large crush. |
| **high** | 50% – 65% | Above-average crush. |
| **normal** | 40% – 50% | Typical; ~45% is the observed center. |
| **mild** | 25% – 40% | Below-average; lingering uncertainty. |
| **minimal** | < 25% | Little reduction; possible ongoing catalyst. |

The same thresholds are applied in both IV paths in `ei_post_earnings_calc.py` (`_calculate_iv_changes` and `_get_iv_from_option_summary`). The scale is provisional (set Feb 2026 from observed distributions).

---

## 8. Tables & Data Lifecycle

### Data Flow

```
yfinance + Finnhub ──→ earnings_upcoming ──→ earnings_watchlist (action list)
   (lite daily /         │   ▲                      ▲
    full Friday)         │   └── tools/earnings_confirm.py (date_confirmed)
                         │                          ├── flow_symbol_summary
                         │                          └── news_symbol_sentiment
                    (daily archive)
                         ▼
                   earnings_events ◀── outcome columns ── earnings_moves
                         │                                   ▲
                         ▼                                   │
             sector archives (Tier 3, 90d COPY,     earnings_snapshots (T-7…T+5)
             production rows retained)                       │
                                                     earnings_sector_effects

performance.db: ei_pipeline_performance, earnings_date_sources, earnings_date_disputes
```

### Table Reference

**`earnings_upcoming`** — one row per symbol (`PK symbol`).
- **Written by:** `ei_collector.py` (weekly), `ei_lite_refresh.py` (daily date/timing), `ei_moves_upcoming.py` (daily analytics), `tools/earnings_confirm.py` (confirmation).
- **Key columns:** `earnings_date`, `earnings_time`, `earnings_days_ahead`, `straddle_expected_move_pct`, `historical_avg_move_pct`, `historical_avg_move_alltime_pct`, `historical_quarters_used`, `relative_underpricing_pct`, `move_difference_pct`, `earnings_play_signal`, `earnings_alert`, `eps_estimate`, `revenue_estimate`, `date_confirmed`, `date_confirmed_by`, `date_confirmed_at`, `updated_at`.
- As of 2026-10-14: 777 rows, 766 future-dated, 540 with known bmo/amc/dmh timing.

**`earnings_watchlist`** — Section 6.

**`earnings_events`** — every past event (`PK event_id`, unique on `symbol, earnings_date`).
- **Written by:** daily archive (sub-step 3) and weekly archive, both `INSERT OR IGNORE`; outcome columns by `PostEarningsCalculator._update_event_outcome()`; derived columns refreshed by `tools/backfill_earnings_events_derived.py`.
- **Signal snapshot (8 columns, frozen at archive time):** `earnings_play_signal`, `relative_underpricing_pct`, `straddle_expected_move_pct`, `historical_avg_move_pct`, `historical_avg_move_alltime_pct`, `historical_quarters_used`, `eps_estimate`, `revenue_estimate`.
- **Outcome columns:** `actual_move_1day_pct`, `actual_max_move_pct`, `move_vs_expected_pct`, `iv_collapse_pct`, `move_vs_straddle_pct`, `straddle_outcome`, `move_vs_straddle_max_pct`, `straddle_outcome_max`, `move_vs_historical_pct`, `signal_accuracy`, `outcome_updated_at`.
- **Archive:** Tier 3 (90-day COPY) to sector databases, but `skip_cleanup` keeps all rows in production because post-earnings calc needs them.

**`earnings_moves`** — post-earnings metrics (`PK move_id`, unique on `event_id, symbol`).
- **Written by:** `PostEarningsCalculator`. Not archived.
- **Key columns:** `move_1day_pct`, `move_2day_pct`, `move_3day_pct`, `move_5day_pct`, `move_direction`, `max_intraday_move_pct`, `pre_earnings_close`, pre/post peak up/down pct and day, `pre_earnings_swing_pct`, `post_earnings_swing_pct`, `total_swing_pct`, `iv_buildup_pct`, `iv_collapse_pct`, `iv_recovery_pct`, `iv_crush_severity`, `expected_move_pct`, `expected_move_entry_pct`, `expected_move_final_pct`, `move_vs_expected_pct`, `earnings_date`.
- `historical_avg_move_pct` (Section 5) is computed from this table, so its quality drives signal quality. As of 2026-10-14: 17,450 rows, earnings dates 2021-01-04 … 2026-10-09.

**`earnings_snapshots`** — daily time series around each event (unique on `symbol, earnings_date, snapshot_date`).
- **Written by:** `SnapshotCollector`. Data alignment: each morning captures the **previous complete trading day** from `historical_prices` (OHLC, volume) and `option_symbol_summary` (IV, OI, put/call, option volume), plus the current `straddle_expected_move_pct` from `earnings_upcoming`.
- **Window:** `earnings_upcoming` rows with `days_from_earnings` −7…+5, unioned with `earnings_events` rows 0…+5, so post-earnings capture continues after the upcoming row rolls to next quarter.
- **Peers:** up to 4 from `industry_peer_mappings` (same industry, leaders first), stored with `is_primary_symbol = 0`.
- **Columns:** `snapshot_id`, `symbol`, `earnings_date`, `event_id`, `snapshot_date`, `days_from_earnings`, `snapshot_type` (pre_earnings / earnings_day / post_earnings), `open_price`, `high_price`, `low_price`, `close_price`, `volume`, `option_volume`, `iv_30dte`, `iv_front_month`, `iv_45dte`, `total_open_interest`, `put_call_ratio`, `is_primary_symbol`, `straddle_expected_move_pct`, `created_at`.
- **Join-key policy:** `earnings_date` is captured *as of* `snapshot_date` and can drift across one event's rows as yfinance revises. **Join on `event_id`, not `(symbol, earnings_date)`.** `event_id` is written immediately for post-earnings rows and back-filled for pre-earnings rows by sub-step 3.5.
- As of 2026-10-14: 44,300 rows since 2026-03-02.

**`earnings_sector_effects`** — peer sympathy metrics. Written by `PostEarningsCalculator._calculate_sector_effects()` for each processed event (160,918 rows as of 2026-10-14). The morning arbitrage scanner that would also write here is disabled (Section 3).

**`news_symbol_sentiment`** — per-symbol news sentiment from Alpha Vantage. `tools/news_sentiment.py`; one fetch per symbol per day.

**performance.db tables:** `ei_pipeline_performance` (Section 11), `earnings_date_sources` (weekly per-symbol source comparison: `stored_date`, `yfinance_date`, `finnhub_date`, `finnhub_timing`, `date_source`, `conflict`), `earnings_date_disputes` (Section 4).

---

## 9. Post-Earnings Analysis

`ei_post_earnings_calc.PostEarningsCalculator`.

### Event selection
Events in `earnings_events` that are **3–10 calendar days** past their date (as measured against the latest `option_symbol_summary` trade date), and that do not yet have an `earnings_moves` row with a non-NULL `iv_collapse_pct`. Weekend gaps are handled naturally: a Thursday report reaches T+3 on Sunday and is picked up Monday. An event whose IV data is still missing is retried each day until day 10. Older misses need the backfill scripts. `recalculate_all()` (`--recalculate` in the CLI) ignores the existing-row check.

### Price moves — BMO/AMC-aware baseline
- **Baseline:** AMC → T0 close; BMO or unknown → T-1 close (treating unknown as BMO avoids missing the gap).
- **Primary source:** `earnings_snapshots` (primary-symbol rows). Computes `move_1/2/3/5day_pct` close-to-close from the baseline, pre-earnings peaks (T-7 to last pre-earnings day), post-earnings peaks (reaction start to T+5), signed swings, `total_swing_pct`, and `max_intraday_move_pct` (largest post-earnings peak by magnitude). Also `expected_move_entry_pct` (earliest snapshot's straddle, ideally T-7) and `expected_move_final_pct` (last pre-earnings snapshot's straddle).
- **Fallback:** `historical_prices` using on-or-after/on-or-before date lookups. `max_intraday_move_pct` comes from the first post-earnings day's high/low only.

### IV changes
- **Primary:** `earnings_snapshots.iv_30dte` — buildup (T-7→T-1), collapse (T-1→first post-earnings snapshot), recovery (first→second post-earnings snapshot).
- **Fallback:** `option_symbol_summary.iv_front_month` — buildup (≤T-5→T-1), collapse (T-1→T+1), recovery (T+1→≥T+3).

### Expected move & move-vs-expected
`expected_move_pct` on `earnings_moves`, in priority order:
1. `expected_move_entry_pct` from snapshots (the straddle when the trade thesis existed).
2. `earnings_upcoming.straddle_expected_move_pct` if the row still has this earnings date.
3. IV reconstruction: pre-earnings IV × √(1/365) × 100. It looks in `option_symbol_summary` first, then the symbol's sector archive (TA Proposal 003).

`move_vs_expected_pct = |move_1day_pct| / expected_move_pct × 100` (>100 = moved more than priced).

### Outcome write-back to `earnings_events`
`_update_event_outcome()` writes the outcome columns using the **signal-time** straddle and history stored on the event:

| Metric | Formula | Classification |
|--------|---------|----------------|
| `move_vs_straddle_pct` / `straddle_outcome` | \|1-day move\| ÷ straddle × 100 | ≥110 **PROFIT**, ≥95 **FLAT**, else **LOSS** (close-exit trade outcome) |
| `move_vs_straddle_max_pct` / `straddle_outcome_max` | \|max move\| ÷ straddle × 100 | same tiers (peak-exit outcome, SA P015) |
| `move_vs_historical_pct` / `signal_accuracy` | \|1-day move\| ÷ historical avg × 100 | ≥100 **CONFIRMED**, ≥80 **CLOSE**, ≥60 **OVER**, else **WAY OFF** |

The two classifiers are pure helpers (`compute_straddle_outcome`, `compute_move_vs_historical`) shared with the backfill tools so thresholds can't drift.

### Derived-column refresh (SA Proposal 016)
Adding an `earnings_moves` row shifts the recent-6Q baseline for that symbol's other events. At the end of each run, the calculator calls `tools/backfill_earnings_events_derived.run(symbols=touched, apply=True)`. That recomputes `historical_avg_move_pct` and its cascade (`relative_underpricing_pct`, `earnings_play_signal`, `move_vs_historical_pct`, `signal_accuracy`) on `earnings_events`, using `as_of_date` semantics so an event's own move never counts toward its own baseline.

---

## 10. Orchestration & Scheduling

### Daily (Step 1.2)
```
Step 1.1: Morning Option Pipeline
Step 1.2: Earnings Intelligence   ← 8 sub-steps (+3.5)
Step 1.3: Metadata Collection
Step 1.4: Trade Ingest
Step 1.5: Query Sync (Morning)
```
Runner: `main_runners.run_earnings_intelligence()` → `ei_main.run_daily_pipeline()`. Phase 1 runs only when the orchestrator starts before 9:00 AM; later starts skip to Flow Monitor.

### Friday (Step 5.3)
```
Step 5.1: Database Backup (Weekly) — background thread
Step 5.2: FM Baseline Update
Step 5.3: Earnings Calendar Refresh   ← EarningsCollector
Step 5.4: Sector Archive Operations
```
Runner: `main_runners.run_earnings_weekly_refresh()`.

### CLI
```bash
python main.py --earnings-intel                                          # orchestrator from Step 1.2
python strategies/earnings_intel/ei_main.py --daily-pipeline --no-interaction
python strategies/earnings_intel/ei_main.py --morning-scan               # standalone arbitrage scanner
python strategies/earnings_intel/ei_moves_upcoming.py --symbol AAPL      # recalc one symbol
python strategies/earnings_intel/ei_post_earnings_calc.py --recalculate  # force T+3..T+10 recalc
python tools/earnings_confirm.py --list-unconfirmed                      # unconfirmed within 21d
python tools/earnings_confirm.py --symbol VZ --date 2026-04-27 --time bmo --by ben
python tools/backfill_earnings_events_derived.py [--symbols A,B] [--apply]
```

### Console Output
The orchestrator prints a mission box listing the 8 sub-steps and a completion box with: snapshots collected, moves calculated, signals updated, watchlist count/new/breakdown, news enriched (if any), arbitrage opportunities (if any), and earnings alerts with the top 5 by underpricing. A watchlist table follows. The strategy layer prints progress lines only, per the console architecture (`docs/CONSOLE_DEVELOPER_GUIDE.md`).

---

## 11. Performance Tracking

Phase 6 writes `performance.db.ei_pipeline_performance` via `tools/performance_writer._write_ei_performance()`. `PK (trade_date, run_type)`, where `run_type` is `daily_pipeline` (from step `1.2 Earnings Intelligence`) or `weekly_refresh` (from step `5.3 Earnings Refresh`).

| Column | Run type | Source |
|--------|----------|--------|
| `duration_seconds`, `success`, `error_count` | both | top-level result |
| `snapshots_created`, `moves_calculated`, `alerts_triggered` | daily | top-level |
| `snapshot_seconds`, `calculation_seconds`, `expected_move_seconds` | daily | `sub_tasks.*.duration_seconds` |
| `watchlist_count`, `watchlist_new`, `news_enriched`, `watchlist_seconds`, `news_seconds` | daily | top-level / sub_tasks |
| `earnings_today`, `opportunities_found`, `high_quality`, `medium_quality`, `low_quality`, `persisted` | daily | arbitrage sub-task (all zero while the scan is disabled) |
| `earnings_found`, `events_archived`, `records_cleaned`, `upcoming_count` | weekly | top-level |
| `fetch_seconds`, `archive_seconds`, `cleanup_seconds` | weekly | sub_tasks |

Not persisted to this table: lite-refresh metrics, the daily archive count, and the event_id backfill count. These appear only in the result dict, the diagnostic log (`logs/diagnostic/`), and the EI health report. Dispute history is available in `earnings_date_disputes`.

---

## 12. Known Limitations & Open Work

### Active limitations

1. **Signal thresholds have never been calibrated.** WATCH/BUY/STRONG BUY (15/30/50) are the 2026-02-10 distribution-based values. Outcome data now exists. A raw count as of 2026-10-14 (events with a `straddle_outcome`, by the signal they carried) is shown below. It is *descriptive only*: it mixes pre- and post-6Q-recency signals, ignores liquidity and timing, and is not a validation.

   | Signal | Events | PROFIT | LOSS | Avg move vs straddle |
   |---|---|---|---|---|
   | STRONG BUY | 68 | 21 | 42 | 97.3% |
   | BUY | 62 | 29 | 31 | 111.9% |
   | WATCH | 86 | 21 | 59 | 76.2% |
   | NEUTRAL | 120 | 51 | 63 | 113.7% |
   | AVOID | 1,175 | 256 | 846 | 72.8% |

2. **Arbitrage scanner disabled.** Sub-step 8 is a stub. The scanner code and `--morning-scan` mode remain.
3. **Peer snapshot `event_id`.** For peer rows (`is_primary_symbol = 0`), both the writer and the 3.5 backfill look up `earnings_events` by the *peer's* symbol. A peer row therefore gets an `event_id` only when the peer itself reported within ±3 days, and that id is the peer's event, not the primary's. As of 2026-10-14, about 23.6K of 31.7K peer rows have a NULL `event_id`. Don't treat peer `event_id` as the primary event's key.
4. **News budget.** 25 Alpha Vantage calls/day shared with Flow Monitor. The 3-day backfill from existing articles softens the impact.
5. **Timing coverage.** As of 2026-10-14, 540 of 777 `earnings_upcoming` rows have bmo/amc/dmh. The rest are `Unknown`; the lite refresh flags these for future events within 21 days, and the researcher resolves them.
6. **Docstring drift.** Some module docstrings predate later changes. The `ei_post_earnings_calc.py` header lists `option_symbol_summary` as the primary IV source, but the code tries snapshots first. Its `_get_expected_move_at_earnings` docstring describes `option_symbol_summary` as Tier 2/30-day, but it is Tier 3 with a 300-day override since SA P028. `ei_collector.py`'s class docstring says existing dates are never overwritten, but the code updates them from yfinance. The weekly runner's mission box says "Finnhub per-symbol". This guide follows the code.

### Open work

| Item | Status |
|------|--------|
| Signal threshold calibration | Data available; not started |
| Arbitrage scanner re-enable | Waiting on design decision |
| Post-earnings actuals (`actual_eps` on `earnings_events`) | Not implemented. Both archive queries (`ei_main.py` sub-step 3, `ei_collector._archive_past_earnings`) insert a literal NULL for `actual_eps` and `estimated_eps`. As of 2026-10-14, all 2,216 pipeline-archived events (`source = 'earnings_upcoming'`) lack actual EPS; backfilled history (yfinance/Finnhub) has it. The estimate is carried in `eps_estimate` instead, so readers of `estimated_eps` (e.g. the Morning View trading journal) see nothing for these rows. |
| Lite-refresh metrics in `ei_pipeline_performance` | Not implemented |

Completed since the last revision: earnings scenario calculator (`tools/earnings_scenario.py`, doc `docs/earnings-scenario-calculator.md`); Morning View earnings screens (`morning_view/screens/earnings_browser.py`); snapshot ramp-up (primary snapshot path active since March 2026).

---

## 13. Operations & Queries

### Downstream consumers
- **Flow Monitor watchlist** — `strategies/flow_monitor/fm_watchlist.py` copies `earnings_date`, `earnings_time`, `earnings_play_signal`, and `relative_underpricing_pct` from `earnings_upcoming` into `flow_watchlist_daily` when it **creates** an entry. The values are not refreshed on later scans, so they reflect the signal on the entry date.
- **Morning View** — reads `earnings_upcoming` (including `earnings_alert`) and `earnings_watchlist`; `morning_view/screens/earnings_browser.py` is the earnings screen.
- **Earnings Researcher agent** — reads `earnings_date_disputes` and unconfirmed `earnings_upcoming` rows, and writes confirmations through `tools/earnings_confirm.py` (Section 4).

### Manual operations

**Confirming a date.** Use `tools/earnings_confirm.py` rather than editing `earnings_upcoming` directly (Section 4). `--list-unconfirmed` shows what the lite refresh will keep checking.

**Recalculating post-earnings metrics.**
```bash
python strategies/earnings_intel/ei_post_earnings_calc.py --recalculate --no-interaction       # T+3..T+10 window, overwrites
python strategies/earnings_intel/ei_post_earnings_calc.py --backfill-outcomes --no-interaction # fill NULL outcome columns from earnings_moves
python strategies/earnings_intel/ei_snapshot_collector.py --backfill --no-interaction          # repair snapshots with NULL OHLC
python tools/backfill_earnings_events_derived.py --symbols NVDA --apply                        # refresh derived signal columns
```
To recalculate a single older event, delete its `earnings_moves` row (by `event_id`) and run `--recalculate` with `--trade-date` set 3–10 days after that event.

**Industry leaders.** `industry_peer_mappings.is_industry_leader` sets which peers get snapshotted first (`SnapshotCollector._get_peer_symbols` sorts leaders first and takes 4). As of 2026-10-14 no leaders are set, so peers are chosen alphabetically within each industry.
```sql
UPDATE industry_peer_mappings SET is_industry_leader = 1
WHERE industry = 'Semiconductors' AND symbol IN ('NVDA', 'AMD');
```

**Trading journal.** `earnings_events` has `notes`, `tags`, `note_type` (trade / observation / pattern / lesson), and `sentiment` columns. Morning View's admin trading-journal screen writes them (`morning_view/admin_data.append_journal_note`). As of 2026-10-14 none are filled in.

### Queries

Run with `python tools/direct_db_query.py --sql "..."` (query DB). Add `--db data/performance.db` for the dispute tables.

```sql
-- Current watchlist, best first
SELECT symbol, status, earnings_date, earnings_time, earnings_play_signal,
       relative_underpricing_pct, straddle_expected_move_pct, iv_front_month_change_5d
FROM earnings_watchlist ORDER BY relative_underpricing_pct DESC;

-- Upcoming actionable signals, with confirmation state
SELECT symbol, earnings_date, earnings_time, earnings_play_signal,
       relative_underpricing_pct, date_confirmed
FROM earnings_upcoming
WHERE earnings_play_signal IN ('WATCH', 'BUY', 'STRONG BUY') AND earnings_date >= DATE('now')
ORDER BY earnings_date;

-- Signal vs outcome (signal frozen at archive time)
SELECT earnings_play_signal, COUNT(*) AS n,
       SUM(straddle_outcome = 'PROFIT') AS profit_close_exit,
       SUM(straddle_outcome_max = 'PROFIT') AS profit_peak_exit,
       SUM(signal_accuracy = 'CONFIRMED') AS confirmed
FROM earnings_events WHERE straddle_outcome IS NOT NULL
GROUP BY earnings_play_signal ORDER BY n DESC;

-- One symbol's earnings history (join on event_id, never on symbol alone)
SELECT ee.earnings_date, ee.earnings_time, em.move_1day_pct, em.max_intraday_move_pct,
       em.expected_move_entry_pct, em.move_vs_expected_pct, em.iv_collapse_pct, em.iv_crush_severity
FROM earnings_moves em JOIN earnings_events ee ON em.event_id = ee.event_id
WHERE em.symbol = 'NVDA' ORDER BY ee.earnings_date DESC;

-- Snapshot series for an event (primary symbol; join on event_id per the snapshot policy)
SELECT es.snapshot_date, es.days_from_earnings, es.close_price, es.iv_30dte, es.straddle_expected_move_pct
FROM earnings_snapshots es JOIN earnings_events ee ON es.event_id = ee.event_id
WHERE ee.symbol = 'NVDA' AND ee.earnings_date = '2026-08-26' AND es.is_primary_symbol = 1
ORDER BY es.days_from_earnings;

-- Peer sympathy for an event
SELECT peer_symbol, primary_move_pct, peer_move_pct, iv_arbitrage_delta,
       correlation_strength, arbitrage_quality
FROM earnings_sector_effects
WHERE primary_event_id = (SELECT event_id FROM earnings_events WHERE symbol = 'NVDA' AND earnings_date = '2026-08-26');

-- Today's open date disputes (performance.db)
SELECT symbol, db_date, yfinance_date, finnhub_date, dispute_reason
FROM earnings_date_disputes
WHERE trade_date = (SELECT MAX(trade_date) FROM earnings_date_disputes) AND resolution = 'unresolved';
```

### Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| Signal `UNKNOWN` inside 14 days | No post-earnings expiration with both ATM call and put priced, or no `earnings_moves` history | `option_contracts` for the symbol on the latest `trade_date` with `expiration_date >= earnings_date`; `COUNT(*)` in `earnings_moves` |
| Snapshot rows with NULL IV | Option Pipeline had no IV for that symbol/day | `iv_30dte`, `iv_front_month` in `option_symbol_summary` for the snapshot's `data_date` |
| Event never gets `earnings_moves` | Event not archived, or outside the 3–10 day window when the pipeline ran | `earnings_events` row exists; rerun with `--recalculate --trade-date` |
| `earnings_moves` row keeps recomputing | `iv_collapse_pct` is NULL, so the event is retried daily until day 10 | IV around the earnings date in snapshots / `option_symbol_summary` |
| Stored date wrong | Unconfirmed: lite refresh or Friday refresh will follow yfinance. Confirmed: locked, divergence logged as `confirmed_row_diverged` | `earnings_date_disputes`; fix with `tools/earnings_confirm.py` |
| Researcher didn't spawn | No disputes and nothing unconfirmed within 14 days, agent disabled in `config.json`, or not installed | lite-refresh log lines in the daily console / `logs/diagnostic/` |
| News columns empty | Alpha Vantage budget used up and no FM-collected articles in the last 3 days | `python tools/news_sentiment.py --budget` |

---

## File Reference

| File | Role |
|------|------|
| `strategies/earnings_intel/ei_main.py` | Daily pipeline orchestrator (8 sub-steps), `--morning-scan` |
| `strategies/earnings_intel/ei_lite_refresh.py` | Daily near-term date verification, dispute flagging, researcher spawn |
| `strategies/earnings_intel/ei_collector.py` | Weekly refresh: archive, cleanup, yfinance+Finnhub fetch, drift detection |
| `strategies/earnings_intel/ei_moves_upcoming.py` | Straddle expected move, recent-6Q history, signals, alert flag |
| `strategies/earnings_intel/ei_watchlist.py` | Watchlist lifecycle, enrichment, news backfill |
| `strategies/earnings_intel/ei_post_earnings_calc.py` | Price moves, IV crush, outcomes, sector effects |
| `strategies/earnings_intel/ei_snapshot_collector.py` | Daily T-7…T+5 snapshots (primary + peers) |
| `strategies/earnings_intel/ei_arbitrage_scanner.py` | Sector sympathy scanner (not run in daily pipeline) |
| `strategies/earnings_intel/ei_health_reporter.py` | EI health status reporting |
| `strategies/earnings_intel/ei_backfill_*.py` | One-time backfill/migration scripts |
| `tools/earnings_confirm.py` | Only writer of `date_confirmed` (human + agent) |
| `tools/backfill_earnings_events_derived.py` | Recompute `earnings_events` derived columns (SA P016) |
| `tools/earnings_scenario.py` | Earnings scenario calculator |
| `tools/news_sentiment.py` | Alpha Vantage sentiment (shared with Flow Monitor) |
| `tools/performance_writer.py` | `ei_pipeline_performance` + canonical DDL for date-source/dispute tables |
| `core/finnhub_api.py` | Finnhub client |
| `main_runners.py` | `run_earnings_intelligence()`, `run_earnings_weekly_refresh()` |

---

## Revision History

| Date | Change |
|------|--------|
| 2025-10-10 | Initial Earnings Intelligence system (PRD 0003) |
| 2026-02-10 | Signal recalibration: `relative_underpricing_pct` replaces `move_difference_pct` |
| 2026-02-25 | Phase 0: stale data filter, snapshot collector fix, logging cleanup |
| 2026-02-26 | Phases 1–3 (PRDs 0008–0010): watchlist, Finnhub timing, price-move fallback, signal archival |
| 2026-03-05 | Date source rewire: yfinance primary for dates, Finnhub for timing (`ei_collector.py`) |
| 2026-04-13 | Recent-6Q historical average drives signal; all-time stored alongside |
| 2026-04-14 | Watchlist audit: T+3 outcome columns removed; `vol_balance_text`, `iv_front_month_change_5d` added |
| 2026-04-16 | Straddle-only underpricing; DB-backed symbol lists (PRD 0013) |
| 2026-04-20 | Outcome + signal-accuracy columns on `earnings_events` |
| 2026-04-22 | Archive runs daily, not just Fridays |
| 2026-04-23 | Lite refresh (sub-step 1), date confirmation, dispute table, Earnings Researcher spawn |
| 2026-04-25 | Peak-exit straddle outcome (SA P015); derived-column refresh (SA P016); archive fallback for expected move (TA P003) |
| 2026-04-26 | `expected_move_pct` dropped from upcoming/events/watchlist (SA P017) |
| 2026-05-04 | Snapshot writer populates `event_id` (SA P020) |
| 2026-05-14 | Confirmed-row drift detection (SA P021); event_id backfill sub-step 3.5 + snapshot join-key policy (SA P029) |
| 2026-06-07 | Config switch to disable main.py-launched agents |
| 2026-09-24 | Researcher also spawns when unconfirmed rows are due within 14 days |
| 2026-10-14 | This guide rewritten against current code; absorbed the User Guide, `MANUAL_OPERATIONS.md`, and the autofix EI guide (Section 13). This is now the single technical reference. |
