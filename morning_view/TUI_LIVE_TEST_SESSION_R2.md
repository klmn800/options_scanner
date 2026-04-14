# TUI Live Test Session - Round 2

**Date:** 2025-10-15
**Goal:** Verify R1 fixes + continue $1000 allocation planning
**User:** Ben

---

## Round 1 Fixes to Verify

### ✅ Flow Alerts in Symbol Detail - PASS ✓
- [x] Test: Navigate to symbol detail, press [5]
- [x] Verify: Shows only that symbol's alerts
- [x] Verify: Header shows "Flow Alerts - {SYMBOL}"
- **Result:** Works perfectly! Data matches flow_alerts table, columns display correctly
- **Enhancement Ideas:**
  - Click alert → drill into contract OI history (oi_daily time series)
  - Add Expiration sorting capability
  - Remove Moneyness column to prevent horizontal scroll (cosmetic space saver)

### ✅ Earnings Column in Watchlist - PASS (with column order issue) ⚠️
- [x] Test: Open My Watchlist
- [x] Verify: "Earn" column present with color coding
- [x] Verify: Green (1-7d), Yellow (8-14d), Dim (15-30d)
- **Issue:** Column order doesn't match Discovery page
  - Should be: `Symbol | Triggers | Earn | New | Recent | Active | Days | Price | Added`
  - Currently: `Symbol | Triggers | New | Recent | Active | Days | Earn | Price | Added`
- **Fix Needed:** Move "Earn" column before "New" to align with Discovery page
- **Reason:** Workflow benefit - eyes scan same position across screens

### ✅ OI Timing Screen Logic - PASS ✓ (with enhancements needed)
- [x] Test: Open PINS symbol detail → OI Timing
- [x] Verify: Shows Nov21 contracts (not just 10/17)
- [x] Verify: Nov21 $35C appears (high OI + alerts)
- **What Works:**
  - Shows relevant expirations (Nov21)
  - Can sort by expiration, build date, OI
  - Can select contract → see full history (Contract History screen)
  - Contract History is useful!
- **Issues Found:**
  1. **Alert column is blank** - No 🚨 indicators despite having flow alerts
     - Expected: Contracts matching flow_alerts should show 🚨
     - Reality: Column exists but empty
  2. **IV%ile column unclear** - Appears to be "IV %ile 20d" but not labeled
     - Need clearer column name or tooltip
  3. **Header blank space** - Should have brief description of page purpose
  4. **Column alignment** - Doesn't match Flow Alerts screen
  5. **Date sorting missing** - Can't sort by Date column
  6. **Data freshness ambiguity** - Mixes morning/EOD data (OI, IV) with build data
- **Enhancement Ideas:**
  - Add visual separator between "Built" and "Position" columns
  - Move "Position" to end for clarity
  - Add "Current Price" to header box (use flow_options_scans for real-time)
  - Consider real-time IV/IV%ile20d during market hours

### ✅ Real-Time Pricing - PARTIAL FAIL ⚠️
- [x] Test: Compare Discovery/Watchlist prices to RH
- **Result:** Close but not current
  - Using yesterday's close_price from oi_daily
  - Some symbols lower than RH current price
- **Root Cause:** My Watchlist using old close_price, not current_price from flow_options_scans
- **Fix Needed:** Use same COALESCE pattern as Discovery page
  - `COALESCE((SELECT underlying_price FROM flow_options_scans...), close_price)`
- **Impact:** Less critical for watchlist than Discovery, but should match

### ✅ Flow Alerts Sorting - PASS ✓
- [x] Test: Flow Alerts screen → press [S] repeatedly
- [x] Verify: Cycles through Date → Symbol → Score
- [x] Verify: Symbol mode groups PINS alerts together
- [x] Verify: Toast notification confirms sort change
- **Result:** Works as designed!

---

## Remaining Pain Points to Test

### Compare Strikes - Missing Expirations
- **Issue:** Cuts off at earnings date, missing post-earnings exps
- **Test:** PCG Compare Strikes (earnings Oct 23, should show Oct 31, Nov 21)
- **Expected:** Currently stops at Nov 7 (or earlier)

### IV Percentile - Missing Everywhere
- **Issue:** Can't see if IV is elevated or depressed historically
- **Test:** Check any option display (OI Distribution, Compare Strikes)
- **Expected:** Only shows absolute IV%, not percentile rank

### OI Distribution - Menu Order
- **Issue:** Ben's natural flow is [1] Distribution, [2] Timing (currently reversed)
- **Test:** Symbol Detail menu numbering
- **Expected:** Currently [1] Timing, [2] Distribution

---

## New Issues Discovered

