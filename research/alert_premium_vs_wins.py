"""
Premium vs Win Rate Analysis

User's strategy: buy on alert, look for 18%+ gain within a few days, sell.
Does premium value correlate with the likelihood of hitting that target?

Uses max_prof_Xd_pct which measures peak option price gain at any point
during the window — this matches "I sell when it's high" behavior.
"""

import sqlite3
import re
import math

conn = sqlite3.connect('data/datalake_query.db')
conn.row_factory = sqlite3.Row

cursor = conn.execute('''
    SELECT symbol, significance_score, premium_value, volume_surprise_factor,
           alert_reason, option_type, alert_timestamp, underlying_price,
           delta, dte, volume,
           max_prof_1d_pct, max_prof_3d_pct, max_prof_7d_pct, max_prof_14d_pct,
           max_loss_1d_pct, max_loss_3d_pct, max_loss_7d_pct, max_loss_14d_pct
    FROM flow_alerts
    WHERE max_prof_3d_pct IS NOT NULL
''')
alerts = [dict(r) for r in cursor.fetchall()]
conn.close()

print(f'Alerts with profit tracking data: {len(alerts)}')

# Check how many have various windows
for field in ['max_prof_1d_pct', 'max_prof_3d_pct', 'max_prof_7d_pct']:
    n = sum(1 for a in alerts if a[field] is not None)
    print(f'  {field}: {n}')
print()

WIN_THRESHOLD = 18.0  # User's target: 18%+ gain


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


# Enrich with fixed scores
for a in alerts:
    smart = parse_smart(a['alert_reason'])
    prem = prem_score_log2(a['premium_value'] or 0)
    vol = vol_surprise_score(a['volume_surprise_factor'] or 0)
    a['fixed_score'] = min(10.0, prem + vol + smart)
    a['prem_score'] = prem
    a['vol_score'] = vol
    a['smart'] = smart


