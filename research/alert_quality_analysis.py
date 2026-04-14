"""
Alert Quality Analysis - Survivors vs Dropouts after bug fix

Compares profitability of alerts that survive the smart money double-count
fix vs those that would drop below 6.0 threshold.
"""

import sqlite3
import re
import math

conn = sqlite3.connect('data/datalake_query.db')
conn.row_factory = sqlite3.Row

cursor = conn.execute('''
    SELECT symbol, significance_score, premium_value, volume_surprise_factor,
           alert_reason, delta, volume, alert_timestamp, dte,
           max_prof_1d_pct, max_prof_3d_pct, max_prof_7d_pct, max_prof_14d_pct, max_prof_30d_pct,
           max_loss_1d_pct, max_loss_3d_pct, max_loss_7d_pct, max_loss_14d_pct, max_loss_30d_pct
    FROM flow_alerts
''')
alerts = [dict(r) for r in cursor.fetchall()]
conn.close()


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


# Recalculate with single smart money (bug-fixed) using effective $150K threshold
survivors = []
dropouts = []

for a in alerts:
    smart = parse_smart(a['alert_reason'])
    prem = prem_score_log2(a['premium_value'] or 0)
    vol = vol_surprise_score(a['volume_surprise_factor'] or 0)

    fixed_score = min(10.0, prem + vol + smart)  # single smart

    a['fixed_score'] = fixed_score
    a['prem_score'] = prem
    a['vol_score'] = vol
    a['smart'] = smart

    if fixed_score >= 6.0:
        survivors.append(a)
    else:
        dropouts.append(a)

surv_with_data = [a for a in survivors if a['max_prof_7d_pct'] is not None]
drop_with_data = [a for a in dropouts if a['max_prof_7d_pct'] is not None]

print(f'Total alerts: {len(alerts)}')
print(f'Survivors (score >= 6.0 after fix): {len(survivors)} ({len(surv_with_data)} with profit data)')
print(f'Dropouts  (score <  6.0 after fix): {len(dropouts)} ({len(drop_with_data)} with profit data)')
print()


def avg(group, field):
    vals = [a[field] for a in group if a[field] is not None]
    return sum(vals) / len(vals) if vals else 0


