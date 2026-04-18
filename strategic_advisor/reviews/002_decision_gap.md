# Proposal 002: The Decision Gap — Bridging Signals to Trades

**Date:** 2026-04-18 (Session 003)
**Status:** Proposal
**Scope:** Workflow analysis + 3 concrete enhancements
**Effort:** Enhancement 1: ~1 hour. Enhancement 2: ~2-3 hours. Enhancement 3: ~1 hour.

---

## Observation: The System Excels at Discovery but Stops Short of Decisions

The Options Scanner generates excellent signals — 16 alerts/day, earnings watchlist with underpricing analysis, dip detection, OI resolution tracking. It is one of the strongest **discovery** systems I've examined.

But after a signal fires, the path to a trade decision is thin. The system says "look at this" and then stops. The user must switch to Robinhood, check the chart, evaluate the option, and decide — largely without the system's help.

This isn't new information — the Watchlist Pipeline brainstorm (March 14) identified exactly this problem and designed a three-level funnel (discovery → investigation → active watch). That vision is sound. But it's a multi-month project blocked by TUI modernization (item 6.6).

**What I'm proposing:** Three small enhancements that bridge the gap NOW, using existing data, within the current console architecture. Not a replacement for the pipeline vision — a bridge while the larger infrastructure work is in progress.

---

## Evidence: What's Available But Not Surfaced

### 1. Data freshness is invisible
The earnings watchlist shows 15 BUY/STRONG BUY signals. 4 are based on stale option data (5-16 days old). 1 has illiquid ATM strikes. Ben has no way to distinguish real signals from garbage without querying the database himself.

Current state (April 18):

| Symbol | Signal | Underpricing | Option Data Age | Verdict |
|--------|--------|-------------|-----------------|---------|
| EXAS | STRONG BUY | 9,082% | **16 days** stale | FALSE |
| AL | STRONG BUY | 442% | **5 days** stale | FALSE |
| SEE | STRONG BUY | 216% | **9 days** stale | FALSE |
| HOLX | STRONG BUY | 201% | **9 days** stale | FALSE |
| APLS | STRONG BUY | 454% | Fresh but illiquid | SUSPECT |
| UNH | STRONG BUY | 107% | Fresh (1 day) | REAL |
| MMM | STRONG BUY | 68% | Fresh (1 day) | REAL |
| *...10 more BUY/STRONG BUY* | | | *All fresh* | *REAL* |

A simple "days since option data" column would make this instantly visible.

### 2. Greeks are collected but hidden
Flow alerts store delta, gamma, theta, and vega at alert time. None of these are shown in the console alert line. For a swing trader buying options:
- **Delta** tells you directional leverage — "for every $1 stock move, your option moves $0.45"
- **Theta** tells you the daily cost of holding — "$3/day in time decay on a $100 position"
- Both are critical for the entry decision and both are already in the `flow_alerts` table

### 3. Historical performance patterns exist but aren't accessible
From my analysis (Session 001-002):
- DTE 0-30 calls hit Ben's 25% target **90%+ of the time** (April 2026 data)
- DTE 0-14 calls are the sweet spot: 93% hit rate, average peak profit 150.9%
- Puts dramatically underperform calls (45% vs 87% hit rate)
- BUY earnings signals have beaten the straddle 100% so far (3/3, small sample)

None of this context reaches the user at decision time.

### 4. Earnings signal performance is accumulating but not reported
11 events have resolved so far this season. BUY signals are 3/3 beating straddle expectations. WATCH signals are 1/5. This running scorecard would build confidence in which signals to trust, but it's not visible anywhere.

---

## Three Recommended Enhancements

### Enhancement 1: Data Freshness Column on Earnings Watchlist

**Add one column to the existing watchlist table: "Age"** — showing days since the straddle calculation's option data.

| Sym | Days | Signal | Undr% | HistMv | StrdMv | **Age** | IV% | ... |
|-----|------|--------|-------|--------|--------|---------|-----|-----|
| EXAS | 19d | STR BUY | 9082% | 5.5% | 0.1% | **16d** | - | ... |
| UNH | 3d | STR BUY | 107% | 10.8% | 5.2% | **1d** | 72 | ... |

**Implementation:** The `get_straddle_expected_move()` function already queries the latest `trade_date` from `option_contracts`. Store it (or pass it through) and display it. Flag anything >3 trading days as stale.

**Why this first:** It addresses the most critical finding from my investigation — false STRONG BUY signals that could mislead trading decisions this week. It's also the smallest possible change (one column, one query already being run). This complements the staleness guard fix from Proposal 001 — the guard prevents stale data from being stored; the column makes staleness visible even before the guard is in place.

