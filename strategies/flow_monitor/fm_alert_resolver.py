#!/usr/bin/env python3
"""
Flow Monitor Alert Resolver (fm_alert_resolver.py)
---------------------------------------------------
Resolves flow alert ambiguity by comparing next-day OI changes.

When a large volume flow alert occurs, we can't immediately tell if it's
opening new positions (bullish) or closing existing ones (bearish). The
next trading day's open interest reveals the truth.

Process:
1. Morning Option Pipeline collects fresh OI (6:35 AM)
2. FM Task 0 resolves yesterday's alerts (8:00 AM)
3. Compare alert volume vs OI change (fuzzy logic)
4. Classify: BUILDING (opening), CLOSING (exiting), NEUTRAL (churning)
5. Aggregate to symbol-level sentiment (recency-based)
6. Update watchlist with actionable intel

Created: 2026-01-07
Author: Ben (with Claude Code assistance)
"""

import logging
from datetime import datetime, timedelta
from tools.timezone_utils import now_eastern, eastern_isoformat
from tools.decimal_formatter import format_percentage
from tools.autofix import queue_error


def get_previous_trading_day(trade_date_str, op_storage):
    """
    Get previous trading day by querying database for most recent data.

    Args:
        trade_date_str: Current trade date (YYYY-MM-DD)
        op_storage: OIDStorage instance to query option_contracts

    Returns:
        str: Previous trade date (YYYY-MM-DD), or None if not found

    Note: Uses actual trading days from option_contracts table.
          Automatically skips weekends and holidays.
    """
    query = """
        SELECT MAX(trade_date) as prev_date
        FROM option_contracts
        WHERE trade_date < ?
    """

    result = op_storage.query_with_params(query, (trade_date_str,))

    if result and result[0] and result[0]['prev_date']:
        return result[0]['prev_date']

    # Fallback: simple calendar day subtraction if no data found
    logging.warning("No previous trading day found in database, using T-1 fallback")
    current = datetime.strptime(trade_date_str, '%Y-%m-%d')
    previous = current - timedelta(days=1)
    return previous.strftime('%Y-%m-%d')


def classify_oi_resolution(alert_volume, alert_oi, next_day_oi):
    """
    Fuzzy logic to determine if alert was opening or closing positions.

    Args:
        alert_volume: Volume from flow alert
        alert_oi: Open interest at time of alert
        next_day_oi: Open interest on T+1 trading day

    Returns:
        tuple: (resolution_type, oi_change, oi_change_pct)
               resolution_type: 'BUILDING', 'CLOSING', or 'NEUTRAL'

    Logic (Dual-Threshold):
        - Volume-based: OI change >= 50% of alert volume (catches large absolute moves)
        - Percentage-based: OI change >= 10% of existing OI (catches significant relative moves)
        - Either threshold triggers classification
        - Positive change → BUILDING (positions opened)
        - Negative change → CLOSING (positions closed)
        - Neither threshold met → NEUTRAL (churning, no clear signal)

    Rationale:
        - 50% volume accounts for intraday churning and multi-day position building
        - 10% OI change catches significant moves in large existing positions
        - Dual thresholds capture both types of real signals

    Examples:
        classify_oi_resolution(4000, 6000, 9500)
        → ('BUILDING', 3500, 58.33)  # 87.5% of volume → BUILDING

        classify_oi_resolution(4000, 6000, 2800)
        → ('CLOSING', -3200, -53.33)  # 80% of volume → CLOSING

        classify_oi_resolution(4000, 6000, 6500)
        → ('NEUTRAL', 500, 8.33)  # Only 12.5% of volume, 8.3% of OI → NEUTRAL

        classify_oi_resolution(2607, 1422, 3214)
        → ('BUILDING', 1792, 126.02)  # 68.7% of volume (miss old threshold)
                                       # BUT 126% of OI (pass new 10% threshold) → BUILDING
    """
    oi_change = next_day_oi - alert_oi
    oi_change_pct_raw = abs((oi_change / alert_oi * 100)) if alert_oi > 0 else 0
    oi_change_pct = format_percentage((oi_change / alert_oi * 100) if alert_oi > 0 else 0)

    # Dual thresholds: volume-based OR percentage-based
    volume_threshold = alert_volume * 0.50  # 50% of alert volume
    percentage_threshold = 10.0             # 10% of existing OI

    volume_test = abs(oi_change) >= volume_threshold
    percentage_test = oi_change_pct_raw >= percentage_threshold

    is_significant = volume_test or percentage_test

    # Classify based on OI change direction if significant
    if is_significant:
        if oi_change > 0:
            return 'BUILDING', oi_change, oi_change_pct
        else:
            return 'CLOSING', oi_change, oi_change_pct
    else:
        return 'NEUTRAL', oi_change, oi_change_pct


