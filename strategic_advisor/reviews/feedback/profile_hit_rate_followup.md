# Follow-up: Profile Hit Rate Research (Observation 011)

**Date:** 2026-04-19
**From:** Ben (via Claude Code session)
**Status:** Good work, needs one more pass

---

## What You Proved

You rigorously debunked the 83% claim as a quality signal — profile calls don't outperform non-profile calls. That was honest, well-controlled analysis. The statistical significance testing was exactly what I asked for.

## What's Still Exciting

Even though the profile doesn't *outperform*, the absolute numbers are striking: 82.5% of evaluated profile calls (and 91.7% of non-profile calls) hit 25% theoretical max within 7 days. If that holds up, FM alerts are a genuine edge — I just follow every alert, set a limit order at 25%, and win most of the time.

## What I Need You to Dig Into

The "theoretical max" caveat is the gap. `max_prof_7d_pct` measures the peak price the option touched at ANY point in 7 days. That could be a 5-minute spike at 2 AM or a sustained move lasting hours. The practical question:

1. **How long does the 25% window stay open?** When an alert's option hits 25% profit, does it stay above 25% for minutes, hours, or days? If it's a brief spike, limit orders won't reliably fill. If it persists, this is a real strategy.

2. **When does the peak typically occur?** Day 1? Day 3? Day 7? The data from Session 002 showed 39% hit 25% on Day 1. Can you break this down further — what % hit it by Day 1, Day 2, Day 3, etc.?

3. **What happens to the ~38% of alerts that aren't evaluable?** Are these likely losers (expired worthless, fell out of scan range) or just missing data? If they're mostly losers, the true hit rate drops from 82.5% to ~50%. If they're random noise, 82.5% holds.

4. **What's the realistic capture rate?** If you set a limit sell at 25% on every profile alert at entry, how often would it actually fill based on the price trajectory data in `flow_options_scans`?

5. **Evaluate the evaluator.** We're relying on `fm_evaluator.py` to tell us how alerts perform, but has the evaluator's methodology itself been validated? Why do 38.5% of alerts have no evaluation data? Understand the specific reasons — expired before next scan, fell outside ±20% strike range, no matching contract in `flow_options_scans`, something else? Most importantly: **are the unevaluated alerts systematically different from the evaluated ones?** If the evaluator disproportionately drops losers (e.g., options that went to zero quickly and stopped appearing in scans), then every hit rate we've calculated is inflated by survivorship bias. This isn't a minor detail — it's the foundation. If the evaluator is painting a rosy picture by only measuring survivors, our 82.5% number is meaningless. And if that's what you find — that the evaluator IS broken — then say so plainly. Accept the existing results as unusable, propose a fix to the evaluator, and we rerun it to get correct numbers. Don't try to salvage the current data or work around the bias. Fix the instrument first, then measure.

This is the most important research thread right now. If you can demonstrate that FM alerts reliably hit 25% in a capturable way AND that the evaluator isn't systematically biasing the results, that's the system's proof of concept — everything else is optimization.
