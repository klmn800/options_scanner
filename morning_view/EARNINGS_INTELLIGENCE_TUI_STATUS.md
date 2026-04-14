# Earnings Intelligence TUI Integration - Status Report

**Date**: 2025-10-15
**Purpose**: Research findings and implementation plan for integrating earnings intelligence into Morning View TUI

---

## Executive Summary

The Earnings Intelligence System (`strategies/earnings_intel/`) has **26,635 historical earnings events** with **9,250 calculated moves**. The system is partially operational:
- ✅ Core data collection working (events, moves)
- ❌ IV time-series tracking not started (snapshots table empty)
- ❌ Sector sympathy analysis not calculated (sector_effects table empty)
- ✅ Morning scanner runs daily but outputs to logs only (no database table)

**Recommended Start**: Phase 4 (Earnings History) + Phase 5 (Intelligence Menu) - focus on what data exists (moves, journal).

---

## Database State Assessment

### Populated Tables (Ready to Use)

| Table | Rows | Content | Status |
|-------|------|---------|--------|
| `earnings_events` | 26,635 | Historical earnings archive (1993-2025)<br>Includes journal fields: `notes`, `tags`, `note_type`, `sentiment` | ✅ Ready |
| `earnings_moves` | 9,250 | Price moves (1-day, 3-day, 5-day)<br>IV changes (buildup, collapse, severity) | ✅ Ready |
| `industry_peer_mappings` | Populated | Peer relationships by industry | ✅ Ready |
| `earnings_upcoming` | Current | Next 90 days earnings calendar | ✅ Ready |

### Empty Tables (Not Yet Collecting)

| Table | Rows | Purpose | Impact |
|-------|------|---------|--------|
| `earnings_snapshots` | 0 | IV/price time-series (T-7 to T+3) | ⚠️ Can't show IV evolution charts |
| `earnings_sector_effects` | 0 | Sector sympathy correlation data | ⚠️ Can't show peer arbitrage analysis |

**Why Empty?**
- `ei_snapshot_collector.py` exists but hasn't run yet (daily 5PM pipeline)
- `ei_post_earnings_calc.py` calculates moves but not sector effects yet
- These will populate as system runs going forward

---

## Morning Scanner Architecture

**Script**: `strategies/earnings_intel/ei_arbitrage_scanner.py`
**Schedule**: Daily at 6:30 AM (automated via `ei_main.py --morning-scan`)
**Output**: Logs only (`logs/ei_arbitrage_scanner.log`)

### What It Does
1. Queries `earnings_events` for today's earnings
2. Gets industry peers from `industry_peer_mappings`
3. Compares IV from `options_symbol_summary` (primary vs peers)
4. Calculates opportunity score: `(iv_discount * 0.5) + (correlation * 50)`
5. Ranks as High/Medium/Low quality

### What It Doesn't Do
- ❌ No database table for results
- ❌ No persistence (scan results disappear after console display)
- ❌ Historical correlation lookups fail (earnings_sector_effects is empty)

**Current State**: Scanner runs but can't calculate correlation because `earnings_sector_effects` table is empty. Still finds IV discounts though.

---

## Critical Questions - Answered

### Q1: Where does morning scanner output go?
**Answer**: Logs only - no database table exists

**Options**:
- Parse `logs/ei_arbitrage_scanner.log` (fragile)
- Create `arbitrage_scan_results` table (clean but needs schema)
- Query live when TUI opens (simple, fresh data)

**Recommendation**: Query live for TUI - no storage needed, always fresh

### Q2: Do trading journal columns exist in earnings_events?
**Answer**: YES - all fields exist and are ready to use:
- `notes` (TEXT)
- `tags` (TEXT - comma-separated)
- `note_type` (TEXT - trade/observation/pattern/lesson)
- `sentiment` (TEXT - bullish/bearish/neutral)

**Implementation**: Can build Trading Journal browser immediately

### Q3: earnings_sector_effects table status?
**Answer**: Empty (0 rows)

**Why**: Post-earnings calculator exists but sector sympathy calculation hasn't run yet

**Impact**: Can't show Phase 6 (Sector Sympathy View) until data is collected

### Q4: Cross-linking between calendar and intelligence?
**Answer**: Easy to add - Textual supports dynamic key bindings

