# Option Pipeline Strategy

Collects options chain data from the Tradier API for the full KLMN 800 symbol universe, calculates Greeks, IV, and contract-level metrics, then aggregates everything into symbol-level summaries. Runs twice daily -- morning (pre-market OI snapshot) and evening (full-day data with volume). Evening data overwrites morning data.

Formerly called "OID" (Open Interest Delta). Renamed October 2025; class names still use the `OID*` prefix.

---

## Files

| File | Class | Responsibility |
|------|-------|---------------|
| `op_main.py` | `OIDOrchestrator` | Pipeline orchestrator. Runs 5 phases sequentially, handles error routing to autofix, generates diagnostic logs. |
| `op_collector.py` | `OIDCollector` | Fetches options chains from Tradier API. Bulk quote optimization (batches of 100 symbols), strike filtering, Greek calculation, contract buffering. |
| `op_storage.py` | `OIDStorage` | Database layer. Creates tables, handles INSERT OR REPLACE with retry logic, calculates time-series metrics (OI momentum, IV changes, volume ratios, build patterns). |
| `op_symbol_rollup.py` | `OIDSymbolRollup` | Aggregates contract data into per-symbol summaries: IV by DTE bucket, Greek exposures, max pain, put/call ratios, moneyness distribution, realized volatility. |
| `op_timing_calculator.py` | `OITimingCalculator` | Smart money detection. Finds when OI first hit 50% of current level, looks up stock price at that date. Updates `oi_build_start_date` and `oi_build_start_price` on contracts with OI > 1000. |
| `op_health_reporter.py` | `OIDHealthReporter` | Generates health report files to `logs/`. Extends `BaseHealthReporter` for memory/API tracking. No database queries -- purely formats data passed from the orchestrator. |
| `op_config.py` | `OIDConfig` | Loads config from `config.json` section `open_interest_delta`. Initializes Tradier client. Provides collection/storage parameters. Creates `cache/` directory on init. |

---

## How It Gets Called

`main_runners.py` calls Option Pipeline directly (in-process, not subprocess):

```python
from strategies.option_pipeline.op_main import OIDOrchestrator

op = OIDOrchestrator(no_interaction=True)
results = op.run_pipeline(trade_date=eastern_date_string(), symbol=None, skip_rollup=False)
```

**Both morning and evening calls pass identical arguments.** The pipeline has no time-of-day awareness -- it collects whatever Tradier returns at the moment of execution. The morning/evening distinction is purely contextual: before market open you get overnight OI; after close you get end-of-day data with volume.

### Schedule

| Run | Method | Approximate Time | Key Difference |
|-----|--------|-----------------|----------------|
| Morning | `run_morning_option_pipeline()` | 6:35 AM ET | Pre-market: OI without volume |
| Evening | `run_evening_option_pipeline()` | ~5:00-5:30 PM ET (after Flow Monitor) | Post-market: OI + volume. Overwrites morning data. |

- Morning is **skipped** if the orchestrator starts after 8:45 AM.
- Evening has a 60-second pause before starting.

### Error Handling Asymmetry

| Scenario | Morning | Evening |
|----------|---------|---------|
| Pipeline failure | CRITICAL -- autofix spawns, process exits | Logs warning, returns False |
| Unhandled exception | CRITICAL -- autofix spawns, process exits | Queues error for batch review, returns False |
| Blocks subsequent steps? | Yes (process exits) | No (pipeline continues to sync) |

Morning failures are treated as fatal because the system needs OI data to function. Evening failures are non-blocking because morning data already exists.

---

## Pipeline Phases

### Phase 1: Collection (~90-120 min)

**Module:** `op_collector.py`

1. Load KLMN 800 symbol list
2. Fetch bulk quotes in batches of 100 symbols (one API call per batch)
3. For each symbol: fetch expirations (1 API call), then fetch chain per expiration (1 API call each)
4. Filter strikes to +/-20% of current price **unioned with sticky contracts** (see Sticky Contract Preservation below)
5. Filter expirations to max 60 DTE
6. Buffer contracts, flush to database in batches

