#!/usr/bin/env python3
"""
Extract raw option contract data for AAL spikes
"""
import csv
from oracle_bridge import OracleBridge
from datetime import datetime, timedelta

def extract_spike_option_data():
    """Extract raw option data around major AAL spikes"""
    
    oracle = OracleBridge(silent=True)
    
    # Define spike periods with target dates
    spike_periods = {
        'august_12_2025': {
            'spike_date': '2025-08-12',
            'lookback_start': '2025-07-28',  # Available data starts here
            'lookback_end': '2025-08-20'
        },
        'august_22_2025': {
            'spike_date': '2025-08-22', 
            'lookback_start': '2025-08-01',
            'lookback_end': '2025-08-30'
        }
    }
    
    # Target strikes (ATM ±2 based on analysis)
    target_strikes = [11, 12, 13, 14]
    
    all_data = []
    
    for period_name, period_data in spike_periods.items():
        print(f"Processing {period_name}...")
        
        # Query raw option data
        query = f"""
        SELECT trade_date, strike, option_type, expiration_date,
               bid, ask, implied_volatility, delta, gamma, theta,
               volume, open_interest, underlying_price
        FROM flow_options_scans
        WHERE symbol = 'AAL' 
        AND strike IN ({','.join(map(str, target_strikes))})
        AND trade_date BETWEEN '{period_data['lookback_start']}' AND '{period_data['lookback_end']}'
        AND expiration_date >= '{period_data['spike_date']}'
        ORDER BY trade_date, strike, option_type, expiration_date
        """
        
        result = oracle.raw_query(query)
        
        if result['success']:
            for row in result['results']:
                # Add period identifier and calculated fields
                row['spike_period'] = period_name
                row['spike_date'] = period_data['spike_date']
                row['days_to_spike'] = (datetime.strptime(period_data['spike_date'], '%Y-%m-%d') - 
                                       datetime.strptime(row['trade_date'], '%Y-%m-%d')).days
                
                # Calculate mid price and spread
                bid = row['bid'] or 0
                ask = row['ask'] or 0
                row['mid_price'] = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
                row['bid_ask_spread'] = ask - bid if (bid > 0 and ask > 0) else 0
                row['spread_pct'] = (row['bid_ask_spread'] / row['mid_price']) if row['mid_price'] > 0 else 0
                
                # Calculate moneyness
                if row['option_type'] == 'call':
                    row['moneyness'] = row['strike'] / row['underlying_price']
                else:
                    row['moneyness'] = row['underlying_price'] / row['strike']
                
                all_data.append(row)
                
            print(f"  Extracted {len(result['results'])} option records")
        else:
            print(f"  Error: {result['error']}")
    
    # Save to CSV
    if all_data:
        csv_file = 'E:/options_scanner/data/airline_thesis/aal-raw-option-data.csv'
        
        fieldnames = [
            'spike_period', 'spike_date', 'days_to_spike',
            'trade_date', 'strike', 'option_type', 'expiration_date',
            'bid', 'ask', 'mid_price', 'bid_ask_spread', 'spread_pct',
            'implied_volatility', 'delta', 'gamma', 'theta',
            'volume', 'open_interest', 'underlying_price', 'moneyness'
        ]
        
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in all_data:
                # Round numeric fields
                for field in ['bid', 'ask', 'mid_price', 'bid_ask_spread', 'spread_pct', 
                             'implied_volatility', 'delta', 'gamma', 'theta', 'underlying_price', 'moneyness']:
                    if row[field] is not None:
                        row[field] = round(float(row[field]), 4)
                
                writer.writerow(row)
        
        print(f"\n✅ SUCCESS: Saved {len(all_data)} option records to aal-raw-option-data.csv")
        return len(all_data)
    else:
        print("❌ No data extracted")
        return 0

if __name__ == '__main__':
    total_records = extract_spike_option_data()
    print(f"\nFinal result: {total_records} total option records extracted")