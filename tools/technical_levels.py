#!/usr/bin/env python3
"""
Technical Levels Detector
==========================

Detects swing highs and lows using price action analysis - identifies price levels
where the security reversed direction after testing resistance or support multiple times.

CONCEPT:
A swing high is a price peak where the high_price is higher than 3 days before AND
3 days after. This identifies significant resistance levels.

A swing low is a price trough where the low_price is lower than 3 days before AND
3 days after. This identifies significant support levels.

TRADING SIGNIFICANCE:
- Swing levels act as psychological barriers where traders make decisions
- Strong swing levels with high volume indicate institutional participation
- Recent swing levels (recency factor) are more relevant than old ones

Extracted from daily_analysis system (deprecated 2025-10-13)

Author: Ben (With assistance from Claude)
Date: 2025-09-18 (Original), 2025-10-13 (Extracted)
"""

import sqlite3
import json
import argparse
import sys
import os


def detect_swing_levels(conn, symbol, trade_date=None, lookback_days=60):
    """
    Detect swing highs and lows using 3-day confirmation algorithm.

    A swing high requires: high_price > (3 days before) AND high_price > (3 days after)
    A swing low requires: low_price < (3 days before) AND low_price < (3 days after)

    Args:
        conn: Database connection
        symbol (str): Stock symbol
        trade_date (str, optional): Date in YYYY-MM-DD format (defaults to most recent)
        lookback_days (int): Number of trading days to analyze (default: 60)

    Returns:
        dict: Swing levels structure with resistance/support levels
    """

    try:
        # If no trade_date provided, use most recent
        if trade_date is None:
            cursor = conn.execute("""
                SELECT MAX(trade_date) FROM historical_prices WHERE symbol = ?
            """, (symbol,))
            trade_date = cursor.fetchone()[0]
            if not trade_date:
                return {"status": "error", "error": "No data found for symbol {}".format(symbol)}

        # Find swing highs: high_price higher than 3 days before AND 3 days after
        swing_highs_sql = """
        WITH swing_highs AS (
            SELECT
                h1.trade_date,
                h1.high_price,
                h1.volume,
                -- Check if this high is higher than 3 days before and 3 days after
                CASE
                    WHEN h1.high_price > LAG(h1.high_price, 3) OVER (ORDER BY h1.trade_date)
                    AND h1.high_price > LAG(h1.high_price, 2) OVER (ORDER BY h1.trade_date)
                    AND h1.high_price > LAG(h1.high_price, 1) OVER (ORDER BY h1.trade_date)
                    AND h1.high_price > LEAD(h1.high_price, 1) OVER (ORDER BY h1.trade_date)
                    AND h1.high_price > LEAD(h1.high_price, 2) OVER (ORDER BY h1.trade_date)
                    AND h1.high_price > LEAD(h1.high_price, 3) OVER (ORDER BY h1.trade_date)
                    THEN 1 ELSE 0
                END as is_swing_high
            FROM historical_prices h1
            WHERE h1.symbol = ?
            AND h1.trade_date IN (
                SELECT trade_date FROM (
                    SELECT trade_date, ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
                    FROM historical_prices
                    WHERE symbol = ? AND trade_date <= ?
                    LIMIT ?
                ) recent_60d
            )
            ORDER BY h1.trade_date
        )
        SELECT
            trade_date,
            high_price,
            volume,
            -- Strength calculation (volume weighting + recency factor)
            ROUND((volume / 1000000.0 * 0.3) +
                  ((julianday(?) - julianday(trade_date)) * -0.1) + 5.0, 1) as strength
        FROM swing_highs
        WHERE is_swing_high = 1
        ORDER BY trade_date DESC
        LIMIT 4
        """

        cursor = conn.execute(swing_highs_sql, (symbol, symbol, trade_date, lookback_days, trade_date))
        swing_high_rows = cursor.fetchall()

        # Find swing lows: low_price lower than 3 days before AND 3 days after
        swing_lows_sql = """
        WITH swing_lows AS (
            SELECT
                h1.trade_date,
                h1.low_price,
                h1.volume,
                CASE
                    WHEN h1.low_price < LAG(h1.low_price, 3) OVER (ORDER BY h1.trade_date)
                    AND h1.low_price < LAG(h1.low_price, 2) OVER (ORDER BY h1.trade_date)
                    AND h1.low_price < LAG(h1.low_price, 1) OVER (ORDER BY h1.trade_date)
                    AND h1.low_price < LEAD(h1.low_price, 1) OVER (ORDER BY h1.trade_date)
                    AND h1.low_price < LEAD(h1.low_price, 2) OVER (ORDER BY h1.trade_date)
                    AND h1.low_price < LEAD(h1.low_price, 3) OVER (ORDER BY h1.trade_date)
                    THEN 1 ELSE 0
                END as is_swing_low
            FROM historical_prices h1
            WHERE h1.symbol = ?
            AND h1.trade_date IN (
                SELECT trade_date FROM (
                    SELECT trade_date, ROW_NUMBER() OVER (ORDER BY trade_date DESC) as rn
                    FROM historical_prices
                    WHERE symbol = ? AND trade_date <= ?
                    LIMIT ?
                ) recent_60d
            )
            ORDER BY h1.trade_date
        )
        SELECT
            trade_date,
            low_price,
            volume,
            -- Strength calculation (volume weighting + recency factor)
            ROUND((volume / 1000000.0 * 0.3) +
                  ((julianday(?) - julianday(trade_date)) * -0.1) + 5.0, 1) as strength
        FROM swing_lows
        WHERE is_swing_low = 1
        ORDER BY trade_date DESC
        LIMIT 4
        """

        cursor = conn.execute(swing_lows_sql, (symbol, symbol, trade_date, lookback_days, trade_date))
        swing_low_rows = cursor.fetchall()

        # Build the swing_levels structure
        swing_levels = {
            "symbol": symbol,
            "trade_date": trade_date,
            "resistance_1": {"price": None, "strength": None, "last_test": None},
            "resistance_2": {"price": None, "strength": None, "last_test": None},
            "support_1": {"price": None, "strength": None, "last_test": None},
            "support_2": {"price": None, "strength": None, "last_test": None}
        }

        # Populate resistance levels (swing highs)
        if len(swing_high_rows) >= 1:
            swing_levels["resistance_1"] = {
                "price": float(swing_high_rows[0][1]),
                "strength": float(swing_high_rows[0][3]),
                "last_test": swing_high_rows[0][0]
            }

        if len(swing_high_rows) >= 2:
            swing_levels["resistance_2"] = {
                "price": float(swing_high_rows[1][1]),
                "strength": float(swing_high_rows[1][3]),
                "last_test": swing_high_rows[1][0]
            }

        # Populate support levels (swing lows)
        if len(swing_low_rows) >= 1:
            swing_levels["support_1"] = {
                "price": float(swing_low_rows[0][1]),
                "strength": float(swing_low_rows[0][3]),
                "last_test": swing_low_rows[0][0]
            }

        if len(swing_low_rows) >= 2:
            swing_levels["support_2"] = {
                "price": float(swing_low_rows[1][1]),
                "strength": float(swing_low_rows[1][3]),
                "last_test": swing_low_rows[1][0]
            }

        swing_levels["status"] = "success"
        return swing_levels

    except Exception as e:
        # Return error structure
        return {
            "status": "error",
            "error": "Swing level detection failed: {}".format(str(e)),
            "symbol": symbol,
            "trade_date": trade_date
        }


