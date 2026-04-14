#!/usr/bin/env python3
"""
Phase 3: Parameter Sweep Analysis
Compare winners vs losers across key parameters to find predictive filters
"""

import sqlite3
import sys
from collections import defaultdict

DB_PATH = "../data/datalake_query.db"

# Load results from Phase 2 analysis
def load_results_from_db():
    """Load all entries and outcomes from Phase 2"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # We need to re-run the basic entry identification
    # Get all qualifying scans
    query = """
    SELECT
        contract_hash,
        trade_date,
        MIN(scan_timestamp) as entry_timestamp,
        symbol,
        strike,
        expiration_date,
        option_type,
        underlying_price,
        dte,
        delta,
        vega,
        theta,
        gamma,
        iv
    FROM flow_options_scans
    WHERE ask >= 0.03 AND ask <= 0.10
      AND dte >= 20 AND dte <= 60
      AND trade_date >= '2025-09-01'
      AND symbol NOT IN ('SPY', 'QQQ', 'IWM', 'DIA', 'VIX')
      AND bid > 0 AND ask > 0
      AND vega IS NOT NULL
      AND delta IS NOT NULL
    GROUP BY contract_hash, trade_date
    """

    cursor = conn.cursor()
    cursor.execute(query)
    entries = cursor.fetchall()
    conn.close()

    return [dict(row) for row in entries]

def get_first_scan_details(contract_hash, trade_date):
    """Get full details of first scan on given date"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
    SELECT ask, bid, delta, vega, theta, iv, dte, underlying_price
    FROM flow_options_scans
    WHERE contract_hash = ?
      AND trade_date = ?
    ORDER BY scan_timestamp
    LIMIT 1
    """

    cursor = conn.cursor()
    cursor.execute(query, (contract_hash, trade_date))
    result = cursor.fetchone()
    conn.close()

    return dict(result) if result else None

def check_if_winner(contract_hash, entry_date, entry_ask):
    """Check if contract hit 25% target in next 5 days"""
    conn = sqlite3.connect(DB_PATH)

    query = """
    SELECT MAX(CASE WHEN bid > last_price THEN bid ELSE COALESCE(last_price, bid) END) as max_sellable
    FROM flow_options_scans
    WHERE contract_hash = ?
      AND trade_date > ?
      AND trade_date <= date(?, '+5 days')
    """

    cursor = conn.cursor()
    cursor.execute(query, (contract_hash, entry_date, entry_date))
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        max_sellable = result[0]
        target = entry_ask * 1.25
        return max_sellable >= target, max_sellable

    return False, 0

# Analysis functions
def analyze_by_delta(entries_with_outcomes):
    """Win rate by delta buckets"""
    buckets = {
        '<0.05': [],
        '0.05-0.10': [],
        '0.10-0.20': [],
        '0.20-0.30': [],
        '>0.30': []
    }

    for entry in entries_with_outcomes:
        delta = abs(entry['delta'])

        if delta < 0.05:
            bucket = '<0.05'
        elif delta < 0.10:
            bucket = '0.05-0.10'
        elif delta < 0.20:
            bucket = '0.10-0.20'
        elif delta < 0.30:
            bucket = '0.20-0.30'
        else:
            bucket = '>0.30'

        buckets[bucket].append(entry)

    print("\n=== WIN RATE BY DELTA ===")
    for bucket, entries in sorted(buckets.items()):
        if len(entries) == 0:
            continue

        winners = sum(1 for e in entries if e['is_winner'])
        win_rate = winners / len(entries) * 100

        print(f"{bucket:15} | n={len(entries):4} | Winners={winners:3} | Win Rate={win_rate:5.2f}%")

def analyze_by_vega(entries_with_outcomes):
    """Win rate by vega buckets"""
    buckets = {
        '<0.01': [],
        '0.01-0.02': [],
        '0.02-0.03': [],
        '>0.03': []
    }

    for entry in entries_with_outcomes:
        vega = entry['vega']

        if vega < 0.01:
            bucket = '<0.01'
        elif vega < 0.02:
            bucket = '0.01-0.02'
        elif vega < 0.03:
            bucket = '0.02-0.03'
        else:
            bucket = '>0.03'

        buckets[bucket].append(entry)

    print("\n=== WIN RATE BY VEGA ===")
    for bucket, entries in sorted(buckets.items()):
        if len(entries) == 0:
            continue

        winners = sum(1 for e in entries if e['is_winner'])
        win_rate = winners / len(entries) * 100

        print(f"{bucket:15} | n={len(entries):4} | Winners={winners:3} | Win Rate={win_rate:5.2f}%")

def analyze_by_iv(entries_with_outcomes):
    """Win rate by IV buckets"""
    buckets = {
        '<0.30': [],
        '0.30-0.50': [],
        '0.50-0.80': [],
        '>0.80': []
    }

    for entry in entries_with_outcomes:
        iv = entry['iv']

        if iv < 0.30:
            bucket = '<0.30'
        elif iv < 0.50:
            bucket = '0.30-0.50'
        elif iv < 0.80:
            bucket = '0.50-0.80'
        else:
            bucket = '>0.80'

        buckets[bucket].append(entry)

    print("\n=== WIN RATE BY IV ===")
    for bucket, entries in sorted(buckets.items()):
        if len(entries) == 0:
            continue

        winners = sum(1 for e in entries if e['is_winner'])
        win_rate = winners / len(entries) * 100

        print(f"{bucket:15} | n={len(entries):4} | Winners={winners:3} | Win Rate={win_rate:5.2f}%")

def analyze_by_dte(entries_with_outcomes):
    """Win rate by DTE buckets"""
    buckets = {
        '20-25': [],
        '26-30': [],
        '31-40': [],
        '41-60': []
    }

    for entry in entries_with_outcomes:
        dte = entry['dte']

        if dte <= 25:
            bucket = '20-25'
        elif dte <= 30:
            bucket = '26-30'
        elif dte <= 40:
            bucket = '31-40'
        else:
            bucket = '41-60'

        buckets[bucket].append(entry)

    print("\n=== WIN RATE BY DTE ===")
    for bucket, entries in sorted(buckets.items()):
        if len(entries) == 0:
            continue

        winners = sum(1 for e in entries if e['is_winner'])
        win_rate = winners / len(entries) * 100

        print(f"{bucket:15} | n={len(entries):4} | Winners={winners:3} | Win Rate={win_rate:5.2f}%")

def analyze_by_entry_price(entries_with_outcomes):
    """Win rate by entry ask price"""
    buckets = {
        '$0.03-0.04': [],
        '$0.05-0.06': [],
        '$0.07-0.10': []
    }

    for entry in entries_with_outcomes:
        ask = entry['entry_ask']

        if ask < 0.05:
            bucket = '$0.03-0.04'
        elif ask < 0.07:
            bucket = '$0.05-0.06'
        else:
            bucket = '$0.07-0.10'

        buckets[bucket].append(entry)

    print("\n=== WIN RATE BY ENTRY PRICE ===")
    for bucket, entries in sorted(buckets.items()):
        if len(entries) == 0:
            continue

        winners = sum(1 for e in entries if e['is_winner'])
        win_rate = winners / len(entries) * 100

        print(f"{bucket:15} | n={len(entries):4} | Winners={winners:3} | Win Rate={win_rate:5.2f}%")

def analyze_by_option_type(entries_with_outcomes):
    """Win rate by put vs call"""
    buckets = {'PUT': [], 'CALL': []}

    for entry in entries_with_outcomes:
        opt_type = entry['option_type'].upper()
        if opt_type in buckets:
            buckets[opt_type].append(entry)

    print("\n=== WIN RATE BY OPTION TYPE ===")
    for opt_type, entries in buckets.items():
        if len(entries) == 0:
            continue

        winners = sum(1 for e in entries if e['is_winner'])
        win_rate = winners / len(entries) * 100

        print(f"{opt_type:15} | n={len(entries):4} | Winners={winners:3} | Win Rate={win_rate:5.2f}%")

def main():
    print("=== Phase 3: Parameter Sweep Analysis ===\n")
    print("Loading entries... (this will take a moment)")

    # Load basic entry data
    entries = load_results_from_db()
    print(f"Loaded {len(entries)} entry points")

    # Sample subset for speed (use every 10th entry)
    print("Sampling entries for analysis speed...")
    sampled_entries = entries[::10]
    print(f"Analyzing {len(sampled_entries)} sampled entries")

    # Enrich with outcomes
    print("\nChecking outcomes for sampled entries...")
    entries_with_outcomes = []

    for i, entry in enumerate(sampled_entries):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(sampled_entries)}...")

        details = get_first_scan_details(entry['contract_hash'], entry['trade_date'])
        if not details:
            continue

        entry_ask = details['ask']
        is_winner, max_sellable = check_if_winner(
            entry['contract_hash'],
            entry['trade_date'],
            entry_ask
        )

        entries_with_outcomes.append({
            **entry,
            'entry_ask': entry_ask,
            'is_winner': is_winner,
            'max_sellable': max_sellable,
            'delta': details['delta'],
            'vega': details['vega'],
            'iv': details['iv'],
            'dte': details['dte']
        })

    print(f"\nAnalyzing {len(entries_with_outcomes)} entries with complete data\n")

    # Run all analyses
    analyze_by_delta(entries_with_outcomes)
    analyze_by_vega(entries_with_outcomes)
    analyze_by_iv(entries_with_outcomes)
    analyze_by_dte(entries_with_outcomes)
    analyze_by_entry_price(entries_with_outcomes)
    analyze_by_option_type(entries_with_outcomes)

    print("\n=== Analysis Complete ===")

if __name__ == "__main__":
    main()