**Effort:** ~1 hour (query modification + column addition to `_render_earnings_watchlist`)

### Enhancement 2: Alert Context Line (Design Discussion)

**Add an optional second line below each flow alert with quick-assess information.**

Current:
```
NVDA [MAG] $150 calls (45d) | Vol: 3,200 (5.2x) | OI: 12,500 | ... | Score: 6.25
```

Proposed:
```
NVDA [MAG] $150 calls (45d) | Vol: 3,200 (5.2x) | OI: 12,500 | ... | Score: 6.25
  Δ: 0.45 | θ: -$0.03/d | Earnings: 12d (BUY) | Profile: 90%+ hit in 7d
```

**What to show on line 2:**
- **Delta (Δ):** Directional exposure — already in `flow_alerts`
- **Theta (θ):** Daily decay cost relative to option price — already in `flow_alerts`
- **Earnings context:** If earnings are within 30 days and signal is WATCH+, show it
- **Profile hit rate:** Based on DTE band + option type, what % of similar alerts achieved 25% in 7 days

**Why this matters:** The first line answers "what happened?" The second line answers "should I act on this?" Currently Ben must mentally evaluate each alert against his trading criteria. This makes the assessment instant.

**Design concern:** ~16 alerts/day × 2 lines = 32 lines vs current 16. Could be noisy. Options:
- Show line 2 only for HIGH conviction alerts (5.0+)
- Show line 2 only for calls with DTE ≤ 30 (the sweet spot)
- Make it configurable (config.json toggle)

**Effort:** ~2-3 hours (data retrieval already exists, needs formatting + profile lookup table)

### Enhancement 3: Weekly Earnings Signal Scorecard in EOD Report

**Add a subsection to the Earnings Outlook section of the end-of-day market report.**

Current Earnings Outlook shows upcoming signals. Proposed addition — a running scorecard:

```
EARNINGS SIGNAL PERFORMANCE (Season-to-date)
  BUY:        3/3 beat straddle (100%)  Avg move: 4.87% vs 3.27% expected
  STRONG BUY: 1/3 beat straddle (33%)   Avg move: 4.61% vs 3.91% expected
  WATCH:      1/5 beat straddle (20%)   Avg move: 2.21% vs 3.26% expected

  Recent: WFC -5.7% (BUY, beat) | MS +4.5% (BUY, beat) | ERIC -6.5% (STR BUY, miss)
```

**Why:** Trust in signals builds through visible track records. Right now, signal performance is invisible — the user must manually check each event. A running scorecard in the daily report creates a feedback loop: signal → event → result → confidence calibration.

**Data source:** `earnings_upcoming` (signal) + `historical_prices` (pre/post close) + `earnings_events` (post-Friday). Can use the same close-to-close calculation I've been running manually.

**Effort:** ~1 hour (query + formatting in the EOD report generator)

---

## What These Do NOT Solve

- **The full investigation workflow (Q1-Q4):** These are console-level improvements, not structured investigation tools. The Watchlist Pipeline vision remains the right long-term answer.
- **Exit guidance:** None of these help with "should I sell?" That remains the biggest gap after "should I buy?"
- **TUI integration:** All three enhancements are console-only. The TUI modernization (6.6) is still a prerequisite for the richer pipeline features.

---

## Relationship to Existing Plans

- **Enhancement 1** is a complement to Proposal 001 Finding 1 (stale straddle fix). The fix prevents future stale data; the column makes current staleness visible.
- **Enhancement 2** aligns with item 6.5 (Chain Context on Flow Alerts) — "the 30-second picture before deciding to dig deeper." This is a lightweight console version of that TUI feature.
- **Enhancement 3** feeds into item C4 (Earnings Signal Threshold Recalibration). Building a visible scorecard now means the data is already organized when recalibration time comes.
- **The Watchlist Pipeline** is the strategic solution. These are tactical improvements for the interim.

---

## Summary

| # | Enhancement | Effort | Impact | Risk |
|---|-------------|--------|--------|------|
| 1 | Data freshness column on earnings watchlist | 1 hour | High — prevents acting on garbage signals | Very low |
| 2 | Alert context line with Greeks + earnings + hit rate | 2-3 hours | Medium — speeds up decision filtering | Medium (console noise) |
| 3 | Weekly earnings signal scorecard in EOD report | 1 hour | Medium — builds signal confidence over time | Very low |

**My recommendation:** Enhancement 1 first (highest impact, lowest risk, immediately useful for this earnings season). Enhancement 3 second (easy, builds foundation for signal evaluation). Enhancement 2 last (needs design discussion about noise tradeoff).
