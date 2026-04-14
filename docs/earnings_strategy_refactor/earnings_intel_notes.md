# Earnings Intelligence — Ben's Strategy Notes & Vision

**Created**: 2026-02-25
**Purpose**: Articulate how earnings information fits into Ben's trading workflow and what the EI module needs to support it. Working document for the earnings refactor.

---

## How Earnings Fit Into the Strategy

Earnings are one input in a broader swing trading workflow. The goal is not to trade earnings events directly every time — it's to use earnings proximity and dynamics as context that improves decision-making across the portfolio.

Key framing: **I swing trade. I buy options when they are cheap and sell them the very moment they reach my profit targets. I do not necessarily buy at the time of alert. I never hold to expiration. I do not sell options.**

---

## How I Use Earnings Information Today

### 1. Flow Alert Context

When an option volume flow alert fires, one of the factors in deciding whether to follow it is proximity to earnings. Is the alert signaling movement around an upcoming catalyst? This is currently an informal mental check — the system doesn't surface this context automatically.

I don't yet have a sophisticated framework for what to do with that information specifically.

### 2. Deciding Whether to Buy Options Around Earnings

If a symbol has upcoming earnings, the decision is whether and when it's worth buying options. The core logic:

- **Options win when stock price changes significantly, or when IV expands.** The options must have large potential for either (or both) to justify entry.
- **If IV is already high, how much room is left for expansion?** If options are already expensive, how much does price have to move just to break even? (Open question: how do I define "high IV" in a systematic way?)
- **Ideally, you buy at relatively low IV and relatively low price**, maximizing the chance of a profitable swing from either direction or volatility expansion.

### 3. The Market Prices for This

IV is naturally part of options pricing, and earnings are predictable events that investors bid up in advance. The market tends to reach a balance point. **You want to get in before that point** — but knowing when that is requires understanding the dynamics.

### 4. Models for Earnings Moves

At a basic level, several factors inform what happens around earnings:

1. **Company doing well** — price tends to rise on optimism heading into earnings, then either reverts to mean or continues if results are strong.
2. **Company struggling** — minimal pre-earnings activity, potential drop on weak results.
3. **Uncertainty** — can cause more dramatic post-earnings swings due to surprise factor.
4. **Historical move patterns** — past moves inform market maker expectations and option pricing. The market is imperfect, so sometimes "arbitrage" opportunities exist where the market underprices the typical move.
5. **Industry knock-on effects** — DAL reports strong earnings and forecast, UAL and AAL may see sympathy moves.
6. **Other factors** — these assumptions are not rules. The reality is much more complex.

### 5. The Gamble

The fundamental unknown is whether a company will beat, meet, or miss expectations. Better inputs lead to better guesses:

- Analyst expectations
- Company fundamentals and data
- News sentiment (and article content — not just scores)
- Industry-specific environmental factors (jet fuel prices, seasonal travel, etc.)
- The better one is at estimating the effect of future earnings, the more successful the trades

### 6. Straddle Plays

A straddle-type play can be a good strategy for earnings — capitalizing on volatility rather than direction. This aligns with the existing [Earnings Straddle Playbook](EARNINGS_STRADDLE_PLAYBOOK.md).

### 7. Timing and Discipline

- **Directional bets**: best entered a few days before earnings, sold just before. Others do this too, so you sometimes see the price drop on the day of — don't want to miss the exit window.
- **Discipline**: You will constantly be tempted to hold out for a better price. Sell once profit targets are reached.
- **Profit target calibration**: Deciding what profit targets should be is part of the gamble. Understanding expected move, the magnitude and effect of IV change, and earnings projections could help maximize this — but this isn't fully understood yet.

---

## Workflow Vision

### What I Want the System to Do

1. **Useful earnings-related flags** — not just standalone alerts, but contextual flags that enrich other signals (e.g., flow alerts near earnings).

2. **Earnings alerts send symbols to watchlist** — when the system identifies an earnings opportunity, it should land on a watchlist, not just flash on the console at 5 PM.

3. **Watchlist enriched with earnings data** — all watchlist entries (from any source — flow alerts, earnings signals, manual adds) should show relevant earnings context: days to earnings, BMO/AMC, expected move, historical average, signal, IV status.

4. **Agents evaluate watchlist for opportunities** — automated analysis layer that scores and ranks candidates based on the factors described above.

5. **Morning briefing from agents** — a synthesized, actionable report delivered before market open.

6. **I sit down and review reports before market open** — the final step is human review and day planning. Possibly through Morning View, but not necessarily right now.

---

## Developer Notes, Suggestions & Questions