def resolve_yesterday_alerts(trade_date, fm_storage, op_storage):
    """
    Resolve yesterday's flow alerts using today's OI data.

    Args:
        trade_date: Today's date (YYYY-MM-DD) - same as OP just collected
        fm_storage: FlowMonitorStorage instance (has flow_alerts)
        op_storage: OIDStorage instance (has option_contracts with fresh OI)

    Returns:
        dict: Statistics {
            'alerts_resolved': 15,
            'building': 8,
            'closing': 4,
            'neutral': 3,
            'not_found': 0
        }

    Process:
        1. Get yesterday's trade_date (T-1)
        2. Query unresolved alerts from yesterday
        3. For each alert, lookup contract in today's option_contracts
        4. Apply fuzzy logic classification
        5. Batch update flow_alerts with resolutions
    """
    stats = {
        'alerts_resolved': 0,
        'building': 0,
        'closing': 0,
        'neutral': 0,
        'not_found': 0
    }

    try:
        # Get yesterday's trade date (previous trading day from database)
        yesterday = get_previous_trading_day(trade_date, op_storage)
        resolved_at = eastern_isoformat()

        logging.debug("ALERT RESOLUTION DIAGNOSTIC")
        logging.debug("  Trade Date (today): {}".format(trade_date))
        logging.debug("  Previous Trading Day: {}".format(yesterday))
        logging.debug("  Resolution Timestamp: {}".format(resolved_at))
        logging.debug("Resolving alerts from {} using OI from {}".format(yesterday, trade_date))

        # Query unresolved alerts from yesterday
        query = """
            SELECT
                id, contract_hash, symbol, strike, expiration_date, option_type,
                underlying_price, volume, open_interest, iv, last_price,
                significance_score, trade_date
            FROM flow_alerts
            WHERE trade_date = ?
              AND oi_resolution IS NULL
            ORDER BY symbol, strike
        """

        alerts_to_resolve = fm_storage.query_with_params(query, (yesterday,))

        logging.debug("Query returned {} alerts from {}".format(
            len(alerts_to_resolve) if alerts_to_resolve else 0, yesterday))

        if not alerts_to_resolve:
            logging.debug("No unresolved alerts found for {}".format(yesterday))
            return stats

        logging.debug("Found {} alerts to resolve from {}".format(len(alerts_to_resolve), yesterday))
        logging.debug("Sample alert: {} {} ${} {}".format(
            alerts_to_resolve[0]['symbol'],
            alerts_to_resolve[0]['option_type'],
            alerts_to_resolve[0]['strike'],
            alerts_to_resolve[0]['expiration_date']
        ) if len(alerts_to_resolve) > 0 else "N/A")

        # Prepare batch updates
        resolutions = []
        details = []  # Per-alert detail for console display
        processed_count = 0

        # Process each alert
        logging.debug("Beginning contract lookup in option_contracts table...")
        for alert in alerts_to_resolve:
            processed_count += 1
            symbol = alert['symbol']
            strike = alert['strike']
            expiration = alert['expiration_date']
            option_type = alert['option_type']
            alert_volume = alert['volume']
            alert_oi = alert['open_interest']
            alert_id = alert['id']

            # Lookup contract in today's option_contracts
            contract_query = """
                SELECT open_interest, underlying_price, iv, last_price
                FROM option_contracts
                WHERE trade_date = ?
                  AND symbol = ?
                  AND strike = ?
                  AND expiration_date = ?
                  AND option_type = ?
                LIMIT 1
            """

            # IMPORTANT: option_contracts stores option_type as UPPERCASE (CALL/PUT)
            # while flow_alerts stores it as lowercase (call/put)
            contract_result = op_storage.query_with_params(
                contract_query,
                (trade_date, symbol, strike, expiration, option_type.upper())
            )

            # Log every 10 contracts for progress tracking
            if processed_count % 10 == 0:
                logging.debug("  Processed {}/{} alerts...".format(processed_count, len(alerts_to_resolve)))

            if not contract_result:
                # Contract not found in today's data
                # Could be expired, delisted, or OP didn't collect it
                stats['not_found'] += 1
                logging.debug("Contract not found for alert {}: {} ${} {} {}".format(
                    alert_id, symbol, strike, option_type, expiration))
                continue

            next_day_oi = contract_result[0]['open_interest']

            # Apply fuzzy logic classification
            resolution_type, oi_change, oi_change_pct = classify_oi_resolution(
                alert_volume, alert_oi, next_day_oi
            )

            # Track stats
            stats['alerts_resolved'] += 1
            if resolution_type == 'BUILDING':
                stats['building'] += 1
            elif resolution_type == 'CLOSING':
                stats['closing'] += 1
            else:
                stats['neutral'] += 1

            # Prepare update
            resolutions.append({
                'id': alert_id,
                'next_day_oi': next_day_oi,
                'oi_resolution': resolution_type,
                'oi_change_contracts': oi_change,
                'oi_change_pct': oi_change_pct,
                'resolved_at': resolved_at
            })

            # Collect detail for console display
            details.append({
                'id': alert_id,
                'contract_hash': alert.get('contract_hash', ''),
                'symbol': symbol,
                'strike': strike,
                'expiration_date': expiration,
                'option_type': option_type,
                'significance_score': alert.get('significance_score', 0),
                'resolution': resolution_type,
                'oi_change': oi_change,
                # Alert-day fields
                'alert_date': alert.get('trade_date', yesterday),
                'alert_ul': alert.get('underlying_price'),
                'alert_oi': alert_oi,
                'alert_vol': alert_volume,
                'alert_iv': alert.get('iv'),
                'alert_last': alert.get('last_price'),
                # Today fields
                'today_ul': contract_result[0].get('underlying_price'),
                'today_oi': next_day_oi,
                'today_iv': contract_result[0].get('iv'),
                'today_last': contract_result[0].get('last_price'),
            })

            logging.debug("Resolved {}: ${} {} → {} (OI: {} → {}, change: {:+d})".format(
                symbol, strike, option_type, resolution_type,
                alert_oi, next_day_oi, oi_change
            ))

        # Batch update flow_alerts
        logging.debug("Preparing batch update: {} resolutions ready".format(len(resolutions)))
        if resolutions:
            logging.debug("Executing batch UPDATE on flow_alerts table...")
            update_sql = """
                UPDATE flow_alerts
                SET next_day_oi = ?,
                    oi_resolution = ?,
                    oi_change_contracts = ?,
                    oi_change_pct = ?,
                    resolved_at = ?
                WHERE id = ?
            """

            params_list = [
                (
                    r['next_day_oi'],
                    r['oi_resolution'],
                    r['oi_change_contracts'],
                    r['oi_change_pct'],
                    r['resolved_at'],
                    r['id']
                )
                for r in resolutions
            ]

            def batch_update_operation(conn):
                cursor = conn.cursor()
                cursor.executemany(update_sql, params_list)
                conn.commit()
                return True

            fm_storage._execute_with_retry(batch_update_operation)

            # Summary logging handled by caller (fm_main.py beautiful_log)

        # Dedup details by contract_hash — keep latest alert (highest id), track count
        deduped = {}
        for d in details:
            key = d['contract_hash']
            if key not in deduped:
                d['alert_count'] = 1
                deduped[key] = d
            else:
                deduped[key]['alert_count'] += 1
                if d['id'] > deduped[key]['id']:
                    count = deduped[key]['alert_count']
                    d['alert_count'] = count
                    deduped[key] = d

        stats['details'] = list(deduped.values())

        return stats

    except Exception as e:
        logging.error("Error resolving alerts: {}".format(e))

        # AUTOFIX: Queue error if resolution fails
        queue_error(
            error_type='alert_resolution_failed',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e),
                'trade_date': trade_date,
                'yesterday': get_previous_trading_day(trade_date, op_storage),
                'alerts_resolved': stats.get('alerts_resolved', 0),
                'building': stats.get('building', 0),
                'closing': stats.get('closing', 0),
                'neutral': stats.get('neutral', 0)
            },
            severity='ERROR'
        )
        return stats