### UX Improvements Needed

**My Watchlist:**
- Remove confirmation dialog when pressing [X] to remove from list
- Streamline workflow (currently shows "Are you sure?" modal)

**Discovery Page:**
- Add sorting capability (currently no sort option)
- Sort modes needed: Symbol, Last (alert date), Score, Earn (days to earnings)
- Should match Flow Alerts [S] key pattern

### OI Timing - Alert Column Logic Issue

**Problem:** Alert column doesn't populate despite matching flow alerts

**Example:** LCID $23.5 CALL 10/17
- Flow alert exists: 2025-10-08
- OI Timing shows: Built 2025-10-09 (correct - OI appears day after alert)
- Alert column: Empty (should show 🚨)

**Root cause to investigate:** Alert matching logic may be too strict
- Possibly checking exact date match instead of "alert exists within X days of build"
- Need to verify join logic between flow_alerts and oi_daily

### Contract History - Data Quality Issues

**LCID $23.5 CALL 10/17 example:**

**Issues Found:**
1. **OI Delta broken after 2025-10-07**
   - Shows "N/A" for OI Δ% column
   - OI values exist, but delta calculation failing
   - Possibly division by zero or missing previous day data?

2. **IV Delta questionable**
   - Shows values but unclear if calculation is correct
   - Need to verify: Is this IV% change or IV percentile change?
   - Color coding unclear (red/green for up/down?)

**Enhancement Opportunities:**
- Add **Price** column (contract price, not just @Price at build)
- Add **Price Δ** or **Price %** to track contract value changes
- Add **Volume Δ** to see unusual activity spikes
- Clarify column headers (IV Δ = IV% change or percentile?)
- Fix OI Δ% calculation for recent dates

**Investigation Needed:**
1. **OI Δ% calculation failure** - Check for:
   - Missing dates in oi_daily sequence (data gaps breaking LAG() window function)
   - Division by zero when previous OI = 0
   - NULL handling in delta calculation

2. **IV Δ definition** - Clarify what's shown:
   - Currently: Likely IV% point change (85% → 87% = +2)
   - Consider adding: IV percentile rank change (more useful for "is IV elevated?" question)
   - Option to show both or toggle between them

3. **Price movement context** - Add underlying price data:
   - Daily OHLC bars in Contract History
   - Or just Price Δ column showing daily underlying price change
   - Helps correlate contract performance with underlying movement
   - Eliminates need to check RH for price timing

### Trading Intelligence Discovery - LCID Story

**Flow Alert Timeline:**
- 10/8: Big CALLS bought at $23.50 (10/17 exp)
- Price dropped immediately after
- 10/8: PUTs bought at exact bottom ($21, $19 strikes 11/21 exp)
- Price recovered slightly but not enough for calls to profit
- Puts timed perfectly at bottom

**Insight:** Institutional traders aren't always right on timing, but the PUT buyers nailed the entry at the bottom. This kind of post-mortem analysis is valuable for learning market dynamics.

**Current workflow gap:** Had to use RH to check underlying price movement timing. Should be able to see intraday price chart or daily OHLC within TUI.

## New Workflow Testing

### Capital Planner
- [ ] Navigate to Capital Planner from main menu
- [ ] Review weekly capital allocation bars
- [ ] Try adding a position (PINS or PCG)
- [ ] Verify: Pre-fills earnings date from database
- [ ] Verify: Calculator shows total cost + target warnings
- [ ] Test: "View Timeline" (Gantt chart view)

### Earnings Intelligence
- [ ] Check if Earnings Calendar is accessible
- [ ] Look for expected vs historical move data
- [ ] See if IV arbitrage opportunities are surfaced

---

## Symbol Search Continuation

**Goal:** Find more T-9 to T-14 candidates for $1000 allocation

**Criteria:**
- Earnings in 9-14 days (entry window)
- Flow alerts (institutional interest)
- High confluence score (3+)
- IV at reasonable levels (need percentile when available)

**Symbols to investigate:**
- From watchlist: INTC, SOFI, ALK, PCG (already reviewed)
- From discovery: (will populate during session)

---

## Session Notes

### Features Used (New)
- [ ] Flow Alerts from Symbol Detail [5]
- [ ] OI Timing with alert indicators
- [ ] Flow Alerts sorting [S]
- [ ] Capital Planner
- [ ] Earnings Calendar

### What Worked Well (R2)
*(Document improvements from R1 fixes)*

### New Pain Points Discovered
*(Issues found during R2 testing)*

### Trading Decisions Made (R2)
*(Symbols analyzed, positions planned)*

---

## Action Items from R2
*(New features/fixes needed)*

