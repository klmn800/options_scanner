> **NOTE:** This is NOT a good example of a proposal. It reads as a findings/analysis report, not a work order. See PROMPT.md for what a proposal should be. Do not use this as a template.

# Proposal 003: Alert Intent Classification — Reducing Noise from 80% to ~40%

**Date:** 2026-04-18 (Session 004)
**Status:** Proposal
**Scope:** New at-alert-time classification heuristic + console enrichment
**Effort:** ~4-6 hours implementation + testing. No schema changes needed.

---

## The Problem

Ben reports that 3-4 of ~16 daily alerts are worth following (~20% signal-to-noise). He mentally filters out closing positions, roll patterns, and late-day chasing. This filtering requires experience and external tools (Robinhood OI chain, next-day resolution). The system has the data to do most of this filtering automatically.

**This is the single highest-value improvement identified across 4 sessions.** It directly reduces the cognitive load of the system's primary output.

---

## What I Found

### 1. V/OI Ratio Predicts Intent with High Accuracy

Analysis of 1,253 alerts with next-day OI resolution reveals that the V/OI ratio (volume / open interest), already computed and displayed at alert time, is a powerful predictor of whether the alert represents new position-building vs closing:

| V/OI Band | BUILDING | CLOSING | NEUTRAL | % BUILDING | Confidence |
|-----------|----------|---------|---------|------------|------------|
| >= 5.0    | 329      | 0       | 11      | **96.8%**  | Very High  |
| 1.0 - 5.0| 212      | 9       | 34      | **83.1%**  | High       |
| < 1.0 + OTM | 182   | 142     | 118     | 41.2%      | Low        |
| < 1.0 + ITM | 33    | 108     | 71      | 15.6%      | Likely Closing |

**Key insight:** 100% of CLOSING alerts have V/OI < 5.0, and 96.5% have V/OI < 1.0. This is structural — closing means the OI already exists, so volume can't exceed it. When V/OI >= 5, you can be 97% confident it's a new position.

**Note on CLOSING profitability:** CLOSING alerts aren't necessarily bad trades (70.4% hit 25% in 7 days vs 71.4% for BUILDING). But they are misleading about intent. Ben's pain isn't about losing money on CLOSING alerts — it's about his thesis being wrong. He thinks "someone is betting on this stock" when actually "someone is exiting their bet."

### 2. Moneyness Adds Discriminating Power

Within the ambiguous V/OI < 1.0 bucket:
- **ITM** options are 51% likely to be CLOSING (profit-taking on positions that moved into the money)
- **OTM** options are only 32% likely to be CLOSING (speculative, could be adding to existing bets)
- **Combined heuristic (V/OI < 1.0 + ITM):** 51% precision for CLOSING, catching 42% of all closings

### 3. Multi-Strike Roll Patterns Are Detectable in Real-Time

Ben's two worst trades (VST -20%, CTRA held too long) both involved roll patterns — institutional positions closing at one strike and opening at another. These are visible in the scan data at alert time:

**VST (4/9):**
- $170 call: V/OI = 0.49. Next day: CLOSING (-4,570 OI, -44%)
- $175 call: V/OI = 4.46. Next day: BUILDING (+4,028 OI, +351%)
- Same timestamp (11:47:20), same expiration, adjacent strikes. Classic roll UP.

**CTRA (4/14):**
- $34 call: V/OI = 517.24 (alert fired). Next day: NEUTRAL (0 OI change)
- $36 call: V/OI = 0.99 (no alert). Next day: closing (15K contracts closing)
- The roll was detectable — $36 had 15,022 volume against 15,240 OI in the same scan.

**Detection algorithm:** When an alert fires, check `flow_options_scans` for same symbol, same expiration, same option type, same scan timestamp. If another strike has comparable volume with V/OI near 1.0, flag as "possible roll."

### 4. Time of Day Strongly Predicts Quality

| Time Slot | N (v2) | Avg 7d Profit | 25% Hit Rate |
|-----------|--------|---------------|--------------|
| 9:30-10am | 56     | 191.4%        | 90.9%        |
| 10-11am   | 58     | 106.3%        | 82.1%        |
| 11am-12pm | 21     | 55.3%         | 69.2%        |
| 12-2pm    | 24     | 113.8%        | 78.6%        |
| 2-4pm     | 21     | 51.7%         | 62.5%        |