def update_watchlist_sentiment(trade_date, fm_storage):
    """
    Update flow_watchlist_daily with symbol-level sentiment from resolved alerts.

    Args:
        trade_date: Current trade date (YYYY-MM-DD)
        fm_storage: FlowMonitorStorage instance

    Returns:
        dict: Statistics {symbols_updated, building, closing, neutral}

    Logic:
        - For each symbol in watchlist, find most recent resolution date
        - Count BUILDING vs CLOSING on that date only
        - Majority determines sentiment (ties = NEUTRAL)
        - Recent signals matter more than old ones
    """
    stats = {
        'symbols_updated': 0,
        'building': 0,
        'closing': 0,
        'neutral': 0
    }

    try:
        # Query active watchlist entries
        watchlist_query = """
            SELECT DISTINCT symbol, entry_date
            FROM flow_watchlist_daily
        """

        watchlist_symbols = fm_storage.query_with_params(watchlist_query, ())

        if not watchlist_symbols:
            logging.debug("No watchlist entries to update with sentiment")
            return stats

        logging.info("Updating sentiment for {} watchlist symbols".format(len(watchlist_symbols)))

        updates = []

        for entry in watchlist_symbols:
            symbol = entry['symbol']
            entry_date = entry['entry_date']

            # Calculate sentiment for this symbol
            sentiment, building_count, closing_count = calculate_symbol_sentiment(
                symbol, entry_date, trade_date, fm_storage
            )

            # Track stats
            stats['symbols_updated'] += 1
            if sentiment == 'BUILDING':
                stats['building'] += 1
            elif sentiment == 'CLOSING':
                stats['closing'] += 1
            else:
                stats['neutral'] += 1

            # Prepare update
            updates.append({
                'symbol': symbol,
                'entry_date': entry_date,
                'sentiment': sentiment,
                'building_count': building_count,
                'closing_count': closing_count
            })

        # Batch update watchlist
        if updates:
            update_sql = """
                UPDATE flow_watchlist_daily
                SET alert_sentiment = ?,
                    building_alerts_count = ?,
                    closing_alerts_count = ?
                WHERE symbol = ? AND entry_date = ?
            """

            params_list = [
                (
                    u['sentiment'],
                    u['building_count'],
                    u['closing_count'],
                    u['symbol'],
                    u['entry_date']
                )
                for u in updates
            ]

            def batch_update_operation(conn):
                cursor = conn.cursor()
                cursor.executemany(update_sql, params_list)
                conn.commit()
                return True

            fm_storage._execute_with_retry(batch_update_operation)

            # Summary logging handled by caller (fm_main.py beautiful_log)

        return stats

    except Exception as e:
        logging.error("Error updating watchlist sentiment: {}".format(e))

        # AUTOFIX: Queue error if sentiment update fails
        queue_error(
            error_type='watchlist_sentiment_update_failed',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e),
                'trade_date': trade_date,
                'symbols_updated': stats.get('symbols_updated', 0)
            },
            severity='WARNING'  # Non-critical - watchlist still works
        )
        return stats


