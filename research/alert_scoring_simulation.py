"""
Alert Scoring Simulation - Evidence-Based Scoring Calibration

Loads historical flow_alerts, parses component scores from alert_reason,
and simulates how different scoring schemes would change alert outcomes.

Stage 1: Quantify the smart money double-count bug fix
Stage 2: Threshold shape (tiered vs flat)
Stage 3: Scaling function (log×2 vs log×3 vs sqrt)
"""

import json
import math
import re
from collections import defaultdict

# Load the exported alert data
with open('E:/options_scanner/research/alert_scoring_data.json') as f:
    raw = json.load(f)
    alerts = raw[0]

print(f"Loaded {len(alerts)} alerts\n")

# --- Market cap lookup (mirrors fm_analyzer.py) ---
MARKET_CAP_LOOKUP = {
    'AAPL': 'mega_cap', 'MSFT': 'mega_cap', 'NVDA': 'mega_cap', 'GOOGL': 'mega_cap',
    'GOOG': 'mega_cap', 'AMZN': 'mega_cap', 'META': 'mega_cap', 'TSLA': 'mega_cap',
    'BRK.B': 'mega_cap', 'TSM': 'mega_cap', 'LLY': 'mega_cap', 'JPM': 'mega_cap',
    'SPY': 'mega_cap', 'QQQ': 'mega_cap', 'IWM': 'mega_cap', 'VTI': 'mega_cap',
    'TLT': 'mega_cap', 'XLF': 'mega_cap', 'XLE': 'mega_cap', 'XLK': 'mega_cap',
    'XLI': 'mega_cap', 'XLV': 'mega_cap', 'XLP': 'mega_cap', 'XLU': 'mega_cap',
    'V': 'large_cap', 'JNJ': 'large_cap', 'WMT': 'large_cap', 'PG': 'large_cap',
    'UNH': 'large_cap', 'HD': 'large_cap', 'MA': 'large_cap', 'NFLX': 'large_cap',
    'DIS': 'large_cap', 'ADBE': 'large_cap', 'PYPL': 'large_cap', 'INTC': 'large_cap',
    'CMCSA': 'large_cap', 'CSCO': 'large_cap', 'PEP': 'large_cap', 'ABT': 'large_cap',
    'CRM': 'large_cap', 'ACN': 'large_cap', 'TMO': 'large_cap', 'COST': 'large_cap',
    'AVGO': 'large_cap', 'DHR': 'large_cap', 'NEE': 'large_cap', 'LIN': 'large_cap',
    'TXN': 'large_cap', 'HON': 'large_cap', 'QCOM': 'large_cap', 'UPS': 'large_cap',
    'LOW': 'large_cap', 'AMD': 'large_cap', 'IBM': 'large_cap', 'ORCL': 'large_cap',
    'CVX': 'large_cap', 'C': 'large_cap', 'MDT': 'large_cap', 'CAT': 'large_cap',
}

PREMIUM_THRESHOLDS_TIERED = {
    'mega_cap': 400_000,
    'large_cap': 300_000,
    'mid_cap': 200_000,
    'small_cap': 150_000,
}


def get_market_cap_category(symbol):
    """Simplified - we don't have volume_baseline here, so unknowns default to small_cap"""
    return MARKET_CAP_LOOKUP.get(symbol, 'small_cap')


def get_tiered_threshold(symbol):
    return PREMIUM_THRESHOLDS_TIERED[get_market_cap_category(symbol)]


def parse_smart_money(alert_reason):
    """Extract smart money score from alert_reason string"""
    match = re.search(r'smart=([\d.]+)', alert_reason or '')
    if match:
        return float(match.group(1))
    return 0.0


def calc_volume_surprise_score(volume_surprise):
    """Volume surprise -> points (0-4), unchanged across all scenarios"""
    if volume_surprise is None or volume_surprise <= 0:
        return 0.0
    if volume_surprise >= 25.0:
        score = min(4.0, 2.0 + math.log10(volume_surprise / 25.0) * 2.0)
    elif volume_surprise >= 10.0:
        score = min(3.0, 1.5 + (volume_surprise - 10.0) / 15.0 * 1.5)
    else:
        score = min(2.0, (volume_surprise - 3.0) / 2.0 + 1.0)
    return max(0.0, score)


def calc_premium_score_log(premium, threshold, multiplier=2.0):
    """Log-scale premium scoring: min(6.0, log10(premium/threshold) * multiplier)"""
    if not premium or premium < 1e-6 or not threshold or threshold < 1e-6:
        return 0.0
    try:
        ratio = premium / threshold
        if ratio <= 0:
            return 0.0
        return min(6.0, max(0.0, math.log10(ratio) * multiplier))
    except (ValueError, OverflowError):
        return 0.0


