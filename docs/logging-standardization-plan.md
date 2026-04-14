# Logging Standardization Plan
**Date:** 2025-11-18
**Goal:** Unified, centralized, machine-parseable logging system for all processes

---

## Design Principles

1. **Centralization**: All logs in `logs/` directory with clear naming
2. **Consistency**: Standard format, timestamp, and log levels across all processes
3. **Separation of Concerns**: Human-readable output separate from machine-parseable logs
4. **Diagnostic Depth**: Sufficient detail for automated weekly review and Autofix analysis
5. **Performance**: Minimal overhead for real-time processes (Flow Monitor)

---

## Proposed Standard Format

### File Naming Convention
```
logs/{process}_{YYYY-MM-DD}.log
```

**Examples:**
- `logs/orchestrator_2025-11-18.log`
- `logs/flow_monitor_2025-11-18.log`
- `logs/option_pipeline_2025-11-18.log`
- `logs/earnings_intel_2025-11-18.log`
- `logs/db_archive_2025-11-18.log`
- `logs/db_backup_2025-11-18.log`
- `logs/morning_views_2025-11-18.log`

### Log Entry Format
```
YYYY-MM-DD HH:MM:SS - LEVEL - [COMPONENT] - MESSAGE
```

**Example:**
```
2025-11-18 06:35:42 - INFO - [OID] - Starting morning pipeline for 800 symbols
2025-11-18 06:36:15 - INFO - [OID] - Processed batch 1/10 (80 symbols, 4,231 contracts)
2025-11-18 06:42:03 - WARNING - [OID] - Rate limit approaching: 145/250 API calls
2025-11-18 07:05:21 - INFO - [OID] - Pipeline complete: 800 symbols, 45,892 contracts
```

### Log Levels (Consistent Usage)
- **DEBUG**: Detailed diagnostic info (disabled by default)
- **INFO**: Normal operational messages (default level)
- **WARNING**: Noteworthy events that don't prevent operation
- **ERROR**: Errors that impact specific operations
- **CRITICAL**: System-level failures requiring immediate attention

---

## Proposed Directory Structure

```
E:\options_scanner\
├── logs/                          # CENTRALIZED LOG DIRECTORY
│   ├── orchestrator_2025-11-18.log
│   ├── flow_monitor_2025-11-18.log
│   ├── option_pipeline_2025-11-18.log
│   ├── earnings_intel_2025-11-18.log
│   ├── oracle_2025-11-18.log
│   ├── db_archive_2025-11-18.log  # NEW: currently console only
│   ├── db_backup_2025-11-18.log
│   ├── morning_views_2025-11-18.log  # NEW: currently console only
│   ├── diagnostic/                # NEW: Structured diagnostic logs
│   │   ├── flow_monitor_health_2025-11-18.json
│   │   ├── option_pipeline_health_2025-11-18.json
│   │   └── database_health_2025-11-18.json
│   └── archive/                   # Older logs (optional future rotation)
│       └── 2025-11/
│           └── [old logs moved here after 30 days]
```

**Changes:**
- Remove `strategies/logs/` - move to centralized `logs/`
- Remove `strategies/option_pipeline/logs/` - move to centralized `logs/`
- Remove `strategies/earnings_intel/logs/` - move to centralized `logs/`
- Remove `oracle/oracle_logs/` - move to centralized `logs/`
- Add `logs/diagnostic/` for structured JSON health reports

---

## Standard Logging Module (Shared Utility)

Create: `tools/standard_logger.py`

### Features
- Automatic log directory creation
- UTF-8 encoding enforcement
- Daily log file rotation by filename
- Console and file handlers
- Consistent formatting
- Component-based naming

### Usage Example
```python
from tools.standard_logger import setup_standard_logging

# In any process
logger = setup_standard_logging(
    process_name='flow_monitor',
    log_level='INFO',
    console_output=True
)

logger.info("Starting flow monitor daemon")
logger.warning("API rate limit approaching")
logger.error("Failed to fetch data for AAPL")
```

### Implementation Sketch
```python
import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_standard_logging(process_name, log_level='INFO', console_output=True, component=None):
    """
    Set up standardized logging for any process.

    Args:
        process_name: Name of process (e.g., 'flow_monitor', 'option_pipeline')
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_output: Whether to output to console
        component: Optional component name for log entries (e.g., 'collector', 'analyzer')

    Returns:
        logging.Logger: Configured logger instance
    """
    # Get project root
    project_root = Path(__file__).parent.parent
    logs_dir = project_root / 'logs'
    logs_dir.mkdir(exist_ok=True)

    # Create log filename
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_file = logs_dir / f"{process_name}_{date_str}.log"

    # Configure logger
    logger_name = f"{process_name}.{component}" if component else process_name
    logger = logging.getLogger(logger_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Standard format with component
    if component:
        log_format = '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    else:
        log_format = '%(asctime)s - %(levelname)s - [' + process_name.upper() + '] - %(message)s'

    formatter = logging.Formatter(
        log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logger.level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler (optional)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logger.level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
```

---

