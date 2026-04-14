# News Collector Quick Fix Plan

**Created:** 2025-10-13
**Goal:** Get news_collector operational and integrated into main.py scheduling

---

## Problem Analysis

### Issue 1: Missing v_morning_watchlist View
**Symptom:** `news_collector --dry-run` shows:
```
ERROR: Failed to get watchlist symbols: no such table: v_morning_watchlist
INFO: Tier 1: 0 watchlist symbols
```

**Root Cause:**
- `v_morning_watchlist` view is created by `morning_views.py` at runtime
- View only exists in `datalake_query.db` (where morning_views.py runs)
- `news_collector` tries to read from `datalake.db` (primary database) by default
- View doesn't exist in primary database

**Impact:**
- Tier 1 collection fails (0 symbols)
- Tier 2 and Tier 3 work fine
- News collection still functional but misses high-priority watchlist symbols

### Issue 2: Not Scheduled
**Symptom:** Last news collection was Oct 5, 2025

**Root Cause:**
- News collector not integrated into `main.py` orchestrator
- Runs manually only

**Impact:**
- News data becomes stale
- Morning View shows old sentiment scores
- Manual intervention required

---

## Quick Fix Solution

### Fix 1: Hybrid Read/Write Approach (RECOMMENDED)

**Option D: Read from Query DB, Write to Primary DB**
- Read Tier 1 symbols from `datalake_query.db` (where views exist)
- Write news data to `datalake.db` (primary database - correct flow)
- Union `v_morning_watchlist` + `v_morning_discovery` for comprehensive coverage
- Pros:
  - Leverages Morning Views' sophisticated trigger logic
  - Proper data flow (writes to primary)
  - No view duplication
  - Comprehensive symbol coverage
- Cons: None
- Implementation: ~15 lines in `nc_storage.py`

