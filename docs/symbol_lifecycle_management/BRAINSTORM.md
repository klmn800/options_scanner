# Symbol Lifecycle Management — Brainstorm

**Status:** Brainstorming. Not a PRD. Not locked. Expect iteration.
**Started:** 2026-04-16
**Bundles:** to-do items 3.3 (Delisted Detection), 8.1 (Symbol Onboarding), 8.2 (Symbol Offboarding)

---

## Why bundle

These three items share the same concerns:
- Archive routing logic (must stay consistent with `db_archive_sector.py`)
- `symbols_klmn800.py` source-of-truth edits
- `symbol_metadata` table integrity
- Audit trail / logging
- Idempotency and safe re-runs

Splitting into three PRDs means triplicating this shared plumbing. One feature, one PRD, one tool surface.

---

## Decisions locked in (from brainstorm conversation)

### Stakes & scope
- **Low-stakes, high-value** refinement work. Not mission-critical.
- Good delegation candidate — decisions front-loaded, building can be autonomous.

### Peer mapping (was step 8 of 8.1)
- **Dropped from this feature.** No meaningful peer algorithm exists today. Deferred to a future item — don't block onboarding on it.

### Delisted detection flow (3.3)
- **"More days is better" — prefer accuracy over speed.**
- Two-stage detection, modeled after Ben's manual workflow:
  1. **Stage A (automated):** After 5 consecutive trading-day data failures, queue to autofix as `delisted_suspect`.
  2. **Stage B (autofix agent):** Agent does web research (ticker lookup, news search) to classify cause: *delisted / acquired / merged / ticker change / temporarily halted / unknown*.
  3. **Outcome:**
     - Confirmed dead → offboard (Stage 1 = stop collection, move to purgatory/removed).
     - Ticker change → linked offboard-old + onboard-new.
     - Ambiguous / halted → move to purgatory block in `symbols_klmn800.py` for Ben's review.
     - False positive (just quiet) → log and ignore.
- **N threshold:** 5 trading days. Weekends/holidays don't count.
- **Feasibility:** Good. Autofix framework already does web research for other categories. This is a new `delisted_suspect` category in the same pipeline.

### Offboarding (8.2) — simplified, no manual purge needed
- **Stage 1 (automatic):** Stop collection. Remove symbol from `symbols_klmn800.py` (or purgatory-move). No more data flows in. Reversible.
- **No Stage 2 purge needed.** Production data migrates out naturally via Friday archive tiers (15d/30d/90d). Stale `earnings_upcoming` rows clean themselves once no collector refreshes them (or: add `earnings_upcoming` cleanup to Stage 1 as a quick safe DELETE).
- **Notification:** End-of-day market report section — "Symbol Lifecycle" when anything pending.
- **Archives keep data forever.** Already there, cheap, has historical research value.

### Pre-flight gates (onboarding)
- **Warn and continue.** Don't hard-block.
- Checks: optionability, liquidity floor, already-in-universe, earnings data available, sector resolvable.
- Ben has idiosyncratic reasons for adding symbols — the tool informs, doesn't gatekeep.

### Liquidity warning metric
- Reuse existing `symbol_metadata.py` liquidity tier classification:
  - Ultra Liquid: 10M+ avg daily volume
  - High: 1M–10M
  - Moderate: 100K–1M
  - Low: <100K
- Warn if `avg_volume < 100K` ("same bucket as the 58 symbols in purgatory"). Not a block.
- Note: purgatory criteria from July 2025 were manual with no documented threshold — these tiers are the closest formal metric we have.

### yfinance correction
- Earnings history backfill uses **Tradier `/beta/markets/fundamentals/calendars`**, not yfinance. yfinance's `get_earnings_dates()` is broken for post-May-2025 dates.
- Tool: `data/health/backfill_earnings_tradier.py` (already exists).
- yfinance remains useful for EPS estimates only.

### Archive routing (onboarding)
- Must replicate sector-split logic from `db_archive_sector.py`:
  - Technology → `semiconductors.db` / `software.db` / `technology.db` depending on industry
  - Consumer Cyclical → `retail.db` / `travel_leisure.db` / `consumer_cyclical.db`
- Import routing logic directly rather than duplicate it.

### FM baseline on onboarding
- `fm_baseline_generator.py` already supports `--symbols ACME` (single-symbol mode works out of the box).
- **Include in onboarding sequence** — no extra code needed, just call `generate_baselines(symbols=['ACME'])`.
- Also run any other ad-hoc data population steps (same philosophy: onboard = fully populate, not "wait for Friday").