**API calls per symbol:** 1 (expirations) + N (one per valid expiration). Bulk quotes amortized across batches.

**Writes to:** `option_contracts` via `INSERT OR REPLACE` on primary key `(contract_hash, trade_date)`.

During insert, `op_storage.py` calculates time-series metrics by looking up prior rows for the same `contract_hash`:
- OI changes: 1d, 5d, 10d (absolute and percentage)
- OI momentum (5-day)
- IV changes: 1d, 5d, 20d (absolute and percentage), averages, momentum
- Volume ratios: 5d, 20d (capped at 100x, minimum avg volume of 10 for ratio calculation)
- Greek changes and momentum: delta, gamma, theta, vega
- Build pattern: "sudden" (>20% 1d OI change), "gradual" (positive <20%), "unwinding" (<-20% 1d), "stable"
- Building/unwinding direction: >10% = BUILDING, <-10% = UNWINDING, else STABLE

**Note:** `oi_build_start_date` and `oi_build_start_price` are NOT populated during collection. They are always NULL until Phase 4 (Timing) runs.

#### Sticky Contract Preservation (added 2026-05-20)

Before the strike-range filter runs, `collect_symbol_oi()` queries `option_contracts` for distinct `(strike, expiration_date, option_type)` tuples for the symbol where `expiration_date >= today`. The filter keeps any chain option whose key is in that sticky set, **even if its strike falls outside the ±20% band**.

Rationale: when a symbol moves >10%, a contract that was ATM yesterday can drift outside the band today and silently disappear from `option_contracts`. The sticky union preserves data continuity on contracts we already track, until they expire. Self-bounding — the sticky set only grows on symbols already experiencing enough movement to surface new strikes.

- Helper: `_get_sticky_contracts(symbol)` (one query per symbol, no cache)
- Filter: `_filter_strikes_by_range(options, underlying_price, expiration=, sticky_set=)`
- Case: `option_contracts.option_type` is UPPERCASE, Tradier returns lowercase — both normalized to lowercase for the sticky key
- Forward-looking only — contracts dropped before 2026-05-20 are not recovered

### Phase 2: Analysis (DEPRECATED -- skipped)

Formerly calculated gap-from-maximum and momentum. Now skipped entirely -- `build_pattern` is calculated inline during the Phase 1 storage insert.

### Phase 3: Symbol Rollup (~10-15 min)

**Module:** `op_symbol_rollup.py`

Aggregates all contracts for each symbol on the given trade_date into a single summary row. Processes in batches of 100 symbols (for progress logging), then bulk-inserts all summaries at once.

**Writes to:** `option_symbol_summary` via `INSERT OR REPLACE` on primary key `(symbol, trade_date)`.

**What it computes (95 columns):**

| Category | Key Metrics |
|----------|------------|
| Core OI | `total_open_interest`, `total_call_oi`, `total_put_oi`, `put_call_ratio` |
| OI Balance | `oi_balance_text`: "Clear Call Bias" / "Heavy Call" / "Balanced" / "Leans Put" / "Heavy Put" / "Clear Put Bias" |
| Concentration | Top call/put strikes by OI (strike, expiration, OI, % of total, display string) |
| Activity | `building_contracts_count`, `unwinding_contracts_count` (based on `oi_momentum_5d`) |
| OI by Time Horizon | 4 DTE buckets (0-7, 8-21, 22-35, 36-60) x combined/call/put x absolute/percent = 24 columns |
| Max Pain | `max_pain_by_friday` -- strike minimizing total intrinsic value for **nearest expiration only** |
| Volume | `option_volume`, `call_volume`, `put_volume`, `volume_put_call_ratio` |
| IV | `call_iv_avg`, `put_iv_avg`, `iv_skew`, OI-weighted IV, `symbol_iv_percentile_30d` |
| IV by DTE | `iv_front_month` (0-21), `iv_30dte` (22-35), `iv_45dte` (36-50), `iv_60dte` (51-70) |
| Greek Exposures | Delta/gamma/theta/vega exposure = greek * OI * 100. Net exposures, max gamma strike. |
| Moneyness Distribution | 5 categories (DEEP_ITM, ITM, ATM, OTM, DEEP_OTM) x call/put x absolute/percent = 20 columns |
| Realized Volatility | `rv_5d`, `rv_10d` via `tools/realized_volatility.py` |
| Quality | `avg_bid_ask_spread_pct` |

