#!/usr/bin/env python3
"""
Phase 5: Practical Constraints Analysis
Analyze real-world implementation details
"""

import sqlite3
from collections import defaultdict

DB_PATH = "../data/datalake_query.db"

def analyze_liquidity():
    """Check bid-ask spreads and volume for optimal filter contracts"""
    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT
        contract_hash,
        trade_date,
        symbol,
        strike,
        option_type,
        bid,
        ask,
        volume,
        open_interest,
        underlying_price,
        (ask - bid) as spread,
        (ask - bid) / ask as spread_pct
    FROM flow_options_scans
    WHERE ask >= 0.03 AND ask <= 0.05
      AND dte >= 20 AND dte <= 28
      AND vega >= 0.015 AND vega <= 0.035
      AND trade_date >= '2025-09-01'
      AND symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')
      AND bid > 0 AND ask > 0
      AND vega IS NOT NULL
      AND delta IS NOT NULL
    """

    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    print("="*70)
    print("LIQUIDITY ANALYSIS")
    print("="*70)
    print()

    # Bid-ask spread analysis
    spreads = [row[11] for row in rows if row[11] is not None]
    avg_spread = sum(spreads) / len(spreads) if spreads else 0
    median_spread = sorted(spreads)[len(spreads)//2] if spreads else 0

    print(f"BID-ASK SPREADS:")
    print(f"  Average spread: {avg_spread*100:.2f}%")
    print(f"  Median spread: {median_spread*100:.2f}%")
    print()

    # Spread buckets
    spread_buckets = {
        '0-20%': len([s for s in spreads if s < 0.20]),
        '20-40%': len([s for s in spreads if 0.20 <= s < 0.40]),
        '40-60%': len([s for s in spreads if 0.40 <= s < 0.60]),
        '60%+': len([s for s in spreads if s >= 0.60])
    }

    print(f"SPREAD DISTRIBUTION:")
    for bucket, count in spread_buckets.items():
        pct = count / len(spreads) * 100 if spreads else 0
        print(f"  {bucket}: {count} scans ({pct:.1f}%)")
    print()

    # Volume analysis
    volumes = [row[7] for row in rows if row[7] is not None and row[7] > 0]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    median_volume = sorted(volumes)[len(volumes)//2] if volumes else 0

    print(f"VOLUME ANALYSIS:")
    print(f"  Average daily volume: {avg_volume:.0f} contracts")
    print(f"  Median daily volume: {median_volume:.0f} contracts")
    print(f"  Zero volume scans: {len(rows) - len(volumes)} ({(len(rows)-len(volumes))/len(rows)*100:.1f}%)")
    print()

    # OI analysis
    oi_values = [row[8] for row in rows if row[8] is not None and row[8] > 0]
    avg_oi = sum(oi_values) / len(oi_values) if oi_values else 0
    median_oi = sorted(oi_values)[len(oi_values)//2] if oi_values else 0

    print(f"OPEN INTEREST:")
    print(f"  Average OI: {avg_oi:.0f} contracts")
    print(f"  Median OI: {median_oi:.0f} contracts")
    print()


def analyze_capital_requirements():
    """Calculate capital needed per trade and portfolio sizing"""

    print("="*70)
    print("CAPITAL REQUIREMENTS")
    print("="*70)
    print()

    # Per-trade costs
    avg_entry = 0.05  # Upper bound of filter
    fee_per_contract = 0.042
    contracts_per_trade = 10  # Example position size

    entry_cost = avg_entry * 100 * contracts_per_trade  # Options are per 100 shares
    fees = fee_per_contract * contracts_per_trade * 2  # Round-trip
    total_capital = entry_cost + fees

    print(f"PER-TRADE CAPITAL (10 contracts @ $0.05):")
    print(f"  Contract cost: ${entry_cost:.2f}")
    print(f"  Round-trip fees: ${fees:.2f}")
    print(f"  Total capital: ${total_capital:.2f}")
    print()

    # Max loss per trade (assume 100% loss)
    max_loss = total_capital
    print(f"  Max loss (100%): ${max_loss:.2f}")
    print()

    # Portfolio sizing scenarios
    print(f"PORTFOLIO SIZING SCENARIOS:")
    print()

    scenarios = [
        ("Conservative (5 positions)", 5),
        ("Moderate (10 positions)", 10),
        ("Aggressive (20 positions)", 20)
    ]

    for name, num_positions in scenarios:
        total_capital_needed = total_capital * num_positions
        total_max_loss = max_loss * num_positions

        print(f"{name}:")
        print(f"  Capital required: ${total_capital_needed:.2f}")
        print(f"  Max portfolio loss: ${total_max_loss:.2f}")
        print(f"  Risk per $1000 portfolio: ${total_max_loss/total_capital_needed*1000:.2f}")
        print()

    # Expected value calculation
    win_rate = 0.40
    avg_winner = 0.67  # 67% from Phase 4
    avg_loser = -0.29  # -29% from Phase 4

    ev_per_trade = (win_rate * avg_winner) + ((1 - win_rate) * avg_loser)

    print(f"EXPECTED VALUE PER TRADE:")
    print(f"  Win rate: {win_rate*100:.0f}%")
    print(f"  Avg winner: {avg_winner*100:+.0f}%")
    print(f"  Avg loser: {avg_loser*100:+.0f}%")
    print(f"  EV: {ev_per_trade*100:+.2f}%")
    print(f"  EV per ${total_capital:.0f} trade: ${ev_per_trade * total_capital:+.2f}")
    print()


def analyze_opportunity_frequency():
    """How often do opportunities arise"""
    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT
        trade_date,
        COUNT(DISTINCT contract_hash) as daily_opps
    FROM (
        SELECT
            contract_hash,
            trade_date,
            MIN(scan_timestamp) as first_scan
        FROM flow_options_scans
        WHERE ask >= 0.03 AND ask <= 0.05
          AND dte >= 20 AND dte <= 28
          AND vega >= 0.015 AND vega <= 0.035
          AND trade_date >= '2025-09-01'
          AND symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')
          AND bid > 0 AND ask > 0
          AND vega IS NOT NULL
          AND delta IS NOT NULL
        GROUP BY contract_hash, trade_date
    )
    GROUP BY trade_date
    ORDER BY trade_date
    """

    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    print("="*70)
    print("OPPORTUNITY FREQUENCY")
    print("="*70)
    print()

    if not rows:
        print("No data found")
        return

    daily_counts = [row[1] for row in rows]
    avg_daily = sum(daily_counts) / len(daily_counts)
    max_daily = max(daily_counts)
    min_daily = min(daily_counts)
    zero_days = len([c for c in daily_counts if c == 0])

    print(f"DAILY OPPORTUNITY COUNT:")
    print(f"  Average per day: {avg_daily:.1f} opportunities")
    print(f"  Maximum: {max_daily} opportunities")
    print(f"  Minimum: {min_daily} opportunities")
    print(f"  Days with zero: {zero_days} days")
    print()

    print(f"WEEKLY/MONTHLY PROJECTIONS:")
    print(f"  Per week (5 days): ~{avg_daily * 5:.0f} opportunities")
    print(f"  Per month (20 days): ~{avg_daily * 20:.0f} opportunities")
    print()

    # Distribution
    print(f"OPPORTUNITY DISTRIBUTION BY DAY:")
    for date, count in rows[:10]:  # Show first 10 days
        print(f"  {date}: {count} opportunities")
    if len(rows) > 10:
        print(f"  ... ({len(rows) - 10} more days)")
    print()


