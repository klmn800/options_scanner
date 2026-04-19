# Feedback on Proposal 006: EOD Earnings Signal Scorecard

**Date:** 2026-04-18
**From:** Ben (via Claude Code session)
**Status:** On hold — being combined with a larger earnings display redesign

---

## Decision

The scorecard idea is still approved in principle — I want to see signal performance tracked visibly. But there's a related discussion in progress about redesigning the earnings watchlist display:

**The broader issue:** The morning earnings watchlist currently shows both pre-earnings and post-earnings (T+) symbols in the same table. The T+ symbols don't belong in the same view — they need different columns (actual move, IV crush, signal accuracy) rather than pre-earnings columns (underpricing, straddle, IV ramp). The proposal is to split into:
- **Pre-earnings table:** Current watchlist format (signal, underpricing, straddle, etc.)
- **Post-earnings section:** Different columns focused on what happened vs. what was expected

Your scorecard (Proposal 006) is conceptually the *summary* of that post-earnings data. It makes more sense to design these together — the scorecard aggregates what the post-earnings display shows per-symbol.

## What To Do

I'm feeding this to you as a design problem. Consider:
1. How should the morning earnings display split pre vs. post-earnings symbols?
2. What columns belong on each view?
3. Where does the season-to-date scorecard fit — morning display, EOD report, or both?
4. How does the post-earnings display relate to the existing `earnings_moves` data?

If you want to take this on as a research thread and propose a unified design, that would be high value. This is a UX/information-architecture problem more than a coding problem.
