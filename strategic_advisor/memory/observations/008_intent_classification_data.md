# Observation: V/OI Ratio Predicts Alert Intent

**Session:** 004 (2026-04-18)
**Status:** CONFIRMED — strong quantitative evidence
**Confidence:** High (1,253 resolved alerts, validated against 6 real trades)
**Proposal:** 003_alert_intent_classification.md

## Core Finding

V/OI ratio at alert time predicts next-day OI resolution:

| V/OI Band | BUILDING | CLOSING | NEUTRAL | % BUILDING |
|-----------|----------|---------|---------|------------|
| >= 5.0    | 329      | 0       | 11      | 96.8%      |
| 1.0 - 5.0| 212      | 9       | 34      | 83.1%      |
| < 1.0 ITM | 33      | 108     | 71      | 15.6%      |
| < 1.0 OTM | 182     | 142     | 118     | 41.2%      |

100% of CLOSING alerts have V/OI < 5.0. 96.5% have V/OI < 1.0. This is structural: closing means OI already exists, so volume can't exceed it.

## Additional Feature Analysis

### Moneyness
CLOSING: 43% ITM, 41% OTM. BUILDING: 13% ITM, 72.5% OTM. ITM + low V/OI = likely closing (profit-taking).

### Time of Day
Morning alerts (9:30-10am) have 3.7x avg 7d profit vs afternoon (2-4pm): 191% vs 52%, 91% vs 63% hit rate.

### Multi-Strike Roll Patterns
VST 4/9: $170 CLOSING (V/OI 0.49) + $175 BUILDING (V/OI 4.46), same timestamp
NOK 4/14: $10 CLOSING + $11 BUILDING
LYB 4/8: $70 put CLOSING + $65 put BUILDING
CTRA 4/14: $34 BUILDING (V/OI 517) + $36 CLOSING (V/OI 0.99, not alerted)

### OI Resolution Does NOT Differentiate Profitability
Surprising: BUILDING, CLOSING, and NEUTRAL alerts all have ~70% hit rate at 25% target. CLOSING intent matters for thesis confidence, not trade profitability.

## Ben's Trade Profile (6 Examples)

| Trade | Opt Price | UL Price | V/OI | Outcome |
|-------|-----------|----------|------|---------|
| SLB (win +25%) | $1.89 | $49 | 1.46 | BUILDING |
| DOW (win +23%) | $1.15 | $35 | 4.54 | TBD |
| DVN (win +10%) | $1.37 | $44 | 11.46 | TBD |
| CTRA (loss) | $0.53 | $32 | 517 | NEUTRAL (roll) |
| VST (loss -20%) | $6.50 | $162 | 4.46 | BUILDING (but roll) |
| NU (flat) | $0.66 | $15 | 4.08 | BUILDING |

Pattern: Successful trades have accessible option prices (<$2), underlying <$50, and a clear directional thesis (sector dip). Losses involve rolls or expensive underlyings.

## Gap Analysis Finding (A12)

30% capture rate: Of 60 big moves (>5%) in FM-scanned symbols over 9 trading days, 18 had prior alerts. The 42 misses are mostly macro-driven (tariff selloffs, market-wide moves), not stock-specific flow signals. This is a structural limitation — the system catches stock-specific unusual activity, not market regime shifts.
