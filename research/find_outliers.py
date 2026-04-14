"""Find outliers that defy the max pain hypothesis."""

import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/sector_archive/airlines.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all data with volume changes
query = """
WITH volume_analysis AS (
    SELECT
        m.*,
        ROUND(ABS((fri.volume - mon.volume) / CAST(mon.volume AS FLOAT) * 100), 2) as abs_vol_change,
        mon.volume as mon_volume,
        fri.volume as fri_volume
    FROM max_pain_analysis m
    JOIN historical_prices mon ON m.symbol = mon.symbol AND m.week_start_date = mon.trade_date
    JOIN historical_prices fri ON m.symbol = fri.symbol AND m.week_end_date = fri.trade_date
)
SELECT
    symbol,
    week_id,
    week_start_date,
    week_end_date,
    hit_max_pain_1pct,
    ROUND(ABS(mon_gap_pct), 2) as init_dist,
    ROUND(ABS(fri_gap_pct), 2) as final_dist,
    abs_vol_change,
    ROUND(mon_oi/1000.0, 1) as oi_k,
    ROUND(mon_iv*100, 2) as iv_pct,
    ROUND(fri_iv*100, 2) as fri_iv_pct,
    ROUND(price_change_pct, 2) as price_chg,
    mon_price,
    fri_price,
    mon_max_pain,
    fri_max_pain
FROM volume_analysis
ORDER BY symbol, week_id
"""

cursor.execute(query)
rows = cursor.fetchall()

# Categorize outliers
should_hit_missed = []
shouldnt_hit_hit = []

for row in rows:
    (symbol, week_id, week_start, week_end, hit, init_dist, final_dist,
     vol_chg, oi_k, iv_pct, fri_iv_pct, price_chg, mon_price, fri_price,
     mon_max_pain, fri_max_pain) = row

    # Should have hit but missed: low volume, close distance, but missed
    if hit == 0 and vol_chg and vol_chg < 20 and init_dist and init_dist < 2:
        should_hit_missed.append({
            'symbol': symbol,
            'week_id': week_id,
            'week_start': week_start,
            'init_dist': init_dist,
            'final_dist': final_dist,
            'vol_chg': vol_chg,
            'oi_k': oi_k,
            'iv_pct': iv_pct,
            'fri_iv_pct': fri_iv_pct,
            'price_chg': price_chg,
            'mon_price': mon_price,
            'fri_price': fri_price,
            'mon_max_pain': mon_max_pain,
            'fri_max_pain': fri_max_pain
        })

    # Shouldn't have hit but did: high volume OR far distance, but hit
    if hit == 1 and ((vol_chg and vol_chg > 40) or (init_dist and init_dist > 5)):
        shouldnt_hit_hit.append({
            'symbol': symbol,
            'week_id': week_id,
            'week_start': week_start,
            'init_dist': init_dist,
            'final_dist': final_dist,
            'vol_chg': vol_chg,
            'oi_k': oi_k,
            'iv_pct': iv_pct,
            'fri_iv_pct': fri_iv_pct,
            'price_chg': price_chg,
            'mon_price': mon_price,
            'fri_price': fri_price,
            'mon_max_pain': mon_max_pain,
            'fri_max_pain': fri_max_pain
        })

conn.close()

# Print results
print("=" * 100)
print("OUTLIERS: SHOULD HAVE HIT BUT MISSED")
print(f"(Low volume <20%, close distance <2%, but missed)")
print("=" * 100)
print(f"Count: {len(should_hit_missed)}")
print()

if should_hit_missed:
    print(f"{'Symbol':<8} {'Week':<10} {'Date':<12} {'InitDist':<10} {'VolChg':<10} {'OI(K)':<10} {'IV%':<8} {'PriceChg':<10}")
    print("-" * 100)
    for r in should_hit_missed:
        iv_str = f"{r['iv_pct']:.0f}" if r['iv_pct'] is not None else "N/A"
        print(f"{r['symbol']:<8} {r['week_id']:<10} {r['week_start']:<12} {r['init_dist']:<10} {r['vol_chg']:<10} {r['oi_k']:<10} {iv_str:<8} {r['price_chg']:<10}")

    print("\nDetailed Analysis:")
    print("-" * 100)
    for r in should_hit_missed:
        print(f"\n{r['symbol']} Week {r['week_id']} ({r['week_start']}):")
        print(f"  Monday:  Price=${r['mon_price']:.2f}, MaxPain=${r['mon_max_pain']:.2f} (gap: {r['init_dist']:.2f}%)")
        print(f"  Friday:  Price=${r['fri_price']:.2f}, MaxPain=${r['fri_max_pain']:.2f} (gap: {r['final_dist']:.2f}%)")
        print(f"  Movement: {r['price_chg']:.2f}% price change, {r['vol_chg']:.2f}% volume change")
        iv_mon = f"{r['iv_pct']:.0f}%" if r['iv_pct'] is not None else "N/A"
        iv_fri = f"{r['fri_iv_pct']:.0f}%" if r['fri_iv_pct'] is not None else "N/A"
        print(f"  Context: {r['oi_k']:.1f}K OI, {iv_mon} IV -> {iv_fri} IV")

print("\n" + "=" * 100)
print("OUTLIERS: SHOULDN'T HAVE HIT BUT DID")
print(f"(High volume >40% OR far distance >5%, but hit anyway)")
print("=" * 100)
print(f"Count: {len(shouldnt_hit_hit)}")
print()

if shouldnt_hit_hit:
    print(f"{'Symbol':<8} {'Week':<10} {'Date':<12} {'InitDist':<10} {'VolChg':<10} {'OI(K)':<10} {'IV%':<8} {'PriceChg':<10}")
    print("-" * 100)
    for r in shouldnt_hit_hit:
        iv_str = f"{r['iv_pct']:.0f}" if r['iv_pct'] is not None else "N/A"
        print(f"{r['symbol']:<8} {r['week_id']:<10} {r['week_start']:<12} {r['init_dist']:<10} {r['vol_chg']:<10} {r['oi_k']:<10} {iv_str:<8} {r['price_chg']:<10}")

    print("\nDetailed Analysis:")
    print("-" * 100)
    for r in shouldnt_hit_hit:
        print(f"\n{r['symbol']} Week {r['week_id']} ({r['week_start']}):")
        print(f"  Monday:  Price=${r['mon_price']:.2f}, MaxPain=${r['mon_max_pain']:.2f} (gap: {r['init_dist']:.2f}%)")
        print(f"  Friday:  Price=${r['fri_price']:.2f}, MaxPain=${r['fri_max_pain']:.2f} (gap: {r['final_dist']:.2f}%)")
        print(f"  Movement: {r['price_chg']:.2f}% price change, {r['vol_chg']:.2f}% volume change")
        iv_mon = f"{r['iv_pct']:.0f}%" if r['iv_pct'] is not None else "N/A"
        iv_fri = f"{r['fri_iv_pct']:.0f}%" if r['fri_iv_pct'] is not None else "N/A"
        print(f"  Context: {r['oi_k']:.1f}K OI, {iv_mon} IV -> {iv_fri} IV")
