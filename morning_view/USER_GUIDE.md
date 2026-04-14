# Morning Views - User Guide
**Last Updated:** 2025-10-07
**Version:** 2.0 (Hybrid Data Strategy)

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [System Overview](#system-overview)
3. [The Four Views](#the-four-views)
4. [Daily Workflow](#daily-workflow)
5. [Feature Deep Dives](#feature-deep-dives)
6. [CLI Commands](#cli-commands)
7. [Analysis Examples](#analysis-examples)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Morning Routine (5 minutes)

**1. Check Your Email (7:30 AM)**
- Morning Views sends daily watchlist email with .docx attachment
- Top 20 symbols ranked by confluence score
- Shows: OI bias, conviction level, catalysts, alerts

**2. Review Watchlist**
```bash
# Get full watchlist
python oracle_bridge.py "show me today's watchlist"

# Or query directly
python tools/direct_db_query.py --sql "SELECT * FROM v_morning_watchlist LIMIT 10"
```

**3. Deep Dive on Interesting Symbols**
```bash
# Example: Analyze KDP from watchlist
python oracle_bridge.py "show me KDP OI timing context and top strikes"
```

**4. Compare Options for Trade Setup**
```bash
# See all KDP calls expiring in 2-4 weeks
python tools/direct_db_query.py --sql "
  SELECT strike, dte, last_price, delta, breakeven_move_pct, delta_per_dollar
  FROM v_option_comparison
  WHERE symbol='KDP' AND option_type='CALL' AND dte BETWEEN 14 AND 30
  ORDER BY delta_per_dollar DESC"
```

**5. Make Decision**
- Use OI timing to verify smart money positioning
- Check confluence score (3+ = high confidence)
- Verify breakeven is achievable based on catalysts

---

## System Overview

### What is Morning Views?

Morning Views is a **daily options watchlist system** that:
1. Scans 800 symbols (KLMN universe) for option activity
2. Ranks top 20 by confluence of signals
3. Shows OI positioning, timing, and Greek exposures
4. Delivers actionable watchlist via email

### Data Strategy: Hybrid Approach

**Critical Concept:** Morning Views combines two data sources:

| Data Type | Source | Why |
|-----------|--------|-----|
| **Open Interest** | Today's scan (6:35 AM) | Fresh positioning data |
| **Volume, Price, Greeks** | Yesterday's complete data | Full trading day needed |

This gives you the **most accurate morning picture**:
- See today's fresh OI builds (who's positioning NOW)
- Use yesterday's complete data for pricing/Greeks (reliable metrics)

### When Does It Run?

**Automatic Schedule (via main.py):**
```
6:35 AM  → OID morning scan (updates OI only)
7:20 AM  → Query database sync (datalake → datalake_query)
7:30 AM  → Morning Views generation (creates SQL views + email)
```

**Manual Execution:**
```bash
cd morning_view
python morning_views.py
```

---

## The Four Views

Morning Views creates 4 SQL views in `datalake_query.db`:

### 1. v_morning_watchlist
**Purpose:** Daily ranked list of top 20 symbols worth analyzing

**Key Features:**
- Confluence scoring (0-5 points based on signal alignment)
- Direction bias (BULLISH/BEARISH/NEUTRAL from put/call ratio)
- Conviction level (HIGH/MEDIUM/LOW from OI concentration)
- Primary signal (what flagged this symbol)
- Earnings catalyst detection
- Flow alert counting
- News sentiment aggregation

**Best For:** Discovering new opportunities each morning

**Schema:** See `Schema_v_morning_watchlist.txt`

---

### 2. v_symbol_oi_detail
**Purpose:** Complete OI distribution pattern for one symbol

**Key Features:**
- Total OI breakdown (calls vs puts)
- Top 5 call/put strikes with OI levels
- Time distribution (0-7 DTE, 8-21 DTE, 22-35 DTE, 36-60 DTE)
- Moneyness distribution (ITM/ATM/OTM percentages)
- Greek exposures (net delta, total gamma, net vega)
- Max pain level

**Best For:** Understanding full positioning on a symbol

**Schema:** See `Schema_v_symbol_oi_detail.txt`

---

### 3. v_oi_timing_context
**Purpose:** "Smart Money vs Retail" - when was OI built and at what price?

**Key Features:**
- OI build start date (when 50% of current OI was first reached)
- OI build start price (stock price when building started)
- Positioning type (PREDICTIVE vs CHASING)
- Price movement since build
- Days elapsed since build

**Best For:** Identifying smart money positions vs retail bagholders

**Schema:** See `Schema_v_oi_timing_context.txt`

**This is the "killer feature" per Ben's feedback (2025-10-06)**

---

### 4. v_option_comparison
**Purpose:** Side-by-side comparison of contracts for choosing strikes

**Key Features:**
- Breakeven calculations (price and % move required)
- Delta per dollar (leverage efficiency)
- Intrinsic vs extrinsic value breakdown
- Theta decay in dollars per day
- Vega sensitivity to IV changes
- Gamma zone detection
- **NEW: Time-to-Target Analysis** (probability-based timing metrics)

**Time-to-Target Analysis (Added 2025-10-13):**
- **required_move_to_strike_pct**: % move needed to reach strike (OTM only)
- **days_to_reach_strike**: Estimated days using IV formula `365 × (Required Move % / IV)²`
- **time_advantage_ratio**: DTE / days_to_reach_strike (how much time cushion you have)
- **time_pressure_level**: COMFORTABLE (>1.5x), TIGHT (1.0-1.5x), or CRITICAL (<1.0x)

**Interpreting Time-to-Target:**
- **Ratio > 1.5**: COMFORTABLE - plenty of time to reach target
- **Ratio 1.0-1.5**: TIGHT - need stock to move fairly soon
- **Ratio < 1.0**: CRITICAL - not enough time, need immediate move

**Best For:** Choosing specific strike/expiration for trade entry with time probability

**Schema:** See `Schema_v_option_comparison.txt`

---

## Daily Workflow

### Workflow 1: Morning Discovery
**Goal:** Find today's best opportunities

```bash
# Step 1: Get watchlist (shows top 20, sorted by confluence)
python oracle_bridge.py "show me today's watchlist"

# Step 2: Filter by signal type if desired
python tools/direct_db_query.py --sql "
  SELECT symbol, confluence_score, primary_signal, direction_bias, active_alerts_count
  FROM v_morning_watchlist
  WHERE primary_signal = 'FLOW_ALERT'
  ORDER BY confluence_score DESC"

# Step 3: Check earnings plays
python tools/direct_db_query.py --sql "
  SELECT symbol, earnings_days_ahead, exp_move_pct, hist_move_pct, earnings_play_signal
  FROM v_morning_watchlist
  WHERE earnings_days_ahead IS NOT NULL
  ORDER BY earnings_days_ahead"
```

**Decision Point:** Which symbol looks interesting?

---

### Workflow 2: Deep Dive Analysis
**Goal:** Understand positioning on a specific symbol

**Example: Analyzing KDP**

```bash
# Step 1: Get OI distribution
python tools/direct_db_query.py --sql "
  SELECT symbol, total_open_interest, put_call_ratio,
         top_call_display, top_put_display,
         oi_0_7_days_percent, oi_8_21_days_percent
  FROM v_symbol_oi_detail
  WHERE symbol='KDP'"

# Step 2: Check OI timing (smart money vs retail)
python tools/direct_db_query.py --sql "
  SELECT symbol, strike, option_type, expiration_date,
         open_interest, positioning_type,
         oi_build_start_date, oi_build_start_price, current_price,
         oi_build_price_move_pct, oi_build_days_since
  FROM v_oi_timing_context
  WHERE symbol='KDP'
  ORDER BY open_interest DESC
  LIMIT 10"

# Step 3: Check Greek exposures
python tools/direct_db_query.py --sql "
  SELECT symbol, net_delta_exposure, total_gamma_exposure,
         max_gamma_strike, net_vega_exposure
  FROM v_symbol_oi_detail
  WHERE symbol='KDP'"
```

**Key Questions to Answer:**
1. Is OI building PREDICTIVELY (smart money) or CHASING (retail)?
2. Where is OI concentrated (which strikes/expirations)?
3. Is net delta positive (bullish) or negative (bearish)?
4. Where is max gamma (pin risk)?

---

### Workflow 3: Trade Selection
**Goal:** Choose specific contract to trade

**Example: Bullish on MGM, need to pick strike/expiration**

```bash
# Step 1: See all calls expiring in 2-4 weeks
python tools/direct_db_query.py --sql "
  SELECT strike, expiration_date, dte, last_price,
         delta, breakeven_move_pct, delta_per_dollar,
         theta_decay_dollars, open_interest
  FROM v_option_comparison
  WHERE symbol='MGM'
    AND option_type='CALL'
    AND dte BETWEEN 14 AND 30
  ORDER BY delta_per_dollar DESC"

# Step 2: Compare 2-3 finalists
python tools/direct_db_query.py --sql "
  SELECT strike, last_price, delta, breakeven_price, breakeven_move_pct,
         intrinsic_value, extrinsic_value, theta_decay_dollars
  FROM v_option_comparison
  WHERE symbol='MGM'
    AND option_type='CALL'
    AND strike IN (35.0, 36.0, 37.0)
    AND dte BETWEEN 7 AND 14
  ORDER BY strike"
```

**Decision Framework:**
- **Low breakeven_move_pct** = easier to achieve, but less leverage
- **High delta_per_dollar** = more leverage, but riskier
- **Low theta_decay** = more time to be right
- **High open_interest** = liquidity for exit

**Real Example (Ben's MGM Trade, 2025-10-06):**
```
Symbol: MGM
Contract: $36 CALL (10/24)
Entry: $0.50
Breakeven: $36.50 (7.6% move from $33.93)
Decision: OI timing showed PREDICTIVE positioning 3 days ago,
          conviction play expecting continuation
```

---

## Feature Deep Dives

### Confluence Score (0-5 Points)

**What It Measures:** How many independent signals are aligned on this symbol

**Scoring System:**
| Signal | Points | Criteria |
|--------|--------|----------|
| **Flow Alerts** | +1 | Active alert in last 7 days |
| **Volume Surge** | +1 | Option volume > 1.5x 20-day avg (NOTE: Currently broken, returns 0) |
| **Earnings Catalyst** | +1 | Earnings in 1-30 days |
| **Strong Sentiment** | +1 | News sentiment score >= 0.10 or <= -0.10 (last 5 days) |
| **High OI Conviction** | +1 | Top call or put strike > 30% of total OI |

**Interpretation:**
- **4-5 points:** High confidence, multiple confirming signals
- **2-3 points:** Moderate confidence, worth investigating
- **0-1 points:** Weak setup, only on watchlist for single signal

**Known Issue:** Max score currently 4/5 due to volume aggregation bug.

---

### OI Timing Analysis (Smart Money vs Retail)

**The Killer Question:**
> "Did people buy $12 puts when stock was $13.50 (predictive) or when stock was $11.30 (chasing)?"

**How It Works:**
1. System tracks historical OI for each contract
2. Identifies when OI first reached 50% of current level
3. Records stock price at that moment
4. Compares build price to current price

**Positioning Types:**

**PREDICTIVE Positioning (Smart Money):**
- **Calls:** Built when stock was LOWER, now stock is HIGHER
  - Example: Bought $36 calls at $34, stock now $36 → predicted the move
- **Puts:** Built when stock was HIGHER, now stock is LOWER
  - Example: Bought $12 puts at $13.50, stock now $11.27 → predicted the drop

**CHASING Positioning (Retail/Momentum):**
- **Calls:** Built when stock was LOWER, stock still LOWER (or built HIGHER, now HIGHER)
  - Example: Bought $36 calls at $36, stock now $33.93 → chasing peak, now underwater
- **Puts:** Built when stock was LOWER, stock still LOWER (or built HIGHER, now even HIGHER)
  - Example: Bought $12 puts at $11.30, stock now $11.27 → chasing after move already happened

**Time Context:**
- **Fresh builds (0-7 days):** More actionable, recent conviction
- **Old builds (30+ days):** Less relevant unless still holding/adding

**Example Query:**
```sql
SELECT symbol, strike, option_type, open_interest,
       positioning_type, oi_build_start_date, oi_build_start_price,
       current_price, oi_build_price_move_pct, oi_build_days_since
FROM v_oi_timing_context
WHERE symbol = 'AAL'
  AND positioning_type LIKE 'PREDICTIVE%'
ORDER BY open_interest DESC;
```

**Trading Application:**
- Look for PREDICTIVE + recent (0-7 days) = early smart money positioning
- Avoid CHASING + old (20+ days) + negative move = likely bagholders

---

### Direction Bias

**How It's Calculated:**
Based on put/call ratio (OI, not volume):

| Put/Call Ratio | Direction Bias |
|----------------|----------------|
| > 2.0 | BEARISH |
| 1.3 - 2.0 | SOMEWHAT_BEARISH |
| 0.8 - 1.3 | NEUTRAL |
| 0.5 - 0.8 | SOMEWHAT_BULLISH |
| < 0.5 | BULLISH |

**Example:**
- KDP: Put/call ratio = 0.42 → BULLISH bias
- AAL: Put/call ratio = 2.1 → BEARISH bias

**What It Means:**
- Current OI positioning leans in this direction
- NOT a prediction, just what the market is positioned for
- Check OI timing to see if positioning is smart money or retail

---

### Conviction Level

**How It's Calculated:**
Based on OI concentration at single strikes:

| Top Strike % of Total OI | Conviction Level |
|--------------------------|------------------|
| > 30% | HIGH |
| 15-30% | MEDIUM |
| < 15% | LOW |

**Example:**
- MGM $36 CALL has 24,239 OI out of 95,000 total = 25.5% → MEDIUM conviction
- If it was 35,000 OI = 36.8% → HIGH conviction

**What It Means:**
- **HIGH:** Market is betting heavily on specific strike (strong view)
- **MEDIUM:** Moderate concentration, some agreement on level
- **LOW:** OI dispersed across many strikes (uncertain/hedged)

**Trading Application:**
- HIGH conviction + PREDICTIVE timing = follow smart money
- HIGH conviction + CHASING + underwater = potential squeeze if reverses
- LOW conviction = less clear, need other signals

---

### Greek Exposures

**Net Delta Exposure:**
- Total directional exposure in shares
- Positive = net bullish positioning
- Negative = net bearish positioning
- Example: KDP = -527,826 shares → net bearish

**Total Gamma Exposure:**
- How fast delta changes near current price
- High gamma = rapid P&L swings
- Gamma peaks ATM, decays OTM/ITM

**Max Gamma Strike:**
- Strike with most gamma concentration
- "Pin risk" - market may gravitate here on expiration
- Example: KDP max gamma at $25.00

**Net Vega Exposure:**
- Sensitivity to IV changes
- Positive = benefits from IV expansion (long options)
- Negative = benefits from IV contraction (short options)
- Example: KDP = +34,126 → long vega, wants IV to rise

**Example Query:**
```sql
SELECT symbol, close_price, net_delta_exposure,
       total_gamma_exposure, max_gamma_strike, net_vega_exposure
FROM v_symbol_oi_detail
WHERE symbol IN (SELECT symbol FROM v_morning_watchlist LIMIT 5);
```

---

### Volume Profile Analysis (Added 2025-10-13)

**What It Is:**
Identifies price levels where significant trading occurred historically. These represent zones where institutions accumulated/distributed positions.

**Key Concepts:**
- **Point of Control (POC)**: Price level with highest volume concentration - strongest support/resistance
- **Value Area**: Price range containing 70% of total volume (fair value zone)
- **High Volume Nodes (HVN)**: Price levels with above-average volume (>1.5x) - "sticky" areas where price tends to return
- **Low Volume Nodes (LVN)**: Price gaps with minimal volume (<0.3x) - "breakout zones" where price moves quickly

**Trading Application:**
- HVN levels act as price magnets - target strikes near these for higher probability
- LVN areas are "speed zones" - price moves fast through them, good for stop placement
- Value Area defines fair value range for position sizing
- POC is the strongest support/resistance level

**Integrated into Symbol Detail:**
Volume profile automatically appears when viewing symbol details (see `python morning_views.py --symbol NVDA`). Shows:
- Current price context (above/below/within value area)
- Distance from POC (%)
- Top 3 HVN levels (price magnets)
- Nearest resistance/support zones

**Standalone Tool:**
```bash
# Generate volume profile for any symbol
python tools/volume_profile_calculator.py --symbol NVDA
python tools/volume_profile_calculator.py --symbol KDP --lookback 90 --output profile.json
```

**Example Interpretation:**
```
Symbol: NVDA
Current Price: $188.32 (ABOVE VALUE AREA)
POC: $178.00 - Strongest support if price pulls back
Value Area: $174-$186 (fair value zone)
HVN Above: None (price has broken above recent accumulation)
HVN Below: $171.00 (first support level)

Trading Insight: Price has left value area above, indicating breakout.
Watch for pullback to POC ($178) for re-entry opportunity.
```

---

## CLI Commands

### Quick Queries with Oracle Bridge

**Natural language queries (uses Claude API, costs ~$0.01-0.03):**

```bash
# Get watchlist
python oracle_bridge.py "show me today's watchlist"

# Deep dive on symbol
python oracle_bridge.py "analyze KDP OI timing and positioning"

# Find specific patterns
python oracle_bridge.py "show me all PREDICTIVE call positions with high OI"

# Earnings plays
python oracle_bridge.py "what symbols have earnings this week?"
```

---

### Direct SQL Queries (Fast, Free)

**Watchlist queries:**
```bash
# Full watchlist
python tools/direct_db_query.py --sql "SELECT * FROM v_morning_watchlist"

# Top 5 by confluence
python tools/direct_db_query.py --sql "SELECT symbol, confluence_score, direction_bias, primary_signal FROM v_morning_watchlist LIMIT 5"

# Flow alert plays only
python tools/direct_db_query.py --sql "SELECT * FROM v_morning_watchlist WHERE primary_signal = 'FLOW_ALERT'"

# Earnings plays
python tools/direct_db_query.py --sql "SELECT symbol, earnings_days_ahead, exp_move_pct, earnings_play_signal FROM v_morning_watchlist WHERE earnings_days_ahead IS NOT NULL"
```

**OI timing queries:**
```bash
# Smart money positions (PREDICTIVE)
python tools/direct_db_query.py --sql "SELECT symbol, strike, option_type, open_interest, positioning_type, oi_build_start_date, oi_build_price_move_pct FROM v_oi_timing_context WHERE positioning_type LIKE 'PREDICTIVE%' ORDER BY open_interest DESC LIMIT 20"

# Fresh builds (last 3 days)
python tools/direct_db_query.py --sql "SELECT symbol, strike, option_type, open_interest, oi_build_days_since FROM v_oi_timing_context WHERE oi_build_days_since <= 3 ORDER BY open_interest DESC"

# Specific symbol timing
python tools/direct_db_query.py --sql "SELECT * FROM v_oi_timing_context WHERE symbol='KDP' ORDER BY open_interest DESC LIMIT 10"
```

**Symbol detail queries:**
```bash
# Full OI breakdown for symbol
python tools/direct_db_query.py --sql "SELECT * FROM v_symbol_oi_detail WHERE symbol='MGM'"

# Time distribution
python tools/direct_db_query.py --sql "SELECT symbol, oi_0_7_days_percent, oi_8_21_days_percent, oi_22_35_days_percent FROM v_symbol_oi_detail WHERE symbol='AAL'"

# Greek exposures
python tools/direct_db_query.py --sql "SELECT symbol, net_delta_exposure, total_gamma_exposure, max_gamma_strike FROM v_symbol_oi_detail WHERE symbol IN (SELECT symbol FROM v_morning_watchlist LIMIT 10)"
```

**Option comparison queries:**
```bash
# All calls for symbol (2-4 week expirations)
python tools/direct_db_query.py --sql "SELECT strike, dte, last_price, delta, breakeven_move_pct, delta_per_dollar FROM v_option_comparison WHERE symbol='KDP' AND option_type='CALL' AND dte BETWEEN 14 AND 30 ORDER BY delta_per_dollar DESC"

# Compare specific strikes
python tools/direct_db_query.py --sql "SELECT strike, last_price, breakeven_price, delta, theta_decay_dollars, intrinsic_value, extrinsic_value FROM v_option_comparison WHERE symbol='MGM' AND option_type='CALL' AND strike IN (35.0, 36.0, 37.0) ORDER BY strike"

# High leverage plays (best delta per dollar)
python tools/direct_db_query.py --sql "SELECT symbol, strike, option_type, last_price, delta, delta_per_dollar FROM v_option_comparison WHERE symbol IN (SELECT symbol FROM v_morning_watchlist LIMIT 5) ORDER BY delta_per_dollar DESC LIMIT 20"
```

---

### Schema Exploration

```bash
# See all tables
python tools/direct_db_query.py --tables

# View specific table schema
python tools/direct_db_query.py --schema v_morning_watchlist
python tools/direct_db_query.py --schema v_oi_timing_context

# Check what data exists
python tools/direct_db_query.py --sql "SELECT MAX(trade_date) FROM oi_daily"
python tools/direct_db_query.py --sql "SELECT COUNT(*) FROM v_morning_watchlist"
```

---

## Analysis Examples

### Example 1: Morning Discovery → Trade (Real Trade: MGM 2025-10-06)

**Context:** Sunday evening, reviewing Monday's watchlist

**Step 1: Check Watchlist**
```bash
python oracle_bridge.py "show me today's watchlist"
```

**Result:** MGM appears with:
- Confluence score: 3
- Direction bias: SOMEWHAT_BULLISH
- Primary signal: OI_SIGNAL
- Active alerts: 2 in last 7 days

**Step 2: Check OI Timing**
```sql
SELECT symbol, strike, option_type, open_interest,
       positioning_type, oi_build_start_date,
       oi_build_start_price, current_price,
       oi_build_price_move_pct
FROM v_oi_timing_context
WHERE symbol='MGM' AND option_type='CALL'
ORDER BY open_interest DESC
LIMIT 5;
```

**Result:** $36 CALL (10/24) shows:
- OI: 24,239 contracts
- Positioning: CHASING (bought calls after stock rose)
- Build date: 2025-10-03 (3 days ago - FRESH)
- Build price: $34.00
- Current price: $33.93
- Move since: -0.2%

**Interpretation:**
- Recent positioning (3 days = still relevant)
- Bought near current level, not underwater yet
- Looking for continuation higher
- Not smart money predicting early, but conviction play

**Step 3: Check Greeks & Distribution**
```sql
SELECT symbol, net_delta_exposure, total_gamma_exposure,
       max_gamma_strike, oi_0_7_days_percent
FROM v_symbol_oi_detail
WHERE symbol='MGM';
```

**Result:**
- Net delta: +450,000 (bullish positioning)
- Max gamma: $36 (same strike as target)
- Near-term OI: 45% in 0-7 DTE (event expected soon?)

**Step 4: Pick Strike**
```sql
SELECT strike, last_price, delta, breakeven_move_pct,
       delta_per_dollar, theta_decay_dollars
FROM v_option_comparison
WHERE symbol='MGM'
  AND option_type='CALL'
  AND strike BETWEEN 35.0 AND 37.0
  AND dte BETWEEN 7 AND 14;
```

**Result:**
| Strike | Price | Delta | Breakeven Move | Delta/$ | Theta |
|--------|-------|-------|----------------|---------|-------|
| $35 | $1.20 | 0.55 | +4.2% | 0.46 | -$0.08 |
| $36 | $0.50 | 0.32 | +7.6% | 0.64 | -$0.04 |
| $37 | $0.20 | 0.15 | +10.4% | 0.75 | -$0.02 |

**Decision:** $36 CALL at $0.50
- Reasoning: High delta per dollar (0.64), reasonable breakeven (+7.6%), matches max gamma strike
- Entry: 2 contracts @ $0.50 = $100 total risk
- Target: 50-100% gain on directional move
- Stop: -50% or if OI timing shows reversal

**Outcome:** (Per Ben's feedback) Position taken, OI timing feature was "invaluable"

---

### Example 2: Avoiding Bagholder Traps

**Scenario:** AAL appears on watchlist with BEARISH bias

**Step 1: Check OI Timing**
```sql
SELECT symbol, strike, option_type, open_interest,
       positioning_type, oi_build_start_date,
       oi_build_start_price, current_price,
       oi_build_price_move_pct, oi_build_days_since
FROM v_oi_timing_context
WHERE symbol='AAL' AND option_type='PUT'
ORDER BY open_interest DESC;
```

**Result 1:** $12 PUT (10/31) - 15,000 OI
- Positioning: PREDICTIVE
- Build date: 2025-08-15 (48 days ago - OLD)
- Build price: $13.50
- Current: $11.27
- Move: -16.5%
- **Interpretation:** Smart money positioned early, big profit. Likely exiting soon.

**Result 2:** $12 PUT (10/31) - 8,000 OI
- Positioning: CHASING
- Build date: 2025-10-01 (2 days ago - FRESH)
- Build price: $11.30
- Current: $11.27
- Move: -0.3%
- **Interpretation:** Late to party, bought after drop. Possible bagholders if bounces.

**Decision:** AVOID both
- PREDICTIVE position is old and deep ITM, smart money likely taking profits
- CHASING position is retail buying after move, weak setup
- No edge following either group here

---

### Example 3: Earnings Play Evaluation

**Scenario:** Looking for earnings plays in next 7 days

**Step 1: Filter Watchlist**
```sql
SELECT symbol, earnings_days_ahead, exp_move_pct,
       hist_move_pct, diff_move_pct, earnings_play_signal,
       direction_bias, confluence_score
FROM v_morning_watchlist
WHERE earnings_days_ahead BETWEEN 1 AND 7
ORDER BY ABS(diff_move_pct) DESC;
```

**Result:** XYZ has earnings in 3 days
- Expected move (IV): 12%
- Historical avg: 8%
- Difference: +4% (IV pricing in larger move than usual)
- Signal: AVOID (overpriced)
- Direction bias: NEUTRAL
- Confluence: 2

**Step 2: Check OI for Directional Clues**
```sql
SELECT symbol, put_call_ratio, top_call_display, top_put_display
FROM v_symbol_oi_detail
WHERE symbol='XYZ';
```

**Result:**
- Put/call: 1.8 (bearish lean)
- Top call: $50 (ATM)
- Top put: $45 (OTM)

**Decision:** PASS
- IV overpriced vs historical (diff_move_pct = +4%)
- No clear directional conviction (put/call = 1.8 is mild)
- Confluence score only 2 (weak setup)
- Avoid expensive straddle/strangle environment

---

## Troubleshooting

### Problem: Watchlist is Empty

**Symptoms:**
```sql
SELECT COUNT(*) FROM v_morning_watchlist;
-- Returns: 0
```

**Diagnosis:**
1. Check if views exist:
   ```bash
   python tools/direct_db_query.py --sql "SELECT name FROM sqlite_master WHERE type='view'"
   ```

2. Check if today's OI data exists:
   ```bash
   python tools/direct_db_query.py --sql "SELECT COUNT(*) FROM oi_symbol_summary WHERE trade_date = DATE('now')"
   ```

**Common Causes:**
- OID morning scan didn't run (no today's data)
- Morning Views ran BEFORE query database sync (views destroyed)
- Filters too restrictive (price < $60, OI > 500)

**Fix:**
```bash
# Re-run morning views manually
cd morning_view
python morning_views.py

# Or re-run full morning pipeline
python main.py --oid-morning
```

---

### Problem: Stale Data (Yesterday's OI Showing)

**Symptoms:**
- Watchlist shows OI from yesterday, not today
- Missing fresh OI builds that you see in oi_daily

**Diagnosis:**
```sql
-- Check what date watchlist is using
SELECT symbol, total_open_interest, trade_date
FROM v_morning_watchlist
LIMIT 1;

-- Compare to oi_daily today
SELECT symbol, SUM(open_interest) as total_oi, trade_date
FROM oi_daily
WHERE trade_date = DATE('now')
GROUP BY symbol
LIMIT 1;
```

**Cause:** Views using wrong date filter (should be TODAY for OI)

**Fix:** Already fixed in v2.0 (hybrid data strategy). If still seeing issue:
1. Check morning_views.py uses self-join with `WHERE s_today.trade_date = DATE('now')`
2. Re-run morning_views.py

---

### Problem: Volume Shows as 0

**Symptoms:**
```sql
SELECT symbol, volume FROM v_morning_watchlist;
-- All volumes = 0
```

**Cause:** Known issue - `option_volume` field in `oi_symbol_summary` is not being aggregated from `oi_daily` during rollup.

**Impact:**
- Volume surge factor shows N/A
- Confluence score max is 4 instead of 5
- Primary signal never shows "VOLUME_SURGE"

**Workaround:** Use other signals (flow alerts, OI concentration, earnings, sentiment)

**Permanent Fix:** (Not yet implemented)
```python
# In oid_symbol_rollup.py, add:
option_volume = SUM(volume) FROM oi_daily WHERE symbol = X AND trade_date = Y
```

---

### Problem: OI Timing Shows NULL

**Symptoms:**
```sql
SELECT * FROM v_oi_timing_context WHERE symbol='XYZ';
-- Returns: 0 rows (or oi_build_start_date = NULL)
```

**Cause:** OI timing calculator hasn't run for this symbol/contract yet.

**Requirements:**
- Contract must have OI > 1000 (filter threshold)
- Timing calculator (`oid_timing_calculator.py`) must have processed it
- Historical OI data must exist in `oi_daily`

**Fix:**
```bash
# Run timing calculator for specific symbol
cd strategies/oi_delta
python oid_timing_calculator.py --symbol XYZ

# Or wait for next automated run (part of evening OID pipeline)
```

---

### Problem: "Database is Locked" Error

**Symptoms:**
```
Error: database is locked
```

**Cause:** Trying to query `datalake.db` while OID scan is writing to it.

**Fix:** Always use `datalake_query.db` for queries:
```bash
# Wrong (will lock during scans)
python tools/direct_db_query.py --db data/datalake.db --sql "SELECT ..."

# Right (read-only query database)
python tools/direct_db_query.py --sql "SELECT ..."  # Defaults to datalake_query.db
```

**When Does It Lock:**
- 6:30-8:00 AM (morning OID scan)
- 4:30-6:00 PM (evening OID scan)

**Database Sync Schedule:**
- ~7:20 AM (after morning OID)
- ~5:45 PM (after evening OID)
- ~7:00 PM (final evening sync)

---

### Problem: Top Strike Display Truncated

**Symptoms:**
```sql
SELECT top_call_display FROM v_symbol_oi_detail WHERE symbol='KDP';
-- Shows: "$28.0 (10/17) OI 9,619 | $29.0" (cut off)
```

**Cause:** Display string may be cut off in query output (investigating)

**Workaround:** Query individual fields instead:
```sql
SELECT top_call_strike, top_call_expiration, top_call_oi
FROM v_symbol_oi_detail
WHERE symbol='KDP';
```

**Status:** Low priority - data exists, just not fully visible in formatted string

---

## Advanced Usage

### Custom Watchlist Filters

**Create your own filters on top of v_morning_watchlist:**

**Example 1: High-Conviction Bullish Plays**
```sql
SELECT symbol, close_price, confluence_score, conviction_level
FROM v_morning_watchlist
WHERE direction_bias IN ('BULLISH', 'SOMEWHAT_BULLISH')
  AND conviction_level = 'HIGH'
  AND confluence_score >= 3
ORDER BY confluence_score DESC;
```

**Example 2: Flow Alert + Earnings Combo**
```sql
SELECT symbol, earnings_days_ahead, active_alerts_count,
       exp_move_pct, earnings_play_signal
FROM v_morning_watchlist
WHERE primary_signal = 'FLOW_ALERT'
  AND earnings_days_ahead BETWEEN 1 AND 14
ORDER BY earnings_days_ahead;
```

**Example 3: Contrarian Setup (Bearish Sentiment + Bullish OI)**
```sql
SELECT symbol, news_sentiment, direction_bias,
       close_price, put_call_ratio
FROM v_morning_watchlist
WHERE news_sentiment IN ('Bearish', 'Somewhat-Bearish')
  AND direction_bias IN ('BULLISH', 'SOMEWHAT_BULLISH')
ORDER BY confluence_score DESC;
```

---

### Combining Multiple Views

**Example: Full Analysis for One Symbol**
```sql
-- Get watchlist context
SELECT symbol, confluence_score, direction_bias,
       primary_signal, active_alerts_count
FROM v_morning_watchlist
WHERE symbol = 'KDP';

-- Get OI distribution
SELECT total_open_interest, put_call_ratio,
       oi_0_7_days_percent, oi_8_21_days_percent,
       net_delta_exposure, max_gamma_strike
FROM v_symbol_oi_detail
WHERE symbol = 'KDP';

-- Get smart money positioning
SELECT strike, option_type, open_interest,
       positioning_type, oi_build_start_date,
       oi_build_price_move_pct
FROM v_oi_timing_context
WHERE symbol = 'KDP'
ORDER BY open_interest DESC
LIMIT 5;

-- Compare top 3 call strikes
SELECT strike, last_price, delta, breakeven_move_pct,
       delta_per_dollar, theta_decay_dollars
FROM v_option_comparison
WHERE symbol = 'KDP'
  AND option_type = 'CALL'
  AND dte BETWEEN 14 AND 30
ORDER BY open_interest DESC
LIMIT 3;
```

---

### Time-Based Analysis

**Track Symbol Over Multiple Days:**
```sql
-- Watch how OI changes day-to-day (use datalake.db for historical)
SELECT trade_date, symbol, total_open_interest, put_call_ratio
FROM oi_symbol_summary
WHERE symbol = 'MGM'
  AND trade_date >= DATE('now', '-7 days')
ORDER BY trade_date;

-- Track specific contract OI growth
SELECT trade_date, open_interest, volume, last_price
FROM oi_daily
WHERE symbol = 'MGM'
  AND strike = 36.0
  AND option_type = 'CALL'
  AND expiration_date = '2025-10-24'
  AND trade_date >= DATE('now', '-7 days')
ORDER BY trade_date;
```

---

## Data Timing Reference

### What Updates When

| Time | Process | Updates | Why |
|------|---------|---------|-----|
| 6:35 AM | OID Morning Scan | `oi_daily.open_interest` for today | Market opens, OI from previous close available |
| 7:20 AM | Query DB Sync | Copies `datalake.db` → `datalake_query.db` | Make fresh OI available for queries |
| 7:30 AM | Morning Views | Creates 4 SQL views in `datalake_query.db` | Generate watchlist from fresh OI |
| 5:00 PM | OID Evening Scan | `oi_daily.volume`, `oi_daily.greeks`, pricing | Market closed, complete data available |

### What Data is "Fresh" When You Query

**Morning (7:30 AM - 4:59 PM):**
- **OI:** Today's data (fresh)
- **Volume:** Yesterday's data (today's volume = 0 until evening scan)
- **Greeks:** Yesterday's data (today's greeks = NULL until evening scan)
- **Price:** Yesterday's close (today's close not available until 4:00 PM+)

**Evening (5:00 PM+):**
- **Everything:** Today's complete data

**This is why Morning Views uses hybrid strategy** - best of both worlds.

---

## Known Issues & Limitations

### Current Gaps (as of 2025-10-07)

**1. Option Volume = 0** ❌
- **Status:** Not being aggregated from oi_daily to oi_symbol_summary
- **Impact:** Volume surge detection doesn't work, confluence max = 4
- **Workaround:** Use other signals
- **Fix:** Update oid_symbol_rollup.py to aggregate SUM(volume)

**2. Top Strike Display Truncated** ⚠️
- **Status:** Strings may be cut off in query output
- **Impact:** LOW - data exists, just not fully visible
- **Workaround:** Query individual fields (top_call_strike, top_call_oi, etc.)

**3. Bid-Ask Spread = NULL** ⚠️
- **Status:** avg_bid_ask_spread_pct not populated
- **Impact:** LOW - can't assess liquidity via spread
- **Workaround:** Use open_interest as liquidity proxy

### Design Limitations

**1. 50% OI Build Threshold**
- OI timing uses 50% of current OI as "build start"
- Misses early accumulation (0-50% phase)
- Good enough for smart money vs retail distinction

**2. DTE Filters**
- v_option_comparison only shows 7-60 DTE
- Excludes weekly options (0-6 DTE) and LEAPS (60+ DTE)
- Keeps view focused on "sweet spot" timeframe

**3. Price Filter**
- v_morning_watchlist filters to price < $60
- Excludes high-price names (NVDA, AAPL, etc.)
- Budget constraint for retail traders

**4. KLMN Universe**
- Only scans 800 symbols (KLMN list)
- Misses small-cap and micro-cap opportunities
- Focused on liquid, well-known names

---

## Feedback & Improvement

### Real User Feedback (Ben, 2025-10-06)

**Trade:** 2x MGM $36 CALL @ $0.50

**Feedback:**
> "The OI timing feature alone justified the entire system. Being able to see that the $36 calls were positioned 3 days ago at $34 gave me confidence this was a conviction play, not retail chasing a peak. Completed my decision in ~15 minutes. 5/5 value despite the volume gap."

**Key Insight:** OI timing is the "killer feature" - everything else is supporting data.

### Feature Requests / Future Enhancements

**Possible Improvements:**
1. Real-time volume tracking during market hours
2. Volume surge alerts in morning email
3. IV rank/percentile in v_option_comparison
4. Historical win rate for similar setups
5. Position sizing recommendations based on confluence score
6. Alerts when OI timing shows reversal patterns

### Documentation Requests

If anything is unclear, incomplete, or needs more examples, please provide feedback.

---

## Quick Reference Card

### Daily Checklist
- [ ] Check morning email (7:30 AM)
- [ ] Review watchlist: `SELECT * FROM v_morning_watchlist LIMIT 5`
- [ ] Pick 1-2 symbols to deep dive
- [ ] Check OI timing: `SELECT * FROM v_oi_timing_context WHERE symbol='XXX'`
- [ ] Compare strikes: `SELECT * FROM v_option_comparison WHERE symbol='XXX'`
- [ ] Make trade decision (or pass)

### Key Metrics
- **Confluence ≥ 3:** High confidence
- **Conviction = HIGH:** Strong directional view
- **Positioning = PREDICTIVE:** Smart money
- **Build Days ≤ 7:** Fresh setup
- **Delta per Dollar > 0.5:** Good leverage
- **Breakeven Move < 10%:** Achievable

### Signal Priority
1. **OI Timing** (PREDICTIVE + fresh = highest edge)
2. **Confluence Score** (multiple signals aligned)
3. **Flow Alerts** (recent unusual activity)
4. **Earnings Catalyst** (if IV not overpriced)
5. **Direction Bias** (what market is positioned for)

### Critical Reminders
- Morning data = TODAY's OI + YESTERDAY's volume/greeks
- Use `datalake_query.db` for queries (not datalake.db)
- Views are recreated daily (no persistence)
- Volume currently broken (all zeros) - use OI instead

---

**Last Updated:** 2025-10-07
**Version:** 2.0 (Hybrid Data Strategy)
**Questions?** Review schema files in `morning_view/Schema_*.txt`
