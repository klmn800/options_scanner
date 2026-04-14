# Flow Monitor Strategy

Real-time options flow monitoring for the KLMN 800 symbol universe. Scans for unusual options activity during market hours, generates alerts, tracks watchlist entries for buy-the-dip opportunities, and runs post-market performance analysis.

**Entry point:** `fm_main.py` (called by `main.py` orchestrator)

---

## Daily Pipeline

Flow Monitor runs three phases each trading day. `main.py` controls timing; FM owns execution.

### Phase 1: Pre-Market (9:15 AM) — ~2-3 minutes

| Step | What happens | Key detail |
|------|-------------|------------|
| Alert Resolution | Resolve yesterday's alerts using today's fresh OI from Option Pipeline | Classifies as BUILDING (opening), CLOSING (exiting), or NEUTRAL. Per-alert details displayed in console (see below). |
| Resolution Sync | Sync resolution updates to query database | Targeted UPDATE of 5 columns — quick-sync's INSERT OR IGNORE skips existing rows |
| Watchlist Sentiment | Update `flow_watchlist_daily` sentiment based on resolutions | Most recent resolution date wins (recency-based) |
| Initialize | Create FMConfig, FMStorage, FMCollector, FMAnalyzer, FMAlerts | Tradier client created here (triggers cache auto-purge) |

Alert resolution requires Option Pipeline to have already run its morning collection (6:35 AM). If no OI data is available, resolution is skipped — not a critical failure.

**Console detail display**: After resolution, each resolved alert is displayed with a 3-line block showing the contract header (symbol, strike, type, expiration, resolution classification, significance score), alert-day snapshot (underlying price, OI, volume, IV, last price), and today's snapshot (underlying price, OI, OI delta, IV, last price). Sorted alphabetically by symbol. Multiple alerts for the same contract are deduped (latest shown, count indicated). The Vol and OI Δ columns share the same position for visual comparison — "was OI delta anywhere near the alert volume?" Display function: `_display_resolution_details()` in `fm_main.py`. Uses `print()`+`log_to_file()` for clean output without per-line timestamps.

**Why Resolution Sync exists**: The alert resolver UPDATEs existing `flow_alerts` rows in `datalake.db` (production). The regular market-hours quick-sync uses `INSERT OR IGNORE`, which only copies *new* rows and skips existing ones — so resolution updates never reach `datalake_query.db`. The targeted resolution sync (`db_backup.py --sync-resolutions`) fixes this by running a surgical UPDATE on the 5 resolution columns (`next_day_oi`, `oi_resolution`, `oi_change_contracts`, `oi_change_pct`, `resolved_at`) for rows that have resolutions in source but not target. Runs in <1 second.

### Phase 2: Market Hours (9:30 AM - 4:00 PM) — continuous loop

The market loop runs continuously — each cycle scans the full ~800 symbol universe, then immediately starts the next. There is no fixed interval; cycle duration depends entirely on API response times and system load.

Each cycle:

1. **Collection** — `fm_collector.py` fetches options chains from Tradier API for ~800 symbols (the bottleneck)
2. **Analysis** — `fm_analyzer.py` calculates premium, volume, OI ratios; scores significance
3. **Alerts** — `fm_alerts.py` generates alerts for flows exceeding threshold
4. **Watchlist** — `fm_watchlist.py` upserts symbol entries, detects dips, sends email notifications (1 per symbol per day, deduplicated via `last_email_date`)
5. **News Sentiment** — When new watchlist entries are created, `tools/news_sentiment.py` enriches them with Alpha Vantage sentiment (inline, not a separate phase)
6. **Quick-Sync** — Syncs new data to query database (non-blocking)

**Cycle timing**: Typically ~20 minutes per full cycle. Can be 12-25 minutes depending on conditions. Faster early morning (fewer chains returned), slower by Friday (larger database). Over 20 minutes is concerning; over 25 minutes is a problem. Ideal is as close to 12 minutes as possible — shorter cycles capture short-lived volume bursts more reliably.

**Cycles per day**: Roughly 20-30 depending on cycle duration (6.5 hours / ~20 min avg).

**What affects cycle speed**: Tradier API response time (primary), database size/lock contention (secondary), number of chains returned per symbol (varies by time of day and market conditions).

### Phase 3: Post-Market (4:30 PM) — ~15-20 minutes

| Task | Module | Duration | Failure severity |
|------|--------|----------|-----------------|
| 1. Historical Backfill | `fm_main.py` → FMP API | 5-8 min | **CRITICAL** — spawns Autofix, exits |
| 2. Market Regime | `fm_main.py` → `market_daily_summary` | 2-3 min | ERROR — queued for batch mode |
| 3. Symbol Rollup | `fm_symbol_rollup.py` | 3-5 min | ERROR — queued for batch mode |
| 4. Daily Evaluation | `evaluation/run_daily_evaluation.py` | 2-3 min | ERROR — queued for batch mode |
| 5. Agent Analysis | `fm_agent.py` (optional, `--run-agent`) | varies | WARNING — non-critical |
| 6. Watchlist Cleanup | `fm_watchlist.py` | <1 min | WARNING — non-critical |