**Why This Works:**
- Query database has both views (created by morning_views.py)
- Primary database is source of truth for news writes
- Query DB gets overwritten by sync (so we can't write there)
- Tier 1 gets union of watchlist (focused) + discovery (all active triggers)

### Fix 2: Main.py Integration

**Where to add:** After morning OID pipeline (~6:35 AM sequence)

**Placement in main.py:**
```python
# Current flow (line ~500-650):
# 6:35 AM - Morning OID Pipeline
def run_morning_oid_pipeline(self):
    ...
    # Query Database Sync #1 (overnight OI data)
    self.sync_query_database()
    # Morning Views (emailed watchlist)  <-- INSERT AFTER THIS
    self.run_morning_views()
```

**Add after morning_views:**
```python
def run_news_collection(self):
    """Collect news for all three tiers"""
    self.beautiful_log("Starting news collection...")

    script_path = os.path.join(project_root, 'strategies', 'news_collector', 'nc_main.py')

    try:
        result = subprocess.run(
            [sys.executable, script_path, '--no-interaction'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            self.beautiful_log("News collection completed successfully")
            return True
        else:
            self.beautiful_log(f"News collection failed: {result.stderr}", 'error')
            return False

    except subprocess.TimeoutExpired:
        self.beautiful_log("News collection timed out (>10 minutes)", 'error')
        return False
    except Exception as e:
        self.beautiful_log(f"Failed to run news collection: {e}", 'error')
        return False
```

**Timing:** ~5-10 minutes (125 API calls with rate limiting)

---

## Implementation Steps

### Step 1: Update Tier 1 Symbol Collection
**File:** `strategies/news_collector/nc_storage.py`
**Method:** `get_watchlist_symbols()` (line ~56-74)

**Replace entire method:**
```python
def get_watchlist_symbols(self):
    """
    Get Tier 1 symbols from Morning Views (union of watchlist + discovery).

    Reads from query database where views exist:
    - v_morning_watchlist: Top 20 curated symbols (focused tracking)
    - v_morning_discovery: All symbols with active triggers (flow alerts, earnings, etc.)

    Returns deduplicated union of both views for comprehensive coverage.

    Returns:
        list: Symbols from both views (deduplicated)
    """
    # Read from query database (where Morning Views creates the views)
    query_db_path = self.database_path.replace('datalake.db', 'datalake_query.db')

    try:
        with sqlite3.connect(query_db_path) as conn:
            cursor = conn.execute("""
                SELECT symbol FROM v_morning_watchlist
                UNION
                SELECT symbol FROM v_morning_discovery
                ORDER BY symbol
            """)
            symbols = [row[0] for row in cursor.fetchall()]
            logging.info("Tier 1: {} symbols from watchlist + discovery union".format(len(symbols)))
            return symbols
    except Exception as e:
        logging.error("Failed to get Tier 1 symbols: {}".format(e))
        return []
```

**Justification:**
- Reads from query database (where views are created by morning_views.py)
- Writes continue to go to primary database (proper data flow)
- Union gives comprehensive coverage: focused watchlist + all active triggers
- Query DB sync happens 3x daily, so views are fresh
- No risk of write data loss (writes go to primary, reads from query)

### Step 2: Add News Collection to main.py
**File:** `main.py`
**Location:** After `run_morning_views()` call (~line 550-600)

**Add method:**
```python
def run_news_collection(self):
    """
    Collect financial news for three-tier priority system.

    Tiers:
    - Tier 1: Watchlist symbols (from v_morning_watchlist) - 25 calls
    - Tier 2: KLMN_PREFERRED + Airlines (~110 symbols) - 75 calls
    - Tier 3: Remaining KLMN_800 (~690 symbols) - 25 calls

    Total: 125 API calls/day across 5 Alpha Vantage keys
    Duration: ~5-10 minutes
    """
    self.beautiful_log("Running news collection pipeline...")

    script_path = os.path.join(project_root, 'strategies', 'news_collector', 'nc_main.py')

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=600  # 10 minute timeout
        )

        if result.returncode == 0:
            self.beautiful_log("✓ News collection completed successfully")

            # Parse summary from output (last few lines contain stats)
            output_lines = result.stdout.strip().split('\n')
            for line in output_lines[-10:]:  # Check last 10 lines for summary
                if 'Total symbols:' in line or 'Articles stored:' in line:
                    self.beautiful_log(f"  {line.strip()}")

            return True
        else:
            self.beautiful_log(f"✗ News collection failed: {result.stderr}", 'error')
            return False

    except subprocess.TimeoutExpired:
        self.beautiful_log("✗ News collection timed out (>10 minutes)", 'error')
        return False
    except Exception as e:
        self.beautiful_log(f"✗ Failed to run news collection: {e}", 'error')
        return False
```

**Call location:**
```python
# In run_daily_sequence() method (~line 580-650):
def run_daily_sequence(self):
    ...
    # Morning pipeline (6:35 AM)
    self.run_morning_oid_pipeline()
    self.sync_query_database()  # Sync #1
    self.run_morning_views()

    # ADD HERE:
    self.run_news_collection()  # ~5-10 minutes, 125 API calls

    # Flow Monitor starts at 9:15 AM
    self.wait_until_flow_monitor_start()
    ...
```

### Step 3: Add Banner Entry
**File:** `main.py`
**Location:** Banner display (~line 180)

**Add line:**
```python
print("║   6:35 AM  🌅 Morning OID Pipeline                                ║")
print("║            📧 Morning Views (emailed watchlist)                   ║")
print("║            📰 News Collection (125 API calls, 3 tiers)            ║")  # <-- ADD THIS
print("║   9:15 AM  📈 Flow Monitor - Pre-Market Prep                     ║")
```

### Step 4: Test
**Commands:**
```bash
# Test with database fix only
cd E:\options_scanner
python strategies/news_collector/nc_main.py --dry-run

# Expected output:
# - Tier 1: >0 symbols (should show watchlist count)
# - Tier 2: 115 symbols
# - Tier 3: 636 symbols
# - No errors about missing table

# Test full collection (limited)
python strategies/news_collector/nc_main.py --limit 5

# Expected: 5 symbols per tier collected, news stored

# Test main.py integration (once mode)
python main.py --once

# Expected: Morning pipeline runs, news collection happens after Morning Views
```

### Step 5: Verify Data Flow
**SQL Check:**
```bash
# Check query database has news
python tools/direct_db_query.py --sql "SELECT COUNT(*) as articles FROM news_articles WHERE article_date >= date('now', '-1 day')"

# Expected: >0 recent articles

# Check primary database gets synced
python data/health/db_backup.py --sync --auto

# Then check primary database
python tools/direct_db_query.py --db data/datalake.db --sql "SELECT COUNT(*) as articles FROM news_articles WHERE article_date >= date('now', '-1 day')"

# Expected: Same count as query database
```

---

## Estimated Time

**Implementation:** 15-20 minutes
- Update Tier 1 symbol collection: 5 minutes
- Add news collection method to main.py: 5 minutes
- Update banner: 1 minute
- Testing: 10 minutes

**First Run Duration:** ~10 minutes
- 125 API calls with rate limiting
- Tier 1: 91 symbols (20 watchlist + 81 discovery, 10 overlap → 25 collected by staleness)
- Tier 2: 115 symbols (KLMN_PREFERRED + Airlines → 75 collected by staleness)
- Tier 3: 636 symbols (remaining KLMN_800 → 25 collected by staleness)
- Writes ~150-250 articles (depends on articles per symbol from Alpha Vantage)
- Updates staleness timestamps for 125 symbols

---

## Success Criteria

✅ **Immediate Success:**
1. `--dry-run` shows Tier 1 with >0 symbols (no errors)
2. Full collection completes without errors
3. `news_articles` and `news_symbol_sentiment` tables populate
4. Morning View shows news sentiment for symbols

✅ **Integration Success:**
1. `main.py --once` runs news collection after Morning Views
2. News collection completes in <10 minutes
3. No database locking conflicts
4. Logs show clear summary stats

✅ **Operational Success (Week 1):**
1. News data updates daily automatically
2. Tier 2 symbols get full rotation every ~1.5 days
3. Morning View rankings include fresh news sentiment
4. No API quota errors (stays under 25 calls/key/day)

---

## Rollback Plan

If issues arise:

**Quick Rollback:**
1. Comment out `self.run_news_collection()` call in main.py
2. System continues without news collection (degraded but functional)

**Tier 1 Fallback:**
If Tier 1 still fails after update (views don't exist in query DB):
```python
# Add to nc_storage.py get_watchlist_symbols():
except Exception as e:
    logging.error("Failed to get Tier 1 symbols from views: {}".format(e))
    logging.warning("Using flow_alerts fallback for Tier 1")

    # Fallback: query flow_alerts directly from primary database
    try:
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.execute("""
                SELECT DISTINCT symbol
                FROM flow_alerts
                WHERE evaluation_status = 'active'
                AND DATE(alert_timestamp) >= DATE('now', '-7 days')
                ORDER BY symbol
            """)
            symbols = [row[0] for row in cursor.fetchall()]
            logging.info("Tier 1 fallback: {} symbols from flow_alerts".format(len(symbols)))
            return symbols
    except Exception as fallback_error:
        logging.error("Tier 1 fallback failed: {}".format(fallback_error))
        return []
```

---

## Future Enhancements (Post-Fix)

Once operational, consider:
1. **Scheduling optimization:** Run at 6:00 AM before Morning Views (fresher sentiment)
2. **Tier 1 expansion:** Include user_watchlist table when redesign is complete
3. **Smart quotas:** Adjust tier allocations based on usage patterns
4. **Parallel collection:** Use asyncio for faster API calls
5. **Enhanced storage:** Store full article JSON for Phase 1 intelligence work

---

## Related Documentation

- **Enhancement Roadmap:** `docs/news-collector-enhancement-roadmap.md`
- **PRD:** `tasks/0002-prd-news-collection-infrastructure.md`
- **Module Code:** `strategies/news_collector/`
- **Morning Views:** `morning_view/morning_views.py` (creates v_morning_watchlist view)