*Comparing Ben's vision above with the current state of the refactor ([RESEARCH_AND_FINDINGS.md](RESEARCH_AND_FINDINGS.md)) and the [EI README](../../strategies/earnings_intel/README.md).*

### What Aligns Well

- **P1 (Stale Data)** directly blocks everything. False alerts at 700-7600% underpricing make all downstream use unreliable. The recommended Option A fix (filter, don't delete) is a one-line change that unblocks the rest.

- **P2 (Morning Delivery)** maps directly to Ben's "morning briefing" and "review before market open" vision. The research doc identifies four delivery options (console, Morning View, email, all three). Ben's notes suggest console output is the minimum viable path; Morning View is the aspirational one.

- **P3 (BMO/AMC)** is explicitly called out in Ben's timing section. Finnhub integration is researched and ready to implement (Session 3). This directly enables "a few days before earnings" timing decisions.

- **Straddle Playbook** is already documented and validated with the TOST case study. The signal thresholds (WATCH/BUY/STRONG BUY based on relative underpricing) are designed for exactly this use case.

### What's New in Ben's Notes (Not Yet in the Refactor)

1. **Flow alert + earnings context integration** — Ben's #1 use case is checking earnings proximity when a flow alert fires.

   **FINDING**: This already partially exists. `flow_watchlist_daily` has three earnings columns: `earnings_date`, `days_to_earnings`, `earnings_time`. These are populated during watchlist entry creation by `fm_watchlist.py`, which looks up the symbol in `earnings_upcoming`. Currently 86 of 98 watchlist rows have earnings data, and 13 have earnings within 5 days. However, the enrichment is limited to date/time — it does NOT include the signal (`earnings_play_signal`), underpricing (`relative_underpricing_pct`), or expected move (`expected_move_pct`). And `earnings_time` is always "Unknown" (the Finnhub gap).

   *Question: Is "flow" watchlist the right place, or is another watchlist table preferred? What is the top level watchlist? See Ben's answer to Q2 below for the `earnings_watchlist_daily` concept.*

2. **"High IV" definition** — Ben asks "how do I know high IV?" systematically.

   **FINDING**: IV percentile already exists and is actively working across the system:

   | Table | Column | Window | Coverage |
   |-------|--------|--------|----------|
   | `option_contracts` | `iv_percentile_20day` | 20-day rolling | 615K rows |
   | `option_symbol_summary` | `symbol_iv_percentile_30d` | 30-day rolling | 11.8K rows |
   | `airline_symbol_tracking` | `iv_percentile_30d` + per-DTE bucket | 30-day | 394 rows |

   **Calculation** (in `op_storage.py` and `op_symbol_rollup.py`): `percentile = (count of historical IVs below current IV) / total days * 100`. Requires 10+ days for contracts, 20+ days for symbols. Interpretation: 0-25% = IV is cheap (good entry), 75-100% = IV is expensive.

   **Already used in**: Morning View contract analysis, airline strategy, decimal formatting pipeline.

   **For earnings context**: The `symbol_iv_percentile_30d` on `option_symbol_summary` directly answers "are this stock's options cheap or expensive right now?" This can be pulled into the earnings watchlist to inform entry timing. A symbol with earnings in 5 days AND IV at the 25th percentile is a much stronger setup than one at the 85th percentile.

   *Assessment: The metric exists, is correctly calculated, and is available. The gap is that it's not surfaced alongside earnings signals. The new `earnings_watchlist_daily` table (see Q2) should include this.*

3. **Watchlist as the central hub** — Ben envisions earnings signals feeding INTO the watchlist, not living in a separate earnings-only view. Today, `flow_watchlist_daily` is populated by flow alerts and enriched with news sentiment. Earnings signals live in `earnings_upcoming` — a separate table with no connection to the watchlist. The vision implies either: (a) earnings signals create watchlist entries, or (b) the watchlist queries both tables and presents a unified view.

   *Question: Should earnings candidates (WATCH+ signals within 7 days) automatically create `flow_watchlist_daily` entries? Or should a unified watchlist view pull from multiple sources? See also the Questions from #1 in this list.*

4. **Agent evaluation layer** — Ben mentions "agents evaluate watchlist for opportunities." This is beyond the current EI refactor scope but worth noting as the downstream consumer. The bones of this have been laid in a previous project that was paused to focus on building infrastructure to feed those agents information.

5. **Profit target calibration using expected move and IV dynamics** — Ben acknowledges this isn't fully understood yet. The scenario calculator proposal (`earnings-scenario-calculator-proposal.md`) addresses part of this — modeling hold-through-earnings vs sell-before decisions. The `move_vs_expected_pct` field (currently 100% NULL — see Q7 in research doc) would provide the historical validation data needed.

### Watchlist Architecture Discussion (from Q2)

Ben's answer to Q2 crystallizes an important design principle: **earnings opportunities should be treated as first-class alerts, not secondary enrichment on flow alerts.** The system should have two investor-facing watchlist tables, each fed by a different detection strategy:

| Table | Fed By | Detects | Model |
|-------|--------|---------|-------|
| `flow_watchlist_daily` | Flow Monitor alerts | Unusual options activity (someone is betting) | Existing, working |
| `earnings_watchlist_daily` (new) | Earnings Intelligence signals | Underpriced earnings moves (market is mispricing) | To be built |

**Why two tables instead of one:**
- Flow alerts are reactive — something happened (unusual volume). Earnings signals are proactive — something is about to happen (earnings date approaching with cheap options).
- Ben wants to catch opportunities BEFORE flow volume appears. An earnings signal might fire 5 days before earnings, and the flow alert might not come until 1-2 days before (or not at all).
- Each table has its own natural columns. Flow watchlist cares about alert counts, significance scores, sentiment. Earnings watchlist cares about expected move, underpricing, IV percentile, BMO/AMC timing.

**What `earnings_watchlist_daily` would look like** (modeled after `flow_watchlist_daily`):
- **Entry criteria**: WATCH+ signal, earnings within 5 trading days, OI >= 4000
- **Key columns**: symbol, entry_date, earnings_date, days_to_earnings, earnings_time (BMO/AMC), expected_move_pct, historical_avg_move_pct, relative_underpricing_pct, earnings_play_signal, iv_percentile_30d, straddle_price, plus news sentiment enrichment
- **Lifecycle**: Created when a symbol first enters the 5-day window with a qualifying signal. Updated daily. Archived or deleted after earnings pass.
- **Fed by**: The daily pipeline (evening) and optionally a morning refresh

**Future consolidation**: A view or lightweight table could unify both watchlists for agent consumption and morning briefing. But even without that, having two focused tables that Ben checks each morning is manageable and clean.

**This is a key deliverable for the refactor.**

---

### Open Questions for Ben

1. **Priority ordering**: The refactor research doc has P1-P7 prioritized. Your notes suggest flow-alert-earnings integration may be equally important to morning delivery (P2). Where does cross-strategy enrichment fall in your priority list?
A: We're doing a comprehensive refactor; if its a priority, we want it done. The order is not important except for dependences, I think.

2. **Watchlist architecture**: Do you want earnings candidates to literally appear on `flow_watchlist_daily` alongside flow-originated entries? Or is a separate "earnings watchlist" acceptable as long as it's visible in the same morning workflow?
A: Great question. Very much worth a discussion. Leaving it in flow_watchlist_daily is easy and places key information in reach of a table used to make decisions, but it also means that flow alerts drive the watchlist, which is not exactly what I want. If an opportunity exists before volume flow happens, I want to bethere, that's the acme of excellence in this system should we be able to do that. So in the principle of treating earnings alerts with the same priority as flow alerts, a new table for earnings alerts is probably in order. In this model, our DB has a number of tables for collecting and analyzing data that are used to flag (alert) symbols as worth looking into, and two tables for storing and displaying those symbols worth looking into for easy reference. Probably will want at some point another table or view to consolidate that further, but maybe not. Even having just two tables that, as an investor, I need to look at to be informed is enough to manage. The other tables serve as reference when I need to dig deeper. Thoughts? flow_watchlist_daily would be a model for, say, earnings_watchlist_daily

3. **IV assessment**: Would an IV percentile metric (e.g., "NVDA IV is at the 35th percentile of its 90-day range") be useful, or do you assess IV intuitively based on experience?
A: We probably have this somewhere, I believe in the option_symbol_summary table - dive into it and make sure it is what we need and the code that calculates it is accurate for our needs.

4. **Agent scope**: When you say "agents evaluate watchlist for opportunities" — are you thinking of Oracle-style Claude API analysis, or rule-based scoring, or both?
A: We have the bones of this somewhere. We stopped to build infrastruture to feed this. What that means is, not worth thinking too much about now, the goal is to display data in a way that makes it easy for agents to access and analyze.

5. **How far out do you look?** You mention "a few days before earnings" for directional bets. For the morning briefing, should the system show earnings within 3 days? 5 days? 7 days? The straddle playbook says 5 trading days; your notes seem to suggest similar.
A: Five trading days seems appropriate. I'm sure there's an industry standard we should consider; I'm sure there's an evidence based answer we'll seek out later once this is built.