Only backfill failure is critical. Everything else logs an error and continues.

---

## Component Map

| File | Purpose |
|------|---------|
| `fm_main.py` (92 KB) | Orchestrator — `run_pre_market()`, market loop, `run_post_market()` |
| `fm_config.py` | Configuration — loads `config.json`, creates Tradier client, exposes thresholds |
| `fm_collector.py` | Data collection — fetches options chains from Tradier API, stores raw scans |
| `fm_analyzer.py` | Analysis engine — calculates metrics, weighted significance scoring |
| `fm_alerts.py` | Alert generation — threshold filtering, profitability tracking setup |
| `fm_alert_resolver.py` | OI resolution — compares next-day OI to classify BUILDING/CLOSING/NEUTRAL |
| `fm_storage.py` | Database layer — all reads/writes to datalake.db |
| `fm_watchlist.py` | Watchlist — symbol tracking, dip detection, email notifications |
| `fm_symbol_rollup.py` | Post-market — aggregates daily alert metrics into `flow_symbol_summary` |
| `fm_health_reporter.py` | Diagnostics — health checks, status reporting |
| `fm_performance_tracker.py` | Performance — tracks cycle timing, API response times |
| `fm_baseline_generator.py` | Baselines — generates baseline metrics for alert scoring |
| `fm_agent.py` | AI agent — optional Claude-powered alert narrative generation (`--run-agent`) |
| `fm_social_notifier.py` | Social notifications — lazy-loaded by `fm_alerts.py` for external notifications |

### Evaluation Subsystem (`evaluation/`)

Runs daily as post-market Task 4 (~5 PM, called by `fm_main.py` as a subprocess). Tracks alert performance over 30 days with multiple timeframes (1hr, 4hr, 1day, 3day, 7day, 14day, 30day). Assigns quality scores (0-10) and marks alerts complete after 30 days or expiration.

| File | Purpose |
|------|---------|
| `run_daily_evaluation.py` | Entry point — called by `fm_main.py` as subprocess. Handles duplicate prevention, PID tracking. |
| `fm_evaluator.py` (116 KB) | Core evaluation engine — `AlertEvaluator` class. Reads config from `FMConfig`. |
| `fm_backfill_evaluator.py` | Historical backfill for evaluation data |
| `backfill_alert_performance.py` | Backfill runner for recovery/corrections |

**Tables touched**: Reads `flow_alerts`, `option_contracts`, `market_daily_summary`. Updates `flow_alerts` with performance columns (`max_profit_Xday`, `final_quality_score`, `evaluation_status`). Writes to `alert_contract_tracking`.

Evaluation logs are written to `evaluation/logs/` and auto-purged to last 30 days.

---

## Database Tables

### Tables Written During Market Hours

| Table | What | Key columns |
|-------|------|-------------|
| `flow_options_scans` | Raw options data per scan cycle | scan_timestamp, symbol, strike, option_type, volume, open_interest, significance_score |
| `flow_alerts` | Significant flow alerts (above threshold) | symbol, trade_date, strike, option_type, significance_score, volume, open_interest, oi_resolution |
| `flow_watchlist_daily` | Symbol-level daily tracking | symbol, entry_date, entry_ul_price, current_ul_price, price_diff_pct, dip_detected, alert_sentiment, news_sentiment_score |

### Tables Written Post-Market

| Table | What | Written by |
|-------|------|-----------|
| `historical_prices` | Daily OHLCV data (~800 symbols) | Historical backfill (Task 1) |
| `market_daily_summary` | Market regime (Bull/Bear/Neutral) | Market regime (Task 2) |
| `flow_symbol_summary` | Aggregated alert metrics by symbol | Symbol rollup (Task 3) |

### Tables Read

| Table | Why |
|-------|-----|
| `option_contracts` | OI data for alert resolution (from Option Pipeline) |
| `flow_alerts` | Historical alerts for evaluation, resolution lookups |

### Key Behaviors

- **`flow_watchlist_daily`** deduplicates: one entry per symbol per `entry_date`. Multiple alerts for the same symbol on the same day increment `alert_count_today` on the existing entry.
- **Alert resolution** uses fuzzy logic: OI change >= 70% of alert volume → BUILDING or CLOSING. Below threshold → NEUTRAL.
- **Watchlist sentiment** is recency-based: only the most recent resolution date's signals determine the sentiment label.
- **Email dedup**: `last_email_date` column prevents multiple dip notification emails per symbol per day. Resets automatically by date comparison (no manual reset needed).
- **`flow_symbol_summary`** is selectively populated — only symbols with `alert_threshold_met = 1` get rows. No zero-alert padding.

For full column definitions: `python tools/direct_db_query.py --schema <table_name>`
For master schema reference: `data/datalake_schema_2026-01-01.md`

---

