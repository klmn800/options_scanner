# FM Alert Scoring v3 — Two-Tier Design Notes

**Status:** Brainstorming / Design phase. Not yet scheduled for implementation.
**Date:** 2026-04-02
**Context:** Emerged from analysis of v2 scoring (deployed 2026-04-01) during first day of live operation. v2 removed smart money score and lowered threshold from 6.0 to 3.5. The discussion below captures insights from walking through real alerts with Ben and identifying gaps in the current scoring model.

**Related research:** `research/alert_scoring_simulation.py`, `research/alert_premium_vs_wins.py`, `research/alert_no_smart_money.py`, `research/alert_threshold_bands.py`

---

## The Core Insight

The current scoring system answers one question: **"Is this unusual options activity?"** (premium size + volume surprise). But alerts serve two distinct purposes in the workflow:

1. **Watchlist intelligence** — track how a symbol evolves over a week after unusual activity. Even TSM puts Ben would never trade are valuable context for understanding institutional positioning.
2. **Investment signals** — flag specific opportunities that match Ben's trading style and constraints.

v2 scoring treats these as one thing. v3 should separate them into two tiers within the same 0-10 score axis.

---

## Two-Tier Scoring Architecture

### Tier 1: Fundamental Score (Watchlist Qualification)

**Question:** "Is this activity meaningful enough to track on the watchlist?"

**Components (existing):**
- **Premium magnitude (0-6 points)** — log-scale scoring. Confirms institutional scale, not retail.
- **Volume surprise (0-4 points)** — how unusual is this volume vs baseline. The "BOOM" detector.

**Component to add:**
- **Flow concentration** — what percentage of this symbol's total daily options volume does this contract represent? High concentration = this IS the story for the symbol. Low concentration = background noise.
  - NVDA $175 calls at 3.1% flow = noise in a sea of NVDA trading. Penalty could push below 3.5 threshold.
  - XPEV $16 calls at 57.3% flow = this IS the XPEV trade today. No penalty (or small boost).
  - FBIN $35 puts at 55.3% flow = dominant trade on a mid-cap. Clear signal.

**Design question:** Should flow concentration be a penalty for low values (dragging noise below threshold), a bonus for high values (boosting concentrated flow), or both? A penalty-only approach is simpler and directly solves the "NVDA noise" problem without inflating scores elsewhere.

**Design question:** What flow% thresholds? Some starting thoughts:
- <5% flow: significant penalty (maybe -1.0 to -1.5 points). This contract is a rounding error in the symbol's daily flow.
- 5-15% flow: mild penalty or neutral
- 15-50% flow: neutral
- 50%+ flow: small bonus? Or just neutral — the volume surprise already captures "this is big."

**Note:** Flow concentration naturally scales inversely with liquidity. NVDA will rarely have a single contract at 50%+ flow because it has enormous breadth. XPEV or FBIN will frequently have concentrated flow. This means the penalty would disproportionately affect mega-cap noise, which is exactly the desired behavior.

### Tier 2: Actionability Bonus (HIGH Signal)

**Question:** "After qualifying for the watchlist, does this alert have characteristics that make it worth acting on NOW?"

These are additive points that can push a MEDIUM alert into HIGH territory. They represent Ben's personal trading filters — things he evaluates in <10 seconds when scanning alerts.

**Candidate factors:**

#### a) V/OI Ratio (Position Building Signal)
Ben's own words: "My favorite alerts are the ones that show something like 15,000 volume on a contract with < 100 OI. That says to me something is definitely worth following and I should jump on now."

High V/OI = unmistakably new position building. Someone is opening, not adjusting or closing.

| V/OI Range | Interpretation | Possible Points |
|------------|---------------|-----------------|
| < 1.0 | Ambiguous (building or closing) | 0 |
| 1.0 - 5.0 | Likely building, some ambiguity | +0.25 |
| 5.0 - 20.0 | Clearly building | +0.5 |
| 20.0 - 100.0 | Strong new interest | +0.75 |
| 100+ | Unmistakably new (FBIN territory) | +1.0 |

**Design question:** Should V/OI of <1 be a negative signal (drag)? Could indicate position closing, which is less actionable. But closing could also be meaningful intelligence (someone exiting before an event).

