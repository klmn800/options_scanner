#!/usr/bin/env python3
"""
Volume Profile Calculator
==========================

Calculates volume profile analysis for stock symbols - identifies price levels where
significant trading occurred historically. These represent areas where institutions
accumulated/distributed positions.

KEY CONCEPTS:
- Point of Control (POC): Price level with highest volume concentration
- Value Area: Price range containing 70% of total volume (fair value zone)
- High Volume Nodes (HVN): Price levels with above-average volume (sticky areas)
- Low Volume Nodes (LVN): Price gaps with minimal volume (breakout zones)

TRADING SIGNIFICANCE:
- HVN levels act as magnets - price tends to return to these levels
- LVN areas are "speed zones" - price moves quickly through them
- Value Area defines fair value range for position sizing
- POC is strongest support/resistance level

USAGE IN OPTIONS TRADING:
- Strike selection: Target strikes near HVN levels for higher probability
- Entry timing: Enter positions when price tests POC or Value Area boundaries
- Risk management: Place stops below LVN areas (fast moves through these)
- Flow context: Weight unusual options flow higher when strikes align with HVN

Extracted from daily_analysis system (deprecated 2025-10-13)

Author: Ben (With assistance from Claude)
Date: 2025-09-18 (Original), 2025-10-13 (Extracted)
"""

import sqlite3
import json
import argparse
import sys
import os


