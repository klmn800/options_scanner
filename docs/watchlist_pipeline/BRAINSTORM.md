# Watchlist Pipeline — Brainstorm & Design Notes

**Project:** Enhance the watchlist system from flat signal lists into a multi-tier pipeline
that guides the user from signal discovery through investigation to active position tracking.

**Status:** Brainstorming (2026-03-14)
**Related to-do items:** 2.1, 6.3, 6.4, 6.5, 6.6

---

## The Problem

The system generates good signals (flow alerts, earnings intelligence) but the path from
"interesting signal" to "trading decision" requires too much manual work — SQL queries, DB
Browser, mental bookkeeping. There's no structured way to investigate a signal, decide it's
worth tracking, and then monitor it with enriched context over time.

---

## The Three-Level Funnel

### Level 1 — Discovery (Automated Feeds)

**What it is:** Automated, broad signal feeds populated by the system. The user reviews these
to find symbols worth investigating.

**Existing tables:**
- `flow_watchlist_daily` — One row per symbol per day that had flow alerts. 7-day rolling
  window. Tracks price movement vs entry, dip detection, alert sentiment (building/closing/
  neutral from next-day OI resolution). ~21 active entries.
- `earnings_watchlist` — Curated earnings opportunities. WATCH/BUY/STRONG BUY signals within
  14 days of earnings. Lifecycle: UPCOMING -> TODAY -> T+1 -> T+2 -> T+3 -> deleted. ~6 entries.

**Current workflow:**
- User checks flow_watchlist_daily for unusual activity over past few days
- User checks earnings_watchlist for upcoming earnings with strong signals
- Most entries get mentally dismissed
- A few catch the eye and need deeper investigation

**Potential enhancement — Cumulative Volume Flags (item 2.1):**
Could feed into flow_watchlist_daily (with a note that it's accumulation, not a burst) or
become its own Level 1 source. See "Volume Accumulation" section below for research needs.

**Key principle:** Level 1 should stay lean. Its job is "here are the symbols, go look." Don't
overload it with investigation data.


### Level 2 — Investigation (On-Demand Analysis)

**What it is:** Tools for evaluating a signal from Level 1. The user asks specific questions
and gets answers to decide whether to promote the symbol to Level 3 or dismiss it.

**Design principle:** Each investigation tool should answer a SPECIFIC QUESTION, not dump data.
The user works through a short checklist and makes a decision.

**The Questions:**

#### Q1: "Is this signal real — did people commit capital, or was this just day trading?"
- **Core data:** Next-day OI change on the alerted contracts
- **Already exists:** `flow_alerts` has `oi_change_contracts`, `oi_change_pct`, `oi_resolution`.
  `flow_watchlist_daily` has `alert_sentiment` summary (building/closing/neutral).
- **Goes deeper:** Knowing ONE contract is closing doesn't tell the full story. What about
  other contracts on the same symbol? If the $12 call is closing but the $14 call is building
  heavily, that's a thesis shift, not an exit. Need symbol-level OI change across the chain.
- **Multi-day view:** OI trajectory over 3-5 days for active contracts. Steady growth =
  position building. Spike then flat = one-time event.

#### Q2: "What does the positioning look like — what can I infer about who's doing this?"
- **What we CAN'T see:** Individual trade sizes (Tradier gives aggregate volume, not prints).
  The closest proxy is flow_options_scans snapshots — seeing volume jump between cycles gives
  a rough sense of burst size.
- **What we CAN see:** Contract characteristics (DTE, delta, moneyness), volume concentration
  (one strike vs scattered), premium magnitude, timing of OI building.
- **The progression view:** Seeing how an option's OI and volume evolved over time (from
  flow_options_scans intraday snapshots and option_contracts daily snapshots) tells a story.
  When were the positions built? At what stock price?

**IMPORTANT — Predictive vs Chasing is flawed:**
  The current v_oi_timing_context classifies OI as PREDICTIVE (bought calls when stock was
  lower) or CHASING (bought calls when stock was higher). This is wrong for a key reason:
  buyers aren't psychic. A stock can dip after they buy — that doesn't mean they were chasing.
  They bought when they thought it was a good entry. Post-purchase price movement is not
  related to the quality of the thesis. The classification should be REMOVED or heavily
  rethought. What IS useful: knowing the stock price at time of OI build, to understand the
  lifecycle and context. Just don't moralize it as "smart" vs "dumb."

