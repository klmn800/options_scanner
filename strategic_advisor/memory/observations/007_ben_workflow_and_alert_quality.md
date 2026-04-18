# Observation: Ben's Actual Workflow and Alert Quality Gap

**Session:** 003 (2026-04-18), from Q&A feedback
**Status:** Key context for all future analysis
**Confidence:** High — direct from Ben

## Ben's Daily Workflow

### Console Usage
- Monitor open in front of him at day job
- Watches semi-continuously, not 100%
- Scrolls up to catch up when attention returns
- Sometimes gets alerts late → possible missed fast-moving opportunities
- **Primary attention:** Earnings display and flow alerts
- Console is THE primary interface. Not TUI, not logs, not DB queries.

### Earnings Signal Response
- Devotes most attention to **STRONG BUY signals**
- Investigation checklist on Robinhood:
  1. Symbol history (price action)
  2. News
  3. Options chain
  4. Popular contracts by OI
  5. Directional cues
- Still learning the earnings signal system — open to best-practice guidance
- This is a MANUAL investigation triggered by the signal. System doesn't pre-package any of this.

### Alert Filtering (CRITICAL FINDING)
- Of ~16 alerts/day, **only 3-4 are worth following** (~20% signal-to-noise)
- Ben mentally filters for:
  - **Closing signals** — existing positions being unwound
  - **Chasing** — buying after the move already happened
  - **Hedging** — protective positioning, not directional conviction
- This mental filtering costs attention and creates decision fatigue
- Would like system-level filtering but worried about removing good signals
- **Wants to do intent classification too** but thought it was too complex at the time
- Two concerns: (a) doesn't know all trader plays to classify, (b) coding complexity may cause false negatives
- **Approach:** research carefully, test retrospectively, don't rush

### Console Verbosity Clarification (Q&A round 2)
- Ben LIKES verbose output when it adds value (context, details, notes)
- The console cleanup was about NOISE (2400 lines of per-symbol logging), not VOLUME
- He scrolls back to see alert details that aren't in the summary
- Enhancement 2 (alert context line) IS welcome if the content genuinely helps
- Key metric: does this line help me decide to investigate or dismiss? If yes, show it.

### The Missing Signals Question
Ben asked: "What if I'm missing things that SHOULD be alerts?"
- Not just about alert quality — also about alert COVERAGE
- Wants to know if the alert criteria are catching the right things
- Would require analyzing flow_options_scans for activity patterns that move stocks but don't trigger alerts
- This is a research project I could do

## Implications for My Proposals

### Reframing Proposal 002
The "decision gap" is real, but the HIGHEST-VALUE intervention isn't "add more information" — it's **"remove noise."** Going from 20% to 50% signal-to-noise would be more valuable than adding context to all 16 alerts.

Enhancement 2 (alert context line) should be reconsidered:
- Adding 16 more lines of output to a console Ben scrolls through = more noise
- Instead: help classify/filter alerts so he only needs to evaluate 6-8

### New Investigation Priority: Alert Intent Classification
Could the system predict at alert time whether activity is:
- **New positioning** (conviction — worth following)
- **Closing** (unwinding — ignore)
- **Chasing** (momentum following — risky)
- **Hedging** (protective — not directional)

Potential heuristics:
- **Closing signals:** V/OI > 1.0 (turnover), OI already very high, declining OI trend
  - **Ben's refinement:** ITM calls (strike < underlying) with high V/OI = likely profit-taking. Intuitive: they're cashing out gains. And Ben wouldn't buy deep ITM anyway, so filtering these doesn't lose good signals.
  - **Caveat (Ben):** Sometimes high volume on top of existing OI could be renewed conviction or chasing, not just closing. Need to distinguish.
- **Chasing:** Stock already moved significantly in same direction as option type (calls on a stock already up 3%+)
- **Hedging:** Puts on rising stocks (protective), far OTM with large notional, part of a spread pattern

Data available: all in flow_options_scans and flow_alerts. V/OI ratio, underlying price vs recent price, option type, moneyness, DTE, volume concentration.

**Ben's guidance:** Think carefully, don't rush. Research with retrospective data before proposing anything. Concern about false negatives is real — removing a good signal is worse than showing a noisy one.

### New Investigation Priority: Gap Analysis (False Negatives)
What are we NOT catching? Research approach:
1. Find stocks that moved >5% in a day (from historical_prices)
2. Check if we had flow alerts in the 1-3 days before
3. If not, check flow_options_scans for unusual activity that didn't cross the 3.5 threshold
4. Identify patterns that should have been flagged

This is a high-value research project I could do with my database access.

## Offboarding Data Architecture Note
- Offboarding removes symbols from `symbol_metadata`, which may break archive routing (`archive_db` column)
- Original design: keep data for historical analysis
- Ben now questioning whether ghost data for untradeable symbols is useful
- Risk: orphaned data in production tables (earnings_upcoming, option_contracts, etc.) that never gets archived
- **Action for me:** Investigate how offboarding interacts with archive routing. Flag if orphaned data is growing.