#### b) DTE Sweet Spot
Ben's preferred holding period is 30-60 days. 8 DTE makes him uncomfortable. The current system has a binary DTE gate (>= 7 days) but no preference scoring.

| DTE Range | Interpretation | Possible Points |
|-----------|---------------|-----------------|
| 7-14 | Too short for Ben's style, higher risk | 0 (or small penalty?) |
| 15-29 | Workable but not ideal | +0.25 |
| 30-60 | Sweet spot | +0.5 |
| 60+ | Long-dated, fine but less urgent | +0.25 |

#### c) Contract Affordability (Last Price)
Ben can't follow a $23 TSM put. He can follow a $2 XPEV call. The system should reflect what he can actually trade.

| Last Price | Interpretation | Possible Points |
|------------|---------------|-----------------|
| > $10.00 | Too expensive to follow directly | 0 |
| $5.00 - $10.00 | Possible but not ideal | +0.25 |
| $1.00 - $5.00 | Sweet spot — affordable, not penny-option | +0.5 |
| < $1.00 | Lottery ticket territory, higher risk | +0.25 |

**Design question:** Does contract price already correlate with things we score? Expensive contracts tend to be ITM or high-IV, which already have lower volume surprise. Might be partially redundant.

#### d) IV Context (IV Percentile)
A 35% IV means nothing without context. Is that high or low for this symbol? IV percentile answers this.

- **Low IV percentile (< 25th):** Options are cheap relative to history. Better entry points. If volume surprise is also high, someone is loading up while options are cheap — strong signal.
- **High IV percentile (> 75th):** Options are expensive. Could mean earnings approaching, event anticipated, or simply overpriced. Less attractive as entry unless it's a put (hedging).
- **Mid IV percentile (25th-75th):** Neutral — neither cheap nor expensive.

| IV Percentile | Interpretation | Possible Points |
|---------------|---------------|-----------------|
| < 15th | Very cheap options, excellent entry | +0.5 |
| 15th - 30th | Cheap, good entry | +0.25 |
| 30th - 70th | Neutral | 0 |
| 70th - 85th | Expensive, less attractive entry | -0.25? |
| > 85th | Very expensive, likely event-driven | -0.5? (or 0 if put) |

**Data availability:** IV percentile is NOT currently in `flow_alerts` or `flow_options_scans`. It IS computed in `option_symbol_summary` (`symbol_iv_percentile_30d`) and `option_contracts` (`iv_percentile_20day`). Would need to look up at alert time and add a column to `flow_alerts`.

**Design question:** Should we use symbol-level IV percentile (from `option_symbol_summary`) or contract-level (from `option_contracts`)? Symbol-level is more stable and answers "are options on this stock cheap/expensive right now?" Contract-level is noisier but more specific to the actual strike/expiration.

**Design question:** Should high IV be a penalty or just neutral? High IV near earnings is expected and doesn't make the alert worse — it means someone is paying up for exposure, which could be bullish conviction. Penalizing high IV might filter out legitimate earnings plays.

#### e) Multi-Leg Pattern Detection
Both HIGH alerts from 2026-04-02 were strangles (paired put+call, similar premiums, same expiration). A strangle with extreme flow on both legs is a stronger signal than either leg alone — it says "someone expects a big move but isn't sure which direction."

Possible approach: when two alerts fire on the same symbol in the same cycle with opposite option_type and similar DTE, flag both as part of a strangle and apply a bonus.

| Pattern | Interpretation | Possible Points |
|---------|---------------|-----------------|
| Isolated alert | Normal | 0 |
| Paired put+call, same cycle | Likely strangle/straddle | +0.5 to each leg |
| Multiple alerts same direction | Directional conviction | +0.25 |

**Design question:** This is more complex to implement than the other factors because it requires cross-alert awareness within a cycle. The daily summary box already detects the `1C/1P` pattern for display — could the same logic feed into scoring?

---

## Data Gaps to Fill

| Data Point | Current Location | Needed In | Action |
|------------|-----------------|-----------|--------|
| IV percentile (30d) | `option_symbol_summary.symbol_iv_percentile_30d` | `flow_alerts` | Look up at alert time, add column |
| Flow percentage | `flow_options_scans.flow_percentage` | Already in alerts display | Verify it's stored in `flow_alerts` or accessible at scoring time |
| V/OI ratio | Computed at display time | Scoring | Already available from `volume` and `open_interest` in the alert data |
| DTE | `flow_alerts.dte` | Scoring | Already stored |
| Last price | `flow_alerts.last_price` | Scoring | Already stored |
| Multi-leg pattern | Not detected at scoring time | Scoring | Requires cross-alert logic in the alert cycle |

