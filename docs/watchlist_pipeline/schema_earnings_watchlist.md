# earnings_watchlist — Schema Reference

**Role:** Level 1 Discovery. Curated earnings opportunities — only symbols with actionable
signals within 14 days of earnings.

**Populated by:** `ei_watchlist.py` (Step 1.2 morning pipeline, ~6:50 AM)
**Source data:** `earnings_upcoming` (filtered by signal + proximity + OI)
**Typical size:** ~6 entries (small by design — only the most interesting)

---

## Schema

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT PK | Ticker symbol |
| status | TEXT | Lifecycle stage: UPCOMING / TODAY / T+1 / T+2 / T+3 |
| current_price | REAL | Stock price at last update |
| days_to_earnings | INTEGER | Days until earnings date |
| earnings_date | TEXT | When earnings will be (or were) reported |
| earnings_time | TEXT | BMO (before market open) or AMC (after market close) |
| earnings_play_signal | TEXT | AVOID / NEUTRAL / WATCH / BUY / STRONG BUY |
| iv_percentile_30d | REAL | 30-day IV percentile — how expensive options are historically |
| relative_underpricing_pct | REAL | `(hist_avg - expected) / expected * 100`. Core signal metric |
| expected_move_pct | REAL | What the market expects (from straddle pricing) |
| historical_avg_move_pct | REAL | What actually happens on average for this symbol |
| straddle_expected_move_pct | REAL | Raw straddle expected move |
| oi_balance_text | TEXT | Put/call ratio interpretation (human-readable) |
| alert_count_5d | INTEGER | Flow alerts in past 5 days (cross-signal enrichment) |
| news_sentiment_label | TEXT | Recent news sentiment: Bullish / Bearish / Neutral |
| news_sentiment_score | REAL | Numeric sentiment score (-1 to 1) |
| news_article_count | INTEGER | How many news articles in recent window |
| actual_move_pct | REAL | Post-earnings: what actually happened (filled after earnings) |
| move_direction | TEXT | Post-earnings: UP or DOWN |
| iv_collapse_pct | REAL | Post-earnings: how much IV crushed |
| iv_crush_severity | TEXT | Post-earnings: minimal / mild / normal / high / severe |
| first_appeared_date | TEXT | When this symbol first entered the watchlist |
| created_at | TEXT | Record creation timestamp |
| last_updated | TEXT | Last update timestamp |

## Key Behaviors

**Entry criteria (all must be true):**
- `earnings_play_signal` is WATCH, BUY, or STRONG BUY
- `days_to_earnings` <= 14
- Total OI >= 4,000

**Signal thresholds (relative_underpricing_pct):**
- WATCH: >= 15% (market underpricing the move by 15%+)
- BUY: >= 30%
- STRONG BUY: >= 50%
- Thresholds are provisional — need ~100 events for calibration (~March 2026)

**Lifecycle:** UPCOMING → TODAY → T+1 → T+2 → T+3 → deleted at T+4 cleanup. Post-earnings
columns (actual_move, iv_collapse, etc.) fill in as data becomes available. This lets you
review how the play performed without leaving the watchlist.

**Signal downgrades don't delete:** If IV rises and underpricing drops below threshold, the
signal column updates but the row stays. Avoids whipsawing entries in and out.

**Not very dynamic right now:** Ben noted this is mostly a static look at days-to-earnings and
signal rating. Potential for intraday IV tracking (item 1.4) to make it more dynamic.
