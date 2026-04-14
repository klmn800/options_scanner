# Logging System Inventory
**Date:** 2025-11-18
**Purpose:** Comprehensive audit of all logging across main.py and subprocess operations

---

## Summary Overview

### Current State
- **Centralized logs:** Partial (main.py in `logs/`, strategies in their own directories)
- **Standardization:** Low (mix of logging module, print(), different formats)
- **Verbosity:** Varies widely (some over-log, some under-log)
- **Machine-parseable:** Minimal (mostly human-readable text)

### Key Issues Identified
1. **Scattered locations**: Logs spread across 5+ directories
2. **Inconsistent formatting**: Some use structured logging, others use print()
3. **No diagnostic logs**: Database health scripts output to console only
4. **Mixed verbosity**: Flow Monitor very verbose, others minimal
5. **UTF-8 handling**: Mostly good, but inconsistent

---

## Process-by-Process Inventory

### 1. Main Orchestrator (main.py)
**Log File:** `logs/orchestrator_{YYYY-MM-DD}.log`
**Format:** `%(asctime)s - %(levelname)s - %(message)s`
**Level:** INFO
**Console Output:** Yes (sys.stdout)
**Rotation:** Daily (by filename)

**Characteristics:**
- ✅ Well-structured logging
- ✅ UTF-8 encoding enforced
- ✅ Centralized location (logs/)
- ✅ Subprocess error tracking via `log_subprocess_error()`
- ⚠️ Very verbose - tracks every subprocess spawn and status
- ⚠️ Mixing logging with safe_print() for banner display

**Subprocess Spawns Tracked:**
- morning_view/morning_views.py
- strategies/earnings_intel/ei_main.py (3 modes)
- data/health/db_backup.py
- data/health/db_archive_sector.py
- tools/fmp_news_collector.py (missing - not found in codebase)

---

### 2. Flow Monitor (strategies/flow_monitor/fm_main.py)
**Log File:** `strategies/logs/fm_main_{YYYY-MM-DD}.log`
**Format:** `%(asctime)s - %(levelname)s - %(message)s`
**Level:** INFO (DEBUG available)
**Console Output:** Yes (via io.TextIOWrapper with UTF-8)
**Rotation:** Midnight, 7-day retention (TimedRotatingFileHandler)

**Characteristics:**
- ✅ Excellent UTF-8 handling (io.TextIOWrapper wrapper)
- ✅ Automatic rotation with backups
- ✅ Both file and console logging
- ✅ Colorized console output (ANSI codes)
- ⚠️ **VERY VERBOSE** - extensive beautification, banners, status boxes
- ⚠️ Logs in strategy subdirectory (not centralized)
- ⚠️ Uses custom `beautiful_log()` and `safe_log()` wrappers

**Additional Logging:**
- Health status tracking (FMHealthReporter)
- Performance tracking (FMPerformanceTracker)
- API budget monitoring

**Verbosity Assessment:** **OVER-LOGGING**
Real-time daemon during market hours (9:30 AM - 4:00 PM). Extensive status updates, emoji banners, progress tracking. Helpful for development but may be too much for production.

---

### 3. Option Pipeline (strategies/option_pipeline/op_main.py)
**Log File:** `strategies/option_pipeline/logs/oid_{YYYY-MM-DD}.log`
**Format:** `%(asctime)s - %(levelname)s - %(message)s`
**Date Format:** `%H:%M:%S`
**Level:** INFO (configurable)
**Console Output:** Yes (sys.stdout)
**Rotation:** None (daily by filename)

**Characteristics:**
- ✅ UTF-8 encoding enforced
- ✅ Both file and console logging
- ✅ Clean format with timestamps
- ⚠️ Logs in strategy subdirectory (not centralized)
- ⚠️ Timestamp format is time-only (no date in log entries)
- ✅ OIDHealthReporter for diagnostic tracking

**Verbosity Assessment:** **MODERATE**
Batch processing (morning 6:35 AM, evening ~5:00 PM). Reasonable detail without excessive output.

---

