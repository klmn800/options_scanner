# Earnings Intelligence TUI Integration

**Status**: Planning phase (2025-10-11)
**Database**: Read-only access to `datalake_query.db`
**Data Source**: Earnings Intelligence System (`strategies/earnings_intel/`)

---

## Overview

The Earnings Intelligence system provides 26,635 historical earnings events across 736 symbols (1993-2025) with:
- **9,250+ calculated moves** (1-day, 2-day, 3-day, 5-day, max intraday)
- **742 peer relationships** across 124 industries
- **Sector sympathy tracking** (correlation strength, sample size)
- **IV arbitrage detection** (morning scan results)
- **Trading journal** (notes, tags, sentiment) - read-only view in TUI

This document covers read-only TUI integration. For write operations and data management, see `EARNINGS_ADMIN_TUI_PLAN.md`.

---

## Architecture: Top-Level Menu Approach

**Design Decision**: Make intelligence features **top-level menu items** rather than nested under calendar.

**Rationale**:
- Calendar is about **planning ahead** (what's coming up?)
- Intelligence is about **retrospective analysis** (what happened historically?)
- Separate concerns = clearer navigation
- Avoids 5-level deep nesting

**Main Menu Structure**:
```
┌─ Morning View Main Menu ──────────────────────────────────┐
│                                                            │
│ 1. Discovery Dashboard                                    │
│ 2. OI Timing Analysis                                     │
│ 3. Earnings Calendar         [forward-looking]            │
│ 4. Earnings Intelligence     [historical analysis] ⭐ NEW │
│ 5. Flow Alerts                                            │
│                                                            │
│ Q. Quit                                                    │
└────────────────────────────────────────────────────────────┘
```

---

## Phase 4: Enhanced Symbol Detail (3-4 hours)

**Goal**: Add earnings history tab/section to existing SymbolDetailScreen

### Implementation
**File**: `morning_view/screens/symbol_detail.py` (modify existing)

**New Section: "Earnings History"**
```
┌─ NVDA Earnings History (Last 8 Quarters) ─────────────────┐
│ Date       │ Move  │ Direction │ IV Crush │ Your Notes    │
├────────────┼───────┼───────────┼──────────┼───────────────┤
│ 2025-02-26 │ -5.1% │ Down      │ Severe   │ Guidance miss │
│ 2024-11-20 │ +8.8% │ Up        │ Moderate │ Beat + raise  │
│ 2024-08-28 │+13.1% │ Up        │ Moderate │ Strong demand │
│ 2024-05-22 │ +9.3% │ Up        │ Moderate │ Data center ↑ │
└────────────────────────────────────────────────────────────┘
Avg Move: 9.2% │ Median: 8.6% │ Max: 13.1% │ Beats: 6/8
Pattern Detected: Tends to move 8-10% on earnings
```

### Data Layer
**File**: `morning_view/tui_data.py` (add method)

```python
def get_earnings_history(self, symbol: str, limit: int = 8):
    """Get historical earnings for symbol with moves"""
    query = """
    SELECT ee.earnings_date, ee.fiscal_quarter, ee.actual_eps, ee.estimated_eps,
           em.move_1day_pct, em.move_direction, em.iv_crush_severity,
           ee.notes, ee.tags
    FROM earnings_events ee
    LEFT JOIN earnings_moves em ON ee.event_id = em.event_id
    WHERE ee.symbol = ?
    ORDER BY ee.earnings_date DESC
    LIMIT ?
    """
    return self.query(query, (symbol, limit))
```

### Key Bindings
- `H` - Toggle earnings history view (from symbol detail screen)
- ESC - Back to previous screen

---

## Phase 5: Earnings Intelligence Menu (2 hours)

**Goal**: Create top-level menu with intelligence features

### Implementation
**New File**: `morning_view/screens/earnings_intelligence_menu.py`

```
┌─ Earnings Intelligence ───────────────────────────────────┐
│ Historical Analysis & Pattern Recognition                 │
│                                                            │
│ 1. Morning Arbitrage Scanner                              │
│    → Today's IV arbitrage opportunities                   │
│                                                            │
│ 2. Trading Journal (Read-Only)                            │
│    → Your earnings notes & observations                   │
│                                                            │
│ 3. Pattern Explorer                                       │
│    → Recurring patterns across 26K+ earnings              │
│                                                            │
│ 4. Database Stats                                         │
│    → Coverage: 26,635 events | 736 symbols | 1993-2025   │
│                                                            │
│ ESC. Back to Main Menu                                    │
└────────────────────────────────────────────────────────────┘
```

---

## Phase 6: Sector Sympathy View (2-3 hours)

**Goal**: Show peer correlation when viewing symbol earning

**When**: User presses `P` (Peers) from symbol detail screen OR day detail screen

**New Screen**: `morning_view/screens/sector_sympathy.py`

```
┌─ Sector Sympathy: NVDA Earnings → Semiconductors ─────────┐
│ When NVDA reports, these peers typically move:            │
│                                                            │
│ Peer │ Avg Move │ Correlation │ Sample │ Current IV Gap  │
├──────┼──────────┼─────────────┼────────┼─────────────────┤
│ AMD  │  +4.2%   │    0.82     │   12   │ -12% (cheap!)   │
│ INTC │  +2.1%   │    0.71     │   12   │  -8%            │
│ SMCI │  +6.8%   │    0.89     │    8   │ -18% (ALERT!)   │
│ QCOM │  +1.5%   │    0.65     │   10   │  -5%            │
└────────────────────────────────────────────────────────────┘
Best Arbitrage: SMCI (Score: 45.2, High Quality)
Reasoning: High correlation (0.89), large IV discount (18%)

[H]istory │ [B]ack
```

### Data Layer
```python
def get_sector_sympathy(self, primary_symbol: str):
    """Get peer correlation data for symbol's earnings"""
    query = """
    SELECT ese.peer_symbol,
           AVG(ese.peer_move_pct) as avg_peer_move,
           ese.correlation_strength, ese.sample_size,
           ese.iv_arbitrage_delta, ese.arbitrage_quality
    FROM earnings_sector_effects ese
    WHERE ese.primary_symbol = ?
    GROUP BY ese.peer_symbol
    ORDER BY ese.correlation_strength DESC
    """
    return self.query(query, (primary_symbol,))
```

### Key Bindings
- `P` - Open sector sympathy view (from symbol detail or day detail)
- `H` - View historical sympathy events
- ESC - Back to previous screen

---

## Phase 7: Morning Arbitrage Scanner (2 hours)

**Goal**: Display today's arbitrage opportunities from morning scan

**New Screen**: `morning_view/screens/arbitrage_scanner.py`

```
┌─ Today's Arbitrage Opportunities (2025-10-11 06:32 AM) ───┐
│ Scan Results: 12 opportunities (3 High, 5 Medium, 4 Low)  │
│                                                            │
│ HIGH QUALITY (Score > 40)                                  │
├──────────┬──────┬──────────┬──────┬───────┬──────────────┤
│ Primary  │ Peer │ IV Disc  │ Corr │ Score │ Earnings Time│
├──────────┼──────┼──────────┼──────┼───────┼──────────────┤
│ NVDA     │ SMCI │   18%    │ 0.89 │  45.2 │ AMC          │
│ NVDA     │ AMD  │   12%    │ 0.82 │  36.1 │ AMC          │
│ JPM      │ BAC  │    8%    │ 0.75 │  28.5 │ BMO          │
└──────────────────────────────────────────────────────────┘

[ENTER] View Peer Details │ [F]ilter │ [B]ack
```

### Data Source Decision

**Option 1: Database Table** (Recommended)
- Create `arbitrage_scan_results` table
- Morning scanner writes results here
- TUI queries table for display
- Clean, queryable, persistent

**Option 2: Log File Parsing**
- Parse `logs/ei_morning_scan_*.log`
- Extract opportunities from structured log output
- No schema changes needed
- More fragile (log format dependency)

**Option 3: On-Demand Scan**
- Run scanner from TUI when user requests
- Fresh data, no storage needed
- Slow (60+ second scan time)

**Recommendation**: Option 1 with new table schema

### Data Layer
```python
def get_arbitrage_opportunities(self, scan_date: str = None):
    """Get arbitrage scan results for specific date (default: today)"""
    if scan_date is None:
        scan_date = datetime.now().strftime('%Y-%m-%d')

    query = """
    SELECT primary_symbol, peer_symbol, iv_discount_pct,
           correlation_strength, arbitrage_score, arbitrage_quality,
           earnings_time, scan_timestamp
    FROM arbitrage_scan_results
    WHERE DATE(scan_timestamp) = ?
    ORDER BY arbitrage_score DESC
    """
    return self.query(query, (scan_date,))
```

### Key Bindings
- ENTER - View peer details (launches sector sympathy view)
- `F` - Filter by quality (High/Medium/Low)
- `D` - Change date (view historical scan results)
- `R` - Refresh (note: read-only TUI can't trigger scanner)
- ESC - Back to intelligence menu

---

## Phase 8: Trading Journal (Read-Only View) (2-3 hours)

**Goal**: Browse trading notes and observations

**New Screen**: `morning_view/screens/earnings_journal.py`

```
┌─ Earnings Trading Journal (Read-Only) ────────────────────┐
│ Your Recent Trades & Observations                          │
│                                                            │
│ Date  │ Symbol │ Type        │ Sentiment │ Tags           │
├───────┼────────┼─────────────┼───────────┼────────────────┤
│ 10/08 │ TSLA   │ Trade       │ Bullish   │ iv-crush,win   │
│ 10/05 │ AAPL   │ Observation │ Neutral   │ delayed-react  │
│ 10/01 │ NVDA   │ Trade       │ Bullish   │ sympathy,AMD   │
│ 09/28 │ JPM    │ Lesson      │ Bearish   │ breakout,loss  │
└────────────────────────────────────────────────────────────┘

[ENTER] View Full Note │ [F]ilter by Tag │ [S]tats │ [B]ack

Note: Read-only view. Use Admin TUI to add/edit notes.
```

### Detail View (Modal or New Screen)
```
┌─ Journal Entry: NVDA 2025-02-26 ──────────────────────────┐
│ Type: Trade                                                │
│ Sentiment: Bearish                                         │
│ Tags: iv-crush, guidance-miss, sector-sympathy             │
│                                                            │
│ Notes:                                                     │
│ Sold 30DTE straddle. IV at 85%. Stock -5.1%, IV           │
│ crushed to 0.41 (-34%). Winner but AMD sympathy           │
│ selloff (-3.2%) was unexpected. Need to track tech        │
│ correlation better next time.                             │
│                                                            │
│ [ESC] Close                                                │
└────────────────────────────────────────────────────────────┘
```

### Data Layer
```python
def get_trading_journal(self, limit: int = 50, tag_filter: str = None):
    """Get user's trading notes (read-only)"""
    base_query = """
    SELECT ee.earnings_date, ee.symbol, ee.note_type,
           ee.sentiment, ee.tags, ee.notes
    FROM earnings_events ee
    WHERE ee.notes IS NOT NULL
    """

    if tag_filter:
        base_query += " AND ee.tags LIKE ?"
        params = (f"%{tag_filter}%", limit)
    else:
        params = (limit,)

    base_query += " ORDER BY ee.earnings_date DESC LIMIT ?"

    return self.query(base_query, params)
```

### Key Bindings
- ENTER - View full note detail
- `F` - Filter by tag
- `S` - Show stats (note count, win rate if tracked, tag frequency)
- ESC - Back to intelligence menu

---

## Phase 9: Pattern Explorer (3-4 hours)

**Goal**: Discover recurring earnings patterns across symbols

**New Screen**: `morning_view/screens/pattern_explorer.py`

```
┌─ Earnings Pattern Explorer ───────────────────────────────┐
│ Detected Patterns Across 26K+ Historical Earnings         │
│                                                            │
│ Pattern: Delayed Reaction Stocks (32 symbols)             │
│ - Move <5% on earnings day (muted)                        │
│ - Move >8% in days 2-5 (guidance digest)                  │
│ - Examples: AAPL, MSFT, GOOGL                             │
│                                                            │
│ Pattern: Severe IV Crush Candidates (18 symbols)          │
│ - IV collapse >40% post-earnings                          │
│ - Consistent across 80%+ of events                        │
│ - Examples: TSLA, NVDA, AMD                               │
│                                                            │
│ Pattern: Earnings Beat Runners (25 symbols)               │
│ - Move >10% on earnings beat                              │
│ - Historical beat rate >70%                               │
│ - Examples: CRM, SNOW, DDOG                               │
│                                                            │
│ [ENTER] View Pattern Details │ [S]earch Symbol │ [B]ack   │
└────────────────────────────────────────────────────────────┘
```

### Pattern Detection Queries (Complex)

**Delayed Reaction Pattern**:
```sql
-- Symbols with small 1-day moves but large 5-day moves
SELECT symbol,
       AVG(ABS(move_1day_pct)) as avg_1day,
       AVG(ABS(move_5day_pct)) as avg_5day,
       COUNT(*) as sample_size
FROM earnings_moves
WHERE move_1day_pct IS NOT NULL AND move_5day_pct IS NOT NULL
GROUP BY symbol
HAVING avg_1day < 5 AND avg_5day > 8 AND sample_size >= 4
```

**Severe IV Crush Pattern**:
```sql
-- Symbols with consistent severe IV collapse
SELECT symbol,
       AVG(iv_crush_pct) as avg_crush,
       COUNT(*) as sample_size,
       SUM(CASE WHEN iv_crush_severity = 'Severe' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as severe_pct
FROM earnings_moves
WHERE iv_crush_pct IS NOT NULL
GROUP BY symbol
HAVING avg_crush < -40 AND severe_pct > 80 AND sample_size >= 4
```

**Earnings Beat Runners**:
```sql
-- Symbols that run hard on earnings beats
SELECT ee.symbol,
       AVG(ABS(em.move_1day_pct)) as avg_move,
       SUM(CASE WHEN ee.earnings_surprise > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as beat_rate,
       COUNT(*) as sample_size
FROM earnings_events ee
JOIN earnings_moves em ON ee.event_id = em.event_id
WHERE ee.earnings_surprise IS NOT NULL AND em.move_1day_pct IS NOT NULL
GROUP BY ee.symbol
HAVING avg_move > 10 AND beat_rate > 70 AND sample_size >= 4
```

### Key Bindings
- ENTER - View pattern detail (list of symbols + historical examples)
- `S` - Search symbol (check if symbol matches any patterns)
- ESC - Back to intelligence menu

---

## Data Schema Extensions

All queries use **read-only** `datalake_query.db`.

### New Methods in `tui_data.py`

```python
def get_earnings_history(self, symbol: str, limit: int = 8):
    """Get historical earnings for symbol with moves"""
    # (query shown in Phase 4)

def get_sector_sympathy(self, primary_symbol: str):
    """Get peer correlation data for symbol's earnings"""
    # (query shown in Phase 6)

def get_arbitrage_opportunities(self, scan_date: str = None):
    """Get today's arbitrage scan results"""
    # (query shown in Phase 7)

def get_trading_journal(self, limit: int = 50, tag_filter: str = None):
    """Get user's trading notes (read-only)"""
    # (query shown in Phase 8)

def get_pattern_matches(self, pattern_type: str):
    """Get symbols matching specific pattern"""
    # (complex queries shown in Phase 9)
```

---

## UI/UX Considerations

### Navigation Depth
- Level 1: Main Menu
- Level 2: Earnings Intelligence Menu OR Calendar
- Level 3: Specific intelligence screen (scanner, journal, patterns) OR Day Detail
- Level 4: Detail view (full note, pattern detail, symbol detail) OR Symbol Detail
- Level 5: Sector Sympathy (from symbol detail)

**Max depth = 5 levels**, but typical path is 3-4 levels. ESC hierarchy must be clear.

### Key Bindings (Avoid Conflicts)
- `P` - Peers/Sympathy view (from day detail or symbol detail)
- `H` - Historical earnings (from symbol detail)
- `J` - Journal (from intelligence menu)
- `T` - Trends/Patterns (from intelligence menu)
- `A` - Arbitrage scanner (from intelligence menu)
- `F` - Filter (context-dependent)
- `S` - Sort or Search (context-dependent)

### Color Coding Consistency
- Green: Bullish/Buy signals, positive moves
- Red: Bearish/Sell signals, negative moves
- Yellow: Watch/Caution, moderate signals
- Blue: Informational
- Cyan: Selected/Highlighted
- Magenta: High-priority alerts

### Data Freshness Indicators
- Show timestamps on scanner results: "Last updated: 6:32 AM"
- Show sync status: "Data synced: 7:20 AM" (from datalake_query.db)
- Auto-refresh buttons where appropriate (but note: read-only TUI can't trigger scans)

---

## Implementation Timeline

**Total Estimated Time**: 14-18 hours

| Phase | Component | Hours | Priority |
|-------|-----------|-------|----------|
| 4 | Enhanced Symbol Detail | 3-4 | HIGH |
| 5 | Intelligence Menu | 2 | HIGH |
| 6 | Sector Sympathy View | 2-3 | HIGH |
| 7 | Arbitrage Scanner | 2 | MEDIUM |
| 8 | Trading Journal (read-only) | 2-3 | MEDIUM |
| 9 | Pattern Explorer | 3-4 | LOW |

**Suggested Approach**:
1. Start with Phases 4-6 (core intelligence features) - ~8 hours
2. Validate user engagement and value
3. Add Phases 7-9 if demand is high

---

## Testing Plan

### Phase 4 Tests (Enhanced Symbol Detail)
- ✓ Symbol detail shows earnings history
- ✓ Correct calculation of avg/median moves
- ✓ Pattern detection messaging works
- ✓ Handles symbols with no earnings history

### Phase 5 Tests (Intelligence Menu)
- ✓ Menu displays correctly
- ✓ All menu options navigate to correct screens
- ✓ Stats display accurate counts

### Phase 6 Tests (Sector Sympathy)
- ✓ Sympathy view loads peers correctly
- ✓ Correlation strength sorting works
- ✓ IV arbitrage delta calculated properly
- ✓ Handles symbols with no peers gracefully

### Phase 7 Tests (Arbitrage Scanner)
- ✓ Scan results display correctly
- ✓ Quality scoring visible and accurate
- ✓ Filter by quality works
- ✓ Handles days with no opportunities

### Phase 8 Tests (Trading Journal)
- ✓ Journal browse view loads notes
- ✓ Detail view shows full note content
- ✓ Tag filtering works correctly
- ✓ Stats calculation accurate

### Phase 9 Tests (Pattern Explorer)
- ✓ Pattern queries return correct symbols
- ✓ Pattern detail shows historical examples
- ✓ Symbol search finds matching patterns
- ✓ Handles symbols with no pattern matches

---

## Database Dependencies

### Required Tables
- `earnings_events` - Historical earnings with journal fields
- `earnings_moves` - Price moves and IV changes
- `earnings_sector_effects` - Sector sympathy and arbitrage
- `earnings_snapshots` - IV/price time series
- `industry_peer_mappings` - Peer relationships
- `arbitrage_scan_results` - **NEW** (see EARNINGS_ADMIN_TUI_PLAN.md for schema)

### Data Quality Requirements
- Earnings history: Need 4+ events per symbol for pattern detection
- Sector sympathy: Need 8+ sample events for correlation confidence
- Arbitrage: Need current-day IV data for discount calculation

---

## Future Enhancements (Beyond Phase 9)

### Multi-Symbol Comparison
- Compare earnings history for 2-3 symbols side-by-side
- Useful for peer analysis

### Watchlist Integration
- Flag symbols on your watchlist that have earnings soon
- Show sympathy peers of watchlist symbols

### Correlation Heatmap
- Visual heatmap of sector correlation strength
- Identify strongest sympathy clusters

### Alerts Integration
- "NVDA earnings tomorrow - AMD has -12% IV discount (HIGH arbitrage)"
- Push notifications or daily email digest

---

**Last Updated**: 2025-10-11
**Status**: Planning phase, ready for prioritization
**Dependencies**: Earnings Intelligence System (strategies/earnings_intel/)
**Database**: Read-only `datalake_query.db`
**Estimated Total Time**: 14-18 hours