**Example**: From calendar day detail, press `H` to jump to earnings history for that day's symbols

### Q5: Which symbol detail screen?
**Answer**: Only one - `morning_view/screens/symbol_detail.py`

Both Discovery Dashboard and Calendar navigation route to same screen. Earnings history should appear in both contexts.

---

## Pattern Detection Query Performance

**Concern**: Complex aggregation queries scanning 9,250 rows

**Test Needed**: Run these queries to check speed:

```sql
-- Delayed Reaction Pattern (small 1-day, large 5-day)
SELECT symbol, AVG(ABS(move_1day_pct)) as avg_1day, AVG(ABS(move_5day_pct)) as avg_5day, COUNT(*) as n
FROM earnings_moves
WHERE move_1day_pct IS NOT NULL AND move_5day_pct IS NOT NULL
GROUP BY symbol
HAVING avg_1day < 5 AND avg_5day > 8 AND n >= 4;

-- Severe IV Crush Pattern
SELECT symbol, AVG(iv_crush_pct) as avg_crush, COUNT(*) as n
FROM earnings_moves
WHERE iv_crush_pct IS NOT NULL
GROUP BY symbol
HAVING avg_crush < -40 AND n >= 4;
```

**If slow**: Pre-compute and cache, or add indexes on move columns

---

## Implementation Plan - Phase 4 + 5

### Phase 4: Enhanced Symbol Detail (3-4 hours)

**File**: `morning_view/screens/symbol_detail.py` (modify existing)

**Add Earnings History Section**:

**UX Decision - Option C (Recommended)**:
- Always show one-liner summary at top of symbol detail
- Example: `Earnings History: 8 quarters | Avg move 9.2% | [H] View Full`
- Press `H` key to toggle full history table

**Data Query**:
```python
def get_earnings_history(self, symbol: str, limit: int = 8):
    """Get historical earnings for symbol with moves"""
    query = """
    SELECT ee.earnings_date, ee.fiscal_quarter,
           em.move_1day_pct, em.move_direction, em.iv_crush_severity,
           ee.notes, ee.tags
    FROM earnings_events ee
    LEFT JOIN earnings_moves em ON ee.event_id = em.event_id AND em.symbol = ee.symbol
    WHERE ee.symbol = ?
    ORDER BY ee.earnings_date DESC
    LIMIT ?
    """
    return self.query(query, (symbol, limit))
```

**Full History Display** (when `H` pressed):
```
┌─ NVDA Earnings History (Last 8 Quarters) ─────────────────┐
│ Date       │ Move  │ Direction │ IV Crush │ Your Notes    │
├────────────┼───────┼───────────┼──────────┼───────────────┤
│ 2025-02-26 │ -5.1% │ Down      │ Severe   │ Guidance miss │
│ 2024-11-20 │ +8.8% │ Up        │ Moderate │ Beat + raise  │
│ 2024-08-28 │+13.1% │ Up        │ Moderate │ Strong demand │
└────────────────────────────────────────────────────────────┘
Avg: 9.2% | Median: 8.6% | Pattern: Tends to move 8-10% on earnings
```

**Key Binding**: Add `Binding("h", "toggle_earnings_history", "History")` to BINDINGS

---

### Phase 5: Earnings Intelligence Menu (2 hours)

**New File**: `morning_view/screens/earnings_intelligence_menu.py`

**Menu Structure** (3 working options):

```
┌─ Earnings Intelligence ───────────────────────────────────┐
│ Historical Analysis & Pattern Recognition                 │
│                                                            │
│ 1. Pattern Explorer                                       │
│    → Recurring patterns across 9,250+ calculated moves    │
│                                                            │
│ 2. Trading Journal (Read-Only)                            │
│    → Your earnings notes & observations                   │
│                                                            │
│ 3. Database Stats                                         │
│    → Coverage: 26,635 events | 736 symbols | 1993-2025   │
│                                                            │
│ [Coming Soon]                                             │
│ - Morning Arbitrage Scanner (needs database table)        │
│ - Sector Sympathy View (needs sector_effects data)        │
│                                                            │
│ ESC. Back to Main Menu                                    │
└────────────────────────────────────────────────────────────┘
```

