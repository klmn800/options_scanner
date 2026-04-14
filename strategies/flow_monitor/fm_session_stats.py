#!/usr/bin/env python3
"""
Flow Monitor Session Stats (fm_session_stats.py)
-------------------------------------------------
Lightweight stats accumulator for FM market hours cycles.

Tracks operational metrics across all cycles and provides:
- Structured summary dict for orchestrator consumption
- Formatted end-of-day lines for console display

No database, no complexity - just structured data collection.

Created: 2026-02-13
Author: Ben (with assistance from Claude)
"""


class FMSessionStats:
    """Accumulates operational statistics across FM market hours cycles.

    Usage: Create once before cycle loop, call record_cycle() each cycle,
    call get_summary() at end to get structured dict for orchestrator.
    """

    def __init__(self):
        # Cycle counts
        self.total_cycles = 0
        self.successful_cycles = 0
        self.failed_cycles = 0

        # Symbol gap tracking: {symbol: count}
        self.missing_quotes = {}
        self.failed_options = {}

        # Error tracking
        self.errors_by_type = {'timeout': 0, 'rate_limit': 0, 'connection': 0, 'other': 0}
        self.errors_by_symbol = {}  # {symbol: [{'type': str, 'cycle': int}]}

        # Timing lists (seconds)
        self.cycle_times = []
        self.collection_times = []
        self.storage_times = []
        self.analysis_times = []
        self.analysis_query_times = []
        self.analysis_scoring_times = []
        self.analysis_db_write_times = []
        self.alert_times = []
        self.watchlist_times = []
        self.sync_times = []
        self.sync_rows = []

        # Per-cycle tracking for performance database
        self.scan_timestamps = []
        self.contracts_collected = []
        self.alerts_generated = []
        self.symbols_attempted = []
        self.symbols_with_data = []

        # News enrichment totals
        self.news_enrichment = {'enriched': 0, 'skipped': 0, 'failed': 0}

    def record_cycle(self, cycle_num, collector, timings, news_stats=None):
        """Record data from one completed cycle.

        Args:
            cycle_num: Current cycle number (1-based)
            collector: FMCollector instance (has last_missing_symbols,
                       last_failed_options_symbols, last_error_details)
            timings: dict with keys: collection, analysis, alert, cycle
            news_stats: dict with keys: enriched, skipped, failed (or None)
        """
        self.total_cycles = cycle_num

        # Determine success from whether scan_timestamp was produced
        scan_ok = timings.get('scan_ok', True)
        if scan_ok:
            self.successful_cycles += 1
        else:
            self.failed_cycles += 1

        # Per-cycle identifiers and counts
        self.scan_timestamps.append(timings.get('scan_timestamp', ''))
        self.contracts_collected.append(timings.get('contracts_collected', 0))
        self.alerts_generated.append(timings.get('alerts_generated', 0))
        self.symbols_attempted.append(timings.get('symbols_attempted', 0))
        self.symbols_with_data.append(timings.get('symbols_with_data', 0))

        # Timing
        self.cycle_times.append(timings.get('cycle', 0))
        self.collection_times.append(timings.get('collection', 0))
        self.storage_times.append(timings.get('storage', 0))
        self.analysis_times.append(timings.get('analysis', 0))
        self.analysis_query_times.append(timings.get('analysis_query', 0))
        self.analysis_scoring_times.append(timings.get('analysis_scoring', 0))
        self.analysis_db_write_times.append(timings.get('analysis_db_write', 0))
        self.alert_times.append(timings.get('alert', 0))
        self.watchlist_times.append(timings.get('watchlist', 0))
        self.sync_times.append(timings.get('sync', 0))
        self.sync_rows.append(timings.get('sync_rows', 0))

        # Missing quotes
        for sym in getattr(collector, 'last_missing_symbols', []):
            self.missing_quotes[sym] = self.missing_quotes.get(sym, 0) + 1

        # Failed options
        for sym in getattr(collector, 'last_failed_options_symbols', []):
            self.failed_options[sym] = self.failed_options.get(sym, 0) + 1

        # Error details from collector
        for detail in getattr(collector, 'last_error_details', []):
            err_type = detail.get('type', 'other')
            sym = detail.get('symbol', 'UNKNOWN')

            # Aggregate by type
            if err_type in self.errors_by_type:
                self.errors_by_type[err_type] += 1
            else:
                self.errors_by_type['other'] += 1

            # Aggregate by symbol
            if sym not in self.errors_by_symbol:
                self.errors_by_symbol[sym] = []
            self.errors_by_symbol[sym].append({'type': err_type, 'cycle': cycle_num})

        # News enrichment
        if news_stats:
            self.news_enrichment['enriched'] += news_stats.get('enriched', 0)
            self.news_enrichment['skipped'] += news_stats.get('skipped', 0)
            self.news_enrichment['failed'] += news_stats.get('failed', 0)

    def get_summary(self):
        """Return structured summary dict for orchestrator consumption.

        Returns:
            dict with all accumulated stats, ready for JSON serialization.
        """
        total_errors = sum(self.errors_by_type.values())

        # Timing stats (guard against empty lists)
        timing = {}
        if self.cycle_times:
            timing = {
                'avg_cycle': sum(self.cycle_times) / len(self.cycle_times),
                'min_cycle': min(self.cycle_times),
                'max_cycle': max(self.cycle_times),
                'avg_collection': sum(self.collection_times) / len(self.collection_times) if self.collection_times else 0,
                'avg_storage': sum(self.storage_times) / len(self.storage_times) if self.storage_times else 0,
                'avg_analysis': sum(self.analysis_times) / len(self.analysis_times) if self.analysis_times else 0,
                'avg_analysis_query': sum(self.analysis_query_times) / len(self.analysis_query_times) if self.analysis_query_times else 0,
                'avg_analysis_scoring': sum(self.analysis_scoring_times) / len(self.analysis_scoring_times) if self.analysis_scoring_times else 0,
                'avg_analysis_db_write': sum(self.analysis_db_write_times) / len(self.analysis_db_write_times) if self.analysis_db_write_times else 0,
                'avg_alert': sum(self.alert_times) / len(self.alert_times) if self.alert_times else 0,
                'avg_watchlist': sum(self.watchlist_times) / len(self.watchlist_times) if self.watchlist_times else 0,
                'avg_sync': sum(self.sync_times) / len(self.sync_times) if self.sync_times else 0,
                'avg_sync_rows': sum(self.sync_rows) / len(self.sync_rows) if self.sync_rows else 0,
            }

        # Identify symbols that failed every single cycle
        always_missing = sorted(s for s, c in self.missing_quotes.items() if c == self.total_cycles) if self.total_cycles > 0 else []
        always_failed_options = sorted(s for s, c in self.failed_options.items() if c == self.total_cycles) if self.total_cycles > 0 else []

        # Per-cycle totals
        total_contracts = sum(self.contracts_collected) if self.contracts_collected else 0
        total_alerts = sum(self.alerts_generated) if self.alerts_generated else 0

        return {
            'total_cycles': self.total_cycles,
            'successful_cycles': self.successful_cycles,
            'failed_cycles': self.failed_cycles,
            'total_contracts_collected': total_contracts,
            'total_alerts_generated': total_alerts,
            'scan_timestamps': list(self.scan_timestamps),
            'contracts_collected': list(self.contracts_collected),
            'alerts_generated': list(self.alerts_generated),
            'symbols_attempted': list(self.symbols_attempted),
            'symbols_with_data': list(self.symbols_with_data),
            'timing': timing,
            'errors': {
                'total': total_errors,
                'by_type': dict(self.errors_by_type),
                'by_symbol_count': len(self.errors_by_symbol),
            },
            'missing_quotes': {
                'total_symbols': len(self.missing_quotes),
                'always_missing': always_missing,
                'details': dict(sorted(self.missing_quotes.items(), key=lambda x: (-x[1], x[0]))),
            },
            'failed_options': {
                'total_symbols': len(self.failed_options),
                'always_failed': always_failed_options,
                'details': dict(sorted(self.failed_options.items(), key=lambda x: (-x[1], x[0]))),
            },
            'news_enrichment': dict(self.news_enrichment),
        }

    def format_end_of_day_lines(self):
        """Return formatted lines for end-of-day console display.

        Returns:
            list[str]: Lines ready for beautiful_log() output.
                       Replaces the ad-hoc printing in fm_main.py.
        """
        lines = []
        total = self.total_cycles
        if total == 0:
            return lines

        # --- Missing quotes summary ---
        if self.missing_quotes:
            sorted_missing = sorted(self.missing_quotes.items(), key=lambda x: (-x[1], x[0]))
            always_missing = [s for s, c in sorted_missing if c == total]
            sometimes_missing = [(s, c) for s, c in sorted_missing if c < total]

            lines.append("")
            lines.append("Missing Quotes Summary ({} symbols across {} cycles):".format(
                len(sorted_missing), total))
            if always_missing:
                lines.append("   Every cycle ({}): {}".format(
                    len(always_missing), ", ".join(always_missing)))
            if sometimes_missing:
                lines.append("   Intermittent:")
                for sym, count in sometimes_missing:
                    lines.append("     {} - {}/{} cycles".format(sym, count, total))

        # --- Failed options summary ---
        if self.failed_options:
            sorted_failed = sorted(self.failed_options.items(), key=lambda x: (-x[1], x[0]))
            always_failed = [s for s, c in sorted_failed if c == total]
            sometimes_failed = [(s, c) for s, c in sorted_failed if c < total]

            lines.append("")
            lines.append("Failed Options Summary ({} symbols across {} cycles):".format(
                len(sorted_failed), total))
            if always_failed:
                lines.append("   Every cycle ({}): {}".format(
                    len(always_failed), ", ".join(always_failed)))
            if sometimes_failed:
                lines.append("   Intermittent:")
                for sym, count in sometimes_failed:
                    lines.append("     {} - {}/{} cycles".format(sym, count, total))

        # --- Collection errors summary ---
        total_errors = sum(self.errors_by_type.values())
        if total_errors > 0:
            type_parts = []
            for etype in ['timeout', 'rate_limit', 'connection', 'other']:
                count = self.errors_by_type[etype]
                if count > 0:
                    type_parts.append("{} {}".format(count, etype))

            lines.append("")
            lines.append("Collection Errors: {} total ({})".format(
                total_errors, ", ".join(type_parts)))

            # Show symbols with recurring errors (appeared in >1 cycle)
            recurring = {s: entries for s, entries in self.errors_by_symbol.items()
                         if len(entries) > 1}
            if recurring:
                recurring_sorted = sorted(recurring.items(), key=lambda x: -len(x[1]))[:10]
                lines.append("   Recurring error symbols: {}".format(
                    ", ".join("{} (x{})".format(s, len(e)) for s, e in recurring_sorted)))

        return lines

    def get_symbol_gaps_data(self):
        """Return data for symbol_gaps JSON file persistence.

        Returns:
            dict: Ready for json.dump, or None if no gaps to report.
        """
        if not self.missing_quotes and not self.failed_options:
            return None

        from tools.timezone_utils import now_eastern
        now = now_eastern()

        return {
            'trade_date': now.strftime('%Y-%m-%d'),
            'total_cycles': self.total_cycles,
            'missing_quotes': dict(sorted(self.missing_quotes.items(), key=lambda x: (-x[1], x[0]))),
            'failed_options': dict(sorted(self.failed_options.items(), key=lambda x: (-x[1], x[0]))),
        }

    def save_to_daily_state(self):
        """Persist current stats to logs/daily_state.json for restart resilience.

        Called after each cycle completes so that if FM is restarted mid-day,
        the session summary at end-of-day reflects ALL cycles from the entire day.
        """
        from main_ui import _save_fm_session
        _save_fm_session({
            'total_cycles': self.total_cycles,
            'successful_cycles': self.successful_cycles,
            'failed_cycles': self.failed_cycles,
            'errors_by_type': dict(self.errors_by_type),
            'scan_timestamps': self.scan_timestamps,
            'contracts_collected': self.contracts_collected,
            'alerts_generated': self.alerts_generated,
            'symbols_attempted': self.symbols_attempted,
            'symbols_with_data': self.symbols_with_data,
            'cycle_times': self.cycle_times,
            'collection_times': self.collection_times,
            'storage_times': self.storage_times,
            'analysis_times': self.analysis_times,
            'analysis_query_times': self.analysis_query_times,
            'analysis_scoring_times': self.analysis_scoring_times,
            'analysis_db_write_times': self.analysis_db_write_times,
            'alert_times': self.alert_times,
            'watchlist_times': self.watchlist_times,
            'sync_times': self.sync_times,
            'sync_rows': self.sync_rows,
            'missing_quotes': dict(self.missing_quotes),
            'failed_options': dict(self.failed_options),
            'news_enrichment': dict(self.news_enrichment),
        })

    @classmethod
    def load_from_daily_state(cls):
        """Restore stats from logs/daily_state.json if today's data exists.

        Returns a new FMSessionStats instance pre-populated with prior cycles
        from today, or a fresh instance if no saved data is found.
        """
        from main_ui import _load_daily_state
        state = _load_daily_state()
        instance = cls()
        if state and state.get('fm_session'):
            fm = state['fm_session']
            instance.total_cycles = fm.get('total_cycles', 0)
            instance.successful_cycles = fm.get('successful_cycles', 0)
            instance.failed_cycles = fm.get('failed_cycles', 0)
            instance.errors_by_type = fm.get('errors_by_type', {'timeout': 0, 'rate_limit': 0, 'connection': 0, 'other': 0})
            instance.scan_timestamps = fm.get('scan_timestamps', [])
            instance.contracts_collected = fm.get('contracts_collected', [])
            instance.alerts_generated = fm.get('alerts_generated', [])
            instance.symbols_attempted = fm.get('symbols_attempted', [])
            instance.symbols_with_data = fm.get('symbols_with_data', [])
            instance.cycle_times = fm.get('cycle_times', [])
            instance.collection_times = fm.get('collection_times', [])
            instance.storage_times = fm.get('storage_times', [])
            instance.analysis_times = fm.get('analysis_times', [])
            instance.analysis_query_times = fm.get('analysis_query_times', [])
            instance.analysis_scoring_times = fm.get('analysis_scoring_times', [])
            instance.analysis_db_write_times = fm.get('analysis_db_write_times', [])
            instance.alert_times = fm.get('alert_times', [])
            instance.watchlist_times = fm.get('watchlist_times', [])
            instance.sync_times = fm.get('sync_times', [])
            instance.sync_rows = fm.get('sync_rows', [])
            instance.missing_quotes = fm.get('missing_quotes', {})
            instance.failed_options = fm.get('failed_options', {})
            instance.news_enrichment = fm.get('news_enrichment', {'enriched': 0, 'skipped': 0, 'failed': 0})
        return instance

    def get_diagnostic_missing_quotes_line(self):
        """Return a single diagnostic log line for missing quotes."""
        if not self.missing_quotes:
            return None

        total = self.total_cycles
        sorted_missing = sorted(self.missing_quotes.items(), key=lambda x: (-x[1], x[0]))
        always_missing = [s for s, c in sorted_missing if c == total]
        sometimes_missing = [(s, c) for s, c in sorted_missing if c < total]

        from tools.timezone_utils import now_eastern
        now = now_eastern()

        return "[{}] Missing Quotes: {} symbols | Always: {} | Intermittent: {} | Details: {}".format(
            now.strftime('%Y-%m-%d %H:%M:%S'),
            len(sorted_missing),
            len(always_missing),
            len(sometimes_missing),
            ", ".join("{}:{}/{}".format(s, c, total) for s, c in sorted_missing))

    def get_diagnostic_failed_options_line(self):
        """Return a single diagnostic log line for failed options."""
        if not self.failed_options:
            return None

        total = self.total_cycles
        sorted_failed = sorted(self.failed_options.items(), key=lambda x: (-x[1], x[0]))
        always_failed = [s for s, c in sorted_failed if c == total]
        sometimes_failed = [(s, c) for s, c in sorted_failed if c < total]

        from tools.timezone_utils import now_eastern
        now = now_eastern()

        return "[{}] Failed Options: {} symbols | Always: {} | Intermittent: {} | Details: {}".format(
            now.strftime('%Y-%m-%d %H:%M:%S'),
            len(sorted_failed),
            len(always_failed),
            len(sometimes_failed),
            ", ".join("{}:{}/{}".format(s, c, total) for s, c in sorted_failed))
