# Options Scanner — Master To-Do List

> Last reorganized: 2026-04-01

---

## Completed

Items fully done. Kept for historical reference — collapse or skip when reading.

### 1.1 — Earnings Scenario Calculator
- **Status:** DONE
- **Deliverable:** `tools/earnings_scenario.py` (from `docs/earnings-scenario-calculator-proposal.md`)

### 2.2 — Flow Alert Scoring v2
- **Status:** DONE (2026-04-01)
- Smart money score removed entirely (double-counted, no discriminating signal — 58% scored 1.3, 87% 1.1-1.3). Threshold 6.0 → 3.5. HIGH conviction 8.0 → 5.0. `alert_reason` prefixed with `v2|` for version tracking. Volume surprise confirmed as strongest predictor (90% 7d win rate at 50x+). Quality flat 3.5-5.0 (78% 7d win rate). Analysis scripts in `research/alert_*.py`.

### 4.1 — Orchestrator Logging Refactor
- **Status:** DONE (2026-02-19)
- Full orchestrator refactor. See `docs/main_orchestrator_refactor/`.

### 4.2 — Text Log Sanitization (P1-P5)
- **Status:** DONE (2026-03-13)
- 5 fixes: emoji stripping, blank line suppression, duplicate removal, subprocess timestamp/banner cleanup. 713 noise lines/day → 0.
- Files: `log_utils.py`, `fm_alert_resolver.py`, `main_runners.py`. Design docs: `docs/orchestrator_text_log_refactor/`.
- **Deferred items:** P6 (coffee break noise), P7 (wait repeats), P8 (morning views dump).

### 5.0 — KLMN800 Two-Tier Symbol Architecture
- **Status:** DONE (2026-03-16)
- 820 symbols organized by PURPOSE: FM_UNIVERSE (388 intraday) + DAILY_ONLY (432 for OP/EI).
- File: `core/symbols_klmn800.py`. FM uses `get_specialty_list('fm_scan')`, everything else uses `get_specialty_list('klmn_800')`.
- Impact: ~53% fewer option chains per FM cycle. Full decision log: `memory/fm_universe_trimming_2026-03-16.md`.

### 5.1 — Symbol Role Architecture
- **Status:** ADDRESSED (80/20 done)
- Two-tier FM/Daily Only split is the pragmatic version. Full formal role tagging remains a possible future refinement.

### 5.2 — Scan Time Management
- **Status:** ADDRESSED
- FM went 820 → 388 symbols, roughly doubling cycle frequency. Further optimization possible via bid-ask spread filtering or additional pruning.

### Decided Against (2026-03-14)
These were considered under Flow Monitor enhancements and explicitly rejected:
- **IV change alerts** — Not independently actionable. The *why* matters more than the *what*. IV tracking for earnings symbols covered by item 1.4.
- **Underlying price momentum** — FM is an options system, not a stock screener. Not an options signal without IV context.
- **Gamma spike detection** — Not actionable for directional trading. Academic interest only.

---

## Ben to Review / Revisit

Items with a scheduled review date. Check these when the date arrives.

### 2.3 — Review v2 Alert Scoring & Begin v3 Design
- **Review:** April 10, 2026 (one week of v2 data)
- Walk through a week's worth of alerts. Are HIGH alerts (5.0+) genuinely better quality? Is 3.5 threshold too low/high? Is flow concentration filtering out mega-cap noise? Collect "should have been higher" and "shouldn't be here" examples.
- **v3 design doc:** `docs/alert_scoring_v3_design.md` — two-tier scoring (fundamental + actionability bonus), flow concentration as Tier 1 multiplier, V/OI + DTE + price + IV percentile as Tier 2 bonuses.
- **Full v2 review:** May 2026. Compare v1 vs v2 using `alert_reason` prefix (`v2|` = new scoring).
- Reference scripts: `research/alert_scoring_simulation.py`, `alert_directional_quality.py`, `alert_premium_vs_wins.py`, `alert_no_smart_money.py`, `alert_threshold_bands.py`.

### 4.2 — Verify Text Log Sanitization Results
- **Review:** Was March 19 — **OVERDUE, check now**
- Verify `orchestrator_*.log` has 0 emoji lines, 0 duplicates, 0 double timestamps, 0 banners, 0 blank lines.

