# PRD: Morning View Watchlist Redesign - Phase 1

**Status**: Approved for Implementation
**Created**: 2025-10-09
**Author**: Ben (with Claude Code)
**Target Completion**: Session-based (1-2 days)

---

## Introduction/Overview

The current Morning View watchlist system has fundamental limitations that reduce its effectiveness as a daily trading discovery tool:

1. **Opaque Scoring**: Symbols ranked by `confluence_score` (0-5 integer) calculated on-the-fly, but users can't see WHY a symbol scored what it did
2. **Arbitrary Cutoff**: Hard limit of 20 symbols means potentially valuable opportunities are hidden
3. **No Persistence**: Watchlist regenerates daily - symbols disappear without user control
4. **Limited Discoverability**: Can only search symbols already meeting filter criteria

This redesign transforms the watchlist from a **passive filtered list** into a **two-tier discovery system**:
- **Discovery Screen** (Tier 1): System-generated feed of ALL symbols meeting triggers (not capped at 20)
- **My Watchlist** (Tier 2): User-curated persistent tracking list with activity monitoring

**Problem Statement**: Users need a way to discover symbols with unusual activity while maintaining persistent focus on symbols they're actively tracking, without arbitrary limits hiding opportunities.

---

## Goals

### Primary Goals
1. **Transparency**: Users see explicit trigger tags (🚨 FLOW_ALERT, 📅 EARNINGS_PLAY) instead of opaque scores
2. **Completeness**: Discovery screen shows ALL symbols meeting ANY trigger (no 20-symbol limit)
3. **Persistence**: User watchlist survives across TUI restarts and daily data refreshes
4. **Temporal Awareness**: New activity surfaces at top of Discovery screen, older activity drifts down naturally
5. **User Control**: Users manually curate their watchlist, adding/removing symbols as needed

### Secondary Goals
6. Keep existing symbol detail views (OI Timing, Distribution, Compare Strikes, AI Council) fully functional
7. Maintain backward compatibility with existing database schema (additive changes only)
8. Preserve performance (views should load in <1 second)

---

## User Stories

### Discovery Workflow
**As a trader**, I want to see all symbols with unusual activity each morning, sorted by recency and magnitude, so I can quickly identify new opportunities without missing anything due to arbitrary limits.

**Acceptance Criteria**:
- Discovery screen shows 40-100+ symbols (whatever meets triggers)
- New alerts (today) appear at top
- Symbols with expired alerts disappear automatically
- Can scroll through full list and drill into any symbol

---

### Persistent Tracking
**As a trader**, I want to manually add symbols to a watchlist that persists across sessions, so I can maintain focus on opportunities I'm actively tracking without re-finding them daily.

**Acceptance Criteria**:
- Can add symbol from Discovery screen (ENTER → W key)
- Watchlist persists when TUI is closed/reopened
- Watchlist persists when morning data pipeline refreshes
- Can remove symbol with confirmation (X → Y/N)

---

### Activity Monitoring
**As a trader**, I want to see when symbols on my watchlist have new activity, so I know which tracked positions need immediate attention.

**Acceptance Criteria**:
- My Watchlist shows 🆕 badge when symbol has new alerts today
- Can see which triggers are currently active vs. expired
- Symbols on My Watchlist are hidden from Discovery (reduce duplicate noise)

---

### Temporal Discovery
**As a trader**, I want the Discovery screen to prioritize symbols with recent activity, so I see the "freshest" opportunities first and older activity naturally drifts down.

**Acceptance Criteria**:
- Symbols with new alerts today (new_alert_count > 0) appear at top
- Secondary sort by total active alerts (active_alert_count)
- Tertiary sort by earnings opportunity magnitude (move_difference_pct)
- Final tiebreaker: days_since_last_alert (ascending)

---

## Functional Requirements

### FR1: Database Schema - User Watchlist Table
**Requirement**: Create `user_watchlist` table to store persistent user symbol selections.