**Note on DTE bucket differences:** IV-by-DTE and OI-by-time-horizon use different ranges intentionally. OI distribution caps at 60 DTE (matching collection filter); IV buckets extend to 70 DTE for the 60dte bucket.

### Phase 4: OI Timing (~5-10 min)

**Module:** `op_timing_calculator.py`

Runs in **both** morning and evening (despite some docs claiming evening-only).

1. Query all contracts with OI > 1000 for the trade date
2. For each: look at full time series for that `contract_hash`
3. Find first date when OI >= 50% of current level
4. Look up stock price on that date from `historical_prices`
5. Update `oi_build_start_date` and `oi_build_start_price` on the contract row

### Phase 5: Health Report (~2-3 min)

**Module:** `op_health_reporter.py`

1. Runs comprehensive pipeline health check (queries `option_contracts` and `option_symbol_summary` for coverage stats)
2. Determines health status: HEALTHY (>95% coverage), DEGRADED (85-95%), CRITICAL (<85%)
3. Writes report to `logs/option_pipeline_health_{date}.txt`
4. Writes diagnostic summary to `logs/diagnostic/option_pipeline_{date}.log`

---

## Database Operations

### Tables Written

| Table | Primary Key | Columns | Write Method |
|-------|-------------|---------|-------------|
| `option_contracts` | `(contract_hash, trade_date)` | 66 | `INSERT OR REPLACE` (evening overwrites morning for same key) |
| `option_symbol_summary` | `(symbol, trade_date)` | 95 | `INSERT OR REPLACE` (evening overwrites morning for same key) |

### Tables Read

| Table | Used By | Purpose |
|-------|---------|---------|
| `option_contracts` | op_storage.py, op_timing_calculator.py | Time-series lookback for prior contract data, timing analysis |
| `historical_prices` | op_timing_calculator.py, op_symbol_rollup.py | Stock price at OI build date, realized volatility calculation |
| `symbol_metadata` | op_collector.py (via KLMN 800) | Symbol universe |

### Connection Settings

- WAL mode, 30-second busy timeout
- Retry on "database is locked": 3 attempts with 0.1s/0.2s/0.3s backoff
- Auto-commit via Python `with conn` context manager

---

## Normal Operation

### What Good Looks Like

| Metric | Expected Range | Notes |
|--------|---------------|-------|
| Symbols collected | 780-810 | Full KLMN 800. Some symbols may have no options. |
| Failed symbols | 0-20 | Usually delisted tickers or API timeouts. <5 is typical. |
| Total contracts | 50,000-100,000 | Varies by market conditions and expiration calendar. |
| Collection time | 90-120 min | Sequential API calls, ~800 symbols. |
| Rollup summaries | ~800 | One per symbol per day (universal coverage). |
| Rollup time | 10-15 min | Batch processing with single bulk insert. |
| Timing contracts updated | Varies | Only contracts with OI > 1000 and sufficient history. |
| Health status | HEALTHY | >95% symbol coverage. |
| Total pipeline time | ~2 hours | Both morning and evening runs. |

### Health Thresholds

| Status | Coverage | Meaning |
|--------|----------|---------|
| HEALTHY | > 95% | Normal operation |
| DEGRADED | 85-95% | Elevated failures, investigate API issues |
| CRITICAL | < 85% | Serious problem, likely API outage or config issue |

---

## Warning Signs & Troubleshooting

### Zero Contracts Stored (CRITICAL)

**Symptom:** Collection reports 0 total contracts despite making API calls.
**Autofix:** Spawns immediately, process exits with `sys.exit(1)`.
**Common causes:** Tradier API key expired, API outage, network issues, config file corrupted.
**Check:** Verify `config.json` has valid `tradier.api_key`. Test with `python op_config.py` from the strategy directory.

