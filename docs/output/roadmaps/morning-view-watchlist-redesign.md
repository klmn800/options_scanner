# Morning View Watchlist Redesign

**Status**: Design Phase
**Created**: 2025-01-10
**Target**: Incremental implementation starting 2025-01-11

---

## The Problem

### Current System Limitations

The existing `v_morning_watchlist` view has fundamental architectural issues:

1. **Opaque Scoring**: Symbols ranked by `confluence_score` (0-5 integer), but:
   - Score not stored, calculated on-the-fly
   - Users can't see WHY a symbol scored what it did
   - Tie-breaking uses only `active_alerts_count`, ignoring other important factors

2. **Arbitrary Cutoff**: Hard limit of 20 symbols
   - If 30 symbols have `confluence_score=3`, only top 15-20 make the list
   - Is symbol #20 really more valuable than #21? Often not.

3. **No Persistence**: Watchlist regenerates daily
   - If user is tracking a symbol, it might disappear tomorrow
   - No way to manually add/prioritize symbols

4. **Limited Search**: Can only search symbols already on watchlist
   - If symbol doesn't meet filter criteria (price > $60, OI < 500), unreachable
   - Can't proactively add symbols user cares about

5. **Trigger-Last Design**: Filters first, scores second
   - Old system used trigger-first: "Does this meet FLOW_ALERT? Add it."
   - Current system: "Calculate score, rank, cut at 20"
   - Trigger-first is more transparent and actionable

---

## The Vision: Two-Tier Watchlist System

### Tier 1: "Big List" (Discovery)
**Purpose**: System-generated daily discovery feed
**Behavior**: Read-only, ephemeral, regenerates each morning

**Characteristics**:
- Shows ALL symbols meeting ANY trigger (no arbitrary limit)
- Explicit trigger tags visible at a glance
- Grouped/sorted by trigger type and strength
- User browses, then manually promotes to "My Watchlist"

**Example Display**:
```
═══ SYMBOL DISCOVERY - 2025-01-10 ═══
Market: BULLISH | Regime: normal_volatility

🚨 FLOW ALERTS (12 symbols)
  TSLA  $245  🚨 FLOW_ALERT + 📅 EARNINGS_PLAY
  NVDA  $520  🚨 FLOW_ALERT + 📈 VOL_SURGE
  AMD   $135  🚨 FLOW_ALERT

📅 EARNINGS PLAYS (8 symbols)
  AAL   $11   📅 EARNINGS_PLAY (2d ahead, 15% exp move)
  DAL   $45   📅 EARNINGS_PLAY (4d ahead, 12% exp move)

✈️ AIRLINE PLAYS (2 symbols)
  DAL   $45   ✈️ AIRLINE_PLAY + 📅 EARNINGS_PLAY
  AAL   $11   ✈️ AIRLINE_PLAY + 📅 EARNINGS_PLAY

📊 OI MOMENTUM (5 symbols)
  PLTR  $38   📊 OI_BUILD (5-day build, +850 contracts)
```

### Tier 2: "My Watchlist" (Active Tracking)
**Purpose**: User-curated list of symbols actively tracking
**Behavior**: Persistent, manual add/remove only

**Characteristics**:
- User explicitly adds symbols from Big List (or manually)
- Stays on watchlist until user removes it
- Shows which triggers are currently active (for context)
- Flags "stale" symbols (no active triggers for 7+ days)

**Example Display**:
```
═══ MY WATCHLIST (8 symbols) ═══

TSLA   $245  Active: 🚨 FLOW + 📅 EARNINGS    Added: 2025-01-08
AAL    $11   Active: ✈️ AIRLINE + 📅 EARNINGS Added: 2025-01-05
PLTR   $38   Active: 📊 OI_BUILD              Added: 2024-12-20
AAPL   $182  Active: (none)                   Added: 2024-11-15  ⚠️ Stale (25d)

[Enter: View details] [D: Remove] [B: Back to Discovery]
```

---

## Trigger System Design

### Core Philosophy
**Trigger-First, Filter-Second**:
1. Check if symbol meets any trigger → Add to Big List with explicit reason(s)
2. Apply hard filters (price < $60, OI > 500, not ETF)
3. Display all survivors, sorted by trigger count and strength

### Trigger Definitions

#### ✅ Ready Now (Existing Data)

**1. 🚨 FLOW_ALERT**
- **Source**: `flow_alerts` table
- **Logic**: `active_alerts_count > 0` in last 7 days
- **Status**: ✅ Already calculated in view, just needs explicit flag