**v2-only caveat:** The dramatic v2 morning effect (191% vs 52%) is driven by small samples (33 vs 16 evaluated) and dominated by MSTR/COIN outliers (5 morning MSTR alerts with 391-720% returns). The all-data picture (1,838 alerts) is more nuanced:

| Time Slot | N (all) | Avg 7d Profit | 25% Hit Rate |
|-----------|---------|---------------|--------------|
| 9:30-10am | 243     | 83.8%         | 63.4%        |
| 10-11am   | 729     | 77.5%         | 72.3%        |
| 11am-12pm | 267     | 65.3%         | 68.9%        |
| 12-2pm    | 331     | 63.8%         | 61.0%        |
| 2-4pm     | 268     | 69.8%         | 70.1%        |

Morning alerts have higher averages (driven by outlier magnitude) but NOT consistently higher hit rates. The 10-11am slot actually has the best hit rate (72.3%). The time-of-day effect is real but moderate -- not the 3.7x difference the v2-only data suggested. **Recommendation: Tier 3 (time-of-day tag) is lower priority than originally stated.** The V/OI intent tag and roll detection are the high-value interventions.

### 5. Ben's "Good Alert" Profile

Analyzing the 6 real trades Ben shared (DOW, DVN, NU, CTRA, VST, SLB), his successful trades share:
- **Accessible option price:** $0.53 - $2.09 (4 of 6 under $2)
- **Underlying under $50:** 4 of 6, and the one expensive underlying (VST at $162) lost money
- **High volume surprise:** 5x - 40x. The extreme outlier (CTRA 517x) was a trap.
- **Near-the-money:** Strike/UL ratio 0.97 - 1.08. Slightly OTM.
- **Sector/event thesis:** DOW and DVN were reversion-to-mean plays on sector crashes. SLB was end-of-day conviction. These aren't random — Ben overlays a macro thesis.

The only feature that doesn't distinguish his trades from the rest is significance_score (3.64 - 7.35, spanning the full range).

---

## Proposed Solution: Three-Tier Intent Label

Add an intent classification label to each alert, computed at alert time from existing data. No new data collection needed.

### Tier 1: V/OI-Based Intent Tag (Simple, High Value)

After the existing alert line, add a tag:

```
[NEW POSITION]     — V/OI >= 5.0 (97% confidence)
[LIKELY NEW]       — V/OI 1.0-5.0 (83% confidence)
[INTENT UNCLEAR]   — V/OI < 1.0, OTM
[LIKELY CLOSING]   — V/OI < 1.0, ITM (51% closing)
```

**Implementation:** 4 lines of logic in `fm_alerts.py:_format_alert_line()`. The V/OI ratio and moneyness are already available in the alert dict.

### Tier 2: Multi-Strike Roll Detection (Moderate, High Value)

When an alert fires, query `flow_options_scans` for same-symbol, same-expiration, same-type contracts in the current scan. If another strike has:
- Volume >= 50% of the alert's volume
- V/OI < 1.5

Flag the alert as `[POSSIBLE ROLL from $X]` where $X is the other strike.

**Implementation:** One additional query per alert in `_generate_alert()`. Uses existing scan data in memory (the same scan that triggered the alert). Cost: minimal — the scan data is already loaded.

### Tier 3: Time-of-Day Quality Signal (Optional)

Add a `[MORNING]` tag to alerts fired before 10:30am. This is a subtle nudge that morning alerts have historically higher hit rates, without being prescriptive.

**Implementation:** One line checking scan_timestamp.

---

## What to Expect

### Noise Reduction Estimate

Current: ~16 alerts/day, ~4 worth following (25% S/N).

With intent labels:
- ~2-3 alerts/day flagged `[LIKELY CLOSING]` or `[POSSIBLE ROLL]` -- Ben can dismiss these faster
- ~5-8 flagged `[NEW POSITION]` -- high confidence worth looking at
- ~5-7 flagged `[LIKELY NEW]` or `[INTENT UNCLEAR]` -- requires judgment

This doesn't eliminate noise, but it moves Ben's mental filtering from "examine all 16" to "focus on the 5-8 NEW POSITION alerts, glance at the rest." Estimated effective S/N improvement from 25% to ~50-60%.

### What This Won't Solve

