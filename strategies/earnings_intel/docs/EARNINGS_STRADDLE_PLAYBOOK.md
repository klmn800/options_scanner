# Earnings Straddle Playbook

**The core idea:** When our system says the market is underpricing a stock's earnings move, don't bet on direction. Bet on magnitude. Buy both sides.

---

## The Play in 30 Seconds

1. EI system flags a stock with **WATCH or higher** relative underpricing (15%+)
2. The stock has adequate liquidity (OI >= 4,000)
3. **Buy an ATM straddle** (1 call + 1 put, same strike, first expiry after earnings)
4. You profit if the stock moves MORE than the market expected, in EITHER direction
5. Sell both legs the morning after earnings

You are not predicting direction. You are betting that the market underestimates how much this stock moves on earnings, which is exactly what the relative underpricing signal measures.

---

## Why This Works (The Logic)

Options are priced based on the market's expected move. When you buy a straddle, you're paying for that expected move. You profit when the actual move is bigger.

Our system compares:
- **What the market prices** (straddle expected move)
- **What actually happens historically** (historical average move)

When there's a gap — the stock historically moves MORE than the market expects — that's the edge. The straddle captures it regardless of whether the stock goes up or down.

**Relative underpricing** measures this gap as a percentage:
```
Relative Underpricing = (Historical Avg - Straddle Expected) / Straddle Expected * 100
```

At 30% relative underpricing, the market is pricing a move that's 30% too small compared to what the stock actually does. That's your edge.

---

## Case Study: AAL Sympathy Play, April 8, 2026

This trade is also the first real-world validation of **Strategy 3: Sector Sympathy**. DAL was the one reporting earnings, but its options were overpriced (EI flagged AVOID). AAL tends to move with DAL on airline earnings, had lower IV (no direct catalyst of its own), and offered better value. The play was to buy a straddle on AAL instead of DAL.

### Setup

- **DAL earnings:** Wed April 8, BMO
- **DAL signal:** AVOID (overpriced)
- **Thesis:** AAL will move sympathetically with DAL, and AAL options are cheaper because AAL isn't the one reporting
- **Structure:** Two straddles at the $11 strike — one short-dated (4/10, week of earnings) and one longer-dated (5/1, ~3 weeks out)

### Entries

**April 6 (T-2), UL ~$10.85:**
- Bought 2x AAL 11P 4/10 @ $0.43 = $86
- Bought 1x AAL 11C 4/10 @ $0.29 = $29

**April 7 (T-1), UL ~$10.60:**
- 3 more 4/10 calls filled on a stale limit order during a morning gap (accidental) @ $0.29 = $87
- Sold 2 of those 4/10 calls back @ $0.21 = $42 (unwinding the accident)
- Bought 2x AAL 11C 5/1 @ $0.61 = $122
- Bought 2x AAL 11P 5/1 @ $0.86 = $172

**Final position going into earnings:**

| Leg | Contracts | Avg Cost | Total |
|-----|-----------|----------|-------|
| AAL 11C 4/10 | 2 | $0.29 | $58 |
| AAL 11P 4/10 | 2 | $0.43 | $86 |
| AAL 11C 5/1 | 2 | $0.61 | $122 |
| AAL 11P 5/1 | 2 | $0.86 | $172 |
| **Total capital** | | | **$438** |

### Earnings Day (April 8)

DAL beat. DAL and AAL both gapped up ~13% pre-market. AAL opened at **$12.09** — a 14% move from the prior day.

**9:31** — Sold 2x 5/1 puts @ $0.32 = $64 (killing the losers before IV crush ate them further)
**9:32** — Sold 2x 4/10 calls @ $1.00 = $200 (+245%)
**9:35** — Sold 2x 5/1 calls @ avg $1.325 = $265 (+117%)
**Held** — 2x 4/10 puts @ ~$0.04 (near-worthless, auto-sell at $0.10 set)

### Results

| Leg | Cost | Sold | P/L | Return |
|-----|------|------|-----|--------|
| 2x 11C 4/10 | $58 | $200 | **+$142** | +245% |
| 2x 11C 5/1 | $122 | $265 | **+$143** | +117% |
| 2x 11P 5/1 | $172 | $64 | **-$108** | -63% |
| 2x 11P 4/10 | $86 | ~$8 | **-$78** | -91% |
| **Total** | **$438** | **$537** | **+$99** | **+23%** |

**Net: +$99 in 2 days (+23% on capital deployed).**

### Why This Worked

