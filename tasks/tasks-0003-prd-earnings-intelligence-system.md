# Task List: PRD 0003 - Earnings Intelligence System

**Generated:** 2025-10-10
**Source PRD:** `0003-prd-earnings-intelligence-system.md`
**Timeline:** 6 days (2 days build, 4 days test/debug)

---

## Relevant Files

### New Files to Create
- `strategies/earnings_play/ep_main.py` - Orchestrator (matches fm_main.py / oid_main.py pattern)
- `strategies/earnings_play/ep_fetch_upcoming.py` - Simplified earnings fetcher (from data/yfinance_earnings_upcoming.py)
- `strategies/earnings_play/ep_populate_peer_mappings.py` - One-time peer mapping setup
- `strategies/earnings_play/ep_backfill_events.py` - Backfill earnings_events from yfinance
- `strategies/earnings_play/ep_backfill_moves.py` - Backfill earnings_moves (price only)
- `strategies/earnings_play/ep_snapshot_collector.py` - Daily IV/price snapshot collection
- `strategies/earnings_play/ep_post_earnings_calc.py` - Post-earnings calculation engine
- `strategies/earnings_play/ep_arbitrage_scanner.py` - Morning arbitrage opportunity scanner
- `strategies/earnings_play/000_run_all_migrations.sql` - Master migration script (exists, ready to run)
- `strategies/earnings_play/001_create_earnings_events.sql` - Schema (exists)
- `strategies/earnings_play/002_create_earnings_snapshots.sql` - Schema (exists)
- `strategies/earnings_play/003_create_earnings_moves.sql` - Schema (exists)
- `strategies/earnings_play/004_create_industry_peer_mappings.sql` - Schema (exists)
- `strategies/earnings_play/005_create_earnings_sector_effects.sql` - Schema (exists)

### Files to Modify
- `data/yfinance_earnings_upcoming.py` - Source for simplification → ep_fetch_upcoming.py (then delete)
- `main.py` - Add ep_main.py integration calls (evening, weekly, morning)

### Files to Reference (No Changes)
- `data/yfinance_earnings_historical.py` - Utility for backfilling (keep as-is)
- `strategies/earnings_play/ep_moves_upcoming.py` - Call from ep_main.py (no changes)
- `strategies/flow_monitor/fm_main.py` - Orchestrator pattern reference
- `strategies/oi_delta/oid_main.py` - Orchestrator pattern reference
- `tools/decimal_formatter.py` - MANDATORY for all database writes
- `tools/timezone_utils.py` - Timezone handling

### Notes
- All SQL schema files already created and reviewed
- Decimal precision: 2 for prices/percentages, 4 for IV/greeks (use decimal_formatter.py)
- Database: Write to `datalake.db` (syncs to `datalake_query.db`)
- Trading-day aware: Use oi_symbol_summary.trade_date as official source

---

## Tasks

### 1.0 Database Foundation & Schema Migration
- [ ] 1.1 Run 000_run_all_migrations.sql to create all 5 tables
- [ ] 1.2 Verify table creation (check that earnings_events, earnings_snapshots, earnings_moves, industry_peer_mappings, earnings_sector_effects exist)
- [ ] 1.3 Test foreign key relationships (insert test data into earnings_events, then earnings_snapshots)
- [ ] 1.4 Verify indexes created successfully (check sqlite_master for index entries)
- [ ] 1.5 Test UNIQUE constraints with duplicate data (ensure symbol+date constraint works)
- [ ] 1.6 Document schema additions in datalake_schema.md (add 5 new tables)

### 2.0 System Orchestration (ep_main.py)
- [ ] 2.1 Create ep_main.py file with argparse setup (match fm_main.py/oid_main.py pattern)
- [ ] 2.2 Implement --weekly-refresh mode (fetch upcoming, archive past, cleanup)
- [ ] 2.3 Implement --daily-pipeline mode (snapshot collection, post-calc, expected moves update)
- [ ] 2.4 Implement --morning-scan mode (run arbitrage scanner)
- [ ] 2.5 Implement --all mode (auto-detect: check last refresh, run daily+morning)
- [ ] 2.6 Add beautiful_log() and create_phase_header() functions (match fm_main pattern)
- [ ] 2.7 Add comprehensive logging and error handling (UTF-8 encoding, timezone awareness)
- [ ] 2.8 Test each mode independently (verify each flag works standalone)