#### Q3: "Why might this be happening — what's the context?"
- Earnings date proximity (from `earnings_upcoming`)
- Recent news sentiment (from `news_symbol_sentiment`)
- Sector peer movement (from `market_daily_summary` sector ETFs)
- Recent price action (from `historical_prices`)
- This is enrichment/context, not a standalone view. Could be a panel or sidebar.

#### Q4: "What's it going to cost me, and when do I get out?"
- **Entry evaluation:** Breakeven, time pressure, bid-ask spread, premium cost. The
  `earnings_scenario.py` CLI tool handles this well. `v_option_comparison` partially covers it.
- **Exit signals (equally important):** Once holding a position, what tells you to sell? OI
  closing on your contract, thesis invalidation (stock moves wrong way past a threshold),
  profit target hit, IV crush approaching, time decay accelerating. Without exit signals,
  you're left holding the bag.
- Entry and exit are two halves of the same question. Deferred for now but essential for
  Level 3 — an Active Watch list without exit guidance is only half useful.

**Comparison to existing views:**
- `v_morning_discovery` — tries to do discovery AND investigation. Muddled purpose.
- `v_symbol_oi_detail` — 50+ column data dump. Answers no specific question.
- `v_oi_timing_context` — partially answers Q2 but with a flawed classification model.
- `v_option_comparison` — answers Q4 reasonably well.
- `v_live_market_snapshot` — market context, useful but not investigation-specific.

**Recommendation:** Rethink Level 2 tools around the question framework. Existing views have
useful computations that can be salvaged, but the organizing principle should change from
"here's a slice of data" to "here's the answer to your question."


### Level 3 — Active Watch (Curated, Enriched, Persistent)

**What it is:** A small, user-curated list of symbols being actively tracked toward a trading
decision. Enriched with real-time context. Supports notes, status tracking, and dismissal.

**DOES NOT EXIST YET.** This is the main deliverable of this project.

**Architecture: Table + View split**
- **Table** (user decisions, persistent): symbol, status, source, notes, dates
  - Status: watching / ready_to_buy / position_open / dismissed
  - Source: flow_alert / earnings / manual / accumulation
  - Notes: free text ("IV buildup looks early, waiting for BUY signal upgrade")
  - Dates: added_date, status_changed_date, source_date
  - Small — maybe 5-15 symbols at a time
  - Could evolve `user_watchlist` or be a new table