1. **The sympathy thesis paid off.** AAL moved 13% on DAL's earnings — correlated move validated. By playing AAL instead of DAL, the entry was cheaper.
2. **Both expirations contributed.** The 4/10 calls made +$142, the 5/1 calls made +$143. Near-identical dollar profit. But the 5/1 calls did it with far less theta risk — they were the insurance policy if the move had been smaller.
3. **Straddle removed directional risk.** No need to predict DAL's beat/miss direction. The trade just needed AAL to move more than breakeven.
4. **Execution discipline.** Sold the winning calls at 9:32-9:35, near the open peak. Dumped the 5/1 puts immediately to salvage value before IV crush. Held the 4/10 puts for lottery-ticket reversion.
5. **The "wife test" worked.** When bragging about the profit feels good, it's already good enough — take it.

### Lessons

- **Sympathy plays work when the reporting stock is overpriced.** DAL was AVOID. AAL was the back door into the same catalyst at a better price.
- **Always buy the longer-dated straddle alongside the short-dated one.** The 4/10 straddle was riskier (theta bleed if the move was delayed). The 5/1 straddle gave flexibility and comparable profit with less gamma risk.
- **Put legs are the insurance premium.** $186 in combined put losses bought directional-risk-free exposure to a 13% move. That's a fair price.
- **Stale limit orders on morning gaps are a real risk — and maybe an opportunity.** The accidental fill cost nothing this time, but could have. Worth studying as a deliberate entry tactic ("gap trap" limit orders).

---

## When to Use This Play

### Green Light (all must be true)

- [ ] EI signal is **WATCH, BUY, or STRONG BUY** (relative underpricing >= 15%)
- [ ] Total open interest >= 4,000 (options are liquid enough to trade)
- [ ] Earnings date is within 5 trading days
- [ ] ATM straddle cost fits position sizing ($300 or adjust to 1 contract)
- [ ] There's an expiration within 7-14 days after earnings (enough time value, not too much premium)

### Red Light (skip if any are true)

- Signal is NEUTRAL or AVOID — the market isn't meaningfully underpricing
- OI is thin (wide bid-ask spreads will eat your edge)
- The straddle costs more than your position size allows
- Earnings is more than 5 days away (theta decay eats the position while waiting)
- Stock is already making a huge pre-earnings move (the "underpricing" may already be correcting)

### Yellow Light (proceed with caution)

- Signal is WATCH but just barely above 15% — edge is thin
- Market is broadly volatile (VIX elevated) — IV across the board is high, harder to find underpriced moves
- The stock has had a regime change (acquisition, new CEO, sector rotation) that makes historical averages less reliable

---

## How to Execute

### Step 1: Identify Candidates (Automated)

The EI system runs daily at 5 PM and updates `earnings_upcoming` with signals. Check for upcoming earnings with WATCH+ signals:

```bash
python tools/direct_db_query.py --sql "
    SELECT symbol, earnings_date, earnings_days_ahead,
        ROUND(relative_underpricing_pct, 1) as rel_underpricing,
        ROUND(straddle_expected_move_pct, 1) as expected_move,
        ROUND(historical_avg_move_pct, 1) as hist_avg,
        earnings_play_signal
    FROM earnings_upcoming
    WHERE earnings_play_signal IN ('WATCH', 'BUY', 'STRONG BUY')
        AND earnings_days_ahead BETWEEN 1 AND 5
    ORDER BY relative_underpricing_pct DESC
"
```

Or just check the earnings alerts — they fire at WATCH+ level.

### Step 2: Check the Straddle Price

For each candidate, look at the ATM options:

```bash
python tools/direct_db_query.py --sql "
    SELECT strike, option_type, last_price, bid, ask, iv, delta, open_interest
    FROM option_contracts
    WHERE symbol = 'XXXX'
        AND expiration_date = 'YYYY-MM-DD'  -- first expiry after earnings
        AND ABS(delta) BETWEEN 0.40 AND 0.60  -- ATM range
        AND trade_date = (SELECT MAX(trade_date) FROM option_contracts WHERE symbol = 'XXXX')
    ORDER BY strike, option_type
"
```

Find the strike closest to the stock price. Add the call ask + put ask = straddle cost.

### Step 3: Sanity Check

Before buying, verify:

| Check | How |
|-------|-----|
| Straddle cost fits position size | Total cost < $300 (or your limit) |
| Breakeven makes sense | Straddle cost / stock price = % move needed to profit. Should be LESS than historical avg move. |
| Bid-ask spreads are reasonable | Spread < 10% of option price on both legs |
| Open interest is adequate | Both legs have OI > 100 |

**The critical check:** Your breakeven % should be less than the historical average move. If the straddle costs 12% of the stock price but the stock historically moves 13%, your edge is razor thin. If it costs 10% and the stock moves 13%, you have room.

### Step 4: Buy on Robinhood

