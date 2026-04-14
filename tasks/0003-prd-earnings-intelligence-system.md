# PRD 0003: Earnings Intelligence System

**Author:** Ben (with Claude)
**Date:** 2025-10-10
**Status:** Planning
**Timeline:** Implementation complete by 2025-10-11 AM, then weekend testing/debugging

---

## 1. Introduction/Overview

The Earnings Intelligence System transforms earnings tracking from static historical averages into **dynamic intelligence gathering** that captures:

1. **IV Evolution Patterns** - Track how implied volatility builds/collapses around earnings (not just end result)
2. **Sector Sympathy Effects** - Identify when one company's earnings moves industry peers with mispriced IV
3. **Volatility Arbitrage** - Find underpriced IV in correlated names that will move on sector leader's earnings
4. **Human Insights** - Capture lived trading experience and lessons that data alone cannot show

**The Core Edge:** While the market prices DAL's earnings (IV pumps), AAL options might stay cheap - yet AAL moves anyway when DAL reports strong guidance. This system finds those opportunities systematically.

**The Problem It Solves:**
- Current system only tracks "what was the average move?" (static)
- Misses IV evolution (when did IV pump? when to enter?)
- Misses sector sympathy plays (which peers moved? was their IV cheap?)
- No capture of trading lessons and context

