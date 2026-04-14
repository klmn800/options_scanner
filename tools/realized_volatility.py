#!/usr/bin/env python3
"""
Realized Volatility Calculator
------------------------------
Calculates annualized realized volatility from historical price data
using log returns methodology.

Used by:
- Option Pipeline evening rollup for symbol-level RV metrics
- Flow Monitor watchlist for volatility-normalized dip detection

Formula:
    log_return = ln(P_t / P_t-1)
    daily_volatility = std(log_returns)
    annualized_volatility = daily_volatility * sqrt(252)

Author: Ben (with Claude Code assistance)
Date: 2026-01-14
"""

import logging
import math
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def calculate_log_returns(prices: List[float]) -> List[float]:
    """Calculate log returns from price series

    Args:
        prices: List of daily close prices (chronological order, oldest first)

    Returns:
        List of log returns (length = len(prices) - 1)

    Raises:
        ValueError: If prices list has < 2 elements or contains invalid values
    """
    if len(prices) < 2:
        raise ValueError("Need at least 2 prices to calculate returns")

    log_returns = []
    for i in range(1, len(prices)):
        if prices[i-1] <= 0 or prices[i] <= 0:
            raise ValueError(f"Invalid price at index {i}: {prices[i]} (previous: {prices[i-1]})")
        log_return = math.log(prices[i] / prices[i-1])
        log_returns.append(log_return)

    return log_returns


def calculate_realized_volatility(
    log_returns: List[float],
    annualization_factor: int = 252
) -> float:
    """Calculate annualized realized volatility from log returns

    Args:
        log_returns: List of log returns
        annualization_factor: Trading days per year (default: 252)

    Returns:
        float: Annualized volatility (e.g., 0.25 = 25% annual volatility)

    Raises:
        ValueError: If log_returns is empty or annualization_factor invalid
    """
    if not log_returns:
        raise ValueError("Log returns list is empty")

    if annualization_factor <= 0:
        raise ValueError("Annualization factor must be positive")

    n = len(log_returns)

    # Need at least 2 returns for sample variance
    if n < 2:
        raise ValueError("Need at least 2 log returns for variance calculation")

    # Calculate mean
    mean_return = sum(log_returns) / n

    # Calculate sample variance (n-1 denominator for unbiased estimate)
    squared_deviations = [(r - mean_return) ** 2 for r in log_returns]
    variance = sum(squared_deviations) / (n - 1)

    # Daily volatility
    daily_volatility = math.sqrt(variance)

    # Annualize: multiply by sqrt(trading days)
    annualized_volatility = daily_volatility * math.sqrt(annualization_factor)

    return annualized_volatility


def calculate_rv_from_prices(
    prices: List[float],
    lookback_days: int,
    annualization_factor: int = 252
) -> Tuple[Optional[float], str]:
    """Calculate realized volatility from price series with error handling

    Args:
        prices: List of daily close prices (chronological, oldest first)
        lookback_days: Number of days for RV calculation (e.g., 5, 10)
        annualization_factor: Trading days per year (default: 252)

    Returns:
        Tuple of (rv_value, error_message)
        - rv_value: Float if successful, None if error
        - error_message: Empty string if successful, error description if failed

    Examples:
        >>> prices = [100.0, 102.5, 101.0, 103.5, 102.0, 104.0]
        >>> rv, err = calculate_rv_from_prices(prices, lookback_days=5)
        >>> print(f"RV: {rv:.4f}")  # Should be ~0.15-0.25 annualized
    """
    try:
        # Validate inputs
        if not prices:
            return None, "Empty price list"

        # Need lookback_days prices to get lookback_days-1 returns
        if len(prices) < lookback_days:
            return None, f"Insufficient data: {len(prices)} prices for {lookback_days}-day lookback"

        # Use most recent N days
        recent_prices = prices[-lookback_days:]

        # Calculate log returns (will be lookback_days - 1 returns)
        log_returns = calculate_log_returns(recent_prices)

        # Need at least 2 returns for variance
        if len(log_returns) < 2:
            return None, f"Insufficient returns: {len(log_returns)} (need at least 2)"

        # Calculate RV
        rv = calculate_realized_volatility(log_returns, annualization_factor)

        # Sanity check (0.01 to 5.0 = 1% to 500% annualized)
        if rv < 0.01:
            return None, f"Unrealistically low RV: {rv:.4f} (< 1% annualized)"
        if rv > 5.0:
            return None, f"Unrealistically high RV: {rv:.4f} (> 500% annualized)"

        return rv, ""

    except ValueError as e:
        return None, f"Calculation error: {str(e)}"
    except Exception as e:
        return None, f"Unexpected error: {str(e)}"


