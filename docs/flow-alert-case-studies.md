# Flow Alert Case Studies

This document tracks analyzed Flow Monitor alerts that demonstrate specific patterns, successful trades, or likely institutional positioning. Each case study provides detailed analysis of alert characteristics, price action, and lessons learned.

---

## ✅ ALB $140 Dec 19 Calls (Dec 1, 2025) - Likely Institutional Positioning

**Detailed Case Study:** `strategies/flow_monitor/case_studies/ALB_2025-12-01_institutional_positioning.md`

### Alert Details
```
Symbol:              ALB (Albemarle - Basic Materials/Lithium)
Contract:            $140 Dec 19, 2025 Calls
Alert Date:          December 1, 2025 @ 10:57 AM
Significance Score:  6.34 (MEDIUM)
Volume:              6,653 contracts (~20 min window)
Open Interest:       286 (before alert)
Underlying Price:    $129.52
Strike Distance:     $10.48 OTM (8.1% move needed)
Option Price:        $3.35 last / $2.54 bid / $2.85 ask
IV:                  63%
DTE:                 18 days
```

### Why This May Have Been Institutional "Smart Money"

1. **Volume-to-OI Ratio: 23:1** - Volume 23x existing OI
2. **OI Confirmation:** Dec 2 OI jumped 286 → 6,879 (+6,593 contracts = positions opened, not day-traded)
3. **Hold Through Drawdown:** OI remained 6,900-7,300 throughout (no panic selling despite -79% drawdown)
4. **Exit at Expiration:** Dec 19 volume = 6,948 contracts (matching opened positions)
5. **Size:** $1.78M notional capital

### Complete Daily Lifecycle

| Date   | Volume | OI    | Last  | Bid-Ask    | UL Price | Intrinsic | DTE | P&L    | Notes |
|--------|--------|-------|-------|------------|----------|-----------|-----|--------|-------|
| Nov 25 | 70     | 212   | $2.86 | $2.72-2.93 | $125.26  | $0        | 24  | --     | Baseline |
| Nov 26 | 75     | 274   | $2.95 | $2.71-3.05 | $126.91  | $0        | 23  | +8%    | Building |
| Nov 28 | 20     | 288   | $3.43 | $3.25-3.45 | $129.99  | $0        | 21  | +26%   | Pre-alert peak |
| **Dec 1** | **6,653** | **286** | **$2.72** | **$2.54-2.85** | **$128.33** | **$0** | **18** | **0%** | **🚨 ALERT** |
| Dec 2  | 107    | 6,879 | $2.80 | $2.29-2.52 | $128.14  | $0        | 17  | +3%    | OI confirms opens |
| Dec 3  | 134    | 6,900 | $2.16 | $1.82-2.36 | $126.49  | $0        | 16  | -21%   | Dropping |
| **Dec 4** | **10** | **6,955** | **$0.74** | **$0.54-1.02** | **$119.14** | **$0** | **15** | **-73%** | **💀 CRASH** |
| Dec 5  | 281    | 6,951 | $1.80 | $1.37-1.93 | $125.19  | $0        | 14  | -34%   | Bounce |
| Dec 10 | 83     | 7,154 | $2.59 | $2.13-2.60 | $133.21  | $0        | 9   | -5%    | Recovering |
| Dec 11 | 10     | 7,205 | $2.26 | $2.07-2.38 | $134.59  | $0        | 8   | -17%   | Near breakeven |
| Dec 12 | 124    | 7,208 | $1.32 | $1.20-1.57 | $132.74  | $0        | 7   | -51%   | Theta decay |
| Dec 15 | 132    | 7,235 | $1.00 | $0.90-1.15 | $132.22  | $0        | 4   | -63%   | 3 DTE bleeding |
| **Dec 16** | **104** | **7,286** | **$0.58** | **$0.45-0.69** | **$131.07** | **$0** | **3** | **-79%** | **Max Drawdown** |
| Dec 17 | 595    | 7,303 | $0.77 | $0.68-0.87 | $134.71  | $0        | 2   | -72%   | Volume spike |
| Dec 18 | 232    | 7,287 | $2.15 | $2.04-2.50 | $140.48  | $0.48     | 1   | -21%   | ✅ ITM! |
| **Dec 19** | **6,948** | **7,272** | **$5.89** | **$4.90-6.55** | **$145.88** | **$5.88** | **0** | **+117%** | **🏆 EXPIRY** |

### Performance Summary

