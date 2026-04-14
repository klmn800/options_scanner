#!/usr/bin/env python3
"""
Airline Volatility Strategy Configuration
Based on validated research in data/airline_thesis/thesis-airline.md
"""

# Target Airline Symbols (validated in research)
PRIMARY_AIRLINES = ['AAL', 'UAL', 'DAL']    # Core trio with strongest pattern
SECONDARY_AIRLINES = ['ALK', 'LUV']         # Additional airlines showing pattern

# Calendar-Based Pattern Windows
PATTERN_WINDOWS = {
    'pre_pattern': {'start_day': 1, 'end_day': 7},      # Monitoring phase
    'entry_window': {'start_day': 7, 'end_day': 8},     # Position deployment
    'peak_window': {'start_day': 9, 'end_day': 10},     # Maximum volatility expected
    'exit_window': {'start_day': 11, 'end_day': 12},    # Mandatory close
    'dormant_period': {'start_day': 13, 'end_day': 31}  # Pattern inactive
}

# Volatility Thresholds (from validated research)
VOLATILITY_THRESHOLDS = {
    'entry_trigger': 0.20,        # 20% volatility increase from baseline
    'volume_confirmation': 0.50,  # 50% volume increase required
    'pattern_failure': 0.10,      # <10% increase by day 10 = failure
    'baseline_lookback': 30       # Days to calculate volatility baseline
}

# Expected Pattern Characteristics (historical data)
PATTERN_EXPECTATIONS = {
    'volatility_spike_range': {'min': 0.40, 'max': 0.94},  # 40-94% increases observed
    'volume_spike_range': {'min': 0.79, 'max': 1.21},      # 79-121% increases observed
    'success_rate': 0.778,                                  # 7/9 months validated
    'max_single_day_moves': {'AAL': 0.2180, 'UAL': 0.2594, 'DAL': 0.1994}
}

# Position Management Parameters
POSITION_CONFIG = {
    'strategy_type': 'straddles',           # Long straddles/strangles (non-directional)
    'max_position_size': 0.025,             # 2.5% of capital per airline
    'max_portfolio_heat': 0.10,             # 10% total capital at risk
    'expected_duration_days': 4,            # 3-4 day swing trades
    'stop_loss_percent': 0.50               # 50% stop loss per position
}

# Risk Management Controls
RISK_CONTROLS = {
    'vix_pause_threshold': 40,              # Pause strategy if VIX >40
    'pattern_failure_exit_day': 10,         # Emergency exit if no spike by day 10
    'max_drawdown_limit': 0.15,             # 15% strategy drawdown limit
    'correlation_minimum': 0.60,            # Min correlation between airlines
    'liquidity_minimum_volume': 100        # Minimum daily volume for options
}

# Market Regime Filters
REGIME_FILTERS = {
    'allowed_regimes': ['Bull', 'Strong Bull', 'Neutral'],  # Skip Bear markets?
    'vix_ranges': {
        'low_vol': {'max': 20, 'position_size_multiplier': 1.2},
        'normal_vol': {'min': 20, 'max': 30, 'position_size_multiplier': 1.0},
        'high_vol': {'min': 30, 'max': 40, 'position_size_multiplier': 0.7},
        'extreme_vol': {'min': 40, 'position_size_multiplier': 0.0}  # No trading
    }
}

# Alert and Notification Settings
ALERT_CONFIG = {
    'enable_entry_alerts': True,
    'enable_exit_alerts': True,
    'enable_risk_alerts': True,
    'enable_pattern_alerts': True,
    'notification_methods': ['console', 'database'],  # Can extend to email/SMS
    'alert_cooldown_hours': 6  # Prevent spam alerts
}

# Database Integration
DATABASE_CONFIG = {
    'trades_table': 'airline_strategy_trades',
    'performance_table': 'airline_performance_metrics',
    'pattern_tracking_table': 'airline_pattern_tracking',
    'enable_trade_logging': True,
    'enable_performance_tracking': True
}

# Options Selection Criteria
OPTIONS_CRITERIA = {
    'expiration_min_days': 7,               # Minimum days to expiration
    'expiration_max_days': 45,              # Maximum days to expiration
    'moneyness_range': {'min': 0.90, 'max': 1.10},  # ATM ± 10%
    'min_bid_ask_spread_pct': 0.20,         # Maximum 20% spread
    'min_open_interest': 50,                # Minimum liquidity
    'preferred_dte_range': {'min': 14, 'max': 30}  # Preferred expiration window
}

# Backtesting and Validation
BACKTEST_CONFIG = {
    'historical_validation_months': 12,     # Months of data to validate against
    'minimum_pattern_occurrences': 8,       # Min patterns needed for validation
    'bootstrap_iterations': 1000,           # Statistical validation runs
    'confidence_interval': 0.95             # 95% confidence interval
}

# Performance Tracking
PERFORMANCE_METRICS = {
    'track_monthly_pnl': True,
    'track_win_loss_ratio': True,
    'track_pattern_accuracy': True,
    'track_risk_metrics': True,
    'benchmark_comparison': 'SPY',          # Compare performance to SPY
    'rebalance_frequency': 'monthly'        # Review and adjust monthly
}

# Strategy States
STRATEGY_STATES = {
    'MONITORING': 'Watching for pattern signals',
    'ENTRY_SIGNAL': 'Pattern detected, ready for entry',
    'POSITION_ACTIVE': 'Positions deployed, monitoring peak',
    'EXIT_SIGNAL': 'Exit window active, closing positions',
    'PATTERN_FAILED': 'Pattern failed, emergency exit',
    'DORMANT': 'Pattern inactive, waiting for next cycle',
    'PAUSED': 'Strategy paused due to risk controls'
}

# Logging Configuration
LOGGING_CONFIG = {
    'log_level': 'INFO',
    'log_file': 'airline_volatility.log',
    'log_rotation': 'daily',
    'max_log_files': 30,
    'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}

# Development and Testing
DEV_CONFIG = {
    'enable_paper_trading': True,           # Paper trade first
    'enable_backtesting': True,
    'enable_live_trading': False,           # Start with paper trading
    'debug_mode': True,
    'simulation_start_date': '2024-01-01',
    'simulation_end_date': '2025-09-01'
}

# Integration with Existing Systems
SYSTEM_INTEGRATION = {
    'flow_monitor_integration': True,       # Use Flow Monitor alerts as confirmation
    'oid_integration': True,                # Use OID data for validation
    'oracle_integration': True,             # Monthly pattern validation queries
    'main_orchestrator_integration': True,  # Coordinate with daily cycles
    'tradier_api_integration': True,        # Options pricing and execution
    'alert_system_integration': True        # Feed into existing alert infrastructure
}

# Strategy Metadata
STRATEGY_METADATA = {
    'name': 'Airline Volatility Strategy',
    'version': '1.0.0',
    'author': 'Ben',
    'based_on_research': 'data/airline_thesis/thesis-airline.md',
    'research_validation_date': '2025-09-05',
    'strategy_type': 'Calendar-based volatility capture',
    'target_sector': 'Airlines',
    'expected_monthly_trades': 1,           # One trade cycle per month
    'capital_allocation': 0.10              # 10% of total capital allocation
}