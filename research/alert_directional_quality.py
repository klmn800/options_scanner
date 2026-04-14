"""
Alert Directional Quality Analysis

Instead of option max profit (always positive), check whether the UNDERLYING
moved in the direction the alert implied. A call alert is correct if the stock
went up. A put alert is correct if it went down. This is the real signal quality.
"""

import sqlite3
import re
import math
from datetime import datetime, timedelta

conn = sqlite3.connect('data/datalake_query.db')
conn.row_factory = sqlite3.Row

# Get alerts with option type (call/put) for direction
cursor = conn.execute('''
    SELECT fa.symbol, fa.significance_score, fa.premium_value, fa.volume_surprise_factor,
           fa.alert_reason, fa.option_type, fa.alert_timestamp, fa.underlying_price,
           fa.delta, fa.dte, fa.volume,
           fa.max_prof_7d_pct, fa.max_loss_7d_pct
    FROM flow_alerts fa
    WHERE fa.option_type IS NOT NULL
''')
alerts = [dict(r) for r in cursor.fetchall()]

print(f'Total alerts with option_type: {len(alerts)}')

# For each alert, look up underlying price 1d, 3d, 7d later from historical_prices
# Build a cache of price data
cursor2 = conn.execute('''
    SELECT symbol, trade_date, close_price
    FROM historical_prices
    WHERE trade_date >= '2025-09-01'
    ORDER BY symbol, trade_date
''')
prices = {}
for r in cursor2.fetchall():
    key = r['symbol']
    if key not in prices:
        prices[key] = {}
    prices[key][r['trade_date']] = r['close_price']

conn.close()

print(f'Price data for {len(prices)} symbols')
print()


def parse_smart(reason):
    m = re.search(r'smart=([\d.]+)', reason or '')
    return float(m.group(1)) if m else 0.0


def vol_surprise_score(vs):
    if vs is None or vs <= 0:
        return 0.0
    if vs >= 25.0:
        s = min(4.0, 2.0 + math.log10(vs / 25.0) * 2.0)
    elif vs >= 10.0:
        s = min(3.0, 1.5 + (vs - 10.0) / 15.0 * 1.5)
    else:
        s = min(2.0, (vs - 3.0) / 2.0 + 1.0)
    return max(0.0, s)


def prem_score_log2(premium, threshold=150000):
    if not premium or premium < 1:
        return 0.0
    try:
        return min(6.0, max(0.0, math.log10(premium / threshold) * 2.0))
    except:
        return 0.0


def get_future_price(symbol, alert_date_str, days_ahead):
    """Find close price N trading days after alert date"""
    if symbol not in prices:
        return None
    sym_prices = prices[symbol]

    # Get alert date
    alert_date = datetime.strptime(alert_date_str[:10], '%Y-%m-%d')

    # Look forward for the Nth trading day
    trading_days_found = 0
    for i in range(1, days_ahead * 2 + 5):  # search window
        check_date = (alert_date + timedelta(days=i)).strftime('%Y-%m-%d')
        if check_date in sym_prices:
            trading_days_found += 1
            if trading_days_found >= days_ahead:
                return sym_prices[check_date]
    return None


# Enrich alerts with direction correctness
enriched = []
for a in alerts:
    smart = parse_smart(a['alert_reason'])
    prem = prem_score_log2(a['premium_value'] or 0)
    vol = vol_surprise_score(a['volume_surprise_factor'] or 0)
    a['fixed_score'] = min(10.0, prem + vol + smart)
    a['prem_score'] = prem
    a['vol_score'] = vol
    a['smart'] = smart

    sym = a['symbol']
    ts = a['alert_timestamp']
    alert_price = a['underlying_price']

    if not alert_price or alert_price <= 0:
        continue

    # Get future prices
    p1 = get_future_price(sym, ts, 1)
    p3 = get_future_price(sym, ts, 3)
    p5 = get_future_price(sym, ts, 5)
    p10 = get_future_price(sym, ts, 10)

    if p5 is None:
        continue  # need at least 5-day data

    is_call = a['option_type'].lower() == 'call'

    # Calculate moves
    a['move_1d'] = ((p1 - alert_price) / alert_price * 100) if p1 else None
    a['move_3d'] = ((p3 - alert_price) / alert_price * 100) if p3 else None
    a['move_5d'] = ((p5 - alert_price) / alert_price * 100) if p5 else None
    a['move_10d'] = ((p10 - alert_price) / alert_price * 100) if p10 else None

    # Directional correctness: call wants up, put wants down
    if is_call:
        a['correct_1d'] = (a['move_1d'] > 0) if a['move_1d'] is not None else None
        a['correct_3d'] = (a['move_3d'] > 0) if a['move_3d'] is not None else None
        a['correct_5d'] = (a['move_5d'] > 0) if a['move_5d'] is not None else None
        a['correct_10d'] = (a['move_10d'] > 0) if a['move_10d'] is not None else None
    else:
        a['correct_1d'] = (a['move_1d'] < 0) if a['move_1d'] is not None else None
        a['correct_3d'] = (a['move_3d'] < 0) if a['move_3d'] is not None else None
        a['correct_5d'] = (a['move_5d'] < 0) if a['move_5d'] is not None else None
        a['correct_10d'] = (a['move_10d'] < 0) if a['move_10d'] is not None else None

    # Magnitude of move in the "right" direction (positive = directionally correct)
    sign = 1 if is_call else -1
    a['directional_move_5d'] = (a['move_5d'] * sign) if a['move_5d'] is not None else None

    enriched.append(a)

print(f'Enriched alerts with directional data: {len(enriched)}')
print()