### High Symbol Failure Rate (>20 symbols)

**Symptom:** `failed_symbols` count significantly above typical 0-5 range.
**Common causes:** API rate limiting (120 calls/min limit), Tradier maintenance window, symbol delistings.
**Not a concern if:** Failed symbols are delisted tickers or very small-cap stocks with no options.

### Rollup or Timing Phase Failure

**Symptom:** Phase completes with error, queued to autofix batch mode.
**Impact:** Non-blocking -- collection data is already stored. Summaries may be missing for that day.
**Recovery:** Can re-run manually: `python op_main.py --no-interaction` (will overwrite existing data via INSERT OR REPLACE).

### Low Contract Count (<30,000)

**Symptom:** Contracts collected well below the 50K-100K range.
**Common causes:** Running before options data is available (too early), holiday-shortened trading week, API returning stale data.
**Check:** Verify the market was open that day. Check Tradier API status.

### Pipeline Running Longer Than 3 Hours

**Symptom:** Collection exceeds 180 minutes.
**Common causes:** API throttling, network latency, very busy expiration week (more contracts per symbol).
**Not a concern if:** Collection is completing successfully, just slowly.

---

## Configuration

Config lives in `config.json` under the `open_interest_delta` section:

```json
{
  "open_interest_delta": {
    "enabled": true,
    "collection_time": "18:00",
    "collection_params": {
      "max_dte": 60,
      "min_dte": 0,
      "strike_range_percent": 20,
      "batch_size": 100,
      "rollup_batch_size": 100,
      "storage_batch_size": 5000,
      "rate_limit_per_minute": 120
    },
    "storage": {
      "retention_days": 365,
      "compression_after_days": 30
    }
  }
}
```

| Parameter | Default | What It Controls |
|-----------|---------|-----------------|
| `max_dte` | 60 | Maximum days to expiration collected |
| `strike_range_percent` | 20 | +/-20% from underlying price |
| `batch_size` | 100 | Contract buffer flush threshold during collection |
| `rollup_batch_size` | 100 | Symbols processed per progress-logging batch |
| `storage_batch_size` | 5000 | Contracts per database INSERT batch |
| `rate_limit_per_minute` | 120 | Tradier API rate limit |
| `retention_days` | 365 | Days before old data cleanup |

---

## Consumers

These systems read data produced by Option Pipeline:

| Consumer | Table Used | What For |
|----------|-----------|---------|
| **Earnings Intelligence** | `option_symbol_summary` | IV metrics (front month, 30/45/60 DTE) for earnings analysis |
| **Morning View TUI** | `option_contracts`, `option_symbol_summary` | Symbol detail display, contract-level browsing |
| **Oracle AI** | `option_symbol_summary` | AI-powered market analysis queries |
| **Sector Archives** | Both tables | Friday night archival to `data/sector_archive/{sector}.db` (Tier 2: 30-day MOVE) |
| **Analysis tools** | Both tables | Volume profile, technical levels, ad-hoc queries |

---

## Notes for Maintainers

- **Legacy class names:** All classes use `OID*` prefix (OIDConfig, OIDStorage, etc.). This is cosmetic -- renaming them would require touching every import across the codebase. Not worth it.
- **`cache/` directory:** Auto-created by `OIDConfig.__init__()` for the Tradier client. Starts empty, populated during collection. Safe to delete anytime -- regenerated automatically.
- **Single-insert path is unused:** `op_storage.py` has both `insert_oi_snapshot()` (single record) and `bulk_insert_oi_snapshots()` (batch). Only the bulk path is called in production. The single-insert path has a column/value alignment issue and would likely error if called.
- **Decimal formatting:** Applied at two levels -- individual formatters during INSERT value construction (op_storage.py) and `clean_database_row()` safety net on symbol summaries. Uses `tools/decimal_formatter.py`.
- **Diagnostic vs operational logs:** Main log goes to `logs/option_pipeline_{date}.log`. Diagnostic summary (high-level one-liners) goes to `logs/diagnostic/option_pipeline_{date}.log`. Health report goes to `logs/option_pipeline_health_{date}.txt`.