def calc_premium_score_sqrt(premium, threshold):
    """Sqrt-scale premium scoring: min(6.0, sqrt(premium/threshold) * scaling)

    Calibrated so that the same premium that gives 2.0 under log×2 gives ~2.0 here.
    log10(10) * 2 = 2.0 at 10x threshold.  sqrt(10) * scaling = 2.0 -> scaling = 0.6325
    """
    if not premium or premium < 1e-6 or not threshold or threshold < 1e-6:
        return 0.0
    ratio = premium / threshold
    if ratio <= 1:
        return 0.0
    # Scale so 10x threshold = ~2.0 points (matching log×2 at that point)
    return min(6.0, max(0.0, math.sqrt(ratio) * 0.6325))


def calc_premium_score_linear(premium, threshold):
    """Linear-scale premium scoring: min(6.0, (premium/threshold - 1) * scaling)

    Calibrated so 10x threshold = ~2.0 points.  (10-1) * scaling = 2.0 -> scaling = 0.222
    """
    if not premium or premium < 1e-6 or not threshold or threshold < 1e-6:
        return 0.0
    ratio = premium / threshold
    if ratio <= 1:
        return 0.0
    return min(6.0, max(0.0, (ratio - 1.0) * 0.222))


def score_alert(alert, threshold_fn, premium_score_fn, single_smart=True):
    """Calculate total score for an alert under a given scheme.

    Args:
        alert: Alert dict from database
        threshold_fn: function(symbol) -> premium threshold in dollars
        premium_score_fn: function(premium, threshold) -> premium points (0-6)
        single_smart: If True, count smart money once. If False, count twice (current bug).
    """
    symbol = alert['symbol']
    premium = alert['premium_value'] or 0
    vol_surprise = alert['volume_surprise_factor'] or 0
    smart = parse_smart_money(alert['alert_reason'])

    threshold = threshold_fn(symbol)

    prem_score = premium_score_fn(premium, threshold)
    vol_score = calc_volume_surprise_score(vol_surprise)

    if single_smart:
        total = prem_score + vol_score + smart
    else:
        # Current bug: smart counted twice
        total = prem_score + vol_score + smart + smart

    return min(10.0, total), prem_score, vol_score, smart


# ============================================================
# Define scenarios
# ============================================================

THRESHOLD_6 = 6.0

scenarios = {}

# --- STAGE 1: Bug fix impact ---
# A: Current production (double smart money, tiered thresholds, log×2)
scenarios['A_current'] = {
    'label': 'A: Current (double smart, tiered, log×2)',
    'threshold_fn': get_tiered_threshold,
    'premium_fn': lambda p, t: calc_premium_score_log(p, t, 2.0),
    'single_smart': False,
}
# B: Fix only (single smart money)
scenarios['B_fix_only'] = {
    'label': 'B: Bug fix only (single smart, tiered, log×2)',
    'threshold_fn': get_tiered_threshold,
    'premium_fn': lambda p, t: calc_premium_score_log(p, t, 2.0),
    'single_smart': True,
}

# --- STAGE 2: Threshold shape (all with bug fix, log×2) ---
for flat_val in [200_000, 250_000, 300_000, 400_000]:
    key = f'C_flat_{flat_val // 1000}K'
    scenarios[key] = {
        'label': f'C: Flat ${flat_val//1000}K threshold (log×2)',
        'threshold_fn': lambda s, fv=flat_val: fv,
        'premium_fn': lambda p, t: calc_premium_score_log(p, t, 2.0),
        'single_smart': True,
    }

# --- STAGE 3: Scaling function (using flat $250K as candidate + tiered for comparison) ---
scenarios['D_log3_tiered'] = {
    'label': 'D: log×3.0 (tiered thresholds)',
    'threshold_fn': get_tiered_threshold,
    'premium_fn': lambda p, t: calc_premium_score_log(p, t, 3.0),
    'single_smart': True,
}
scenarios['D_log3_flat250'] = {
    'label': 'D: log×3.0 (flat $250K)',
    'threshold_fn': lambda s: 250_000,
    'premium_fn': lambda p, t: calc_premium_score_log(p, t, 3.0),
    'single_smart': True,
}
scenarios['E_sqrt_tiered'] = {
    'label': 'E: sqrt (tiered thresholds)',
    'threshold_fn': get_tiered_threshold,
    'premium_fn': calc_premium_score_sqrt,
    'single_smart': True,
}
scenarios['E_sqrt_flat250'] = {
    'label': 'E: sqrt (flat $250K)',
    'threshold_fn': lambda s: 250_000,
    'premium_fn': calc_premium_score_sqrt,
    'single_smart': True,
}

