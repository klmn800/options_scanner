#!/usr/bin/env python3
"""
Flow Monitor Watchlist (fm_watchlist.py)
-----------------------------------------
Symbol-level price tracking for buy-the-dip detection.

Tracks symbols that have generated flow alerts and monitors for price drops
that present buying opportunities. Uses daily staggered entries to avoid
mental lock-in on single entry points.

Features:
- Daily entry creation when alerts fire
- Automatic price update from scan data
- Buy-the-dip detection (5% threshold)
- Call/Put/Mixed directionality handling
- 7-day automatic expiration
- Archive for historical pattern analysis

Created: 2026-01-06
Author: Ben (with Claude Code assistance)
"""

import logging
from datetime import datetime, timedelta
from tools.timezone_utils import now_eastern, eastern_isoformat, eastern_date_string
from tools.decimal_formatter import format_percentage, format_score, format_greek
from tools.autofix import queue_error
from tools.email_notifier import send_email
from tools.log_utils import beautiful_log
from strategies.flow_monitor.fm_config import FMConfig


def _fetch_earnings_lookup(storage, symbols, trade_date):
    """Fetch earnings proximity for a list of symbols.

    Queries earnings_upcoming for each symbol's next earnings date and computes
    days_to_earnings relative to trade_date. Returns dict keyed by symbol.

    Reads: earnings_upcoming
    """
    if not symbols:
        return {}

    try:
        placeholders = ','.join('?' for _ in symbols)
        query = """
            SELECT symbol, earnings_date, earnings_time,
                   earnings_play_signal, relative_underpricing_pct
            FROM earnings_upcoming
            WHERE symbol IN ({})
              AND earnings_date >= ?
        """.format(placeholders)

        params = list(symbols) + [trade_date]
        rows = storage.query_with_params(query, params)

        if not rows:
            return {}

        trade_date_obj = datetime.strptime(trade_date, '%Y-%m-%d')
        lookup = {}
        for row in rows:
            sym = row['symbol']
            e_date = row['earnings_date']
            e_time = row['earnings_time']
            try:
                e_date_obj = datetime.strptime(e_date, '%Y-%m-%d')
                days = (e_date_obj - trade_date_obj).days
                lookup[sym] = {
                    'earnings_date': e_date,
                    'days_to_earnings': days,
                    'earnings_time': e_time,
                    'earnings_play_signal': row.get('earnings_play_signal'),
                    'relative_underpricing_pct': row.get('relative_underpricing_pct'),
                }
            except (ValueError, TypeError):
                continue

        return lookup

    except Exception as e:
        logging.warning("Failed to fetch earnings lookup: {}".format(e))
        return {}