**3. 📅 EARNINGS_PLAY**
- **Source**: `earnings_upcoming` table
- **Logic**: `earnings_alert = 1` (set when promising exp vs hist move detected)
- **Status**: ⚠️ Column exists, but only 1/506 symbols have it set (needs tuning)
- **Context Display**: Still show upcoming earnings for ALL symbols when near (1-30d) for context

#### ⚠️ Need Development

**2. 📊 OI_BUILD (OI Delta Momentum)**
- **Purpose**: Detect gradual institutional position building
- **Logic**: Multi-day OI increases showing accumulation pattern
- **Candidates**:
  - OI increasing 5+ consecutive days
  - Steady build without big spikes (avoids flow alert overlap)
  - Rising OI while price flat/slightly down (predictive positioning)
- **Implementation**: New calculation logic, add `oi_momentum_trigger` flag

**4. ✈️ AIRLINE_PLAY**
- **Purpose**: Trigger DAL, AAL 14 days before month's 10th
- **Logic**: Hardcoded strategy for specific symbols + date window
- **Implementation**:
  - Option A: Custom column `airline_play_trigger` in triggers table
  - Option B: Generic "date-triggered strategies" system
- **Symbols**: DAL, AAL (UAL too expensive, >$60)

**5. 📰 NEWS_CATALYST (Future)**
- **Purpose**: Identify symbols with strong news momentum
- **Status**: Speculative, needs design work
- **Current Data**: `news_symbol_sentiment` table exists, avg sentiment calculated
- **Gap**: Need better threshold logic, possibly trending analysis

**6. 🔄 SECTOR_ROTATION (Future - February)**
- **Purpose**: Identify sectors/industries with increased momentum
- **Status**: Design phase, target next month
- **Approach**: Detect sector strength, recommend symbols within hot sectors

---

## Database Schema Changes

### 1. Central Triggers Table
**Purpose**: Store all symbol triggers, allows flexible trigger management

```sql
CREATE TABLE morning_view_triggers (
    symbol TEXT NOT NULL,
    trigger_date TEXT NOT NULL,
    trigger_type TEXT NOT NULL,  -- 'FLOW_ALERT', 'OI_BUILD', 'EARNINGS_PLAY', etc.
    trigger_active INTEGER DEFAULT 1,  -- 1=active, 0=expired
    trigger_strength REAL,  -- Optional: magnitude (e.g., 2.3x volume surge, 15% exp move)
    trigger_details TEXT,  -- Optional: JSON with specifics
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, trigger_date, trigger_type)
);

CREATE INDEX idx_triggers_active ON morning_view_triggers(symbol, trigger_active);
CREATE INDEX idx_triggers_type ON morning_view_triggers(trigger_type, trigger_active);
CREATE INDEX idx_triggers_date ON morning_view_triggers(trigger_date);
```

**Rationale**:
- Central source of truth for all triggers
- Allows historical tracking ("when did this trigger fire?")
- Flexible: new trigger types added without schema changes
- Can be populated by multiple strategies (Flow Monitor, OID, earnings scanner, etc.)

### 2. User Watchlist Table
**Purpose**: Persistent user-curated watchlist

```sql
CREATE TABLE user_watchlist (
    symbol TEXT PRIMARY KEY,
    added_date TEXT NOT NULL,
    added_reason TEXT,  -- Which trigger(s) prompted the add
    user_notes TEXT,  -- Freeform notes
    priority INTEGER DEFAULT 0,  -- Optional: user-set priority (0=normal, 1=high, etc.)
    removed_date TEXT,  -- NULL while active, set when removed (keeps history)
    FOREIGN KEY (symbol) REFERENCES symbol_metadata(symbol)
);

CREATE INDEX idx_watchlist_active ON user_watchlist(removed_date);
```

**Rationale**:
- Stores user's active tracking list
- `removed_date` allows historical tracking without deleting rows
- `added_reason` captures trigger context at time of add

### 3. Updated v_morning_watchlist View
**Purpose**: Generate Big List with explicit trigger flags

