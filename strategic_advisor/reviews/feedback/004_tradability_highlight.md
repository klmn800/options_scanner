# Feedback on Proposal 004: Tradability Highlight

**Date:** 2026-04-18
**From:** Ben (via Claude Code session)
**Status:** Not implementing — but the research direction is valuable

---

## The Display Change

**Verdict: Declined.**

`[ACTIONABLE]` is too bulky for the alert line, and a simpler marker (star, bullet) doesn't add enough value — I already mentally filter on price and DTE without needing a tag. With Tier 1 intent tags coming (Proposal 003), stacking more tags creates clutter.

The profile analysis itself (underlying <= $175, option <= $3, call, DTE 7-60) is useful research. But the display change isn't the right output from it.

---

## What I Actually Want: Prove the Hit Rate

You claim 83% hit rate for profile-matching alerts. I'd love to believe that, but I need more rigorous analysis before I trust it enough to act differently. Specifically:

- **Control for data vintage.** Is 83% across all historical data (including v1 alerts with known data quality issues), or does it hold in v2-only (April 2026+)?
- **What's the baseline?** If ALL alerts have a 75% hit rate, then 83% for the profile subset isn't meaningful. What's the delta vs. non-profile alerts?
- **Sample size and confidence.** How many alerts are in the 83% bucket? Is this 83% of 12 alerts or 83% of 200?
- **Define "hit."** Max profit >= 25% within 7 days? At what point in the 7-day window — day 1? day 5? Does this account for the fact that a swing trader needs to actually be watching at the peak?
- **Survivorship.** Are you only counting alerts where profitability data exists (58% coverage), or does the missing 42% skew the result?

If you can demonstrate rigorously that this profile produces statistically significant outperformance vs. the general alert population, that's a genuine signal worth building around — not just a display tag, but potentially a scoring input for v3 or a filter for what even gets shown.

---

## Bigger Question: Should We Show Untradeable Alerts?

You identified that ~10 of ~16 daily alerts don't match my profile. Right now they all display equally. The question isn't whether to *tag* the good ones — it's whether the untradeable ones should display at all, or display differently (dimmed, collapsed, moved to a summary line).

This is a design question worth thinking about. The alert console is my primary interface. If 60% of what scrolls by is stuff I can't or won't trade, that's a UX problem beyond what a tag solves.

I'm not asking you to solve this now. Just consider it as you continue studying the alert system.

---

## Overall

Don't take this as a negative. Your profile analysis was solid work — the data on which alerts I actually follow vs. which I scroll past is exactly the kind of insight I need. The proposal just aimed too small (a display tag) when the finding deserves bigger thinking (what makes a good alert, and should we restructure what gets shown).

Keep asking questions. Your questions_for_ben and observations are genuinely useful — don't hesitate to ask more. The back-and-forth is where the best ideas come from.
