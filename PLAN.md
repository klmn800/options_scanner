# Implementation Plan: Z-Score Dip Detection System

**Goal:** Replace flat 5% dip threshold with volatility-normalized z-score logic in Flow Monitor watchlist.

**Core Concept:** "Is price temporarily stretched relative to what smart money paid, in a way that is statistically unusual for this stock?"

---

## Summary

| Phase | Description | Files Changed | Estimated Effort |
|-------|-------------|---------------|------------------|
| 1 | RV Calculation Module | 2 new, 1 modify | ~2 hours |
| 2 | Evening Rollup Integration | 2 modify | ~1.5 hours |
| 3 | Z-Score Dip Detection | 3 modify, 1 new | ~2.5 hours |

**Total:** ~6 hours implementation + observation period

---

## Phase 1: Realized Volatility Calculation Infrastructure

### 1.1 Create RV Calculation Module

**File:** `tools/realized_volatility.py` (NEW)

**Purpose:** Calculate annualized realized volatility from daily log returns

**Key Functions:**
```python
def calculate_log_returns(prices: List[float]) -> List[float]:
    """Calculate log returns: ln(P_t / P_t-1)"""

def calculate_realized_volatility(log_returns: List[float], annualization_factor: int = 252) -> float:
    """Calculate annualized RV: std(returns) * sqrt(252)"""

def calculate_rv_from_prices(prices: List[float], lookback_days: int) -> Tuple[Optional[float], str]:
    """Safe wrapper with error handling, returns (rv, error_msg)"""

def calculate_rv_metrics(storage, symbol: str, trade_date: str, lookback_periods: List[int] = [5, 10]) -> Dict:
    """Main entry point - queries historical_prices and returns {'rv_5d': float, 'rv_10d': float}"""
```

**Data Source:** `historical_prices.close_price` (48.7K rows, daily OHLC)

**Error Handling:**
- Empty/insufficient price data → Return None (triggers fallback)
- Invalid prices (≤0) → Return None
- Unrealistic RV (>500% or <1%) → Return None
- Log warnings, never crash

### 1.2 Schema Migration for option_symbol_summary

**File:** `strategies/option_pipeline/migrations/add_rv_columns.py` (NEW)

**SQL Changes:**
```sql
ALTER TABLE option_symbol_summary ADD COLUMN rv_5d REAL DEFAULT NULL;
ALTER TABLE option_symbol_summary ADD COLUMN rv_10d REAL DEFAULT NULL;
```

**Apply to BOTH databases:**
- `data/datalake.db` (production)
- `data/datalake_query.db` (query)

### 1.3 Update Decimal Formatter

**File:** `tools/decimal_formatter.py` (MODIFY)

Add to `default_types` dictionary:
```python
'rv_5d': 'greek',   # 4 decimals (volatility metric)
'rv_10d': 'greek',  # 4 decimals
'z_score': 'score', # 2 decimals
```

---

## Phase 2: Integration into Evening Rollup

### 2.1 Add RV Calculation to Symbol Rollup

**File:** `strategies/option_pipeline/op_symbol_rollup.py` (MODIFY)

**New Method:**
```python
def _calculate_realized_volatility(self, contracts, symbol, trade_date) -> Dict:
    """Calculate RV metrics from historical prices

    Returns: {'rv_5d': float, 'rv_10d': float} or None values
    """
    from tools.realized_volatility import calculate_rv_metrics
    return calculate_rv_metrics(self.storage, symbol, trade_date, [5, 10])
```

**Integration Point:** After IV bucket calculation (~line 970), before Greek exposure
```python
# Calculate realized volatility metrics
rv_metrics = self._calculate_realized_volatility(contracts, symbol, trade_date)
summary.update(rv_metrics)  # Adds rv_5d, rv_10d to symbol summary
```

**Performance:** +800 queries (one per symbol), ~10-15 seconds additional processing

### 2.2 Verification Query

After first evening rollup:
```sql
SELECT symbol, trade_date, rv_5d, rv_10d, iv_front_month
FROM option_symbol_summary
WHERE trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
  AND rv_5d IS NOT NULL
ORDER BY rv_5d DESC
LIMIT 10;
```

**Expected:** High-vol stocks (TSLA, NVDA) show rv_5d > 0.30, low-vol (MRK, KO) show < 0.20

---