### 5.3 — Incremental Peer Group Audit
- **Review:** June 2026 (parental leave)
- Audit peer groups one industry at a time as earnings approach. Use `industry_peer_mappings` (742 symbols) and `symbol_metadata` as starting points.
- Don't start until a full earnings season of `earnings_sector_effects` data has accumulated (~March-June 2026).
- Feeds into 1.3 (arbitrage scanner) and 5.1 (role architecture).

---

## In Progress — Pending Actions

Started but not finished. Each has a clear next step.

### 1.3 — Earnings Sector Peer Arbitrage Scanner
- **Status:** Post-earnings pipeline FIXED (2026-03-12). Pre-earnings scanner still DISABLED.
- **What was fixed:**
  - 4 snapshot queries switched from `event_id` (always NULL) to `earnings_date` (populated)
  - Weekend gap: T+3 query changed from `= 3` to `BETWEEN 3 AND 10` with `NOT EXISTS`
  - `clean_database_row` nullification bug fixed for string fields
  - `earnings_sector_effects` now populating (first rows: MDB + 3 peers)
- **Still disabled:** Pre-earnings morning scanner (`ei_arbitrage_scanner.py`) is commented out in `ei_main.py` (lines 421-451). Needs historical correlation data — now accumulating naturally.
- **Next action:** Uncomment pre-earnings scanner after ~1-2 months of data (est. **May 2026**). Consider targeted symbol adds to `DAILY_ONLY` to flesh out sector/industry peers. Foundation for 1.4.

### 1.5 — Backfill earnings_moves
- **Status:** IN PROGRESS (2026-04-13)
- **Root cause found:** `cleanup_tier3_production()` was deleting `earnings_events` and `historical_prices` from production after 90 days. Post-earnings calc couldn't find source data for Q3-Q4 2025 earnings because it had been purged.
- **Fix applied (2026-04-13):** Added `skip_cleanup: True` to both tables in Tier 3 config. They still get COPIED to sector archives (DR), but no longer DELETED from production.
- **Restoration tool:** `data/health/restore_from_archives.py` — copies 27K earnings_events + 665K historical_prices back from sector archives into production. INSERT OR IGNORE (idempotent). Run after main.py.
- **Done previously:** Dec 2025-Feb 2026 backfilled (581 rows, 94.5% with IV) via `ei_backfill_dec_feb.py` (2026-03-02).
- **Restoration COMPLETE (2026-04-13):** Archive restoration (27K events, 665K prices) + yfinance backfill (35K events, 10K moves). earnings_events: 602→63,128. earnings_moves: 9,926→20,194. Symbols with 6+ quarters: 706→744.
- **Remaining gap:** Q3-Q4 2025 (~800 events) — yfinance/Finnhub don't have this data. Going-forward pipeline will capture future quarters naturally.
- **Tools:** `data/health/restore_from_archives.py` (archive→production), `data/health/backfill_earnings_yfinance.py` (yfinance historical dates + move computation).

---

## To Do — Not Yet Started

### Symbol Lifecycle Management

#### 8.1 — Symbol Onboarding Tool
- `tools/onboard_symbol.py` — interactive script to properly add a new symbol to the universe.
- **Steps:**
  1. Add to `symbols_klmn800.py` (ask: FM_UNIVERSE or DAILY_ONLY)
  2. Fetch & insert `symbol_metadata` immediately (sector, industry, market cap via Tradier)
  3. Set `archive_db` routing in metadata based on sector mapping
  4. Backfill `historical_prices` (Tradier historical endpoint, ~1 year)
  5. Backfill earnings history via yfinance (dates, estimates, timing)
  6. Compute `earnings_moves` from backfilled data
  7. Populate `earnings_upcoming` with next earnings date
  8. Insert `industry_peer_mappings` based on industry
  9. Print summary of everything set up
- Should support batch mode (`--symbols ACME,NEWCO,XYZ`) for adding multiple at once.
- Inverse of 3.3 (delisted detection). Together they form full symbol lifecycle management.

