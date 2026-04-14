# TUI Live Test Session - Real Trading Decisions

**Date:** 2025-10-14
**Goal:** Use Morning View TUI to plan $1000 allocation for this week and next
**User:** Ben

---

## Session Notes

### Features Used
- [x] Discovery page (finding triggered symbols)
- [x] Symbol Detail page (deep dive analysis)
- [x] OI Distribution (strike selection)
- [ ] OI Timing (Smart Money vs Retail)
- [ ] Watchlist page (curated tracking)
- [ ] Capital Planner (position planning)
- [ ] AI Analysis (trading insights)
- [ ] Compare Strikes (contract comparison)

### What Worked Well
- **Confluence breakdown** is super useful - shows exactly why PINS scored 4/5
- **Symbol Detail** gives quick overview before diving deep
- **OI Distribution** shows overall positioning clearly
- Top 5 strikes listing is helpful

### Pain Points / Missing Data

**CRITICAL GAPS:**
1. **NO WAY TO FILTER FLOW ALERTS BY SYMBOL** - Had to go to main menu [6] Flow Alerts to find PINS alerts
   - Should have "View Alerts" option in Symbol Detail
   - Or show recent alerts directly in Symbol Detail

2. **OI TIMING BROKEN FOR THIS USE CASE** - Shows wrong expiration dates
   - Showing 10/17 exp when we want 11/21
   - Logic appears to show "high OI strikes" but not filtering by relevant expiration
   - Needs fixing or different view

3. **COMPARE STRIKES INCOMPLETE** - Doesn't show strikes past 11/7
   - Missing the 11/21 exp that has all the action
   - Can't do IV shopping within TUI

4. **MISSING: Strike comparison tool for IV shopping**
   - What Ben needs: "Same price, different exp" OR "same exp, different strikes"
   - Goal: Find optimal entry/exit combo based on IV skew
   - Currently has to leave TUI and check Robinhood

**MINOR GAPS:**
5. **MISSING: Days to earnings on Discovery page** - Have to drill into detail to see 24d
6. **MISSING: P/C ratio by expiration** - Ben manually calculated short-term vs long-term P/C flip
   - Short-term (0-7 DTE): Put-heavy based on top strikes
   - Long-term (36-60 DTE): Call-heavy ($35 Nov21 has 21k OI)
   - Should integrate P/C ratio WITH Time Distribution bars
7. **MISSING: Moneyness + P/C context** - Would help understand if OTM calls are bullish or just hedges
8. **UX: OI Distribution should be [1], OI Timing should be [2]** - Ben's natural flow

### Trading Decisions Made

**PINS Analysis:**
- 5 flow alerts (all 11/21 exp, all CALLS)
- Institutional consensus: $35 strike (multiple alerts), $40 also active
- All alerts from Oct 13-14 (fresh positioning)
- Alert pattern: Building bullish post-earnings position (Nov 7 earnings, Nov 21 exp)
- **Decision:** Added to watchlist, waiting for better entry (price/IV pullback)
- **Next step:** Monitor for entry conditions (post-Friday opex cleanup)

**PCG Analysis:**
- Earnings: Oct 23 BMO (9 days away = **T-9, within entry window**)
- 3 flow alerts from 4d ago (Oct 10)
- Current price: $16.45 (TUI showed stale $15.97)
- **Massive call bias:** 88.6% calls, P/C ratio 0.13
- **OI split:** 54% short-term (10/17), 39.5% long-term (36-60 DTE)
- **Interesting:** No significant OI for earnings exp (Oct 31/Nov 7)
- **Pin risk:** $16 | **Max pain:** $15 (-6.1% from current)

**RH Option Chain Analysis (PCG):**
- Oct 31 $16C (7d post-earnings): IV 42.15%, $0.89
- Nov 21 $16C (29d post-earnings): IV 38%, $1.11
- Nov 21 $19C (OTM, 78k OI): IV 39%, **$0.16** ← cheap lottery

**Ben's thesis consideration:**
- Follow the money → $19 Nov21 calls (78k OI, massive institutional position)
- Very cheap ($0.16) = low risk
- Could gain from volatility alone (not just directional move)
- IV 39% but **don't know percentile** (is this high or low historically?)

