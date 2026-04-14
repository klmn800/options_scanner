# Earnings Date Source Rewire Plan

**Created:** 2026-03-05
**Status:** Implemented (2026-03-05) — fresh start block active, pending first Friday run
**Background:** `docs/earnings_strategy_refactor/earnings_date_investigation.md`
**File to modify:** `strategies/earnings_intel/ei_collector.py`
**Reference code:** `strategies/earnings_intel/Deprecated/ei_fetch_upcoming.py` (yfinance patterns)

---

## Problem

Finnhub earnings dates are 50% accurate vs Robinhood. yfinance is 100% accurate on confirmed dates. Currently `ei_collector.py` uses Finnhub for everything.

## Design

### Source Roles

| Field | Source | Notes |
|-------|--------|-------|
| **Date** | yfinance (primary), Finnhub (fallback for new symbols only) | Never auto-overwrite an existing date |
| **Timing (bmo/amc)** | Finnhub | yfinance doesn't provide this. Always update. |
| **EPS estimate** | yfinance (primary), Finnhub (fallback) | Always update — consensus shifts legitimately |
| **Revenue estimate** | yfinance (primary), Finnhub (fallback) | Always update — consensus shifts legitimately |

### Core Rule: Dates Are Never Auto-Overwritten

The collector distinguishes between **new symbols** and **existing symbols**:

**New symbol** (not yet in `earnings_upcoming`):
- Insert with best available date: yfinance if it has a future date, else Finnhub
- Set timing from Finnhub

**Existing symbol** (already in `earnings_upcoming`):
- **DO NOT overwrite `earnings_date`** — ever
- Compare stored date vs yfinance and Finnhub. If either disagrees, **log the conflict** to console + text log
- DO update: timing (bmo/amc), eps_estimate, revenue_estimate, earnings_days_ahead (recalculated from stored date)

This means:
- Ben's manual SQL corrections survive weekly runs
- Dates that were correct on initial insert stay correct
- Bad dates require Ben to review the disagreement log and correct manually
- No `date_override` column or priority chain needed

### Disagreement Logging

Printed to console AND text log during the collector run:

```
  DATE CONFLICT: NKE — stored=2026-03-18, yfinance=2026-03-31, finnhub=2026-03-18
  DATE CONFLICT: LULU — stored=2026-03-26, yfinance=2026-03-17, finnhub=2026-03-26
  DATE CONFLICT: PAYX — stored=2026-03-25, yfinance=2026-03-26, finnhub=2026-03-24
```

Ben reviews these after the Friday run, checks against Robinhood, and corrects via direct SQL:

```sql
UPDATE earnings_upcoming SET earnings_date = '2026-03-31' WHERE symbol = 'NKE';
```

This is expected to be rare — most conflicts are on unverified dates that will resolve naturally as companies confirm. Checking weekly is the right cadence since dates can change between runs regardless.

### Performance Tracking

Track source comparison data in `data/performance.db`:

**New table: `earnings_date_sources`**

| Column | Type | Description |
|--------|------|-------------|
| `trade_date` | TEXT | Date of collector run |
| `symbol` | TEXT | Stock symbol |
| `stored_date` | TEXT | Date currently in earnings_upcoming (NULL for new symbols) |
| `yfinance_date` | TEXT | Date from yfinance (NULL if no data / stale) |
| `finnhub_date` | TEXT | Date from Finnhub (NULL if no data) |
| `finnhub_timing` | TEXT | Timing from Finnhub (bmo/amc/etc) |
| `date_source` | TEXT | For new symbols: 'yfinance' or 'finnhub'. For existing: 'preserved' |
| `conflict` | INTEGER | 1 if any source disagrees with stored date, 0 otherwise |

Useful queries:
```sql
-- How often do sources disagree with stored dates?
SELECT trade_date, SUM(conflict), COUNT(*) FROM earnings_date_sources GROUP BY trade_date;

-- Which symbols are chronic disagreers?
SELECT symbol, COUNT(*) as conflicts
FROM earnings_date_sources WHERE conflict = 1
GROUP BY symbol ORDER BY conflicts DESC;

-- What did sources say for a specific symbol over time?
SELECT * FROM earnings_date_sources WHERE symbol = 'NKE' ORDER BY trade_date;
```

**Not stored in datalake** — only the active date lives there. Performance DB captures the audit trail.

---

## Implementation Steps

### 1. Add yfinance fetch helper

Lift pattern from `Deprecated/ei_fetch_upcoming.py` lines 188-253:
- `contextlib.redirect_stderr` to suppress yfinance noise
- `yf.Ticker(sym).calendar` → extract `Earnings Date[0]`, `Earnings Average`, `Revenue Average`
- 0.1s rate limiting between calls
- Stale detection: if `Earnings Date[0] < today`, treat as no data (yfinance returns past quarter)

### 2. Restructure the per-symbol loop in `_fetch_and_upsert_earnings()`

Current flow:
```
for symbol in stock_symbols:
    finnhub_data = fetch(symbol)         # date, timing, eps, revenue
    records.append(finnhub_data)         # all fields from Finnhub
batch_upsert(records)                    # INSERT OR REPLACE
```