def median_val(group, field):
    vals = sorted([a[field] for a in group if a[field] is not None])
    if not vals:
        return 0
    return vals[len(vals) // 2]


def pct_positive(group, field):
    vals = [a[field] for a in group if a[field] is not None]
    if not vals:
        return 0
    return sum(1 for v in vals if v > 0) / len(vals) * 100


def print_stats(group, label):
    if not group:
        print(f'{label}: No data')
        return

    print(f'=== {label} ({len(group)} alerts with profit data) ===')
    print(f'  Avg premium:       ${avg(group, "premium_value"):>12,.0f}')
    print(f'  Avg vol surprise:     {avg(group, "volume_surprise_factor"):>8.1f}x')
    print(f'  Avg fixed score:      {avg(group, "fixed_score"):>8.2f}')
    print()

    header = f'  {"Window":<8} {"Avg Profit":>11} {"Median Prof":>12} {"% Positive":>11} {"Avg Loss":>11}  {"n":>5}'
    print(header)
    print(f'  {"-"*60}')

    for window in ['1d', '3d', '7d', '14d', '30d']:
        prof_field = f'max_prof_{window}_pct'
        loss_field = f'max_loss_{window}_pct'
        ap = avg(group, prof_field)
        mp = median_val(group, prof_field)
        pp = pct_positive(group, prof_field)
        al = avg(group, loss_field)
        n = sum(1 for a in group if a[prof_field] is not None)
        print(f'  {window:<8} {ap:>+10.1f}% {mp:>+11.1f}% {pp:>10.0f}% {al:>+10.1f}%  {n:>5}')
    print()


print_stats(surv_with_data, 'SURVIVORS (would keep)')
print_stats(drop_with_data, 'DROPOUTS (would lose)')


# Dropout quality by score band
print('=== DROPOUT QUALITY BY SCORE BAND ===')
header = f'{"Score Band":<12} {"Count":>6} {"w/Data":>6} {"Avg Prem":>12} {"Avg 7d Prof":>12} {"% Prof>0":>10} {"Avg 7d Loss":>12}'
print(header)
print('-' * 80)

for lo, hi, label in [(5.5, 6.0, '5.5-6.0'), (5.0, 5.5, '5.0-5.5'), (4.5, 5.0, '4.5-5.0'), (4.0, 4.5, '4.0-4.5'), (0, 4.0, '<4.0')]:
    band = [a for a in dropouts if lo <= a['fixed_score'] < hi]
    band_data = [a for a in band if a['max_prof_7d_pct'] is not None]
    if band_data:
        ap = avg(band_data, 'premium_value')
        a7 = avg(band_data, 'max_prof_7d_pct')
        pp = pct_positive(band_data, 'max_prof_7d_pct')
        al = avg(band_data, 'max_loss_7d_pct')
        print(f'{label:<12} {len(band):>6} {len(band_data):>6} {ap:>12,.0f} {a7:>+11.1f}% {pp:>9.0f}% {al:>+11.1f}%')
    else:
        print(f'{label:<12} {len(band):>6} {len(band_data):>6}')

# Survivor quality by score band
print()
print('=== SURVIVOR QUALITY BY SCORE BAND ===')
print(header)
print('-' * 80)

for lo, hi, label in [(6.0, 6.5, '6.0-6.5'), (6.5, 7.0, '6.5-7.0'), (7.0, 8.0, '7.0-8.0'), (8.0, 10.1, '8.0+')]:
    band = [a for a in survivors if lo <= a['fixed_score'] < hi]
    band_data = [a for a in band if a['max_prof_7d_pct'] is not None]
    if band_data:
        ap = avg(band_data, 'premium_value')
        a7 = avg(band_data, 'max_prof_7d_pct')
        pp = pct_positive(band_data, 'max_prof_7d_pct')
        al = avg(band_data, 'max_loss_7d_pct')
        print(f'{label:<12} {len(band):>6} {len(band_data):>6} {ap:>12,.0f} {a7:>+11.1f}% {pp:>9.0f}% {al:>+11.1f}%')
    else:
        print(f'{label:<12} {len(band):>6} {len(band_data):>6}')

# The big question: do higher scores predict better outcomes?
print()
print('=== SCORE vs OUTCOME CORRELATION ===')
print('(Using all alerts with 7d profit data, binned by CURRENT production score)')
print()
print(f'{"Score Band":<12} {"Count":>6} {"Avg Prem":>12} {"Avg 7d Prof":>12} {"% Prof>0":>10} {"Med 7d Prof":>12}')
print('-' * 70)

all_with_data = [a for a in alerts if a['max_prof_7d_pct'] is not None]
for lo, hi, label in [(4.0, 5.0, '4.0-5.0'), (5.0, 5.5, '5.0-5.5'), (5.5, 6.0, '5.5-6.0'),
                       (6.0, 6.5, '6.0-6.5'), (6.5, 7.0, '6.5-7.0'), (7.0, 7.5, '7.0-7.5'),
                       (7.5, 8.0, '7.5-8.0'), (8.0, 9.0, '8.0-9.0'), (9.0, 10.1, '9.0+')]:
    band = [a for a in all_with_data if lo <= a['fixed_score'] < hi]
    if band:
        ap = avg(band, 'premium_value')
        a7 = avg(band, 'max_prof_7d_pct')
        pp = pct_positive(band, 'max_prof_7d_pct')
        mp = median_val(band, 'max_prof_7d_pct')
        print(f'{label:<12} {len(band):>6} {ap:>12,.0f} {a7:>+11.1f}% {pp:>9.0f}% {mp:>+11.1f}%')