### 4. Earnings Intel (strategies/earnings_intel/ei_main.py)
**Log File:** `strategies/earnings_intel/logs/ei_{mode}_{timestamp}.log`
**Modes:** daily-pipeline, morning-scan, weekly-refresh
**Format:** `%(asctime)s - %(levelname)s - %(message)s`
**Date Format:** `%H:%M:%S`
**Level:** INFO (configurable)
**Console Output:** Yes (sys.stdout)
**Rotation:** None (unique timestamp per execution)

**Characteristics:**
- ✅ UTF-8 encoding enforced
- ✅ Mode-based log naming (ei_daily-pipeline_20251118_063500.log)
- ✅ Both file and console logging
- ⚠️ Logs in strategy subdirectory (not centralized)
- ⚠️ Timestamp in filename prevents easy log consolidation
- ⚠️ Time-only format (no date in log entries)

**Verbosity Assessment:** **MODERATE**
Scheduled tasks (daily 5 PM, morning 6:30 AM, Sunday weekly refresh). Good detail level.

---

### 5. Oracle (oracle/oracle_main.py)
**Log File:** `oracle/oracle_logs/oracle_main_{YYYY-MM-DD}.log`
**Format:** `%(asctime)s - %(levelname)s - %(message)s`
**Level:** INFO (DEBUG available)
**Console Output:** Only in debug mode
**Rotation:** Daily (by filename)

**Characteristics:**
- ✅ Clean daily log files
- ✅ Debug mode available
- ⚠️ Logs in oracle subdirectory (not centralized)
- ⚠️ No console output unless debug mode
- ⚠️ No UTF-8 encoding specified (potential Windows issue)
- ℹ️ Has session-based conversation logging (separate feature)

**Verbosity Assessment:** **MINIMAL**
Interactive CLI tool. Minimal logging by design (unless debug mode).

---