## Phase 3: Z-Score Dip Detection

### 3.1 Schema Migration for flow_watchlist_daily

**File:** `strategies/flow_monitor/migrations/add_zscore_columns.py` (NEW)

**SQL Changes (both tables):**
```sql
-- flow_watchlist_daily
ALTER TABLE flow_watchlist_daily ADD COLUMN rv_5d REAL DEFAULT NULL;
ALTER TABLE flow_watchlist_daily ADD COLUMN z_score REAL DEFAULT NULL;
ALTER TABLE flow_watchlist_daily ADD COLUMN dip_threshold_used REAL DEFAULT NULL;

-- flow_watchlist_daily_archive (same columns)
ALTER TABLE flow_watchlist_daily_archive ADD COLUMN rv_5d REAL DEFAULT NULL;
ALTER TABLE flow_watchlist_daily_archive ADD COLUMN z_score REAL DEFAULT NULL;
ALTER TABLE flow_watchlist_daily_archive ADD COLUMN dip_threshold_used REAL DEFAULT NULL;
```

### 3.2 Configuration

**File:** `strategies/flow_monitor/fm_config.py` (MODIFY)

**New Method:**
```python
def get_dip_thresholds(self):
    """Return dip detection threshold parameters"""
    defaults = {
        'use_zscore_detection': True,
        'zscore_threshold': -1.50,              # -1.5 sigma
        'fallback_percentage_threshold': -5.0,  # When RV missing
        'rv_cap': 0.12,                         # Cap at 12% daily vol
        'min_rv_for_zscore': 0.05,              # Below 5%, use fallback
    }
    return {**defaults, **self.flow_monitor_config.get('dip_detection', {})}
```

**Config.json Addition:**
```json
{
  "flow_monitor": {
    "dip_detection": {
      "use_zscore_detection": true,
      "zscore_threshold": -1.50,
      "fallback_percentage_threshold": -5.0,
      "rv_cap": 0.12,
      "min_rv_for_zscore": 0.05
    }
  }
}
```

### 3.3 Z-Score Detection Logic

**File:** `strategies/flow_monitor/fm_watchlist.py` (MODIFY)

**Function:** `update_prices_and_detect()` (lines ~176-407)

**Z-Score Formula (CRITICAL - units must be correct):**
```python
# Convert return volatility to price-space volatility
rv_effective = min(rv_5d, rv_cap)  # Cap at 12%
sigma_price = rv_effective * entry_anchor_price

# Calculate z-score
z_score = (current_price - entry_anchor_price) / sigma_price
```

**Detection Logic:**
```python
# CALL alerts: Want price drops (negative z-score)
if option_type == 'CALL' and z_score <= zscore_threshold:  # e.g., <= -1.5
    dip_detected = True

# PUT alerts: Want price rises (positive z-score)
elif option_type == 'PUT' and z_score >= -zscore_threshold:  # e.g., >= +1.5
    dip_detected = True

# MIXED: Either direction
elif option_type == 'MIXED' and abs(z_score) >= abs(zscore_threshold):
    dip_detected = True
```

**Fallback Logic:**
```python
# Use percentage threshold if:
# - RV data missing (rv_5d is None)
# - RV too low (rv_5d < 0.05) - stock barely moves
if rv_5d is None or rv_5d < min_rv_for_zscore:
    # Fall back to flat 5% logic (existing behavior)
    use_percentage_fallback = True
```

**Data Flow:**
1. Query active watchlist entries
2. LEFT JOIN `option_symbol_summary` to get latest `rv_5d`
3. For each entry: calculate z-score, compare to threshold
4. Update `z_score`, `rv_5d`, `dip_threshold_used` columns
5. `price_diff_pct` column REMAINS populated (user visibility)

### 3.4 Email Notification Update

**Same file, email body section:**

Add z-score info to email:
```
Symbol: TSLA
Entry: $250.00 → Current: $228.50
Change: -8.60%
Z-Score: -1.43σ
RV (5d): 45.2%
Type: CALL
```

### 3.5 Archive Function Update

**Same file, `archive_expired_entries()`:**

Add new columns to INSERT statement for archive table.

---

## What This Achieves

### Before (Flat 5%)
| Stock | Entry | 5% Threshold | Problem |
|-------|-------|--------------|---------|
| TSLA | $250 | $237.50 | Normal volatility, triggers too often |
| MRK | $100 | $95.00 | Low vol stock, never triggers |

