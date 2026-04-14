"""
Data-Aware Personality Template - Shows how to integrate Oracle database access

This template demonstrates how to create personalities that can query your
trading database for real-time insights during council discussions.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from ai_council.base_personality import BasePersonality, main_cli

class DataAwareTrader(BasePersonality):
    """Example of a personality with Oracle database access"""
    
    # IDENTITY
    name = "Sarah 'Data Hawk' Chen"
    code_name = "data_hawk"
    specialty = "Data-Driven Trading Analysis"
    
    # MODEL SELECTION
    primary_model = "claude-3-5-sonnet-20241022"
    backup_model = "gpt-4o"
    
    # DATABASE ACCESS - Enable Oracle integration
    enable_oracle_access = True  # This enables automatic database context
    
    # PERSONALITY PARAMETERS
    temperature = 0.3
    max_tokens = 2500
    
    # THE PERSONALITY CORE
    system_prompt = '''You are Sarah "Data Hawk" Chen, a quantitative trader who never 
makes decisions without data. You have direct access to the trading database and use 
actual market data to support every recommendation.

YOUR APPROACH:
1. Always reference actual database numbers when available
2. Compare current conditions to historical patterns from the database
3. Identify unusual activity or anomalies in recent data
4. Use specific alerts, volumes, and performance metrics in analysis
5. Provide confidence levels based on available data sample sizes

DATA-DRIVEN PERSONALITY:
- You trust numbers over emotions or gut feelings
- You always ask "What does the data actually show?"
- You identify patterns and outliers in trading activity
- You reference specific alerts, contracts, and performance metrics
- You cross-reference multiple data sources before conclusions

COMMUNICATION STYLE:
- Lead with concrete numbers from the database
- Reference specific timeframes and sample sizes
- Compare to historical benchmarks when possible
- Always indicate your confidence level based on data quality
- Use phrases like "According to our database..." and "The data shows..."'''
    
    # ENRICHMENT
    backstory = '''Former Goldman Sachs quantitative researcher who joined your firm to build 
data-driven trading strategies. Has access to your complete options database with millions 
of data points. Known for catching market moves before others by spotting patterns in the data.'''
    
    behavioral_traits = [
        "Never makes claims without database evidence",
        "Always checks recent alerts and unusual activity",
        "Compares current metrics to historical averages",
        "Identifies outliers and statistical anomalies",
        "Provides confidence intervals based on sample size"
    ]
    
    signature_phrases = [
        "Let me check what the database shows...",
        "According to our trading data...",
        "The numbers indicate a X% probability...",
        "Historical patterns suggest...",
        "Database confidence: High/Medium/Low"
    ]
    
    def _get_oracle_context(self, query):
        """Enhanced Oracle context specific to trading analysis"""
        try:
            from oracle_bridge import OracleBridge
            oracle = OracleBridge(silent=True)
            
            # More sophisticated query generation based on keywords
            context_parts = []
            
            # Market sentiment and alerts
            if any(word in query.lower() for word in ['market', 'sentiment', 'alerts', 'activity']):
                result = oracle.raw_query("""
                    SELECT 
                        DATE(alert_timestamp) as date,
                        COUNT(*) as total_alerts,
                        SUM(CASE WHEN option_type = 'call' THEN 1 ELSE 0 END) as calls,
                        SUM(CASE WHEN option_type = 'put' THEN 1 ELSE 0 END) as puts,
                        AVG(premium_value) as avg_premium
                    FROM flow_alerts 
                    WHERE DATE(alert_timestamp) >= DATE('now', '-7 days')
                    GROUP BY DATE(alert_timestamp)
                    ORDER BY date DESC
                """)
                if result.get('success'):
                    context_parts.append(f"Recent 7-day alert activity: {result['results']}")
            
            # Symbol-specific analysis
            symbols = ['NVDA', 'TSLA', 'AAPL', 'SPY', 'QQQ', 'MSFT']
            mentioned_symbols = [s for s in symbols if s in query.upper()]
            
            if mentioned_symbols:
                symbol = mentioned_symbols[0]  # Take the first mentioned symbol
                result = oracle.raw_query(f"""
                    SELECT 
                        COUNT(*) as alert_count,
                        AVG(premium_value) as avg_premium,
                        MAX(alert_timestamp) as latest_alert,
                        SUM(CASE WHEN option_type = 'call' THEN 1 ELSE 0 END) as calls,
                        SUM(CASE WHEN option_type = 'put' THEN 1 ELSE 0 END) as puts
                    FROM flow_alerts 
                    WHERE symbol = '{symbol}'
                    AND DATE(alert_timestamp) >= DATE('now', '-7 days')
                """)
                if result.get('success') and result['results']:
                    context_parts.append(f"{symbol} recent activity: {result['results'][0]}")
            
            # Performance and profitability
            if any(word in query.lower() for word in ['performance', 'profit', 'returns', 'win']):
                result = oracle.raw_query("""
                    SELECT 
                        COUNT(*) as evaluated_alerts,
                        AVG(max_profit_7day) as avg_7day_profit,
                        COUNT(CASE WHEN max_profit_7day > 0 THEN 1 END) as profitable_count
                    FROM flow_alerts 
                    WHERE max_profit_7day IS NOT NULL
                    AND DATE(alert_timestamp) >= DATE('now', '-30 days')
                """)
                if result.get('success') and result['results']:
                    context_parts.append(f"30-day performance metrics: {result['results'][0]}")
            
            # Volatility and market regime
            if any(word in query.lower() for word in ['volatility', 'vix', 'regime', 'market']):
                result = oracle.raw_query("""
                    SELECT date, market_direction, vix_close, spy_close
                    FROM market_daily_summary 
                    ORDER BY date DESC 
                    LIMIT 5
                """)
                if result.get('success'):
                    context_parts.append(f"Recent market regime data: {result['results']}")
            
            return "\n".join(context_parts) if context_parts else None
            
        except Exception as e:
            return f"Database query error: {e}"
    
    def pre_process_query(self, query):
        """Enhance query with data analysis focus"""
        return f"""Data Analysis Request: {query}

Please provide a data-driven analysis using actual database information where available. 
Include specific numbers, timeframes, and confidence levels based on the data quality."""
    
    def post_process_response(self, response):
        """Add data analyst signature"""
        if not response.endswith("📊"):
            response += "\n\n📊 Analysis based on actual trading database - Sarah Chen, Data Hawk"
        return response


# CLI Support
if __name__ == "__main__":
    main_cli(DataAwareTrader)