**Schema**:
```sql
CREATE TABLE user_watchlist (
    symbol TEXT PRIMARY KEY,
    added_date TEXT NOT NULL,
    added_reason TEXT,  -- Which trigger(s) prompted the add
    user_notes TEXT,    -- Freeform notes (future enhancement)
    priority INTEGER DEFAULT 0,  -- User-set priority (future enhancement)
    removed_date TEXT,  -- NULL while active, set when removed (keeps history)
    FOREIGN KEY (symbol) REFERENCES symbol_metadata(symbol)
);

CREATE INDEX idx_watchlist_active ON user_watchlist(removed_date);
```

**Behavior**:
- One row per symbol
- `removed_date = NULL` means symbol is active on watchlist
- Setting `removed_date` soft-deletes (preserves history)
- `added_reason` captures trigger context at time of add (e.g., "FLOW_ALERT + EARNINGS_PLAY")

---

### FR2: Database View - v_morning_discovery
**Requirement**: Replace `v_morning_watchlist` with new `v_morning_discovery` view that calculates explicit trigger flags and sorts by temporal relevance.

**Trigger Logic**:
- `trigger_flow_alert` = 1 if `active_alert_count > 0` (from `options_symbol_summary` table)
- `trigger_earnings_play` = 1 if `earnings_upcoming.earnings_alert = 1`

**Implementation Pattern**: Use CTE (Common Table Expression) to calculate triggers, then filter:
```sql
CREATE VIEW v_morning_discovery AS
WITH triggers AS (
    SELECT
        s.symbol,
        s.close_price,
        s.active_alert_count,
        s.new_alert_count,
        s.days_since_last_alert,
        -- Trigger flags
        CASE WHEN s.active_alert_count > 0 THEN 1 ELSE 0 END as trigger_flow_alert,
        CASE WHEN e.earnings_alert = 1 THEN 1 ELSE 0 END as trigger_earnings_play,
        e.move_difference_pct,
        -- ... all other context fields
    FROM options_symbol_summary s
    LEFT JOIN earnings_upcoming e ON s.symbol = e.symbol
    WHERE
        s.trade_date = (SELECT MAX(trade_date) FROM options_symbol_summary)
        AND s.close_price < 60  -- Price filter
        AND s.total_open_interest > 500  -- Liquidity filter
        -- Exclude ETFs (if symbol_metadata available)
)
SELECT * FROM triggers
WHERE trigger_flow_alert = 1 OR trigger_earnings_play = 1
ORDER BY
    new_alert_count DESC,        -- New alerts today = top priority
    active_alert_count DESC,     -- Total alert count = secondary
    move_difference_pct DESC,    -- Earnings opportunity magnitude
    days_since_last_alert ASC    -- Recency (0 days = most recent)
;
```

**Note for Future Enhancement**: Phase 2+ will migrate to materialized `morning_view_triggers` table for:
- Faster query performance
- Historical trigger tracking
- Flexible trigger expansion

---

### FR3: TUI Discovery Screen
**Requirement**: Replace current Watchlist screen with Discovery screen showing all triggered symbols.

**Navigation**:
- Main Menu → [1] Discovery
- Arrow keys to navigate symbol list
- ENTER to drill into Symbol Detail screen
- From Symbol Detail: press W to add to My Watchlist

**Display Format**:
```
═══ SYMBOL DISCOVERY - 2025-10-09 ═══
Market: BULLISH | Regime: normal_volatility | Symbols: 47

[#]  Symbol  Triggers  Alerts  Price   Context
──────────────────────────────────────────────────────────
1    TSLA    🚨📅      2 NEW   $245    Earnings 4d, 2 alerts today
2    NVDA    🚨        1 NEW   $520    1 alert today
3    AAL     📅        -       $11     Earnings 2d, 15% exp move
4    PLTR    🚨        5       $38     Last alert 1d ago
...

[↑↓: Navigate] [Enter: Detail] [R: Refresh] [ESC: Back]
```

