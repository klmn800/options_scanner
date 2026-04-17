# PRD 0013: Symbol Lifecycle Management

**Status:** Ready for Review
**Created:** 2026-04-16
**Bundles:** To-do items 3.3 (Delisted Detection), 8.1 (Symbol Onboarding), 8.2 (Symbol Offboarding)
**Brainstorm doc:** `docs/symbol_lifecycle_management/BRAINSTORM.md`

---

## 1. Introduction / Overview

The Options Scanner tracks ~820 symbols across multiple strategies. Today, adding or removing symbols is a manual, multi-step process spanning a Python source file, database tables, backfill scripts, and archive routing configuration. Steps are easy to forget, leading to half-onboarded symbols (missing metadata, wrong archive routing, no earnings history) or ghost data from delisted symbols that no one cleaned up.

This feature creates a **unified symbol lifecycle management system** with three capabilities:

1. **Onboarding** — An interactive CLI tool that walks the user through adding a symbol, performing all data population steps automatically.
2. **Health monitoring** — A daily automated check that detects symbols with missing data and surfaces warnings in the end-of-day report.
3. **Offboarding** — A manual CLI command to stop collection for a symbol, with production data archiving out naturally via existing Friday tiers.

A key architectural change underpins all three: **migrating the symbol universe source of truth** from Python list literals in `core/symbols_klmn800.py` to the `symbol_metadata` database table, enabling programmatic management without editing source code.

---

## 2. Goals

1. **Eliminate half-onboarded symbols.** Every new symbol gets metadata, archive routing, historical prices, earnings history, earnings moves, upcoming earnings, and FM baseline in one operation.
2. **Detect stale symbols automatically.** Symbols with no data for 3+ consecutive trading days appear in the end-of-day report. The user investigates and acts.
3. **Make offboarding a one-command operation.** Stop collection, log the reason, let production data archive out naturally.
4. **Create a queryable audit trail.** Every onboarding, offboarding, and purgatory decision is logged with timestamp, reason, and operator in `symbol_lifecycle_events`.
5. **Migrate universe source of truth to the database.** `symbol_metadata` table gains `universe_tier` and classification columns, replacing hardcoded Python lists. `get_specialty_list()` becomes a thin DB query wrapper.

---

## 3. User Stories

**As Ben, I want to** add a new symbol to the scanner by typing one command, **so that** all data sources are populated correctly without me remembering 8+ manual steps.

**As Ben, I want to** see symbols with missing data highlighted in my end-of-day report, **so that** I catch delisted, acquired, or ticker-changed symbols within a few days instead of discovering them months later during a backfill.

**As Ben, I want to** offboard a dead symbol with one command, **so that** the system stops wasting API calls on it and the reason is logged for future reference.

**As Ben, I want to** see the current state of my universe at a glance (`--list`), **so that** I know which symbols are active, in purgatory, or recently changed.

**As Ben, I want** the symbol universe stored in the database rather than a Python file, **so that** the lifecycle tool can manage it programmatically without fragile source file editing.

---

## 4. Functional Requirements

### 4.1 — Source of Truth Migration

**FR-1.** Add the following columns to `symbol_metadata` in `datalake.db`:
- `universe_tier` (TEXT) — `'fm_universe'`, `'daily_only'`, `'purgatory'`, `'removed'`
- `protected_reason` (TEXT, nullable) — `'airline'`, `'adr'`, `'cherry_pick'`, or NULL. Governs FM tier protection (why a symbol is protected from pruning out of FM_UNIVERSE).
- `is_etf` (INTEGER, DEFAULT 0) — factual flag: 1 for ETFs, 0 otherwise. Separate from `protected_reason` because ETF-ness is a category attribute, not a protection rule. (JETS gets both `protected_reason = 'airline'` AND `is_etf = 1`.)
- `tier_changed_date` (DATE, nullable) — date of last tier change
- `notes` (TEXT, nullable) — free-form notes (e.g., "low liquidity July 2025", "nuclear/defense thematic")