- **View** (market context, computed fresh on every query):
  Joins the table with summary tables to provide:
  - Current stock price (tradeability check)
  - IV percentile (cheap or expensive options?)
  - Today's call vs put volume and vs baseline (directional lean, activity level)
  - Earnings proximity (catalyst timeline)
  - Recent alert count and pattern (one-off or sustained interest?)
  - Put/call OI ratio (sentiment)
  - Any cumulative volume flags from 2.1
  - Volume concentration by top strikes (where's the action?)

**Key design goal:** "Least columns possible to tell the richest story." Every column must
help make a decision. If you can't explain what you'd DO differently based on a column's
value, it shouldn't be there.

**Interaction (TUI):**
- Promote from Level 1 (flow_watchlist_daily or earnings_watchlist) with one keypress
- Add notes explaining why you're watching
- Change status as thesis evolves
- Dismiss with reason tag (hedge, closed position, lost conviction, too expensive)
- View chain context inline (Q1/Q2 investigation without leaving the screen)


---

## Volume Accumulation Research (Item 2.1)

### The Core Idea
Detect gradual volume/OI accumulation that never triggered a burst alert. Both intraday
(steady buying throughout a day) and multi-day (steady OI growth over 3-5 days on the same
contracts).

### Architecture Decision
- **Evening OP** does the discovery (has end-of-day volume + historical baselines)
- **FM snapshots** provide the narrative (intraday timeline for flagged contracts)
- **Multi-day:** `option_contracts` already tracks OI per contract per day — look at OI
  trajectory over rolling 5-day windows

### The Signal Problem — RESEARCH BEFORE BUILDING
A simple volume/OI threshold will generate massive noise. The goal is finding smart money
(people who know what's going to happen), not just popular options. High volume/OI does NOT
mean the trade will win.

**Hypotheses to test against historical data:**
1. **OI confirmation:** Volume without next-day OI increase = day trading, not positioning
2. **Contract profile:** 30-45 DTE, near ATM, reasonable delta = institutional characteristics.
   Weekly deep OTM = lottery tickets. Does contract profile correlate with outcome?
3. **Concentration:** All volume on 1-2 strikes = conviction. Spread across many = hedging or
   market-making. Does concentration correlate with directional moves?
4. **Premium magnitude:** $2M on one strike vs $2M across 40 contracts. Size as signal.
5. **Multi-day OI trajectory:** Steady OI growth on same contracts over 3-5 days, especially
   without the stock moving much yet. Is this predictive?
6. **Retrospective validation:** Find historical cases where we KNOW the outcome (big earnings
   surprise, takeover, material news) and work backward. Were any of these patterns visible
   beforehand in our data?

**Research approach:** Query sector archives for historical cases. Compare options activity
before known-outcome events vs random periods. This is a data science exercise, not a
feature build.

### How It Feeds the Funnel
- Could populate `flow_watchlist_daily` with a flag (accumulation, not burst)
- Could be its own Level 1 feed
- Also enriches Level 3 — if a symbol on Active Watch had unusual accumulation today, show it
- The right answer depends on the research findings


---

## View Refresh for Evening Use (Part of 6.6)

The SQL views (v_morning_discovery, v_symbol_oi_detail, etc.) use a "hybrid timing" pattern:
today's OI (from morning scan) + yesterday's volume/Greeks/prices (complete end-of-day data).
This works at 7:30 AM but is stale by 6 PM.

After the evening OP run, the views should use today's complete data for both OI AND
volume/Greeks/prices. Options:
- Time-detect in the view SQL (check current hour, switch join logic)
- Regenerate views after evening OP run with different join parameters
- Use a config flag that the orchestrator sets after evening OP completes

This is prerequisite for the TUI being useful for evening review sessions.


---

## TUI's Role in the Pipeline

The TUI is the interactive layer for Levels 1-3. Console output handles passive intraday
monitoring; the TUI handles structured review sessions (morning and evening).

**Console during market hours:** Market mood (7.2), flow alerts as they fire, cycle summaries.
Passive — you watch, it reports.

**TUI for review sessions:** Discovery feeds (Level 1), investigation tools (Level 2), active
watch management (Level 3). Interactive — you make decisions, it records them.

**Prerequisite:** 6.6 (TUI Modernization Pass) must happen before building new features.
Includes evening view refresh and schema compatibility audit. Follow with a week of actual
usage to identify real friction before building 6.3-6.5.


---

## User Workflow (To Be Documented)

Ben will track his actual daily trading workflow for a week (~March 17-21, 2026) and take
notes on what he looks at, in what order, what questions he asks, and where friction occurs.
This will validate or revise the three-level funnel model.

Preliminary understanding:
- **Morning:** Check discovery feeds, review overnight OI changes, plan the day
- **During market hours:** Console monitoring, alerts fire passively
- **Evening:** Review what happened today, investigate signals, update active watch
- **Rarely buys same-day** — usually waits for next-day OI confirmation before acting


---

## Decisions Made (2026-03-14)

1. **Three-level funnel** (discovery → investigation → active watch) — APPROVED as framework
2. **Table + View split** for Level 3 — APPROVED (table for decisions, view for enrichment)
3. **Volume accumulation belongs in evening OP**, not FM — APPROVED
4. **Predictive vs Chasing classification is flawed** — NOTED, needs rethink or removal
5. **Research before building** for accumulation signals — APPROVED
6. **Question-driven investigation tools** vs data dumps — APPROVED as design principle
7. **6.6 (modernization + evening refresh) before new TUI features** — APPROVED
8. **Q4 (cost/trade evaluation) deferred** — not a priority yet

## Ideas Explicitly Rejected (2026-03-14)

- IV change alerts as standalone FM feature (belongs in 1.4 for earnings symbols)
- Underlying price momentum in FM (not an options signal)
- Gamma spike detection (not actionable for directional trading)

---

## Open Questions

1. Does Level 3 evolve `user_watchlist` table or need a new table?
2. What columns belong on the Level 3 enrichment view? ("least columns, richest story")
3. Where does cumulative volume surface — Level 1 feed, Level 3 enrichment, or both?
4. What does the investigation toolset actually look like — reworked views, TUI screens, or
   a mix?
5. What does Ben's actual daily workflow look like? (tracking week ~March 17-21)