**Symbols Hidden from Discovery**:
- Symbols already on My Watchlist (to reduce noise)
- Rationale: Discovery = "what should I look at?", Watchlist = "what I'm already watching"

---

### FR4: TUI My Watchlist Screen
**Requirement**: Create new persistent watchlist screen with manual add/remove controls.

**Navigation**:
- Main Menu → [2] My Watchlist
- Arrow keys to navigate
- ENTER to drill into Symbol Detail
- X to remove symbol (Y/N confirmation)
- S to toggle sort mode

**Display Format**:
```
═══ MY WATCHLIST (8 symbols) ═══

Symbol  Triggers  Price   Added       Notes
────────────────────────────────────────────────────────
TSLA    🚨📅 🆕   $245    2025-01-08  (2 new alerts today!)
AAL     ✈️📅      $11     2025-01-05  Airline earnings play
PLTR    📊        $38     2024-12-20  OI build pattern
AAPL    -         $182    2024-11-15  ⚠️ Stale (25 days)

[Enter: Detail] [X: Remove] [S: Sort] [ESC: Back]
```

**Sort Modes** (cycle with S key):
1. **Relevance** (default): `(new_alert_count * 3) + (active_alert_count * 2) + move_difference_pct`
2. **Date Added** (newest first)
3. **Alphabetical**

**🆕 Badge Logic**:
- Show 🆕 next to symbol if `new_alert_count > 0`
- Show count in parentheses: "(2 new alerts today!)"

**⚠️ Stale Warning**:
- Show if `days_since_last_alert > 25` OR `active_alert_count = 0`
- Format: "⚠️ Stale (25 days)" or "⚠️ Stale (no active triggers)"

---

### FR5: Add to Watchlist Workflow
**Requirement**: Users can add symbols to watchlist from Symbol Detail screen.

**User Flow**:
1. From Discovery screen → ENTER on symbol → Symbol Detail opens
2. In Symbol Detail → Press W key
3. Confirmation prompt appears: "Add TSLA to My Watchlist? [Y/N]"
4. Press Y → Symbol added with:
   - `added_date` = current date
   - `added_reason` = active trigger tags ("FLOW_ALERT + EARNINGS_PLAY")
   - `removed_date` = NULL
5. Notification: "✅ TSLA added to My Watchlist"

---

### FR6: Remove from Watchlist Workflow
**Requirement**: Users can remove symbols from My Watchlist screen.

**User Flow**:
1. From My Watchlist → Arrow keys to select symbol
2. Press X key
3. Confirmation prompt: "Remove TSLA from watchlist? [Y/N]"
4. Press Y → `removed_date` set to current date (soft delete)
5. Notification: "✅ TSLA removed from My Watchlist"

---

### FR7: Preserve Existing Symbol Detail Views
**Requirement**: All existing Symbol Detail sub-screens remain fully functional.

**No Changes Required**:
- OI Timing Analysis screen
- OI Distribution screen
- Compare Strikes screen
- AI Council screen
- Confluence Score breakdown (C key toggle)

**Minor Change**: Add watchlist status indicator to Symbol Detail header:
```
═══ TSLA - Symbol Detail ═══
Technology - Auto Manufacturers
Price: $245.00 | 5d Change: +3.2%
★ On My Watchlist | Press W to remove
```

---

## Non-Goals (Out of Scope for Phase 1)

### Explicitly NOT Included
1. **Materialized Trigger Table**: Phase 1 uses CTE pattern for simplicity. Trigger table migration deferred to Phase 2.
2. **Advanced Discovery Score Formula**: Phase 1 uses multi-column sort. Composite "Discovery Score" deferred to Phase 2.
3. **Trigger History Tracking**: "When did TSLA fire FLOW_ALERT?" requires trigger table. Deferred to Phase 2.
4. **Additional Triggers**: Phase 1 only implements FLOW_ALERT + EARNINGS_PLAY. OI_BUILD, AIRLINE_PLAY, NEWS_CATALYST deferred to Phase 2.
5. **Stale Symbol Cleanup Prompts**: "You have 5 stale symbols, review now?" deferred to Phase 3.
6. **User Notes on Watchlist**: `user_notes` column exists but UI for editing deferred to Phase 3.
7. **Priority Sorting**: `priority` column exists but UI for setting deferred to Phase 3.
8. **Search Integration**: Existing search screen remains unchanged in Phase 1.