## What "Normal" Looks Like

### Market Hours
- **Cycles per day**: ~20-30 (continuous loop, ~20 min per cycle)
- **Cycle time**: 12-25 minutes typical. ~20 min is normal. Over 25 min is a problem.
- **Alerts per day**: Varies widely by market conditions. 50-300 is normal. Zero alerts across multiple cycles = something is broken.
- **Watchlist entries created**: 10-50 new symbols per day typical
- **Scans stored**: Every cycle writes to `flow_options_scans`. If `flow_options_scans` has 0 rows for today after several cycles, collection is failing.

### Post-Market
- **Backfill**: Should complete in 5-8 minutes for ~800 symbols. Failure here is critical.
- **Regime**: Should produce exactly 1 row in `market_daily_summary` for today.
- **Rollup**: Should produce rows in `flow_symbol_summary` for every symbol that had alerts today.
- **Evaluation**: Logs written to `evaluation/logs/daily_evaluation_YYYYMMDD_HHMMSS.log`

### Log Output
Normal startup looks like:
```
🌅 PRE-MARKET PREPARATION - Flow Monitor system ready
   ⚡ Market hours monitoring will begin at 9:30 AM
🔍 TASK 0: Resolving Yesterday's Flow Alerts
   ✅ Resolved 47 alerts (28 BUILDING, 12 CLOSING, 7 NEUTRAL)
```

Normal cycle completion:
```
✅ Cycle 142 complete - Performance Breakdown:
   📊 Collection: 18.2s
   🔍 Analysis: 6.4s
   🚨 Alerts: 3.1s
   🎯 Watchlist: 1.2s
   ⏱️ Total: 28.9s
```

---

## Troubleshooting

### Zero alerts being stored
- **Symptom**: "CRITICAL ERROR: Zero alerts stored" → Autofix spawns
- **Cause**: Usually API issue (Tradier rate limit, network timeout, or API key expiration)
- **Check**: Look at collection logs for API errors. Verify Tradier API key in `config.json`.

### Alert resolution shows "No unresolved alerts from yesterday"
- **Normal if**: No alerts fired yesterday, or resolution already ran today
- **Problem if**: Alerts exist but aren't being found. Check that Option Pipeline ran its morning collection (need fresh OI in `option_contracts` for today's date).

### Watchlist sentiment always NEUTRAL
- **Normal if**: Market is choppy (OI changes below 70% threshold) or system just started (no resolutions yet)
- **Check**: `SELECT COUNT(*) FROM flow_alerts WHERE oi_resolution IS NOT NULL` — if 0, resolutions aren't running

### Cycles exceeding 25 minutes
- **Cause**: Tradier API slow, network issues, or database lock contention (especially Friday with larger DB)
- **Check**: Collection time in cycle breakdown. If collection dominates, it's API latency. If analysis/storage is slow, suspect database locks.

### Backfill failure (CRITICAL)
- **Symptom**: Post-market exits with Autofix spawn
- **Cause**: FMP API down or rate limited
- **Impact**: No fresh price data → regime calculation and evaluation use stale data

### Dip emails not sending
- **Check**: Email credentials in `config.json`, SMTP connectivity
- **Note**: Only first detection per day sends email (dedup via `last_email_date`). Subsequent cycles with same dip are intentionally suppressed.

---

## Cache

Options chain and quote data is cached in `cache/` during market hours to avoid redundant API calls within the same cycle.

**Auto-purge**: Cache files older than 24 hours are automatically deleted when the Tradier client initializes (once per day at FM startup). No manual cleanup needed.

**Directories**:
- `cache/options_chains/` — Options chain JSON files (largest, ~200 MB/day active)
- `cache/quotes/` — Quote data JSON files (~1 MB)

---

## Configuration

All configuration lives in `config.json` (project root), loaded by `fm_config.py`.

Key settings actually used in production:
- **Dip detection thresholds** (`flow_monitor.dip_detection`) — z-score parameters for buy-the-dip alerts (used by `fm_watchlist.py`)
- **Tradier API** (`tradier`) — API key, endpoint (used by `fm_config.py` to create client)
- **Database path** — derived from config file location

---

## Running Standalone

```bash
# Full daemon (called by main.py normally)
python strategies/flow_monitor/fm_main.py --start-daemon --no-interaction

# Test mode with MAG7 only
python strategies/flow_monitor/fm_main.py --test --force --no-interaction
```

In production, always run via `main.py` which handles timing, coordination with Option Pipeline, and market calendar awareness.

---

## Related Documentation

- **System orchestration**: `main.py`, `main_runners.py` — how FM is called
- **Master database schema**: `data/datalake_schema_2026-01-01.md`
- **News sentiment**: `docs/news_sentiment.md` — Alpha Vantage integration details
- **Evaluation guides** (archived): `Deprecated/evaluation_user_guide.md`, `Deprecated/evaluation_troubleshooting.md`
- **Project overview**: `CLAUDE.md` (root) — full system architecture