def pct_correct(group, field):
    vals = [a[field] for a in group if a[field] is not None]
    if not vals:
        return 0, 0
    return sum(1 for v in vals if v) / len(vals) * 100, len(vals)


def avg_val(group, field):
    vals = [a[field] for a in group if a[field] is not None]
    return sum(vals) / len(vals) if vals else 0


def median_val(group, field):
    vals = sorted([a[field] for a in group if a[field] is not None])
    if not vals:
        return 0
    return vals[len(vals) // 2]


# MAIN ANALYSIS: Score band vs directional correctness
print('=' * 95)
print('DIRECTIONAL ACCURACY BY FIXED SCORE BAND')
print('(% of time the underlying moved in the direction the option type implies)')
print('=' * 95)

header = f'{"Score Band":<12} {"Count":>6} {"Avg Prem":>12} {"1d Correct":>11} {"3d Correct":>11} {"5d Correct":>11} {"Avg 5d Move":>12}'
print(header)
print('-' * 95)

for lo, hi, label in [
    (4.0, 4.5, '4.0-4.5'), (4.5, 5.0, '4.5-5.0'), (5.0, 5.5, '5.0-5.5'),
    (5.5, 6.0, '5.5-6.0'), (6.0, 6.5, '6.0-6.5'), (6.5, 7.0, '6.5-7.0'),
    (7.0, 8.0, '7.0-8.0'), (8.0, 10.1, '8.0+')
]:
    band = [a for a in enriched if lo <= a['fixed_score'] < hi]
    if not band:
        print(f'{label:<12} {0:>6}')
        continue

    ap = avg_val(band, 'premium_value')
    c1, n1 = pct_correct(band, 'correct_1d')
    c3, n3 = pct_correct(band, 'correct_3d')
    c5, n5 = pct_correct(band, 'correct_5d')
    avg_dir = avg_val(band, 'directional_move_5d')

    print(f'{label:<12} {len(band):>6} {ap:>12,.0f} {c1:>9.0f}%  {c3:>9.0f}%  {c5:>9.0f}%  {avg_dir:>+10.2f}%')

# Now the key question: survivors vs dropouts
print()
print('=' * 95)
print('SURVIVORS vs DROPOUTS - DIRECTIONAL QUALITY')
print('=' * 95)

survivors = [a for a in enriched if a['fixed_score'] >= 6.0]
dropouts = [a for a in enriched if a['fixed_score'] < 6.0]

for group, label in [(survivors, 'SURVIVORS (>= 6.0)'), (dropouts, 'DROPOUTS (< 6.0)')]:
    print(f'\n  {label} ({len(group)} alerts)')
    print(f'    Avg premium:       ${avg_val(group, "premium_value"):>12,.0f}')
    print(f'    Avg vol surprise:     {avg_val(group, "volume_surprise_factor"):>8.1f}x')

    for window in ['1d', '3d', '5d', '10d']:
        correct_field = f'correct_{window}'
        move_field = f'move_{window}'
        pct, n = pct_correct(group, correct_field)
        avg_m = avg_val(group, move_field) if window != '10d' else avg_val(group, 'move_10d')
        med_m = median_val(group, move_field) if window != '10d' else median_val(group, 'move_10d')
        print(f'    {window}: {pct:>5.1f}% correct (n={n:>4})  avg underlying move: {avg_m:>+6.2f}%  median: {med_m:>+6.2f}%')

# Premium-weighted directional analysis
print()
print('=' * 95)
print('PREMIUM-WEIGHTED: Does premium SIZE predict direction better?')
print('(Higher premium = institution put more money behind the thesis)')
print('=' * 95)

prem_bands = [
    (0, 1_000_000, '<$1M'),
    (1_000_000, 3_000_000, '$1-3M'),
    (3_000_000, 5_000_000, '$3-5M'),
    (5_000_000, 10_000_000, '$5-10M'),
    (10_000_000, 50_000_000, '$10-50M'),
    (50_000_000, 1e12, '$50M+'),
]

header = f'{"Premium Band":<14} {"Count":>6} {"1d Correct":>11} {"3d Correct":>11} {"5d Correct":>11} {"Avg DirMove 5d":>15}'
print(header)
print('-' * 75)

for lo, hi, label in prem_bands:
    band = [a for a in enriched if lo <= (a['premium_value'] or 0) < hi]
    if not band:
        continue
    c1, _ = pct_correct(band, 'correct_1d')
    c3, _ = pct_correct(band, 'correct_3d')
    c5, _ = pct_correct(band, 'correct_5d')
    avg_dir = avg_val(band, 'directional_move_5d')
    print(f'{label:<14} {len(band):>6} {c1:>9.0f}%  {c3:>9.0f}%  {c5:>9.0f}%  {avg_dir:>+13.2f}%')

# Volume surprise bands
print()
print('=' * 95)
print('VOLUME SURPRISE: Does volume surprise predict direction?')
print('=' * 95)

vol_bands = [
    (3, 5, '3-5x'), (5, 10, '5-10x'), (10, 20, '10-20x'),
    (20, 50, '20-50x'), (50, 1000, '50x+'),
]

print(header.replace('Premium Band', 'Vol Surprise '))
print('-' * 75)

for lo, hi, label in vol_bands:
    band = [a for a in enriched if lo <= (a['volume_surprise_factor'] or 0) < hi]
    if not band:
        continue
    c1, _ = pct_correct(band, 'correct_1d')
    c3, _ = pct_correct(band, 'correct_3d')
    c5, _ = pct_correct(band, 'correct_5d')
    avg_dir = avg_val(band, 'directional_move_5d')
    print(f'{label:<14} {len(band):>6} {c1:>9.0f}%  {c3:>9.0f}%  {c5:>9.0f}%  {avg_dir:>+13.2f}%')
