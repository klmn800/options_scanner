# Institutional Options Flow — Taxonomy & Diagnostic Signatures

Reference for interpreting large-block options flow alerts. Two parts:

1. **Taxonomy of motivations** — why an institution might buy 10,000 contracts at $2M
2. **Diagnostic signatures** — what observable footprints distinguish each play type, organized by detectability

Use this to label alerts. When the footprint isn't clear, classify as **Unknown** rather than forcing a label.

---

## PART 1 — Why Institutions Buy Options

### 1. Directional speculation (the obvious read)
- **Catalyst bet** — earnings, FDA, M&A rumor, product launch, court ruling, conference
- **Macro/thematic bet** — sector rotation, rate decision, geopolitical event
- **Momentum chase** — joining an existing trend, breakout positioning
- **Whisper / informed conviction** — rare but real; usually OTM short-dated calls

### 2. Hedging (often misread as directional)
- **Portfolio hedge** — fund holds the stock long, buys puts for protection
- **Short hedge** — fund is short stock, buys calls to cap upside risk *(looks bullish but is bearish positioning elsewhere)*
- **Tail-risk hedge** — deep OTM puts, low cost, catastrophic protection
- **Pension/insurance liability hedge** — mechanical, not view-based
- **Convertible bond hedge** — buying puts against long convert position
- **Structured product hedge** — bank desks hedging autocallables, variance swaps, sold notes

### 3. Yield / income (selling, not buying — but appears as flow)
- **Covered call overwriting** — selling calls against long stock
- **Cash-secured put writing** — selling puts to acquire stock at lower price
- **Buy-write programs** — systematic, monthly, mechanical

### 4. Spread legs (the alert is only one leg)
- **Vertical** (bull/bear call or put spread)
- **Calendar/diagonal** — long one expiry, short another
- **Risk reversal** — long call + short put (synthetic long), or inverse
- **Collar** — long put + short call vs long stock (cost-free protection)
- **Straddle/strangle** — pure vol bet, no direction
- **Butterfly/condor** — pinning bet
- **Ratio spread** — asymmetric structure
- **Box spread** — synthetic financing, not directional

### 5. Volatility-only plays
- **Long gamma into a catalyst** — wants the move, doesn't care which direction
- **Short vol after IV spike** — selling expensive premium
- **Dispersion** — long single-name vol, short index vol (or inverse)
- **Skew trade** — puts vs calls relative pricing
- **Term structure** — front month vs back month

### 6. Position management (not new views)
- **Roll out** — close near-dated, open further-dated
- **Roll up/down** — adjust strike on existing position
- **Closing** — exiting a prior trade *(huge flow can be just unwinding)*
- **Assignment defense** — preventing early exercise

### 7. Synthetic / capital efficiency
- **Stock replacement via deep ITM calls** — leverage, capital efficiency
- **Synthetic long** (call + short put) — avoid disclosure thresholds (13D/13G), avoid borrow
- **Synthetic short** — when borrow is hard or expensive
- **LEAPS as long-term equity proxy** — tax/margin reasons

### 8. Arbitrage / relative value
- **Merger arb** — hedging deal-break risk on announced M&A
- **Capital structure arb** — equity vol vs credit spreads
- **Dividend arb** — early-exercise plays on deep ITM calls before ex-div
- **Cross-listing arb** — same-name vol on different exchanges

### 9. Dealer / market-maker mechanical flow
- **Counter-flow hedging** — MM took the other side of client flow, now hedging delta/gamma
- **Not a view at all** — pure inventory management

### 10. Systematic / quant
- **Vol-targeting funds** rebalancing
- **Risk parity** adjustments
- **CTA / trend-following** signals firing
- **Index rebalance front-running**
- **Gamma-squeeze pre-positioning** — buying calls to force dealer hedging cascades

### 11. Tax / regulatory
- **Loss harvesting** via puts (wash-sale workarounds)
- **Year-end positioning**
- **Constructive sale** avoidance
- **Disclosure threshold** management (stay below 5% beneficial ownership)

---

