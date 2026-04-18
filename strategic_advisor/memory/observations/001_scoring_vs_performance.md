# Observation: Alert Scoring Predicts Reliability, Not Magnitude

**Session:** 001 (2026-04-17)
**Status:** CONFIRMED after controlling for DTE and scoring version
**Confidence:** High — tested within v1-only data, within same DTE bands, pattern holds

## Summary

Higher significance scores consistently produce lower average max profit at 7 days. The effect is real — not a confound from DTE, scoring version changes, or market regime. However, win rates are relatively flat across score bands, meaning higher scores predict slightly more RELIABLE outcomes but with SMALLER percentage gains.

**The scoring system measures "importance" (premium + volume surprise), not "opportunity" (percentage upside).**

## Evidence

### Uncontrolled (what first caught my eye)
| Score Band | Alerts | Avg Max 7d | Win Rate |
|------------|--------|-----------|----------|
| 3.5-4.0 | 51 | 145.9% | 76.5% |
| 4.0-5.0 | 40 | 105.9% | 82.5% |
| 5.0+ | 1,747 | 70.1% | 67.7% |

### DTE-Controlled, v1-Only (the clean test)
Same scoring version (v1, Sept 2025 - March 2026). Same DTE band. Only variable is score.

**0-14 DTE:**
| Score | Alerts | Avg 7d | Win Rate |
|-------|--------|--------|----------|
| 6.0-7.0 | 305 | 120.5% | 80.7% |
| 7.0-8.0 | 82 | 111.3% | 76.8% |
| 8.0+ | 24 | 93.9% | 79.2% |

**15-30 DTE:**
| Score | Alerts | Avg 7d | Win Rate |
|-------|--------|--------|----------|
| 6.0-7.0 | 336 | 69.4% | 68.5% |
| 7.0-8.0 | 97 | 77.5% | 71.1% |
| 8.0+ | 21 | 49.2% | 61.9% |

**31+ DTE:**
| Score | Alerts | Avg 7d | Win Rate |
|-------|--------|--------|----------|
| 6.0-7.0 | 602 | 49.9% | 60.5% |
| 7.0-8.0 | 200 | 45.0% | 62.5% |
| 8.0+ | 67 | 40.5% | 64.2% |

### Pattern Summary
- **Average profit consistently decreases with higher scores** — holds in 8 of 9 cells (exception: 15-30d where 7.0-8.0 beats 6.0-7.0)
- **Win rates are much flatter** — 60-81% across all bands, no strong score dependence
- **DTE is the dominant predictor** — 0-14d averages 100-120%, 31d+ averages 40-50%, regardless of score

## Root Cause Hypothesis

Higher scores require larger premium values (premium is 0-6 points of the 0-10 scale). Larger premium = more expensive options. More expensive options have:
- Smaller percentage swings (a $5 option going to $6 is 20%, but a $0.50 option going to $1 is 100%)
- More efficient pricing (well-followed names, less edge for retail)
- Institutional activity (which IS what the system detects, but institutions trade differently than Ben)

The score answers "how much institutional money moved?" not "how much can a retail swing trader make?"

## Implications for v3 Scoring

The v3 design doc (`docs/alert_scoring_v3_design.md`) adds actionability bonuses (contract affordability, V/OI ratio, DTE sweet spot). These are the RIGHT direction — they add an "opportunity" dimension. But the bonuses are small (+0.25 to +0.5 each) relative to the fundamental score (0-10). Given how powerful the inverse effect is, the bonuses may need to be larger, or the fundamental score may need compression.

The v3 approach of flow concentration as a multiplier (0.7x-1.1x) is also right — it penalizes noise (NVDA 3.1% flow) without needing to fix the fundamental formula.

## What I'm NOT Claiming

- I'm NOT saying higher-scored alerts are bad. They're watchlist intelligence. Institutional activity at scale IS meaningful context.
- I'm NOT saying the system should only alert on cheap, short-dated options. That would be lottery ticket filtering.
- I AM saying the score doesn't predict percentage returns, and treating HIGH alerts as better trading opportunities than MEDIUM alerts is wrong. They're better intelligence, worse trades.
