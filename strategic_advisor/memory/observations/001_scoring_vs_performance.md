# Observation: Alert Scoring Inversely Correlates with Performance

**Session:** 001 (2026-04-17)
**Status:** Finding documented, needs deeper analysis (see A1 on agenda)
**Confidence:** Medium — strong quantitative signal but confounders not yet controlled

## The Data

### By Score Band (alerts with 7d profitability data)
| Score Band | Alerts | Avg Max 7d Profit | Win Rate (>=25%) |
|------------|--------|-------------------|-----------------|
| 3.5-4.0 | 51 | 145.9% | 76.5% |
| 4.0-5.0 | 40 | 105.9% | 82.5% |
| 5.0+ | 1,747 | 70.1% | 67.7% |

### By Alert Level
| Level | Alerts w/ Data | Avg 7d | Avg 7d Loss | Avg Score |
|-------|---------------|--------|-------------|-----------|
| HIGH | 125 | 54.0% | -17.6% | 8.31 |
| MEDIUM | 1,713 | 74.4% | -17.4% | 6.49 |

### By Scoring Version
| Version | Level | Alerts w/ Data | Avg 7d | Win Rate |
|---------|-------|---------------|--------|----------|
| v1 | HIGH | 112 | 53.6% | 67.0% |
| v1 | MEDIUM | 1,622 | 71.4% | 67.6% |
| v2 | HIGH | 13 | 58.1% | 84.6% |
| v2 | MEDIUM | 91 | 128.3% | 79.1% |

## Potential Confounders

1. **Time period:** v2 (3.5-5.0 band) is almost entirely April 2026. Market conditions matter.
2. **DTE distribution:** Short-DTE options have higher % gains. If lower-scored alerts cluster at shorter DTE, that explains the inverse.
3. **Option price:** Cheaper options have higher % swings. Lower-scored alerts may target cheaper names.
4. **Sample size:** 3.5-5.0 band has only 91 alerts. 5.0+ has 1,747. Hugely different samples.

## Next Step

Control for DTE: within the 15-30d DTE band (largest sample), does score still inversely predict?
Control for time: within March 2026 (v1 scoring only), does the pattern hold?

## Why This Matters

If the scoring system is genuinely not predictive (or inversely predictive), then:
- The v3 design should weight the bonus factors much more heavily than planned
- Or the fundamental score formula needs reworking, not just augmentation
- Ben's time reviewing HIGH alerts is potentially worse-spent than reviewing MEDIUM alerts