### 3.0 Data Collection & Population
- [ ] 3.1 Create ep_fetch_upcoming.py (simplify data/yfinance_earnings_upcoming.py from 698→200 lines)
- [ ] 3.2 Create ep_populate_peer_mappings.py (query symbol_metadata.industry, insert into industry_peer_mappings)
- [ ] 3.3 Create ep_backfill_events.py (call yfinance_earnings_historical.py utility, transform to earnings_events)
- [ ] 3.4 Test ep_fetch_upcoming.py (fetch next 90 days, insert into earnings_upcoming)
- [ ] 3.5 Test peer mappings population (verify all 745+ KLMN 800 symbols grouped by industry)
- [ ] 3.6 Test backfill from yfinance API (2021-2025 data, mark is_backfilled=TRUE)
- [ ] 3.7 Test archival logic in ep_main.py --weekly-refresh (earnings_upcoming → earnings_events)
- [ ] 3.8 Verify cleanup (archived earnings deleted from earnings_upcoming)

### 4.0 Daily Intelligence Pipeline
- [ ] 4.1 Create ep_snapshot_collector.py (collect IV/price snapshots for primary + peers)
- [ ] 4.2 Create ep_post_earnings_calc.py (calculate price moves, IV changes, sector effects)
- [ ] 4.3 Implement price move calculations (move_1day, move_2day, move_3day, move_5day, max_intraday, direction)
- [ ] 4.4 Implement IV change calculations (buildup_pct, collapse_pct, recovery_pct, crush_severity)
- [ ] 4.5 Implement sector effects calculations (correlation_strength, sample_size, iv_arbitrage_delta, expected moves)
- [ ] 4.6 Integrate snapshot collector into ep_main.py --daily-pipeline
- [ ] 4.7 Integrate post-earnings calc into ep_main.py --daily-pipeline (trigger for T-3 day events)
- [ ] 4.8 Call ep_moves_upcoming.py from ep_main.py (update expected moves with latest IV)
- [ ] 4.9 Test snapshot collection for upcoming earnings (verify 7-day window, primary + 4 peers)
- [ ] 4.10 Test post-calc for T-3 day events (verify earnings_moves and earnings_sector_effects populated)
- [ ] 4.11 Verify decimal formatting (use tools/decimal_formatter.py for all database writes)
- [ ] 4.12 Verify trading-day awareness (only collect snapshots when oi_symbol_summary has data)

### 5.0 Arbitrage Scanner & Morning View Integration
- [ ] 5.1 Create ep_arbitrage_scanner.py (query today's earnings, find peers with cheap IV)
- [ ] 5.2 Implement opportunity ranking algorithm (IV discount * 0.5 + correlation * 50)
- [ ] 5.3 Implement quality scoring (High: score>40, Medium: 20-40, Low: <20)
- [ ] 5.4 Integrate scanner into ep_main.py --morning-scan
- [ ] 5.5 Add has_arbitrage_opportunity flag column to earnings_upcoming (or create tracking table)
- [ ] 5.6 Test scanner output (verify: symbol, peer, IV discount, correlation, sample_size, quality)
- [ ] 5.7 Integrate ep_main.py into main.py (add evening --daily-pipeline call)
- [ ] 5.8 Integrate ep_main.py into main.py (add weekly --weekly-refresh call)
- [ ] 5.9 Integrate ep_main.py into main.py (add morning --morning-scan call)
- [ ] 5.10 Verify morning view flag system (test that flags are set correctly)
- [ ] 5.11 Test end-to-end: main.py calls → ep_main.py executes → data updated

### 6.0 Backfill & System Polish
- [ ] 6.1 Create ep_backfill_moves.py (calculate historical price moves from historical_prices)
- [ ] 6.2 Run backfill for all events in earnings_events (populate earnings_moves with price data only)
- [ ] 6.3 Test backfilled moves (verify: move_1day, move_2day calculated correctly, IV fields NULL)
- [ ] 6.4 Add manual notes for recent trades (SQL UPDATE examples on earnings_events.notes)
- [ ] 6.5 Delete data/yfinance_earnings_upcoming.py (replaced by ep_fetch_upcoming.py)
- [ ] 6.6 Move data/yfinance_earnings_upcoming.py to tools/Deprecated/ (keep as reference)
- [ ] 6.7 Test full workflow: ep_main.py --weekly-refresh → --daily-pipeline → --morning-scan
- [ ] 6.8 Run end-to-end system test with actual market data (verify all 3 modes work)
- [ ] 6.9 Debug and fix any errors discovered during testing
- [ ] 6.10 Verify standalone operation (ep_main.py runs without main.py)
- [ ] 6.11 Document manual steps required (leader detection, note entry examples)
- [ ] 6.12 Update CLAUDE.md with ep_main.py usage examples

---

**Status:** Phase 2 Complete - Detailed sub-tasks generated
**Total Sub-Tasks:** 61 actionable items across 6 parent tasks
**Next Step:** Begin implementation - start with Task 1.0 (Database Foundation)