def analyze_band(group, label):
    """For a group of alerts, compute win rates at various thresholds and windows"""
    if not group:
        return None

    results = {}
    for window in ['1d', '3d', '7d']:
        field = f'max_prof_{window}_pct'
        with_data = [a for a in group if a[field] is not None]
        if not with_data:
            continue

        n = len(with_data)
        wins = sum(1 for a in with_data if (a[field] or 0) >= WIN_THRESHOLD)
        avg_prof = sum(a[field] or 0 for a in with_data) / n
        med_prof = sorted(a[field] or 0 for a in with_data)[n // 2]

        # Also compute avg max loss as risk measure
        loss_field = f'max_loss_{window}_pct'
        losses = [a[loss_field] for a in with_data if a[loss_field] is not None]
        avg_loss = sum(losses) / len(losses) if losses else 0

        results[window] = {
            'n': n,
            'win_rate': wins / n * 100,
            'avg_prof': avg_prof,
            'med_prof': med_prof,
            'avg_loss': avg_loss,
        }
    return results


# ==========================================
# PREMIUM BANDS vs WIN RATE
# ==========================================
print('=' * 100)
print(f'PREMIUM vs WIN RATE (win = option peaks >= {WIN_THRESHOLD}% at any point in window)')
print('=' * 100)
print()

prem_bands = [
    (0, 500_000, '<$500K'),
    (500_000, 1_000_000, '$500K-1M'),
    (1_000_000, 2_000_000, '$1-2M'),
    (2_000_000, 3_500_000, '$2-3.5M'),
    (3_500_000, 5_000_000, '$3.5-5M'),
    (5_000_000, 10_000_000, '$5-10M'),
    (10_000_000, 25_000_000, '$10-25M'),
    (25_000_000, 1e12, '$25M+'),
]

print(f'{"Premium Band":<14} {"Count":>6} | {"1d Win%":>8} {"1d Avg":>8} {"1d Loss":>8} | {"3d Win%":>8} {"3d Avg":>8} {"3d Loss":>8} | {"7d Win%":>8} {"7d Avg":>8} {"7d Loss":>8}')
print('-' * 120)

for lo, hi, label in prem_bands:
    band = [a for a in alerts if lo <= (a['premium_value'] or 0) < hi]
    r = analyze_band(band, label)
    if not r:
        print(f'{label:<14} {len(band):>6}')
        continue

    parts = [f'{label:<14} {len(band):>6} |']
    for w in ['1d', '3d', '7d']:
        if w in r:
            d = r[w]
            parts.append(f' {d["win_rate"]:>6.0f}% {d["avg_prof"]:>+7.1f}% {d["avg_loss"]:>+7.1f}% |')
        else:
            parts.append(f' {"N/A":>7} {"N/A":>8} {"N/A":>8} |')
    print(''.join(parts))


# ==========================================
# VOLUME SURPRISE BANDS vs WIN RATE
# ==========================================
print()
print('=' * 100)
print(f'VOLUME SURPRISE vs WIN RATE (win = option peaks >= {WIN_THRESHOLD}%)')
print('=' * 100)
print()

vol_bands = [
    (3, 5, '3-5x'),
    (5, 8, '5-8x'),
    (8, 15, '8-15x'),
    (15, 25, '15-25x'),
    (25, 50, '25-50x'),
    (50, 1000, '50x+'),
]

print(f'{"Vol Surprise":<14} {"Count":>6} | {"1d Win%":>8} {"1d Avg":>8} {"1d Loss":>8} | {"3d Win%":>8} {"3d Avg":>8} {"3d Loss":>8} | {"7d Win%":>8} {"7d Avg":>8} {"7d Loss":>8}')
print('-' * 120)

for lo, hi, label in vol_bands:
    band = [a for a in alerts if lo <= (a['volume_surprise_factor'] or 0) < hi]
    r = analyze_band(band, label)
    if not r:
        print(f'{label:<14} {len(band):>6}')
        continue

    parts = [f'{label:<14} {len(band):>6} |']
    for w in ['1d', '3d', '7d']:
        if w in r:
            d = r[w]
            parts.append(f' {d["win_rate"]:>6.0f}% {d["avg_prof"]:>+7.1f}% {d["avg_loss"]:>+7.1f}% |')
        else:
            parts.append(f' {"N/A":>7} {"N/A":>8} {"N/A":>8} |')
    print(''.join(parts))


# ==========================================
# CROSS-TABULATION: Premium × Volume Surprise → Win Rate (7d)
# ==========================================
print()
print('=' * 100)
print(f'CROSS-TAB: Premium x Vol Surprise -> 7d Win Rate (>= {WIN_THRESHOLD}%)')
print('(cell = win_rate% / count)')
print('=' * 100)
print()

prem_cross = [
    (0, 1_000_000, '<$1M'),
    (1_000_000, 2_500_000, '$1-2.5M'),
    (2_500_000, 5_000_000, '$2.5-5M'),
    (5_000_000, 10_000_000, '$5-10M'),
    (10_000_000, 1e12, '$10M+'),
]

vol_cross = [
    (3, 7, '3-7x'),
    (7, 15, '7-15x'),
    (15, 30, '15-30x'),
    (30, 1000, '30x+'),
]

# Header
header = f'{"":>14}'
for _, _, vlabel in vol_cross:
    header += f' {vlabel:>14}'
print(header)
print('-' * (14 + 15 * len(vol_cross)))

alerts_7d = [a for a in alerts if a['max_prof_7d_pct'] is not None]

for plo, phi, plabel in prem_cross:
    row = f'{plabel:>14}'
    for vlo, vhi, vlabel in vol_cross:
        cell = [a for a in alerts_7d
                if plo <= (a['premium_value'] or 0) < phi
                and vlo <= (a['volume_surprise_factor'] or 0) < vhi]
        if cell:
            wins = sum(1 for a in cell if (a['max_prof_7d_pct'] or 0) >= WIN_THRESHOLD)
            wr = wins / len(cell) * 100
            row += f' {wr:>5.0f}%/n={len(cell):<4}'
        else:
            row += f' {"---":>14}'
    print(row)


# ==========================================
# SCORE BAND vs WIN RATE (using fixed score)
# ==========================================
print()
print('=' * 100)
print(f'FIXED SCORE vs WIN RATE (win = option peaks >= {WIN_THRESHOLD}%)')
print('=' * 100)
print()

score_bands = [
    (4.0, 4.5, '4.0-4.5'), (4.5, 5.0, '4.5-5.0'), (5.0, 5.5, '5.0-5.5'),
    (5.5, 6.0, '5.5-6.0'), (6.0, 6.5, '6.0-6.5'), (6.5, 7.0, '6.5-7.0'),
    (7.0, 8.0, '7.0-8.0'), (8.0, 10.1, '8.0+'),
]

print(f'{"Score Band":<12} {"Count":>6} | {"1d Win%":>8} {"1d Avg":>8} | {"3d Win%":>8} {"3d Avg":>8} | {"7d Win%":>8} {"7d Avg":>8} | {"Avg Prem":>12} {"Avg VolSurp":>11}')
print('-' * 115)

for lo, hi, label in score_bands:
    band = [a for a in alerts if lo <= a['fixed_score'] < hi]
    r = analyze_band(band, label)
    if not r:
        print(f'{label:<12} {len(band):>6}')
        continue

    avg_prem = sum(a['premium_value'] or 0 for a in band) / len(band)
    avg_vol = sum(a['volume_surprise_factor'] or 0 for a in band) / len(band)

    parts = [f'{label:<12} {len(band):>6} |']
    for w in ['1d', '3d', '7d']:
        if w in r:
            d = r[w]
            parts.append(f' {d["win_rate"]:>6.0f}% {d["avg_prof"]:>+7.1f}% |')
        else:
            parts.append(f' {"N/A":>7} {"N/A":>8} |')
    parts.append(f' {avg_prem:>12,.0f} {avg_vol:>10.1f}x')
    print(''.join(parts))


# ==========================================
# RISK-ADJUSTED: Win% minus max drawdown
# ==========================================
print()
print('=' * 100)
print('RISK PROFILE BY PREMIUM BAND')
print('(How bad does it get before the win? Avg max drawdown within 3d window)')
print('=' * 100)
print()

print(f'{"Premium Band":<14} {"Count":>6} {"3d Win%":>8} {"Avg 3d Peak":>12} {"Avg 3d Trough":>14} {"Peak/Trough":>12}')
print('-' * 75)

for lo, hi, label in prem_bands:
    band = [a for a in alerts if lo <= (a['premium_value'] or 0) < hi
            and a['max_prof_3d_pct'] is not None and a['max_loss_3d_pct'] is not None]
    if not band:
        continue

    wins = sum(1 for a in band if (a['max_prof_3d_pct'] or 0) >= WIN_THRESHOLD)
    wr = wins / len(band) * 100
    avg_peak = sum(a['max_prof_3d_pct'] or 0 for a in band) / len(band)
    avg_trough = sum(a['max_loss_3d_pct'] or 0 for a in band) / len(band)
    ratio = abs(avg_peak / avg_trough) if avg_trough != 0 else 0

    print(f'{label:<14} {len(band):>6} {wr:>7.0f}% {avg_peak:>+11.1f}% {avg_trough:>+13.1f}% {ratio:>11.1f}x')
