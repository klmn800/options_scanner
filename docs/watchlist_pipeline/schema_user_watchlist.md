# user_watchlist — Schema Reference

**Role:** Persistent user-curated list. The only watchlist that reflects YOUR decisions rather
than automated signals. Survives across days (no expiration window).

**Populated by:** Morning View TUI (My Watchlist screen — user adds/removes symbols)
**Written to:** Production DB (`datalake.db`)
**Typical size:** ~27 entries

---

## Schema

| Column | Type | Description |
|--------|------|-------------|
| symbol | TEXT PK | Ticker symbol |
| added_date | TEXT | When the user added this symbol |
| added_reason | TEXT | Auto-captured trigger reason (FLOW_ALERT, EARNINGS_PLAY, or both) |
| user_notes | TEXT | Free-text notes. **NO UI YET** — field exists but can't be edited in TUI |
| priority | INTEGER | User-assigned priority. **NO UI YET** — defaults to 0 |
| removed_date | TEXT | Soft delete. NULL = active. Set to date when "removed" |

**Index:** `idx_watchlist_active` on `(removed_date)` for fast active filtering.
**Foreign key:** `symbol` references `symbol_metadata(symbol)`.

## Key Behaviors

**Soft delete pattern:** Removing a symbol sets `removed_date` rather than deleting the row.
Active entries are `WHERE removed_date IS NULL`. Historical entries remain for analysis.

**No enrichment data stored:** This table is just the list of symbols + metadata about
the decision. All market context (price, IV, volume, alerts) must come from joining with
summary tables at query time. This is intentional — keeps the table clean and context always
fresh.

**Currently underused:** Has fields for notes and priority that aren't wired to any UI.
Item 6.4 in the to-do list addresses this.

**Candidate for Level 3 evolution:** This table could be extended or replaced to become the
Active Watch table described in the Watchlist Pipeline brainstorm. Would need: status
tracking (watching/ready_to_buy/position_open/dismissed), source tracking, and a companion
view for enrichment. See `docs/watchlist_pipeline/BRAINSTORM.md`.
