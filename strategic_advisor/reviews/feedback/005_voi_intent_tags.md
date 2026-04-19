# Feedback on Proposal 005: V/OI Intent Tags

**Date:** 2026-04-18
**From:** Ben (via Claude Code session)
**Status:** Declined

---

## Decision

Not implementing. The high-confidence tags (`[NEW POSITION]`, `[LIKELY NEW]`) are accurate but don't add enough value beyond what I can already see from the V/OI number that's already displayed on the alert line. The ambiguous bucket (`[CHECK OI]` covering ~40% of alerts) is the real problem, and tagging it "check OI" is just restating "I don't know" — which is distracting rather than helpful.

The underlying research (V/OI as intent predictor) is solid and valuable. But the display change isn't worth the console clutter. The deeper problem — understanding intent for the ambiguous low-V/OI bucket — requires the kind of analysis you outlined in Proposal 003 feedback (position age, P&L trajectory, OI trends, roll patterns). Tags can't solve that.

## What To Do Instead

- Keep the V/OI research as a foundation for the roll detection work (Proposal 007)
- Consider whether V/OI could be an input to v3 scoring rather than a display tag
- The intent classification problem is real — it just needs a deeper solution than labels