---

## Design Considerations

### UI/UX Design
**Visual Indicators**:
- 🚨 = FLOW_ALERT trigger
- 📅 = EARNINGS_PLAY trigger
- 🆕 = New activity today
- ⚠️ = Stale (no recent activity)

**Color Coding** (using existing Textual CSS):
- Green = bullish bias, new activity
- Red = bearish bias
- Yellow = warnings, moderate alerts
- Dim = stale/inactive

**Navigation Consistency**:
- Main Menu: [1] Discovery, [2] My Watchlist, [3] Search (unchanged)
- All screens: ESC = back, ? = help, R = refresh
- Discovery/Watchlist: ENTER = drill down
- Symbol Detail: Number keys = sub-views, W = add/remove watchlist

---

### Database Performance
**View Query Optimization**:
- CTE pattern avoids duplicate CASE logic
- Indexes already exist on `options_symbol_summary(trade_date, symbol)`
- JOIN to `earnings_upcoming` is LEFT JOIN (safe if missing data)
- Expected query time: <500ms for 800 symbols

**Watchlist Table Performance**:
- Primary key on `symbol` = instant lookups
- Index on `removed_date` = fast filtering of active watchlist
- Expected watchlist size: 5-30 symbols (trivial performance impact)

---

## Technical Considerations

### Data Dependencies
**Required Tables** (must exist and be populated):
- `options_symbol_summary` - populated by Flow Monitor daily rollup
  - Must have columns: `active_alert_count`, `new_alert_count`, `days_since_last_alert`
  - Verified in `strategies/flow_monitor/fm_symbol_rollup.py` (lines 651-710)
- `earnings_upcoming` - populated by earnings calendar pipeline
  - Must have column: `earnings_alert` (BOOLEAN)
- `symbol_metadata` - for ETF filtering (optional in Phase 1)

**Database**:
- Target: `data/datalake_query.db` (read-only for TUI)
- User watchlist writes: Consider using `datalake.db` OR add sync mechanism

### Backward Compatibility
**No Breaking Changes**:
- `v_morning_watchlist` renamed to `v_morning_discovery` (new view, old view can remain)
- All existing TUI screens preserved
- New `user_watchlist` table is additive (no schema modifications to existing tables)

**Migration Path**:
- Existing TUI users: No migration needed, just see new screens
- Existing watchlist behavior: Replaced by Discovery screen, but functionally similar

### Data Sync Strategy
**Challenge**: TUI operates on `datalake_query.db` (read-only), but needs to write watchlist changes.

**Options**:
1. **Write to query DB, sync to primary**: Breaks read-only pattern (not ideal)
2. **Write to primary DB directly**: Requires TUI to connect to `datalake.db` for watchlist operations only
3. **Separate watchlist DB**: Create `watchlist.db` for user data only

**Recommended Approach**: Option 2 - TUI uses dual connection pattern:
- Read-only connection to `datalake_query.db` for all market data queries
- Read-write connection to `datalake.db` ONLY for `user_watchlist` operations
- Rationale: Watchlist writes are infrequent (1-5/day), no lock contention with pipelines

---

## Success Metrics

### Phase 1 Success Criteria
**Week 1 Completion Checklist**:
- [x] Discovery screen shows symbols with triggers (40-100 symbols typical)
- [x] Can add symbols to My Watchlist from Symbol Detail (W key)
- [x] Watchlist persists across TUI restarts
- [x] Can remove symbols from My Watchlist (X key → Y/N confirm)
- [x] Trigger flags visible in Discovery (🚨 🚨 emojis or text labels)
- [x] All existing symbol detail views still work (OI Timing, Distribution, etc.)