```sql
CREATE VIEW v_morning_discovery AS
SELECT
    s_today.symbol,
    s_yesterday.close_price,

    -- TRIGGER FLAGS (explicit boolean indicators)
    CASE WHEN (SELECT COUNT(*) FROM flow_alerts fa
               WHERE fa.symbol = s_today.symbol
               AND fa.evaluation_status = 'active'
               AND DATE(fa.alert_timestamp) >= DATE('now', '-7 days')) > 0
    THEN 1 ELSE 0 END as trigger_flow_alert,

    CASE WHEN e.earnings_alert = 1
         AND e.earnings_days_ahead BETWEEN 1 AND 30
    THEN 1 ELSE 0 END as trigger_earnings_play,

    CASE WHEN s_yesterday.option_volume > (SELECT AVG(s2.option_volume) * 1.5
                                          FROM oi_symbol_summary s2
                                          WHERE s2.symbol = s_yesterday.symbol
                                          AND s2.trade_date BETWEEN DATE(s_yesterday.trade_date, '-20 days')
                                                                AND DATE(s_yesterday.trade_date, '-1 days'))
    THEN 1 ELSE 0 END as trigger_volume_surge,

    CASE WHEN s_today.top_call_pct_of_total > 30 OR s_today.top_put_pct_of_total > 30
    THEN 1 ELSE 0 END as trigger_oi_conviction,

    -- TODO: Add trigger_oi_build when logic developed
    -- TODO: Add trigger_airline_play when logic developed

    -- TRIGGER COUNT (for sorting)
    (
        CASE WHEN (SELECT COUNT(*) FROM flow_alerts...) > 0 THEN 1 ELSE 0 END +
        CASE WHEN e.earnings_alert = 1... THEN 1 ELSE 0 END +
        CASE WHEN s_yesterday.option_volume > ... THEN 1 ELSE 0 END +
        CASE WHEN s_today.top_call_pct_of_total > 30... THEN 1 ELSE 0 END
    ) as trigger_count,

    -- LEGACY SCORE (keep for now, phase out later)
    confluence_score,

    -- ALL EXISTING FIELDS (price, OI, earnings, greeks, etc.)
    ...

FROM oi_symbol_summary s_today
JOIN oi_symbol_summary s_yesterday ON ...
JOIN symbol_metadata meta ON ...
LEFT JOIN earnings_upcoming e ON ...

WHERE
    s_today.trade_date = (SELECT MAX(trade_date) FROM oi_symbol_summary)
    AND s_yesterday.close_price < 60  -- Filter: price
    AND s_today.total_open_interest > 500  -- Filter: OI
    AND meta.is_etf = 0  -- Filter: no ETFs
    AND (
        trigger_flow_alert = 1 OR
        trigger_earnings_play = 1 OR
        trigger_volume_surge = 1 OR
        trigger_oi_conviction = 1
        -- Add more triggers as developed
    )

ORDER BY
    trigger_count DESC,  -- Most triggers first
    e.earnings_days_ahead ASC NULLS LAST,  -- Closer earnings prioritized
    s_yesterday.option_volume / AVG_20d DESC,  -- Volume surge magnitude
    active_alerts_count DESC  -- Tiebreaker
;
```

**Key Changes**:
- Explicit trigger flags (`trigger_flow_alert`, etc.)
- `trigger_count` for sorting
- WHERE clause requires ≥1 trigger (no arbitrary limit)
- Multi-level sorting: trigger_count → earnings proximity → volume magnitude
- Removes LIMIT 20

---

## UI Changes (TUI)

### New Screens

**1. Discovery Screen (replaces current Watchlist)**
```
═══ SYMBOL DISCOVERY ═══
[F: Filter by trigger] [S: Sort] [Enter: Add to watchlist]

🚨 FLOW ALERTS (12)
☑ TSLA  $245  🚨📅📊  Score: 3  [2 alerts, earn 4d, OI build]
  NVDA  $520  🚨📈     Score: 2  [1 alert, 2.3x vol surge]

📅 EARNINGS PLAYS (8)
  AAL   $11   📅✈️     Score: 2  [earn 2d, airline window]

[Space: Select] [A: Add selected] [M: My Watchlist] [ESC: Back]
```

**2. My Watchlist Screen (new)**
```
═══ MY WATCHLIST (8 symbols) ═══

TSLA   $245  🚨📅  Added: 2025-01-08  Active triggers
AAL    $11   ✈️📅  Added: 2025-01-05  Active triggers
PLTR   $38   📊    Added: 2024-12-20  Active triggers
AAPL   $182  -     Added: 2024-11-15  ⚠️ Stale (25 days)

[Enter: Details] [D: Remove] [N: Add note] [B: Discovery]
```

**3. Symbol Detail (enhanced)**
- Show ALL active triggers for symbol
- Show trigger history (when each fired)
- Add to/Remove from My Watchlist button