New flow:
```
# Pre-fetch: get existing dates from earnings_upcoming
existing_dates = {row.symbol: row.earnings_date for row in SELECT symbol, earnings_date FROM earnings_upcoming}

for symbol in stock_symbols:
    yf_data = fetch_yfinance(symbol)     # date, eps, revenue (or None if stale/missing)
    fh_data = fetch_finnhub(symbol)      # timing (+ date as fallback)

    if symbol in existing_dates:
        # EXISTING: preserve stored date, update other fields, log conflicts
        record.date = existing_dates[symbol]
        record.timing = fh_data.timing
        record.eps = yf_data.eps or fh_data.eps
        record.revenue = yf_data.revenue or fh_data.revenue
        log_conflicts(stored=existing_dates[symbol], yf=yf_data.date, fh=fh_data.date)
    else:
        # NEW: pick best date
        record.date = yf_data.date (if future) or fh_data.date
        record.timing = fh_data.timing
        record.eps = yf_data.eps or fh_data.eps
        record.revenue = yf_data.revenue or fh_data.revenue

    records.append(record)
    perf_records.append(comparison_data)

batch_upsert(records)                    # date unchanged for existing symbols
write_perf_records(perf_records)         # to performance.db
```

### 3. Modify the upsert SQL

Current upsert overwrites `earnings_date` on conflict. Change to preserve it:

```sql
ON CONFLICT(symbol) DO UPDATE SET
    -- earnings_date NOT updated (preserved)
    earnings_days_ahead = excluded.earnings_days_ahead,
    earnings_time = COALESCE(
        NULLIF(excluded.earnings_time, 'Unknown'),
        earnings_upcoming.earnings_time
    ),
    eps_estimate = COALESCE(excluded.eps_estimate, earnings_upcoming.eps_estimate),
    revenue_estimate = COALESCE(excluded.revenue_estimate, earnings_upcoming.revenue_estimate),
    updated_at = excluded.updated_at
```

Note: `earnings_days_ahead` MUST be recalculated every run from the stored date (not the source date), since it's relative to today. The update path must recompute `(stored_date - today).days`.

### 4. Write performance data

After the main loop, batch-insert comparison records into `performance.db` → `earnings_date_sources`.

### 5. Console output

Follow existing console patterns (via `log_utils.py`):
- Per-symbol progress lines every 50 symbols (existing pattern)
- Conflict lines printed inline as they occur
- Summary at end:
  ```
  Date sources: X new (yfinance) | Y new (finnhub fallback) | Z preserved | W conflicts logged
  ```

### 6. Performance consideration

- Finnhub: rate limited at 60/min → ~1s between calls
- yfinance: ~0.5s per call, no formal rate limit
- **Interleave in same loop** — yfinance call fills Finnhub rate-limit dead time
- Interleaved: ~1s per symbol × 742 = **~12 minutes** (same as current Finnhub-only!)
- Two-pass would be ~19.5 minutes — no reason to do this
- yfinance errors must be fast (try/except, short timeout) so they don't block the Finnhub cadence

---

## What Changes

- `ei_collector.py` — rewired per-symbol loop, upsert SQL, new yfinance helper, conflict logging
- `performance.db` — new `earnings_date_sources` table
- `tools/performance_writer.py` — may need update if it handles table creation

## What Does NOT Change

- `ei_main.py` daily pipeline — unchanged, doesn't fetch dates
- `ei_moves_upcoming.py` — unchanged, consumes dates from `earnings_upcoming`
- `ei_watchlist.py` — unchanged
- `earnings_upcoming` table schema — no new columns
- Archive/cleanup logic in collector — unchanged
- Finnhub API client — unchanged (still fetches per-symbol)

## First-Run Fresh Start

The first run after this rewire should start from a clean slate so all 742 symbols hit the "new symbol" path and get yfinance dates. Since Ben won't be available to clear the table manually, the code handles it automatically with a one-time self-removing block.

### Implementation

In `_fetch_and_upsert_earnings()`, before the pre-fetch of existing dates, add a clearly marked one-time block:

```python
# ╔══════════════════════════════════════════════════════════════════╗
# ║ ONE-TIME FRESH START — Remove this entire block after first run ║
# ║                                                                  ║
# ║ AUTOFIX INSTRUCTIONS: After the collector completes successfully ║
# ║ on its first run with the yfinance rewire, delete everything     ║
# ║ between the ╔ and ╚ markers (inclusive). The fresh start is no   ║
# ║ longer needed — subsequent runs should preserve existing dates.  ║
# ║ Also remove the queue_error() call at the end of this method     ║
# ║ that triggers this removal.                                      ║
# ╚══════════════════════════════════════════════════════════════════╝
beautiful_log("FRESH START: Clearing earnings_upcoming for yfinance rewire", level='warning')
conn = self._get_connection()
conn.execute("DELETE FROM earnings_upcoming")
conn.commit()
conn.close()
beautiful_log("  Cleared — all symbols will be re-fetched with yfinance dates", level='warning')
```

At the end of a successful run, trigger autofix to remove the block:

```python
# Trigger autofix to remove the one-time fresh start block
queue_error(
    error_type='scheduled_code_removal',
    context={
        'file': 'strategies/earnings_intel/ei_collector.py',
        'action': 'Remove the ONE-TIME FRESH START block (between ╔ and ╚ markers) '
                  'and remove this queue_error() call itself. '
                  'The fresh start was a one-time migration step for the yfinance rewire.',
    },
    severity='INFO'
)
```

### Why this works
- Signal columns (expected_move_pct, earnings_play_signal, etc.) are wiped but recalculated by Monday morning's daily pipeline (Phase 1.2)
- Collector runs Friday evening → fresh dates from yfinance/Finnhub
- Autofix runs Phase 4.2 (after collector) → removes the block for next week
- If autofix doesn't run or fails, the block runs again next Friday — harmless since the table would be repopulated with yfinance dates anyway

## Testing

1. Run modified collector standalone for a subset (10-20 symbols)
2. Verify: new symbols get yfinance dates, existing symbols keep stored dates
3. Verify: conflict logging appears correctly in console + log file
4. Verify: performance DB records written to `earnings_date_sources`
5. Full 742-symbol run
6. Spot-check near-term conflicts against Robinhood