## Diagnostic Health Logs (Machine-Parseable)

Create: `tools/diagnostic_logger.py`

### Purpose
Separate from human-readable logs, these JSON files contain structured diagnostic data for:
- Weekly batch mode review
- Autofix analysis
- Performance monitoring
- Trend analysis

### Format
JSON with standardized keys:

```json
{
  "process": "flow_monitor",
  "date": "2025-11-18",
  "timestamp": "2025-11-18T16:05:23-05:00",
  "execution_summary": {
    "start_time": "2025-11-18T09:15:00-05:00",
    "end_time": "2025-11-18T16:05:23-05:00",
    "duration_seconds": 24923,
    "status": "completed"
  },
  "data_metrics": {
    "symbols_processed": 800,
    "scans_completed": 42,
    "alerts_generated": 87,
    "contracts_analyzed": 12453
  },
  "api_usage": {
    "fmp_calls": 149,
    "fmp_limit": 250,
    "tradier_calls": 2341,
    "rate_limit_hits": 0
  },
  "errors": [
    {
      "timestamp": "2025-11-18T14:23:12-05:00",
      "level": "WARNING",
      "component": "collector",
      "message": "Rate limit approaching: 145/250 calls",
      "context": {"symbol": "TSLA", "retry_count": 0}
    }
  ],
  "performance": {
    "avg_scan_duration_seconds": 25.3,
    "max_memory_mb": 456.2,
    "database_writes": 3421,
    "cache_hit_rate": 0.73
  }
}
```

### Usage Example
```python
from tools.diagnostic_logger import DiagnosticLogger

# In any process
diag = DiagnosticLogger('flow_monitor')

# Record metrics throughout execution
diag.record_metric('symbols_processed', 800)
diag.record_metric('api_calls', 149)
diag.record_error('WARNING', 'Rate limit approaching', context={'calls': 145})

# Write diagnostic log at end of execution
diag.write_diagnostic_log()
```

---

## Phase 1: Critical Gaps (Week 1)

### Goal: Add logging to processes with NO file logs

#### 1.1 Add Logging to db_archive_sector.py
**Current:** Console-only print() statements
**Target:** `logs/db_archive_{date}.log`

**Changes:**
```python
from tools.standard_logger import setup_standard_logging

logger = setup_standard_logging('db_archive', log_level='INFO', console_output=True)

# Replace print statements with logger calls
# Keep console output for real-time monitoring
# Add structured logging for audit trail
```

**Benefit:** Friday night archives will have persistent audit trail

#### 1.2 Add Logging to morning_views.py
**Current:** Console-only print() statements
**Target:** `logs/morning_views_{date}.log`

**Changes:**
```python
from tools.standard_logger import setup_standard_logging

logger = setup_standard_logging('morning_views', log_level='INFO', console_output=True)

# Log watchlist generation steps
# Track email delivery
# Record symbol counts and metrics
```

**Benefit:** Daily watchlist generation will have audit trail

#### 1.3 Add Logging to db_optimize_sectors.py
**Current:** Console-only print() statements
**Target:** `logs/db_optimize_{date}.log`

**Changes:**
```python
from tools.standard_logger import setup_standard_logging

logger = setup_standard_logging('db_optimize', log_level='INFO', console_output=True)

# Log optimization operations
# Track sector processing
# Record ANALYZE results
```

**Benefit:** Post-archive optimization will have audit trail

**Estimated Effort:** 2-3 hours
**Risk:** Low (additive changes, no removal of existing output)

---

## Phase 2: Centralization (Week 2)

### Goal: Move all strategy logs to centralized logs/ directory

#### 2.1 Update Flow Monitor (fm_main.py)
**Current:** `strategies/logs/fm_main_{date}.log`
**Target:** `logs/flow_monitor_{date}.log`

**Changes:**
```python
# In setup_logging()
logs_dir = Path(__file__).parent.parent.parent / "logs"  # Up to project root
logfile_name = f"flow_monitor_{datetime.now().strftime('%Y-%m-%d')}.log"
```

#### 2.2 Update Option Pipeline (op_main.py)
**Current:** `strategies/option_pipeline/logs/oid_{date}.log`
**Target:** `logs/option_pipeline_{date}.log`

**Changes:**
```python
# In setup_logging()
project_root = Path(__file__).parent.parent.parent
logs_dir = project_root / 'logs'
log_filename = f'option_pipeline_{trade_date}.log'
```

#### 2.3 Update Earnings Intel (ei_main.py)
**Current:** `strategies/earnings_intel/logs/ei_{mode}_{timestamp}.log`
**Target:** `logs/earnings_intel_{date}.log` (drop mode from filename)

**Changes:**
```python
# In setup_logging()
project_root = Path(__file__).parent.parent.parent
logs_dir = project_root / 'logs'
date_str = datetime.now().strftime('%Y-%m-%d')
log_filename = f'earnings_intel_{date_str}.log'

# Add mode to log entries instead of filename
logger.info(f"Starting Earnings Intel - Mode: {mode}")
```