def update_daily_watchlist(trade_date, storage, scan_timestamp):
    """Create or update watchlist entries from new alerts

    Args:
        trade_date: Trading date string (YYYY-MM-DD)
        storage: FlowMonitorStorage instance
        scan_timestamp: Scan timestamp to query alerts from

    Returns:
        dict: Statistics (entries_created, entries_updated, total_alerts_processed)
    """
    stats = {
        'entries_created': 0,
        'entries_updated': 0,
        'total_alerts_processed': 0,
        'created_symbols': [],  # Symbols with new watchlist entries (for news enrichment)
    }

    # Idempotent column migration for earnings signal enrichment (PRD 0008)
    try:
        def _migrate_columns(conn):
            for col_def in [
                "earnings_play_signal TEXT",
                "relative_underpricing_pct REAL",
            ]:
                try:
                    conn.execute(
                        "ALTER TABLE flow_watchlist_daily ADD COLUMN {}".format(col_def))
                except Exception:
                    pass  # "duplicate column name" — already exists
            return True
        storage._execute_with_retry(_migrate_columns)
    except Exception:
        pass  # Non-fatal — columns may already exist

    try:
        # Query alerts from this scan
        query = """
            SELECT
                id, symbol, underlying_price, option_type, significance_score
            FROM flow_alerts
            WHERE scan_timestamp = ?
            ORDER BY significance_score DESC
        """

        new_alerts = storage.query_with_params(query, (scan_timestamp,))

        if not new_alerts:
            logging.debug("No alerts found for scan timestamp: {}".format(scan_timestamp))
            return stats

        stats['total_alerts_processed'] = len(new_alerts)

        # Calculate expiration date (7 days from entry_date)
        entry_date_obj = datetime.strptime(trade_date, '%Y-%m-%d')
        expiration_date_obj = entry_date_obj + timedelta(days=7)
        expiration_date = expiration_date_obj.strftime('%Y-%m-%d')

        current_time = eastern_isoformat()

        # Pre-fetch earnings data for all symbols in this scan
        alert_symbols = list(set(a['symbol'] for a in new_alerts))
        earnings_lookup = _fetch_earnings_lookup(storage, alert_symbols, trade_date)

        # Process each alert
        for alert in new_alerts:
            symbol = alert['symbol']
            underlying_price = alert['underlying_price']
            option_type = alert['option_type']
            alert_id = alert['id']
            significance_score = alert['significance_score']

            # Check if entry already exists for this symbol today
            check_query = """
                SELECT id, option_type, alert_count_today, max_significance_score
                FROM flow_watchlist_daily
                WHERE symbol = ? AND entry_date = ?
            """

            existing = storage.query_with_params(check_query, (symbol, trade_date))

            if not existing:
                # Look up earnings proximity for this symbol
                earnings_info = earnings_lookup.get(symbol, {})
                earnings_date = earnings_info.get('earnings_date')
                days_to_earnings = earnings_info.get('days_to_earnings')
                earnings_time = earnings_info.get('earnings_time')
                earnings_play_signal = earnings_info.get('earnings_play_signal')
                relative_underpricing_pct = earnings_info.get('relative_underpricing_pct')

                # CREATE new entry
                insert_sql = """
                    INSERT INTO flow_watchlist_daily (
                        symbol, entry_date, entry_expiration_date,
                        entry_ul_price, current_ul_price, price_diff_pct,
                        option_type, first_alert_id, alert_count_today, max_significance_score,
                        dip_detected, earnings_date, days_to_earnings, earnings_time,
                        earnings_play_signal, relative_underpricing_pct,
                        created_at, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """

                def create_operation(conn):
                    conn.execute(insert_sql, (
                        symbol, trade_date, expiration_date,
                        underlying_price, underlying_price, 0.0,
                        option_type.upper(), alert_id, 1, significance_score,
                        0, earnings_date, days_to_earnings, earnings_time,
                        earnings_play_signal, relative_underpricing_pct,
                        current_time, current_time
                    ))
                    conn.commit()
                    return True

                if storage._execute_with_retry(create_operation):
                    stats['entries_created'] += 1
                    stats['created_symbols'].append(symbol)
                    logging.debug("Created watchlist entry: {} at ${:.2f}".format(symbol, underlying_price))

            else:
                # UPDATE existing entry
                entry = existing[0]
                existing_type = entry['option_type']

                # Determine new option_type
                if existing_type != option_type.upper():
                    new_type = 'MIXED'
                else:
                    new_type = existing_type

                # Update max score if higher
                new_max_score = max(entry['max_significance_score'], significance_score)

                update_sql = """
                    UPDATE flow_watchlist_daily
                    SET alert_count_today = alert_count_today + 1,
                        max_significance_score = ?,
                        option_type = ?,
                        last_updated = ?
                    WHERE id = ?
                """

                def update_operation(conn):
                    conn.execute(update_sql, (
                        new_max_score, new_type, current_time, entry['id']
                    ))
                    conn.commit()
                    return True

                if storage._execute_with_retry(update_operation):
                    stats['entries_updated'] += 1
                    logging.debug("Updated watchlist entry: {} (count: {} -> {}, type: {})".format(
                        symbol, entry['alert_count_today'], entry['alert_count_today'] + 1, new_type))

        if stats['entries_created'] > 0 or stats['entries_updated'] > 0:
            logging.info("Watchlist updated: {} created, {} updated from {} alerts in flow_watchlist_daily".format(
                stats['entries_created'], stats['entries_updated'], stats['total_alerts_processed']))
        else:
            logging.info("No new watchlist entries this cycle")

        return stats

    except Exception as e:
        logging.error("Error updating daily watchlist: {}".format(e))

        # AUTOFIX: Queue error if database operation fails
        # This catches schema mismatches, corruption, or other database issues
        queue_error(
            error_type='watchlist_update_failed',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e),
                'trade_date': trade_date,
                'scan_timestamp': scan_timestamp,
                'alerts_processed': stats.get('total_alerts_processed', 0),
                'entries_created': stats.get('entries_created', 0),
                'entries_updated': stats.get('entries_updated', 0)
            },
            severity='ERROR'
        )
        return stats