### User Experience Validation
**Qualitative Metrics**:
- User can browse full Discovery list without feeling "something is missing"
- User finds new opportunities not visible in old 20-symbol limit
- User can track 5-10 symbols persistently without re-finding daily
- New activity (🆕 badge) is immediately obvious at a glance

**Performance Benchmarks**:
- Discovery view loads in <1 second
- My Watchlist loads in <100ms
- Add/remove operations complete instantly (<200ms)

---

## Open Questions

### Resolved (Answered in Design Session)
1. ✅ **Trigger thresholds**: Use `active_alert_count > 0` for FLOW_ALERT, `earnings_alert = 1` for EARNINGS_PLAY
2. ✅ **Add/remove UX**: ENTER → Symbol Detail → W to add, X → Y/N to remove from watchlist
3. ✅ **Discovery sorting**: Multi-level: new_alert_count → active_alert_count → move_difference_pct → days_since_last_alert
4. ✅ **Hide watchlist symbols from Discovery**: Yes, to reduce noise
5. ✅ **My Watchlist default sort**: Relevance score (default), toggle with S key
6. ✅ **Discovery default view**: Show all symbols (no grouping), scroll to browse
7. ✅ **SQL view pattern**: Use CTE (Option 1), note future trigger table migration (Option 3)

### Remaining (To Decide During Implementation)
1. **Dual-DB write strategy**: Confirm user_watchlist writes to `datalake.db` directly (need to test lock behavior)
2. **Search screen integration**: Should search also allow adding to watchlist? (Defer to Phase 2 if complex)
3. **Confluence score**: Keep as hidden field for backward compatibility, or remove entirely?

---

## Implementation Notes

### Phase 1 Scope Boundaries
**What We're Building**:
- Core two-tier discovery system
- Persistent watchlist with add/remove
- Temporal sorting with new activity badges
- Two triggers: FLOW_ALERT + EARNINGS_PLAY

**What We're NOT Building Yet**:
- Trigger history ("when did this trigger fire?")
- Additional triggers (OI_BUILD, AIRLINE_PLAY, etc.)
- User notes/priority UI
- Advanced discovery scoring
- Stale symbol cleanup automation

### Testing Plan
**Manual Testing Checklist**:
1. Verify Discovery shows symbols with `active_alert_count > 0`
2. Verify Discovery shows symbols with `earnings_alert = 1`
3. Add 3 symbols to watchlist, close TUI, reopen → verify persistence
4. Remove symbol from watchlist → verify soft delete (removed_date set)
5. Add symbol with 2 new alerts → verify 🆕 badge appears
6. Drill into symbol from Discovery → verify OI Timing/Distribution/AI views still work
7. Refresh data (R key) → verify Discovery updates with new symbols

**Edge Cases**:
- Symbol has 0 active alerts but earnings_alert=1 → should appear in Discovery
- Symbol on watchlist loses all triggers → should show ⚠️ Stale warning
- No symbols meet triggers → Discovery shows "No symbols meeting triggers today"
- User tries to add symbol already on watchlist → show warning "Already on watchlist"

---

## Appendix: Key File Locations

**Database Views**:
- Current: `morning_view/morning_views.py` (contains view creation logic)
- New view: `v_morning_discovery` (replaces `v_morning_watchlist`)

**TUI Screens**:
- Main entry: `morning_view/mv_main.py`
- Current watchlist: `WatchlistScreen` class (line 134)
- New Discovery screen: Modify `WatchlistScreen` → rename to `DiscoveryScreen`
- New My Watchlist: Create `MyWatchlistScreen` class

**Data Layer**:
- Query functions: `morning_view/tui_data.py`
- New functions: `get_discovery()`, `get_my_watchlist()`, `add_to_watchlist()`, `remove_from_watchlist()`

**Alert Counts**:
- Populated by: `strategies/flow_monitor/fm_symbol_rollup.py` (lines 651-710)
- Function: `_get_alert_counts()` → returns active_alert_count, new_alert_count, days_since_last_alert

---

**End of PRD**