**Relationship to Existing Tables:**
- **`earnings_upcoming`:** KEEP - remains active working pipeline, enhanced with archival logic
- **`earnings_historical`:** DEPRECATE - use as backfill source, then keep as legacy archive (don't delete, just stop updating)
- **Why new system:** Wide format → event-based format, adds IV tracking, adds peer analysis

**Relationship to Existing Scripts:**
- **`data/yfinance_earnings_upcoming.py`:** RELOCATE → `strategies/earnings_play/ep_fetch_upcoming.py` (simplified, fetch-only)
- **`data/yfinance_earnings_historical.py`:** KEEP in data/ as backfill utility (called by ep_backfill_events.py)
- **NEW:** `strategies/earnings_play/ep_main.py` - orchestrator matching fm_main.py / oid_main.py pattern

---

## 2. Goals

1. **Capture the Full Story** - Time-series snapshots of IV/price evolution (7 days before, 3 days after)
2. **Find Hidden Arbitrage** - Systematic sector sympathy detection with IV discount quantification
3. **Survive Data Source Failures** - Immutable archive, never delete earnings events
4. **Learn from Experience** - Queryable trading journal with tag-based pattern searching
5. **Actionable Insights** - Morning view integration to surface today's opportunities

---

## 3. User Stories

**As a trader (Ben), I want to:**

1. **See IV evolution patterns:**
   - "Show me how AAPL's IV typically builds in the 7 days before earnings"
   - "What's the optimal entry timing based on IV pump history?"

2. **Find sector sympathy opportunities:**
   - "DAL has earnings today - which airline peers have cheap IV and historically move with DAL?"
   - "Show me all times NVDA earnings moved AMD, and what the IV discount was"

3. **Track my lessons:**
   - "Show me all times I tagged 'missed-opportunity' - what pattern emerges?"
   - "Search my notes for 'sector-sympathy' in airlines"

4. **Get daily signals:**
   - "What earnings are happening today with high-quality arbitrage setups in their peers?"
   - "Morning view shows me: MSFT earnings, GOOGL IV is 18 points cheaper, historical correlation 0.82"

5. **Backfill historical context:**
   - "Use yfinance historical earnings data to populate the archive"
   - "Calculate historical price moves even where IV snapshots don't exist"

---

## 4. Functional Requirements

### 4.1 Database Schema (5 Tables - Notes Merged into Events)

**FR-1.1:** Create `earnings_events` table (includes trading journal)
- Immutable archive of all earnings (never delete, only insert)
- Columns: event_id (PK), symbol, earnings_date, fiscal_year, fiscal_quarter, estimated_eps, actual_eps, eps_surprise_pct, earnings_time, source, is_backfilled, created_at, **notes, tags, note_type, sentiment**
- Unique constraint on (symbol, earnings_date)
- Indexes on symbol, earnings_date, symbol+date, fiscal period
- **NOTE:** Human insights (notes/tags) merged into this table - no separate earnings_notes table

**FR-1.2:** Create `earnings_snapshots` table
- Time-series capture of IV/price evolution (7 days before, 3 days after earnings)
- Columns: snapshot_id (PK), event_id (FK), symbol, snapshot_date, days_from_earnings, snapshot_type, close_price, volume, iv_30dte, iv_front_month, iv_45dte, total_open_interest, put_call_ratio, is_primary_symbol, created_at
- Unique constraint on (event_id, symbol, snapshot_date)
- Indexes on event_id, symbol, symbol+date, days_from_earnings, snapshot_type
- NOTE: Symbol can differ from event symbol (captures peer snapshots for same event)

**FR-1.3:** Create `earnings_moves` table
- Derived metrics (price moves and IV changes) - can be regenerated
- Columns: move_id (PK), event_id (FK), symbol, move_1day_pct, move_2day_pct, move_3day_pct, move_5day_pct, max_intraday_move_pct, move_direction, iv_buildup_pct, iv_collapse_pct, iv_recovery_pct, iv_crush_severity, expected_move_pct, move_vs_expected_pct, calculated_at
- Unique constraint on (event_id, symbol)
- Indexes on event_id, symbol, move_direction, iv_crush_severity

**FR-1.4:** Create `industry_peer_mappings` table
- Defines industry peer relationships (based on symbol_metadata.industry)
- Columns: mapping_id (PK), industry, symbol, is_industry_leader, peer_type, weight, is_active, notes, created_at, updated_at
- Unique constraint on (industry, symbol)
- Indexes on industry, symbol, is_industry_leader, is_active
- Leader = earliest earnings reporter in industry (manual override possible via is_industry_leader flag)

**FR-1.5:** Create `earnings_sector_effects` table
- Sector sympathy analysis and IV arbitrage signals
- Columns: effect_id (PK), primary_event_id (FK), primary_symbol, peer_symbol, industry, primary_iv_buildup_pct, peer_iv_buildup_pct, iv_arbitrage_delta, primary_move_pct, peer_move_pct, **correlation_strength, sample_size** (grouped together), expected_peer_move_pct, actual_vs_expected_diff, arbitrage_quality, calculated_at
- Unique constraint on (primary_event_id, peer_symbol)
- Indexes on primary_symbol, peer_symbol, industry, arbitrage_quality, primary_event_id
- **CRITICAL:** `correlation_strength` and `sample_size` positioned together in schema with analyst warnings
- `correlation_strength` = weighted average of move ratios (recent events weighted higher)
- `sample_size` = count of historical events used (MUST check this - low sample = anecdotal!)
- `arbitrage_quality` = 'High', 'Medium', 'Low' (basic scoring, iterate later)

**FR-1.6:** ~~Create `earnings_notes` table~~ **MERGED INTO earnings_events**
- Human insights (notes, tags, note_type, sentiment) added as columns to `earnings_events`
- Simpler schema, no separate table needed
- Ben can add notes via direct SQL UPDATE on earnings_events records

**FR-1.7:** Decimal precision standards (MANDATORY)
- Prices/percentages: 2 decimals
- IV/Greeks: 4 decimals
- Ratios/weights: 4 decimals
- Use `tools/decimal_formatter.py` clean_database_row() before all inserts/updates

---

### 4.2 System Orchestration (ep_main.py)

**FR-2.0:** Create `ep_main.py` - Earnings Intelligence Orchestrator
- Central coordinator for all earnings intelligence operations
- Matches pattern of `fm_main.py` (Flow Monitor) and `oid_main.py` (OID)
- Can run standalone or be called by main.py
- Three operational modes:

**Mode 1: Weekly Refresh** (`--weekly-refresh`)
- Fetch upcoming earnings from yfinance (call ep_fetch_upcoming.py)
- Archive past earnings (earnings_upcoming → earnings_events)
- Trigger post-earnings calculations for newly archived earnings
- Clean up earnings_upcoming table (delete archived records)

**Mode 2: Daily Pipeline** (`--daily-pipeline`)
- Collect IV/price snapshots for upcoming earnings (next 7 days)
- Calculate moves for earnings T-3 days ago (post-earnings calc)
- Update expected moves for all upcoming earnings (call ep_moves_upcoming.py)

**Mode 3: Morning Scan** (`--morning-scan`)
- Run arbitrage scanner for today's earnings
- Set morning view flags for high-quality opportunities
- Output: Today's sector arbitrage plays

**Mode 4: Auto-Detect** (`--all`)
- Determines what to run based on current state
- Checks: "Has weekly refresh run in last 7 days?"
- Always runs: daily pipeline, morning scan (if earnings today)

**Integration with main.py:**
```python
# Evening pipeline (~5:00 PM)
subprocess.run([sys.executable, 'strategies/earnings_play/ep_main.py', '--daily-pipeline'])

# Weekly (configurable schedule, default Thursday 8 PM)
subprocess.run([sys.executable, 'strategies/earnings_play/ep_main.py', '--weekly-refresh'])

# Morning pipeline
subprocess.run([sys.executable, 'strategies/earnings_play/ep_main.py', '--morning-scan'])
```

---

### 4.3 Data Population & Archival (Existing Tables Integration)

**FR-2.1:** Simplify and relocate earnings fetcher
- **Source:** `data/yfinance_earnings_upcoming.py` (existing, 698 lines)
- **Destination:** `strategies/earnings_play/ep_fetch_upcoming.py`
- **Simplifications:**
  - Remove `_cleanup_past_earnings()` - ep_main handles archival/cleanup
  - Remove `_calculate_earnings_play_analysis()` - ep_moves_upcoming handles this
  - Keep ONLY: fetch from yfinance + populate earnings_upcoming table
  - Result: ~200 lines (down from 698)
- **Responsibilities:**
  - Fetch next 90 days earnings from yfinance for KLMN 800
  - INSERT OR REPLACE into earnings_upcoming
  - That's it - no analysis, no cleanup
- **Called by:** ep_main.py --weekly-refresh

**FR-2.2:** Auto-populate `industry_peer_mappings` from `symbol_metadata`
- One-time script: `ep_populate_peer_mappings.py`
- Insert all symbols grouped by `symbol_metadata.industry`
- All marked as `is_active=TRUE`, leader detection manual for now
- Default weight=1.0, peer_type='peer'

**FR-2.3:** Backfill `earnings_events` from yfinance API (PREFERRED)
- Script: `ep_backfill_events.py`
- **Primary source:** Pull fresh earnings history from yfinance API for all KLMN 800 symbols
  - yfinance API calls are free
  - Use existing `data/yfinance_earnings_historical.py` as utility (call it, process results)
  - Gets fiscal_year, fiscal_quarter, estimated_eps, actual_eps from `temp_earnings_raw`
  - Transform temp_earnings_raw → earnings_events format
- **Fallback source:** `earnings_historical` table if yfinance historical script fails
  - Parse wide format (q_2021_1_date, q_2021_2_date...) into event records
  - Extract fiscal period from column name (q_2021_1 → year=2021, quarter=1)
- Mark all as `is_backfilled=TRUE`, source='yfinance' or 'earnings_historical'
- Handle duplicates (UNIQUE constraint on symbol+date will skip existing)

**FR-2.4:** Archival logic in `ep_main.py --weekly-refresh`
- **KEEP earnings_upcoming table** - it remains the active working pipeline
- ep_main.py handles archival (NOT ep_fetch_upcoming.py)
- When earnings_date < today in `earnings_upcoming`:
  - Insert into `earnings_events` (if not exists) - archive the event
  - Trigger post-earnings calculation (call ep_post_earnings_calc.py for that event)
  - Delete from `earnings_upcoming` - clean up working table
- Runs on configurable schedule (default: weekly Thursday 8 PM)
- No breaking changes to existing earnings_upcoming table structure

**FR-2.5:** Backfill `earnings_moves` for historical events
- Script: `ep_backfill_moves.py`
- Calculate price moves only (IV fields NULL, no snapshot data)
- Query `historical_prices` for T-1, T+0, T+1, T+2, T+4
- Calculate move_1day_pct, move_2day_pct, move_3day_pct, move_5day_pct, max_intraday_move_pct
- Mark in metadata or comments as "backfilled without IV data"

**FR-2.6:** Deprecate `earnings_historical` table after backfill
- After `ep_backfill_events.py` completes successfully:
  - All earnings events now in `earnings_events`
  - All price moves now in `earnings_moves`
- **Do NOT delete `earnings_historical`** - keep as backup/reference
- Stop updating `earnings_historical` going forward
- Add note to schema: "LEGACY - see earnings_events for current data"

**FR-2.7:** Clean up old scripts post-migration
- Delete `data/yfinance_earnings_upcoming.py` (replaced by ep_fetch_upcoming.py)
- Keep `data/yfinance_earnings_historical.py` (utility for backfilling, called by ep_backfill_events.py)

---

### 4.4 Daily Snapshot Collection

**FR-3.1:** Build `ep_snapshot_collector.py`
- Called by `ep_main.py --daily-pipeline`
- Runs daily as part of main.py evening pipeline (~5:00 PM)
- Query `earnings_upcoming` for earnings in next 7 days
- For each upcoming earnings:
  - Get primary symbol data from `oi_symbol_summary` (latest trade_date)
  - Get industry peers from `industry_peer_mappings` WHERE industry=[symbol's industry] AND is_active=TRUE
  - Get peer symbol data from `oi_symbol_summary` (same trade_date)
  - Get price/volume from `historical_prices` (same trade_date)
  - Insert into `earnings_snapshots` with:
    - days_from_earnings = earnings_date - snapshot_date (negative before, positive after)
    - snapshot_type = 'pre_earnings' if days < 0, 'earnings_day' if days = 0, 'post_earnings' if days > 0
    - is_primary_symbol = TRUE for primary, FALSE for peers
- Trading-day aware: only collect on days where `oi_symbol_summary` has data
- Handle missing data: leave fields NULL if data unavailable
- **Error handling:** Fail loudly if collection fails (log ERROR, don't break system, but be noticeable to maintainers)

**FR-3.2:** Snapshot collection window
- Start: 7 days before earnings (when earnings_days_ahead <= 7)
- Continue: Through earnings day (day 0)
- End: 3 days after earnings (day +3)
- Total: 10 days of snapshots per event

**FR-3.3:** Data source priority
- IV data: `oi_symbol_summary.iv_30dte`, `iv_front_month`, `iv_45dte` (primary source)
- OI data: `oi_symbol_summary.total_open_interest`, `put_call_ratio`
- Price data: `historical_prices.close_price`, `volume`
- NOTE: historical_prices backfills -5 days daily, should never have gaps

---

### 4.5 Post-Earnings Calculation

**FR-4.1:** Build `ep_post_earnings_calc.py`
- Called by `ep_main.py --daily-pipeline` AND `ep_main.py --weekly-refresh` (for newly archived earnings)
- Runs daily as part of main.py
- Check for events in `earnings_events` where earnings_date = (today - 3 days) AND not yet in `earnings_moves`
- For each event:
  - Calculate price moves (query `historical_prices`)
  - Calculate IV changes (query `earnings_snapshots`)
  - Calculate sector effects (query `industry_peer_mappings` for peers)
  - Insert into `earnings_moves` and `earnings_sector_effects`

**FR-4.2:** Update expected moves for upcoming earnings
- ep_main.py calls existing `ep_moves_upcoming.py` after snapshot collection
- Recalculates straddle expected moves with latest IV data
- Updates earnings_upcoming table with fresh metrics
- No changes to existing ep_moves_upcoming.py logic

**FR-4.3:** Price move calculations
- Query `historical_prices` for symbol:
  - T-1 (day before earnings)
  - T+0 (earnings day)
  - T+1, T+2, T+4
- Calculate:
  - move_1day_pct = (T+0 close - T-1 close) / T-1 close * 100
  - move_2day_pct = (T+1 close - T-1 close) / T-1 close * 100
  - move_3day_pct = (T+2 close - T-1 close) / T-1 close * 100
  - move_5day_pct = (T+4 close - T-1 close) / T-1 close * 100
  - max_intraday_move_pct = MAX(abs((high - T-1 close) / T-1 close), abs((low - T-1 close) / T-1 close)) * 100 for T+0 to T+2
  - move_direction = 'UP' if move_1day_pct > 1, 'DOWN' if < -1, else 'FLAT'

**FR-4.4:** IV change calculations
- Query `earnings_snapshots` for event_id + primary symbol:
  - T-7 (7 days before)
  - T-1 (day before)
  - T+1 (day after)
  - T+3 (3 days after)
- Calculate:
  - iv_buildup_pct = (T-1 iv_30dte - T-7 iv_30dte) / T-7 iv_30dte * 100
  - iv_collapse_pct = (T+1 iv_30dte - T-1 iv_30dte) / T-1 iv_30dte * 100
  - iv_recovery_pct = (T+3 iv_30dte - T+1 iv_30dte) / T+1 iv_30dte * 100
  - iv_crush_severity = 'Mild' if abs(iv_collapse_pct) < 20, 'Moderate' if < 40, else 'Severe'

**FR-4.5:** Sector effect calculations
- For each peer in `industry_peer_mappings` (same industry as primary):
  - Get peer's snapshots for same event
  - Calculate peer_iv_buildup_pct (T-7 to T-1)
  - Calculate iv_arbitrage_delta = peer_iv_buildup_pct - primary_iv_buildup_pct (negative = peer was cheaper)
  - Get peer's price move on earnings day (from `historical_prices`)
  - Calculate correlation_strength:
    - Query past `earnings_sector_effects` for same primary+peer pair
    - Weighted average of move ratios: SUM(peer_move / primary_move * weight) / SUM(weight)
    - Recent events weighted higher (exponential decay)
    - Return value ~0.0-1.5 (typically 0.5-1.0 for correlated names)
  - Calculate expected_peer_move_pct = primary_move_pct * correlation_strength
  - Calculate actual_vs_expected_diff = peer_move_pct - expected_peer_move_pct
  - Determine arbitrage_quality:
    - 'High' if iv_arbitrage_delta < -15 AND correlation_strength > 0.7 (or sample_size < 3)
    - 'Medium' if iv_arbitrage_delta < -10 OR correlation_strength > 0.6
    - 'Low' otherwise
  - Set sample_size = COUNT of historical sector_effects for this pair
  - Insert into `earnings_sector_effects`

**FR-4.6:** Handle backfilled events
- When calculating for backfilled events (is_backfilled=TRUE):
  - Calculate price moves normally
  - IV fields stay NULL (no historical snapshot data)
  - Skip sector effects calculation (requires IV snapshots)

---

### 4.6 Arbitrage Scanner & Integration

**FR-5.1:** Build `ep_arbitrage_scanner.py`
- Called by `ep_main.py --morning-scan`
- Can also run standalone (manual run before market open)
- Query `earnings_upcoming` for earnings happening today
- For each earnings today:
  - Get historical `earnings_sector_effects` for primary_symbol
  - Filter peers with correlation_strength > 0.7 OR sample_size < 3 (give new peers a chance)
  - Get latest snapshots to calculate current IV discount
  - Rank opportunities by:
    - IV discount size (more negative = better)
    - Historical correlation strength (higher = better)
    - Expected move magnitude (larger = better)
  - Output: Symbol, industry, IV discount, correlation, sample_size, arbitrage_quality

**FR-5.2:** Morning view integration (flag-based)
- Earnings strategy raises a flag for symbols with arbitrage opportunities
- Morning view reads flags from strategy modules and adds symbols to tracking lists
- Morning view team handles display/formatting
- **Implementation:** Add flag column to `earnings_upcoming` or use separate tracking table
  - `has_arbitrage_opportunity BOOLEAN` (set by arbitrage scanner)
  - Morning view imports peer data for display: "MSFT earnings today → Watch GOOGL (IV 18pts cheaper, 0.82 correlation, sample_size=8)"

**FR-5.3:** Opportunity ranking logic (initial, basic)
- Use simple weighted score: (abs(iv_arbitrage_delta) * 0.5) + (correlation_strength * 50)
- Score > 40 = High quality
- Score 20-40 = Medium quality
- Score < 20 = Low quality
- NOTE: Will iterate and refine after collecting initial data

---

### 4.7 Notes & Human Insights (Merged into earnings_events)

**FR-6.1:** Manual entry via SQL UPDATE
- Ben manually updates `earnings_events` records to add notes
- Example:
  ```sql
  UPDATE earnings_events
  SET notes = 'DAL positive guidance, all airlines popped. Should have held AAL through call.',
      tags = 'sector-sympathy,missed-opportunity,airlines',
      note_type = 'lesson',
      sentiment = 'mixed'
  WHERE symbol = 'AAL' AND earnings_date = '2025-04-15';
  ```
- Required: symbol, earnings_date (to identify event)
- Optional: notes, tags, note_type, sentiment (all nullable)
- TUI interface deferred to future phase

**FR-6.2:** Tag-based searching
- Support queries like:
  ```sql
  SELECT symbol, earnings_date, notes
  FROM earnings_events
  WHERE tags LIKE '%sector-sympathy%'
  ORDER BY earnings_date DESC;
  ```
- Common tags: sector-sympathy, missed-opportunity, lesson-learned, exit-too-early, airlines, tech

---

### 4.8 Integration Points

**FR-7.1:** Existing table dependencies
- Reads from: `symbol_metadata` (industry), `oi_symbol_summary` (IV data), `historical_prices` (price/volume), `earnings_upcoming` (pipeline source)
- Writes to: `datalake.db` (syncs to `datalake_query.db` automatically)

**FR-7.2:** main.py integration (via ep_main.py)
- Evening pipeline (~5:00 PM): Call `ep_main.py --daily-pipeline`
- Weekly refresh (configurable): Call `ep_main.py --weekly-refresh`
- Morning pipeline: Call `ep_main.py --morning-scan`
- Alternative: Call `ep_main.py --all` (auto-detects what to run)

**FR-7.3:** Trading day awareness
- Use `oi_symbol_summary` trade_date as official "trading days" source
- Only collect snapshots on days where OID ran successfully
- If OID fails (rare), snapshot will have NULL IV fields (historical_prices still available)

---

## 5. Non-Goals (Out of Scope)

**NG-1:** TUI interface for notes entry
- Deferred to future phase
- Manual SQL UPDATE on earnings_events sufficient for initial launch

**NG-2:** Advanced correlation algorithms
- Start with simple weighted average of move ratios
- Defer Pearson correlation, machine learning models to future

**NG-3:** Automated yfinance failure recovery
- If yfinance misses earnings date, manual intervention required
- Alternative data sources (FMP, Polygon) deferred

**NG-4:** Intraday snapshot collection
- Only end-of-day snapshots (~5:00 PM)
- No intraday IV tracking

**NG-5:** Extensive snapshot verification criteria
- Basic "did it run?" verification sufficient
- Detailed quality checks deferred

**NG-6:** Historical IV snapshot backfill
- Cannot backfill IV data that wasn't collected (no historical source)
- Only backfill price moves for historical events
- IV-based analysis (sector effects) requires forward data collection only

**NG-7:** Multi-quarter earnings trend analysis
- Future enhancement: "Does AAPL's Q4 earnings always move more than Q2?"
- Initial version: treat all earnings equally

**NG-8:** Discord/email alerts for arbitrage opportunities
- Initially: morning view integration only
- Alert infrastructure deferred

---

## 6. Technical Considerations

### 6.1 Database Design
- All tables use `INTEGER PRIMARY KEY AUTOINCREMENT` for IDs
- Foreign keys reference `earnings_events(event_id)`
- Extensive indexing for query performance
- Decimal precision enforced via `tools/decimal_formatter.py`

### 6.2 Data Retention
- **Never delete:** earnings_events, earnings_snapshots, earnings_notes, industry_peer_mappings
- **Recalculate freely:** earnings_moves, earnings_sector_effects (derived data)
- **Working table:** earnings_upcoming (refreshed weekly)

### 6.3 Performance Estimates
- Snapshot collection: ~50 earnings/week × 10 days × 5 symbols (1 primary + 4 peers) = 2,500 rows/week
- Annual growth: ~130K snapshots, ~2.5K events, ~13K sector effects
- Total database size: ~5-10MB growth per year (very manageable)

### 6.4 Error Handling
- Missing snapshot data: leave NULL, continue processing
- Missing peer data: skip that peer, continue with others
- Division by zero in correlation: return NULL, set sample_size=0
- Backfill duplicates: UNIQUE constraints prevent duplicates, log and skip

### 6.5 Existing Code References
- Snapshot collector pattern: similar to `oid_snapshot_collector.py`
- Post-calc pattern: similar to `oid_post_analysis.py`
- Decimal formatting: `tools/decimal_formatter.py` (MANDATORY for all writes)
- Timezone handling: `tools/timezone_utils.py` now_eastern()

---

## 7. Success Metrics

### 7.1 Phase 1 Success (Foundation) - Day 1
- ✅ All 5 tables created with correct schema (notes merged into events)
- ✅ Successfully archive 10+ earnings from `earnings_upcoming` to `earnings_events`
- ✅ Backfill earnings_events from yfinance API (2021-2025 historical data)
- ✅ No database errors during weekly refresh
- ✅ All foreign key relationships intact
- ✅ `industry_peer_mappings` populated with all 745 symbols grouped by industry

### 7.2 Phase 2 Success (Snapshots) - Day 2
- ✅ Snapshot collection runs daily without errors
- ✅ Collect snapshots for 5+ upcoming earnings over 1 week
- ✅ Verify snapshots include primary + peers (avg 5 symbols per event)
- ✅ Trading-day aware (only collects when OID data exists)

### 7.3 Phase 3 Success (Post-Calc) - Day 3
- ✅ Post-earnings calculation runs daily
- ✅ Successfully calculate moves for 5+ events
- ✅ IV changes calculated where snapshot data exists
- ✅ Sector effects populated with correlation_strength and sample_size

### 7.4 Phase 4 Success (Arbitrage Scanner) - Day 4
- ✅ Arbitrage scanner runs manually and outputs ranked opportunities
- ✅ Morning view shows earnings with `has_arbitrage_opportunity=TRUE`
- ✅ Can answer: "Which peers have cheap IV for today's earnings?"

### 7.5 Phase 5 Success (Backfill) - Day 5-6
- ✅ Backfill earnings_events from earnings_historical (2021-2025)
- ✅ Backfill earnings_moves for historical events (price moves only)
- ✅ Can query: "Show AAPL's IV buildup pattern across last 10 earnings"

### 7.6 Overall Success Criteria
**System is working when you can answer:**
1. ✅ "Which stocks have earnings this week with cheap IV in their industry peers?"
2. ✅ "When AAPL reports earnings, which other tech stocks typically move?"
3. ✅ "Show me all times I noted 'missed opportunity' - what pattern do I see?"
4. ✅ "What's the optimal entry timing for DAL earnings based on IV evolution?"
5. ✅ "If MSFT moves +5% on earnings, what's the expected move in GOOGL?"

---

## 8. Implementation Phases (6-Day Timeline)

### Day 1: Foundation & Orchestration (2025-10-11)
- [ ] Run migrations (create all 5 tables)
- [ ] Build `ep_main.py` orchestrator (weekly-refresh, daily-pipeline, morning-scan modes)
- [ ] Simplify and relocate `data/yfinance_earnings_upcoming.py` → `ep_fetch_upcoming.py`
- [ ] Build `ep_populate_peer_mappings.py` (auto-populate from symbol_metadata)
- [ ] Build `ep_backfill_events.py` (use yfinance_earnings_historical.py utility)
- [ ] Test: Weekly refresh workflow, archival logic, foreign keys

### Day 2: Snapshot Collection (2025-10-12)
- [ ] Build `ep_snapshot_collector.py`
- [ ] Integrate into `ep_main.py --daily-pipeline`
- [ ] Test: Run daily pipeline, verify snapshots for upcoming earnings
- [ ] Verify: Primary + peer snapshots, trading-day aware

### Day 3: Post-Earnings Calculation (2025-10-13)
- [ ] Build `ep_post_earnings_calc.py`
- [ ] Integrate into `ep_main.py --daily-pipeline` and `--weekly-refresh`
- [ ] Update expected moves (call ep_moves_upcoming.py from ep_main)
- [ ] Test: Calculate moves for historical events (T-3 days)
- [ ] Verify: Price moves, IV changes, sector effects populated

### Day 4: Arbitrage Scanner & Integration (2025-10-14)
- [ ] Build `ep_arbitrage_scanner.py`
- [ ] Integrate into `ep_main.py --morning-scan`
- [ ] Add morning view integration (has_arbitrage_opportunity flag)
- [ ] Integrate ep_main.py into main.py (evening, weekly, morning calls)
- [ ] Test: Run morning scan for today's earnings
- [ ] Verify: Ranked opportunities, correlation + sample_size shown

### Day 5-6: Backfill & Polish (2025-10-15 - 2025-10-16)
- [ ] Build `ep_backfill_moves.py` (historical price moves)
- [ ] Run backfill for all events in earnings_events
- [ ] Add manual notes for recent sector sympathy plays (SQL UPDATE)
- [ ] Clean up old scripts (delete data/yfinance_earnings_upcoming.py)
- [ ] Test end-to-end: ep_main --weekly-refresh → --daily-pipeline → --morning-scan
- [ ] Debug and patch holes as discovered

### Weekend: Testing & Automation
- [ ] Monitor automated runs (main.py → ep_main.py)
- [ ] Verify all three modes: weekly-refresh, daily-pipeline, morning-scan
- [ ] Fix any edge cases or errors
- [ ] Verify morning view integration
- [ ] Document any manual steps required
- [ ] Verify ep_main.py can run standalone (independent of main.py)

---

## 9. Open Questions

**Q1:** Correlation calculation method confirmation
- **Proposed:** Weighted average of move ratios with recency weighting
- **Alternative:** Simple ratio (less stable) or Pearson correlation (more complex)
- **Decision:** Use weighted average (approved above)

**Q2:** Leader detection frequency
- **Proposed:** One-time setup, manual updates after
- **Monitoring:** Should we add a report showing "who reported first in each industry last quarter"?
- **Decision:** One-time setup for now (approved above)

**Q3:** Snapshot collection failure handling
- **Proposed:** Leave NULL fields if data missing, continue processing
- **Monitoring:** Log missing data counts, alert if >10% snapshots have NULL IV?
- **Decision:** NULL fields acceptable (approved above)

**Q4:** Arbitrage quality scoring refinement
- **Proposed:** Start with basic weighted formula, iterate after data collection
- **Monitoring:** Track how often 'High' quality plays actually work
- **Decision:** Basic formula initially, refine later (approved above)

**Q5:** Morning view integration details
- **Question:** Where exactly in morning view should arbitrage plays appear?
- **Options:** New section? Embedded in existing earnings section? Separate tab?
- **Decision:** TBD - will determine during implementation

---

## 10. Appendices

### Appendix A: SQL Schema Files
All schema files created in `strategies/earnings_play/`:
- `001_create_earnings_events.sql` (includes notes/tags columns)
- `002_create_earnings_snapshots.sql`
- `003_create_earnings_moves.sql`
- `004_create_industry_peer_mappings.sql`
- `005_create_earnings_sector_effects.sql` (correlation+sample_size grouped)
- ~~`006_create_earnings_notes.sql`~~ (merged into earnings_events)
- `000_run_all_migrations.sql` (master script - creates 5 tables)

### Appendix B: Key Queries
See `TABLE_RELATIONSHIPS.md` for:
- Today's arbitrage opportunities query
- IV evolution pattern analysis
- Sector sympathy historical performance
- Notes search by tags

### Appendix C: Data Sources
- **IV data:** `oi_symbol_summary` (primary source, end-of-day)
- **Price data:** `historical_prices` (backfills -5 days daily)
- **Industry grouping:** `symbol_metadata.industry`
- **Earnings pipeline:** `earnings_upcoming` (refreshed weekly Thursday 8 PM)
- **Trading days:** `oi_symbol_summary.trade_date` (official source)

### Appendix D: Existing Code to Reference
- `strategies/flow_monitor/fm_main.py` - orchestrator pattern to match
- `strategies/oi_delta/oid_main.py` - orchestrator pattern to match
- `strategies/oi_delta/oid_snapshot_collector.py` - snapshot collection pattern
- `strategies/oi_delta/oid_post_analysis.py` - post-analysis calculation pattern
- `strategies/earnings_play/ep_moves_upcoming.py` - existing earnings logic (call from ep_main)
- `data/yfinance_earnings_upcoming.py` - source for ep_fetch_upcoming.py (simplify this)
- `data/yfinance_earnings_historical.py` - backfill utility (keep as-is, call from ep_backfill_events)
- `tools/decimal_formatter.py` - MANDATORY for all database writes
- `tools/timezone_utils.py` - timezone handling

---

**PRD Status:** ✅ Complete - Ready for task generation

**Next Step:** Generate task list using `@ai-dev-tasks/generate-tasks.md`
