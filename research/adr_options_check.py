#!/usr/bin/env python3
"""
ADR Options Availability Check
-------------------------------
Checks which major ADR symbols have options available on Tradier,
and pulls quote data (price, volume, market cap) for a full picture.

Output: CSV report of ADR candidates with options availability + metadata.
"""

import sys
import os
import csv
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tradier_api import TradierAPI, TradierDataClient

logging.basicConfig(level=logging.WARNING)

# All ~80 ADR candidates identified as missing from KLMN universe
ADR_CANDIDATES = {
    # Technology / Semiconductors
    'TSM': ('TSMC', 'Taiwan', 'Technology', 'Semiconductors'),
    'ASML': ('ASML Holding', 'Netherlands', 'Technology', 'Semiconductor Equipment'),
    'SAP': ('SAP SE', 'Germany', 'Technology', 'Enterprise Software'),
    'SHOP': ('Shopify', 'Canada', 'Technology', 'E-commerce Platform'),
    'INFY': ('Infosys', 'India', 'Technology', 'IT Services'),
    'WIT': ('Wipro', 'India', 'Technology', 'IT Services'),
    'WIX': ('Wix.com', 'Israel', 'Technology', 'Web Platform'),
    'GLOB': ('Globant', 'Argentina', 'Technology', 'IT Services'),

    # E-Commerce / Internet
    'BABA': ('Alibaba Group', 'China', 'Technology', 'E-commerce/Cloud'),
    'JD': ('JD.com', 'China', 'Consumer Cyclical', 'E-commerce'),
    'SE': ('Sea Limited', 'Singapore', 'Technology', 'E-commerce/Gaming'),
    'MELI': ('MercadoLibre', 'Argentina', 'Consumer Cyclical', 'E-commerce/Fintech'),
    'GRAB': ('Grab Holdings', 'Singapore', 'Technology', 'Ride-hail/Delivery'),
    'BIDU': ('Baidu', 'China', 'Technology', 'Search/AI'),
    'SPOT': ('Spotify', 'Sweden', 'Communication Services', 'Music Streaming'),
    'YUMC': ('Yum China', 'China', 'Consumer Cyclical', 'Restaurants'),

    # Pharma / Healthcare
    'NVO': ('Novo Nordisk', 'Denmark', 'Healthcare', 'Pharma - GLP-1/Obesity'),
    'NVS': ('Novartis', 'Switzerland', 'Healthcare', 'Pharma'),
    'GSK': ('GSK plc', 'UK', 'Healthcare', 'Pharma'),
    'SNY': ('Sanofi', 'France', 'Healthcare', 'Pharma'),
    'TAK': ('Takeda Pharmaceutical', 'Japan', 'Healthcare', 'Pharma'),
    'BGNE': ('BeiGene', 'China', 'Healthcare', 'Oncology Biotech'),
    'ARGX': ('argenx SE', 'Netherlands', 'Healthcare', 'Biotech - Autoimmune'),
    'LEGN': ('Legend Biotech', 'China', 'Healthcare', 'Cell Therapy'),

    # Energy
    'SHEL': ('Shell plc', 'UK/Netherlands', 'Energy', 'Integrated Oil & Gas'),
    'BP': ('BP plc', 'UK', 'Energy', 'Integrated Oil & Gas'),
    'TTE': ('TotalEnergies', 'France', 'Energy', 'Integrated Oil & Gas'),
    'PBR': ('Petrobras', 'Brazil', 'Energy', 'Oil & Gas'),
    'EC': ('Ecopetrol', 'Colombia', 'Energy', 'Oil & Gas'),
    'YPF': ('YPF SA', 'Argentina', 'Energy', 'Oil & Gas'),
    'EQNR': ('Equinor', 'Norway', 'Energy', 'Oil & Gas'),
    'E': ('Eni SpA', 'Italy', 'Energy', 'Oil & Gas'),
    'SU': ('Suncor Energy', 'Canada', 'Energy', 'Oil Sands'),
    'CNQ': ('Canadian Natural Resources', 'Canada', 'Energy', 'Oil & Gas'),
    'TRP': ('TC Energy', 'Canada', 'Energy', 'Pipelines/Midstream'),

    # Mining / Materials
    'VALE': ('Vale SA', 'Brazil', 'Basic Materials', 'Iron Ore/Mining'),
    'RIO': ('Rio Tinto', 'UK/Australia', 'Basic Materials', 'Diversified Mining'),
    'BHP': ('BHP Group', 'Australia', 'Basic Materials', 'Diversified Mining'),
    'GOLD': ('Barrick Gold', 'Canada', 'Basic Materials', 'Gold Mining'),
    'VEDL': ('Vedanta Limited', 'India', 'Basic Materials', 'Diversified Mining'),
    'AU': ('AngloGold Ashanti', 'South Africa', 'Basic Materials', 'Gold Mining'),
    'WPM': ('Wheaton Precious Metals', 'Canada', 'Basic Materials', 'Precious Metals Streaming'),
    'AEM': ('Agnico Eagle Mines', 'Canada', 'Basic Materials', 'Gold Mining'),
    'FNV': ('Franco-Nevada', 'Canada', 'Basic Materials', 'Precious Metals Royalties'),
    'TECK': ('Teck Resources', 'Canada', 'Basic Materials', 'Diversified Mining'),

    # Financials
    'UBS': ('UBS Group', 'Switzerland', 'Financial Services', 'Investment Banking'),
    'DB': ('Deutsche Bank', 'Germany', 'Financial Services', 'Banking'),
    'MUFG': ('Mitsubishi UFJ Financial', 'Japan', 'Financial Services', 'Banking'),
    'SMFG': ('Sumitomo Mitsui Financial', 'Japan', 'Financial Services', 'Banking'),
    'ING': ('ING Group', 'Netherlands', 'Financial Services', 'Banking'),
    'BBVA': ('Banco Bilbao Vizcaya', 'Spain', 'Financial Services', 'Banking'),
    'SAN': ('Banco Santander', 'Spain', 'Financial Services', 'Banking'),
    'MFG': ('Mizuho Financial', 'Japan', 'Financial Services', 'Banking'),
    'KB': ('KB Financial', 'South Korea', 'Financial Services', 'Banking'),
    'HDB': ('HDFC Bank', 'India', 'Financial Services', 'Banking'),
    'IBN': ('ICICI Bank', 'India', 'Financial Services', 'Banking'),
    'ITUB': ('Itau Unibanco', 'Brazil', 'Financial Services', 'Banking'),

    # Consumer / Retail
    'UL': ('Unilever', 'UK/Netherlands', 'Consumer Defensive', 'Consumer Staples'),
    'DEO': ('Diageo', 'UK', 'Consumer Defensive', 'Beverages - Spirits'),
    'AMX': ('America Movil', 'Mexico', 'Communication Services', 'Telecom'),
    'BTI': ('British American Tobacco', 'UK', 'Consumer Defensive', 'Tobacco'),
    'TD': ('Toronto-Dominion Bank', 'Canada', 'Financial Services', 'Banking'),

    # Automotive / EV
    'TM': ('Toyota Motor', 'Japan', 'Consumer Cyclical', 'Automotive'),
    'HMC': ('Honda Motor', 'Japan', 'Consumer Cyclical', 'Automotive'),
    'NIO': ('NIO Inc', 'China', 'Consumer Cyclical', 'Electric Vehicles'),
    'LI': ('Li Auto', 'China', 'Consumer Cyclical', 'Electric Vehicles'),
    'XPEV': ('XPeng', 'China', 'Consumer Cyclical', 'Electric Vehicles'),
    'STLA': ('Stellantis', 'Netherlands', 'Consumer Cyclical', 'Automotive'),

    # Telecom / Media
    'TEF': ('Telefonica', 'Spain', 'Communication Services', 'Telecom'),
    'ERIC': ('Ericsson', 'Sweden', 'Technology', 'Telecom Equipment'),
    'NOK': ('Nokia', 'Finland', 'Technology', 'Telecom Equipment'),

    # Other Notable
    'WDS': ('Woodside Energy', 'Australia', 'Energy', 'LNG'),
    'FLUT': ('Flutter Entertainment', 'Ireland', 'Consumer Cyclical', 'Sports Betting'),
    'BAM': ('Brookfield Asset Management', 'Canada', 'Financial Services', 'Asset Management'),
    'BN': ('Brookfield Corporation', 'Canada', 'Financial Services', 'Asset Management'),
    'CSAN': ('Cosan', 'Brazil', 'Energy', 'Energy/Logistics'),
    'ABEV': ('Ambev', 'Brazil', 'Consumer Defensive', 'Beverages'),
    'SQM': ('Sociedad Quimica y Minera', 'Chile', 'Basic Materials', 'Lithium/Chemicals'),
}

