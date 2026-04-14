#!/usr/bin/env python3
"""
Process airline flow alerts into comprehensive JSON format
"""
import json
import re
from oracle_bridge import OracleBridge

def calculate_moneyness(strike, underlying, option_type):
    """Calculate option moneyness"""
    if option_type == 'call':
        return strike / underlying
    else:  # put
        return underlying / strike

def extract_multiplier_and_smart(alert_reason):
    """Extract volume multiplier and smart money indicator from alert reason"""
    vol_match = re.search(r'vol=([0-9.]+)x', alert_reason)
    smart_match = re.search(r'smart=([0-9.]+)', alert_reason)
    
    vol_multiplier = float(vol_match.group(1)) if vol_match else 0.0
    smart_indicator = float(smart_match.group(1)) if smart_match else 1.0
    
    return vol_multiplier, smart_indicator

def process_alerts():
    """Process all airline alerts data"""
    
    # Get all alerts data
    oracle = OracleBridge(silent=True)
    result = oracle.raw_query("""
        SELECT symbol, alert_timestamp, strike, option_type, implied_volatility, 
               delta, gamma, theta, days_to_expiration, volume, open_interest, 
               underlying_price, bid, ask, premium_value, alert_reason 
        FROM flow_alerts 
        WHERE symbol IN ('AAL', 'UAL', 'DAL', 'LUV') 
        ORDER BY alert_timestamp DESC
    """)
    
    if not result['success']:
        print("Error:", result['error'])
        return
    
    alerts_data = result['results']
    total_alerts = len(alerts_data)
    
    # Process each alert
    processed_alerts = []
    symbol_stats = {'AAL': [], 'UAL': [], 'DAL': [], 'LUV': []}
    type_counts = {'calls': 0, 'puts': 0}
    
    for alert in alerts_data:
        # Extract alert data
        vol_multiplier, smart_indicator = extract_multiplier_and_smart(alert['alert_reason'])
        
        # Calculate derived fields
        bid = alert['bid'] or 0
        ask = alert['ask'] or 0
        mid_price = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
        spread = ask - bid if (bid > 0 and ask > 0) else 0
        spread_percentage = (spread / mid_price) if mid_price > 0 else 0
        moneyness = calculate_moneyness(alert['strike'], alert['underlying_price'], alert['option_type'])
        
        processed_alert = {
            'symbol': alert['symbol'],
            'alert_timestamp': alert['alert_timestamp'],
            'strike': round(alert['strike'], 2),
            'option_type': alert['option_type'],
            'implied_volatility': round(alert['implied_volatility'], 4),
            'delta': round(alert['delta'], 4),
            'gamma': round(alert['gamma'], 4),
            'theta': round(alert['theta'], 4),
            'days_to_expiration': alert['days_to_expiration'],
            'volume': alert['volume'],
            'open_interest': alert['open_interest'],
            'underlying_price': round(alert['underlying_price'], 4),
            'bid': round(bid, 2),
            'ask': round(ask, 2),
            'mid_price': round(mid_price, 2),
            'premium_value': round(alert['premium_value'], 2),
            'moneyness': round(moneyness, 3),
            'bid_ask_spread': round(spread, 2),
            'spread_percentage': round(spread_percentage, 4),
            'alert_reason': alert['alert_reason'],
            'volume_multiplier': vol_multiplier,
            'smart_money_indicator': smart_indicator
        }
        
        processed_alerts.append(processed_alert)
        
        # Track statistics
        symbol_stats[alert['symbol']].append(alert)
        if alert['option_type'] == 'call':
            type_counts['calls'] += 1
        else:
            type_counts['puts'] += 1
    
    # Calculate statistics
    stats_by_symbol = {}
    for symbol, alerts in symbol_stats.items():
        if alerts:
            avg_premium = sum(a['premium_value'] for a in alerts) / len(alerts)
            avg_iv = sum(a['implied_volatility'] for a in alerts) / len(alerts) * 100
            stats_by_symbol[symbol] = {
                'count': len(alerts),
                'avg_premium': round(avg_premium, 2),
                'avg_iv': round(avg_iv, 2)
            }
        else:
            stats_by_symbol[symbol] = {
                'count': 0,
                'avg_premium': 0,
                'avg_iv': 0
            }
    
    # Find date range
    timestamps = [alert['alert_timestamp'] for alert in alerts_data]
    earliest = min(timestamps)
    latest = max(timestamps)
    
    # Build complete dataset
    complete_dataset = {
        'metadata': {
            'dataset_name': 'Comprehensive Airline Options Flow Alerts with Complete Pricing Data',
            'airlines': ['AAL', 'UAL', 'DAL', 'LUV'],
            'query_date': '2025-09-05',
            'total_alerts': total_alerts,
            'data_description': 'Complete options flow alerts for all four major airlines with bid/ask spreads, underlying prices, Greeks, volumes, and premium calculations',
            'key_columns': [
                'symbol', 'alert_timestamp', 'strike', 'option_type', 'implied_volatility',
                'delta', 'gamma', 'theta', 'days_to_expiration', 'volume', 'open_interest',
                'underlying_price', 'bid', 'ask', 'premium_value', 'alert_reason'
            ]
        },
        'alert_statistics': {
            'by_symbol': stats_by_symbol,
            'by_type': {
                'calls': {'count': type_counts['calls'], 'percentage': round(type_counts['calls']/total_alerts*100, 2)},
                'puts': {'count': type_counts['puts'], 'percentage': round(type_counts['puts']/total_alerts*100, 2)}
            },
            'date_range': {
                'earliest': earliest,
                'latest': latest
            }
        },
        'alerts': processed_alerts
    }
    
    # Save to file
    with open('E:/options_scanner/data/airline_thesis/airline-flow-alerts-complete.json', 'w') as f:
        json.dump(complete_dataset, f, indent=2)
    
    print(f"Processed {total_alerts} alerts successfully")
    print(f"Saved to airline-flow-alerts-complete.json")

if __name__ == '__main__':
    process_alerts()