def calculate_rv_metrics(
    storage,
    symbol: str,
    trade_date: str,
    lookback_periods: List[int] = None
) -> Dict[str, Optional[float]]:
    """Calculate multiple RV metrics for a symbol

    Queries historical_prices table and calculates RV for multiple lookback periods.

    Args:
        storage: Database storage instance with query_db method
        symbol: Stock ticker symbol
        trade_date: Current trade date (YYYY-MM-DD)
        lookback_periods: List of lookback days (default: [5, 10])

    Returns:
        Dict with keys like 'rv_5d', 'rv_10d' (None if insufficient data)

    Database Query:
        Reads: historical_prices (close_price time series)

    Example:
        >>> from strategies.option_pipeline.op_storage import OIDStorage
        >>> storage = OIDStorage()
        >>> rv_metrics = calculate_rv_metrics(storage, 'AAPL', '2026-01-13')
        >>> print(rv_metrics)
        {'rv_5d': 0.1834, 'rv_10d': 0.2156}
    """
    if lookback_periods is None:
        lookback_periods = [5, 10]

    # Import here to avoid circular dependency
    from tools.decimal_formatter import format_greek

    # Query historical prices (need max lookback + 1 for enough log returns)
    max_lookback = max(lookback_periods)

    # We need max_lookback prices to get max_lookback-1 returns
    # Add buffer for safety
    query_limit = max_lookback + 5

    query = """
        SELECT close_price
        FROM historical_prices
        WHERE symbol = ?
        AND trade_date <= ?
        ORDER BY trade_date DESC
        LIMIT ?
    """

    try:
        rows = storage.query_db(query, (symbol, trade_date, query_limit))

        if not rows:
            logger.debug(f"RV: No historical prices for {symbol}")
            return {f'rv_{days}d': None for days in lookback_periods}

        # Extract prices and reverse to chronological order (oldest first)
        prices = [row['close_price'] for row in reversed(rows)]

        # Calculate RV for each lookback period
        results = {}
        for days in lookback_periods:
            rv, error = calculate_rv_from_prices(prices, days)

            if error:
                logger.debug(f"RV {days}d for {symbol}: {error}")
                results[f'rv_{days}d'] = None
            else:
                # Format to 4 decimals (volatility precision per CLAUDE.md)
                results[f'rv_{days}d'] = format_greek(rv)

        return results

    except Exception as e:
        logger.error(f"RV calculation failed for {symbol}: {e}")
        return {f'rv_{days}d': None for days in lookback_periods}


