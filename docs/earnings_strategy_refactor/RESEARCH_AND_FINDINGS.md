# Earnings Intelligence Refactor — Research & Findings

**Started**: 2026-02-23
**Status**: Research Phase — collecting information, auditing data, defining goals
**Goal**: Make the Earnings Intelligence system actually useful for making money

---

## Table of Contents

1. [What We Want](#what-we-want)
2. [System Inventory](#system-inventory)
3. [Data Quality Audit](#data-quality-audit)
4. [Component Analysis](#component-analysis)
5. [Existing Strategy Docs](#existing-strategy-docs)
6. [Problems to Solve](#problems-to-solve)
7. [Design Decisions & Open Questions](#design-decisions--open-questions)
8. [Implementation Plan](#implementation-plan)
9. [Session Log](#session-log)

---

## What We Want

The earnings system should answer one question every morning: **"Which upcoming earnings events should I act on today, and what exactly should I do?"**

Concretely:
- Know which stocks have earnings in the next 1-7 days
- Know which ones the market is underpricing (the straddle play from EARNINGS_STRADDLE_PLAYBOOK.md)
- Know BMO vs AMC so timing makes sense
- Have confidence the data is complete and current
- Get this information surfaced in the morning when I can act on it, not at 5 PM when I'm making dinner
- Track outcomes to validate and calibrate the system over time

---

## System Inventory

### Active Components (what runs today)

| Step | When | What | File(s) | Status |
|------|------|------|---------|--------|
| **1.2 Arbitrage Scanner** | 6:35 AM (Pre-Market) | Scans for sector sympathy plays on today's earnings | `ei_arbitrage_scanner.py` | **Dead** — `earnings_sector_effects` is empty (0 rows), so correlation = 0 for everything. Also only looks at "today" which is too late. |
| **3.3 Earnings Pipeline** | ~5:30 PM (Evening) | 3-task pipeline: snapshots, post-earnings calcs, expected moves + alerts | `ei_main.py` → `ei_snapshot_collector.py`, `ei_post_earnings_calc.py`, `ei_moves_upcoming.py` | **Running** — produces signals and alerts. But alerts display at 5 PM and aren't persisted in a morning-accessible way. Has stale data bug. |
| **5.2 Weekly Refresh** | Friday evening | Fetches next 90 days of earnings from YFinance for all 800 symbols | `ei_fetch_upcoming.py` | **Running** — but all `earnings_time` is "Unknown" (YFinance limitation). 404 errors suppressed. No completeness reporting. |
| **Thursday Scheduled Task** | Thursday 8 PM | `run_yfinance_earnings_upcoming.bat` | `scheduled_tasks/run_yfinance_earnings_upcoming.bat` | **BROKEN** — calls `python -m data.yfinance_earnings_upcoming` which doesn't exist. Silent failure every week since Oct 2025. |

### Database Tables

| Table | Rows | Status | Notes |
|-------|------|--------|-------|
| `earnings_upcoming` | 613 | Has stale rows | PK: symbol. One row per symbol. Updated daily by pipeline (signals/alerts) and weekly by refresh (dates). |
| `earnings_events` | 187 | OK | Historical archive. ~3 months (Nov 2025 - Feb 2026). Has trading journal columns (notes, tags, sentiment). |
| `earnings_moves` | 9,323 | Good | Historical move calculations. ~4.5 months. Source of `historical_avg_move_pct`. |
| `earnings_sector_effects` | **0** | Empty | Needs correlation history before arbitrage scanner can work. Chicken-and-egg problem. |
| `earnings_snapshots` | ~0 | Empty | Known issue — snapshot collector queries `earnings_events` (post-hoc only). Separate fix needed. |
| `industry_peer_mappings` | 742 | OK | Reference data for peer relationships. |

### Related Existing Documents

| Document | Location | What |
|----------|----------|------|
| Straddle Playbook | `docs/earnings_strategy_refactor/EARNINGS_STRADDLE_PLAYBOOK.md` | The trading strategy — buy ATM straddles on underpriced earnings. Complete with TOST case study. |
| Scenario Calculator Proposal | `docs/_local/earnings_strategy_refactor/earnings-scenario-calculator-proposal.md` (parked) | Tool to model straddle P/L accounting for IV crush. Not yet built. |
| Manual Operations | `strategies/earnings_intel/docs/MANUAL_OPERATIONS.md` | SQL queries for trading journal, manual tasks. |
| Config Thresholds | `config.json` → `earnings_play` | Signal thresholds: WATCH=15%, BUY=30%, STRONG BUY=50%. Alert: underpricing >= 15% AND OI >= 4000. |

---

## Data Quality Audit

*Initial audit: 2026-02-23 against query DB. Deep dive: 2026-02-24 against production DB (`data/datalake.db`). Production numbers supersede the earlier query DB numbers.*

---

### Table 1: `earnings_upcoming` (720 rows)

**Purpose**: Active roster of upcoming earnings. One row per symbol (PK: symbol). Populated weekly by YFinance refresh (dates), enriched daily by pipeline (signals, expected moves, alerts).

**Schema**: 12 columns — `symbol`, `earnings_date`, `earnings_days_ahead`, `expected_move_pct`, `historical_avg_move_pct`, `move_difference_pct`, `earnings_play_signal`, `earnings_time`, `earnings_alert`, `updated_at`, `straddle_expected_move_pct`, `relative_underpricing_pct`

**Date distribution**:
| Category | Count | % |
|----------|-------|---|
| Future | 677 | 94.0% |
| Today | 27 | 3.8% |
| Past (stale) | 16 | 2.2% |

Date range: 2026-02-17 (stale) to 2026-05-20 (~3 months out). All 720 rows last updated 2026-02-23 17:20 (within a 37-second batch window).

**Field completeness**:
| Field | Populated | of 720 | Fill Rate | Notes |
|-------|-----------|--------|-----------|-------|
| `earnings_date` | 720 | 720 | 100% | |
| `earnings_time` (non-"Unknown") | **0** | 720 | **0%** | YFinance limitation. Finnhub will fix (Session 3). |
| `expected_move_pct` | 298 | 720 | 41.4% | IV-based method. See coverage-by-horizon analysis below. |
| `straddle_expected_move_pct` | 183 | 720 | 25.4% | Straddle method. Fills in as earnings approach. |
| `historical_avg_move_pct` | 704 | 720 | 97.8% | Healthy — sourced from earnings_moves history. |
| `relative_underpricing_pct` | 376 | 720 | 52.2% | Computed from straddle (preferred) OR IV-based expected move. |
| `move_difference_pct` | 376 | 720 | 52.2% | Same population as relative_underpricing. |
| `earnings_play_signal` | 720 | 720 | 100% | Always set (defaults to UNKNOWN/AVOID when data missing). |
| `earnings_alert` (= 1) | 16 | 720 | 2.2% | Down from 75 false alerts — stale cleanup has improved. |
| `earnings_days_ahead` | 720 | 720 | 100% | Stale rows show 0. |

**Expected move coverage by time horizon** (the number that matters):

| Days to Earnings | Symbols | Has Expected Move | Coverage |
|------------------|---------|-------------------|----------|
| **0-7 days** | 73 | 70 | **95.9%** |
| **8-14 days** | 19 | 19 | **100%** |
| **15-30 days** | 30 | 29 | **96.7%** |
| 31-60 days | 166 | 91 | 54.8% |
| 60+ days | 389 | 144 | 37.0% |

**The 41% headline number is misleading. Coverage is 96-100% in the actionable window (0-30 days).** The low overall rate is driven by 555 symbols with earnings 31-90 days out. These lack coverage because:

1. **IV-based method** (`expected_move_pct`): Uses `iv_front_month` from `option_symbol_summary`, which is only populated for 43% of symbols (strict DTE bucketing). `iv_30dte` is 99.9% populated but not used. This is a minor improvement opportunity — could fall back to `iv_30dte` — but not a real problem since these distant earnings aren't actionable.

2. **Straddle method** (`straddle_expected_move_pct`): Requires `option_contracts` with `expiration_date >= earnings_date`. The Option Pipeline only collects contracts ~2 months out, so late-April/May earnings have no post-earnings expirations yet. **This fills in naturally as earnings dates approach** — by the time a symbol is within 30 days, option contracts spanning the earnings date are in the database.

**How the two methods relate**: The code (lines 418-435 of `ei_moves_upcoming.py`) tries both independently. For `relative_underpricing_pct`, it prefers the straddle method; falls back to IV-based. The 376 rows with underpricing = union of both methods. The 87 rows with both = overlap. Neither method has bugs — confirmed by Q9 audit showing zero symbols where IV data exists but expected_move is NULL.

**The 3 uncovered symbols within 7 days**: ENOV, MIDD, SEE — likely very illiquid names where ATM option data is thin or absent. Acceptable edge case.

**Stale data poisoning (partially improved)**

Down from 75 false alerts (Session 1 against query DB) to 16 stale rows in production. The false alert problem persists for the 16 remaining stale rows, including some with signals computed when options data was still available (ADI got "BUY", DE got "STRONG BUY" — both with `earnings_days_ahead = 0` and no expected_move). See P1 for fix options.

---

### Table 2: `earnings_events` (177 rows)

**Purpose**: Historical archive of earnings events. The canonical record of "symbol X had earnings on date Y." Populated by Friday weekly refresh archiving past-due rows from `earnings_upcoming`. Also serves as the FK parent for `earnings_moves`.

**Schema**: 16 columns — `event_id` (PK auto-increment), `symbol`, `earnings_date`, `fiscal_year`, `fiscal_quarter`, `estimated_eps`, `actual_eps`, `eps_surprise_pct`, `earnings_time`, `source`, `is_backfilled`, `created_at`, `notes`, `tags`, `note_type`, `sentiment`

**Date range**: 2025-11-24 to 2026-02-20 (~3 months)

**Field completeness**:
| Field | Populated | of 177 | Fill Rate | Notes |
|-------|-----------|--------|-----------|-------|
| `symbol` | 177 | 177 | 100% | |
| `earnings_date` | 177 | 177 | 100% | |
| `is_backfilled` | 177 | 177 | 100% | All = 0 (none backfilled) |
| `source` | 177 | 177 | 100% | All = "earnings_upcoming" |
| `earnings_time` (non-"Unknown") | **0** | 177 | **0%** | Inherited "Unknown" from earnings_upcoming |
| `fiscal_year` | **0** | 177 | **0%** | Never populated — YFinance doesn't provide |
| `fiscal_quarter` | **0** | 177 | **0%** | Never populated |
| `estimated_eps` | **0** | 177 | **0%** | Never populated |
| `actual_eps` | **0** | 177 | **0%** | Never populated |
| `eps_surprise_pct` | **0** | 177 | **0%** | Never populated |
| `notes` | **0** | 177 | **0%** | Trading journal — never used |
| `tags` | **0** | 177 | **0%** | Trading journal — never used |
| `sentiment` | **0** | 177 | **0%** | Trading journal — never used |

**This table is essentially a bare calendar.** Out of 16 columns, only 4 are populated: symbol, earnings_date, source, is_backfilled. Everything else — EPS data, fiscal periods, timing, trading journal — is empty.

**Monthly distribution**:
| Month | Events |
|-------|--------|
| 2025-11 | 8 |
| 2025-12 | 34 |
| 2026-01 | 59 |
| 2026-02 | 76 |

Growing month-over-month. The low November count is because the system started archiving around that time.

**177 unique symbols — exactly 1 event per symbol.** Over a 3-month span, some companies should have reported twice (Q3 and Q4 for odd fiscal years). The missing earlier events were archived to sector databases.

**Event ID range**: 28,982 to 32,421 (span of 3,439) but only 177 rows present. The 3,262 missing IDs were archived to sector DBs. This matches the MEMORY.md note about 9,292 orphaned rows in `earnings_moves`.

**Where the archived data lives**: Sector archive databases (`data/sector_archive/{sector}.db`). `earnings_events` is Tier 3 (90-day COPY). So historical earnings for, say, NVDA would be in the technology sector archive.

**Ben's observation re: on-demand lookup**: The earnings_date in this table (and sector archives) is valuable for charting — overlaying earnings dates on price charts. This is a legitimate use case that could be served by a simple query tool that checks both production and sector archives. Worth considering as a Morning View feature or CLI tool.

**Open questions**:
- Should we enrich this table with EPS data from Finnhub? Finnhub provides `epsActual`, `epsEstimate`, `quarter`, `year` — fields that are 0% populated today. Low priority but would make the historical record more useful.
- The trading journal columns (notes, tags, sentiment) exist but are 0% used. Is the MANUAL_OPERATIONS.md workflow too friction-heavy? Would an easier mechanism (Morning View button, CLI shortcut) increase usage?

---

### Table 3: `earnings_moves` (9,324 rows)

**Purpose**: Historical record of how stocks moved after earnings. Contains price moves (1d/2d/3d/5d), IV metrics (buildup/collapse/recovery), and expected vs actual move comparison. This is the primary source for `historical_avg_move_pct` in `earnings_upcoming`. Keyed by `event_id` FK to `earnings_events`.

**Schema**: 16 columns — `move_id` (PK), `event_id` (FK), `symbol`, `move_1day_pct`, `move_2day_pct`, `move_3day_pct`, `move_5day_pct`, `max_intraday_move_pct`, `move_direction`, `iv_buildup_pct`, `iv_collapse_pct`, `iv_recovery_pct`, `iv_crush_severity`, `expected_move_pct`, `move_vs_expected_pct`, `calculated_at`

**Date range**: calculated_at from 2025-10-10 to 2026-02-23 (~4.5 months). 727 distinct symbols.

**Field completeness**:
| Field | Populated | of 9,324 | Fill Rate | Notes |
|-------|-----------|----------|-----------|-------|
| `event_id` | 9,324 | 9,324 | 100% | |
| `symbol` | 9,324 | 9,324 | 100% | |
| `move_1day_pct` | 9,250 | 9,324 | 99.2% | 74 missing = recent events awaiting T+1 data |
| `move_2day_pct` | 9,250 | 9,324 | 99.2% | Same 74 |
| `move_3day_pct` | 9,250 | 9,324 | 99.2% | Same 74 |
| `move_5day_pct` | 9,250 | 9,324 | 99.2% | Same 74 |
| `max_intraday_move_pct` | 9,250 | 9,324 | 99.2% | Same 74 |
| `move_direction` | 9,250 | 9,324 | 99.2% | Same 74 |
| `iv_buildup_pct` | **28** | 9,324 | **0.3%** | Only from Feb 2026 backfill |
| `iv_collapse_pct` | **27** | 9,324 | **0.3%** | Same |
| `iv_recovery_pct` | **27** | 9,324 | **0.3%** | Same |
| `iv_crush_severity` | **27** | 9,324 | **0.3%** | 20 severe, 4 moderate, 3 mild |
| `expected_move_pct` | **28** | 9,324 | **0.3%** | Same |
| `move_vs_expected_pct` | **0** | 9,324 | **0.0%** | **Completely empty — never populated** |

**Two populations of data, very different completeness:**

1. **Bulk (9,250 rows)**: Price moves only. Calculated from Oct 2025 seed data. Has 1d/2d/3d/5d moves and direction. No IV metrics at all. These were computed before the IV calculation logic was added to `ei_post_earnings_calc.py`.

2. **Recent (28 rows)**: From Feb 2026 backfill (`ei_backfill_metrics.py`). Has IV buildup/collapse/recovery/crush severity AND expected_move_pct. But interestingly, the 28 rows with IV data have **NULL price moves** — they're very recent events where T+3 data hasn't accumulated yet. And the 9,250 rows with price moves have **NULL IV data** — they predate the IV computation logic.

**`move_vs_expected_pct` is 100% NULL** — the column that answers "did the stock move more or less than expected?" has never been populated for any of the 9,324 rows. Even the 28 rows with `expected_move_pct` show NULL. This is either a bug in the calculation or the field is computed separately and was never wired up. **This needs investigation** — it's the field that would close the loop on backtesting signal accuracy.

**Orphan rate: 99.7%** — 9,292 of 9,324 rows have `event_id` values that don't exist in production `earnings_events` (they were archived to sector DBs). Only 32 rows match current production events.

**No `earnings_date` column** — the table has no date field. To know WHEN an earnings event occurred, you must JOIN to `earnings_events` on `event_id`. For the 99.7% orphan rows, this JOIN returns nothing — you'd need to query sector archive databases to find the parent event. This makes the table unintuitive to query directly.

**Ben's observation**: "I wish we had the dates stored in the moves table." This is a legitimate design concern. Adding `earnings_date` as a denormalized column would make the table self-contained and queryable without JOINs to a table where 99.7% of parents don't exist.

**Open questions**:
- Why is `move_vs_expected_pct` always NULL? The calculation `actual_move / expected_move * 100` should be straightforward. Need to read `ei_post_earnings_calc.py` to find the bug or missing code path.
- Can the 9,250 bulk rows be backfilled with IV data? The `option_symbol_summary` data likely still exists in sector archives for the older events. But matching orphan `event_id` to archived `earnings_events` to get dates, then querying option data... that's a complex cross-archive join.
- Should we denormalize `earnings_date` onto this table? Pro: self-contained queries. Con: data duplication, potential desync.

---

### Table 4: `earnings_snapshots` (0 rows → FIXED Feb 2026)

**Design Intent** (from migration 002, Oct 2025): *"Time-series capture of IV and price evolution around earnings events. Shows the 'movie' not just the 'ending' — captures buildup and collapse."*

Two purposes:
1. **IV Buildup Curve** — Track daily IV ramp into earnings for the primary symbol. Answers: *when* should you enter a straddle? Is IV still cheap at T-5, or has the buildup already priced it in?
2. **Peer Sympathy Detection** — Track peer IV alongside the primary. If DAL's IV pumps 20 points but AAL's only moves 2, AAL might be a sympathy play. This is the data source intended to feed `earnings_sector_effects`.

The DAL example from the migration comments illustrates the core insight: the *shape* of the IV buildup curve matters, not just the endpoint. And peer divergence reveals underpriced sympathy plays that wouldn't show up in the primary symbol's data alone. This directly supports the straddle playbook strategy.

**Schema (updated Feb 2026)**: 15 columns — `snapshot_id` (PK), `symbol`, `earnings_date`, `event_id` (nullable), `snapshot_date`, `days_from_earnings`, `snapshot_type`, `close_price`, `volume`, `iv_30dte`, `iv_front_month`, `iv_45dte`, `total_open_interest`, `put_call_ratio`, `is_primary_symbol`, `created_at`. UNIQUE on `(symbol, earnings_date, snapshot_date)`.

**Original bugs (4 total, all fixed):**

1. **Wrong source table**: Queried `earnings_events` (historical, post-hoc only) instead of `earnings_upcoming` (forward-looking). Events only appear in `earnings_events` after earnings pass, so the T-7 to T+3 window was always empty.
2. **Inverted window bounds**: `BETWEEN -7 AND 3` on `earnings_date - trade_date` looked 7 days into the past and 3 into the future. Correct window (for `trade_date - earnings_date`) is `BETWEEN -7 AND 3` which looks 7 days into the future and 3 into the past.
3. **`days_from_earnings` stored with wrong sign**: Stored `earnings_date - trade_date` but the column convention (per migration) is `trade_date - earnings_date` (negative = before earnings, positive = after).
4. **`snapshot_type` logic inverted**: Labeled future earnings as `post_earnings` and past as `pre_earnings`.

**Schema migration**: Original schema had `event_id INTEGER NOT NULL REFERENCES earnings_events(event_id)`, but `earnings_upcoming` has no `event_id`. Fixed by making `event_id` nullable and adding `earnings_date` column. UNIQUE constraint changed from `(event_id, symbol, snapshot_date)` to `(symbol, earnings_date, snapshot_date)`. Migration is automatic (checks for `earnings_date` column, drops and recreates if missing — safe because table has always had 0 rows).

**Fix applied**: Session 6 (Feb 2026). Collector now queries `earnings_upcoming`, uses correct sign convention, proper snapshot_type logic. Will begin populating on next daily pipeline run.

**Not in any archive tier** — explicitly excluded from sector archiving. Will need archive strategy once data accumulates.

**Downstream consumers**: `ei_post_earnings_calc.py` still reads snapshots by `event_id` (which is now nullable and won't be populated for new rows). The existing `option_symbol_summary` fallback continues to handle IV data. Future work: update readers to use `(symbol, earnings_date)` key instead of `event_id`, or backfill `event_id` after events are archived.

---

### Table 5: `earnings_sector_effects` (0 rows)

**Purpose**: Track how peer/industry stocks react to a primary symbol's earnings (sector sympathy). Also stores arbitrage scanner morning scan results. FK to `earnings_events` via `primary_event_id`.

**Status**: Empty. The arbitrage scanner writes to it during morning scans, but only for today's earnings, and only when correlation data already exists (chicken-and-egg). The post-earnings calculator would populate it with actual peer moves at T+3, but this code path also depends on having matching `earnings_events` records.

**Not blocking anything immediately** — the arbitrage scanner (Step 1.2) is already acknowledged as a no-op. This table will populate gradually as more earnings cycles complete. Not a priority for this refactor.

---

### Cross-Table Issues

**1. The archive orphan problem**: `earnings_moves` has 9,292 orphan rows (99.7%) whose parent `earnings_events` were archived to sector DBs. These moves are historically valuable (price data for 727 symbols across 4.5 months) but cannot be queried with date context without cross-referencing sector archives. Options:
- Denormalize `earnings_date` onto `earnings_moves` (solves queryability)
- Accept the orphan state (data is still used for `historical_avg_move_pct` via symbol-level AVG)
- Backfill from sector archives (complex, one-time operation)

**2. ~~The expected_move gap~~ RESOLVED**: The 58% NULL rate for `expected_move_pct` across all rows looked alarming but is a non-issue. Coverage is **96-100% within 30 days of earnings** — the only window where signals are actionable. The gap is entirely in the 31-90 day horizon where options data doesn't extend far enough. The straddle method naturally fills in as earnings dates approach. No fix needed.

**3. Signal data is ephemeral**: When earnings pass, the signal that was computed (`earnings_play_signal`, `relative_underpricing_pct`) is discarded during archiving. No record of what the system recommended vs what actually happened. This prevents backtesting and threshold calibration.

**4. `move_vs_expected_pct` never populated**: The field designed to answer "was the move bigger than expected?" is 0/9,324 rows. Need to trace the bug in `ei_post_earnings_calc.py`.

---

### Legitimate Future Signals (next 14 days, non-AVOID, from Session 1 query DB data)

| Symbol | Date | Signal | Underpricing% | Expected% | Historical% |
|--------|------|--------|---------------|-----------|-------------|
| NVDA | 02-25 | STRONG BUY | 51.5% | 5.27 | 8.11 |
| LINE | 02-25 | STRONG BUY | 64.7% | 4.92 | 8.10 |
| XYZ | 02-26 | STRONG BUY | 105.6% | 10.51 | 19.47 |
| SEE | 03-02 | STRONG BUY | 213.1% | 2.65 | 8.29 |
| TTD | 02-25 | WATCH | 25.7% | 12.41 | 16.30 |
| SNOW | 02-25 | WATCH | 16.2% | 9.83 | 12.64 |
| FIS | 02-24 | WATCH | 22.3% | 30.04 | 7.55 |
| MDB | 03-02 | WATCH | 17.6% | 36.41 | 17.75 |
| APLS | 02-24 | BUY | 32.1% | 5.97 | 7.88 |

Note: SEE at 213% — verify. FIS has historical (7.55) < expected (30.04) which is OVERPRICED, yet shows WATCH — investigate formula. Production data may differ from query DB snapshot.

---

## Component Analysis

### 1. Morning Step 1.2: Earnings Arbitrage Scanner

**Purpose**: Find sector sympathy plays — if Delta reports, maybe UAL moves too.

**Current state**: Effectively a no-op.

**Why it's broken**:
1. `earnings_sector_effects` table has 0 rows → all correlation calculations return 0
2. With correlation = 0 and sample_size penalty of 0.5, everything scores LOW quality
3. Scanner only looks at "today's" earnings — too late to position

**What would need to happen to make it useful**:
1. Post-earnings calculator needs to run through multiple full earnings cycles to build correlation history
2. Scanner should look ahead 3-7 days, not just today
3. Requires `industry_peer_mappings` to be accurate (742 symbols — seems OK)

**Recommendation**:
- **Short term**: Add honest narrative text to the console output explaining the dependency ("Sector correlation data: 0 historical events — building baseline. Scanner will become useful after ~20 earnings cycles populate correlation data.")
- **Long term**: Shift to a 7-day lookahead once correlation data exists

**Code issues found**:
- Uses `date.today()` instead of `now_eastern()` — could cause date mismatch
- Quality thresholds are hardcoded (40/20), not in config.json
- No config section at all for arbitrage scanner parameters

### 2. Evening Step 3.3: Earnings Pipeline

**Purpose**: The workhorse. Collects data, calculates metrics, generates signals and alerts.

**What it does well**:
- Structured 3-task pipeline with good error isolation
- Relative underpricing metric is well-designed (validated by TOST case study)
- Signal thresholds are configurable in config.json
- Returns structured data to orchestrator (alert_details with symbol, days_ahead, underpricing, signal)
- Console completion box shows signal breakdown and top symbols

**What it does poorly**:
- **Timing**: Runs at 5 PM. You can't act on it until morning. By then, the console output is scrolled away.
- **Stale data**: Doesn't clean up past-due earnings → false alerts dominate
- **No morning delivery**: Alerts exist in the database but nothing surfaces them at 6:35 AM when you're sitting at the computer
- **earnings_time = "Unknown"**: Can't distinguish BMO from AMC, which determines whether you need to position today or tomorrow
- **Snapshot collector**: Depends on `earnings_events` which only has post-hoc entries → `earnings_snapshots` stays empty

**The delivery gap**: The pipeline generates genuinely useful data (the NVDA STRONG BUY at 51.5% underpricing for 02-25 is a real, actionable signal). The problem is getting it in front of Ben at the right time.

### 3. Friday Step 5.2: Weekly Refresh

**Purpose**: Refresh the earnings calendar from YFinance.

**What it does well**:
- Covers all 800 KLMN symbols
- INSERT OR REPLACE handles updates cleanly
- Archives past earnings to `earnings_events`
- Cleans up stale records

**What it does poorly**:
- **404 errors suppressed silently** — errors logged at DEBUG level only, invisible in normal operation. You don't know which symbols failed or why.
- **No completeness reporting** — says "Earnings found: 613" but doesn't say "187 symbols had no data" or "43 symbols returned errors"
- **earnings_time always "Unknown"** — YFinance doesn't provide BMO/AMC
- **Only runs Fridays** — if an earnings date changes mid-week, you don't know until next Friday
- **No validation against external source** — no way to know if YFinance is giving us accurate dates

**Logging improvement needed**: After the fetch loop, should report:
```
Earnings found: 613 of 800 symbols (76.6%)
  No data from YFinance: 145 symbols
  Errors during fetch: 42 symbols
  Symbols with errors: SYMBOL1, SYMBOL2, ... (list all, not truncated)
```

### 4. Thursday Scheduled Task

**Status**: Dead code. `scheduled_tasks/run_yfinance_earnings_upcoming.bat` calls `python -m data.yfinance_earnings_upcoming` — a module that was moved/deleted in the Oct 2025 refactor when earnings was reorganized into `strategies/earnings_intel/`. Has been silently failing every Thursday for 4+ months.

**References found**: Only the batch file and old PRD/task docs (`tasks/0003-*.md`) reference the dead module. No active Python code imports it. A stale log file exists at `data/logs/yfinance_earnings_calendar.log` (last entry: Sept 2025).

**Note**: `data/yfinance_earnings_historical.py` is a *different* file — it handles historical earnings backfill and is still used by `ei_backfill_events.py`. Don't confuse the two.

**There is no module it "should" call** — Friday's Step 5.2 does the same job (full YFinance refresh for all 800 symbols). The Thursday task was a redundant mid-week refresh from the old architecture. If we later decide we want mid-week refreshes, we'd build that into the orchestrator properly.

**Action**: Ben has disabled the Windows Task Scheduler entry. Delete the batch file and stale log. The task docs are historical records — leave them.

---

## Existing Strategy Docs

### EARNINGS_STRADDLE_PLAYBOOK.md — Key Points

The playbook defines a trading strategy worth exploring and building into workflow: **buy ATM straddles on underpriced earnings**.

- Entry criteria: WATCH or higher signal, OI >= 4000, earnings within 5 trading days
- Position sizing: Stocks under $40 preferred (straddle < $300)
- Exit: Sell both legs morning after earnings, wait 15-30 min
- Validated by TOST case study: directional bet lost $208, straddle would have gained +47%

**What the playbook needs from the system**:
1. A reliable, timely list of candidates (WATCH+ signals)
2. BMO/AMC timing (not currently available)
3. Straddle pricing alongside the signal data
4. Post-trade outcome tracking

### earnings-scenario-calculator-proposal.md — Key Points

Proposed tool for modeling hold-through-earnings vs sell-before decisions:
- Uses existing Greeks + IV crush estimates
- `post_earnings_iv = pre_earnings_iv * 0.54` (46% median crush from 17 events)
- Greek-based approximation (Taylor expansion with gamma correction)
- Phase 1: CLI tool. Phase 2: Morning View integration.

**Status**: Not yet built. Depends on having accurate IV crush data per symbol (needs `iv_collapse_pct` backfilled in `earnings_moves`).

---

## Problems to Solve

### P1: Stale Data Poisoning Alerts (CRITICAL — Fix immediately)

Past-due earnings in `earnings_upcoming` produce false STRONG BUY signals with absurd underpricing values (700-7600%). 75 of 75 current alerts are false.

**Root cause**: Cleanup only runs on Fridays. Between Monday and Friday, stale rows accumulate. The daily pipeline recalculates signals on ALL rows including stale ones, and the near-zero straddle values for expired options produce divide-by-near-zero inflation.

**Important discovery — data lifecycle gap**:

Deleting stale rows is NOT as simple as it first appeared. The archive chain has a vulnerability:

1. `earnings_upcoming` → `earnings_events` archive only happens during **Friday weekly refresh** (`ei_main.py` lines 132-142, INSERT OR IGNORE)
2. The cleanup function in `ei_fetch_upcoming.py:_cleanup_past_earnings()` **does not archive before deleting** — it just does `DELETE FROM earnings_upcoming WHERE earnings_date < date('now')`
3. If we add daily deletion, rows could be lost before Friday's archive captures them to `earnings_events`

**Worse — signal data is never archived at all**:

The `earnings_events` table lacks columns for `earnings_play_signal`, `relative_underpricing_pct`, `expected_move_pct`, and `straddle_expected_move_pct`. Even when the Friday archive runs, it only copies symbol + date + earnings_time. All the daily pipeline's analysis (the valuable part) is discarded.

Column comparison:
| Column | `earnings_upcoming` | `earnings_events` | Lost on archive? |
|--------|-------|-------|------|
| symbol, earnings_date, earnings_time | Yes | Yes | No |
| expected_move_pct | Yes | No | **Yes** |
| historical_avg_move_pct | Yes | No | **Yes** |
| relative_underpricing_pct | Yes | No | **Yes** |
| earnings_play_signal | Yes | No | **Yes** |
| straddle_expected_move_pct | Yes | No | **Yes** |
| earnings_alert | Yes | No | **Yes** |
| earnings_days_ahead | Yes | No | **Yes** |
| move_difference_pct | Yes | No | **Yes** |

**Practical question**: Does losing signal data matter? The signals are point-in-time ("on Feb 20, NVDA was 51% underpriced"). After earnings pass, they're not actionable. BUT — they're essential for backtesting signal accuracy ("Of all STRONG BUY signals, what % produced profitable straddles?"). Without archiving signals, we can never validate the system.

**Fix options** (see Q4 for full discussion):
- **Option A (Safest, simplest)**: Don't delete stale rows. Add `WHERE earnings_date >= date('now')` to the daily pipeline's signal calculation. Stale rows sit harmlessly — they exist but never get recalculated with bad data. Friday cleanup handles actual deletion after archiving. Zero risk.
- **Option B**: Archive signal data to `earnings_events` (add columns) or a new `earnings_signal_history` table before deleting. Preserves everything for backtesting.
- **Option C**: Delete daily, accept that pre-earnings signal data is ephemeral. `earnings_moves` captures post-earnings outcomes. Backtesting would need to be reconstructed from historical option data.

### P2: Morning Delivery of Actionable Intelligence (HIGH — Core value)

The pipeline runs at 5 PM but the information is needed at 6:35 AM. No mechanism to surface it.

**Options (not mutually exclusive)**:
1. **Morning View screen**: Add an earnings tab to the TUI showing upcoming earnings with signals, sorted by actionability
2. **Enhanced Step 1.2 console output**: Instead of just the (broken) arbitrage scan, also display the top earnings opportunities from `earnings_upcoming` at 6:35 AM
3. **Email digest**: Send a morning earnings briefing to `klmn800alerts@gmail.com` using existing email infrastructure
4. **Morning scan query**: Simple SQL query added to morning phase that reads `earnings_upcoming` and displays candidates

Option 2 or 4 is fastest to ship. Option 1 is the richest experience. Option 3 is useful for days Ben isn't at the computer.

### P3: BMO/AMC Timing (HIGH — Affects trade planning)

All 613 `earnings_time` values are "Unknown". This matters because:
- BMO earnings: position needs to be entered the day before
- AMC earnings: position can be entered day-of
- Without this, Ben can't time his entries correctly

**Options**:
1. Supplement YFinance with another data source (Yahoo Finance earnings calendar page scrape, Nasdaq API, earnings whispers)
2. Manual override mechanism (let Ben set BMO/AMC for specific symbols he's tracking)
3. Default assumption: treat all as "unknown timing, enter 2 days before to be safe"

### P4: Confidence in Calendar Completeness (MEDIUM)

No clear reporting on how many symbols had errors, which ones are missing, or how fresh the data is. The suppressed 404s make it feel like the system is hiding problems.

**Fix**: Better summary logging after the weekly fetch. Show: total symbols attempted, earnings found, no data, errors, error rate.

### P5: Dead Thursday Scheduled Task (DONE)

Silent failure for 4+ months. Ben has disabled the Windows Task Scheduler entry. Batch file (`scheduled_tasks/run_yfinance_earnings_upcoming.bat`) and stale log (`data/logs/yfinance_earnings_calendar.log`) can be deleted. No orphaned code — the old module was already removed during Oct 2025 refactor.

### P6: Arbitrage Scanner Dependency (LOW — Long-term)

`earnings_sector_effects` will populate naturally as the post-earnings calculator processes more events. No immediate action needed, but:
- Add honest narrative text to Step 1.2 console output
- Consider shifting from "today only" to "next 7 days" when correlation data exists

### P7: Scenario Calculator (FUTURE — After P1-P4)

The proposal is solid but depends on P1-P4 being resolved first. Building a calculator on top of unreliable signal data doesn't help.

---

## Design Decisions & Open Questions

### Q1: Where should the morning earnings briefing live?

**Context**: The data exists in `earnings_upcoming`. We need to get it in front of Ben at 6:35 AM.

**Options**:
- **A) Morning console output in Step 1.2** — cheapest. Just query `earnings_upcoming` for WATCH+ signals with earnings in next 5 days and print them. Could replace or supplement the arbitrage scanner.
- **B) Morning View TUI screen** — richest. Dedicated earnings screen with signal table, straddle pricing, days to earnings. Persistent — can check it anytime.
- **C) Email notification** — useful for remote days. Morning email with candidates.
- **D) All of the above** — A for immediate console awareness, B for deep analysis, C for mobility.

**Decision**: TBD

### Q2: How do we get BMO/AMC data?

**Context**: YFinance doesn't provide it. It's critical for timing entries.

**Options**:
- Scrape Yahoo Finance earnings calendar page
- Use Nasdaq earnings API
- Use Earnings Whispers data
- Manual entry for tracked symbols
- Don't solve it — assume all need 2-day lead time
- **Finnhub API** (see Session 3 research below)

**Decision**: **Finnhub API** — free tier, REST endpoint, returns `hour` field with `bmo`/`amc`/`dmh` values. See Session 3 for full details.

### Q3: Should the daily pipeline run twice (morning + evening)?

**Context**: Currently runs at 5 PM only. The expected move data would be more current if refreshed in the morning too. But it adds ~10-15 minutes to the morning phase.

**Options**:
- Run full pipeline twice (morning + evening)
- Run only Task 3 (expected moves update) in the morning — lightweight, just recalculates with latest options data
- Keep evening-only, rely on the data from last evening being "close enough"

**Decision**: TBD

### Q4: What's the right cleanup strategy for past earnings?

**Context**: Currently only Friday cleanup. Stale rows get recalculated with bad data (near-zero straddle values) and produce false alerts.

**The core tension**: We need stale rows to stop poisoning alerts (immediate), but we may want their signal data preserved for backtesting (future).

**Options**:

- **A) Filter, don't delete (RECOMMENDED for now)**: Add `WHERE earnings_date >= date('now')` to the signal calculation query in `ei_moves_upcoming.py`. Stale rows remain in the table but are never touched by the daily pipeline. Friday's weekly refresh handles archiving and deletion on its normal schedule. **Pros**: Zero risk, simplest change, no data loss. **Cons**: Stale rows visible in raw SQL queries (minor annoyance).

- **B) Archive signals, then delete daily**: Add signal columns (`earnings_play_signal`, `relative_underpricing_pct`, `expected_move_pct`, `straddle_expected_move_pct`) to `earnings_events` table, or create a new `earnings_signal_history` table. Archive full enriched row before deleting. **Pros**: Preserves everything for backtesting. **Cons**: Schema change, more code, needs design work.

- **C) Delete daily, lose signal data**: Run `_cleanup_past_earnings()` at start of daily pipeline. Signals are ephemeral — `earnings_moves` captures actual outcomes. **Pros**: Clean table. **Cons**: Can never answer "was the STRONG BUY signal accurate?" without reconstructing from raw option data.

- **D) Belt + suspenders**: Option A (filter) now, Option B (archive) later as part of Phase 2 backtesting work.

**Recommendation**: Option A now. It's a one-line WHERE clause change. Revisit signal archiving when we build backtesting capability.

**Decision**: TBD

### Q5: Should we validate signal quality before trusting it for trades?

**Context**: Production data (Session 4) shows only 14 of 704 future rows (2.0%) have actionable signals (WATCH/BUY/STRONG BUY).

**Updated framing (Session 5)**: The 48.9% UNKNOWN rate that looked alarming is a non-issue — it's driven by symbols with earnings 31-90 days out that lack option data. In the actionable 0-30 day window, coverage is 96-100%. The signal distribution within the covered population is the real question.

**Remaining action**:
- After fixing stale data (Q4), re-audit signal distribution for the 0-30 day window only. The 14 actionable signals out of ~122 near-term symbols (11.5%) seems plausible but should be validated.
- Finnhub integration (Q2) won't change expected_move — it comes from options data, not calendar data.

**Decision**: TBD (needs clean data first, but the expected_move gap is resolved)

### Q6: Should we denormalize `earnings_date` onto `earnings_moves`?

**Context**: `earnings_moves` has no date column. To know when an earnings event occurred, you must JOIN to `earnings_events` on `event_id`. But 99.7% of event_ids in moves are orphans (parent archived to sector DBs). This makes the table nearly impossible to query directly.

**Options**:
- **A) Add `earnings_date` column to `earnings_moves`**: Denormalize. Makes table self-contained. Can query "what was NVDA's avg 1-day move across all earnings?" without any JOINs.
- **B) Leave as-is**: Accept that detailed historical queries need sector archive access. The AVG calculation for `historical_avg_move_pct` works via symbol-level grouping (no date needed).
- **C) Create a view**: `CREATE VIEW earnings_moves_dated AS SELECT em.*, ee.earnings_date FROM earnings_moves em LEFT JOIN earnings_events ee ON em.event_id = ee.event_id`. Only works for the 32 non-orphan rows.

