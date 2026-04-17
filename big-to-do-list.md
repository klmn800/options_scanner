# Options Scanner — Master To-Do List

> Last updated: 2026-04-16

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

### 8.1 — Symbol Onboarding Tool
- **Status:** DONE (2026-04-16, PRD 0013)
- `python tools/symbol_lifecycle.py --add SYMBOL` — full interactive flow: Tradier API fetch (quotes + fundamentals + expirations + calendars), symbol card display, pre-flight checks, tier selection, archive routing, 7-step backfill (metadata, prices, earnings events, earnings moves, upcoming, FM baseline, audit event).

### 8.2 — Symbol Offboarding / Cleanup
- **Status:** DONE (2026-04-16, PRD 0013)
- `python tools/symbol_lifecycle.py --offboard SYMBOL` — confirms active tier, warns on protected status, prompts reason, moves to purgatory, cleans earnings_upcoming, logs audit event.
- `python tools/symbol_lifecycle.py --restore SYMBOL` — restores from purgatory with tier selection.
- `python tools/symbol_lifecycle.py --list` — universe dashboard (tier counts, protected groups, suspects, recent activity, purgatory residents).
- `python tools/symbol_lifecycle.py --review` — interactive suspect review (offboard/dismiss/skip).

### 3.3 — Delisted Symbol Auto-Detection
- **Status:** DONE (2026-04-16, PRD 0013)
- Phase 6.2 health check detects symbols missing from `option_contracts` for 3+ days (warning) / 5+ days (suspect). 90% safety gate prevents false positives on API outage days. Suspects logged to `symbol_lifecycle_events`, surfaced in end-of-day report "Symbol Health" section. Interactive review via `--review` command.
- **Remaining deferred:** Task 2.6 (human gate — verify DB-backed `get_specialty_list()` over a full trading day), Task 2.7 (remove Python list literals from `symbols_klmn800.py` after verification).

### 1.5 — Backfill earnings_moves
- **Status:** DONE (2026-04-13)
- Three-phase effort: archive restoration (27K events, 665K prices) + yfinance backfill (35K events, 10K moves) + Tradier calendars backfill (Q1-Q4 2025 + Q1 2026). Final: 64,389 events, 21,919 moves, 97.1% coverage at 5+ quarters.

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

---

## To Do — Not Yet Started

### Symbol Lifecycle Management

#### 8.3 — Automated Symbol Discovery (Future)
- Scan IPO calendars, new options listings, or detect symbols appearing in Tradier data that aren't in our universe.
- Suggest candidates for onboarding via end-of-day report or lifecycle review queue.
- Human-initiated onboarding only — discovery just surfaces candidates, doesn't auto-add.
- **Prerequisite:** 8.1 (onboarding tool) — DONE.
- Brainstorm origin: symbol lifecycle management brainstorm session (2026-04-16).

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

#### 1.8 — IV Ramp Tracking for Earnings Watchlist
- **Status:** Deferred — collecting data this quarter, build after earnings season (~Q3 2026).
- **Goal:** Show how much IV has ramped so far vs. historical pattern, so Ben knows if it's "too late" to buy premium.
- **Key finding (2026-04-14 audit):** `iv_front_month` is the right metric, NOT `iv_30dte`. Front-month captures earnings premium concentration; 30dte dampens the signal by blending expirations. DAL example: iv_30dte *declined* 15% into earnings while iv_front_month showed classic ramp-and-crush.
- **Data available:** `earnings_snapshots` already collects `iv_front_month` + `iv_30dte` daily for T-7 to T+5. 136 symbols have 3+ pre-earnings snapshots. Sector archives have ~9 months of daily `option_symbol_summary` IV data for retroactive curve building.
- **Proposed metrics:**
  - `iv_ramp_pct`: current `iv_front_month` vs T-7 value (simple ramp measurement)
  - IV term structure slope: `iv_front_month / iv_30dte` — values above 1.3-1.5x = earnings premium fully priced
  - Per-symbol "typical ramp profile" computed from historical snapshots + archived `option_symbol_summary`
- **Prerequisites:** ~50-100 more earnings events for meaningful per-symbol profiles. Data accumulating naturally through snapshot collector.
- **No external data needed** — our own snapshots + archives are sufficient.

#### 1.4 — Real-Time Earnings Signal Tracking
- **Status:** DONE (2026-04-17)
- FM cycle sub-step recomputes straddle underpricing from live `flow_options_scans` data, compares to morning baseline in `earnings_upcoming`, logs signal upgrades/downgrades to console.
- Runs every N cycles (default 4, ~hourly) to manage query cost. Starts on cycle 2.
- Console only — no DB writes, no email alerts. Deduped per session.
- Config: `flow_monitor.earnings_signal_tracking` — `enabled`, `max_days_ahead` (30), `check_interval_cycles` (4).
- Output includes straddle dollar price + underlying price for quick RH comparison.
- File: `strategies/flow_monitor/fm_earnings_signals.py`. Reuses `determine_earnings_play_signal()` from `ei_moves_upcoming.py`.

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