---

## Score Budget & Calibration

Current v2 score range: premium (0-6) + volume surprise (0-4) = **0-10 theoretical max**.

With Tier 2 bonuses, the theoretical max increases. Options:

**Option A: Expand the scale.** Let scores go above 10 with bonuses. Simple but breaks the 0-10 mental model.

**Option B: Compress the fundamental score.** Reduce premium + volume surprise to fit within, say, 0-7, leaving 3 points for bonuses. Requires recalibrating thresholds.

**Option C: Keep 0-10, let bonuses push past 10 but cap at 10.** Bonuses only matter for crossing the HIGH threshold (5.0). Once you're HIGH, the exact score is less important. This means FBIN at 7.9 fundamentals + bonuses still displays as, say, 9.5 or capped at 10.0. The score above HIGH is "how loud is the system tapping your shoulder" — useful for sorting but not a different category.

**Option D: Keep 0-10, but integrate flow concentration as a modifier to the existing score rather than additive points.** For example, flow concentration acts as a multiplier (0.7x to 1.1x) on the fundamental score, and bonuses are small additive adjustments (+0.25 to +0.5 each) that can push a 4.5 to 5.0+ but won't massively distort the scale.

**Preliminary lean: Option D.** Flow concentration as a multiplier naturally solves the mega-cap noise problem (NVDA at 3.1% gets 0.7x multiplier → score drops from 4.4 to ~3.1, below threshold). Bonuses are small enough to not distort the scale. A strong MEDIUM (4.5) with good V/OI (+0.5) and right DTE (+0.25) crosses into HIGH at 5.25.

---

## Observations from First Day of v2 (2026-04-02)

### Alert Volume
- 7 cycles, 21 alerts, 15 symbols through ~1:30 PM
- ~3 alerts/cycle average — manageable, not overwhelming
- Score range: 3.5 (PBR) to 7.9 (FBIN)

### What Scored HIGH (5.0+) Naturally
- **FBIN strangle** (7.9/7.5): 176x/142x volume surprise, OI of 1-5 on $88K+ volume, $32M total premium, 43 DTE, $1.62-$2.00 last price. Every single factor screams.
- **NKE strangle** (6.8/6.4): 23x/20x volume surprise, strong V/OI (36.6/17.7), $28.4M total premium, 43 DTE, $1.57-$1.64 last price.

These scored HIGH on fundamentals alone. Under v3, the actionability bonuses would push them even higher — but crossing the threshold is what matters, so the extra points are academic. **This confirms the fundamental scoring is working correctly for extreme cases.**

### What Scored MEDIUM but Was Actionable
- **XPEV $16 calls** (4.1): $1.6M premium, 5x surprise, V/OI of 834, 43 DTE, $2.24 last price, 57% flow concentration. Ben's assessment: "Probably act on it." Under v3, the V/OI bonus (+1.0), DTE bonus (+0.5), price bonus (+0.5) could push this to ~6.1 → HIGH. That's the desired outcome.

### What Scored MEDIUM and Was Noise
- **NVDA $175 calls** (4.4): $6.2M premium, 5.8x surprise, V/OI of 1.2, 8 DTE, $3.00 last price, 3.1% flow concentration. Ben's assessment: "Not going to act on it." Under v3, the flow concentration penalty (0.7x multiplier → 3.1) would drop it below threshold. Also no bonuses from V/OI (ambiguous), DTE (too short), or price (borderline). **This is the key win — noise removed from watchlist.**

### What Scored MEDIUM and Was Correctly Positioned
- **TSM $340 puts** (4.5): $11.9M premium, 10.4x surprise, V/OI 0.4, too expensive to trade, but valuable intelligence about institutional positioning. Ben: "Not going to act on it" but acknowledged the two TSM puts together paint a bearish picture. Under v3, flow concentration wouldn't penalize this (16.9% is fine), but no actionability bonuses either. Stays MEDIUM. **Correct outcome — good watchlist intelligence, not an entry signal.**