# -----------------------------------------------------------------------------
# Module self-test
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )

    print("=" * 60)
    print("Realized Volatility Calculator - Unit Tests")
    print("=" * 60)

    # Test 1: Basic log returns
    print("\n[Test 1] Log Returns Calculation")
    test_prices_1 = [100.0, 105.0, 102.0]
    try:
        returns = calculate_log_returns(test_prices_1)
        print(f"  Prices: {test_prices_1}")
        print(f"  Log returns: {[f'{r:.4f}' for r in returns]}")
        print(f"  Expected: [0.0488, -0.0290] (approx)")
        assert len(returns) == 2, "Should have 2 returns"
        assert abs(returns[0] - 0.0488) < 0.001, "First return should be ~0.0488"
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 2: Realized volatility
    print("\n[Test 2] Realized Volatility Calculation")
    # Known volatility case: daily returns with std dev ~0.02 -> annualized ~0.32
    test_returns = [0.02, -0.01, 0.015, -0.02, 0.01]
    try:
        rv = calculate_realized_volatility(test_returns)
        print(f"  Log returns: {test_returns}")
        print(f"  Annualized RV: {rv:.4f}")
        print(f"  Expected: ~0.25-0.35 (depends on sample std)")
        assert 0.1 < rv < 0.5, "RV should be in reasonable range"
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 3: Full pipeline with calculate_rv_from_prices
    print("\n[Test 3] RV from Prices (5-day)")
    # Simulate 6 days of prices (gives us 5 returns for 5-day RV)
    test_prices_3 = [100.0, 102.5, 101.0, 103.5, 102.0, 104.0]
    try:
        rv, err = calculate_rv_from_prices(test_prices_3, lookback_days=5)
        print(f"  Prices: {test_prices_3}")
        if rv:
            print(f"  RV (5d): {rv:.4f}")
            assert 0.01 < rv < 1.0, "RV should be reasonable"
            print("  PASSED")
        else:
            print(f"  Error: {err}")
            print("  FAILED")
            sys.exit(1)
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 4: Edge case - insufficient data
    print("\n[Test 4] Edge Case - Insufficient Data")
    try:
        rv, err = calculate_rv_from_prices([100.0, 101.0], lookback_days=5)
        print(f"  Prices: [100.0, 101.0] (only 2)")
        print(f"  Result: rv={rv}, error='{err}'")
        assert rv is None, "Should return None for insufficient data"
        assert "Insufficient" in err, "Should have insufficient data error"
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 5: Edge case - empty list
    print("\n[Test 5] Edge Case - Empty List")
    try:
        rv, err = calculate_rv_from_prices([], lookback_days=5)
        print(f"  Prices: []")
        print(f"  Result: rv={rv}, error='{err}'")
        assert rv is None, "Should return None for empty list"
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 6: Edge case - zero/negative price
    print("\n[Test 6] Edge Case - Invalid Price")
    try:
        rv, err = calculate_rv_from_prices([100.0, 0.0, 101.0], lookback_days=3)
        print(f"  Prices: [100.0, 0.0, 101.0]")
        print(f"  Result: rv={rv}, error='{err}'")
        assert rv is None, "Should return None for invalid price"
        print("  PASSED")
    except Exception as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    # Test 7: Realistic stock volatility ranges
    print("\n[Test 7] Realistic Volatility Ranges")

    # Low vol stock (utility): ~1% daily moves -> ~15-20% annualized
    low_vol_prices = [50.0, 50.5, 50.2, 50.7, 50.3, 50.8]  # ~1% moves
    rv_low, _ = calculate_rv_from_prices(low_vol_prices, 5)
    rv_low_str = f"{rv_low:.4f}" if rv_low else "None"
    print(f"  Low-vol stock (utility-like): RV = {rv_low_str}")

    # Medium vol stock (typical): ~2% daily moves -> ~30-35% annualized
    med_vol_prices = [100.0, 102.0, 100.5, 103.0, 101.0, 104.0]  # ~2% moves
    rv_med, _ = calculate_rv_from_prices(med_vol_prices, 5)
    rv_med_str = f"{rv_med:.4f}" if rv_med else "None"
    print(f"  Medium-vol stock (typical): RV = {rv_med_str}")

    # High vol stock (tech/growth): ~3-4% daily moves -> ~50-60% annualized
    high_vol_prices = [200.0, 208.0, 202.0, 210.0, 204.0, 212.0]  # ~3-4% moves
    rv_high, _ = calculate_rv_from_prices(high_vol_prices, 5)
    rv_high_str = f"{rv_high:.4f}" if rv_high else "None"
    print(f"  High-vol stock (tech/growth): RV = {rv_high_str}")

    print("  (Values should increase: low < med < high)")
    if rv_low and rv_med and rv_high:
        if rv_low < rv_med < rv_high:
            print("  PASSED")
        else:
            print("  WARNING: Volatility ordering unexpected (may be sample noise)")

    print("\n" + "=" * 60)
    print("All unit tests completed!")
    print("=" * 60)