#### 8.2 — Symbol Offboarding / Cleanup (extension of 3.3)
- When 3.3 detects a delisted symbol, beyond removing from `symbols_klmn800.py`:
  - Clean `earnings_upcoming` (stale future dates for dead symbols)
  - Clean `flow_watchlist_daily` (open watchlist entries that will never resolve)
  - Optionally purge recent production data (option_contracts, flow_options_scans) for the symbol to avoid noise
  - Archive routing becomes irrelevant — data already archived stays, new data stops flowing
  - Log the removal with reason (acquired, merged, delisted, ticker change) for audit trail
- Keeps the database clean of ghost data from symbols we no longer track.

### Earnings Strategy

#### 1.2 — Straddle Tactics for Earnings Intel
- Enhance Earnings Intel to consider straddle tactics.
- Reference: `EARNINGS_STRADDLE_PLAYBOOK.md`

#### 1.6 — Recency-Weighted Historical Average Move ✅ DONE (2026-04-13)
- Switched from all-time `AVG(ABS(move_1day_pct))` to recent-6Q average. `historical_avg_move_pct` now holds 6Q value (signal driver). All-time stored in `historical_avg_move_alltime_pct` for transparency. `historical_quarters_used` shows data depth (1-6). Config: `earnings_play.recent_quarters` (default 6). 51 symbols changed signal in first 30-day window analysis.
- Files changed: `ei_moves_upcoming.py`, `ei_collector.py`, `ei_backfill_dec_feb.py`, `config.json`.

#### 1.7 — Intraday OHLC-Based Expected Move (Deferred to Q3 2026)
- Use `max_intraday_move_pct` (high/low extremes) instead of or alongside `move_1day_pct` (close-to-close) for historical average move calculation.
- Rationale: Ben's trading style sells at intraday extremes — a 10% intraday swing that settles to 2% at close is still a win. Close-to-close understates the actual trading opportunity.
- Data shows intraday max averages ~1.8x the close-to-close move (10.44% vs 5.69%) across 5,604 rows with valid data.
- **Prerequisites:** (1) Backfill earnings_moves (item 1.5) to fill 2025-2026 gaps and fix 4,322 rows where `max_intraday_move_pct = 0.0` (bug legacy defaults). (2) Verify how `_calculate_price_moves()` in `ei_post_earnings_calc.py` computes `max_intraday_move_pct` — confirm it's measuring peak deviation from previous close. (3) Consider that straddle expected move is priced to close, so comparing intraday historical vs close-based expected creates an apples-to-oranges issue.
- **Decision needed:** Use intraday as signal driver (replacing close-to-close), as secondary display, or as a separate signal.

#### 1.4 — Real-Time Earnings Signal Tracking
- Wire FM to recompute straddle underpricing each cycle for symbols in `earnings_upcoming`.
- Detect intraday signal upgrades (WATCH → BUY, BUY → STRONG BUY) as IV fluctuates.
- Track window open/close. Needs: FM cycle integration, `earnings_upcoming` live update, alerting when thresholds cross.
- IV change detection for earnings symbols lives here, not in FM (decided 2026-03-14). Related to 1.3.

### Flow Monitor Strategy

#### 2.1 — Cumulative Volume Tracking
- **Status:** Concept approved, research phase needed before building.
- **Design doc:** `docs/watchlist_pipeline/BRAINSTORM.md` — full Watchlist Pipeline vision (three-level funnel, investigation framework, volume accumulation research needs). Items 2.1, 6.3-6.6 are all part of this larger project.

**The problem:** FM detects volume *bursts* between cycles but misses gradual accumulation. A contract could have 100K volume through steady buying all day and never trigger an alert. Institutional desks build positions this way intentionally.

**Architecture decision (2026-03-14):** Discovery scan belongs in the evening Option Pipeline (OP already has end-of-day volume + historical baselines). FM provides the *story* — intraday snapshots show how volume built up. OP discovers, FM narrates.

**Multi-day angle:** Someone could build a position over 3-5 days (2K contracts/day). No single day triggers, but OI trajectory tells the story. We already track OI per contract per day — just not looking at it for accumulation.

**Research needed before building (2026-03-14):**
- OI confirmation: volume without next-day OI growth = day trading, not positioning
- Contract profile: 30-45 DTE near-ATM = institutional. Weekly deep OTM = lottery tickets
- Concentration: one strike = conviction. Many strikes = hedging/market-making
- Premium magnitude: $2M on one strike vs $2M across 40 contracts
- Multi-day OI trajectory: steady growth on same contracts over 3-5 days without stock moving
- Retrospective validation: find historical cases with known outcomes and work backward
- **Do the research before designing the system. Don't build a flag factory.**

