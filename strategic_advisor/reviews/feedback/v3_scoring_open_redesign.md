# Note: v3 Alert Scoring — Open to Redesign

**Date:** 2026-04-19
**From:** Ben (via Claude Code session)

---

The v3 scoring design doc (`docs/alert_scoring_v3_design.md`) represents my initial thinking, but I'm 100% open to it being redesigned and improved by you if you think it's improvable. Don't treat the existing design as fixed — treat it as a starting point.

Your observation 012 (factor-by-factor review) is exactly the right approach. You've now accumulated significant evidence across 6+ sessions about what actually predicts alert quality: DTE dominance, score-magnitude inverse, V/OI as intent (not quality), flow concentration noise, call vs. put asymmetry.

If you believe the v3 design should be different from what's currently spec'd, propose a redesign. It should represent the lessons we've learned together about alerts, tradability, and what success looks like. I'd rather have a v3 that's informed by real data analysis than one that just implements my initial guesses.