# ============================================================
# Run simulations
# ============================================================

results = {}

for key, scenario in scenarios.items():
    scores = []
    above_threshold = 0
    high_conviction = 0
    prem_scores = []
    vol_scores_list = []

    for alert in alerts:
        total, prem_s, vol_s, smart_s = score_alert(
            alert,
            scenario['threshold_fn'],
            scenario['premium_fn'],
            scenario['single_smart']
        )
        scores.append({
            'symbol': alert['symbol'],
            'total': total,
            'prem_score': prem_s,
            'vol_score': vol_s,
            'smart_score': smart_s,
            'premium_value': alert['premium_value'],
            'vol_surprise': alert['volume_surprise_factor'],
            'original_score': alert['significance_score'],
            'timestamp': alert['alert_timestamp'],
        })
        prem_scores.append(prem_s)
        vol_scores_list.append(vol_s)
        if total >= THRESHOLD_6:
            above_threshold += 1
        if total >= 8.0:
            high_conviction += 1

    results[key] = {
        'label': scenario['label'],
        'total_alerts': len(scores),
        'above_6': above_threshold,
        'above_8': high_conviction,
        'below_6': len(scores) - above_threshold,
        'scores': scores,
        'avg_prem_score': sum(prem_scores) / len(prem_scores),
        'avg_vol_score': sum(vol_scores_list) / len(vol_scores_list),
    }


# ============================================================
# Report
# ============================================================

print("=" * 90)
print("STAGE 1: SMART MONEY DOUBLE-COUNT BUG FIX")
print("=" * 90)
print(f"{'Scenario':<50} {'>=6.0':>7} {'>=8.0':>7} {'<6.0':>7} {'Avg Prem':>9} {'Avg Vol':>9}")
print("-" * 90)
for key in ['A_current', 'B_fix_only']:
    r = results[key]
    print(f"{r['label']:<50} {r['above_6']:>7} {r['above_8']:>7} {r['below_6']:>7} {r['avg_prem_score']:>9.2f} {r['avg_vol_score']:>9.2f}")

# Show which alerts would be lost
a_scores = {i: results['A_current']['scores'][i]['total'] for i in range(len(alerts))}
b_scores = {i: results['B_fix_only']['scores'][i]['total'] for i in range(len(alerts))}

lost = []
for i in range(len(alerts)):
    if a_scores[i] >= 6.0 and b_scores[i] < 6.0:
        s = results['B_fix_only']['scores'][i]
        lost.append(s)

print(f"\nAlerts that would DROP below 6.0 after bug fix: {len(lost)}")
if lost:
    print(f"  {'Symbol':<8} {'Old':>6} {'New':>6} {'Premium':>12} {'VolSurp':>8} {'Smart':>6} {'Timestamp':<20}")
    for s in sorted(lost, key=lambda x: x['total'], reverse=True)[:20]:
        print(f"  {s['symbol']:<8} {s['original_score']:>6.1f} {s['total']:>6.2f} ${s['premium_value']:>10,.0f} {s['vol_surprise']:>7.1f}x {s['smart_score']:>5.1f} {s['timestamp'][:16]}")
    if len(lost) > 20:
        print(f"  ... and {len(lost) - 20} more")

print()
print("=" * 90)
print("STAGE 2: THRESHOLD SHAPE (all with bug fix, log×2)")
print("=" * 90)
print(f"{'Scenario':<50} {'>=6.0':>7} {'>=8.0':>7} {'<6.0':>7} {'Avg Prem':>9}")
print("-" * 90)
# Include B (tiered) for comparison
for key in ['B_fix_only', 'C_flat_200K', 'C_flat_250K', 'C_flat_300K', 'C_flat_400K']:
    r = results[key]
    print(f"{r['label']:<50} {r['above_6']:>7} {r['above_8']:>7} {r['below_6']:>7} {r['avg_prem_score']:>9.2f}")

# Show what changes between tiered and flat $250K
print(f"\nComparing Tiered vs Flat $250K:")
tiered = results['B_fix_only']['scores']
flat250 = results['C_flat_250K']['scores']
gained = []
lost_flat = []
for i in range(len(alerts)):
    t_score = tiered[i]['total']
    f_score = flat250[i]['total']
    if t_score < 6.0 and f_score >= 6.0:
        gained.append((tiered[i], f_score))
    elif t_score >= 6.0 and f_score < 6.0:
        lost_flat.append((tiered[i], f_score))

