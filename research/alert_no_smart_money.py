"""
Simulate removing smart money score entirely.

Three scenarios:
  A: Current production (double smart, threshold 6.0)
  B: No smart money, threshold 6.0
  C: No smart money, find the threshold that preserves "good" alert volume

What threshold with no-smart-money produces the same quality distribution
as current production?
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

WIN_THRESHOLD = 18.0


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


# Calculate all three scores for each alert
for a in alerts:
    smart = parse_smart(a['alert_reason'])
    prem = prem_score_log2(a['premium_value'] or 0)
    vol = vol_surprise_score(a['volume_surprise_factor'] or 0)

    # A: Current production (double smart)
    a['score_current'] = min(10.0, prem + vol + smart + smart)
    # B/C: No smart money (just premium + volume surprise)
    a['score_no_smart'] = min(10.0, prem + vol)

    a['prem_score'] = prem
    a['vol_score'] = vol
    a['smart'] = smart

alerts_with_prof = [a for a in alerts if a['max_prof_7d_pct'] is not None]

print(f'Total alerts: {len(alerts)}')
print(f'With 7d profit data: {len(alerts_with_prof)}')
print()

# ===========================================
# What threshold with no-smart gives similar alert quality?
# ===========================================
print('=' * 100)
print('THRESHOLD SWEEP: No smart money, varying alert threshold')
print(f'(Win = option peaks >= {WIN_THRESHOLD}% within window)')
print('=' * 100)
print()

print(f'{"Threshold":<10} {"Total":>6} {"w/Data":>6} | {"3d Win%":>8} {"3d Avg":>8} {"3d Loss":>8} | {"7d Win%":>8} {"7d Avg":>8} {"7d Loss":>8} | {"Avg Prem":>12} {"Avg VolS":>9}')
print('-' * 115)

# Also show current production for reference
current_pass = [a for a in alerts if a['score_current'] >= 6.0]
current_with_prof = [a for a in current_pass if a['max_prof_7d_pct'] is not None]
if current_with_prof:
    w3 = sum(1 for a in current_with_prof if (a['max_prof_3d_pct'] or 0) >= WIN_THRESHOLD) / len(current_with_prof) * 100 if current_with_prof else 0
    a3 = sum(a['max_prof_3d_pct'] or 0 for a in current_with_prof) / len(current_with_prof)
    l3_vals = [a['max_loss_3d_pct'] for a in current_with_prof if a['max_loss_3d_pct'] is not None]
    l3 = sum(l3_vals) / len(l3_vals) if l3_vals else 0
    w7 = sum(1 for a in current_with_prof if (a['max_prof_7d_pct'] or 0) >= WIN_THRESHOLD) / len(current_with_prof) * 100
    a7 = sum(a['max_prof_7d_pct'] or 0 for a in current_with_prof) / len(current_with_prof)
    l7_vals = [a['max_loss_7d_pct'] for a in current_with_prof if a['max_loss_7d_pct'] is not None]
    l7 = sum(l7_vals) / len(l7_vals) if l7_vals else 0
    ap = sum(a['premium_value'] or 0 for a in current_pass) / len(current_pass)
    av = sum(a['volume_surprise_factor'] or 0 for a in current_pass) / len(current_pass)
    print(f'{"CURRENT":>10} {len(current_pass):>6} {len(current_with_prof):>6} | {w3:>7.0f}% {a3:>+7.1f}% {l3:>+7.1f}% | {w7:>7.0f}% {a7:>+7.1f}% {l7:>+7.1f}% | {ap:>12,.0f} {av:>8.1f}x')
    print('-' * 115)

for threshold in [3.0, 3.5, 4.0, 4.2, 4.4, 4.5, 4.6, 4.8, 5.0, 5.5, 6.0, 6.5, 7.0]:
    passing = [a for a in alerts if a['score_no_smart'] >= threshold]
    with_prof = [a for a in passing if a['max_prof_7d_pct'] is not None]

    if not with_prof:
        print(f'{threshold:>10.1f} {len(passing):>6} {len(with_prof):>6}')
        continue

    # 3d metrics
    w3_data = [a for a in with_prof if a['max_prof_3d_pct'] is not None]
    if w3_data:
        w3 = sum(1 for a in w3_data if (a['max_prof_3d_pct'] or 0) >= WIN_THRESHOLD) / len(w3_data) * 100
        a3 = sum(a['max_prof_3d_pct'] or 0 for a in w3_data) / len(w3_data)
        l3_vals = [a['max_loss_3d_pct'] for a in w3_data if a['max_loss_3d_pct'] is not None]
        l3 = sum(l3_vals) / len(l3_vals) if l3_vals else 0
    else:
        w3, a3, l3 = 0, 0, 0

    # 7d metrics
    w7 = sum(1 for a in with_prof if (a['max_prof_7d_pct'] or 0) >= WIN_THRESHOLD) / len(with_prof) * 100
    a7 = sum(a['max_prof_7d_pct'] or 0 for a in with_prof) / len(with_prof)
    l7_vals = [a['max_loss_7d_pct'] for a in with_prof if a['max_loss_7d_pct'] is not None]
    l7 = sum(l7_vals) / len(l7_vals) if l7_vals else 0

    ap = sum(a['premium_value'] or 0 for a in passing) / len(passing)
    av = sum(a['volume_surprise_factor'] or 0 for a in passing) / len(passing)

    print(f'{threshold:>10.1f} {len(passing):>6} {len(with_prof):>6} | {w3:>7.0f}% {a3:>+7.1f}% {l3:>+7.1f}% | {w7:>7.0f}% {a7:>+7.1f}% {l7:>+7.1f}% | {ap:>12,.0f} {av:>8.1f}x')


# ===========================================
# Show specific alerts near the boundary
# ===========================================
print()
print('=' * 100)
print('BOUNDARY ALERTS: Score 4.0-5.0 (no smart money)')
print('These are the alerts that would survive at a ~4.5 threshold but not at 6.0')
print('=' * 100)
print()

boundary = [a for a in alerts if 4.0 <= a['score_no_smart'] < 5.0 and a['max_prof_7d_pct'] is not None]
boundary.sort(key=lambda x: x['score_no_smart'], reverse=True)

print(f'{"Symbol":<8} {"NoSmart":>8} {"Current":>8} {"Prem":>8} {"Vol":>6} {"Premium$":>12} {"VolSurp":>8} {"3dProf":>8} {"7dProf":>8} {"3dLoss":>8}')
print('-' * 100)

for a in boundary[:30]:
    p3 = a['max_prof_3d_pct'] or 0
    p7 = a['max_prof_7d_pct'] or 0
    l3 = a['max_loss_3d_pct'] or 0
    print(f'{a["symbol"]:<8} {a["score_no_smart"]:>8.2f} {a["score_current"]:>8.2f} {a["prem_score"]:>8.2f} {a["vol_score"]:>6.2f} ${a["premium_value"]:>10,.0f} {a["volume_surprise_factor"]:>7.1f}x {p3:>+7.1f}% {p7:>+7.1f}% {l3:>+7.1f}%')


# ===========================================
# What does a 4.5 threshold MISS that current catches?
# ===========================================
print()
print('=' * 100)
print('COMPARISON: Alerts in CURRENT (>=6.0) that would be MISSED at no-smart 4.5')
print('=' * 100)
print()

current_set = set(i for i, a in enumerate(alerts) if a['score_current'] >= 6.0)
new_set = set(i for i, a in enumerate(alerts) if a['score_no_smart'] >= 4.5)

only_current = current_set - new_set  # In current but NOT in new
only_new = new_set - current_set  # In new but NOT in current

print(f'Current production alerts: {len(current_set)}')
print(f'No-smart at 4.5 alerts:   {len(new_set)}')
print(f'In both:                  {len(current_set & new_set)}')
print(f'Only in current (would lose): {len(only_current)}')
print(f'Only in new (would gain):     {len(only_new)}')

if only_current:
    lost = [alerts[i] for i in only_current if alerts[i]['max_prof_7d_pct'] is not None]
    lost.sort(key=lambda x: x['score_current'], reverse=True)
    print(f'\nWould LOSE ({len(lost)} with profit data):')
    print(f'{"Symbol":<8} {"Current":>8} {"NoSmart":>8} {"Prem$":>12} {"VolSurp":>8} {"PremPts":>8} {"VolPts":>7} {"Smart":>6} {"7dProf":>8}')
    for a in lost[:15]:
        p7 = a['max_prof_7d_pct'] or 0
        print(f'{a["symbol"]:<8} {a["score_current"]:>8.1f} {a["score_no_smart"]:>8.2f} ${a["premium_value"]:>10,.0f} {a["volume_surprise_factor"]:>7.1f}x {a["prem_score"]:>8.2f} {a["vol_score"]:>6.2f} {a["smart"]:>6.1f} {p7:>+7.1f}%')

if only_new:
    gained = [alerts[i] for i in only_new if alerts[i]['max_prof_7d_pct'] is not None]
    gained.sort(key=lambda x: x['score_no_smart'], reverse=True)
    print(f'\nWould GAIN ({len(gained)} with profit data):')
    print(f'{"Symbol":<8} {"Current":>8} {"NoSmart":>8} {"Prem$":>12} {"VolSurp":>8} {"PremPts":>8} {"VolPts":>7} {"7dProf":>8}')
    for a in gained[:15]:
        p7 = a['max_prof_7d_pct'] or 0
        print(f'{a["symbol"]:<8} {a["score_current"]:>8.1f} {a["score_no_smart"]:>8.2f} ${a["premium_value"]:>10,.0f} {a["volume_surprise_factor"]:>7.1f}x {a["prem_score"]:>8.2f} {a["vol_score"]:>6.2f} {p7:>+7.1f}%')