### Navigation Flow
```
Main Menu
├─ [1] Discovery (Big List)
│   ├─ [Space] Select symbols
│   ├─ [A] Add selected to My Watchlist
│   ├─ [Enter] Symbol detail → Add to watchlist
│   └─ [M] Jump to My Watchlist
│
├─ [2] My Watchlist
│   ├─ [Enter] Symbol detail
│   ├─ [D] Remove from watchlist
│   └─ [B] Back to Discovery
│
└─ [3] Search (unchanged)
```

---

## Implementation Phases

### Phase 1: Infrastructure (Week 1)
**Goal**: Get two-tier system working with existing triggers

**Tasks**:
1. Create `user_watchlist` table
2. Create `morning_view_triggers` table
3. Modify `v_morning_watchlist` → `v_morning_discovery` with trigger flags
4. Add Discovery screen to TUI
5. Add My Watchlist screen to TUI
6. Add/remove functionality

**Deliverable**: Can browse Big List, manually add to My Watchlist, persist across sessions

### Phase 2: Trigger Expansion (Week 2)
**Goal**: Add missing triggers, improve existing ones

**Tasks**:
1. Tune `earnings_alert` logic (fix 1/506 problem)
2. Develop OI Build detection logic
3. Implement Airline Play trigger (DAL, AAL date logic)
4. Add trigger management functions (populate `morning_view_triggers`)

**Deliverable**: Big List populates with 4-5 working triggers

### Phase 3: Refinement (Week 3)
**Goal**: Polish UX, add advanced features

**Tasks**:
1. Trigger filtering in Discovery screen
2. Sorting options (by trigger type, strength, date)
3. Trigger history view (when did TSLA fire FLOW_ALERT?)
4. Stale watchlist detection/cleanup prompts
5. User notes on watchlist items

**Deliverable**: Production-ready two-tier system

### Phase 4: Future Triggers (February+)
**Goal**: Add sophisticated triggers

**Tasks**:
1. News Catalyst trigger (design + implementation)
2. Sector Rotation trigger (design + implementation)
3. Technical breakout triggers (if desired)

---

## Open Questions

### To Decide Tomorrow

1. **Trigger Storage Strategy**:
   - Option A: Populate `morning_view_triggers` table daily (via cron/scheduler)
   - Option B: Calculate triggers on-the-fly in view (current approach)
   - Recommendation: Hybrid - store in table for history, recalculate daily

2. **My Watchlist Size Limit**:
   - Should we cap it? (e.g., max 50 symbols)
   - Or let user manage unbounded?
   - Recommendation: No hard limit, but warn if >30 ("hard to track this many")

3. **Trigger Lifecycle**:
   - Do triggers expire? (e.g., FLOW_ALERT after 7 days)
   - Should we show expired triggers? ("Had flow alert 5 days ago")
   - Recommendation: Mark as inactive in `trigger_active` column, show in gray

4. **Earnings Context Display**:
   - Show ALL upcoming earnings (1-30d) for context, even without trigger?
   - Or only show if `earnings_alert=1`?
   - Recommendation: Show all upcoming earnings in symbol detail, but only trigger if `earnings_alert=1`

5. **Airline Play Generalization**:
   - Build generic "date-window strategies" system?
   - Or hardcode airline-specific logic?
   - Recommendation: Start hardcoded, generalize if more date-based strategies emerge

---

## Success Metrics

**Week 1 Success**:
- [ ] Can browse Big List with trigger tags
- [ ] Can add symbols to My Watchlist
- [ ] Watchlist persists across TUI restarts
- [ ] Can remove symbols from watchlist

**Week 2 Success**:
- [ ] OI Build trigger fires for gradual accumulation patterns
- [ ] Airline Play trigger fires 14d before month's 10th
- [ ] Earnings alert logic tuned (>1 symbol triggering)
- [ ] Big List shows 30-50 symbols daily (vs current 20)

**Week 3 Success**:
- [ ] Can filter Big List by trigger type
- [ ] Stale symbols flagged in My Watchlist
- [ ] Trigger history visible in symbol detail
- [ ] User notes on watchlist items

---

## Notes

- **Philosophy**: "Fix a broken house, not build from scratch"
  - Build infrastructure first with existing triggers
  - Incrementally add/improve triggers over time
  - UI drives requirements (seeing gaps prompts fixes)

- **Transparency over Magic**:
  - Explicit trigger tags > opaque scores
  - User curates > algorithm decides
  - Context always visible

- **Practical > Perfect**:
  - Ship Phase 1 quickly, iterate on triggers
  - Some triggers will be simple/naive at first (that's OK)
  - User feedback shapes trigger tuning

---

**Next Session**: Start Phase 1 implementation - create tables, modify view, build UI screens.