### 6. Database Backup (data/health/db_backup.py)
**Log File:** `logs/db_backup_{YYYY-MM-DD}.log`
**Format:** `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
**Level:** INFO
**Console Output:** Yes (sys.stdout)
**Rotation:** Daily (by filename)

**Characteristics:**
- ✅ Centralized location (logs/)
- ✅ UTF-8 encoding enforced
- ✅ Named logger ('db_backup')
- ✅ Both file and console logging
- ✅ Duplicate handler prevention
- ✅ Includes logger name in format (helpful for debugging)

**Verbosity Assessment:** **APPROPRIATE**
Scheduled task (~7:20 AM, ~5:45 PM, ~7:00 PM). Good detail without excess.

---

### 7. Database Archive (data/health/db_archive_sector.py)
**Log File:** **NONE** (console output only)
**Format:** print() statements with emojis
**Level:** N/A
**Console Output:** Yes (extensive print() with progress tracking)
**Rotation:** N/A

**Characteristics:**
- ❌ **NO FILE LOGGING** - all output to console only
- ❌ Not machine-parseable (emoji-heavy print statements)
- ⚠️ Progress tracking via print() during batch processing
- ⚠️ Extensive console output (batch progress, row counts, timings)
- ⚠️ Captured by main.py subprocess wrapper but not independently logged

**Verbosity Assessment:** **OVER-LOGGING (console)**
Friday night operation (6:30 PM → Monday 5:45 AM cutoff). Very verbose console output with emojis, but NO persistent log file.

**Critical Gap:** Long-running Friday archive operations produce no audit trail.

---

### 8. Database Optimization (data/health/db_optimize_sectors.py)
**Log File:** **NONE** (console output only)
**Format:** print() statements
**Level:** N/A
**Console Output:** Yes
**Rotation:** N/A

**Characteristics:**
- ❌ **NO FILE LOGGING**
- ❌ Console-only output
- ⚠️ No structured logging

**Verbosity Assessment:** **MINIMAL**
Runs ANALYZE on sector archives. Brief output.

---

### 9. Morning Views (morning_view/morning_views.py)
**Log File:** **NONE** (console output only)
**Format:** print() statements
**Level:** N/A
**Console Output:** Yes (captured by main.py subprocess)
**Rotation:** N/A

**Characteristics:**
- ❌ **NO FILE LOGGING**
- ❌ Console-only output
- ⚠️ Output captured by main.py subprocess wrapper
- ℹ️ Sends email (separate delivery mechanism)

**Verbosity Assessment:** **MINIMAL**
Morning watchlist generation (~7:00 AM). Brief console output.

---

### 10. Database Health Scripts (Other)
**Scripts:**
- db_archive_expired.py (deprecated)
- query_archives.py
- migrate_symbol_archive.py
- create_sector_archive.py

**Log Files:** **NONE** (all console output only)
**Format:** print() statements

**Characteristics:**
- ❌ No structured logging
- ❌ Console-only output
- ℹ️ Mostly utility/migration scripts (infrequent use)

---

## Log File Locations Summary

### Centralized (logs/)
1. `logs/orchestrator_{date}.log` - Main orchestrator
2. `logs/db_backup_{date}.log` - Database backup

### Strategy Subdirectories
3. `strategies/logs/fm_main_{date}.log` - Flow Monitor
4. `strategies/option_pipeline/logs/oid_{date}.log` - Option Pipeline
5. `strategies/earnings_intel/logs/ei_{mode}_{timestamp}.log` - Earnings Intel

### Oracle Subdirectory
6. `oracle/oracle_logs/oracle_main_{date}.log` - Oracle

### No Logging
7. data/health/db_archive_sector.py - **CONSOLE ONLY**
8. data/health/db_optimize_sectors.py - **CONSOLE ONLY**
9. morning_view/morning_views.py - **CONSOLE ONLY**
10. data/health/*.py (various utilities) - **CONSOLE ONLY**

---

## Verbosity Assessment

### Over-Logging
- **Flow Monitor (fm_main.py)**: Excessive beautification, status boxes, emoji banners. Real-time daemon generates very large log files during market hours.
- **Database Archive (db_archive_sector.py)**: Extremely verbose console output with batch progress, but NO file logging.

### Appropriate Logging
- **Database Backup (db_backup.py)**: Good balance of detail and conciseness
- **Option Pipeline (op_main.py)**: Reasonable detail for batch processing

### Under-Logging
- **Morning Views**: No file logging, minimal console output
- **Database Health Scripts**: No persistent logs, console-only
- **Oracle**: Minimal logging unless debug mode

---

## Critical Gaps

### 1. No Persistent Logs for Critical Operations
- **db_archive_sector.py**: Friday night multi-hour operation with NO log file
- **db_optimize_sectors.py**: Post-archive optimization with NO log file
- **morning_views.py**: Daily watchlist generation with NO log file

### 2. Scattered Log Locations
- 3 different strategy subdirectories
- 1 oracle subdirectory
- 1 centralized logs/ directory
- Makes comprehensive log review difficult

### 3. Inconsistent Formats
- Some use `%(asctime)s` with full date
- Some use `%H:%M:%S` time-only
- Some use print() statements only
- No consistent approach to error vs. info vs. debug

### 4. No Diagnostic Health Logs
- Database health scripts produce console output only
- No persistent diagnostic data for weekly review
- Autofix can't analyze what doesn't exist

### 5. Not Machine-Parseable
- Heavy use of emojis and beautification
- Status boxes and banners mixed with actual data
- Difficult to parse for automated analysis

---

## Recommendations for Standardization

### Phase 1: Immediate Wins (Low Effort, High Value)
1. **Add file logging to db_archive_sector.py** - Critical gap
2. **Centralize all logs to logs/** - Move strategy logs to logs/
3. **Standardize timestamp format** - Use full datetime in all logs

### Phase 2: Structure and Format (Medium Effort)
4. **Consistent log format** - Standardize across all processes
5. **Add structured diagnostic logging** - Separate human-readable from machine-parseable
6. **Implement log levels properly** - Use DEBUG/INFO/WARNING/ERROR consistently

### Phase 3: Advanced Features (Higher Effort)
7. **Automated log rotation** - Implement for all processes
8. **JSON-structured logging option** - For automated analysis
9. **Health check logs** - Dedicated diagnostic logs for weekly review

---

## Next Steps

1. Review this inventory with Ben
2. Prioritize which gaps to address first
3. Design standardized logging approach
4. Implement changes incrementally
5. Update Autofix to leverage new structured logs
