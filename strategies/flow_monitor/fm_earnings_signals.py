"""
Real-time earnings signal tracking during Flow Monitor cycles.

Recomputes straddle-based underpricing using fresh intraday option prices
from flow_options_scans, compares against morning baseline from
earnings_upcoming, and logs signal upgrades/downgrades to console.

Runs every N cycles (default 4, ~hourly) to avoid excessive query cost.
Console output only — no database writes, no email alerts.

Config (flow_monitor.earnings_signal_tracking):
    enabled: bool — master toggle (default false)
    max_days_ahead: int — only check earnings within N days (default 30)
    check_interval_cycles: int — run every N cycles (default 4)

Database reads:
    - earnings_upcoming (morning baseline signals + historical avg move)
    - flow_options_scans (fresh intraday option prices at current scan_timestamp)

Database writes:
    None
"""

import logging
from collections import defaultdict

from tools.log_utils import beautiful_log
from strategies.earnings_intel.ei_moves_upcoming import determine_earnings_play_signal


# Signal rank for comparison — higher = more bullish signal
_SIGNAL_RANKS = {
    'AVOID': 0,
    'NEUTRAL': 1,
    'WATCH': 2,
    'BUY': 3,
    'STRONG BUY': 4,
}


class FMEarningsSignalTracker:
    """Track intraday earnings signal changes using fresh FM scan data.

    Instantiated once per FM session in run_market_hours(). Holds in-memory
    dedup set so the same signal transition isn't logged repeatedly.
    """

    def __init__(self, storage, config):
        """
        Args:
            storage: FMStorage instance (provides query_with_params)
            config: Full config dict (needs earnings_play + flow_monitor sections)
        """
        self._storage = storage
        self._config = config
        self._logged_changes = set()  # (symbol, new_signal) pairs already logged

        # Extract config
        est_config = config.get('flow_monitor', {}).get('earnings_signal_tracking', {})
        self._max_days_ahead = est_config.get('max_days_ahead', 30)
        self._check_interval = est_config.get('check_interval_cycles', 4)
        self._earnings_play_config = config.get('earnings_play', {})

    @property
    def check_interval(self):
        """How often to run (in cycles). Exposed for caller skip logic."""
        return self._check_interval

    def track_signals(self, scan_timestamp):
        """Recompute signals from fresh scan data and log any changes.

        Args:
            scan_timestamp: Current FM scan timestamp (ISO string)

        Returns:
            dict: {'symbols_checked': int, 'upgrades': int, 'downgrades': int}
        """
        stats = {'symbols_checked': 0, 'upgrades': 0, 'downgrades': 0}

        # 1. Get morning baselines
        baselines = self._get_earnings_baselines()
        if not baselines:
            return stats

        # 2. Bulk fetch fresh option data
        symbols = [b['symbol'] for b in baselines]
        option_data = self._get_fresh_option_data(symbols, scan_timestamp)
        if not option_data:
            return stats

        # 3. Compute straddles and compare signals
        for baseline in baselines:
            symbol = baseline['symbol']
            if symbol not in option_data:
                continue

            contracts = option_data[symbol]
            straddle = self._compute_straddle(
                contracts, baseline['earnings_date'], symbol
            )
            if straddle is None:
                continue

            stats['symbols_checked'] += 1

            # Compute fresh signal
            historical_avg = baseline['historical_avg_move_pct']
            fresh_move = straddle['expected_move_pct']

            if fresh_move <= 0:
                continue

            fresh_underpricing = ((historical_avg - fresh_move) / fresh_move) * 100
            fresh_signal = determine_earnings_play_signal(
                fresh_underpricing, self._earnings_play_config
            )

            # Compare to morning baseline
            morning_signal = baseline['baseline_signal']
            morning_rank = _SIGNAL_RANKS.get(morning_signal, -1)
            fresh_rank = _SIGNAL_RANKS.get(fresh_signal, -1)

            if morning_rank < 0 or fresh_rank < 0:
                continue  # Unknown signal — skip

            if fresh_rank != morning_rank:
                direction = 'upgrade' if fresh_rank > morning_rank else 'downgrade'
                self._log_change(
                    symbol=symbol,
                    morning_signal=morning_signal,
                    fresh_signal=fresh_signal,
                    morning_underpricing=baseline['baseline_underpricing'],
                    fresh_underpricing=fresh_underpricing,
                    straddle=straddle,
                    direction=direction,
                )
                if direction == 'upgrade':
                    stats['upgrades'] += 1
                else:
                    stats['downgrades'] += 1

        return stats

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_earnings_baselines(self):
        """Query earnings_upcoming for actionable symbols with morning baselines."""
        query = """
            SELECT
                symbol,
                earnings_date,
                earnings_play_signal AS baseline_signal,
                relative_underpricing_pct AS baseline_underpricing,
                historical_avg_move_pct,
                straddle_expected_move_pct AS morning_straddle
            FROM earnings_upcoming
            WHERE earnings_days_ahead >= 1
                AND earnings_days_ahead <= ?
                AND earnings_play_signal IS NOT NULL
                AND earnings_play_signal NOT IN ('UNKNOWN', '')
                AND historical_avg_move_pct IS NOT NULL
                AND historical_avg_move_pct > 0
            ORDER BY earnings_days_ahead ASC
        """
        rows = self._storage.query_with_params(query, (self._max_days_ahead,))
        return rows

    def _get_fresh_option_data(self, symbols, scan_timestamp):
        """Bulk fetch option contracts from flow_options_scans for all earnings symbols.

        Returns:
            dict mapping symbol -> list of contract dicts
        """
        if not symbols:
            return {}

        placeholders = ','.join('?' for _ in symbols)
        query = """
            SELECT
                symbol,
                strike,
                expiration_date,
                option_type,
                last_price,
                underlying_price
            FROM flow_options_scans
            WHERE scan_timestamp = ?
                AND symbol IN ({})
                AND last_price > 0
                AND option_type IN ('call', 'put')
        """.format(placeholders)

        params = (scan_timestamp,) + tuple(symbols)
        rows = self._storage.query_with_params(query, params)

        # Group by symbol
        grouped = defaultdict(list)
        for row in rows:
            grouped[row['symbol']].append(row)

        return dict(grouped)

    def _compute_straddle(self, contracts, earnings_date, symbol):
        """Compute straddle expected move from intraday option contracts.

        Mirrors get_straddle_expected_move() logic from ei_moves_upcoming.py
        but uses flow_options_scans data instead of option_contracts.

        Args:
            contracts: List of contract dicts from flow_options_scans
            earnings_date: Earnings date string (YYYY-MM-DD)
            symbol: Stock symbol (for debug logging)

        Returns:
            Dict with expected_move_pct, expiration_date, atm_strike,
                call_price, put_price, underlying_price — or None
        """
        if not contracts:
            return None

        # Get underlying price from first contract
        underlying_price = contracts[0].get('underlying_price')
        if not underlying_price or underlying_price <= 0:
            return None

        # Find all unique post-earnings expirations
        post_earnings_exps = sorted(set(
            c['expiration_date'] for c in contracts
            if c['expiration_date'] >= earnings_date
        ))

        if not post_earnings_exps:
            logging.debug("No post-earnings expiration for {} (earnings: {})".format(
                symbol, earnings_date))
            return None

        target_exp = post_earnings_exps[0]  # First expiration after earnings

        # Get contracts at target expiration
        exp_contracts = [c for c in contracts if c['expiration_date'] == target_exp]

        # Find ATM strike (closest to underlying price)
        strikes = sorted(set(c['strike'] for c in exp_contracts),
                         key=lambda s: abs(s - underlying_price))

        if not strikes:
            return None

        atm_strike = strikes[0]

        # Get call and put at ATM strike
        call_price = None
        put_price = None

        for c in exp_contracts:
            if c['strike'] == atm_strike:
                # flow_options_scans uses lowercase option_type
                if c['option_type'] == 'call':
                    call_price = c['last_price']
                elif c['option_type'] == 'put':
                    put_price = c['last_price']

        if not call_price or not put_price:
            logging.debug("Incomplete straddle for {} at ${:.0f} (call: {}, put: {})".format(
                symbol, atm_strike, call_price, put_price))
            return None

        # Calculate straddle expected move (same formula as ei_moves_upcoming)
        straddle_price = call_price + put_price
        expected_move_dollars = straddle_price * 0.85  # Industry standard multiplier
        expected_move_pct = (expected_move_dollars / underlying_price) * 100

        return {
            'expected_move_pct': expected_move_pct,
            'expiration_date': target_exp,
            'atm_strike': atm_strike,
            'call_price': call_price,
            'put_price': put_price,
            'underlying_price': underlying_price,
        }

    def _log_change(self, symbol, morning_signal, fresh_signal,
                    morning_underpricing, fresh_underpricing,
                    straddle, direction):
        """Log a signal change to console (with per-session deduplication)."""
        dedup_key = (symbol, fresh_signal)
        if dedup_key in self._logged_changes:
            return

        self._logged_changes.add(dedup_key)

        morning_und_str = "{:.1f}%".format(morning_underpricing) if morning_underpricing is not None else "N/A"
        fresh_und_str = "{:.1f}%".format(fresh_underpricing)

        straddle_str = ""
        if straddle.get('expected_move_pct'):
            straddle_dollars = straddle['call_price'] + straddle['put_price']
            straddle_str = " | Straddle ${:.2f} ({:.1f}%) @ ${:.2f} (exp {}, ATM ${:.0f})".format(
                straddle_dollars,
                straddle['expected_move_pct'],
                straddle['underlying_price'],
                straddle['expiration_date'],
                straddle['atm_strike'],
            )

        arrow = "UPGRADE" if direction == 'upgrade' else "DOWNGRADE"
        beautiful_log(
            "{}: {} -> {} | {} | Underpricing {} -> {}{}".format(
                symbol, morning_signal, fresh_signal, arrow,
                morning_und_str, fresh_und_str, straddle_str,
            ),
            'warning' if direction == 'upgrade' else 'info',
        )