**FR-2.** Write a one-time migration script that populates the new columns from the current Python list data in `core/symbols_klmn800.py`:
- Symbols in `FM_UNIVERSE` list (388) → `universe_tier = 'fm_universe'`
- Symbols in `DAILY_ONLY` list (432) → `universe_tier = 'daily_only'`
- Symbols in purgatory blocks (58) → `universe_tier = 'purgatory'` with appropriate `notes` (e.g., "low liquidity July 2025")
- ADR symbols (74, `KLMN_ADR_COMPONENT`) → `protected_reason = 'adr'`
- Airline symbols (7, `AIRLINE_PLAY_SYMBOLS`) → `protected_reason = 'airline'`
- Cherry picks (14, `FM_CHERRY_PICKS`) → `protected_reason = 'cherry_pick'` with notes from comments
- JETS → `protected_reason = 'airline'` AND `is_etf = 1`
- All 19 `ETF_SYMBOLS` → `is_etf = 1`
- All `tier_changed_date` set to migration date
- Symbols in `symbol_metadata` but NOT in any Python list (e.g., CFLT, URG — ghost metadata) → `universe_tier = 'removed'` with note "not in Python universe at migration time"

**Verification query after migration:**
```sql
-- Must match Python list counts exactly
SELECT universe_tier, COUNT(*) FROM symbol_metadata GROUP BY universe_tier;
-- Expected: fm_universe=388, daily_only=432, purgatory=58, removed=small number
```

**FR-3.** Rewrite `get_specialty_list()` in `core/symbols_klmn800.py` to query `symbol_metadata`:
- `'fm_scan'` → `SELECT symbol FROM symbol_metadata WHERE universe_tier = 'fm_universe'`
- `'klmn_800'` → `SELECT symbol FROM symbol_metadata WHERE universe_tier IN ('fm_universe', 'daily_only')`
- `'airline_play'` → `SELECT symbol FROM symbol_metadata WHERE protected_reason = 'airline'`
- `'etf'` → `SELECT symbol FROM symbol_metadata WHERE is_etf = 1`
- `'adr'` → `SELECT symbol FROM symbol_metadata WHERE protected_reason = 'adr'`
- Function signature and return type remain the same (returns list of symbol strings)
- The file stays at `core/symbols_klmn800.py` to preserve all existing import paths
- Remove the hardcoded Python list literals once migration is verified

**FR-4.** `get_specialty_list()` must accept an optional `db_path` parameter. Default behavior: connect to `data/datalake.db` (production). All existing callers that don't pass a path continue working unchanged.

**FR-5.** Existing direct imports of list constants must be replaced with `get_specialty_list()` calls:
- `KLMN_800_SYMBOLS` → `get_specialty_list('klmn_800')` in `oracle/oracle_config.py` (line 596), `oracle/oracle_vanna.py` (line 157)
- `ETF_SYMBOLS` → `get_specialty_list('etf')` in `strategies/earnings_intel/ei_collector.py` (line 45, used for `ETF_EXCLUSIONS`), `strategies/earnings_intel/ei_backfill_dec_feb.py` (line 44)
- `KLMN_ADR_COMPONENT` is only used via `get_specialty_list('klmn_adr')` already — no change needed

### 4.2 — Audit Trail Table

**FR-6.** Create table `symbol_lifecycle_events` in `datalake.db`:

| Column | Type | Constraints |
|---|---|---|
| event_id | INTEGER | PRIMARY KEY AUTOINCREMENT |
| symbol | TEXT NOT NULL | Indexed |
| event_type | TEXT NOT NULL | Controlled vocab (see below) |
| event_date | DATE NOT NULL | Trading day of event |
| event_timestamp | TEXT NOT NULL | ISO timestamp |
| tier | TEXT | Universe tier at time of event |
| reason | TEXT | Free-form explanation |
| operator | TEXT NOT NULL | `'human'` or `'system'` |
| metadata_json | TEXT | JSON blob with full context |

