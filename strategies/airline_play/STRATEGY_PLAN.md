# Airline Volatility Strategy Module Plan

**Module Name:** `airline_volatility`  
**Based on Research:** `data/airline_thesis/thesis-airline.md`  
**Strategy Type:** Calendar-based volatility capture  
**Target Sector:** Airlines (AAL, UAL, DAL, ALK, LUV)  

## Mission Statement

Systematically capture the validated mid-month volatility pattern in airline stocks through automated options positioning, real-time pattern monitoring, and disciplined risk management.

## Core Strategy Components

### 1. Pattern Detection Engine (`pattern_detector.py`)
- **Calendar Monitor**: Track days 1-31 with heightened alertness on days 7-12
- **Volatility Expansion Detection**: Real-time monitoring vs historical baselines
- **Volume Confirmation**: Cross-validate with >50% volume spikes
- **Entry Signal Generation**: Trigger when pattern conditions align on days 7-8

### 2. Position Manager (`position_manager.py`) 
- **Entry Logic**: Deploy long straddles/strangles on pattern signals
- **Peak Monitoring**: Track maximum volatility capture on days 9-10
- **Exit Discipline**: Force close by days 11-12 regardless of P&L
- **Portfolio Coordination**: Manage multiple airline positions simultaneously

### 3. Risk Controller (`risk_controller.py`)
- **Pattern Failure Detection**: Emergency exit if volatility doesn't expand by day 10
- **Market Regime Filters**: Pause during extreme VIX environments (>40)
- **Position Sizing**: Dynamic sizing based on historical volatility expectations
- **Stop Loss Management**: Hard stop at -50% to preserve capital

### 4. Strategy Orchestrator (`airline_main.py`)
- **Daily Monitoring**: Continuous pattern assessment during market hours
- **Signal Coordination**: Integrate with existing Flow Monitor and OID data
- **Performance Tracking**: Real-time P&L and pattern evolution analysis
- **Alert System**: Notifications for entry/exit windows and risk events

## Data Integration Points

### Input Sources
- **Historical Prices**: From `historical_prices` table for baseline calculations
- **Options Data**: From OID pipeline for volatility analysis
- **Flow Alerts**: From Flow Monitor for confirmation signals
- **Market Regime**: From `market_daily_summary` for regime filtering

### Output Integration
- **Alerts**: Feed into existing alert system
- **Performance Data**: Store in dedicated `airline_strategy_trades` table
- **Risk Metrics**: Integration with portfolio risk management

## Implementation Architecture

### Module Structure
```
strategies/airline_volatility/
├── airline_main.py           # Main orchestrator
├── pattern_detector.py       # Calendar and volatility pattern detection
├── position_manager.py       # Options position lifecycle management
├── risk_controller.py        # Risk management and stops
├── airline_config.py         # Strategy configuration
├── utils/
│   ├── calendar_utils.py     # Month day calculations
│   ├── volatility_utils.py   # Volatility calculations
│   └── airline_symbols.py    # Airline ticker management
├── tests/
│   ├── test_pattern_detection.py
│   ├── test_position_manager.py
│   └── backtest_validation.py
└── STRATEGY_PLAN.md         # This document
```

## Key Strategy Parameters (From Validated Research)

### Timing Windows
- **Pre-Pattern Monitoring**: Days 1-7 (setup phase)
- **Entry Window**: Days 7-8 (position deployment)
- **Peak Window**: Days 9-10 (maximum profit potential)
- **Exit Window**: Days 11-12 (mandatory close)
- **Rest Period**: Days 13-31 (pattern dormant)

### Volatility Thresholds
- **Entry Trigger**: 20% volatility increase from monthly baseline
- **Volume Confirmation**: 50% volume increase from monthly average
- **Peak Detection**: 40-94% volatility spike (historical range)
- **Failure Threshold**: <10% volatility increase by day 10

