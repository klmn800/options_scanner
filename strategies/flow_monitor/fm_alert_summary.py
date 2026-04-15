#!/usr/bin/env python3
"""
Flow Monitor Alert Summary (fm_alert_summary.py)
-------------------------------------------------
End-of-cycle dashboard showing today's flow alert landscape.

Two display elements in one status box:
1. Cycle Timeline — chronological strip, one line per alert-producing cycle
2. Symbol Roll-Up — accumulated story per symbol across all cycles

Stateless: rebuilds from flow_alerts table each call. Restart-proof.

Created: 2026-03-08
Author: Ben (with assistance from Claude)
"""

import logging
from collections import OrderedDict, Counter

from tools.log_utils import create_status_box


class FMAlertSummary:
    """Renders a running daily alert summary box after each FM cycle.

    Pure display component — no state, no side effects.
    Queries flow_alerts for today, groups by cycle and symbol, renders via create_status_box().
    """

    def display(self, storage, trade_date):
        """Query today's alerts and render the flow activity dashboard.

        Args:
            storage: FlowMonitorStorage instance (has query_with_params)
            trade_date: str 'YYYY-MM-DD'
        """
        rows = self._query_alerts(storage, trade_date)
        if not rows:
            return  # No alerts today — skip the box entirely

        cycles = self._build_cycle_map(rows)
        symbols = self._build_symbol_rollup(rows, cycles)
        lines = self._render(cycles, symbols, len(rows))

        create_status_box(
            "📊 TODAY'S FLOW ACTIVITY — {} cycles, {} alerts, {} symbols".format(
                len(cycles), len(rows), len(symbols)),
            lines
        )

    def _query_alerts(self, storage, trade_date):
        """Fetch today's alerts ordered by cycle then time."""
        try:
            return storage.query_with_params(
                """SELECT symbol, option_type, moneyness, significance_score,
                          premium_value, dte, expiration_date, iv, underlying_price,
                          alert_timestamp, scan_timestamp, iv_percentile_30d
                   FROM flow_alerts
                   WHERE trade_date = ?
                   ORDER BY scan_timestamp, alert_timestamp""",
                (trade_date,)
            )
        except Exception as e:
            logging.warning("Alert summary query failed: {}".format(e))
            return []

    def _build_cycle_map(self, rows):
        """Group alerts by scan_timestamp, assign sequential cycle numbers.

        Returns:
            OrderedDict: {cycle_num: {'time': 'HH:MM', 'alerts': [row, ...]}}
        """
        # Group by scan_timestamp preserving order
        by_scan = OrderedDict()
        for row in rows:
            ts = row['scan_timestamp']
            if ts not in by_scan:
                by_scan[ts] = []
            by_scan[ts].append(row)

        # Assign sequential cycle numbers
        cycles = OrderedDict()
        for i, (scan_ts, alerts) in enumerate(by_scan.items(), 1):
            # Parse time from first alert's alert_timestamp (format: 'YYYY-MM-DD HH:MM:SS')
            time_str = ''
            try:
                alert_ts = alerts[0]['alert_timestamp']
                time_str = alert_ts[11:16]  # Extract HH:MM
            except (IndexError, TypeError):
                time_str = '??:??'

            cycles[i] = {
                'time': time_str,
                'alerts': alerts,
            }

        return cycles

    def _build_symbol_rollup(self, rows, cycles):
        """Aggregate alert data per symbol across all cycles.

        Returns:
            list of dicts, sorted by count desc then peak_score desc.
        """
        # Build reverse lookup: scan_timestamp -> cycle number
        scan_to_cycle = {}
        for cycle_num, data in cycles.items():
            if data['alerts']:
                scan_ts = data['alerts'][0]['scan_timestamp']
                scan_to_cycle[scan_ts] = cycle_num

        # Accumulate per symbol
        accum = {}
        for row in rows:
            sym = row['symbol']
            if sym not in accum:
                accum[sym] = {
                    'symbol': sym,
                    'count': 0,
                    'calls': 0,
                    'puts': 0,
                    'moneyness_list': [],
                    'peak_score': 0.0,
                    'total_premium': 0.0,
                    'iv_sum': 0.0,
                    'iv_count': 0,
                    'iv_percentile': None,
                    'latest_price': None,
                    'expirations': Counter(),
                    'min_dte': None,
                    'cycles': [],
                }

            s = accum[sym]
            s['count'] += 1

            # Direction
            opt_type = (row.get('option_type') or '').lower()
            if opt_type == 'call':
                s['calls'] += 1
            elif opt_type == 'put':
                s['puts'] += 1

            # Moneyness
            m = row.get('moneyness')
            if m:
                s['moneyness_list'].append(m)

            # Peak score
            score = row.get('significance_score') or 0.0
            if score > s['peak_score']:
                s['peak_score'] = score

            # Premium
            prem = row.get('premium_value') or 0.0
            s['total_premium'] += prem

            # IV
            iv = row.get('iv')
            if iv is not None and iv > 0:
                s['iv_sum'] += iv
                s['iv_count'] += 1

            # IV Percentile (symbol-level, keep latest non-null)
            ivp = row.get('iv_percentile_30d')
            if ivp is not None:
                s['iv_percentile'] = ivp

            # Price (keep latest by row order — rows are ordered by scan_timestamp, alert_timestamp)
            price = row.get('underlying_price')
            if price is not None:
                s['latest_price'] = price

            # Expiration
            exp = row.get('expiration_date')
            if exp:
                s['expirations'][exp] += 1

            # DTE
            dte = row.get('dte')
            if dte is not None:
                if s['min_dte'] is None or dte < s['min_dte']:
                    s['min_dte'] = dte

            # Cycle number
            cycle_num = scan_to_cycle.get(row['scan_timestamp'])
            if cycle_num and cycle_num not in s['cycles']:
                s['cycles'].append(cycle_num)

        # Sort: count desc, then peak_score desc
        result = sorted(accum.values(), key=lambda s: (-s['count'], -s['peak_score']))
        return result

    def _render(self, cycles, symbols, total_alerts):
        """Build content lines for the status box.

        Args:
            cycles: OrderedDict from _build_cycle_map
            symbols: list of dicts from _build_symbol_rollup
            total_alerts: int total alert count

        Returns:
            list[str]: Lines for create_status_box content.
        """
        lines = []
        lines.append("")

        # --- Section 1: Cycle Timeline ---
        for cycle_num, data in cycles.items():
            alert_tags = []
            for a in data['alerts']:
                sym = a['symbol']
                opt = (a.get('option_type') or '').lower()
                if opt == 'call':
                    alert_tags.append("{} ▲C".format(sym))
                elif opt == 'put':
                    alert_tags.append("{} ▼P".format(sym))
                else:
                    alert_tags.append(sym)

            cycle_label = "#{:<3}".format(cycle_num)
            time_label = data['time']
            alert_str = "  ".join(alert_tags) if alert_tags else "—"
            lines.append("  {}  {}   {}".format(cycle_label, time_label, alert_str))

        # --- Separator ---
        lines.append("")
        lines.append("  ─── Symbol Summary ─────────────────────────────────────────")
        lines.append("")

        # --- Section 2: Symbol Roll-Up ---
        for s in symbols:
            parts = []

            # Symbol (left-padded to 6 chars for alignment)
            parts.append("{:<6}".format(s['symbol']))

            # Count
            parts.append("{}x".format(s['count']))

            # Direction breakdown
            if s['puts'] == 0:
                parts.append("({}C)".format(s['calls']))
            elif s['calls'] == 0:
                parts.append("({}P)".format(s['puts']))
            else:
                parts.append("({}C/{}P)".format(s['calls'], s['puts']))

            # Dominant moneyness
            if s['moneyness_list']:
                dominant_m = Counter(s['moneyness_list']).most_common(1)[0][0]
                parts.append("{:<3}".format(dominant_m))
            else:
                parts.append("   ")

            # Peak score
            parts.append("★{:.1f}".format(s['peak_score']))

            # Premium
            parts.append(_format_premium(s['total_premium']))

            # Avg IV
            if s['iv_count'] > 0:
                avg_iv = (s['iv_sum'] / s['iv_count']) * 100
                parts.append("IV {:.0f}%".format(avg_iv))
            else:
                parts.append("      ")

            # IV Percentile
            if s['iv_percentile'] is not None:
                parts.append("IVP {:.0f}".format(s['iv_percentile']))
            else:
                parts.append("      ")

            # Latest price
            if s['latest_price'] is not None:
                if s['latest_price'] >= 100:
                    parts.append("${:.0f}".format(s['latest_price']))
                else:
                    parts.append("${:.2f}".format(s['latest_price']))
            else:
                parts.append("     ")

            # Dominant expiration + DTE
            if s['expirations']:
                dom_exp = s['expirations'].most_common(1)[0][0]
                exp_label = _format_expiration(dom_exp)
                if s['min_dte'] is not None:
                    parts.append("{} {}d".format(exp_label, s['min_dte']))
                else:
                    parts.append(exp_label)
            elif s['min_dte'] is not None:
                parts.append("{}d".format(s['min_dte']))

            # Cycles
            cycle_refs = " ".join("#{}".format(c) for c in s['cycles'])
            parts.append(cycle_refs)

            lines.append("  " + "  ".join(parts))

        lines.append("")
        return lines


def _format_premium(value):
    """Format premium value for compact display."""
    if value is None or value == 0:
        return "     "
    elif value >= 1_000_000:
        return "${:.1f}M".format(value / 1_000_000)
    elif value >= 1_000:
        return "${:.0f}K".format(value / 1_000)
    else:
        return "${:.0f}".format(value)


def _format_expiration(date_str):
    """Format 'YYYY-MM-DD' expiration to compact 'MmmDD' format."""
    try:
        month_names = {
            '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
            '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
            '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
        }
        parts = date_str.split('-')
        month = month_names.get(parts[1], parts[1])
        day = parts[2].lstrip('0') or '0'
        return "{}{}".format(month, day)
    except (IndexError, AttributeError):
        return date_str or ""