def analyze_monitoring_requirements():
    """How often must positions be checked"""

    print("="*70)
    print("MONITORING REQUIREMENTS")
    print("="*70)
    print()

    print("ENTRY MONITORING:")
    print("  - Scan frequency: Every 20 minutes during market hours")
    print("  - Market hours: 9:30 AM - 4:00 PM ET (6.5 hours)")
    print("  - Scans per day: ~20 scans")
    print("  - Time per scan: 2-3 minutes")
    print("  - Total daily monitoring: ~1 hour")
    print()

    print("POSITION MONITORING (Once entered):")
    print("  - Check frequency: Every 1-2 hours during market")
    print("  - Target: 25% profit (sell immediately when hit)")
    print("  - Average time to target: 2.8 days (from Phase 2)")
    print("  - Max hold period: 5 days")
    print("  - Exit strategy:")
    print("    • Profit target hit: Sell at bid or last (whichever higher)")
    print("    • Day 5: Sell at market regardless of P&L")
    print("    • Loss exceeds -50%: Consider early exit")
    print()


def analyze_risk_management():
    """Risk management rules and guidelines"""

    print("="*70)
    print("RISK MANAGEMENT FRAMEWORK")
    print("="*70)
    print()

    print("POSITION SIZING RULES:")
    print("  1. Max 5% of portfolio per trade")
    print("  2. Max 10 positions simultaneously")
    print("  3. Max 2 positions in same symbol")
    print("  4. Max 50% total capital deployed")
    print()

    print("ENTRY RULES:")
    print("  1. Ask price: $0.03-0.05 only")
    print("  2. DTE: 20-28 days only")
    print("  3. Vega: 0.015-0.035 only")
    print("  4. Symbols: Focus XLI and XLF primarily")
    print("  5. Option type: Calls only (puts excluded)")
    print("  6. Delta: Confirm <0.15 (deep OTM)")
    print("  7. IV: Lower is better within filter range")
    print()

    print("EXIT RULES:")
    print("  1. Primary: Exit at 25% profit (sell immediately)")
    print("  2. Time stop: Exit day 5 regardless of P&L")
    print("  3. Loss stop: Consider exit if loss >-50%")
    print("  4. Execution: Use limit orders, sell at max(bid, last)")
    print()

    print("PORTFOLIO LIMITS:")
    print("  1. Max total capital at risk: 50% of account")
    print("  2. Max loss per day: 3 position stop-outs")
    print("  3. Max loss per week: -10% of starting capital")
    print("  4. Pause trading if weekly loss >-10%")
    print()


def main():
    print("\n")
    print("="*70)
    print("PHASE 5: PRACTICAL CONSTRAINTS ANALYSIS")
    print("="*70)
    print("\n")

    analyze_liquidity()
    analyze_capital_requirements()
    analyze_opportunity_frequency()
    analyze_monitoring_requirements()
    analyze_risk_management()

    print("="*70)
    print("PHASE 5 COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
