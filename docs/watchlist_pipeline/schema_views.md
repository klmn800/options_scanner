# SQL Views — Schema Reference

All views are defined in `morning_view/morning_views.py` and created in the query database.
They compute fresh data on every query — no storage, no update jobs.

**Critical timing note:** All views that join `option_symbol_summary` use a "hybrid timing"
pattern: today's OI data (from morning scan) + yesterday's volume/Greeks/prices (complete
end-of-day data). This works at 7:30 AM but is STALE by 6 PM after the evening OP run.
Item 6.6 addresses making these evening-aware.

---

## v_morning_discovery

**Role:** Level 1/2 hybrid. Surfaces symbols with active triggers (flow alerts OR earnings
plays) and provides initial context for investigation. Used by TUI Discovery screen.

**Source tables:** `option_symbol_summary` (self-join today+yesterday), `symbol_metadata`,
`earnings_upcoming`, `market_daily_summary`, `flow_symbol_summary`, `user_watchlist`,
`flow_options_scans` (for current_price), `news_symbol_sentiment`, `historical_prices`

**Filters:** close_price < $60, total_open_interest > 500, is_etf = 0, must have flow alert
OR earnings play trigger.

| Column | Type | Notes |
|--------|------|-------|
| symbol | TEXT | |
| close_price | REAL | Yesterday's close (from OP) |
| current_price | REAL | Latest price from flow_options_scans (intraday if FM running) |
| volume | INTEGER | Yesterday's option volume |
| put_call_ratio | REAL | Today's OI-based P/C ratio |
| total_open_interest | INTEGER | Today's total OI |
| total_call_oi | INTEGER | |
| total_put_oi | INTEGER | |
| price_change_5d_pct | REAL | 5-day stock price change. Subquery against historical_prices |
| direction_bias | TEXT | BULLISH / SOMEWHAT_BULLISH / NEUTRAL / SOMEWHAT_BEARISH / BEARISH. From P/C ratio thresholds: <0.5=BULL, 0.5-0.8=SOMEWHAT_BULL, 0.8-1.3=NEUTRAL, 1.3-2.0=SOMEWHAT_BEAR, >2.0=BEAR |
| conviction_level | TEXT | HIGH / MEDIUM / LOW. Based on OI concentration in top strike (>30%=HIGH, >15%=MED) |
| earnings_days_ahead | INTEGER | From earnings_upcoming. NULL if no upcoming earnings |
| exp_move_pct | REAL | Straddle-implied expected move |
| hist_move_pct | REAL | Historical average earnings move |
| diff_move_pct | REAL | Expected minus historical (negative = underpriced) |
| earnings_play_signal | TEXT | AVOID / NEUTRAL / WATCH / BUY / STRONG BUY |
| earnings_alert | BOOLEAN | Flag from earnings_upcoming |
| active_alert_count | INTEGER | From flow_symbol_summary (pre-computed) |
| new_alert_count | INTEGER | Alerts generated today |
| days_since_last_alert | INTEGER | 999 if no alerts ever |
| recent_alert_count_5d | INTEGER | Pre-computed 5-day rolling count |
| news_sentiment_avg | REAL | 5-day average news sentiment score (-1 to 1) |
| news_sentiment | TEXT | Bullish/Somewhat-Bullish/Neutral/Somewhat-Bearish/Bearish |
| volume_surge_factor | REAL | Yesterday's volume / 20-day average. 2.0 = 2x normal |
| confluence_score | INTEGER | 0-5 sum of: alerts + volume surge + earnings catalyst + news signal + OI conviction |
| primary_signal | TEXT | FLOW_ALERT / EARNINGS_CATALYST / VOLUME_SURGE / OI_SIGNAL |
| market_direction | TEXT | From market_daily_summary |
| market_regime | TEXT | trending / choppy / volatile |
| sector | TEXT | From symbol_metadata |
| industry | TEXT | |
| trade_date | TEXT | Yesterday's trade date |
| trigger_flow_alert | INTEGER | 1 if active alerts > 0 |
| trigger_earnings_play | INTEGER | 1 if earnings_alert = 1 |

**Ordering:** new alerts DESC, recent 5d alerts DESC, active alerts DESC, earnings diff DESC.

**Design issue (noted in brainstorm):** Tries to be both discovery feed AND investigation
context. Confluence score mixes signal types. Future rethink may split these roles.