def update_prices_and_detect(storage, current_prices_dict):
    """Update current prices and detect dip signals using z-score logic

    Uses volatility-normalized z-scores instead of flat 5% thresholds.
    Falls back to percentage threshold if RV data is missing.

    Args:
        storage: FlowMonitorStorage instance
        current_prices_dict: Dict mapping symbol -> current_ul_price

    Returns:
        dict: Statistics (prices_updated, dips_detected, zscore_detections, fallback_detections)
    """
    stats = {
        'prices_updated': 0,
        'dips_detected': 0,
        'zscore_detections': 0,
        'fallback_detections': 0,
        'missing_rv_count': 0
    }

    try:
        # Load configuration
        config = FMConfig()
        dip_config = config.get_dip_thresholds()

        use_zscore = dip_config['use_zscore_detection']
        zscore_min = dip_config['zscore_min']  # Shallow end (e.g., -0.10)
        zscore_max = dip_config['zscore_max']  # Deep end (e.g., -0.20)
        fallback_min_pct = dip_config['fallback_min_pct']  # Shallow end (e.g., -1.5%)
        fallback_max_pct = dip_config['fallback_max_pct']  # Deep end (e.g., -3.5%)
        rv_cap = dip_config['rv_cap']
        min_rv = dip_config['min_rv_for_zscore']
        require_building = dip_config['require_building_sentiment']

        # Query active entries with RV data and sentiment
        # LEFT JOIN to get latest rv_5d for each symbol
        query = """
            SELECT
                w.id, w.symbol, w.entry_ul_price, w.option_type, w.dip_detected,
                w.entry_date, w.rv_5d as entry_rv_5d, w.alert_sentiment,
                s.rv_5d as current_rv_5d
            FROM flow_watchlist_daily w
            LEFT JOIN option_symbol_summary s
                ON w.symbol = s.symbol
                AND s.trade_date = (SELECT MAX(trade_date) FROM option_symbol_summary)
        """

        active_entries = storage.query_with_params(query, ())

        if not active_entries:
            return stats

        current_time = eastern_isoformat()
        updates = []

        # Process each entry
        for entry in active_entries:
            symbol = entry['symbol']
            entry_price = entry['entry_ul_price']
            option_type = entry['option_type']
            already_flagged = entry['dip_detected']
            alert_sentiment = entry.get('alert_sentiment')

            # Get current price
            current_price = current_prices_dict.get(symbol)

            if current_price is None or current_price <= 0:
                continue

            # Calculate raw price change (always populate for visibility)
            price_change = current_price - entry_price
            price_diff_pct = format_percentage((price_change / entry_price) * 100)

            # Get RV (prefer current, fallback to entry snapshot)
            rv_5d = entry.get('current_rv_5d') or entry.get('entry_rv_5d')

            # Initialize detection variables
            # Preserve existing flag if already detected ("ever detected" semantic)
            dip_detected = 1 if already_flagged else 0
            dip_detected_date = None
            detection_method = None

            # NOTE (2026-02-10): We removed z_score and dip_threshold_used storage.
            # These columns caused bugs - values were overwritten with NULL on subsequent
            # scans when already_flagged=True. The z_score is still calculated locally
            # for the detection decision, just not persisted. If needed for analysis,
            # it can be recalculated from price_diff_pct and rv_5d.

            if not already_flagged:  # Only flag if not already detected

                # SENTIMENT CHECK: Only detect dips for BUILDING sentiment
                # Sentiment is determined next-day from OI comparison
                # CLOSING alerts have ~45% win rate - skip them
                # MIXED option_type is noisy - skip them too
                if require_building and alert_sentiment != 'BUILDING':
                    # Skip non-BUILDING sentiment (includes None for same-day entries)
                    pass
                elif option_type == 'MIXED':
                    # Skip MIXED - too noisy, usually accompanied by clearer alerts
                    pass

                # Z-SCORE DETECTION (range-based)
                elif use_zscore and rv_5d is not None and rv_5d >= min_rv:
                    # Apply RV cap to prevent meme stock chaos
                    rv_effective = min(rv_5d, rv_cap)

                    # Calculate sigma_price (price-space volatility)
                    sigma_price = rv_effective * entry_price

                    # Calculate z-score (local variable for detection decision only)
                    if sigma_price > 0:
                        z_score = format_score(price_change / sigma_price)

                        # CALL: want price drops in sweet spot range
                        # zscore_max <= z_score <= zscore_min (e.g., -0.20 <= z <= -0.10)
                        if option_type == 'CALL':
                            if zscore_max <= z_score <= zscore_min:
                                dip_detected = 1
                                dip_detected_date = current_time
                                detection_method = 'zscore'
                                stats['dips_detected'] += 1
                                stats['zscore_detections'] += 1

                        # PUT: want price rises in sweet spot range (adverse move = cheaper puts)
                        # -zscore_min <= z_score <= -zscore_max (e.g., +0.10 <= z <= +0.20)
                        elif option_type == 'PUT':
                            if -zscore_min <= z_score <= -zscore_max:
                                dip_detected = 1
                                dip_detected_date = current_time
                                detection_method = 'zscore'
                                stats['dips_detected'] += 1
                                stats['zscore_detections'] += 1

                # FALLBACK: PERCENTAGE DETECTION (range-based)
                elif option_type in ('CALL', 'PUT'):
                    if rv_5d is None or rv_5d < min_rv:
                        stats['missing_rv_count'] += 1

                    # CALL: price drop in range (e.g., -3.5% <= diff <= -1.5%)
                    if option_type == 'CALL':
                        if fallback_max_pct <= price_diff_pct <= fallback_min_pct:
                            dip_detected = 1
                            dip_detected_date = current_time
                            detection_method = 'percentage_fallback'
                            stats['dips_detected'] += 1
                            stats['fallback_detections'] += 1

                    # PUT: price rise in range (e.g., +1.5% <= diff <= +3.5%)
                    elif option_type == 'PUT':
                        if -fallback_min_pct <= price_diff_pct <= -fallback_max_pct:
                            dip_detected = 1
                            dip_detected_date = current_time
                            detection_method = 'percentage_fallback'
                            stats['dips_detected'] += 1
                            stats['fallback_detections'] += 1

            # Prepare update
            updates.append({
                'id': entry['id'],
                'symbol': symbol,
                'current_ul_price': current_price,
                'price_diff_pct': price_diff_pct,
                'rv_5d': rv_5d,
                'dip_detected': dip_detected,
                'dip_detected_date': dip_detected_date,
                'detection_method': detection_method,
                'last_updated': current_time
            })

            stats['prices_updated'] += 1

            # Log detection for monitoring
            if dip_detected and not already_flagged:
                entry_date_str = entry.get('entry_date', '')[:10]  # YYYY-MM-DD
                if entry_date_str:
                    from datetime import datetime as dt
                    try:
                        ed = dt.strptime(entry_date_str, '%Y-%m-%d')
                        entry_date_label = ed.strftime('%m/%d')
                    except ValueError:
                        entry_date_label = entry_date_str
                else:
                    entry_date_label = '?'
                logging.info("Dip detected: {} ({}, entry {}) via {} - ${:.2f}->${:.2f} ({:+.2f}%)".format(
                    symbol, option_type, entry_date_label, detection_method,
                    entry_price, current_price, price_diff_pct))

        # Batch update
        if updates:
            update_sql = """
                UPDATE flow_watchlist_daily
                SET current_ul_price = ?,
                    price_diff_pct = ?,
                    rv_5d = ?,
                    dip_detected = ?,
                    dip_detected_date = COALESCE(dip_detected_date, ?),
                    last_updated = ?
                WHERE id = ?
            """

            params_list = [
                (
                    u['current_ul_price'],
                    u['price_diff_pct'],
                    u['rv_5d'],
                    u['dip_detected'],
                    u['dip_detected_date'],
                    u['last_updated'],
                    u['id']
                )
                for u in updates
            ]

            def batch_update_operation(conn):
                cursor = conn.cursor()
                cursor.executemany(update_sql, params_list)
                conn.commit()
                return True

            storage._execute_with_retry(batch_update_operation)

        # Log summary
        if stats['dips_detected'] > 0:
            logging.info("Buy-the-dip opportunities: {} detected (zscore: {}, fallback: {})".format(
                stats['dips_detected'], stats['zscore_detections'], stats['fallback_detections']))

            # Send email notification for newly detected dips
            try:
                # Get today's date for deduplication
                today_str = now_eastern().strftime('%Y-%m-%d')

                # Collect details of newly detected dips (filter out already-emailed symbols today)
                dip_details = []
                symbols_to_update = []  # Track which symbols we'll email about

                for u in updates:
                    if u['dip_detected'] == 1 and u['dip_detected_date'] is not None:
                        # Query to get full entry details for email AND check last_email_date
                        query = """
                            SELECT id, symbol, entry_date, entry_ul_price, current_ul_price,
                                   price_diff_pct, option_type, max_significance_score,
                                   alert_count_today, alert_sentiment,
                                   building_alerts_count, closing_alerts_count,
                                   last_email_date, rv_5d,
                                   earnings_date, days_to_earnings,
                                   first_alert_id
                            FROM flow_watchlist_daily
                            WHERE id = ?
                        """
                        result = storage.query_with_params(query, (u['id'],))
                        if result:
                            entry = dict(result[0])  # Convert to mutable dict

                            # Add detection method from update dict
                            entry['detection_method'] = u.get('detection_method')

                            # Fetch original alert contract details
                            if entry.get('first_alert_id'):
                                alert_query = """
                                    SELECT strike, expiration_date, option_type, dte, iv, alert_reason
                                    FROM flow_alerts WHERE id = ?
                                """
                                alert_result = storage.query_with_params(alert_query, (entry['first_alert_id'],))
                                if alert_result:
                                    entry['orig_alert'] = dict(alert_result[0])
                                else:
                                    entry['orig_alert'] = None  # Alert may have been archived
                            else:
                                entry['orig_alert'] = None

                            # DEDUPLICATION: Only include if we haven't emailed today
                            if entry.get('last_email_date') != today_str:
                                dip_details.append(entry)
                                symbols_to_update.append((entry['id'], entry['symbol']))
                            else:
                                logging.debug("Skipping email for {} - already notified today".format(entry['symbol']))

                if dip_details and dip_config.get('email_alerts', True):
                    # Build email body
                    subject = "🎯 Buy-the-Dip Alert: {} Opportunit{} Detected".format(
                        len(dip_details), "y" if len(dip_details) == 1 else "ies"
                    )

                    body_lines = []
                    body_lines.append("Flow Monitor Watchlist detected {} buy-the-dip opportunit{}:".format(
                        len(dip_details), "y" if len(dip_details) == 1 else "ies"))
                    body_lines.append("")
                    body_lines.append("=" * 70)

                    for dip in dip_details:
                        sentiment = dip.get('alert_sentiment') or 'NEUTRAL'
                        building = dip.get('building_alerts_count') or 0
                        closing = dip.get('closing_alerts_count') or 0
                        detection_method = dip.get('detection_method') or 'unknown'

                        body_lines.append("")
                        body_lines.append("Symbol: {}".format(dip['symbol']))
                        body_lines.append("  Entry Date:    {}".format(dip['entry_date']))

                        # Original alert contract details
                        orig = dip.get('orig_alert')
                        if orig and orig.get('strike') is not None:
                            strike_str = "${:.0f}".format(orig['strike']) if orig['strike'] == int(orig['strike']) else "${:.1f}".format(orig['strike'])
                            body_lines.append("  Original Alert: {} {} {} ({} DTE, IV {:.0f}%)".format(
                                strike_str,
                                (orig['option_type'] or '').upper(),
                                orig['expiration_date'] or '?',
                                orig['dte'] or '?',
                                (orig['iv'] or 0) * 100
                            ))
                        else:
                            body_lines.append("  Original Alert: (unavailable - may have been archived)")

                        body_lines.append("  Entry Price:   ${:.2f}".format(dip['entry_ul_price']))
                        body_lines.append("  Current Price: ${:.2f}".format(dip['current_ul_price']))
                        body_lines.append("  Change:        {:+.2f}%".format(dip['price_diff_pct']))
                        body_lines.append("  Detection:     {}".format(detection_method))
                        body_lines.append("  Option Type:   {}".format(dip['option_type']))
                        body_lines.append("  Alert Score:   {:.1f}".format(dip['max_significance_score']))
                        body_lines.append("  Alert Count:   {} today".format(dip['alert_count_today']))
                        body_lines.append("  Sentiment:     {} ({}B {}C)".format(sentiment, building, closing))

                        # Earnings proximity (if available)
                        dte = dip.get('days_to_earnings')
                        if dte is not None:
                            body_lines.append("  Earnings:      {} ({} days away)".format(
                                dip.get('earnings_date', '?'), dte))

                    body_lines.append("")
                    body_lines.append("=" * 70)
                    body_lines.append("")
                    body_lines.append("Detection Time: {}".format(now_eastern().strftime('%Y-%m-%d %H:%M:%S ET')))
                    body_lines.append("")
                    body_lines.append("View details:")
                    body_lines.append("  python strategies/flow_monitor/query_watchlist.py")

                    body = "\n".join(body_lines)

                    # Send email
                    email_sent = send_email(subject, body)
                    if email_sent:
                        beautiful_log("Email notification sent for {} dip(s)".format(len(dip_details)), 'success')

                        # UPDATE last_email_date for symbols we just emailed about
                        try:
                            def update_email_dates(conn):
                                cursor = conn.cursor()
                                for entry_id, symbol in symbols_to_update:
                                    cursor.execute("""
                                        UPDATE flow_watchlist_daily
                                        SET last_email_date = ?
                                        WHERE id = ?
                                    """, (today_str, entry_id))
                                conn.commit()
                                logging.debug("Updated last_email_date for {} symbols".format(len(symbols_to_update)))

                            storage._execute_with_retry(update_email_dates)
                        except Exception as update_error:
                            logging.warning("Failed to update last_email_date: {}".format(update_error))
                            # Non-critical - worst case is duplicate email tomorrow

                    else:
                        logging.warning("Failed to send email notification for dips")

            except Exception as email_error:
                logging.warning("Error sending dip email notification: {}".format(email_error))
                # Don't fail the entire function if email fails
        else:
            logging.info("No dip opportunities detected")

        logging.debug("Watchlist prices updated: {} entries processed".format(stats['prices_updated']))

        return stats

    except Exception as e:
        logging.error("Error updating prices and detecting dips: {}".format(e))

        # AUTOFIX: Queue error if price update fails
        queue_error(
            error_type='watchlist_price_update_failed',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e),
                'symbols_attempted': len(current_prices_dict),
                'prices_updated': stats.get('prices_updated', 0),
                'dips_detected': stats.get('dips_detected', 0)
            },
            severity='ERROR'
        )
        return stats