Related: Item 6.5 (Chain Context on Flow Alerts) is the TUI display layer for this data.

### Autofix System

#### 3.1 — Autofix Custodian Enhancement
- See: `autofix/custodian_enhancement.md`

#### 3.2 — Autofix Enhancement Ideas
- See: `autofix/enhancement_ideas.md`

#### 3.3 — Delisted Symbol Auto-Detection
- When OP/FM collectors fail to get data for a symbol (no quotes, no option chains, `unmatched_symbols`), track the failure.
- After N consecutive trading-day failures (e.g., 3), queue to autofix as `"delisted_suspect"` category.
- Autofix agent does web research to determine cause (acquisition, merger, delisting, ticker change) and either removes from `symbols_klmn800.py` or moves to a delisted purgatory section for Ben's review.
- Detection signals from Tradier: `unmatched_symbols` (definite), `volume=0 + open=null` on trading days (probable).
- Lightweight — piggybacks on failures already happening in collectors, no extra API calls.
- Origin: SEE/HOLX/EXAS/AL all discovered manually via backfill failures (2026-04-13).

### Morning Views TUI

> The TUI is already substantial (21 screens, 5 database views, watchlist CRUD, capital planner, AI analysis, admin mode). It was built for morning review sessions but hasn't been used recently. May need updating to match current system state. The TUI handles interactive review; console output handles passive monitoring.
>
> **Existing infrastructure:** `user_watchlist` has `user_notes` and `priority` fields with NO UI yet. `v_morning_discovery` filters <$60, scores confluence 0-5, direction bias, earnings context, alert temporal context. OI Distribution + Compare Strikes screens provide chain context. Capital Planner tracks earnings positions. Admin mode allows production DB writes.

#### 6.6 — TUI Modernization Pass (DO THIS FIRST)
- **Prerequisite for 6.1-6.5.** Audit all screens against current DB schema and workflows. Some screens may reference stale columns or miss new data sources.
- Make SQL views time-aware for evening use (currently assume morning timing).
- **After this:** Use the TUI daily for at least a week before building 6.3-6.5. Real usage reveals actual needs.

#### 6.1 — Integrate Earnings System and Calculator into TUI

#### 6.2 — OI Resolution Guessing Game
- **PRD-scale feature** — significantly bigger than 6.3-6.5. Needs its own design cycle.
- Screen shows today's alerts (OI Resolution blank until next day). User guesses Building/Closing/Neutral. Next day shows actual resolution vs guess with scoring. Tracks performance over time. Includes bug report / contest-a-decision feature for model improvement.

#### 6.3 — Alert Dismissal & Curation
- Dismiss/categorize individual flow alerts from Flow Alerts screen (currently read-only).
- Dismiss with reason tag (hedge, position closing, not tradeable, not interested, other).
- Dismissed alerts hidden from default views but preserved in DB.
- Could feed back into smarter filtering over time.
- Decision needed: dismissal columns on `flow_alerts` vs separate tracking table.

#### 6.4 — Watchlist Notes & Priority
- Wire up `user_notes` and `priority` fields that already exist in `user_watchlist` but have no UI.
- Low effort — data layer already exists.

#### 6.5 — Chain Context on Flow Alerts
- Lightweight inline preview when reviewing a flow alert: total call vs put volume, volume vs baseline, top 2-3 active strikes.
- "The 30-second picture" before deciding to dig deeper (OI Distribution screen does the deep dive).
- Related: Item 2.1 (Cumulative Volume Tracking) produces the data that feeds this display.

### Console Display Upgrades

#### 7.1 — Multi-Day Data Display
- Display multi-day data with some other data types to show changes over time in the console.

#### 7.2 — Market Mood Per Cycle
- One-line summary each FM cycle describing current market environment. Derived from SPY direction, VIX movement, put/call ratio from scan data.
- Console display only, no DB save. Low effort, high situational awareness.
- Examples:
  - "Buyers in control — SPY climbing, fear low, traders favor calls"
  - "Defensive — SPY falling, fear rising, heavy put buying"
  - "Choppy — SPY flat, mixed signals, no clear direction"
  - "Volatility expanding — big swings expected, fear spiking"