#### 2.4 Update Oracle (oracle_main.py)
**Current:** `oracle/oracle_logs/oracle_main_{date}.log`
**Target:** `logs/oracle_{date}.log`

**Changes:**
```python
# In setup_logging()
log_dir = Path(__file__).parent.parent / 'logs'  # Up to project root
log_file = log_dir / f'oracle_{datetime.now().strftime("%Y-%m-%d")}.log'
```

**Estimated Effort:** 3-4 hours
**Risk:** Low (just path changes)

---

## Phase 3: Format Standardization (Week 3)

### Goal: Consistent format across all processes

#### 3.1 Implement Standard Logger Utility
Create `tools/standard_logger.py` (see above)

#### 3.2 Migrate Each Process to Standard Logger
- Replace custom logging setup with `setup_standard_logging()`
- Maintain existing console beautification if desired
- Ensure consistent timestamp format (full datetime)
- Add component tags where helpful

#### 3.3 Standardize Log Levels
- Review all logging calls
- Ensure INFO/WARNING/ERROR used appropriately
- Add DEBUG statements for troubleshooting (disabled by default)

**Estimated Effort:** 6-8 hours
**Risk:** Medium (requires testing each process)

---

## Phase 4: Diagnostic Health Logs (Week 4)

### Goal: Machine-parseable structured logs for automated analysis

#### 4.1 Implement Diagnostic Logger
Create `tools/diagnostic_logger.py` (see above)

#### 4.2 Add Diagnostic Logging to Key Processes
- Flow Monitor: Scan counts, alert metrics, API usage
- Option Pipeline: Symbol coverage, contract counts, processing time
- Earnings Intel: Event processing, snapshot timing, move calculations
- Database Archive: Row counts, duration, sector breakdown

#### 4.3 Configure Autofix to Parse Diagnostic Logs
Update Batch Mode weekly review to:
- Parse JSON diagnostic logs
- Identify anomalies (sudden drops, API limit hits, processing failures)
- Queue errors for investigation

**Estimated Effort:** 8-10 hours
**Risk:** Medium (new functionality)

---

## Phase 5: Polish and Automation (Week 5+)

### Optional Enhancements

#### 5.1 Automated Log Rotation
- Move logs older than 30 days to `logs/archive/YYYY-MM/`
- Compress archived logs (gzip)
- Scheduled cleanup script

#### 5.2 Log Analysis Dashboard
- Weekly summary report
- Trend analysis (API usage, processing times, error rates)
- Email digest for Ben

#### 5.3 Structured Exception Logging
- Capture stack traces in standardized format
- Link errors to Autofix queue entries
- Provide full context for debugging

---

## Migration Strategy

### Backward Compatibility
- Keep old log directories for 30 days
- Symlinks or duplicate logging during transition
- Gradual migration process-by-process

### Testing Plan
1. Test each process in isolation
2. Verify log files are created in correct location
3. Confirm console output still works
4. Check UTF-8 encoding with emoji test
5. Run full daily cycle and verify all logs present

### Rollback Plan
- Each phase is independent
- Can revert to old logging setup if issues arise
- Git commits for each phase

---

## Success Metrics

### Phase 1 Success
- [ ] db_archive_sector.py creates log file
- [ ] morning_views.py creates log file
- [ ] db_optimize_sectors.py creates log file
- [ ] All 3 processes maintain console output

### Phase 2 Success
- [ ] All logs in centralized logs/ directory
- [ ] Old log directories empty or removed
- [ ] No broken log file references

### Phase 3 Success
- [ ] Consistent timestamp format across all logs
- [ ] Standard log levels used appropriately
- [ ] All processes use standard_logger.py utility

### Phase 4 Success
- [ ] JSON diagnostic logs generated daily
- [ ] Autofix can parse diagnostic logs
- [ ] Weekly review includes diagnostic analysis

---

## Timeline

| Phase | Duration | Effort | Risk | Priority |
|-------|----------|--------|------|----------|
| Phase 1: Critical Gaps | Week 1 | 2-3 hrs | Low | **HIGH** |
| Phase 2: Centralization | Week 2 | 3-4 hrs | Low | **HIGH** |
| Phase 3: Format Standardization | Week 3 | 6-8 hrs | Med | **MEDIUM** |
| Phase 4: Diagnostic Logs | Week 4 | 8-10 hrs | Med | **MEDIUM** |
| Phase 5: Polish | Week 5+ | TBD | Low | **LOW** |

**Total Estimated Effort:** 19-25 hours core work

---

## Recommendation

**Start with Phase 1 immediately:**
1. Add logging to db_archive_sector.py (biggest gap - Friday night operations)
2. Add logging to morning_views.py (daily watchlist audit trail)
3. Add logging to db_optimize_sectors.py (post-archive audit trail)

**Then proceed with Phase 2:**
- Centralize all logs to logs/ directory
- Clean up scattered log locations

**Evaluate Phase 3+ based on Phase 1-2 results**

This phased approach:
- Addresses critical gaps first
- Minimizes risk with incremental changes
- Provides immediate value
- Allows evaluation before committing to full standardization