def archive_expired_entries(storage):
    """Move expired watchlist entries to archive

    Args:
        storage: FlowMonitorStorage instance

    Returns:
        dict: Statistics (entries_archived, entries_deleted)
    """
    stats = {
        'entries_archived': 0,
        'entries_deleted': 0
    }

    try:
        today = now_eastern().strftime('%Y-%m-%d')
        current_time = eastern_isoformat()

        # Query expired entries
        query = """
            SELECT *
            FROM flow_watchlist_daily
            WHERE entry_expiration_date < ?
        """

        expired_entries = storage.query_with_params(query, (today,))

        if not expired_entries:
            logging.debug("No expired watchlist entries found")
            return stats

        # Insert into archive (includes z-score, news sentiment, and earnings columns)
        insert_sql = """
            INSERT INTO flow_watchlist_daily_archive (
                symbol, entry_date, entry_expiration_date,
                entry_ul_price, current_ul_price, price_diff_pct,
                option_type, first_alert_id, alert_count_today, max_significance_score,
                dip_detected, dip_detected_date,
                rv_5d,
                news_sentiment_score, news_sentiment_label, news_article_count,
                earnings_date, days_to_earnings, earnings_time,
                created_at, last_updated, archived_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        archive_values = [
            (
                entry['symbol'], entry['entry_date'], entry['entry_expiration_date'],
                entry['entry_ul_price'], entry['current_ul_price'], entry['price_diff_pct'],
                entry['option_type'], entry['first_alert_id'], entry['alert_count_today'],
                entry['max_significance_score'], entry['dip_detected'], entry['dip_detected_date'],
                entry.get('rv_5d'),
                entry.get('news_sentiment_score'), entry.get('news_sentiment_label'),
                entry.get('news_article_count'),
                entry.get('earnings_date'), entry.get('days_to_earnings'),
                entry.get('earnings_time'),
                entry['created_at'], entry['last_updated'], current_time
            )
            for entry in expired_entries
        ]

        def archive_operation(conn):
            cursor = conn.cursor()
            cursor.executemany(insert_sql, archive_values)
            conn.commit()
            return True

        if storage._execute_with_retry(archive_operation):
            stats['entries_archived'] = len(expired_entries)

            # Delete from active table
            delete_sql = """
                DELETE FROM flow_watchlist_daily
                WHERE entry_expiration_date < ?
            """

            def delete_operation(conn):
                cursor = conn.cursor()
                cursor.execute(delete_sql, (today,))
                rows_deleted = cursor.rowcount
                conn.commit()
                return rows_deleted

            rows_deleted = storage._execute_with_retry(delete_operation)
            stats['entries_deleted'] = rows_deleted or 0

            logging.debug("Archived {} expired watchlist entries".format(stats['entries_archived']))

        return stats

    except Exception as e:
        logging.error("Error archiving expired entries: {}".format(e))

        # AUTOFIX: Queue error if archiving fails
        queue_error(
            error_type='watchlist_archive_failed',
            context={
                'exception_type': type(e).__name__,
                'error_message': str(e),
                'today': now_eastern().strftime('%Y-%m-%d'),
                'entries_archived': stats.get('entries_archived', 0),
                'entries_deleted': stats.get('entries_deleted', 0)
            },
            severity='WARNING'  # Non-critical - watchlist still works, just doesn't clean up
        )
        return stats


def backfill_missing_news(storage):
    """Backfill NULL news sentiment on active watchlist entries using remaining API budget.

    Called post-market after archive_expired_entries() — only live entries remain,
    so every call is worth spending. Prioritizes by max_significance_score DESC.

    Args:
        storage: FlowMonitorStorage instance

    Returns:
        dict: {backfilled: int, failed: int, budget_remaining: int, skipped_no_budget: int}

    Reads: flow_watchlist_daily
    Writes: flow_watchlist_daily (news columns), news_articles, news_symbol_sentiment
    """
    stats = {
        'backfilled': 0,
        'failed': 0,
        'budget_remaining': 0,
        'skipped_no_budget': 0,
    }

    try:
        from tools.news_sentiment import get_budget_status, enrich_watchlist_symbol, _create_av_client

        # Share a single AV client across all backfill calls (preserves per-minute rate limiter)
        av_client = _create_av_client()

        # Check budget first — skip entirely if nothing left
        budget = get_budget_status()
        stats['budget_remaining'] = budget.get('remaining', 0)
        if not budget.get('can_make_request', False):
            logging.debug("News backfill: no budget remaining")
            return stats

        # Find active entries missing news, prioritized by significance
        query = """
            SELECT symbol, entry_date
            FROM flow_watchlist_daily
            WHERE news_sentiment_score IS NULL
            ORDER BY max_significance_score DESC
        """
        candidates = storage.query_with_params(query, ())

        if not candidates:
            logging.debug("News backfill: no NULL-sentiment entries to fill")
            return stats

        logging.info("News backfill: {} NULL-sentiment entries, {} budget remaining".format(
            len(candidates), stats['budget_remaining']))

        for row in candidates:
            # Re-check budget each iteration
            budget = get_budget_status()
            stats['budget_remaining'] = budget.get('remaining', 0)
            if not budget.get('can_make_request', False):
                stats['skipped_no_budget'] = len(candidates) - stats['backfilled'] - stats['failed']
                break

            sym = row['symbol']
            entry_date = row['entry_date']

            try:
                result = enrich_watchlist_symbol(sym, storage, av_client=av_client, entry_date=entry_date)
                if result.get('success') and result.get('sentiment'):
                    stats['backfilled'] += 1
                    logging.info("  {} ({}): backfilled".format(sym, entry_date))
                elif result.get('success'):
                    stats['failed'] += 1
                    logging.info("  {} ({}): no symbol-specific sentiment".format(sym, entry_date))
                else:
                    stats['failed'] += 1
                    logging.info("  {} ({}): fetch failed".format(sym, entry_date))
            except Exception as e:
                logging.warning("  {} ({}): error - {}".format(sym, entry_date, e))
                stats['failed'] += 1

        # Update final budget
        budget = get_budget_status()
        stats['budget_remaining'] = budget.get('remaining', 0)

        # Persist API usage counters
        total_calls = stats['backfilled'] + stats['failed']
        if total_calls > 0:
            try:
                from main_ui import _save_news_api_usage
                _save_news_api_usage(
                    source='fm',
                    api_calls=total_calls,
                    symbols_enriched=stats['backfilled'],
                    zero_article_calls=stats['failed'],
                )
            except Exception as usage_err:
                logging.debug("Could not save news API usage: {}".format(usage_err))

    except Exception as e:
        logging.warning("News backfill error (non-critical): {}".format(e))

    return stats


# Module test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Flow Monitor Watchlist Module - Functions defined:")
    print("  - update_daily_watchlist(trade_date, storage, scan_timestamp)")
    print("  - update_prices_and_detect(storage, current_prices_dict)")
    print("  - archive_expired_entries(storage)")
    print("  - backfill_missing_news(storage)")
    print("\nModule ready for integration into fm_main.py")