**If Bought at Alert (Dec 1):**
- Entry: $2.72 (close) or $2.54 (bid)
- Peak Drawdown: $0.58 on Dec 16 = **-79% unrealized loss**
- Final Value: $5.89 on Dec 19 = **+117% realized gain**

**If Bought the Crash (Dec 4):**
- Entry: $0.74
- Final Value: $5.89
- **Profit: +696%** ($5.15 gain per contract)

**Total Position Estimate:**
- Contracts: ~6,593 (OI increase)
- Entry: $2.70 avg × 6,593 × 100 = **$1.78M**
- Exit: $5.89 × 6,593 × 100 = **$3.88M**
- **Total Profit: ~$2.10M (+118%)**

### Stock Price Movement

```
Nov 25  $125.26  Baseline
Dec 1   $128.33  🚨 Alert day
Dec 4   $119.14  💀 Crash (-$9.19 from alert)
Dec 10  $133.21  Recovery building
Dec 18  $140.48  ✅ Strike breached (high: $140.78)
Dec 19  $145.88  🏆 Expiration (high: $149.82)

Total: $119.14 (low) → $149.82 (high) = +25.8%
```

### Key Lessons

1. **OI Validation Critical:** Next-day OI jump (286 → 6,879) confirmed this was real positioning, not day-trading
2. **Diamond Hands Required:** Holders survived -79% drawdown over 15 days before profit
3. **Alternative Strategies:**
   - Buy the crash (Dec 4 @ $0.74) → +696% instead of +117%
   - Use further-dated options (more time value, less theta decay)
   - Scale in on weakness (average cost ~$1.50 vs $2.72)
4. **Alert Was Correct:** Detected $1.78M institutional bet that proved profitable
5. **Execution Differs from Detection:** Alert shows WHERE institutional money is, not necessarily WHEN/HOW to follow

### Pattern Classification

**Institutional Positioning Indicators:**
- ✅ Large size (23x existing OI)
- ✅ OI confirmation next day
- ✅ Held through extreme drawdown (-79%)
- ✅ Held to expiration/exercise
- ✅ Stock thesis proved correct ($128 → $145)

---

## Narrative for Flow Monitor Agent

"Alert fired for ALB|140.0|2025-12-19|CALL on Dec 1 2025 10:57 AM, when 6653 contracts were traded against an OI of 286, suggesting a purchase. 
Last Price was $2.72 for an estimated premium of $1.8 million, larger than expected for retail traders. ALB is Lithium, Basic Materials, and has 
an average total daily volume of 57,856 which is not a lot (100x less than AAPL), suggesting that this was very targeted and intentional. UL was 
$128.33 (up from $125.26 on Nov 25), 18 DTE, no upcoming earnings. Monitoring. 
Dec 2 OI climbs to 6879, confirming purchase. 
On Dec 4, the value of option dropped to $0.74, a 73% loss, with the UL at $119.14. No alerts fired; volume remains steady, suggesting the alert 
buyer has not cut losses. This is either an end of the thesis, or an opportunity to buy low. We often see these dips following alerts; given the 
low cost, I notified Ben of the potential opportunity of mean reversion via email.
Dec 5, price recovers to $1.80, still a 34% loss for the alert, but if the dip was bought, would be a ~140% gain, a swing trade win.
Dec 10 UL price exceeds alert UL price at $133.21, and contract last price is at its peak $2.59 - still lower than alert price, but highest until 
expiration. Ideal exit point, 9 DTE; from here UL will climb but last price will sharply decline, suggesting theta decay while the option is still 
OTM. 
Dec 18 contract is ITM, UL $140.48, last price $2.15, 1 DTE. OI is 7287, no high volume events recorded, alert holder is still holding onto these 
contracts. 
Dec 19, expiration day, UL jumps to $145.88, securely ITM, and last price is $5.89. Volume 6948 recorded, showing the alerted position closing 
with a 117% gain at the last minute. Good for them!
If Ben bought the dip at $0.74 and held to expiration, he would have seen 8x gains.
How did the alert holder know that the price would be $140+ by Dec 19? Expected move at time of alert was ±$4 (128.33*.63*√(18/365)) or $132, 
so this exceeded that expectation. 
Contract expired, no longer tracking."

---

**Last Updated:** December 29, 2025
**Total Case Studies:** 1 (ALB Dec 1, 2025)
**Detailed Files:** `strategies/flow_monitor/case_studies/`
