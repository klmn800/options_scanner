# Case Study: ALB $140 Dec 19 Calls - Institutional Positioning

**Date:** December 1, 2025
**Symbol:** ALB (Albemarle Corporation)
**Sector:** Basic Materials (Lithium)
**Alert Type:** Flow Monitor MEDIUM (6.34 score)
**Outcome:** SUCCESS (+116% if held to expiry)
**Pattern:** Institutional Conviction Trade

---

## Executive Summary

On December 1, 2025, Flow Monitor detected a 6,653-contract volume spike in ALB $140 Dec 19 calls. OI analysis confirmed this was a massive position opening (286 → 6,879 OI), not day-trading. Despite suffering a -79% drawdown over the following two weeks, the position holders maintained their conviction and ultimately profited +116% when ALB rallied to $145.88 on expiration day.

**This case demonstrates genuine institutional positioning**: large size, high conviction, willingness to weather extreme volatility, and holding through expiration.

---

## Alert Details

### Initial Detection (Dec 1, 2025 @ 10:57 AM)

```
Symbol:              ALB
Contract:            $140 Dec 19, 2025 Calls
Significance Score:  6.34 (MEDIUM)
Volume:              6,653 contracts (~20 min window)
Open Interest:       286 (before alert)
Underlying Price:    $129.52
Strike Distance:     $10.48 OTM (8.1% move needed)
Option Price:        $3.35 (last)
Bid-Ask:             $2.54 - $2.85
IV:                  63%
DTE:                 18 days
```

### Critical Indicators of Institutional Activity

1. **Volume-to-OI Ratio: 23:1** - Volume was 23x existing OI, indicating massive new position
2. **OI Confirmation:** Next day OI jumped from 286 → 6,879 (+6,593 contracts opened)
3. **Position Held:** OI remained 6,900-7,300 range through entire lifecycle (no early exits)
4. **Expiration Volume:** 6,948 contracts traded on Dec 19 (matching the opened positions)

---

## Stock Price Lifecycle

### Pre-Alert Movement
```
Nov 25:  $125.26  (baseline)
Nov 26:  $126.91  (+1.3%)
Nov 28:  $129.99  (+2.4%)
```

### Alert Day & Initial Move
```
Dec 1:   $128.33  (-1.3%) 🚨 ALERT - 6,653 volume spike
Dec 2:   $128.14  (-0.1%)
Dec 3:   $126.49  (-1.3%)
```

### The Crash (Maximum Drawdown)
```
Dec 4:   $119.14  (-7.2%) 💀 Stock crashes $9+ from alert day
Dec 5:   $125.19  (+5.1%) Recovery begins
```

### Recovery Rally
```
Dec 8:   $127.20  (+1.6%)
Dec 10:  $133.21  (+4.7%)
Dec 11:  $134.19  (+0.7%)
Dec 12:  $132.74  (-1.1%)
```

### Final Surge
```
Dec 17:  $134.71  (+1.5%)
Dec 18:  $140.48  (+4.3%) ✅ STRIKE BREACHED (high: $140.78)
Dec 19:  $145.88  (+3.8%) 🏆 EXPIRATION (high: $149.82)
```

**Total Move:** $119.14 (low) → $149.82 (high) = **+25.8% range**

---

## Option Contract Performance

### Daily Tracking

