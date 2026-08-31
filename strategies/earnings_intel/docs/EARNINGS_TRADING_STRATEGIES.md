# Earnings Trading Strategies

Three approaches to trading around earnings events. All are subject to refinement as we accumulate data and experience.

---

## 1. IV Harvest

**Goal:** Capture the natural IV ramp leading into earnings. Sell before the event.

**Structure:**
- **Direction:** Directional bet (call or put based on conviction)
- **Timing:** Buy 2-3 trading days before earnings
- **Strike:** ATM
- **Expiration:** One or two expirations after earnings
- **Entry:** Buy over the course of a few days to secure lower prices that may take advantage of reversion to the mean
- **Exit:** Aim for 20% profit, bail before earnings. Don't be afraid to take profits early.
- **Profit driver:** Natural IV increase as earnings approaches. Bonus profitability from actual directional movement; negative movement lessened by rising IV.

**Open Questions:**
- How can we use Earnings Intelligence to make smarter IV Harvest plays?
- How does expected move play into this?
- Is it better to have more or less volatility moving into earnings?

---

## 2. Earnings Straddle

**Goal:** Bet on move magnitude, not direction. Requires a large earnings move to profit.

**Structure:**
- **Direction:** Non-directional (calls AND puts)
- **Timing:** Buy ~5-7 trading days before earnings
- **Strike:** ATM
- **Expiration:** 25-35 DTE
- **Entry:** Buy over the course of a few days to capture lower prices
- **Exit rules:**
  - If price movement before earnings captures profit, take it and wait for better re-entry
  - If holding through earnings, watch carefully on earnings day and try to capture the peak — 100%+ profit is the goal
  - Do NOT sell both legs at the same time
  - Sell the winning leg when you think you've hit the peak
  - Sell the losing leg within 5 trading days at best price point (reversion to mean)
- **Cash tie-up:** 5-8 days for winning leg, 5-12 days for losing leg

---

## 3. Sector Sympathy

**Goal:** Play a correlated stock instead of the one reporting earnings. Lower IV = better value.

**Structure:**
- Played very similarly to Earnings Straddle
- Find a stock that tends to move alongside the stock experiencing earnings
- Play the sympathetic stock as if it were the one approaching earnings
- IV will be lower on the non-reporting stock, leading to better value and profitability

**The trick:** Finding the sympathetic symbols. Known examples:
- Airlines: DAL, AAL, UAL move together around earnings

---

## Relationship to Existing Docs

- **EARNINGS_STRADDLE_PLAYBOOK.md** — Detailed execution guide for Strategy 2, including the TOST case study
- **Earnings Scenario Calculator** (`tools/earnings_scenario.py`) — Models post-earnings P/L with IV crush for any of these strategies
