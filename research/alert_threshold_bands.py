"""
Threshold band analysis - quality per half-point band (no smart money score).

Question: where does alert quality actually drop off?
If we set threshold at 4.0 instead of 4.5, what are those extra 900 alerts like?
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
           max_loss_1d_pct, max_loss_3d_pct, max_loss_7d_pct
    FROM flow_alerts
''')
alerts = [dict(r) for r in cursor.fetchall()]
conn.close()

WIN = 18.0


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


for a in alerts:
    prem = prem_score_log2(a['premium_value'] or 0)
    vol = vol_surprise_score(a['volume_surprise_factor'] or 0)
    a['score_no_smart'] = min(10.0, prem + vol)
    a['prem_score'] = prem
    a['vol_score'] = vol


# Per-band quality
print('=' * 115)
print(f'QUALITY BY HALF-POINT BAND (no smart money)')
print(f'Each band shows the INCREMENTAL alerts you get by lowering the threshold to include that band')
print(f'Win = option peaks >= {WIN}% at any point in window')
print('=' * 115)
print()

header = (f'{"Band":<10} {"Count":>6} {"w/Data":>6} | '
          f'{"3d Win%":>7} {"3d Avg":>8} {"3d Loss":>8} | '
          f'{"7d Win%":>7} {"7d Avg":>8} {"7d Loss":>8} | '
          f'{"Avg Prem$":>12} {"Avg VolS":>9} | '
          f'{"Per Day":>7}')
print(header)
print('-' * 115)

# Estimate trading days in our dataset
from datetime import datetime
timestamps = [a['alert_timestamp'][:10] for a in alerts if a['alert_timestamp']]
unique_days = len(set(timestamps))

bands = [
    (6.5, 7.0), (6.0, 6.5), (5.5, 6.0), (5.0, 5.5),
    (4.5, 5.0), (4.0, 4.5), (3.5, 4.0), (3.0, 3.5),
]

for lo, hi in bands:
    band = [a for a in alerts if lo <= a['score_no_smart'] < hi]
    with_data = [a for a in band if a['max_prof_7d_pct'] is not None]

    if not with_data:
        per_day = len(band) / unique_days if unique_days else 0
        print(f'{lo:.1f}-{hi:.1f}  {len(band):>6} {len(with_data):>6} | {"":>7} {"":>8} {"":>8} | {"":>7} {"":>8} {"":>8} | {"":>12} {"":>9} | {per_day:>6.1f}')
        continue

    # 3d
    d3 = [a for a in with_data if a['max_prof_3d_pct'] is not None]
    if d3:
        w3 = sum(1 for a in d3 if (a['max_prof_3d_pct'] or 0) >= WIN) / len(d3) * 100
        a3 = sum(a['max_prof_3d_pct'] or 0 for a in d3) / len(d3)
        l3v = [a['max_loss_3d_pct'] for a in d3 if a['max_loss_3d_pct'] is not None]
        l3 = sum(l3v) / len(l3v) if l3v else 0
    else:
        w3, a3, l3 = 0, 0, 0

    # 7d
    w7 = sum(1 for a in with_data if (a['max_prof_7d_pct'] or 0) >= WIN) / len(with_data) * 100
    a7 = sum(a['max_prof_7d_pct'] or 0 for a in with_data) / len(with_data)
    l7v = [a['max_loss_7d_pct'] for a in with_data if a['max_loss_7d_pct'] is not None]
    l7 = sum(l7v) / len(l7v) if l7v else 0

    ap = sum(a['premium_value'] or 0 for a in band) / len(band)
    av = sum(a['volume_surprise_factor'] or 0 for a in band) / len(band)
    per_day = len(band) / unique_days if unique_days else 0

    print(f'{lo:.1f}-{hi:.1f}  {len(band):>6} {len(with_data):>6} | '
          f'{w3:>6.0f}% {a3:>+7.1f}% {l3:>+7.1f}% | '
          f'{w7:>6.0f}% {a7:>+7.1f}% {l7:>+7.1f}% | '
          f'{ap:>12,.0f} {av:>8.1f}x | '
          f'{per_day:>6.1f}')


# Cumulative view: "if I set threshold HERE, what's my total?"
print()
print('=' * 115)
print('CUMULATIVE VIEW: "If I set the threshold at X, here is my total alert profile"')
print('=' * 115)
print()

header2 = (f'{"Threshold":<10} {"Total":>6} {"Per Day":>7} | '
           f'{"3d Win%":>7} {"3d Avg":>8} {"3d Loss":>8} | '
           f'{"7d Win%":>7} {"7d Avg":>8} {"7d Loss":>8} | '
           f'{"Avg Prem$":>12} {"Med Prem$":>12}')
print(header2)
print('-' * 115)

for thresh in [6.0, 5.5, 5.0, 4.5, 4.0, 3.5, 3.0]:
    passing = [a for a in alerts if a['score_no_smart'] >= thresh]
    with_data = [a for a in passing if a['max_prof_7d_pct'] is not None]
    per_day = len(passing) / unique_days if unique_days else 0

    if not with_data:
        continue

    d3 = [a for a in with_data if a['max_prof_3d_pct'] is not None]
    if d3:
        w3 = sum(1 for a in d3 if (a['max_prof_3d_pct'] or 0) >= WIN) / len(d3) * 100
        a3 = sum(a['max_prof_3d_pct'] or 0 for a in d3) / len(d3)
        l3v = [a['max_loss_3d_pct'] for a in d3 if a['max_loss_3d_pct'] is not None]
        l3 = sum(l3v) / len(l3v) if l3v else 0
    else:
        w3, a3, l3 = 0, 0, 0

    w7 = sum(1 for a in with_data if (a['max_prof_7d_pct'] or 0) >= WIN) / len(with_data) * 100
    a7 = sum(a['max_prof_7d_pct'] or 0 for a in with_data) / len(with_data)
    l7v = [a['max_loss_7d_pct'] for a in with_data if a['max_loss_7d_pct'] is not None]
    l7 = sum(l7v) / len(l7v) if l7v else 0

    ap = sum(a['premium_value'] or 0 for a in passing) / len(passing)
    prems_sorted = sorted(a['premium_value'] or 0 for a in passing)
    med_prem = prems_sorted[len(prems_sorted) // 2]

    print(f'{thresh:<10.1f} {len(passing):>6} {per_day:>6.1f} | '
          f'{w3:>6.0f}% {a3:>+7.1f}% {l3:>+7.1f}% | '
          f'{w7:>6.0f}% {a7:>+7.1f}% {l7:>+7.1f}% | '
          f'{ap:>12,.0f} {med_prem:>12,.0f}')


# Show what the 3.5-4.0 band looks like — the marginal alerts
print()
print('=' * 115)
print('SAMPLE ALERTS IN 3.5-4.0 BAND (the marginal ones at a 3.5 threshold)')
print('=' * 115)
print()

marginal = [a for a in alerts if 3.5 <= a['score_no_smart'] < 4.0 and a['max_prof_7d_pct'] is not None]
marginal.sort(key=lambda x: x['score_no_smart'], reverse=True)

print(f'{"Symbol":<8} {"Score":>6} {"PremPts":>8} {"VolPts":>7} {"Premium$":>12} {"VolSurp":>8} {"3dProf":>8} {"7dProf":>8} {"3dLoss":>8}')
print('-' * 85)

for a in marginal[:25]:
    p3 = a['max_prof_3d_pct'] or 0
    p7 = a['max_prof_7d_pct'] or 0
    l3 = a['max_loss_3d_pct'] or 0
    print(f'{a["symbol"]:<8} {a["score_no_smart"]:>6.2f} {a["prem_score"]:>8.2f} {a["vol_score"]:>6.2f} ${a["premium_value"]:>10,.0f} {a["volume_surprise_factor"]:>7.1f}x {p3:>+7.1f}% {p7:>+7.1f}% {l3:>+7.1f}%')

# And 4.0-4.5
print()
print('=' * 115)
print('SAMPLE ALERTS IN 4.0-4.5 BAND')
print('=' * 115)
print()

mid = [a for a in alerts if 4.0 <= a['score_no_smart'] < 4.5 and a['max_prof_7d_pct'] is not None]
mid.sort(key=lambda x: x['score_no_smart'], reverse=True)

print(f'{"Symbol":<8} {"Score":>6} {"PremPts":>8} {"VolPts":>7} {"Premium$":>12} {"VolSurp":>8} {"3dProf":>8} {"7dProf":>8} {"3dLoss":>8}')
print('-' * 85)

for a in mid[:25]:
    p3 = a['max_prof_3d_pct'] or 0
    p7 = a['max_prof_7d_pct'] or 0
    l3 = a['max_loss_3d_pct'] or 0
    print(f'{a["symbol"]:<8} {a["score_no_smart"]:>6.2f} {a["prem_score"]:>8.2f} {a["vol_score"]:>6.2f} ${a["premium_value"]:>10,.0f} {a["volume_surprise_factor"]:>7.1f}x {p3:>+7.1f}% {p7:>+7.1f}% {l3:>+7.1f}%')