def calculate_volume_profile(conn, symbol, trade_date=None, current_price=None, lookback_days=60):
    """
    Calculate Volume Profile Analysis - identifies key price levels based on volume distribution.

    Args:
        conn: Database connection
        symbol (str): Stock symbol
        trade_date (str, optional): Date in YYYY-MM-DD format (defaults to most recent)
        current_price (float, optional): Current stock price (queries from DB if not provided)
        lookback_days (int): Number of trading days to analyze (default: 60)

    Returns:
        dict: Volume zone analysis with POC, Value Area, HVN/LVN levels
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

        # If no current_price provided, get it from database
        if current_price is None:
            cursor = conn.execute("""
                SELECT close_price FROM historical_prices
                WHERE symbol = ? AND trade_date = ?
            """, (symbol, trade_date))
            row = cursor.fetchone()
            if not row or not row[0]:
                return {"status": "error", "error": "No price data for {} on {}".format(symbol, trade_date)}
            current_price = row[0]

        # Get historical price/volume data for volume profile calculation
        volume_data_sql = """
        SELECT close_price, volume, trade_date
        FROM historical_prices
        WHERE symbol = ?
        AND trade_date <= ?
        AND volume > 0
        AND close_price > 0
        ORDER BY trade_date DESC
        LIMIT ?
        """

        cursor = conn.execute(volume_data_sql, (symbol, trade_date, lookback_days))
        price_volume_data = cursor.fetchall()

        if len(price_volume_data) < 30:
            return {
                "status": "insufficient_data",
                "days_available": len(price_volume_data),
                "note": "Need at least 30 days of data for reliable volume profile"
            }

        # Create price buckets (rounded to nearest $0.50 for stocks under $50, $1.00 for higher)
        bucket_size = 0.50 if current_price < 50 else 1.00

        # Build volume profile - group volume by price buckets
        volume_profile = {}
        total_volume = 0

        for close_price, volume, date in price_volume_data:
            if close_price and volume:
                # Round to bucket size
                bucket_price = round(close_price / bucket_size) * bucket_size
                volume_profile[bucket_price] = volume_profile.get(bucket_price, 0) + volume
                total_volume += volume

        if not volume_profile or total_volume == 0:
            return {"status": "no_valid_data", "note": "No valid price/volume data found"}

        # Sort by volume to find Point of Control (highest volume price)
        sorted_by_volume = sorted(volume_profile.items(), key=lambda x: x[1], reverse=True)
        point_of_control = sorted_by_volume[0][0]  # Price with highest volume
        poc_volume = sorted_by_volume[0][1]

        # Calculate Value Area (70% of total volume)
        value_area_volume_target = total_volume * 0.70
        cumulative_volume = 0
        value_area_prices = []

        # Start from POC and expand outward until we capture 70% of volume
        sorted_prices = sorted(volume_profile.keys())
        poc_index = sorted_prices.index(point_of_control)

        # Add POC first
        value_area_prices.append(point_of_control)
        cumulative_volume += volume_profile[point_of_control]

        # Expand outward from POC alternating up/down
        up_index = poc_index + 1
        down_index = poc_index - 1

        while cumulative_volume < value_area_volume_target and (up_index < len(sorted_prices) or down_index >= 0):
            # Choose direction with higher volume
            up_volume = volume_profile.get(sorted_prices[up_index], 0) if up_index < len(sorted_prices) else 0
            down_volume = volume_profile.get(sorted_prices[down_index], 0) if down_index >= 0 else 0

            if up_volume >= down_volume and up_index < len(sorted_prices):
                price = sorted_prices[up_index]
                value_area_prices.append(price)
                cumulative_volume += volume_profile[price]
                up_index += 1
            elif down_index >= 0:
                price = sorted_prices[down_index]
                value_area_prices.append(price)
                cumulative_volume += volume_profile[price]
                down_index -= 1
            else:
                break

        # Calculate Value Area High and Low
        value_area_high = max(value_area_prices)
        value_area_low = min(value_area_prices)
        value_area_coverage = round((cumulative_volume / total_volume) * 100, 1)

        # Identify High Volume Nodes (above average volume)
        avg_volume = total_volume / len(volume_profile)
        high_volume_threshold = avg_volume * 1.5  # 50% above average

        high_volume_nodes = []
        for price, volume in volume_profile.items():
            if volume >= high_volume_threshold:
                high_volume_nodes.append({
                    "price": price,
                    "volume": volume,
                    "strength": "strong" if volume >= avg_volume * 2 else "medium"
                })

        # Sort HVN by volume strength
        high_volume_nodes.sort(key=lambda x: x["volume"], reverse=True)

        # Identify Low Volume Nodes (price gaps with minimal volume)
        low_volume_threshold = avg_volume * 0.3  # 30% of average
        low_volume_nodes = []

        for price in sorted_prices:
            if volume_profile[price] <= low_volume_threshold:
                low_volume_nodes.append({
                    "price": price,
                    "volume": volume_profile[price],
                    "note": "Potential breakout zone - price moves quickly through low volume areas"
                })

        # Calculate current price context
        price_context = "unknown"
        if current_price > value_area_high:
            price_context = "above_value_area"
        elif current_price < value_area_low:
            price_context = "below_value_area"
        else:
            price_context = "within_value_area"

        # Find nearest volume zones to current price
        hvn_above = [node for node in high_volume_nodes if node["price"] > current_price]
        hvn_below = [node for node in high_volume_nodes if node["price"] < current_price]

        nearest_hvn_above = min(hvn_above, key=lambda x: abs(x["price"] - current_price)) if hvn_above else None
        nearest_hvn_below = max(hvn_below, key=lambda x: abs(x["price"] - current_price)) if hvn_below else None

        return {
            "symbol": symbol,
            "trade_date": trade_date,
            "current_price": current_price,
            "point_of_control": {
                "price": point_of_control,
                "volume": poc_volume,
                "note": "Strongest support/resistance - highest volume concentration"
            },
            "value_area": {
                "high": value_area_high,
                "low": value_area_low,
                "volume_coverage_percent": value_area_coverage,
                "note": "Fair value range where 70% of volume traded"
            },
            "current_price_context": {
                "position": price_context,
                "current_price": current_price,
                "distance_from_poc": round(((current_price - point_of_control) / point_of_control) * 100, 2)
            },
            "high_volume_nodes": high_volume_nodes[:5],  # Top 5 HVN levels
            "low_volume_nodes": low_volume_nodes[:3],    # Top 3 LVN gaps
            "nearest_zones": {
                "hvn_above": nearest_hvn_above,
                "hvn_below": nearest_hvn_below,
                "note": "Closest high-volume price magnets for targeting"
            },
            "trading_levels": {
                "resistance_targets": [node["price"] for node in hvn_above[:2]],
                "support_targets": [node["price"] for node in hvn_below[:2]],
                "breakout_zones": [node["price"] for node in low_volume_nodes[:2]]
            },
            "bucket_size": bucket_size,
            "analysis_period_days": len(price_volume_data),
            "total_volume_analyzed": total_volume,
            "status": "success"
        }

    except Exception as e:
        return {
            "status": "calculation_error",
            "error": "Volume zone calculation failed: {}".format(str(e))
        }


def format_volume_profile_output(result):
    """Format volume profile results for human-readable display."""
    if result.get('status') != 'success':
        return "ERROR: {}".format(result.get('error', result.get('note', 'Unknown error')))

    output = []
    output.append("=" * 80)
    output.append("VOLUME PROFILE ANALYSIS - {} ({})".format(result['symbol'], result['trade_date']))
    output.append("=" * 80)
    output.append("")

    # Current Price Context
    output.append("Current Price: ${:.2f}".format(result['current_price']))
    output.append("Position: {}".format(result['current_price_context']['position'].upper().replace('_', ' ')))
    output.append("Distance from POC: {:+.2f}%".format(result['current_price_context']['distance_from_poc']))
    output.append("")

    # Point of Control
    poc = result['point_of_control']
    output.append("POINT OF CONTROL (Strongest S/R):")
    output.append("  Price: ${:.2f}".format(poc['price']))
    output.append("  Volume: {:,}".format(int(poc['volume'])))
    output.append("")

    # Value Area
    va = result['value_area']
    output.append("VALUE AREA (Fair Value Zone - {}% of volume):".format(va['volume_coverage_percent']))
    output.append("  High: ${:.2f}".format(va['high']))
    output.append("  Low:  ${:.2f}".format(va['low']))
    output.append("  Range: ${:.2f}".format(va['high'] - va['low']))
    output.append("")

    # High Volume Nodes
    output.append("HIGH VOLUME NODES (Price Magnets):")
    for i, hvn in enumerate(result['high_volume_nodes'][:5], 1):
        output.append("  #{}: ${:.2f} - {:,} volume ({})".format(
            i, hvn['price'], int(hvn['volume']), hvn['strength']
        ))
    output.append("")

    # Nearest Zones for Trading
    output.append("NEAREST TRADING LEVELS:")
    nearest = result['nearest_zones']
    if nearest['hvn_above']:
        output.append("  Resistance (HVN Above): ${:.2f}".format(nearest['hvn_above']['price']))
    else:
        output.append("  Resistance (HVN Above): None identified")

    if nearest['hvn_below']:
        output.append("  Support (HVN Below): ${:.2f}".format(nearest['hvn_below']['price']))
    else:
        output.append("  Support (HVN Below): None identified")
    output.append("")

    # Low Volume Nodes
    if result['low_volume_nodes']:
        output.append("LOW VOLUME NODES (Breakout Zones):")
        for i, lvn in enumerate(result['low_volume_nodes'][:3], 1):
            output.append("  #{}: ${:.2f} - {:,} volume (fast move zone)".format(
                i, lvn['price'], int(lvn['volume'])
            ))
        output.append("")

    # Analysis Stats
    output.append("Analysis Period: {} days | Bucket Size: ${:.2f}".format(
        result['analysis_period_days'], result['bucket_size']
    ))
    output.append("=" * 80)

    return "\n".join(output)


def main():
    """Main entry point for standalone execution."""
    parser = argparse.ArgumentParser(
        description="Volume Profile Calculator - Identify key price levels based on volume",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/volume_profile_calculator.py --symbol KDP
  python tools/volume_profile_calculator.py --symbol MGM --date 2025-10-13
  python tools/volume_profile_calculator.py --symbol NVDA --lookback 90 --output profile.json
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
            result = calculate_volume_profile(
                conn,
                args.symbol,
                trade_date=args.date,
                lookback_days=args.lookback
            )

            # Print formatted output to console
            print(format_volume_profile_output(result))

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
