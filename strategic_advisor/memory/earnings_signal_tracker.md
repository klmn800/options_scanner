# Earnings Signal Tracking -- Q1 2026 Season

Track signal performance as events accumulate. Run the tracking query each session.

## Standard Tracking Query

**IMPORTANT:** After the Friday collector runs, `earnings_upcoming` gets updated to NEXT quarter dates. Use `earnings_events` for historical lookback, not `earnings_upcoming`.

```sql
-- Run against production DB (data/datalake.db) since query DB sync may lag
SELECT ee.symbol, ee.earnings_date, ee.earnings_play_signal,
       ee.straddle_expected_move_pct, ee.historical_avg_move_pct,
       ee.relative_underpricing_pct,
       hp_pre.close_price as pre_close, hp_post.close_price as post_close,
       ROUND((hp_post.close_price - hp_pre.close_price) / hp_pre.close_price * 100, 2) as move_1day_pct,
       ROUND(ABS((hp_post.close_price - hp_pre.close_price) / hp_pre.close_price * 100), 2) as abs_move_pct,
       CASE WHEN ABS((hp_post.close_price - hp_pre.close_price) / hp_pre.close_price * 100) > ee.straddle_expected_move_pct THEN 'BEAT' ELSE 'MISS' END as vs_straddle
FROM earnings_events ee
JOIN historical_prices hp_pre ON ee.symbol = hp_pre.symbol
    AND hp_pre.trade_date = (SELECT MAX(trade_date) FROM historical_prices hp WHERE hp.symbol = ee.symbol AND hp.trade_date < ee.earnings_date)
JOIN historical_prices hp_post ON ee.symbol = hp_post.symbol
    AND hp_post.trade_date = (SELECT MIN(trade_date) FROM historical_prices hp WHERE hp.symbol = ee.symbol AND hp.trade_date >= ee.earnings_date)
WHERE ee.earnings_date >= '2026-04-13'
    AND ee.earnings_play_signal IN ('BUY', 'STRONG BUY', 'WATCH')
ORDER BY ee.earnings_date
```

## Results Log

### Session 004 (2026-04-18) -- EXPANDED: 11 events from earnings_events (production DB)

Same events as Session 002, now confirmed against `earnings_events` table (populated by Friday collector).

| Symbol | Date | Signal | Straddle | Hist Avg | Actual Move | Abs Move | Beat? |
|--------|------|--------|----------|----------|-------------|----------|-------|
| FAST | 4/13 | STRONG BUY (101.6%) | 2.73% | 5.50% | -6.85% | 6.85% | YES |
| WFC | 4/14 | BUY (33.6%) | 3.79% | 5.06% | -5.70% | 5.70% | YES |
| KMI | 4/15 | WATCH (19.6%) | 1.85% | 2.22% | +0.16% | 0.16% | NO |
| MS | 4/15 | BUY (49.5%) | 2.92% | 4.36% | +4.52% | 4.52% | YES |
| MAN | 4/16 | WATCH (19.9%) | 7.80% | 9.35% | +0.88% | 0.88% | NO |
| ABT | 4/16 | WATCH (17.1%) | 4.25% | 4.98% | -6.00% | 6.00% | YES |
| INFY | 4/16 | STRONG BUY (51.7%) | 2.44% | 3.69% | +0.49% | 0.49% | NO |
| MRSH | 4/16 | BUY (35.2%) | 3.09% | 4.18% | +4.39% | 4.39% | YES |
| PLD | 4/16 | WATCH (16.6%) | 2.93% | 3.41% | +1.72% | 1.72% | NO |
| TFC | 4/17 | WATCH (18.5%) | 2.46% | 2.91% | +2.31% | 2.31% | NO |
| ERIC | 4/17 | STRONG BUY (82.8%) | 6.57% | 12.01% | -6.50% | 6.50% | MISS |

### Signal Performance Summary (n=11, WATCH+)

| Signal | n | Beat Straddle | Beat % | Avg Abs Move | Avg Straddle |
|--------|---|---------------|--------|--------------|--------------|
| BUY | 3 | 3 | **100%** | 4.87% | 3.27% |
| STRONG BUY | 3 | 1 | 33% | 4.61% | 3.91% |
| WATCH | 5 | 1 | 20% | 2.21% | 3.86% |

### Full Signal Performance (n=38, ALL signals including AVOID/NEUTRAL)

From the full 38-event dataset (Session 004 query):

| Signal | n | Beat Straddle | Beat % | Avg Abs Move |
|--------|---|---------------|--------|--------------|
| BUY | 3 | 3 | **100%** | 4.87% |
| STRONG BUY | 3 | 1 | 33% | 4.61% |
| WATCH | 5 | 1 | 20% | 2.21% |
| NEUTRAL | 4 | 0 | 0% | 1.47% |
| AVOID | 23 | 3 | 13% | 2.92% |

**Observations (LOW-MEDIUM CONFIDENCE -- 38 events total, still small signal samples):**

1. **BUY is the best signal: 3/3 = 100%.** All three (WFC, MS, MRSH) beat their straddle by substantial margins. Average absolute move of 4.87% vs 3.27% straddle expectation.

2. **STRONG BUY is disappointing: 1/3 = 33%.** FAST was a clear winner (-6.85% vs 2.73% straddle). INFY was a dud (+0.49% vs 2.44%). ERIC missed (-6.50% vs 6.57% -- close!). Two of three had large absolute moves but the straddle expectation was also high.

3. **Signal ranking correlates with move magnitude:** BUY 4.87% > STRONG BUY 4.61% > AVOID 2.92% > WATCH 2.21% > NEUTRAL 1.47%. The signal system does capture something real about expected move magnitude.

4. **AVOID has surprises:** 3/23 beat straddle (13%). ALLY surprised with 8.1% move on an AVOID signal. KMX had a massive -15.12% move on AVOID -- these are events where the straddle was OVER-priced relative to history but the actual move was huge anyway (news-driven).

5. **The straddle benchmark matters:** ERIC moved -6.50% which would be a win on most signals, but the straddle was priced at 6.57%. It ALMOST beat the straddle. The signal identified correctly that ERIC moves more than average, but the market also priced this in.

6. **BUY > STRONG BUY (early evidence for threshold tuning):** This continues the pattern from Session 002. BUY signals (30-50% underpricing) may be the "sweet spot" where the market is underpricing enough to be profitable but not so extreme that data quality issues dominate. Worth monitoring through 50+ events.

### Next Events to Watch

**Reporting this week (April 20-25):**
- CLF 4/20 (WATCH, 24%) -- Sunday, likely reported BMO Monday
- HAL 4/21 (WATCH, 22%)
- **MMM 4/21 (STRONG BUY, 68%)** -- key test of STRONG BUY on fresh data
- **UNH 4/21 (STRONG BUY, 107%)** -- highest conviction signal. Ben mentioned too expensive to trade.
- PM 4/22 (WATCH, 21%)
- TSLA 4/22 (WATCH, 29%)
- GILD 4/23 (WATCH, 17%)
- LMT 4/23 (WATCH, 28%)
- **HON 4/23 (BUY, 50%)** -- another BUY signal test
- WST 4/23 (WATCH, 29%)

**Priority tracking:** MMM and UNH are the week's most important data points for STRONG BUY validation. HON tests the BUY streak.

### Session 005 Action Items
- Re-run tracking query against production DB (or query DB if synced by then)
- Update with MMM, UNH, HON results
- Check if `earnings_moves` pipeline has caught up for April events
- Track cumulative signal performance curve