def main():
    print(f"Checking {len(ADR_CANDIDATES)} ADR candidates for options availability on Tradier...")
    print()

    import json
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')
    with open(config_path) as f:
        config = json.load(f)
    token = config['tradier']['api_key']
    api = TradierAPI(token)

    # Get quotes for all symbols in one batch call
    all_symbols = list(ADR_CANDIDATES.keys())
    print(f"Fetching quotes for {len(all_symbols)} symbols...")
    quotes_response = api.get_quotes(','.join(all_symbols))

    # Parse quotes into dict
    quotes = {}
    if quotes_response and 'quotes' in quotes_response:
        quote_data = quotes_response['quotes']
        if 'quote' in quote_data:
            q_list = quote_data['quote']
            if isinstance(q_list, dict):
                q_list = [q_list]
            for q in q_list:
                sym = q.get('symbol', '')
                quotes[sym] = q
        # Also capture unmatched symbols
        if 'unmatched_symbols' in quote_data:
            unmatched = quote_data['unmatched_symbols']
            if isinstance(unmatched, dict) and 'symbol' in unmatched:
                um = unmatched['symbol']
                if isinstance(um, str):
                    um = [um]
                for s in um:
                    quotes[s] = None  # Mark as not found

    print(f"Got quotes for {len([v for v in quotes.values() if v is not None])} symbols")
    print()

    # Check option expirations for each symbol that has a valid quote
    results = []
    has_options_count = 0
    no_options_count = 0
    no_quote_count = 0

    for i, (symbol, (name, country, sector, industry)) in enumerate(sorted(ADR_CANDIDATES.items())):
        quote = quotes.get(symbol)

        if quote is None:
            print(f"  [{i+1}/{len(ADR_CANDIDATES)}] {symbol:6s} - NO QUOTE (not found on Tradier)")
            no_quote_count += 1
            results.append({
                'symbol': symbol,
                'name': name,
                'country': country,
                'sector': sector,
                'industry': industry,
                'has_quote': False,
                'has_options': False,
                'price': None,
                'avg_volume': None,
                'week_52_high': None,
                'week_52_low': None,
                'num_expirations': 0,
            })
            continue

        price = quote.get('last', quote.get('close', 0))
        avg_vol = quote.get('average_volume', 0)
        w52_high = quote.get('week_52_high', 0)
        w52_low = quote.get('week_52_low', 0)

        # Check options availability
        exp_response = api.get_option_expirations(symbol)
        has_options = False
        num_exp = 0

        if exp_response and 'expirations' in exp_response:
            exp_data = exp_response['expirations']
            if exp_data and 'date' in exp_data:
                dates = exp_data['date']
                if isinstance(dates, list):
                    num_exp = len(dates)
                elif isinstance(dates, str):
                    num_exp = 1
                has_options = num_exp > 0

        status = f"OPTIONS ({num_exp} exp)" if has_options else "NO OPTIONS"
        print(f"  [{i+1}/{len(ADR_CANDIDATES)}] {symbol:6s} ${price:>8.2f}  vol={avg_vol:>12,}  {status}")

        if has_options:
            has_options_count += 1
        else:
            no_options_count += 1

        results.append({
            'symbol': symbol,
            'name': name,
            'country': country,
            'sector': sector,
            'industry': industry,
            'has_quote': True,
            'has_options': has_options,
            'price': price,
            'avg_volume': avg_vol,
            'week_52_high': w52_high,
            'week_52_low': w52_low,
            'num_expirations': num_exp,
        })

        time.sleep(0.5)  # Rate limit courtesy

    # Write CSV
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               'docs', 'output', 'reports', 'adr_candidates_2026-03-12.csv')

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Symbol', 'Company', 'Country', 'Sector', 'Industry',
                         'Has Quote', 'Has Options', 'Price', 'Avg Volume',
                         '52w High', '52w Low', 'Num Expirations'])

        for r in sorted(results, key=lambda x: (not x['has_options'], x['sector'], x['symbol'])):
            writer.writerow([
                r['symbol'], r['name'], r['country'], r['sector'], r['industry'],
                r['has_quote'], r['has_options'],
                f"{r['price']:.2f}" if r['price'] else '',
                r['avg_volume'] or '',
                f"{r['week_52_high']:.2f}" if r['week_52_high'] else '',
                f"{r['week_52_low']:.2f}" if r['week_52_low'] else '',
                r['num_expirations'],
            ])

    print()
    print(f"{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Total candidates checked:  {len(ADR_CANDIDATES)}")
    print(f"  Has options on Tradier:    {has_options_count}")
    print(f"  No options available:      {no_options_count}")
    print(f"  No quote (not on Tradier): {no_quote_count}")
    print(f"  Report saved to: {output_path}")


if __name__ == '__main__':
    main()