Event types: `onboarded`, `offboarded`, `purgatory_added`, `purgatory_restored`, `suspect_detected`, `tier_changed`

### 4.3 — Interactive CLI Tool

**FR-7.** Create `tools/symbol_lifecycle.py` as the primary entry point with the following subcommands:

#### `--add SYMBOL` (Onboarding)

**FR-8.** On `--add SYMBOL`, the tool must perform the following steps in order:

1. **Fetch symbol info from Tradier** — call `get_quotes([SYMBOL])` for price, volume; call option chain expirations endpoint to verify optionability; fetch company fundamentals for sector/industry/market cap.

2. **Display symbol card** — show name, sector, industry, market cap, avg volume, last price, optionability status, and last earnings date (if available from Tradier calendars).

3. **Run pre-flight checks** with warn-and-continue behavior:
   - Optionable (has listed options)
   - Liquidity tier (warn if avg volume < 100K — "same bucket as purgatory symbols")
   - Not already in universe (`symbol_metadata.universe_tier` not in `fm_universe`/`daily_only`)
   - Sector resolvable to an archive DB
   - Earnings data available from Tradier calendars

4. **Prompt: "Add to system? [Y/n]"**

5. **Prompt: Tier assignment** — `[1] FM_UNIVERSE` or `[2] DAILY_ONLY`

6. **Display and confirm archive routing** — determine archive DB from sector/industry using the same routing logic as `db_archive_sector.py`. Show the proposed routing. Allow override if user wants a different archive.

7. **Execute onboarding steps**, trying all steps regardless of individual failures:
   - Insert/update `symbol_metadata` row with all fields including `universe_tier`, `protected_reason` (prompt if applicable), `archive_db`, `tier_changed_date`
   - Backfill `historical_prices` (~1 year) via Tradier historical endpoint (same logic as `data/tradier_historical_backfill.py`)
   - Backfill `earnings_events` via Tradier calendars endpoint (same logic as `data/health/backfill_earnings_tradier.py`)
   - Compute `earnings_moves` from backfilled events and prices (same logic as `ei_post_earnings_calc.py`)
   - Populate `earnings_upcoming` with next earnings date
   - Generate FM baseline via `fm_baseline_generator.generate_baselines(symbols=[SYMBOL])` (only if tier is `fm_universe`)
   - Log `onboarded` event to `symbol_lifecycle_events`

8. **Print summary** — show each step with done/failed/skipped status and row counts. If any steps failed, warn the user that the system will naturally fill gaps on subsequent collection cycles.

**FR-9.** Create a `determine_archive_db(sector, industry)` function that encodes the current routing rules. The archiver (`db_archive_sector.py`) reads `archive_db` from `symbol_metadata` at runtime — it does NOT compute routing. So the onboarding tool must set `archive_db` correctly at insert time. The routing rules (derived from current data):

**Technology sector splits (by industry):**
- Semiconductors, Semiconductor Equipment & Materials → `'semiconductors'`
- Software - Application, Software - Infrastructure → `'software'`
- All other Technology industries → `'technology'`

**Consumer Cyclical sector splits (by industry):**
- Apparel Retail/Footwear, Department Stores, Home Improvement, Internet Retail, Luxury Goods, Specialty Retail → `'retail'`
- Gambling/Casinos, Leisure, Restaurants, Travel Lodging, Travel Services → `'travel_leisure'`
- All other Consumer Cyclical industries → `'consumer_cyclical'`

**Special industry-based routing (overrides sector):**
- Industry = Airlines → `'airlines'`
- Industry = Asset Management → `'asset_management'`