print(f"  Gained (new alerts with flat): {len(gained)}")
for s, new_score in sorted(gained, key=lambda x: x[1], reverse=True)[:10]:
    cat = get_market_cap_category(s['symbol'])
    print(f"    {s['symbol']:<8} {cat:<10} tiered={s['total']:>5.2f} flat250={new_score:>5.2f} prem=${s['premium_value']:>10,.0f}")

print(f"  Lost (dropped alerts with flat): {len(lost_flat)}")
for s, new_score in sorted(lost_flat, key=lambda x: x[1], reverse=True)[:10]:
    cat = get_market_cap_category(s['symbol'])
    print(f"    {s['symbol']:<8} {cat:<10} tiered={s['total']:>5.2f} flat250={new_score:>5.2f} prem=${s['premium_value']:>10,.0f}")


print()
print("=" * 90)
print("STAGE 3: SCALING FUNCTION")
print("=" * 90)
print(f"{'Scenario':<50} {'>=6.0':>7} {'>=8.0':>7} {'<6.0':>7} {'Avg Prem':>9}")
print("-" * 90)
for key in ['B_fix_only', 'D_log3_tiered', 'D_log3_flat250', 'E_sqrt_tiered', 'E_sqrt_flat250']:
    r = results[key]
    print(f"{r['label']:<50} {r['above_6']:>7} {r['above_8']:>7} {r['below_6']:>7} {r['avg_prem_score']:>9.2f}")

# Premium score distribution comparison
print()
print("=" * 90)
print("PREMIUM SCORE DISTRIBUTION (how many points does premium typically contribute?)")
print("=" * 90)
for key in ['A_current', 'B_fix_only', 'D_log3_tiered', 'D_log3_flat250', 'E_sqrt_tiered']:
    scores = results[key]['scores']
    prem_vals = [s['prem_score'] for s in scores]
    buckets = defaultdict(int)
    for p in prem_vals:
        if p < 1.0:
            buckets['0-1'] += 1
        elif p < 2.0:
            buckets['1-2'] += 1
        elif p < 3.0:
            buckets['2-3'] += 1
        elif p < 4.0:
            buckets['3-4'] += 1
        elif p < 5.0:
            buckets['4-5'] += 1
        else:
            buckets['5-6'] += 1

    label = results[key]['label'][:45]
    dist = "  ".join(f"{k}:{v}" for k, v in sorted(buckets.items()))
    print(f"  {label:<47} {dist}")

# Show score composition for top and bottom quintile
print()
print("=" * 90)
print("SCORE COMPOSITION: What drives high vs low scores? (Bug-fixed baseline)")
print("=" * 90)
fixed = sorted(results['B_fix_only']['scores'], key=lambda x: x['total'], reverse=True)
top_20pct = fixed[:len(fixed)//5]
bottom_20pct = fixed[-len(fixed)//5:]

avg_prem_top = sum(s['prem_score'] for s in top_20pct) / len(top_20pct)
avg_vol_top = sum(s['vol_score'] for s in top_20pct) / len(top_20pct)
avg_smart_top = sum(s['smart_score'] for s in top_20pct) / len(top_20pct)

avg_prem_bot = sum(s['prem_score'] for s in bottom_20pct) / len(bottom_20pct)
avg_vol_bot = sum(s['vol_score'] for s in bottom_20pct) / len(bottom_20pct)
avg_smart_bot = sum(s['smart_score'] for s in bottom_20pct) / len(bottom_20pct)

print(f"  {'Quintile':<20} {'Avg Premium':>12} {'Avg Volume':>12} {'Avg Smart':>10} {'Avg Total':>10}")
print(f"  {'Top 20%':<20} {avg_prem_top:>12.2f} {avg_vol_top:>12.2f} {avg_smart_top:>10.2f} {avg_prem_top+avg_vol_top+avg_smart_top:>10.2f}")
print(f"  {'Bottom 20%':<20} {avg_prem_bot:>12.2f} {avg_vol_bot:>12.2f} {avg_smart_bot:>10.2f} {avg_prem_bot+avg_vol_bot+avg_smart_bot:>10.2f}")
print(f"  {'Difference':<20} {avg_prem_top-avg_prem_bot:>+12.2f} {avg_vol_top-avg_vol_bot:>+12.2f} {avg_smart_top-avg_smart_bot:>+10.2f}")