### Position Parameters
- **Strategy Type**: Long straddles/strangles (non-directional)
- **Target Airlines**: AAL, UAL, DAL (primary); ALK, LUV (secondary)
- **Expected Duration**: 3-4 day swings
- **Magnitude Expectation**: 19-26% single-day moves possible
- **Success Rate**: 7/9 months validated (77.8%)

## Risk Management Framework

### Position-Level Risk
- **Maximum Loss**: 50% stop loss per position
- **Position Sizing**: 2-3% of capital per airline
- **Portfolio Heat**: Maximum 10% total capital at risk

### Pattern-Level Risk
- **Pattern Failure**: If no volatility spike by day 10, exit all positions
- **Market Regime**: Pause strategy if VIX >40 or market crash conditions
- **Correlation Risk**: Monitor airline sector correlation breakdown

### System-Level Risk
- **Calendar Risk**: Account for market holidays affecting day counts
- **Black Swan**: Emergency exit procedures for sector-specific events
- **Execution Risk**: Ensure sufficient options liquidity for entry/exit

## Success Metrics & KPIs

### Primary Metrics
- **Monthly Win Rate**: Target >70% (based on 77.8% historical)
- **Average Profit**: Target 100-300% per winning trade
- **Maximum Drawdown**: Limit to 15% of strategy allocation
- **Sharpe Ratio**: Target >1.5 for risk-adjusted returns

### Pattern Validation Metrics
- **Pattern Consistency**: Monthly pattern occurrence tracking
- **Volatility Expansion**: Average spike magnitude vs baseline
- **Volume Confirmation**: Percentage of entries with volume confirmation
- **Duration Accuracy**: Actual vs expected pattern duration

### Risk Metrics
- **Stop Loss Frequency**: Track pattern failure rate
- **Market Regime Impact**: Performance across different VIX environments
- **Correlation Stability**: Monitor airline sector correlation coefficients

## Development Phases

### Phase 1: Core Implementation (Week 1)
- [ ] Basic pattern detection engine
- [ ] Simple position entry/exit logic
- [ ] Risk controls and stop losses
- [ ] Configuration and logging

### Phase 2: Integration (Week 2) 
- [ ] Connect to existing data pipelines
- [ ] Alert system integration
- [ ] Performance tracking database
- [ ] Oracle query integration for validation

### Phase 3: Enhancement (Week 3)
- [ ] Advanced pattern recognition
- [ ] Dynamic position sizing
- [ ] Multi-timeframe analysis
- [ ] Backtesting framework

### Phase 4: Production (Week 4)
- [ ] Live trading integration
- [ ] Monitoring dashboards
- [ ] Performance reporting
- [ ] Strategy optimization

## Integration with Existing Systems

### Coordination Points
- **Flow Monitor**: Use airline flow alerts as confirmation signals
- **OID Strategy**: Leverage open interest data for position validation  
- **Oracle System**: Monthly pattern validation and parameter tuning
- **Main Orchestrator**: Integration with daily trading cycle scheduling

### Data Dependencies
- **Database Access**: Read/write access to `datalake.db`
- **API Access**: Tradier API for options pricing and execution
- **Market Data**: Real-time quotes for volatility calculations
- **Calendar Data**: Market calendar for accurate day counting

## Success Criteria for Module Completion

### Minimum Viable Product (MVP)
- [ ] Automated pattern detection on calendar schedule
- [ ] Entry signal generation with risk controls
- [ ] Position lifecycle management (entry/exit/stops)
- [ ] Basic performance tracking and logging

### Full Production Ready
- [ ] Integration with existing alert systems
- [ ] Real-time monitoring and risk management
- [ ] Comprehensive backtesting validation
- [ ] Performance analytics and reporting

### Advanced Features (Future)
- [ ] Machine learning pattern enhancement
- [ ] Cross-sector pattern detection
- [ ] Options flow integration for entry timing
- [ ] Automated parameter optimization

---

**Next Steps:**
1. Review and approve strategy plan
2. Begin Phase 1 implementation with core components
3. Validate against historical data using Oracle queries
4. Integrate with existing system architecture

**Document Status:** Draft v1.0 - Ready for review and implementation