**Ambiguous cases requiring user confirmation:**
- Aerospace & Defense maps to BOTH `'defense'` and `'nuclear'` (5 symbols in nuclear, 3 in defense). The function should suggest the most common mapping and present the override prompt.
- Uranium → `'nuclear'` (special case, cross-sector)
- ETFs → varies by theme (JETS→airlines, sector ETFs→asset_management). Always show archive routing for user confirmation.

**Default:** lowercase sector name (e.g., `'Financial Services'` → `'financial_services'`, `'Energy'` → `'energy'`).

The UX already includes "Confirm archive routing: X.db? [Y/change]" so the user always has override capability for edge cases.

#### `--offboard SYMBOL` (Offboarding)

**FR-10.** On `--offboard SYMBOL`, the tool must:
1. Confirm the symbol exists in the universe (`universe_tier` in `fm_universe`/`daily_only`)
2. Prompt for reason (free text, e.g., "delisted", "acquired by Danaher", "ticker change to AER")
3. Update `symbol_metadata`: set `universe_tier = 'purgatory'`, update `tier_changed_date`
4. Delete any row in `earnings_upcoming` for this symbol (stale future date, safe cleanup)
5. Log `offboarded` event to `symbol_lifecycle_events` with reason
6. Print confirmation: "SYMBOL moved to purgatory. Collection will stop on next cycle. Production data will archive out naturally via Friday tiers."

**FR-11.** No data deletion from production tables (`option_contracts`, `flow_options_scans`, etc.). Production data migrates to sector archives via the existing Friday archive tiers (15d/30d/90d MOVE operations). Archives keep data forever.

#### `--restore SYMBOL` (Restore from Purgatory)

**FR-12.** On `--restore SYMBOL`:
1. Confirm the symbol is in purgatory (`universe_tier = 'purgatory'`)
2. Prompt for tier: FM_UNIVERSE or DAILY_ONLY
3. Update `symbol_metadata`: set `universe_tier`, update `tier_changed_date`
4. Log `purgatory_restored` event
5. Print confirmation

#### `--list` (Universe Dashboard)

**FR-13.** On `--list`, display a summary dashboard:
- Count by tier: FM_UNIVERSE (N), DAILY_ONLY (N), Purgatory (N), Removed (N)
- Recently onboarded (last 30 days, from lifecycle events)
- Recently offboarded (last 30 days, from lifecycle events)
- Symbols currently flagged by health check (suspect_detected events with no resolution)
- Purgatory residents with dates and reasons

#### `--review` (Review Pending Actions)

**FR-14.** On `--review`, show symbols with pending lifecycle actions:
- Symbols flagged by health check (no data 5+ days) that haven't been offboarded or restored
- For each, show: symbol, days without data, last data date, sector
- Allow user to select and take action (offboard, restore, dismiss)

### 4.4 — Symbol Health Check (Phase 6.2)

**FR-15.** Add a new step to the orchestrator's Phase 6 (System Maintenance) that runs after performance data collection:

1. Query `option_contracts` to find symbols in the active universe that have no data for the last N trading days
2. Safety gate: if fewer than 90% of universe symbols have data for the most recent trading day, skip the check entirely and log "Collection success rate below threshold — skipping symbol health check (possible API issue)"
3. For symbols missing 3-4 consecutive trading days: **early warning** — include in report only
4. For symbols missing 5+ consecutive trading days: **suspect** — log `suspect_detected` event to `symbol_lifecycle_events` (if not already logged for this symbol) and include in report

**FR-16.** The health check query should derive missing data from absence of rows in `option_contracts`, NOT from tracking failure counters. No new columns or tracking tables needed.

**FR-17.** The health check must be idempotent — running it multiple times on the same day produces the same results and does not create duplicate lifecycle events.

### 4.5 — End-of-Day Report Integration

**FR-18.** Add a "Symbol Health" section to the end-of-day market report (generated in `main_runners.py` post-market). This section appears only when there is something to report. Content:

```
Symbol Health
  Warnings (3-4 days no data):
    ACME  — no data 3 of last 5 trading days (last: 2026-04-11)
  Suspects (5+ days no data):
    XYZ   — no data 5 consecutive days (last: 2026-04-09) [flagged]
  Recent changes:
    NEWCO — onboarded 2026-04-15 (fm_universe)
    SEE   — offboarded 2026-04-12 (delisted)
```

If nothing to report, the section is omitted entirely (no empty section).

### 4.6 — Collector Integration

**FR-19.** OP and FM collectors must respect the `universe_tier` column when fetching symbol lists. Symbols with `universe_tier = 'purgatory'` or `universe_tier = 'removed'` are excluded from collection. This happens naturally once `get_specialty_list()` queries the DB (FR-3).

**FR-20.** No changes to collector error handling or failure tracking logic. Detection is handled entirely by the Phase 6.2 health check (FR-15).

---

## 5. Non-Goals (Out of Scope)

- **Peer mapping algorithm** — no `industry_peer_mappings` updates during onboarding. Separate future item.
- **Ticker change auto-rewrite** — no rewriting of `symbol` columns in historical data. V1 handles ticker changes as manual offboard + onboard with linked lifecycle events.
- **Batch/CSV onboarding** — interactive only. No `--symbols A,B,C` mode.
- **Automated discovery** — onboarding is always human-initiated. Automated discovery tracked as to-do item 8.3.
- **Morning View TUI integration** — no lifecycle screen in TUI. Deferred.
- **Autofix integration** — no automated web research or autofix handler for delisted suspects. Detection + notification only; user investigates manually.
- **Automated offboarding** — health check flags only, does not auto-move to purgatory. User decides.
- **Data purge workflow** — no manual purge commands. Production data archives naturally via Friday tiers.

---

## 6. Design Considerations

### CLI UX Pattern
The interactive prompts use simple `[Y/n]` and numbered-choice patterns consistent with the system's existing CLI tools. No TUI frameworks (Textual, Rich prompts) — just `input()` with formatted output using `tools/log_utils.py` for console formatting.

### Archive Routing
The archiver (`db_archive_sector.py`) does NOT compute routing at runtime — it reads the pre-set `archive_db` column from `symbol_metadata`. The lifecycle tool must set this column correctly at onboarding time. A new `determine_archive_db(sector, industry)` function (see FR-9) encodes the mapping rules. This function lives in the lifecycle package (`tools/lifecycle/routing.py`) and is the single place these rules are defined.

### Onboarding Step Resilience
Each onboarding step runs independently. If step 3 (price backfill) fails, step 4 (earnings backfill) still runs. The summary shows which steps succeeded and which failed. The system's normal collection cycles (OP, EI, FM) will naturally fill most gaps on subsequent runs.

---

## 7. Technical Considerations

### Database Changes
- **ALTER TABLE `symbol_metadata`**: Add 5 columns (`universe_tier`, `protected_reason`, `is_etf`, `tier_changed_date`, `notes`). Migration auto-runs on first use.
- **CREATE TABLE `symbol_lifecycle_events`**: New table in `datalake.db`. Created by lifecycle tool on first use.
- Both changes use the same `_ensure_schema` pattern (ALTER TABLE with try/except for "duplicate column") used throughout the codebase.

### Existing Tool Reuse
Several onboarding steps call existing code rather than reimplementing:
- `data/tradier_historical_backfill.py` logic for price backfill
- `data/health/backfill_earnings_tradier.py` logic for earnings events
- `strategies/earnings_intel/ei_post_earnings_calc.py` logic for earnings moves
- `strategies/flow_monitor/fm_baseline_generator.py` for baseline generation
- `core/tradier_api.py` for all Tradier API calls

Import the functions/classes directly. Do not shell out to scripts via subprocess.