---

## v_symbol_oi_detail

**Role:** Level 2 investigation. Complete OI breakdown for a single symbol. Used by TUI
OI Distribution screen.

**Source tables:** `option_symbol_summary` (self-join today+yesterday), `flow_options_scans`
(for current_price)

| Column | Type | Notes |
|--------|------|-------|
| symbol | TEXT | |
| trade_date | TEXT | Yesterday's date |
| close_price | REAL | Yesterday's close |
| current_price | REAL | Latest intraday price |
| total_open_interest | INTEGER | Today's OI |
| total_call_oi / total_put_oi | INTEGER | |
| put_call_ratio | REAL | |
| oi_balance_text | TEXT | Human-readable P/C interpretation |
| top_call_strike / expiration / oi / pct / display | MIXED | Highest-concentration call. `display` is pre-formatted string |
| top_put_strike / expiration / oi / pct / display | MIXED | Highest-concentration put |
| oi_0_7/8_21/22_35/36_60_days | REAL | OI bucketed by expiration timeframe (raw + percent) |
| call_oi_0_7/8_21/22_35/36_60_days | REAL | Same buckets, calls only |
| put_oi_0_7/8_21/22_35/36_60_days | REAL | Same buckets, puts only |
| option_volume / call_volume / put_volume | INTEGER | Yesterday's volume |
| volume_put_call_ratio | REAL | Volume-based P/C ratio |
| call_iv_avg / put_iv_avg | REAL | Average IV by type |
| iv_skew | REAL | Put IV - Call IV. Positive = put premium |
| symbol_iv_percentile_30d | REAL | Where current IV sits vs 30-day range |
| total/call/put/net_delta_exposure | REAL | Aggregate Greek exposures |
| total_gamma_exposure | REAL | |
| max_gamma_strike | REAL | Strike with highest gamma. Often near current price |
| total_theta_exposure | REAL | Daily time decay across all contracts |
| total/call/put/net_vega_exposure | REAL | IV sensitivity exposure |
| deep_itm/itm/atm/otm/deep_otm_call_oi + pct | MIXED | Moneyness distribution (calls) |
| deep_itm/itm/atm/otm/deep_otm_put_oi + pct | MIXED | Moneyness distribution (puts) |
| avg_bid_ask_spread_pct | REAL | Liquidity indicator. High = expensive to trade |
| max_pain_by_friday | REAL | Price where most options expire worthless |

**Design issue (noted in brainstorm):** This is a 50+ column data dump. It doesn't answer
a specific question — it shows everything. Could be refactored into question-driven views.

---

## v_oi_timing_context

**Role:** Level 2 investigation. Classifies when OI was built relative to price movement.
Used by TUI OI Timing screen.

**Source tables:** `option_contracts` (self-join today+yesterday)
**Filter:** Only symbols in `v_morning_discovery`, OI > 1000, has `oi_build_start_date`