| Date   | Volume | OI    | Last  | Bid-Ask    | UL Price | Intrinsic | DTE | P&L from $2.72 | Notes |
|--------|--------|-------|-------|------------|----------|-----------|-----|----------------|-------|
| Nov 25 | 70     | 212   | $2.86 | $2.72-2.93 | $125.26  | $0        | 24  | --             | Baseline |
| Nov 26 | 75     | 274   | $2.95 | $2.71-3.05 | $126.91  | $0        | 23  | +8%            | Building |
| Nov 28 | 20     | 288   | $3.43 | $3.25-3.45 | $129.99  | $0        | 21  | +26%           | Pre-alert peak |
| **Dec 1** | **6,653** | **286** | **$2.72** | **$2.54-2.85** | **$128.33** | **$0** | **18** | **0%** | **🚨 ALERT** |
| Dec 2  | 107    | 6,879 | $2.80 | $2.29-2.52 | $128.14  | $0        | 17  | +3%            | OI confirms opens |
| Dec 3  | 134    | 6,900 | $2.16 | $1.82-2.36 | $126.49  | $0        | 16  | -21%           | Starting to drop |
| **Dec 4** | **10** | **6,955** | **$0.74** | **$0.54-1.02** | **$119.14** | **$0** | **15** | **-73%** | **💀 CRASH** |
| Dec 5  | 281    | 6,951 | $1.80 | $1.37-1.93 | $125.19  | $0        | 14  | -34%           | Bounce |
| Dec 10 | 83     | 7,154 | $2.59 | $2.13-2.60 | $133.21  | $0        | 9   | -5%            | Recovering |
| Dec 11 | 10     | 7,205 | $2.26 | $2.07-2.38 | $134.59  | $0        | 8   | -17%           | Near breakeven |
| Dec 12 | 124    | 7,208 | $1.32 | $1.20-1.57 | $132.74  | $0        | 7   | -51%           | Theta decay |
| Dec 15 | 132    | 7,235 | $1.00 | $0.90-1.15 | $132.22  | $0        | 4   | -63%           | 3 DTE bleeding |
| **Dec 16** | **104** | **7,286** | **$0.58** | **$0.45-0.69** | **$131.07** | **$0** | **3** | **-79%** | **Max Drawdown** |
| Dec 17 | 595    | 7,303 | $0.77 | $0.68-0.87 | $134.71  | $0        | 2   | -72%           | Volume spike (bailouts?) |
| Dec 18 | 232    | 7,287 | $2.15 | $2.04-2.50 | $140.48  | $0.48     | 1   | -21%           | ✅ ITM! |
| **Dec 19** | **6,948** | **7,272** | **$5.89** | **$4.90-6.55** | **$145.88** | **$5.88** | **0** | **+117%** | **🏆 EXPIRY** |

### Performance Summary

**Entry Price (Dec 1 alert):** $2.72 (close) or $2.54 (bid)

**Exit Scenarios:**
- **Peak Drawdown:** $0.58 on Dec 16 = **-79% unrealized loss**
- **Expiration Value:** $5.89 on Dec 19 = **+117% realized gain**

**If Held to Expiry:**
- Entry at $2.72: **+116.5%** ($3.17 profit/contract)
- Entry at $2.54 (bid): **+131.9%** ($3.35 profit/contract)

**Total Position Value:**
- Contracts: ~6,593 (OI increase)
- Entry cost: 6,593 × $2.70 × 100 = **$1.78M**
- Exit value: 6,593 × $5.89 × 100 = **$3.88M**
- **Total Profit: ~$2.10M (+118%)**

---

## What Made This "Institutional"?

### 1. Size & Conviction
- 6,653 contracts = $1.78M initial capital
- 23x existing OI (dominated the float)
- Position represented nearly entire OI post-opening

### 2. Hold Through Drawdown
- Survived -73% crash on Dec 4 (3 days after entry)
- Maximum drawdown: -79% on Dec 16
- OI remained stable 6,900-7,300 throughout (no panic selling)

### 3. Hold to Expiration
- Volume on Dec 19: 6,948 contracts (matching opened positions)
- Likely exercised (stock finished $5.88 ITM)
- Pattern: **position opening → hold → expiration/exercise**

### 4. Timing Suggests Inside Information
- Stock rallied from $119 → $145 (+22%) in final week
- Dec 18-19 surge was dramatic ($135 → $149 peak)
- Thesis played out EXACTLY on expiration day

---

## Lessons & Exploitation Strategies