**Decision**: TBD

### Q7: Why is `move_vs_expected_pct` always NULL? — ROOT CAUSE FOUND

**Root cause (Session 6):** Cascading failure from the `earnings_snapshots` bug.

`move_vs_expected_pct` (line 182 of `ei_post_earnings_calc.py`) needs two inputs — both are NULL:

1. **`move_1day_pct`**: `_calculate_price_moves()` (line 207) reads from `earnings_snapshots` (0 rows) → returns `{}`. **No fallback to `historical_prices` exists** — unlike IV which got a fallback in Feb 2026.
2. **`expected_move_pct`**: Uses `iv_front_month` (~43% populated). Moot since the other input is always NULL.

The 9,250 rows WITH price moves = legacy Oct 2025 seed data (different code path). Current production code can never produce price moves.

**Fix**: Add `_get_price_moves_from_historical()` fallback in `ei_post_earnings_calc.py` — query `historical_prices` for close prices at T+0/+1/+2/+3. Same pattern as existing `_get_iv_from_option_summary()`. Unblocks both `move_1day_pct` and `move_vs_expected_pct`.

**Priority**: HIGH — closes the backtesting loop. Without it, can't validate signal accuracy.

**Decision**: Implement the fallback.

### Q8: Is `earnings_snapshots` worth reviving or should we deprecate it? — DECIDED: Rewire (Option B)