### After (Z-Score Normalized)
| Stock | Entry | RV (5d) | σ_price | -1.5σ Threshold | Result |
|-------|-------|---------|---------|-----------------|--------|
| TSLA | $250 | 45% (capped→12%) | $30 | $205 (-18%) | Fewer false positives |
| MRK | $100 | 15% | $15 | $77.50 (-22.5%) | Catches real opportunities |

**Key Insight:** Same statistical significance (-1.5σ), different dollar thresholds appropriate for each stock's volatility profile.

---

## Database Changes Summary

### option_symbol_summary (existing table, +2 columns)
| Column | Type | Precision | Source |
|--------|------|-----------|--------|
| rv_5d | REAL | 4 decimals | Calculated from historical_prices |
| rv_10d | REAL | 4 decimals | Calculated from historical_prices |

### flow_watchlist_daily (existing table, +3 columns)
| Column | Type | Precision | Purpose |
|--------|------|-----------|---------|
| rv_5d | REAL | 4 decimals | Snapshot of RV at detection time |
| z_score | REAL | 2 decimals | Current z-score (sortable!) |
| dip_threshold_used | REAL | 2 decimals | Threshold that triggered dip |

### flow_watchlist_daily_archive (same +3 columns)
For historical analysis of dip detection effectiveness.

---

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_zscore_detection` | true | Enable z-score logic |
| `zscore_threshold` | -1.50 | Trigger at -1.5 sigma |
| `fallback_percentage_threshold` | -5.0 | Use when RV missing |
| `rv_cap` | 0.12 | Cap RV at 12% (prevent meme chaos) |
| `min_rv_for_zscore` | 0.05 | Below 5% RV, use percentage |

---

## Rollback Plan

**Quick Rollback (config change):**
```json
{ "dip_detection": { "use_zscore_detection": false } }
```
Instantly reverts to 5% logic while keeping z-score columns populated for analysis.

**Full Rollback (if needed):**
```sql
ALTER TABLE option_symbol_summary DROP COLUMN rv_5d;
ALTER TABLE option_symbol_summary DROP COLUMN rv_10d;
ALTER TABLE flow_watchlist_daily DROP COLUMN rv_5d;
ALTER TABLE flow_watchlist_daily DROP COLUMN z_score;
ALTER TABLE flow_watchlist_daily DROP COLUMN dip_threshold_used;
```

---

## Future Enhancements (Deferred)

### IV Filter (v1.1)
The analyst suggested: "RV ≤ IV" as a soft filter to avoid information events.

**Concept:** If realized volatility exceeds implied volatility, the stock is moving MORE than options are pricing - could indicate news-driven moves that won't revert.

**Implementation:** Add optional check:
```python
if rv_5d > iv_front_month:
    # Skip dip detection - likely information event
    pass
```

**Status:** Deferred until we observe z-score behavior. Will revisit after 2-3 weeks of data.

### Reversion Speed Heuristic (v1.2)
Track how quickly detected dips actually revert. Could inform threshold tuning.

---

## Implementation Sequence

1. **Phase 1** (~2 hours)
   - Create `tools/realized_volatility.py`
   - Run migration `add_rv_columns.py`
   - Update `decimal_formatter.py`
   - Unit test RV calculations

2. **Phase 2** (~1.5 hours)
   - Modify `op_symbol_rollup.py`
   - Run evening rollup
   - Verify RV values in database

3. **Phase 3** (~2.5 hours)
   - Run migration `add_zscore_columns.py`
   - Add config to `fm_config.py`
   - Modify `fm_watchlist.py` detection logic
   - Update email format
   - Update archive function
   - Test with simulated prices

4. **Observation** (ongoing)
   - Monitor z-score distribution
   - Compare old vs new detection triggers
   - Tune threshold if needed (-1.5σ → -1.25σ?)

---

## Success Criteria

- [ ] RV values present for >95% of symbols after evening rollup
- [ ] Z-score calculated for all watchlist entries with RV
- [ ] Fallback working for entries without RV
- [ ] `price_diff_pct` column still populated (user visibility)
- [ ] Email includes z-score information
- [ ] Configurable threshold working
- [ ] No increase in error rates
- [ ] Processing time increase <10%
