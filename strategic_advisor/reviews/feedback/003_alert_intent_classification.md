# Feedback on Proposal 003: Alert Intent Classification

**Date:** 2026-04-18
**From:** Ben (via Claude Code session)
**Status:** Tier 1 approved with caveats, Tier 2 encouraged for deeper proposal, Tier 3 declined

---

## Tier 1: V/OI Intent Tag

**Verdict: Approved — implement it.**

This is a shorthand for mental math I already do, and turning numbers into words is a genuine UX improvement. As long as the labels are accurate, this is worth adding. It's not groundbreaking, but it addresses a real weakness and could improve decision speed. I wouldn't have gone after this myself because it seemed like too much effort for the apparent gain — but the agent's analysis makes it clear the effort is tiny and the accuracy is high.

**One important caveat:** `[LIKELY CLOSING]` at 51% is misleading. That's a coin flip, not "likely" anything. Most of my trouble comes from exactly this ambiguous bucket, and V/OI alone can't solve it. The real answer requires deeper analysis:
- When was the existing position built?
- Has the position gained value (profit-taking) or declined (cutting losses, buying the dip)?
- Did similar-sized flow appear at a different strike or expiration (rolling)?
- What's the OI trajectory on this contract over recent days?

So Tier 1 scratches the surface of the intent problem. The `[LIKELY CLOSING]` label specifically may need a more honest name — `[MIXED INTENT]` or `[CHECK OI]` — since 51% is not "likely" anything. The high-confidence labels (`[NEW POSITION]` and `[LIKELY NEW]`) are solid.

**Action:** Implement as proposed, but rename the low-V/OI ITM label to something that doesn't overstate confidence. Consider this a v1 of intent classification, not the final answer. The harder problem (the ambiguous bucket) deserves its own research thread.

---

## Tier 2: Roll Detection

**Verdict: Encouraged — but needs a deeper, PRD-ready proposal.**

This is exactly the kind of thing that's too complex for me to program without sinking significant thought into it. If roll detection can be put into the code and done right, it would be a big win. The VST and CTRA examples are compelling evidence.

**What I need from you:** A proposal detailed enough to kick off a PRD process. Not necessarily 100% complete, but enough that a Claude Code session with PRD tools can:
- Ask me deliberate clarifying questions
- Research the implementation path
- Design the detection algorithm with edge cases considered
- Build it incrementally with testing

The scan-data approach (same symbol, same expiration, same type, adjacent strikes, comparable volume, one leg V/OI < 1.5) is a good starting point. But consider:
- What about rolls across expirations (not just strikes)?
- Time window — must both legs appear in the same scan, or within N minutes?
- How to present it — flag the alert? suppress it? add context?
- False positive rate — how many non-roll patterns match these criteria?

This is the kind of work I struggle to articulate well enough to start a PRD. If you can get it to the point where a PRD session can take off, that's extremely valuable.

---

## Tier 3: Time-of-Day Tag

**Verdict: Declined.**

I already check time of day on alerts, but mainly for freshness (how old is this alert?), not because morning alerts are inherently better. Your own analysis showed hit rates are flat across time slots. No need to add a tag for something with no demonstrated correlation.

---

## A Note on the "Counterintuitive Finding" (CLOSING ≈ BUILDING hit rates)

I'm skeptical of findings that compare across the full historical dataset. The system has changed significantly over time — scoring v1 vs v2, data integrity issues, schema changes, the OP timing bug (morning pipeline starting before OI data updates, so first ~10 minutes of symbols get previous day's OI, making "next day OI" columns show neutral when they shouldn't). Data quality is improving but older data has real problems.

This doesn't mean your finding is wrong — it might be structurally true. But I'd trust it more if you could reproduce it using only v2 alerts (April 2026+) or at least control for data vintage. The system from 6 months ago was very different from today.

This is actually one of the reasons I value having you analyze the system — you're surfacing exactly these kinds of data quality concerns that I know exist but can't always articulate or quantify.

---

## Overall

This proposal has the strongest evidence base of the four. The V/OI structural logic (closing means OI already exists, so volume can't exceed it) is elegant and clearly correct. Tier 1 is worth implementing now. Tier 2 (roll detection) is the highest-potential enhancement you've identified — invest in making it PRD-ready.
