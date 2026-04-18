# Observation: The Decision Gap — Signals to Trades

**Session:** 003 (2026-04-18)
**Status:** Confirmed — analysis complete, proposal written
**Confidence:** High (system output fully mapped, quantitative evidence)
**Proposal:** 002_decision_gap.md

## Summary

The system excels at signal discovery (16 alerts/day, earnings watchlist, dip detection) but provides minimal decision support after a signal fires. The path from "interesting signal" to "should I buy this?" requires significant manual work outside the system. The data needed to bridge this gap already exists in the database but isn't surfaced.

## Evidence

### What Ben sees at alert time
- Symbol, strike, type, DTE, volume (surprise multiple), OI, V/OI, last price, underlying, IV%, IVP, score, flow%, alert reason
- **NOT shown:** delta, gamma, theta, vega, bid-ask spread, concentration score, moneyness, surrounding strike context, historical performance context

### What Ben sees on earnings watchlist
- Symbol, days to earnings, time, signal, underpricing%, historical move, straddle move, IV percentile, IV change 5d, price, OI balance, volume balance
- **NOT shown:** data freshness (option data age), straddle confidence level, historical signal performance

### What the TUI offers (but may not be used)
- 9 screens: My Watchlist, Symbol Discovery, Earnings Calendar/Browser, Symbol Detail (hub), OI Distribution, OI Timing, Capital Planner, Flow Alerts
- End-of-day report: 4 sections (Market Summary, Flow Activity, Earnings Outlook, System Performance)
- TUI "hasn't been used recently" per big-to-do-list

### Quantified gaps
- 4/15 BUY/STRONG BUY signals are based on stale/illiquid data — invisible to user
- Greeks (delta, theta) collected but never shown — critical for entry decision
- 90%+ hit rate for calls ≤30 DTE — never communicated at alert time
- BUY signals 3/3 beating straddle — no running scorecard visible

## Root Cause

Not a single design flaw — it's an organic growth pattern. The system was built bottom-up: data collection → alert generation → evaluation. The "top" of the funnel (user decision support) was left for later. The Watchlist Pipeline brainstorm (March 14) identified this correctly but the vision is blocked by TUI modernization (6.6).

## Key Insight

The right answer isn't "build more infrastructure." It's "surface what already exists at the right moment." The data is there — delta, theta, historical profiles, data freshness, signal performance. Three targeted console enhancements could bridge the gap while the larger pipeline vision develops.

## Usage Evidence (Session 003 investigation)

**Ben is a console-first user.** Evidence:
- `user_watchlist`: 27 entries, ALL from October 2025. Zero notes. All priority=0. Untouched for 6 months.
- Morning View TUI: "hasn't been used recently" (big-to-do-list)
- Workflow tracking week (March 17-21): unclear if it happened. No notes found.
- Console output (FM alerts, earnings watchlist, EOD report): actively generated every day
- `flow_watchlist_daily`: 9-18 entries/day, auto-populated
- `earnings_watchlist`: 26 entries, auto-maintained

**Implication:** Enhancements to the console surface (which Ben reads) will be used. Enhancements to the TUI (which Ben doesn't currently use) may not be. The Watchlist Pipeline vision requires TUI usage. This is a strategic question worth flagging.

## Implications

1. Enhancement 1 (freshness column) is the highest ROI — prevents false signal investigation, 1 hour of work, on a surface Ben reads daily
2. Enhancement 3 (signal scorecard) builds the feedback loop that's missing — on a surface Ben reads daily
3. Enhancement 2 (alert context line) is the most ambitious but also most debatable — risk of console noise
4. TUI modernization (6.6) may not be the right next step if Ben doesn't use the TUI. Before building TUI features, understand whether Ben WILL use the TUI or whether the pipeline vision should be delivered through console/CLI instead.
5. The Watchlist Pipeline's delivery medium (TUI) might need reconsideration.