## PART 2 — Diagnostic Signatures by Detectability

For each play type: **footprint** (what suggests it) and **rule-outs** (what contradicts it).

### Tier A — Detectable from flow + OI + stock action

#### Opening Directional Bet
- **Footprint:** Volume >> open interest at that strike; ATM or moderately OTM; near-dated to mid-dated (typically <90 DTE); single concentrated print or tight cluster of prints; OI rises next day.
- **Rule out:** mirror trade on opposite side (→ straddle), similar-sized print on adjacent strike same expiry (→ spread leg), similar-sized print at same strike different expiry (→ roll/calendar), volume ≤ existing OI (→ closing, not opening), heavy recent alert history on same name (→ momentum follow-on, not initiation).

#### Roll
- **Footprint:** Two near-simultaneous prints on the same symbol — one closes (volume ≤ OI on shorter-dated/different strike), one opens (volume > OI on longer-dated/different strike); often net cash near-neutral; OI on the closing leg drops next day, OI on the opening leg rises.
- **Rule out:** opening leg in opposite direction (→ different play), closing leg has no OI to support it (→ not actually a roll), prints separated by hours (→ probably independent trades).

#### Closing Position
- **Footprint:** Volume ≤ existing OI on that exact contract; no opening trade elsewhere on the symbol; OI drops next day; often follows a meaningful price move in the underlying (taking profit or cutting loss).
- **Rule out:** OI rises next day (→ was actually opening), simultaneous opening print elsewhere (→ roll).

#### Vertical Spread (bull call / bear put / etc.)
- **Footprint:** Two simultaneous prints, **same expiration**, **different strikes**, **same option type** (both calls or both puts), one bought one sold, similar size.
- **Rule out:** different expirations (→ calendar), opposite types (→ risk reversal or straddle), only one leg visible (→ might be one leg of a spread but treat as ambiguous).

#### Calendar / Diagonal Spread
- **Footprint:** Two simultaneous prints, **same strike (or close)**, **different expirations**, same option type, one bought one sold; usually long the back month, short the front.
- **Rule out:** same expiration (→ vertical), no offsetting leg (→ probably outright).

#### Straddle / Strangle (pure vol)
- **Footprint:** Simultaneous **call + put** prints, same expiration, similar size; straddle = same strike (ATM), strangle = equidistant OTM strikes; usually with an event in the window (earnings, FDA, court date).
- **Rule out:** asymmetric size between legs (→ directional with hedge), no nearby catalyst AND low IV environment (→ unusual, recheck).

#### Risk Reversal / Synthetic Long
- **Footprint:** Buy call + sell put simultaneously, similar size, often different strikes (skew play); near-zero net debit; sometimes near-zero net credit.
- **Rule out:** both legs bought (→ strangle), legs not simultaneous (→ unrelated).

#### Stock Replacement (deep ITM call / LEAPS)
- **Footprint:** Deep ITM call (delta >0.85), long-dated (often >180 DTE), low extrinsic value, usually at round-number strikes well below spot; volume can be modest but notional is large.
- **Rule out:** OTM strikes (→ directional), short-dated (→ different intent).

#### Gamma Squeeze / Coordinated Buying
- **Footprint:** Repeated, layered buying across multiple short-dated OTM calls over hours or days; high short interest in underlying; often ladder pattern (multiple strikes, same expiry); volume builds rather than arriving in one block.
- **Rule out:** single block with no follow-through (→ one-off directional), no short interest context (→ probably just bullish bet).

#### Catalyst / Earnings Vol Play
- **Footprint:** Buying within 1-7 days of known event; IV already elevated but they paid anyway; OTM strikes both sides or ATM straddle.
- **Rule out:** no event in window (→ pure directional or hedge).

---

### Tier B — Partially detectable (need correlated data)