def format_swing_levels_output(result):
    """Format swing levels results for human-readable display."""
    if result.get('status') != 'success':
        return "ERROR: {}".format(result.get('error', 'Unknown error'))

    output = []
    output.append("=" * 80)
    output.append("SWING LEVELS ANALYSIS - {} ({})".format(result['symbol'], result['trade_date']))
    output.append("=" * 80)
    output.append("")

    # Resistance Levels
    output.append("RESISTANCE LEVELS (Swing Highs):")
    for i in [1, 2]:
        key = "resistance_{}".format(i)
        level = result[key]
        if level['price']:
            output.append("  R{}: ${:.2f} (Strength: {:.1f}) - Last tested: {}".format(
                i, level['price'], level['strength'], level['last_test']
            ))
        else:
            output.append("  R{}: Not identified".format(i))
    output.append("")

    # Support Levels
    output.append("SUPPORT LEVELS (Swing Lows):")
    for i in [1, 2]:
        key = "support_{}".format(i)
        level = result[key]
        if level['price']:
            output.append("  S{}: ${:.2f} (Strength: {:.1f}) - Last tested: {}".format(
                i, level['price'], level['strength'], level['last_test']
            ))
        else:
            output.append("  S{}: Not identified".format(i))
    output.append("")

    output.append("STRENGTH SCALE:")
    output.append("  4.0-5.0: Recent level with high volume (strongest)")
    output.append("  3.0-4.0: Recent level with moderate volume")
    output.append("  2.0-3.0: Older level or low volume")
    output.append("  <2.0: Weak level (old and/or low volume)")
    output.append("")

    output.append("=" * 80)

    return "\n".join(output)


def main():
    """Main entry point for standalone execution."""
    parser = argparse.ArgumentParser(
        description="Technical Levels Detector - Identify swing highs/lows for support/resistance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/technical_levels.py --symbol KDP
  python tools/technical_levels.py --symbol MGM --date 2025-10-13
  python tools/technical_levels.py --symbol NVDA --lookback 90 --output levels.json
        """
    )
    parser.add_argument("--symbol", required=True, help="Stock symbol to analyze")
    parser.add_argument("--date", help="Date to analyze (YYYY-MM-DD, defaults to most recent)")
    parser.add_argument("--lookback", type=int, default=60, help="Days of history to analyze (default: 60)")
    parser.add_argument("--db", default="data/datalake_query.db", help="Database path (default: data/datalake_query.db)")
    parser.add_argument("--output", help="Output JSON file path (optional)")

    args = parser.parse_args()

    # Connect to database and run analysis
    try:
        with sqlite3.connect(args.db) as conn:
            result = detect_swing_levels(
                conn,
                args.symbol,
                trade_date=args.date,
                lookback_days=args.lookback
            )

            # Print formatted output to console
            print(format_swing_levels_output(result))

            # Save to output file if specified
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2)
                print("\nFull analysis saved to: {}".format(args.output))

            # Return success/failure based on analysis status
            if result.get('status') != 'success':
                sys.exit(1)
            else:
                sys.exit(0)

    except Exception as e:
        print("ERROR: Analysis failed: {}".format(str(e)))
        sys.exit(1)


if __name__ == "__main__":
    main()