**Why Skip Scanner & Sympathy**:
- Morning scanner has no database table yet
- Sector sympathy table is empty (0 rows)
- Build infrastructure first, add features when data exists

---

## What We Can Build NOW

| Feature | Data Source | Status | Ready? |
|---------|-------------|--------|--------|
| Earnings History | earnings_moves (9,250 rows) | ✅ Data exists | YES |
| Trading Journal | earnings_events.notes/tags | ✅ Fields exist | YES |
| Pattern Explorer | earnings_moves queries | ✅ Data exists | YES |
| Database Stats | All tables | ✅ Data exists | YES |
| Morning Scanner View | ❌ No table | Needs implementation | NO |
| Sector Sympathy | earnings_sector_effects (0 rows) | Needs data collection | NO |
| IV Evolution Charts | earnings_snapshots (0 rows) | Needs data collection | NO |

---

## Next Steps (When Ready)

### Immediate (Phase 4 + 5)
1. Add earnings history to symbol_detail.py
2. Create intelligence menu with 3 working options
3. Test pattern queries for performance
4. Build trading journal browser

**Estimated Time**: 5-6 hours

### Future (Phase 6+)
1. **Start collecting snapshots**: Run `ei_main.py --daily-pipeline` to populate earnings_snapshots
2. **Calculate sector effects**: Enhance post-earnings calculator to populate earnings_sector_effects
3. **Create arbitrage table**: Add schema for morning scanner results
4. **Build remaining views**: Sector sympathy, arbitrage scanner, IV evolution

---

## Design Decisions Made

### UX Patterns
- **Earnings History**: Always-visible one-liner + toggle (Option C)
- **Navigation**: Add `H` key for history, `P` key for peers (when data exists)
- **Menu Structure**: Top-level intelligence menu (not nested under calendar)

### Data Queries
- **Live queries**: No caching for earnings data (small dataset, fast queries)
- **Pattern detection**: Test performance first, add indexes if needed
- **Graceful degradation**: Show "No data available" when tables empty

### Feature Priority
1. HIGH: Earnings history (core value, data exists)
2. HIGH: Trading journal (unique insights, fields ready)
3. MEDIUM: Pattern explorer (interesting but not critical)
4. LOW: Scanner/sympathy (blocked by missing data)

---

## Questions to Answer Later

1. **Should we create arbitrage_scan_results table?** Or query live/parse logs?
2. **Should we backfill sector_effects?** Or wait for forward data collection?
3. **Pattern query caching?** Pre-compute patterns or query on-demand?
4. **Snapshot collection schedule?** When to start populating earnings_snapshots?

---

## File Locations Reference

**Earnings Intelligence System**:
- Main orchestrator: `strategies/earnings_intel/ei_main.py`
- Arbitrage scanner: `strategies/earnings_intel/ei_arbitrage_scanner.py`
- System docs: `strategies/earnings_intel/docs/EARNINGS_INTELLIGENCE_SYSTEM.md`
- Manual operations: `strategies/earnings_intel/docs/MANUAL_OPERATIONS.md`

**Morning View TUI**:
- Symbol detail: `morning_view/screens/symbol_detail.py` (modify this)
- Data layer: `morning_view/tui_data.py` (add earnings methods here)
- Main menu: `morning_view/mv_main.py` (add intelligence menu item)
- Implementation plan: `morning_view/EARNINGS_INTELLIGENCE_TUI_PLAN.md`

**Database**:
- Query DB: `data/datalake_query.db` (read-only, use for TUI)
- Primary DB: `data/datalake.db` (production, avoid during collection)
- Query tool: `tools/direct_db_query.py`

---

## Summary: What's Working, What's Not

✅ **Working**:
- 26,635 earnings events archived
- 9,250 price moves calculated
- Trading journal fields ready
- Morning scanner runs daily (logs only)
- Peer mappings defined

❌ **Not Working**:
- IV time-series tracking (snapshots table empty)
- Sector sympathy analysis (sector_effects table empty)
- Scanner result persistence (no database table)

🎯 **Strategy**: Build Phase 4+5 with existing data (moves, journal). Add Phase 6+ when data collection starts.

---

**Last Updated**: 2025-10-15
**Next Review**: After Phase 4+5 implementation
**Status**: Research complete, ready to implement when user returns