### What the Alert Detected
✅ **Large committed capital** ($1.78M notional)
✅ **Conviction trade** (held through -79% drawdown)
✅ **Genuine institutional positioning** (not day-trading)
✅ **Ultimately profitable** (+116% if held)

### Alternative Execution Strategies

#### 1. Buy the Crash (Dec 4)
- **Entry:** $0.74 (when stock crashed to $119)
- **Exit:** $5.89 (Dec 19 expiry)
- **Profit:** +696% ($5.15 gain)
- **Risk:** Less than original entry, but still required conviction

#### 2. Buy Further-Dated Options
- If alert signaled institutional thesis, could buy Jan or Feb expiries
- More time value, less theta decay
- Survived drawdown more comfortably
- Example: $135 Jan 16 calls (see related alert Dec 19)

#### 3. Scale In on Weakness
- Buy 25% on alert day ($2.72)
- Add 25% on Dec 4 crash ($0.74)
- Add 25% on Dec 12 dip ($1.32)
- Reserve 25% for final week
- Average cost: ~$1.50 → Exit $5.89 = +293%

#### 4. Sell Spreads Instead
- Sell $150 calls against long $140 calls
- Cap upside but reduce cost basis
- Better risk-adjusted returns through drawdown

### Red Flags to Monitor

⚠️ **High IV (63%)** - expensive premium, needs big move
⚠️ **OTM position** - requires 8% stock move in 18 days
⚠️ **Near-term expiry** - theta decay accelerates
⚠️ **Volatile sector** - lithium stocks prone to swings

### Validation Checklist

When similar alerts occur, validate with:
1. **Next-day OI increase** (confirms positions opened, not day-traded)
2. **Subsequent OI stability** (confirms holding pattern)
3. **Volume at expiry** (confirms whether exercised or closed)
4. **Stock fundamentals** (any catalysts supporting the thesis?)

---

## Research Questions

### Why Did ALB Rally?

**Potential Catalysts (to be researched):**
- Lithium price movement in mid-December?
- EV demand news or policy changes?
- Earnings announcement or guidance?
- Sector rotation into materials?
- Technical breakout from consolidation?

**Action:** Review news/earnings calendar for Dec 15-19, 2025

### Who Was the Buyer?

**Characteristics suggest:**
- Large institutional desk or hedge fund
- Access to fundamental research or inside track
- Risk tolerance for high-conviction bets
- Execution capability ($1.78M position)

**Unlikely to be:**
- Retail (too large, too much conviction through drawdown)
- Day traders (OI proves overnight holds)
- Market makers (directional exposure too large)

---

## Conclusion

This case represents a **textbook example of institutional positioning** detected by Flow Monitor alerts:

1. ✅ Large volume spike (6,653 contracts) created alert
2. ✅ OI confirmed genuine position opening (+6,593 OI)
3. ✅ Diamond hands through -79% drawdown
4. ✅ Held to expiration with profitable outcome (+116%)
5. ✅ Thesis proved correct (stock rallied $119 → $149)

**Key Takeaway:** The Dec 1 alert correctly identified institutional activity, but executing the same trade required exceptional risk tolerance. Better strategies include:
- Buying the crash (Dec 4 @ $0.74)
- Using further-dated options
- Scaling in on weakness
- Spreading to reduce cost

**Future Use:** When similar patterns emerge (huge volume spike → OI confirmation → sustained holding), treat as high-conviction institutional signal and explore alternative entries beyond copying the exact trade.

---

## Files Referenced
- Flow alert data: `flow_alerts` table (2025-12-01)
- Option lifecycle: `data/sector_archive/basic_materials.db` (option_contracts table)
- Stock prices: `historical_prices` table
- Analysis date: 2025-12-29

## Related Alerts
- ALB $135 Jan 16 Calls (Dec 19, 2025 - Score 8.80 HIGH)
- ALB $155 Jan 16 Calls (Dec 19, 2025 - Score 8.58 HIGH)

Both Jan 16 alerts occurred AFTER the stock rallied to $146, representing chase flow rather than positioning.