**Context**: 0 rows, never populated, fully bypassed by `option_symbol_summary` fallback. Root cause was architecture mismatch — collector queried `earnings_events` (historical) but needed `earnings_upcoming` (forward-looking).

**Decision**: **Option B — Rewire.** The design intent (IV buildup curves + peer sympathy detection) directly supports the straddle playbook strategy. The collector code was well-structured — it just pointed at the wrong table. Fixed in Session 6:
- Collector now queries `earnings_upcoming` instead of `earnings_events`
- Schema migrated: `event_id` nullable, `earnings_date` added, UNIQUE constraint updated
- Also fixed 3 additional bugs: inverted window bounds, wrong sign convention, inverted snapshot_type
- Will begin collecting data on next pipeline run

**What this unlocks (over time)**:
- Daily IV buildup visualization (is IV still cheap or already priced in?)
- Peer sympathy detection (which peers react and which don't?)
- Better IV crush data (actual daily T-7 through T+3 series vs point-in-time lookups)
- Foundation for `earnings_sector_effects` population

---

## Implementation Plan

*To be developed after design decisions are made. Will use PRD workflow if scope exceeds 5 files.*

### Phase 0: Immediate Fixes (no design decisions needed)
- [ ] Fix stale data bug — needs Q4 decision first (Option A is low-risk: filter, don't delete)
- [x] Thursday scheduled task — Ben disabled in Task Scheduler. Delete batch file + stale log.
- [ ] Add narrative text to Step 1.2 console about sector effects dependency
- [ ] Improve weekly refresh logging (completeness reporting)

### Phase 1: Morning Delivery (needs Q1 decision)
- [ ] Surface earnings opportunities at 6:35 AM
- [ ] Include: symbol, date, days ahead, signal, underpricing%, expected move%, historical avg
- [ ] Filter: WATCH+ only, earnings within 7 days, OI >= 4000

### Phase 2: Data Quality (needs Q2, Q3, Q4 decisions)
- [ ] BMO/AMC data source
- [ ] Morning recalculation of expected moves
- [ ] Signal quality validation after clean data

### Phase 3: Rich Experience (needs Phase 1-2 complete)
- [ ] Scenario Calculator (from existing proposal)
- [ ] Morning View earnings screen
- [ ] Historical straddle backtest to validate thresholds

---

## Session Log

### Session 1 — 2026-02-23 (Initial Research & Audit)

**What we did**:
- Full code audit of all 4 earnings components (Step 1.2, 3.3, 5.2, Thursday task)
- Data quality audit against `datalake_query.db`
- Reviewed existing strategy documents (playbook + calculator proposal)

**Key findings**:
1. **75 false alerts** from stale data — past-due earnings with collapsed straddles produce absurd underpricing numbers
2. **Thursday scheduled task is dead** — calls a module deleted in Oct 2025 refactor
3. **Arbitrage scanner is a no-op** — 0 rows in correlation table, only scans "today"
4. **100% "Unknown" earnings time** — YFinance doesn't provide BMO/AMC
5. **Morning delivery gap** — pipeline runs at 5 PM, no mechanism to surface data at 6:35 AM
6. **Real signals exist** — NVDA (02-25, STRONG BUY, 51.5% underpricing) and others are legitimate candidates buried under the stale data noise
7. **Logging is poor** — 404 errors suppressed, no completeness metrics, no visibility into what's missing

**What we discussed**:
- The trading strategy is well-defined (straddle playbook)
- The data pipeline infrastructure is solid — it just needs cleanup and better delivery
- The gap is between "data exists" and "data reaches Ben at the right time in the right format"

**Next steps**: Ben to review findings, make design decisions (Q1-Q5), then we prioritize implementation.

### Session 2 — 2026-02-24 (Phase 0 Deep Dive & Data Lifecycle Discovery)

**What we did**:
- Deep research into Thursday scheduled task — confirmed fully dead, no orphaned code
- Traced the full `earnings_upcoming` data lifecycle and discovered the archive gap
- Revised P1 (stale data fix) after discovering deletion risks

**Key findings**:
1. **Thursday task is safe to delete** — the batch file calls a module deleted in Oct 2025. `data/yfinance_earnings_historical.py` is a different file (still in use for backfill). No active code references the dead module. Ben has disabled it in Task Scheduler.
2. **Deleting stale rows is risky** — the archive chain (`earnings_upcoming` → `earnings_events`) only runs on Fridays via weekly refresh. Daily deletion would lose rows before they're archived. The cleanup function in `ei_fetch_upcoming.py` does NOT archive before deleting.
3. **Signal data is never preserved** — `earnings_events` lacks signal columns (`earnings_play_signal`, `relative_underpricing_pct`, `expected_move_pct`, `straddle_expected_move_pct`). Even when Friday archive runs, all analysis data is discarded. This means we currently have no ability to backtest signal accuracy.
4. **Recommended approach changed** — instead of "delete stale rows daily" (Session 1), now recommending "filter stale rows during calculation" (Option A). One-line WHERE clause in `ei_moves_upcoming.py`, zero data loss risk, stale rows stop poisoning alerts immediately.

**Decisions made**:
- Thursday task: disabled by Ben, batch file + log to be deleted (P5 DONE)

**Open items carried forward**:
- Q4 (cleanup strategy): Option A recommended, awaiting Ben's approval
- Q1-Q3, Q5: still TBD
- Phase 0 remaining: Fix 2 (narrative text), Fix 3 (logging), Fix 1 (stale data — pending Q4)

### Session 3 — 2026-02-24 (BMO/AMC Data Source Research)

**What we did**:
- Researched alternatives to yfinance for corporate earnings data, specifically BMO/AMC timing
- Evaluated Finnhub, Financial Modeling Prep (FMP), Alpha Vantage, Nasdaq/Zacks
- Vetted Finnhub's legitimacy (company background, history, red flags)
- Mapped Finnhub's earnings endpoint fields against our `earnings_upcoming` schema
- Audited what yfinance actually provides vs what we currently capture

**Decision: Finnhub for BMO/AMC timing**

Q2 is answered. Finnhub's earnings calendar API provides the `hour` field (`bmo`/`amc`/`dmh`) that yfinance cannot. Implementation will be part of Phase 2 of the earnings refactor, not a standalone task.

---

#### Finnhub Background

- **Not Finnish.** "Fin" (finance) + "hub" with doubled N. Likely a domain availability choice.
- Founded 2017, New York. Founders: Spencer Sands, Tri Do. Public API since 2019.
- Bootstrapped, ~1-10 employees (NYC/Mumbai/Sydney/HCMC). No VC funding disclosed.
- Interactive Brokers features their API in IBKR Campus tutorials. Scam Detector: 80.9/100.
- Minor flag: one astroturfing allegation on Medium, some GitHub issues about data delays.
- **Assessment**: Legitimate small provider. Adequate as a supplementary data source — we're not relying on it for primary trading signals, just earnings calendar metadata.

#### Finnhub Earnings Calendar Endpoint

**`GET https://finnhub.io/api/v1/calendar/earnings`**

**Authentication**: Query param `token=API_KEY` or header `X-Finnhub-Token: API_KEY`

**Parameters** (all optional):

| Parameter | Type | Description |
|-----------|------|-------------|
| `from` | date (YYYY-MM-DD) | Start of date range |
| `to` | date (YYYY-MM-DD) | End of date range |
| `symbol` | string | Filter by ticker |
| `international` | boolean | Include international markets (default false) |

Can query by date range, by symbol, or both. No params = current/upcoming week.

**Response fields** (flat JSON, array of `EarningRelease` objects):

| Field | Type | Description |
|-------|------|-------------|
| `date` | date | Earnings release date (YYYY-MM-DD) |
| `epsActual` | float | Actual EPS (null if not yet reported) |
| `epsEstimate` | float | Consensus EPS estimate (includes Finnhub proprietary) |
| `hour` | string | **`bmo`** (before market open), **`amc`** (after market close), **`dmh`** (during market hours), or **`""`** (unknown) |
| `quarter` | int | Fiscal quarter (1-4) |
| `revenueActual` | float | Actual revenue (null if unreported) |
| `revenueEstimate` | float | Consensus revenue estimate |
| `symbol` | string | Ticker |
| `year` | int | Fiscal year |

**EPS/revenue figures are non-GAAP** (adjusted, matches what investors react to).

**Rate limits**: Free tier = **60 calls/minute**, 30 calls/sec hard cap across all tiers. HTTP 429 on exceed.

**No pip install needed** — hit the REST API directly with `requests` (already in our environment). No `finnhub-python` package required.

#### Other Finnhub Earnings Endpoints (for future reference)

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `/stock/earnings` | Historical EPS surprises per symbol | `surprise`, `surprisePercent` fields |
| `/stock/eps-estimate` | Forward EPS consensus (avg/high/low) | Per-symbol, quarterly or annual |
| `/stock/revenue-estimate` | Forward revenue consensus (avg/high/low) | Same structure as EPS |
| `/stock/earnings-quality-score` | Multi-dimensional quality grade (A-F) | Growth, profitability, leverage, cash gen |
| `/stock/transcripts-list` | Earnings call transcript index | Lists available transcripts per symbol |
| `/stock/transcripts` | Full transcript with speakers | Management discussion + Q&A |

These are not needed now. Documented for future consideration.

#### Alignment with `earnings_upcoming` Table

| Finnhub Field | Maps To | Current State | Action |
|---------------|---------|---------------|--------|
| `hour` | `earnings_time` | Always 'Unknown' | **Primary win — direct mapping** |
| `date` | `earnings_date` | Populated by yfinance | Cross-validation source |
| `epsEstimate` | — | Not stored | Could add column, low priority |
| `revenueEstimate` | — | Not stored | Could add column, low priority |
| `quarter` | — | Not stored | Could add column, low priority |
| `epsActual` | — | Not stored (post-hoc) | For post-earnings pipeline, not upcoming |
| `revenueActual` | — | Not stored (post-hoc) | Same |

**Minimum viable integration**: Finnhub provides `hour` → populate `earnings_time`. That's the one field we need.

#### yfinance: What We Have vs What We Capture

The current fetcher (`ei_fetch_upcoming.py`) calls `ticker.calendar` but only extracts the earnings date. yfinance also returns:

| yfinance Field | Currently Captured? | Useful? |
|----------------|-------------------|---------|
| `Earnings Date` | Yes | — |
| `Earnings Average` (consensus EPS) | **No — ignored** | Maybe, but we don't act on EPS |
| `Earnings High` / `Earnings Low` | **No — ignored** | Low priority |
| `Revenue Average` / `High` / `Low` | **No — ignored** | Low priority |

Ben's assessment: EPS/revenue estimates are unnecessary refinements for where we are now. The system cares about options pricing around earnings (IV, expected moves, underpricing), not whether Street EPS consensus is $1.42 vs $1.38. Not worth adding columns we don't act on.

yfinance also has `ticker.earnings_dates` with timezone-aware timestamps that could *theoretically* derive BMO/AMC, but this is unreliable (it's earnings *call* time, not results release time; many entries lack timestamps; the fetcher already has a comment: "yfinance doesn't provide BMO/AMC"). Not a viable path.

#### Collection Strategy Options

For ~750 symbols at 60 calls/min:

| Approach | API Calls | Time | Pros | Cons |
|----------|-----------|------|------|------|
| **Per-symbol** | ~750 | ~12.5 min | Complete coverage | Slow, burns budget |
| **Date-range scan** | 1-4 | Seconds | Fast, minimal calls | Only gets symbols with imminent earnings |
| **Hybrid (recommended)** | ~20-50 | ~1 min | Best of both | Slightly more code |

**Hybrid approach**: Weekly date-range scan for next 14 days (1-2 calls, returns all symbols reporting). Then per-symbol calls only for KLMN 800 symbols not covered. Most of our universe won't have earnings in any given 2-week window, so the date-range scan catches nearly everything. Per-symbol backfill only for edge cases.

Could also do a full per-symbol sweep on Fridays (alongside yfinance refresh) and date-range updates during the week.

#### Architecture Notes

Client would follow the `core/tradier_api.py` pattern:
- `core/finnhub_api.py` — `FinnhubAPI` class with rate limiting, `FinnhubDataClient` with caching
- API key stored in `config.json` under `finnhub` section
- No pip install — direct `requests` calls to REST endpoint
- Rate limiter: 60 calls/min (reuse `RateLimiter` class pattern from tradier_api.py)

#### Hybrid Source Strategy (yfinance + Finnhub)

Both sources serve different purposes and should coexist:

| Responsibility | Source | Rationale |
|----------------|--------|-----------|
| Earnings dates | **yfinance** (primary) | Already working, 720 rows, covers full universe |
| Earnings dates | **Finnhub** (cross-validation) | Flag discrepancies, catch date changes mid-week |
| BMO/AMC timing | **Finnhub** (sole source) | yfinance can't provide this |
| EPS/revenue estimates | **Neither for now** | Not actionable in current strategy |

If yfinance ever becomes unreliable for dates, Finnhub could take over entirely — the endpoint returns dates too. But no reason to migrate what's working.

**Open items for implementation**:
- Get a Finnhub API key (free registration at finnhub.io/register)
- Decide whether Finnhub runs in the Friday refresh, the daily pipeline, or both
- Decide how to handle `hour = ""` (unknown timing) — treat as "position 2 days early" per P3 Option 3?

### Session 4 — 2026-02-24 (Deep Table Audit — Production DB)

**What we did**:
- Comprehensive data quality audit of all 5 earnings tables against production DB (`data/datalake.db`)
- Full field completeness analysis for every column on every table
- Traced orphan relationships and archive effects
- Researched `earnings_snapshots` intent, root cause of emptiness, and deprecation status

**Key findings**:

1. **`expected_move_pct` only 41% populated (298/720)** — This is the fundamental problem. Without expected move data, the system can't compute underpricing signals. 416 rows (58%) have historical avg but no expected move → UNKNOWN signal. Only 288 rows have both fields needed for a real signal. Root cause likely: these symbols lack ATM options in `option_contracts` (illiquid names not in OP collection range).

2. **`move_vs_expected_pct` is 100% NULL across all 9,324 rows in `earnings_moves`** — The column designed to validate signal accuracy has never been populated. Even the 28 rows with `expected_move_pct` show NULL. This is either a bug or unimplemented code path. Blocks backtesting entirely.

3. **`earnings_events` is a bare calendar** — Only 3 of 16 columns populated (symbol, date, is_backfilled). Zero EPS data, zero timing data, zero fiscal info, zero trading journal entries. The trading journal feature (notes, tags, sentiment) has never been used.

4. **`earnings_moves` orphan rate is 99.7%** — 9,292 of 9,324 rows reference archived `event_id`s. No `earnings_date` column means you can't query these rows with date context without sector archive JOINs. Table is functional (AVG works by symbol) but unintuitive.

5. **`earnings_snapshots` is effectively deprecated** — 0 rows, fundamental architecture bug (collector queries historical `earnings_events` instead of forward-looking `earnings_upcoming`), fully bypassed by `option_symbol_summary` fallback. Working code exists but never fires.

6. **Production numbers differ from query DB** — 720 rows (production) vs 613 (query DB from Session 1). Query DB was behind due to sync timing. All future audits should use production DB.

**New questions added**: Q6 (denormalize dates onto moves), Q7 (move_vs_expected bug), Q8 (snapshots deprecation)

**Emerging picture**: The earnings system has a good design but thin data coverage. The pipeline infrastructure works — the problem is upstream data availability (`expected_move_pct` coverage) and downstream data preservation (signals not archived, move_vs_expected never computed). Fixing these coverage and lifecycle gaps would make the existing WATCH/BUY/STRONG BUY signals reliable enough to trade on.

### Session 5 — 2026-02-24 (Expected Move Coverage — Non-Issue)

**What we did**:
- Investigated why `expected_move_pct` is only 41% populated (looked like a critical data gap)
- Ran diagnostic queries breaking down coverage by days-to-earnings bucket
- Traced both calculation methods through `ei_moves_upcoming.py`

**Key findings**:

1. **The 41% number is misleading — coverage is 96-100% where it matters.** Expected move coverage by time horizon:
   - 0-7 days: **95.9%** (70/73)
   - 8-14 days: **100%** (19/19)
   - 15-30 days: **96.7%** (29/30)
   - 31-60 days: 54.8% (91/166)
   - 60+ days: 37.0% (144/389)

2. **Root cause of distant gaps is structural, not a bug:**
   - IV-based method uses `iv_front_month` (43% populated) rather than `iv_30dte` (99.9%). Minor improvement possible but irrelevant for trading.
   - Straddle method needs `option_contracts` with expirations past the earnings date. OP collects ~2 months out. Distant earnings don't have post-earnings expirations yet. **Fills in naturally as dates approach.**

3. **No bugs in calculation code.** Zero symbols exist where IV data is available but expected_move is NULL. The code works perfectly when data exists.

4. **Only 3 symbols within 7 days lack coverage** (ENOV, MIDD, SEE) — likely illiquid names with thin ATM options. Acceptable edge case.

**Conclusion**: This is not a problem to solve. The system's coverage is strong exactly in the actionable window. The high UNKNOWN rate for distant earnings is expected behavior, not a bug. Documented in code and research doc.

### Session 6 — 2026-02-25 (earnings_snapshots Deep Dive & Fix)

**What we did**:
- Comprehensive investigation of `earnings_snapshots` — schema, all code references, design intent, root cause analysis
- Traced the original vision from migration 002 comments: "shows the movie, not just the ending"
- Discovered 4 bugs total in `ei_snapshot_collector.py` (not just the wrong-table bug)
- Implemented the fix — rewired collector to query `earnings_upcoming`, migrated schema, fixed all 4 bugs

**Key findings**:

1. **Design intent is valuable**: The table was designed to capture daily IV buildup curves and peer sympathy divergence — both directly support the straddle playbook strategy. The concept is sound; only the implementation was broken.

2. **Four bugs, not one**:
   - Wrong source table (`earnings_events` instead of `earnings_upcoming`)
   - Inverted window bounds (looked backward instead of forward)
   - `days_from_earnings` stored with wrong sign
   - `snapshot_type` labels were inverted

3. **Schema needed updating**: `earnings_upcoming` has no `event_id` (PK is `symbol`), so the `event_id NOT NULL` FK constraint couldn't work. Made `event_id` nullable, added `earnings_date` column, changed UNIQUE from `(event_id, symbol, snapshot_date)` to `(symbol, earnings_date, snapshot_date)`.

4. **Cascading impact of empty snapshots**: The table being empty caused `_calculate_price_moves()` in `ei_post_earnings_calc.py` to always return empty (no fallback), which kept `move_1day_pct` NULL, which kept `move_vs_expected_pct` NULL across all 9,324 `earnings_moves` rows. IV data was OK because it had a separate fallback to `option_symbol_summary`.

**Changes made**:
- `ei_snapshot_collector.py`: `_ensure_schema()` migration method, `_get_events_in_window()` rewired to `earnings_upcoming`, `_collect_snapshots_for_event()` updated for new schema, `_collect_symbol_snapshot()` updated (earnings_date instead of event_id, correct sign convention, 3-way snapshot_type)
- `RESEARCH_AND_FINDINGS.md`: Table 4 section expanded with design intent, Q8 decided (Option B: Rewire)

**Decisions made**:
- Q8: Rewire (Option B). The design intent is valuable for the straddle strategy. Fix applied.

**What's next for snapshots**:
- Data will begin accumulating on next daily pipeline run
- Downstream consumers (`ei_post_earnings_calc.py`) still use `event_id` lookup — they'll continue using the `option_symbol_summary` fallback until updated to use `(symbol, earnings_date)` key
- Q7 fix (add `_get_price_moves_from_historical()` fallback) is still the higher-priority item for unblocking `move_vs_expected_pct`