- Buy 1 ATM Call (ask price)
- Buy 1 ATM Put (ask price)
- Same strike, same expiration
- Enter as two separate orders (RH supports straddle orders too but separate gives you more control on fills)

### Step 5: Sell the Morning After Earnings

**Do not wait.** The edge is in the earnings move, not in holding afterward.

- **Both in profit:** Sell both. Take the win.
- **One winning, one losing:** Sell both. The winner should more than cover the loser if the move exceeded the expected move. Don't hold the loser hoping for a reversal.
- **Both losing (stock barely moved):** Sell both. IV crush is eating you alive — every hour you hold makes it worse.

**Timing:** Wait 15-30 minutes after market open for the initial volatility to settle. Don't sell in the first 5 minutes unless the move is enormous and you want to lock it in.

### Step 6: Record the Result

Add a trading journal note for post-trade learning:

```sql
UPDATE earnings_events
SET notes = 'Straddle play: 29 strike, cost $3.60, sold at $X.XX. +/-XX%',
    tags = 'straddle,earnings_arb',
    sentiment = 'positive'  -- or 'negative'
WHERE symbol = 'TOST' AND earnings_date = '2026-02-12';
```

Over time this builds a record of which signals led to profitable straddle trades.

---

## Position Sizing

Based on a ~$4,000 portfolio and $300 max position size:

| Stock Price | Approx Straddle Cost | Contracts | Notes |
|-------------|---------------------|-----------|-------|
| $15-25 | $2.00-4.00 | 1 | Sweet spot for position sizing |
| $25-40 | $3.50-6.50 | 1 | Fits within $300 if IV isn't extreme |
| $40-60 | $5.00-10.00 | 1 | May exceed $300 — check before buying |
| $60+ | $8.00+ | Skip or reduce | Too expensive for current sizing |

Stocks under $40 are the best fit. Above that, the straddle gets expensive.

**Rule of thumb:** If the straddle costs more than $350, skip it or find a cheaper alternative (slightly OTM strangle instead — buy a call one strike above ATM and a put one strike below ATM, costs less but needs a bigger move).

---

## What This Is NOT

- **Not a guaranteed win.** If the stock moves LESS than the market expected, you lose on both legs plus IV crush. The historical average is an average — sometimes the stock moves less.
- **Not a substitute for flow alerts.** Flow alerts tell you someone is making a big directional bet. That's different information. If a flow alert AND an EI signal align, you might buy a straddle but lean the size toward the directional side.
- **Not a reason to ignore direction entirely.** If you have strong conviction on direction AND the EI signal says underpriced, a directional play with a bigger position can outperform a straddle. The straddle is for when you believe in the magnitude signal but don't have directional conviction.

---

## Workflow Summary

```
WEEKLY: Check earnings_upcoming for WATCH+ signals in the next 5 days
   |
   v
FOUND CANDIDATES? --> No --> Wait for next week
   |
   Yes
   v
CHECK STRADDLE PRICING --> Too expensive or illiquid? --> Skip
   |
   Affordable and liquid
   v
BUY ATM STRADDLE (1-2 days before earnings)
   |
   v
EARNINGS ANNOUNCED (after market or pre-market)
   |
   v
SELL BOTH LEGS (morning after, wait 15-30 min for dust to settle)
   |
   v
RECORD RESULT in earnings_events trading journal
   |
   v
REVIEW monthly: Are WATCH+ signals actually producing profitable straddles?
   Adjust thresholds if needed (config.json signal_thresholds)
```

---

## Future Enhancements

- **Automated candidate screening**: Morning scan could include straddle pricing and breakeven % alongside the arbitrage signals.
- **Historical straddle backtest**: With `move_vs_expected_pct` now backfilled across 9,900+ events, simulate straddle returns at each signal level to validate thresholds with real P/L.
- **Signal + Flow Alert integration**: When a flow alert fires on a symbol with an active WATCH+ EI signal, flag it as a "magnitude + direction" opportunity.

---

## Key Dates

- **2026-02-10**: Relative underpricing metric designed, signal thresholds recalibrated
- **2026-04-08**: AAL sympathy play validated both Strategy 2 (Earnings Straddle) and Strategy 3 (Sector Sympathy) — +$99 net (+23%) on a 13% AAL move triggered by DAL's earnings beat
- **2026-02-27**: Earnings Scenario Calculator complete (`tools/earnings_scenario.py`) — models straddle P/L across price scenarios with IV crush, breakevens, and `--straddle` mode
- **2026-04-02**: `earnings_snapshots` rewritten with OHLC + `straddle_expected_move_pct`. `earnings_moves` expanded with 15 new columns (OHLC peaks, BMO/AMC baseline, swing analysis, expected move from straddle snapshots). Denormalized outcomes on `earnings_events`.
