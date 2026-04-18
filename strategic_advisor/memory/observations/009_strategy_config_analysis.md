# Observation: Strategy Configuration Analysis (Session 005)

**Date:** 2026-04-18
**Status:** Complete — findings feed into Proposal 004 and v3 scoring review

## Daily Alert Volume (April 2026, 12 trading days)

Average: ~16/day (range 9-27). Ben wants ~4 that are worth acting on.

## Score Band Performance (v2 only, April 2026)

| Band | Total | Evaluated | Avg Max 7d | Hit Rate ≥25% |
|------|-------|-----------|------------|---------------|
| HIGH 5.0+ | 40 | 20 | 54.1% | 80.0% |
| MED 4.5-5.0 | 21 | 10 | 88.4% | 80.0% |
| MED 4.0-4.5 | 52 | 30 | 111.7% | 83.3% |
| MED 3.5-4.0 | 78 | 51 | 145.9% | 76.5% |

**Key finding:** Inverse score-profit relationship CONFIRMED in v2. Higher scores = lower average returns. Hit rates are flat (76-83%). Score doesn't predict success — it predicts option expensiveness.

Raising the threshold would CUT average returns while barely improving hit rate. The 3.5 threshold is the right floor. Noise should be addressed through filtering/tagging, not threshold changes.

## DTE Performance (v2 only)

| DTE Band | Total | Evaluated | Avg Max 7d | Hit Rate ≥25% |
|----------|-------|-----------|------------|---------------|
| 0-14d | 55 | 32 | 248.4% | 90.6% |
| 15-30d | 46 | 23 | 53.7% | 87.0% |
| 31-60d | 90 | 56 | 63.8% | 69.6% |

DTE is the strongest single predictor. 0-14d has 90.6% hit rate and 248.4% avg (gamma effect).

## V/OI Performance (v2 only)

| V/OI Band | Total | Evaluated | Avg Max 7d | Hit Rate ≥25% |
|-----------|-------|-----------|------------|---------------|
| V/OI >= 5 | 57 | 40 | 93.0% | 75.0% |
| V/OI 1-5 | 46 | 34 | 129.2% | 76.5% |
| V/OI < 1 | 88 | 37 | 125.5% | 86.5% |

**Surprising:** V/OI < 1 has the BEST hit rate (86.5%). Intent classification helps thesis confidence, not trade profitability. (See observation 008 — CLOSING and BUILDING have similar hit rates.)

## Ben's Trading Profile

Criteria derived from 6 real trade examples (Session 004):
- Underlying ≤ $50
- Option price ≤ $3.00
- Call option
- DTE 7-60 days

**Daily match count:** 0-7/day, average ~3/day (36 total in April)

**Hit rate of profile matches:** 19/23 evaluated = 82.6% hit ≥25% in 7 days

**Key winners in profile:** KHC (255.6%), SMCI (345.7%), AAL (218.7%), WULF (213.5%), U (152%), NVO (134%), CPNG (122.9%)

## Noise Composition (non-profile alerts: 155/191 = 81%)

| Category | Count | % of Noise | Examples |
|----------|-------|-----------|----------|
| Expensive underlying ($150+) | 59 | 38% | MSTR, NVDA, AMZN, TSM, COIN |
| Mid-range underlying ($50-150) | 46 | 30% | MRVL, INTC, FSLR |
| Expensive options (>$5) | 25 | 16% | Deep ITM, high-IV |
| Puts | 23 | 15% | Intelligence value, not tradeable |

**MSTR alone = 16/191 alerts (8.4%).** Fires 4 alerts in a single day twice. MSTR+NVDA+AMZN = 29 alerts (15%). Flow concentration penalty (v3 design) would address this.

## Most-Alerted Symbols (April 2026)

MSTR (16), MRVL (9), INTC (8), NVDA (7), WULF (7), AMZN (6), COIN (6), XYZ (6), VST (5), DAL (4), FSLR (4)

## Implications for v3 Scoring Design

1. **Flow concentration penalty** — correctly identified as highest-priority v3 change. Would cut MSTR/NVDA/AMZN noise.
2. **DTE bonus too small** — v3 proposes +0.25/+0.5 for DTE sweet spot. Data shows DTE is the strongest predictor (90.6% vs 69.6%). Should be +1.0 at minimum.
3. **Contract affordability bonus** — v3 proposes +0.25/+0.5 for cheap options. Data shows profile alerts have 83% hit rate vs ~79% overall. Worth the bonus.
4. **Don't raise the threshold** — inverse relationship means higher threshold = worse average returns.
5. **Consider tradability highlighting** as an interim step before v3. Simple tag, ~10 lines of code, immediate value.