### Ticker change handling (V1)
- Offboard old symbol + onboard new symbol as linked lifecycle events.
- No historical data rewriting — old-ticker data stays as-is in archives.
- Lifecycle events table creates the breadcrumb trail (`rename_from: OLD`, `rename_to: NEW`).
- Auto-rewrite of `symbol` columns across tables = Phase 2, only if need emerges.

### Batch onboarding
- **No batch mode.** Interactive-only for V1.

### Half-onboarded failure recovery
- **Warn and expect manual cleanup.** The system populates itself naturally — a half-onboarded symbol will fill in its gaps on next OP/EI/FM cycle. Simplest approach, matches current behavior.

---

## UX design

> "Is this an automated behind-the-scenes project? a TUI feature? part of the main.py workflow? its own interactive script?"

**Answer: Different parts live in different places.** One conceptual feature, three invocation surfaces.

### Surface 1: Interactive CLI — `tools/symbol_lifecycle.py`
Primary human entry point. Onboarding and manual offboarding review.

**Onboarding flow (expected UX):**
```
$ python tools/symbol_lifecycle.py --add ACME

Pinging Tradier for ACME...

━━━ ACME — Acme Corp ━━━
  Sector:       Industrials
  Industry:     Aerospace & Defense
  Market Cap:   $4.2B
  Avg Volume:   1.2M (20d)
  Last Price:   $87.45
  Optionable:   YES (14 expirations available)
  Last Earnings: 2026-02-15

Pre-flight checks:
  [OK]  Optionable
  [OK]  Liquidity: HIGH (1.2M avg volume)
  [OK]  Not already in universe
  [OK]  Earnings data available (Tradier calendars)
  [OK]  Sector resolvable → industrials.db

Add ACME to system? [Y/n]: y

Tier assignment:
  [1] FM_UNIVERSE  (full intraday scan, ~388 symbols)
  [2] DAILY_ONLY   (OP/EI only, ~432 symbols)
Choice [1/2]: 2

Confirm archive routing: industrials.db? [Y/change]: y

Running onboarding steps:
  [1/8] Adding to symbols_klmn800.py                      done
  [2/8] Inserting symbol_metadata + archive routing       done
  [3/8] Backfilling historical_prices (~1 year)           done  (251 rows)
  [4/8] Backfilling earnings_events (Tradier calendars)   done  (8 events)
  [5/8] Computing earnings_moves                          done  (6 moves)
  [6/8] Populating earnings_upcoming (next event)         done  (2026-05-12)
  [7/8] Generating FM baseline                            done  (7-day lookback)
  [8/8] Logging to symbol_lifecycle_events                done

Onboarded ACME. Event ID: 2041
```

**Offboarding review flow:**
```
$ python tools/symbol_lifecycle.py --review

Pending lifecycle actions:
  [1] SEE   — delisted, confirmed by autofix 2026-04-06. Collection stopped.
  [2] HOLX  — acquired by Danaher, confirmed 2026-04-09. Collection stopped.
  [3] AL    — ticker changed → AER, detected 2026-04-11. Propose offboard AL + onboard AER.

These symbols are already in purgatory (collection stopped). Production data
will archive out naturally via Friday tiers. No manual purge needed.

Acknowledge? [y/n]: y
```

**Other manual invocations:**
- `--list` — current state dashboard (active, purgatory, recently onboarded/offboarded)
- `--restore SYMBOL` — pull back from purgatory into FM_UNIVERSE or DAILY_ONLY

### Surface 2: Behind-the-scenes (no TUI, no prompts)
- **Collector failure tracking:** OP/FM collectors flag symbols with consecutive failures. Writes to a tracking table (or lightweight counter). Autofix consumes on nightly run.
- **Autofix `delisted_suspect` handler:** Does web research. Classifies. Moves to purgatory in `symbols_klmn800.py` and logs lifecycle event. No data deletion.

### Surface 3: Notification
- **End-of-day market report** — new "Symbol Lifecycle" section when anything pending/changed.
- Morning View TUI integration deferred (not V1).

---

## Audit trail — new table

**Table: `symbol_lifecycle_events` in `datalake.db`**