| Column | Type | Notes |
|--------|------|-------|
| contract_hash | TEXT | SYMBOL\|STRIKE\|EXPIRATION\|TYPE |
| symbol | TEXT | |
| strike | REAL | |
| option_type | TEXT | CALL or PUT |
| expiration_date | TEXT | |
| trade_date | TEXT | |
| open_interest | INTEGER | Current OI (today) |
| dte | INTEGER | Days to expiration |
| oi_build_start_date | TEXT | When the current OI buildup started |
| oi_build_start_price | REAL | Stock price when OI buildup started |
| current_price | REAL | Current stock price (yesterday's data) |
| iv | REAL | Current implied volatility |
| iv_percentile | REAL | 20-day IV percentile |
| positioning_type | TEXT | PREDICTIVE / CHASING / NEUTRAL. **SEE WARNING BELOW** |
| oi_build_days_since | INTEGER | Days since OI buildup started |
| oi_build_price_move_pct | REAL | Stock price change since OI was built |

**WARNING — positioning_type is flawed:**
The PREDICTIVE vs CHASING classification compares the stock price at OI build start vs current
price. "Bought calls when stock was lower = PREDICTIVE" assumes the buyer was right about
direction. But buyers aren't psychic — a stock can dip after they buy. Being underwater
doesn't mean they were wrong; the anticipated move just hasn't happened yet. This
classification should be RETHOUGHT or REMOVED. What IS useful: knowing the build start price
and how the stock has moved since, without moralizing it.

---

## v_option_comparison

**Role:** Level 2 investigation. Side-by-side contract comparison with efficiency metrics.
Used by TUI Compare Strikes screen.

**Source tables:** `option_contracts` (self-join today+yesterday), `option_symbol_summary`
**Filter:** DTE 7-60, last_price > 0

| Column | Type | Notes |
|--------|------|-------|
| contract_hash | TEXT | |
| symbol / trade_date | TEXT | |
| strike / expiration_date | TEXT/REAL | |
| option_type | TEXT | CALL or PUT |
| dte | INTEGER | Days to expiration |
| moneyness | TEXT | ITM / ATM / OTM |
| last_price | REAL | Yesterday's last traded price |
| underlying_price | REAL | Yesterday's stock price |
| delta / gamma / theta / vega | REAL | Greeks (yesterday's values) |
| IV | REAL | Implied volatility |
| iv_percentile | REAL | 20-day IV percentile |
| open_interest | INTEGER | Today's OI |
| volume | INTEGER | Yesterday's volume |
| breakeven_price | REAL | Stock price needed to break even. Call: strike + premium. Put: strike - premium |
| breakeven_move_pct | REAL | How far the stock needs to move to break even (%) |
| delta_per_dollar | REAL | `abs(delta) / last_price`. Higher = more delta exposure per dollar spent. Efficiency metric |
| in_gamma_zone | INTEGER | 1 if gamma > 0.05. Near-ATM contracts where delta changes fastest |
| theta_decay_dollars | REAL | `theta * 100`. Daily time decay in dollars per contract |
| vega_dollars_per_iv_point | REAL | `vega * 100`. Dollar impact per 1pt IV change |
| intrinsic_value | REAL | In-the-money value (0 for OTM) |
| extrinsic_value | REAL | `last_price - intrinsic`. Time value + volatility premium |
| avg_bid_ask_spread_pct | REAL | From symbol summary. Liquidity cost |
| required_move_to_strike_pct | REAL | OTM only. How far stock needs to move to reach strike (%) |
| days_to_reach_strike | REAL | IV-based estimate: `365 * (required_move / IV)^2`. Statistical, not predictive |
| time_advantage_ratio | REAL | `DTE / days_to_reach_strike`. >1.5 = comfortable time. <1.0 = critical |
| time_pressure_level | TEXT | COMFORTABLE (>1.5) / TIGHT (1.0-1.5) / CRITICAL (<1.0) |

**The time-to-target analysis is useful but approximate.** It uses IV to estimate how long
the stock would statistically take to reach the strike. Not a prediction — more like "given
this stock's typical volatility, do you have enough time?"

---

## v_live_market_snapshot

**Role:** Real-time market context during trading hours. Computed from latest FM scan.

**Source tables:** `flow_options_scans` (latest scan_timestamp for today)
**Note:** Returns nothing outside market hours (no scans, no data).

| Column | Type | Notes |
|--------|------|-------|
| last_updated | TEXT | Timestamp of the latest FM scan |
| trade_date | TEXT | Today's date |
| spy_price | REAL | SPY price from latest scan |
| spy_change_pct | REAL | SPY % change today |
| vix_price | REAL | VIX level from latest scan |
| vix_change_pct | REAL | VIX % change today |
| advancing_stocks | INTEGER | Distinct symbols with positive price change in latest scan |
| declining_stocks | INTEGER | Distinct symbols with negative price change |
| adv_dec_ratio | REAL | advancing / declining. >1 = broad buying. <1 = broad selling |
| market_direction | TEXT | Strong Bull / Bull / Neutral / Bear / Strong Bear |
| volatility_regime | TEXT | LOW (<15) / NORMAL (15-20) / ELEVATED (20-30) / PANIC (>30) |

**Market direction thresholds:**
- Strong Bull: SPY > +1.0% AND VIX < -5.0%
- Bull: SPY > +0.5% AND VIX < 0%
- Strong Bear: SPY < -1.0% AND VIX > +5.0%
- Bear: SPY < -0.5% AND VIX > 0%
- Everything else: Neutral

**Related to item 7.2 (Market Mood Per Cycle):** This view computes similar data but is
query-time only. The console market mood feature would compute per-cycle and display inline.