**Questions/Concerns:**
1. Why no earnings-dated OI? (Oct 31 has almost nothing)
2. Is $19 realistic? Current $16.45, needs +15.5% by Nov 21
3. What's the institutional thesis for $19? (Need to check flow alerts)

### Workflow Observations

**Ben's Current Trading Methodology:**

**Two Types of Plays:**
1. **Gamma Scalp** (PCG $19C example)
   - Buy cheap OTM ($0.04-0.16)
   - Hold 1-3 days
   - Sell at 25% profit ($0.05, $0.20)
   - Only need small UL move (2-4%)
   - High % return, low $ risk
   - Experimenting with this approach

2. **Directional Earnings Bet** (ITM preferred)
   - Target earnings-dated expirations (T+7 to T+14)
   - Use RH "Simulate Returns" to compare options
   - Add multiple strikes/exps to RH watchlist
   - Set fixed future date + target price
   - Compare % returns across options
   - Pick highest % return (unless premium too high)
   - Doesn't account for IV change (Ben knows this is a gap)

**RH Workflow for Option Selection:**
1. Browse option chain (flip through strikes/exps)
2. Add interesting ones to RH watchlist (4-6 candidates)
3. Use Simulate Returns on each (same target date/price)
4. Compare % returns
5. Factor in premium cost as tiebreaker
6. Execute on "winner"