### Migration Safety
The source-of-truth migration (Python lists → DB) should be done in stages:
1. Add columns + populate from Python data
2. Verify: query results match Python list outputs for all specialty lists
3. Switch `get_specialty_list()` to read from DB
4. Run a full trading day to verify all strategies work correctly
5. Only then remove the Python list literals

### Performance
DB query for symbol list: ~0.57ms (benchmarked). Python import: ~0.02ms. Called once per strategy startup, not in hot loops. No performance concern.

### Integration Points (files modified)
- `core/symbols_klmn800.py` — rewrite `get_specialty_list()` to query DB, remove list constants
- `data/symbol_metadata.py` — add new columns, add routing helper
- `oracle/oracle_config.py`, `oracle/oracle_vanna.py` — replace `KLMN_800_SYMBOLS` import
- `strategies/earnings_intel/ei_collector.py`, `ei_backfill_dec_feb.py` — replace `ETF_SYMBOLS` import
- `main_runners.py` — add Phase 6.2 health check + end-of-day report section
- `strategies/flow_monitor/fm_collector.py` — `get_symbols_klmn800()` wrapper imports `get_specialty_list` without `core.` prefix and falls back to MAG7. No changes needed — the wrapper works as-is once `get_specialty_list()` is rewritten, since the import path and function signature are unchanged. The MAG7 fallback is a safety net that shouldn't trigger in normal operation.

### New Files
- `tools/symbol_lifecycle.py` — CLI entry point
- `tools/lifecycle/` — package with modules: `onboarding.py`, `offboarding.py`, `preflight.py`, `routing.py`, `audit.py`, `health_check.py`, `ui.py`

---

## 8. Success Metrics

1. **Onboarding completeness**: Running `--add SYMBOL` successfully populates all 7 data sources (metadata, prices, earnings events, earnings moves, earnings upcoming, baseline, lifecycle event) in a single invocation.
2. **Detection coverage**: Health check correctly identifies symbols with no `option_contracts` data for 3+ and 5+ consecutive trading days, with zero false positives when Tradier has an outage (90% gate works).
3. **Audit trail**: Every onboarding, offboarding, purgatory, and restore action has a corresponding row in `symbol_lifecycle_events`.
4. **Migration parity**: After source-of-truth migration, `get_specialty_list()` returns identical symbol lists from DB as from the old Python lists for all specialty list names.
5. **Zero regressions**: All strategies (OP, FM, EI, AP) continue to function correctly with DB-sourced symbol lists.

---

## 9. Resolved Investigation Notes

These were open questions during drafting, now resolved via codebase research:

1. **ETF classification in DB**: ETFs have `sector = 'N/A'` and `industry = 'N/A'` in `symbol_metadata`, but so do 2-3 non-ETF symbols (CFLT ghost, FOXA). Cannot use sector as proxy. **Solution:** dedicated `is_etf` column (INTEGER DEFAULT 0). The 19 `ETF_SYMBOLS` + JETS get `is_etf = 1`. `get_specialty_list('etf')` queries `WHERE is_etf = 1`. `protected_reason` remains separate (governs FM tier protection, not ETF categorization).

2. **Archive routing**: The archiver (`db_archive_sector.py`) does NOT compute routing — it reads `archive_db` from `symbol_metadata` at runtime via `get_symbol_archive_db()`. No extraction needed. The lifecycle tool sets `archive_db` at onboarding time using a new `determine_archive_db(sector, industry)` function. Full routing rules documented in FR-9, derived from current data across all 818 symbols and 19 archive databases. One ambiguity: Aerospace & Defense industry maps to both 'defense' (3 symbols) and 'nuclear' (5 symbols) — handled via user confirmation prompt.

3. **FM collector wrapper**: `fm_collector.py:get_symbols_klmn800()` imports `from symbols_klmn800 import get_specialty_list` (no `core.` prefix) and falls back to MAG7 on ImportError. No changes needed — the import path and function signature are unchanged after migration. The MAG7 fallback is a safety net for edge cases (e.g., running collector standalone outside project root).
