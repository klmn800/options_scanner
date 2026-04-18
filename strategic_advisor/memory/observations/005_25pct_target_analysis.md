# Observation: Alert System Achieves Ben's 25% Profit Target with High Reliability

**Session:** 002 (2026-04-18)
**Status:** Confirmed for April 2026 data (v2 era). Small sample, needs more months.
**Confidence:** Medium — strong pattern but only ~3 weeks of v2 data

## Summary

In the v2 era (April 2026), 79% of alerts with profitability data achieved >=25% max profit within 7 days. Call alerts with 0-30 DTE hit 25% over 90% of the time. 39% of all alerts hit 25% on Day 1 alone.

## Evidence

### Overall April 2026 (v2)
- 111 alerts with 7d data
- 88 hit 25% target (79.3%)
- Avg max 7d profit: 115%

### Time to Target
| When First Hit 25% | Alerts | % | Avg Max 7d |
|--------------------|--------|---|-----------|
| Day 1 | 43 | 39% | 156% |
| Day 2-3 | 14 | 13% | 92% |
| Day 4-7 | 31 | 28% | 144% |
| Never | 23 | 21% | 12.5% |

### Best Profile for Ben (25% target within 7 days)
| DTE | Type | N | Day 1 Rate | Week Rate |
|-----|------|---|-----------|-----------|
| 0-14d | Call | 29 | 37.9% | **93.1%** |
| 15-30d | Call | 21 | 52.4% | **90.5%** |
| 31d+ | Call | 41 | 36.6% | 80.5% |
| 31d+ | Put | 15 | 26.7% | 40.0% |

### By Option Type
- Calls: 86.8% hit rate (79/91), avg max 132%
- Puts: 45.0% hit rate (9/20), avg max 37%

## Implications

1. **The alert system works.** It generates real value for Ben's trading style.
2. **Calls dominate.** Puts in April 2026 dramatically underperform — likely market-regime-dependent (bull market).
3. **Short DTE is the sweet spot.** 0-30 DTE calls have 90%+ hit rates. This reinforces the Session 001 finding that DTE is the strongest predictor.
4. **15-30 DTE has the best Day 1 rate (52.4%)** — the option is close enough to expiration for gamma to amplify moves but far enough for time value to remain.
5. **This is theoretical max.** A trader won't capture 25% on every alert that theoretically reached it — they need to be watching, enter at the right time, and exit at or near the peak.

## What I'm Uncertain About

- **Market regime dependency.** April 2026 was likely a favorable month for calls. Would puts outperform in a downturn? **Session 003 update:** Confirmed the alert mix is regime-driven. Early April (VIX ~25): 37-55% puts. Late April (VIX 17.5): 96% calls. The 90%+ call hit rate may reflect a bull market, not a universal property.
- **Survivorship in the data.** The evaluator only tracks contracts where it can find price data (58% coverage). The missing 42% might be worse performers.
- **Practical capture rate.** 25% theoretical max does NOT mean 25% realized. Need to think about what a disciplined trader would actually capture. This connects to B1 (Theoretical Evaluation Enhancement) on the agenda.

## Future Use

This analysis framework is useful for:
- Tracking v2 performance month-over-month
- Comparing against historical v1 data
- Calibrating actionability bonuses in v3 scoring
- Potentially: building a "signal card" that shows "alerts like this hit 25% X% of the time in Y days"
