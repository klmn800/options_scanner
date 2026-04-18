# Earnings Signal Tracking — Q1 2026 Season

Track signal performance as events accumulate. Run the "Standard Tracking Query" each session.

## Standard Tracking Query

```sql
-- Run this each session against datalake_query.db
SELECT eu.symbol, eu.earnings_date, eu.earnings_play_signal,
       eu.straddle_expected_move_pct, eu.historical_avg_move_pct,
       eu.relative_underpricing_pct,
       hp_pre.close_price as pre_close, hp_post.close_price as post_close,
       ROUND((hp_post.close_price - hp_pre.close_price) / hp_pre.close_price * 100, 2) as move_1day_pct,
       CASE WHEN ABS((hp_post.close_price - hp_pre.close_price) / hp_pre.close_price * 100) > eu.straddle_expected_move_pct THEN 'BEAT' ELSE 'MISS' END as vs_straddle
FROM earnings_upcoming eu
JOIN historical_prices hp_pre ON eu.symbol = hp_pre.symbol
    AND hp_pre.trade_date = (SELECT MAX(trade_date) FROM historical_prices WHERE symbol = eu.symbol AND trade_date < eu.earnings_date)
JOIN historical_prices hp_post ON eu.symbol = hp_post.symbol
    AND hp_post.trade_date = (SELECT MIN(trade_date) FROM historical_prices WHERE symbol = eu.symbol AND trade_date >= eu.earnings_date)
WHERE eu.earnings_date BETWEEN '2026-04-01' AND '2026-05-31'
    AND eu.earnings_play_signal IN ('BUY', 'STRONG BUY', 'WATCH')
ORDER BY eu.earnings_date
```

## Results Log

### Session 002 (2026-04-18) — 11 events with outcomes

| Symbol | Date | Signal | Straddle | Hist Avg | Actual Move | Beat Straddle? |
|--------|------|--------|----------|----------|-------------|----------------|
| FAST | 4/13 | STRONG BUY (101.6%) | 2.73% | 5.50% | -6.85% | YES |
| WFC | 4/14 | BUY (33.6%) | 3.79% | 5.06% | -5.70% | YES |
| KMI | 4/15 | WATCH (19.6%) | 1.85% | 2.22% | +0.16% | NO |
| MS | 4/15 | BUY (49.5%) | 2.92% | 4.36% | +4.52% | YES |
| MAN | 4/16 | WATCH (19.9%) | 7.80% | 9.35% | +0.88% | NO |
| ABT | 4/16 | WATCH (17.1%) | 4.25% | 4.98% | -6.00% | YES |
| INFY | 4/16 | STRONG BUY (51.7%) | 2.44% | 3.69% | +0.49% | NO |
| MRSH | 4/16 | BUY (35.2%) | 3.09% | 4.18% | +4.39% | YES |
| PLD | 4/16 | WATCH (16.6%) | 2.93% | 3.41% | +1.72% | NO |
| TFC | 4/17 | WATCH (18.5%) | 2.46% | 2.91% | +2.31% | NO |
| ERIC | 4/17 | STRONG BUY (82.8%) | 6.57% | 12.01% | -6.50% | MATCH |

**Summary (n=11):**
- Overall beat rate: 5/11 (45%)
- BUY: 3/3 beat straddle (100%)
- STRONG BUY: 1/3 beat straddle, 1 match (33-67%)
- WATCH: 1/5 beat straddle (20%)
- Avg absolute move: 3.55%
- Avg straddle expectation: 3.88%

**Early observations (LOW CONFIDENCE — 11 events):**
- BUY signals are performing best. All 3 had actual moves exceeding straddle.
- STRONG BUY is mixed. FAST worked spectacularly, INFY was a dud, ERIC was a coin flip.
- WATCH signals rarely beat the straddle but also rarely had big moves in either direction.
- The signal is directionally useful: BUY/STRONG BUY events DO tend to move more than WATCH events.
- Much too early for conclusions. Need 30+ events for any pattern to stabilize.

**Note:** Using close-to-close moves only. Intraday max moves would change the picture significantly (FAST peak might be >6.85%, ERIC might have had intraday move >6.50% before reverting). Post-earnings calc pipeline hasn't populated max_intraday for these events yet — check next session.

### Next Events to Watch
- CLF 4/20, HAL/MMM/UNH 4/21, PM/TSLA 4/22, GILD/LMT/HON/WST 4/23 — all have WATCH+ signals
- UNH (STRONG BUY, 107%) and MMM (STRONG BUY, 68%) are the highest-conviction upcoming signals with fresh data
- HOLX 4/30 and AES 4/30 are STRONG BUY but HOLX has stale data (likely false positive — see Proposal 001)