| Column | Type | Notes |
|---|---|---|
| event_id | INTEGER PK |  |
| symbol | TEXT | Indexed |
| event_type | TEXT | `onboarded`, `offboarded`, `purgatory_added`, `purgatory_restored`, `suspect_queued`, `suspect_classified`, `rename_from`, `rename_to` |
| event_date | DATE | Trading day of event |
| event_timestamp | TIMESTAMP |  |
| tier | TEXT | `fm_universe`, `daily_only`, `purgatory` (state at time of event) |
| reason | TEXT | Free-form or controlled vocab |
| operator | TEXT | `human` or `autofix` or `collector` |
| metadata_json | TEXT | Full context (what was backfilled, web research summary, linked events, etc.) |

Queryable history of every symbol decision. Supports "why was X removed?" and "when did we add Y?" months later.

---

## Open questions (resolved)

| # | Question | Answer | Source |
|---|---|---|---|
| A | Delisted threshold | 5 trading days | Ben (round 2) |
| B | Notification surface | End-of-day market report | Ben (round 2) |
| C | Ticker change V1 | Offboard + onboard, linked events, no data rewrite | Claude proposal, Ben silent approval |
| D | Batch mode | No | Ben (round 2) |
| E | Liquidity thresholds | Reuse symbol_metadata tiers, warn at <100K avg volume | Codebase investigation |
| F | FM baseline gap | Run baseline ad-hoc during onboarding (already supported) | Ben pushed back, generator already supports it |
| G | Half-onboarded failure | Warn + manual cleanup, system self-heals on next cycle | Ben (round 2) |
| H | Data retention | Archives forever, production archives out naturally | Ben (round 2) |

---

## Remaining open questions

### I. Automated symbol discovery (future)
- **Out of scope for V1** but should be tracked in `big-to-do-list.md` as a future item.
- Potential: scan IPO calendars, new options listings, or detect symbols appearing in Tradier data that aren't in our universe.
- Ben flagged as "very interesting."

### J. `symbols_klmn800.py` programmatic editing
- Onboarding/offboarding need to **edit a Python source file** to add/remove symbols from list literals.
- Options:
  - AST manipulation (parse the file, modify the list, rewrite). Robust but complex.
  - Regex/string replacement (find the list block, insert alphabetically). Simpler but fragile.
  - Move symbol lists to a data file (JSON/TOML) that Python imports. Cleanest long-term but a refactor.
- **Decision needed.** This affects implementation complexity significantly.

### K. How does autofix agent actually do web research?
- Need to verify: does the current autofix framework have web search capability, or would `delisted_suspect` be the first handler that needs it?
- If web search isn't wired up, this becomes a prerequisite task.

---

## Architecture sketch (rough)

```
tools/
  symbol_lifecycle.py          # Main CLI entry point
  lifecycle/
    __init__.py
    onboarding.py              # add + backfills + metadata + baseline
    offboarding.py             # stage 1 (stop collection, purgatory move)
    detection.py               # failure tracking, autofix bridge
    routing.py                 # imports db_archive_sector logic
    preflight.py               # optionability, liquidity, existence checks
    audit.py                   # symbol_lifecycle_events writer
    ui.py                      # interactive prompts, tables, progress display

autofix/
  handlers/
    delisted_suspect.py        # new category handler (web research + classify)
```

Integration points (existing code we touch):
- `core/symbols_klmn800.py` — writes to FM_UNIVERSE / DAILY_ONLY / purgatory blocks
- `data/health/backfill_earnings_tradier.py` — called for earnings history
- `data/tradier_historical_backfill.py` — called for price history
- `strategies/flow_monitor/fm_baseline_generator.py` — called for ad-hoc baseline
- `strategies/*/op_collector.py`, `fm_collector.py` — emit failure events
- `tools/autofix.py` — new category registration
- `main_runners.py` — end-of-day report lifecycle section

---

## What's NOT in scope (V1)

Explicitly out to prevent scope creep:
- Peer mapping algorithm (separate future item)
- Ticker change auto-rewrite of historical data
- Batch/CSV onboarding
- Morning View TUI lifecycle screen
- Automated discovery of new symbols (future item — tracked in big-to-do-list)
- Manual data purge workflow (production archives naturally)

---

## Next steps

1. Resolve remaining questions J–K.
2. Any further brainstorm rounds Ben wants.
3. Promote to PRD via `/create-prd`.
4. Generate task list via `/generate-tasks`.
5. Build in supervised overnight sessions with dry-run-first on every destructive step.