1. **Next-day confirmation is still valuable.** The morning OI resolution (BUILDING/CLOSING/NEUTRAL) is definitive. The at-alert-time prediction is probabilistic.
2. **Macro thesis overlay.** DOW's dip-buy thesis can't be automated. Ben's sector crash intuition is his edge, not the system's.
3. **Roll context beyond the alert strike range.** CTRA's $42 and $44 strikes were outside the +-20% range. Some rolls will be invisible.
4. **False negative gap.** 70% of >5% moves in FM-scanned symbols had no prior alert. Most are macro-driven, not stock-specific flow. This is a structural limitation, not a fixable gap.
5. **Roll BUILDING legs aren't necessarily bad trades.** Confirmed roll patterns (n=28 BUILDING legs) have 67.9% hit rate vs 71.6% for standalone BUILDING -- a small difference. The value of flagging rolls is thesis correction (knowing it's a roll), not necessarily trade avoidance.

---

## Measurement Plan

### Before/After Metrics

1. **Resolved alert accuracy:** Track what % of `[NEW POSITION]` alerts resolve as BUILDING the next day. Target: >90%.
2. **Roll detection precision:** Track what % of `[POSSIBLE ROLL]` alerts involve actual position transfers (next-day OI shows closing at one strike, building at another). Target: >70%.
3. **Ben's qualitative feedback:** After 1-2 weeks, does the label reduce his mental filtering effort? Does he still look at `[LIKELY CLOSING]` alerts?
4. **Alert composition:** Does adding intent labels change which alerts Ben follows?

### Validation Against Historical Data

Before implementing, the heuristic can be tested against all 1,253 resolved alerts. Expected results:
- V/OI >= 5.0 + BUILDING: 329/340 = 96.8% match
- V/OI < 1.0 + ITM + CLOSING: 108/212 = 51.0% match
- Roll detection: at least VST (2x) and NOK should be caught; CTRA partially (the $36 leg is in scan range)

---

## Risks and Uncertainties

1. **Console noise.** Adding another tag to the already-dense alert line. Could be a suffix tag or a second line. Design decision for Ben.
2. **V/OI < 1.0 OTM is ambiguous.** 40% of the alert population falls here. The label says `[INTENT UNCLEAR]`, which is honest but not helpful. Over time, adding more features (volume surprise direction, sector-relative activity) could improve this bucket.
3. **Roll detection query cost.** One additional scan of `flow_options_scans` per alert. With 16 alerts/day and the table at 23M+ rows, this needs an efficient query (exact match on symbol + expiration_date + scan_timestamp, which is indexed).
4. **The OI resolution itself has noise.** NEUTRAL (churning) is 19% of resolved alerts. Some "BUILDING" may actually be day trades that happened to increase OI. The labels are probabilistic, not definitive.

---

## Effort and Priority

| Component | Effort | Priority | Dependencies |
|-----------|--------|----------|-------------|
| Tier 1: V/OI intent tag | ~1 hour | **Do first** | None |
| Tier 2: Roll detection | ~3 hours | **Do second** | Tier 1 (for label format) |
| Tier 3: Time-of-day tag | ~15 min | Optional | None |
| Testing & validation | ~1-2 hours | After Tiers 1-2 | Historical alert data |

**Recommended implementation sequence:** Tier 1 alone is a meaningful improvement. It can be live within an hour and tested immediately. Tier 2 is the bigger engineering effort but addresses Ben's most painful specific examples (VST, CTRA). Tier 3 is trivially cheap insurance.

---

## Ready-to-Run Command

For implementing Tier 1 (V/OI intent tag):

```
cd /d E:\options_scanner
claude -p "Add an intent classification tag to flow alert console output. In fm_alerts.py, in the _format_alert_line() method, after the existing alert_line is built, add an intent tag based on V/OI ratio and moneyness: [NEW POSITION] if V/OI >= 5.0, [LIKELY NEW] if V/OI 1.0-5.0, [LIKELY CLOSING] if V/OI < 1.0 AND moneyness is ITM, [INTENT UNCLEAR] if V/OI < 1.0 AND moneyness is OTM or ATM. The V/OI is already computed as vol_oi_ratio and moneyness is already in the alert dict. Add the tag right after the symbol name, like: DOW [NEW POSITION] [MID] $37.5 calls..."
```

For implementing Tier 2 (roll detection), a separate session is recommended due to the additional query logic.