**Discipline Issues (Ben's admission):**
- No systematic entry/exit rules
- Ad-hoc comparison methodology
- Experimenting with different strategies simultaneously
- System is intended to add structure + discipline

**The Decision Gap:**
- TUI excels at DISCOVERY (finding symbols with institutional interest)
- TUI excels at CONTEXT (understanding WHY institutions are interested)
- TUI FAILS at EXECUTION (when to enter, tracking entry conditions)
- TUI COMPLETELY MISSING: Strike comparison + return simulation

**Current workaround:**
1. Use TUI to find symbol + understand thesis (PINS = bullish post-earnings)
2. Switch to Robinhood for IV shopping (find best strike/exp combo)
3. **NO SYSTEM** for tracking "waiting for better entry"
4. **NO SYSTEM** for alerting when entry conditions met

**The "Waiting for Entry" problem:**
- Ben won't buy PINS today (IV elevated, price not ideal)
- Needs to wait for: price drop, IV drop, or contract price drop
- RH only alerts on UL price (not contract price, not IV)
- RH doesn't remember WHY you set alert or what to do when triggered
- **This is where system could add huge value**

**What Ben wants:**
- "Watch this symbol for better entry conditions"
- Alert when: PINS Nov21 $35C drops below $X, or IV drops below Y%, or UL drops to $Z
- Include thesis reminder: "Bullish post-earnings play, institutions building $35 calls"

---

---

## IMPLEMENTATION LOG (2025-10-14 Evening Session)

### ✅ COMPLETED - Quick Wins

**1. Flow Alerts in Symbol Detail** ✅ DONE
- Added [5] Flow Alerts option to Symbol Detail menu
- Modified `tui_data.get_flow_alerts()` to accept optional `symbol` parameter
- Flow Alerts screen now accepts `symbol` filter in constructor
- Shows only alerts for current symbol with header "Flow Alerts - {SYMBOL}"
- **Impact:** No more exiting to main menu to find symbol-specific alerts

**2. Earnings Column in Watchlist** ✅ DONE
- Added "Earn" column to My Watchlist table
- Color-coded like Discovery page:
  - 1-7d: Bold green (entry window)
  - 8-14d: Yellow (watch zone)
  - 15-30d: Dim (planning horizon)
  - No earnings: "─"
- **Impact:** Can see earnings urgency without drilling into detail

**3. OI Timing Screen Logic** ✅ DONE
- **Root cause:** Query sorted by `expiration_date ASC` (nearest first), not by OI significance
- **Fix:** New 3-tier sort priority:
  1. Contracts with flow alerts (last 14d) → Shows institutional activity even if OI=0 now
  2. Highest OI → Shows where positions are concentrated
  3. Nearest expiration → Tiebreaker
- **Visual enhancements:**
  - Added "Alert" column with 🚨 indicator for contracts with recent flow alerts
  - Status bar shows alert count
- **Result:** Now shows PINS Nov21 $35C (high OI + alerts) instead of irrelevant 10/17 contracts
- **Impact:** Can now see the full OI narrative - where institutions built positions and when

**4. Stale Price Data Fix** ✅ DONE
- **Root cause:** Morning views used yesterday's close price for completeness
- **Ben's solution:** Use `flow_options_scans` table which updates every ~20 minutes during market hours
- **Implementation:**
  - Added `current_price` field to `v_morning_discovery` and `v_symbol_oi_detail` views
  - SQL pattern: `COALESCE((SELECT underlying_price FROM flow_options_scans WHERE symbol = X ORDER BY scan_timestamp DESC LIMIT 1), close_price)`
  - Pulls latest scan price (last 20 min), falls back to yesterday's close if market is closed
- **Updated screens:**
  - Discovery: Now shows current_price instead of close_price
  - Symbol Detail: Now shows current_price
  - My Watchlist: Now shows current_price
  - OI Distribution: Max pain distance calculated from current_price
  - Compare Strikes: Header shows current_price
- **Result:** Live prices during market hours, historical prices outside market hours
- **Impact:** Gamma scalping decisions now based on real-time data (2-4% moves matter!)

**5. Flow Alerts Sorting** ✅ DONE
- **Feature:** Added [S] key to cycle through 3 sort modes
- **Sort modes:**
  1. **Date** (newest first) - default, best for spotting new activity
  2. **Symbol** (alphabetically grouped, then by date) - best for pattern recognition
  3. **Score** (highest significance first) - best for finding highest-quality alerts
- **Implementation:**
  - Added `sort_mode` attribute to FlowAlertsScreen
  - Sort logic applied in `_load_alerts()` before populating table
  - Header dynamically shows current sort mode
  - Toast notification confirms sort change
- **Impact:** Can now group PINS alerts together to see institutional pattern (5 alerts, all 11/21 CALLS, $35 & $40 strikes)

### 🔧 NEXT UP

None - all quick wins completed!

---

## Action Items / Improvements

### CRITICAL (Blocking real trading decisions)

**1. Build "Options Comparison & Simulation" tool** (replaces RH workflow)
   - Purpose: Replace RH's "Simulate Returns" feature
   - Input: Target date + target UL price
   - Show 4-6 candidate options side-by-side
   - Calculate projected returns for each (with IV modeling)
   - Highlight "winner" based on % return
   - Account for theta decay + IV crush/expansion
   - Filter: ITM/ATM/OTM, by expiration range

   **This is the killer feature** - eliminates RH dependency for decision-making

**2. Build "Entry Watch" system** - track symbols waiting for ideal entry conditions
   - Set multiple condition types: contract price, IV%, UL price
   - Store thesis/reasoning with each watch
   - Alert when conditions met
   - Integration with watchlist/capital planner
   - Support for both play types: gamma scalp + directional

**3. Add real-time price updates**
   - Currently showing stale prices (PCG $15.97 vs actual $16.45)
   - Need live data or clear "as of" timestamp
   - Critical for gamma scalping (2-4% moves matter)

**4. Add Flow Alert filtering by symbol** in Symbol Detail screen
   - Show recent alerts for current symbol
   - Or add "View Alerts" button that filters Flow Alerts page

**5. Add sorting to Flow Alerts screen**
   - Group by symbol, sort by date
   - Currently random order makes pattern recognition hard

**6. Fix OI Timing screen** - show relevant expirations
   - Currently shows wrong exp dates (10/17 instead of 11/21)
   - Need to understand the filtering logic

**7. Extend Compare Strikes** to show all relevant expirations
   - Currently cuts off at 11/7 (earnings date)
   - Missing 11/21 which has all the action

### HIGH PRIORITY (IV Shopping automation)
6. **Build IV Shopping view** - compare options for same symbol
   - Group by expiration, compare strikes
   - Show IV% (what RH shows) AND IV percentile (our edge)
   - Highlight IV skew opportunities
   - "Same price, different exp" or "same exp, different strikes" comparison

7. **Add IV percentile to all option displays**
   - RH only shows IV% (absolute)
   - IV percentile helps identify mispricing
   - Use for entry timing (buy when IV percentile low)

### MEDIUM PRIORITY (UX improvements)
8. **Add days to earnings column to Discovery page**
9. **Add P/C ratio by expiration to OI Distribution**
10. **Swap menu order: OI Distribution [1], OI Timing [2]**
11. **Add moneyness + P/C context to better interpret OTM positioning**