def calculate_symbol_sentiment(symbol, entry_date, current_date, storage):
    """
    Calculate symbol sentiment based on most recent alert resolutions.

    Args:
        symbol: Stock symbol
        entry_date: Watchlist entry date (start of tracking window)
        current_date: Current trade date
        storage: FlowMonitorStorage instance

    Returns:
        tuple: (sentiment, building_count, closing_count)
               sentiment: 'BUILDING', 'CLOSING', or 'NEUTRAL'

    Logic:
        - Query resolved alerts from entry_date to current_date
        - Find most recent resolution date
        - Count BUILDING vs CLOSING on that date only
        - Majority wins, ties = NEUTRAL
        - Ignore old signals - recency matters most
    """
    # Query resolved alerts ordered by resolution date (most recent first)
    query = """
        SELECT
            DATE(resolved_at) as resolution_date,
            oi_resolution
        FROM flow_alerts
        WHERE symbol = ?
          AND trade_date >= ?
          AND trade_date <= ?
          AND oi_resolution IS NOT NULL
          AND oi_resolution != 'NEUTRAL'
        ORDER BY resolved_at DESC
    """

    alerts = storage.query_with_params(query, (symbol, entry_date, current_date))

    if not alerts:
        # No resolutions yet - all alerts still pending or all neutral
        return 'NEUTRAL', 0, 0

    # Get most recent resolution date
    most_recent_date = alerts[0]['resolution_date']

    # Filter to only alerts resolved on that date
    recent_resolutions = [
        a for a in alerts
        if a['resolution_date'] == most_recent_date
    ]

    # Count building vs closing on most recent date
    building = sum(1 for a in recent_resolutions if a['oi_resolution'] == 'BUILDING')
    closing = sum(1 for a in recent_resolutions if a['oi_resolution'] == 'CLOSING')

    # Determine sentiment from most recent day
    if building > closing:
        sentiment = 'BUILDING'
    elif closing > building:
        sentiment = 'CLOSING'
    else:
        sentiment = 'NEUTRAL'  # Tie or all neutral

    return sentiment, building, closing


# Module test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Flow Monitor Alert Resolver Module - Functions defined:")
    print("  - resolve_yesterday_alerts(trade_date, fm_storage, op_storage)")
    print("  - update_watchlist_sentiment(trade_date, fm_storage)")
    print("  - calculate_symbol_sentiment(symbol, entry_date, current_date, storage)")
    print("  - classify_oi_resolution(alert_volume, alert_oi, next_day_oi)")
    print("\nModule ready for integration into fm_main.py")