#### Long-stock Hedge (bought puts)
- **Footprint:** Large put volume on a stock with strong **recent uptrend** (3-12 months); puts are slightly OTM, mid-to-long dated (30-180 DTE); IV ramp without a panic move in the underlying; often round-number strikes.
- **Tells it apart from bearish bet:** stock is calm or rising (panic-down moves wouldn't pay these IV levels), put strikes are protective (5-15% OTM) not lottery-ticket (30%+ OTM), longer-dated than typical directional play.
- **Need:** insider/13F data to *confirm* the hedger holds the stock.

#### Collar (long stock + protective put + short call)
- **Footprint:** Three-legged on the same name same day — put bought, call sold, both same expiry, often equidistant from spot; net cost near zero or small credit.
- **Rule out:** only two legs visible (→ probably risk reversal or vertical).
- **Need:** stock holding context to confirm.

#### Merger Arb Hedge
- **Footprint:** Only relevant on **announced M&A targets**. Put buying clustered around or just below deal price (deal-break protection); call selling above deal price (capping upside since shares cap at deal price).
- **Need:** active deal calendar.

---

### Tier C — Basically invisible from flow (classify as Unknown)

#### Short-stock Hedge (bought calls)
Looks **identical** to a directional bullish bet at the contract level. The only tell is *contextual* — stock has been weak, high short interest, no positive catalyst — but you can't distinguish it from a contrarian bullish thesis. **This is the #1 false-positive source for "bullish flow."**

#### Dealer / Market-Maker Mechanical Hedge
Often appears as fragmented volume following a larger trade by 5-30 minutes, ATM-biased, no news. Hard to separate from real flow without time-and-sales sequencing and exchange/MM identification.

#### Vol Surface / Skew Arb
Specific structures (long ATM call + short OTM call as a skew bet) look like ordinary verticals. Without the trader's full book or surface data, you can't know it's relative-value rather than directional.

#### Convertible Bond Hedge / Structured Product Hedge / Pension Tail Hedge
Need bank-book or fund-holdings data. From flow alone these look like ordinary directional or protective trades. Tail hedges have one tell: extremely far OTM (>30%), very long-dated (>180 DTE), very low premium per contract but huge contract count.

#### Covered Call Writing / Cash-Secured Put Writing
You typically see these as the **dealer's BUY** in your alerts, not the institution's sell. Persistent monthly cadence at slightly OTM strikes on big-cap names is the signature, but it's a population-level pattern, not a single-alert signal.

#### Box Spreads
Four legs, all expiring same day, net result is synthetic financing. If you see a four-legged structure with no directional view it's probably this — but most retail flow data won't reconstruct all four legs.

---

## PART 3 — Cross-cutting Structural Features

A few features disambiguate many categories above. Use these as the primary classification axes:

1. **Volume vs. OI ratio** — the single most important "opening vs. closing" indicator.
2. **Mirror-search** — for any large print, scan ±2 strikes, ±1 expiration, opposite side, within a 5-minute window. Most multi-leg plays leave a partner print.
3. **Next-day OI delta** — confirms opening vs. closing after the fact; useful for retroactive labeling and training data.
4. **DTE bucketing** — short (<14d) is gamma/event/squeeze territory; mid (15-90d) is directional/spreads; long (>90d) is hedging/replacement/LEAPS.
5. **Strike distance from spot** — ATM is delta-1/vol; near-OTM is directional; far-OTM (>20%) is lottery or tail-hedge; deep ITM is replacement.
6. **Symbol context** — recent alert density, short interest, earnings window, M&A status, stock trend regime.
7. **Time of day** — open and last-hour have different signatures (open = conviction/news, last-hour = systematic/rebalance).

---

## Honest Limits

- Many alerts will land in **Ambiguous / Unknown** even with all this. That's honest classification, not failure.
- Single-leg flow data cannot, by itself, distinguish a directional bullish bet from a short-stock hedge. External data (short interest, 13F, insider holdings) is required.
- Multi-leg plays (spreads, rolls, collars) are only detectable if the partner legs are visible in the same data feed within a tight time window.
- Population-level patterns (monthly covered-call programs, systematic rebalancing) are visible only by aggregation across days, not from individual alerts.

The goal is high-confidence labels on the subset where the footprint is clear, not forced labels on every alert.