### Ben's Disposition of 8 First-Cycle Alerts
| Alert | Score | Ben's Verdict | v3 Predicted Outcome |
|-------|-------|--------------|---------------------|
| ROKU $95C | 4.5 | No (too expensive, high IV) | MEDIUM (no bonuses, flow 69% is fine) |
| TSM $340P | 4.5 | No (can't afford, ambiguous V/OI) | MEDIUM (good intelligence, stays) |
| NVDA $175C | 4.4 | No (noisy, ambiguous, short DTE) | Below threshold (3.1% flow penalty) |
| XOM $165P | 4.3 | Maybe (V/OI 11.7 attractive, short DTE concern) | MEDIUM+ (V/OI bonus, but DTE penalty nets out) |
| XPEV $16C | 4.1 | Probably (V/OI 834, 43d, $2.24, 57% flow) | HIGH (~6.1 with bonuses) |
| TSM $330P | 4.1 | No (expensive, second TSM put) | MEDIUM (stays as intelligence) |
| COIN $170C | 3.8 | No (expensive, short DTE, high IV) | MEDIUM or below (8 DTE, no bonuses) |
| NVDA $180C | 3.6 | No (same as NVDA $175, lottery ticket) | Below threshold (3.1% flow penalty) |

**v3 alignment with Ben's judgment: 7/8 match.** The only mismatch is XOM — Ben said "maybe" but v3 would probably leave it as MEDIUM rather than push to HIGH, because the short DTE offsets the V/OI bonus. That's a reasonable conservative miss.

---

## Implementation Considerations

### Column Additions to `flow_alerts`
- `iv_percentile` — REAL, 2 decimals. Looked up from `option_symbol_summary.symbol_iv_percentile_30d` at alert time.
- `flow_percentage` — verify this is already stored or needs to be added.

### Scoring Integration Point
The actionability bonus logic should live in `fm_analyzer.py`, probably as a separate method called after `_calculate_flow_score()` returns the fundamental score. Something like `_calculate_actionability_bonus(contract, fundamental_score)` that returns additional points.

Flow concentration should modify the fundamental score (multiplier approach) before the bonus is applied.

### Backward Compatibility
- `alert_reason` prefix: could use `v3|` when this ships, continuing the version tracking pattern.
- Existing v2 alerts in the database are preserved with `v2|` prefix for comparison.
- The 0-10 score axis stays the same, so all downstream consumers (watchlist, daily summary, console display) work without changes.

### Threshold Recalibration
May need to adjust after implementation:
- MEDIUM threshold: 3.5 may still be right (flow concentration multiplier handles noise)
- HIGH threshold: 5.0 may be right (bonuses are small enough that only alerts with multiple actionability factors cross it)
- Needs a week of live v2 data first to establish baseline before layering v3 changes.

---

## Open Questions

1. **Flow concentration formula:** Multiplier vs additive penalty? What breakpoints? Need to analyze distribution of flow_percentage across all historical alerts to calibrate.
2. **IV percentile direction:** Should high IV be penalized, or just low IV rewarded? Earnings context complicates this.
3. **V/OI vs V/OI on the same symbol across time:** A V/OI of 100 means more if it's the FIRST day of building (was 0 OI yesterday) vs the 5th day (OI has been growing). Need to think about whether prior-day OI context adds value.
4. **Multi-leg detection complexity:** Is cross-alert awareness worth the implementation cost, or does the daily summary box already serve this purpose visually?
5. **Score budget:** How many total bonus points are possible? If all factors max out (+1.0 V/OI, +0.5 DTE, +0.5 price, +0.5 IV, +0.5 multi-leg), that's +3.0 — which could push a 4.0 fundamental to 7.0. Is that too much? Or is it fine because all those factors rarely align simultaneously?
6. **Calibration data:** Should we run the v3 formula retrospectively against historical alerts (with known outcomes via max_prof_7d_pct) to validate that the bonus factors actually improve the 18%+ win rate for HIGH vs MEDIUM?

---

## Timeline

- **April 2026:** Let v2 run. Collect observations on alert quality, flow concentration distribution, and V/OI patterns.
- **May 2026:** Review v2 per item 2.3 in big-to-do-list.txt. If satisfied with fundamental scoring, design v3 bonus formula with calibration data.
- **May/June 2026:** Implement v3. Backtest against historical alerts before deploying live.
