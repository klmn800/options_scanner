# flow_watchlist_daily — Schema Reference

**Role:** Level 1 Discovery. One entry per symbol per day that had a flow alert. 7-day rolling
window for buy-the-dip detection.

**Populated by:** `fm_watchlist.py` during market hours
**Archived to:** `flow_watchlist_daily_archive` after 7 days
**Typical size:** ~20 active entries

---

## Schema

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| symbol | TEXT | Ticker symbol |
| entry_date | TEXT | Date this watchlist entry was created |
| entry_expiration_date | TEXT | 7 days after entry_date — auto-archive trigger |
| entry_ul_price | REAL | Stock price when entry was created. Anchor for dip detection |
| current_ul_price | REAL | Latest stock price. Updated every FM cycle (~60s) |
| price_diff_pct | REAL | `(current - entry) / entry * 100`. Negative = stock dropped since alert |
| option_type | TEXT | CALL, PUT, or MIXED. Determines dip direction logic |
| first_alert_id | INTEGER | FK to `flow_alerts`. The alert that created this entry |
| alert_count_today | INTEGER | How many alerts fired for this symbol today |
| max_significance_score | REAL | Highest alert score among today's alerts (0-10) |
| dip_detected | BOOLEAN | True if price moved 5%+ in the "buy" direction |
| dip_detected_date | TEXT | When the dip was first detected |
| building_alerts_count | INTEGER | Count of alerts with BUILDING OI resolution (most recent date) |
| closing_alerts_count | INTEGER | Count of alerts with CLOSING OI resolution (most recent date) |
| alert_sentiment | TEXT | BUILDING / CLOSING / NEUTRAL — net sentiment from OI resolution |
| created_at | TEXT | Record creation timestamp |
| last_updated | TEXT | Last price update timestamp |

**Unique constraint:** `(symbol, entry_date)` — one row per symbol per day.

## Key Behaviors

**Dip direction depends on option_type:**
- CALL alert → dip = stock price drops 5%+ (cheaper entry for bullish play)
- PUT alert → dip = stock price rises 5%+ (cheaper entry for bearish play)
- MIXED → any 5% move in either direction

**Staggered entries prevent anchor bias:** If MRVL alerts on Monday and Wednesday, it gets
two entries with two different `entry_ul_price` values. Monday's entry tracks dips from
Monday's price; Wednesday's tracks from Wednesday's price.

**Alert sentiment comes from next-day OI resolution:** `fm_alert_resolver.py` runs at 9:15 AM,
checks if yesterday's alerts saw OI increase (BUILDING = new positions opened) or decrease
(CLOSING = positions exited). This is the core "is this signal real?" check.

**7-day lifecycle:** After 7 days, entries auto-archive to `flow_watchlist_daily_archive`.
The assumption is that a signal more than a week old has either played out or isn't worth
tracking in this table. (Symbols worth longer tracking would move to Level 3 Active Watch.)
