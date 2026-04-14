#!/usr/bin/env python3
"""
Symbol Universe Repository (symbols_klmn800.py)
------------------------------------------------
Curated ~820-symbol universe organized by PURPOSE, not source.

Two main blocks:
  - FM_UNIVERSE: ~388 symbols scanned by ALL strategies including Flow Monitor intraday
  - DAILY_ONLY:  ~432 symbols scanned by Option Pipeline + Earnings Intel, NOT Flow Monitor

Combined as KLMN_800_SYMBOLS (~820 total) for backwards compatibility.

Special groups (ETFs, Airlines, ADRs) are maintained separately for strategies
that need them. All special group symbols are included in FM_UNIVERSE.

FM Universe Classification (2026-03-16):
  - Protected groups (ETFs, ADRs, Airlines) -> always in FM
  - Symbols with flow alert history (Sep 2025 - Mar 2026) -> in FM if <$300
  - Cherry-picked symbols (high options volume or thematic value) -> always in FM
  - Everything else -> DAILY_ONLY (still tracked by OP and EI, just not FM intraday)

To refresh the classification, re-run the analysis from the March 16, 2026 session
using flow_alerts from query DB + sector archives, latest prices from historical_prices,
and the protected/cherry-pick rules documented below.

Author: Ben (with assistance from Claude)
Date: 2025-06-07 (Reorganized 2026-03-16: source-based -> purpose-based grouping)
"""

# =============================================================================
# FM UNIVERSE — Scanned by all strategies including Flow Monitor intraday
# =============================================================================
# ~388 symbols: alert history + protected groups + cherry picks
# These are the symbols FM monitors for unusual intraday options flow.
# Trimmed 2026-03-16: removed 48 symbols in $150-300 range (expensive premiums)
# and 19 ETFs (regime data uses its own Tradier calls, not FM). JETS kept for Airline Play.

FM_UNIVERSE = [
    'AA', 'AAL', 'AAP', 'ABNB', 'ABT', 'ACI', 'ADM', 'AEM',
    'AEP', 'AES', 'AFRM', 'AGNC', 'AKAM', 'ALAB', 'ALB', 'ALK', 'ALLY',
    'AMD', 'AMX', 'AMZN', 'ANET', 'APH', 'APO', 'AR', 'ARGX', 'ARM',
    'AS', 'ASML', 'AU', 'AVTR', 'AZN', 'B', 'BA', 'BABA', 'BAC', 'BAH',
    'BAM', 'BAX', 'BBVA', 'BBWI', 'BBY', 'BG', 'BHP', 'BIDU', 'BILL',
    'BJ', 'BKR', 'BMY', 'BN', 'BP', 'BRBR', 'BROS', 'BSX', 'BTI',
    'BWA', 'BWXT', 'BX', 'BYD', 'C', 'CAG', 'CAR', 'CARR', 'CART',
    'CAVA', 'CC', 'CCJ', 'CCL', 'CDW', 'CE', 'CELH', 'CF', 'CFG',
    'CHTR', 'CLF', 'CMCSA', 'CMG', 'CNC', 'CNM', 'CNQ', 'CNXC',
    'COIN', 'COP', 'COTY', 'CPNG', 'CPRI', 'CRH', 'CRM', 'CROX', 'CSCO',
    'CSGP', 'CSX', 'CTRA', 'CVS', 'CVX', 'CZR', 'DAL', 'DAR', 'DASH',
    'DB', 'DD', 'DDOG', 'DECK', 'DELL', 'DEO', 'DG', 'DHI', 'DINO',
    'DIS', 'DKNG', 'DLTR', 'DNN', 'DOCS', 'DOCU', 'DOW', 'DT', 'DUK',
    'DVN', 'DXC', 'DXCM', 'E', 'EBAY', 'EC', 'EIX', 'EL', 'ELF',
    'EMN', 'EMR', 'ENPH', 'ENTG', 'EOG', 'EQNR', 'EQT', 'ERIC', 'ET',
    'ETSY', 'EW', 'EXE', 'EXEL', 'F', 'FBIN', 'FCX', 'FE', 'FHN',
    'FIS', 'FISV', 'FIVN', 'FLR', 'FLUT', 'FNB', 'FND', 'FNV', 'FOUR',
    'FSLR', 'FTNT', 'GAP', 'GDDY', 'GFS', 'GILD', 'GLOB', 'GLW', 'GM',
    'GME', 'GMED', 'GO', 'GOLD', 'GPC', 'GRAB', 'GRAL', 'GSK', 'GTES',
    'GTLB', 'GTM', 'GXO', 'HAL', 'HAS', 'HDB', 'HMC', 'HOG', 'HOOD',
    'HPE', 'HPQ', 'HUN', 'IBM', 'IBN', 'IFF', 'INFY', 'ING', 'INSP',
    'INTC', 'IP', 'ITUB', 'JBLU', 'JCI', 'JD', 'JEF', 'JETS', 'JNJ',
    'KB', 'KD', 'KDP', 'KEY', 'KHC', 'KKR', 'KMB', 'KMI', 'KMX',
    'KNX', 'KO', 'KR', 'KSS', 'KVUE', 'LCID', 'LEGN', 'LI', 'LNC',
    'LRCX', 'LSCC', 'LULU', 'LUV', 'LVS', 'LW', 'LYB', 'LYFT', 'M',
    'MAT', 'MCHP', 'MDT', 'MELI', 'MET', 'MFG', 'MGM', 'MHK', 'MMM',
    'MO', 'MOH', 'MOS', 'MP', 'MPT', 'MRK', 'MRNA', 'MRVL', 'MSTR',
    'MTCH', 'MTN', 'MUFG', 'NCLH', 'NEM', 'NFLX', 'NIO', 'NKE', 'NLY', 'NNE',
    'NOK', 'NRG', 'NTAP', 'NU', 'NVDA', 'NVO', 'NVS', 'NVT', 'NXE',
    'OKE', 'OKLO', 'OKTA', 'OLN', 'OMF', 'ON', 'ORCL', 'ORLY', 'OWL',
    'OXY', 'PANW', 'PATH', 'PAYC', 'PAYX', 'PBR', 'PCG', 'PCOR', 'PDD',
    'PENN', 'PEP', 'PFE', 'PINS', 'PLTR', 'PPL', 'PSN', 'PSTG', 'PYPL',
    'QCOM', 'QRVO', 'QS', 'RBLX', 'RCL', 'RGEN', 'RIO', 'RIVN', 'RKT',
    'ROKU', 'RRC', 'RTX', 'S', 'SAN', 'SAP', 'SBUX', 'SCCO', 'SCHW',
    'SE', 'SGI', 'SHEL', 'SHOP', 'SIRI', 'SJM', 'SLB', 'SMCI', 'SMFG',
    'SMR', 'SN', 'SNOW', 'SNY', 'SO', 'SOFI', 'SPOT', 'SQM', 'SRPT',
    'STLA', 'STT', 'STZ', 'SU', 'SWKS', 'SYF', 'SYY', 'T', 'TAK',
    'TD', 'TECK', 'TFC', 'TGT', 'TM', 'TOL', 'TOST', 'TRP', 'TSCO',
    'TSM', 'TSN', 'TTD', 'TTE', 'U', 'UAL', 'UBER', 'UBS', 'UEC',
    'UL', 'UNH', 'UPS', 'USB', 'UUUU', 'UWMC', 'VALE', 'VFC', 'VKTX',
    'VRT', 'VST', 'VZ', 'W', 'WBD', 'WDAY', 'WDS', 'WFC', 'WIT',
    'WIX', 'WLK', 'WMB', 'WMT', 'WOLF', 'WPM', 'WULF', 'WYNN', 'XOM',
    'XP', 'XPEV', 'XYZ', 'YETI', 'YPF', 'YUMC', 'Z', 'ZBH', 'ZM',
    'ZTS',
]

# =============================================================================
# DAILY ONLY — Scanned by Option Pipeline + Earnings Intel, NOT Flow Monitor
# =============================================================================
# ~432 symbols: never-alerted, expensive premiums ($150-300), $300+, or non-JETS ETFs.
# Still get full daily OI/IV/earnings
# coverage — just not intraday FM scanning.
#
# These symbols can be moved to FM_UNIVERSE if:
#   - They start generating flow alerts after being added to FM
#   - Peer-propagation research identifies them as bellwether signal sources
#   - Price drops into tradeable range
#   - You just want to track them more closely

DAILY_ONLY = [
    'A', 'AAON', 'AAPL', 'ABBV', 'ACGL', 'ACM', 'ACN', 'ADBE', 'ADC',
    'ADI', 'ADP', 'ADSK', 'ADT', 'AEE', 'AFL', 'AIG', 'AJG',
    'ALGM', 'ALGN', 'ALL', 'AM', 'AMAT', 'AMCR', 'AME', 'AMGN', 'AMT',
    'AMTM', 'AON', 'AOS', 'APA', 'APD', 'APLS', 'APP', 'APTV', 'ARE',
    'ARMK', 'ATI', 'ATO', 'AVB', 'AVGO', 'AWK', 'AXP', 'AXS', 'AXTA',
    'BALL', 'BC', 'BDX', 'BEN', 'BEPC', 'BIIB', 'BK', 'BLDR', 'BMRN',
    'BPOP', 'BR', 'BRKR', 'BRO', 'BSY', 'BXP', 'CAH', 'CAT', 'CB',
    'CBOE', 'CBRE', 'CCC', 'CCEP', 'CCI', 'CCK', 'CDNS', 'CEG', 'CG',
    'CGNX', 'CHD', 'CHRD', 'CHRW', 'CI', 'CIEN', 'CINF', 'CL', 'CLX',
    'CME', 'CMI', 'CNH', 'CNP', 'COF', 'COHR', 'COKE', 'COLD', 'COO',
    'COR', 'CPB', 'CPRT', 'CRI', 'CRL', 'CRWD', 'CTAS', 'CTSH', 'CTVA',
    'CUBE', 'D', 'DBX', 'DE', 'DGX', 'DHR', 'DIA', 'DLR', 'DOC',
    'DOV', 'DPZ', 'DRI', 'DTE', 'DV', 'DVA', 'EA', 'ECL', 'ED',
    'EFX', 'EG', 'ELAN', 'ELV', 'ENOV', 'EPAM', 'EQH', 'EQR', 'ES',
    'ETN', 'ETR', 'EVRG', 'EWBC', 'EXC', 'EXPD', 'EXPE', 'EXR',
    'FAF', 'FANG', 'FAST', 'FDS', 'FDX', 'FERG', 'FFIV', 'FITB', 'FIVE',
    'FLO', 'FLS', 'FMC', 'FOX', 'FOXA', 'FRPT', 'FRT', 'FTI', 'FTV',
    'G', 'GD', 'GE', 'GEHC', 'GEN', 'GEV', 'GIS', 'GL', 'GNRC',
    'GNTX', 'GOOG', 'GOOGL', 'GPK', 'GPN', 'GRMN', 'GWRE', 'H', 'HAYW',
    'HBAN', 'HCA', 'HD', 'HIG', 'HII', 'HLT', 'HON', 'HRB',
    'HRL', 'HSIC', 'HST', 'HSY', 'HUBB', 'HUM', 'HWM', 'IAC', 'ICE',
    'IDXX', 'ILMN', 'INCY', 'INVH', 'IQV', 'IR', 'IRDM', 'IRM', 'ISRG',
    'IT', 'ITW', 'IVES', 'IVZ', 'IWM', 'JBHT', 'JBL', 'JHG', 'JKHY',
    'JPM', 'KBR', 'KEYS', 'L', 'LAZ', 'LDOS', 'LEG', 'LEN', 'LEU',
    'LH', 'LHX', 'LII', 'LIN', 'LINE', 'LKQ', 'LMT', 'LNG', 'LOAR',
    'LOW', 'LPX', 'LYV', 'MA', 'MAA', 'MAN', 'MAR', 'MAS', 'MCD',
    'MCO', 'MDB', 'MDLZ', 'META', 'MIDD', 'MKC', 'MKSI', 'MKTX', 'MLM',
    'MNST', 'MPC', 'MRP', 'MRSH', 'MS', 'MSCI', 'MSFT', 'MSI', 'MTB',
    'MU', 'NCNO', 'NDAQ', 'NEE', 'NET', 'NI', 'NLR', 'NNN', 'NOC',
    'NOV', 'NSC', 'NTNX', 'NTRA', 'NTRS', 'NUE', 'NVST', 'NWL', 'NXPI',
    'O', 'OC', 'ODFL', 'OGN', 'OHI', 'OMC', 'ONTO', 'ORI', 'OSK',
    'OTIS', 'OVV', 'PCAR', 'PEG', 'PEGA', 'PFGC', 'PG', 'PGR', 'PHM',
    'PII', 'PK', 'PKG', 'PLD', 'PM', 'PNC', 'PNR', 'PODD', 'POOL',
    'PPG', 'PR', 'PRU', 'PSA', 'PSX', 'PTC', 'PVH', 'PWR', 'QDEL',
    'QQQ', 'RBA', 'REG', 'REGN', 'REXR', 'RF', 'RHI', 'RITM', 'RJF',
    'RL', 'RMD', 'RNG', 'ROK', 'ROL', 'ROST', 'RPRX', 'RRX', 'RSG',
    'RVTY', 'RYN', 'SARO', 'SBAC', 'SCI', 'SF', 'SHW', 'SLM',
    'SNA', 'SNDK', 'SNPS', 'SOLV', 'SPG', 'SPGI', 'SPY', 'SRE', 'SSNC',
    'ST', 'STAG', 'STE', 'STLD', 'STX', 'SW', 'SWK', 'SYK', 'TAP',
    'TDC', 'TECH', 'TEL', 'TER', 'THC', 'TJX', 'TKO', 'TMO', 'TMUS',
    'TPG', 'TPR', 'TRGP', 'TRMB', 'TROW', 'TRU', 'TRV', 'TSLA', 'TT',
    'TTC', 'TTEK', 'TTWO', 'TW', 'TXG', 'TXN', 'TXT', 'UA', 'UDR',
    'UGI', 'UHS', 'ULTA', 'UNM', 'UNP', 'URA', 'URNM', 'V', 'VEEV',
    'VICI', 'VIX', 'VLO', 'VLTO', 'VMC', 'VNOM', 'VRSK', 'VRSN', 'VRTX',
    'VTR', 'VTRS', 'VVV', 'WAL', 'WAT', 'WBS', 'WDC', 'WEC', 'WELL',
    'WH', 'WHR', 'WM', 'WMS', 'WRB', 'WSC', 'WSM', 'WST', 'WY',
    'XEL', 'XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU',
    'XLV', 'XLY', 'XPO', 'XRAY', 'XYL', 'YUM', 'ZBRA', 'ZION', 'ZS',
]

# =============================================================================
# SPECIAL PURPOSE GROUPS — Used by specific strategies
# =============================================================================
# These symbols also appear in FM_UNIVERSE (all are protected).
# Kept as separate lists for strategies that need targeted access.

# Airline Industry Tracking (Airline Play Strategy)
# Purpose: Lock-step volatility pattern analysis for airline stocks
AIRLINE_PLAY_SYMBOLS = [
    # Primary: Lock-step pattern airlines (move together)
    'DAL', 'UAL', 'AAL',
    # Secondary: Related airlines (less correlated)
    'LUV', 'JBLU', 'ALK',
    # Airline ETF (sector exposure)
    'JETS',
]

# ETF additions for market signal and sector exposure
ETF_SYMBOLS = [
    'SPY', 'QQQ', 'IWM', 'DIA',  # Core indices
    'XLF', 'XLK', 'XLE', 'XLV', 'XLI', 'XLU', 'XLP', 'XLY', 'XLB', 'XLRE',  # Sectors
    'VIX', # For intra-day market activity reports
    'IVES', 'NLR', 'URA', 'URNM', # Industries (JETS in AIRLINE_PLAY_SYMBOLS)
]

# ADR / Foreign-Listed symbols with US options (added 2026-03-12)
# Signal sources for sector sympathy, earnings ripple effects, and peer network coverage.
# Many are too expensive to trade directly but their earnings move domestic peers.
KLMN_ADR_COMPONENT = [
    # Technology / Semiconductors
    'ASML', 'INFY', 'SAP', 'SHOP', 'TSM', 'WIT', 'WIX', 'GLOB',
    # E-Commerce / Internet / Platforms
    'BABA', 'BIDU', 'GRAB', 'JD', 'MELI', 'SE', 'SPOT', 'YUMC',
    # Pharma / Healthcare / Biotech
    'ARGX', 'GSK', 'LEGN', 'NVO', 'NVS', 'SNY', 'TAK',
    # Energy
    'BP', 'CNQ', 'E', 'EC', 'EQNR', 'PBR', 'SHEL', 'SU', 'TRP', 'TTE',
    # Mining / Materials
    'AEM', 'AU', 'BHP', 'FNV', 'GOLD', 'RIO', 'SQM', 'TECK', 'VALE', 'WPM',
    # Financials
    'BAM', 'BBVA', 'BN', 'DB', 'HDB', 'IBN', 'ING', 'ITUB', 'KB',
    'MFG', 'MUFG', 'SAN', 'SMFG', 'TD', 'UBS',
    # Consumer / Retail / Telecom
    'AMX', 'BTI', 'DEO', 'UL',
    # Automotive / EV
    'HMC', 'LI', 'NIO', 'STLA', 'TM', 'XPEV',
    # Other
    'ERIC', 'FLUT', 'NOK', 'WDS', 'YPF',
]

# Cherry picks: never-alerted symbols kept in FM for volume/thematic reasons (2026-03-16)
# These are documented here so the reasoning is preserved for future pruning sessions.
FM_CHERRY_PICKS = [
    'DIS', 'ET', 'MO', 'ABT', 'S', 'AKAM',      # High daily options volume
    'PENN', 'ELF', 'DOCU', 'ALLY',                 # Thematic (gambling, beauty, SaaS, fintech)
    'AGNC', 'NLY', 'MPT', 'CC',                    # Cheap + very liquid options markets
    'DNN', 'BWXT',                                   # Nuclear energy / defense crossover
]

# =============================================================================
# COMBINED UNIVERSE (backwards compatible)
# =============================================================================
# This is what Option Pipeline, Earnings Intel, and other full-universe
# consumers use. FM uses FM_UNIVERSE (via get_specialty_list('fm_scan')).

KLMN_800_SYMBOLS = FM_UNIVERSE + DAILY_ONLY

'''
Low Liquidity purgatory to be re-evaluated at some undetermined point.
Based on low average and max volume in June / July 2025

'ABEV' — options consistently fail to meet OI/volume requirements (April 2026)
'AFG', 'AIZ', 'ALLE', 'AMH', 'AMP', 'ANGI', 'APG',
'AVY', 'AZEK', 'AZTA', 'BRX', 'CERT', 'CMS', 'CPAY',
'CPT', 'CUZ', 'CWEN', 'DNB', 'DTM', 'ERIE', 'ESI',
'ESS', 'FR', 'FTRE', 'FYBR', 'FHB', 'GGG', 'HR', 'HXL',
'IEX', 'INFA', 'J', 'KIM', 'KRC', 'LEA', 'LNT', 'MDU',
'MTD', 'MTG', 'NDSN', 'NWS', 'NWSA', 'OGE', 'PFG', 'PINC',
'PNW', 'REYN', 'ROP', 'RPM', 'SHC', 'SPR', 'TDY', 'TYL',
'VNT', 'WAB', 'WTRG', 'WTW'
'''


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_specialty_list(list_name):
    """
    Get specialty symbol list by name.

    Args:
        list_name (str): Name of the specialty list to retrieve

    Returns:
        list: List of symbols for the specified specialty list

    Available specialty lists:
        - 'klmn_800': Full ~820-symbol universe (OP, EI, metadata, etc.)
        - 'fm_scan': FM scan universe (~454 symbols with alert history/protection)
        - 'fm_cherry_picks': Cherry-picked symbols kept in FM for volume/thematic reasons
        - 'daily_only': Symbols tracked by OP/EI but not FM
        - 'klmn_adr': ADR / foreign-listed symbols with US options
        - 'airline_play': Airline industry tracking symbols
        - 'etf': ETF symbols for market/sector exposure
    """
    specialty_lists = {
        'klmn_800': KLMN_800_SYMBOLS,
        'fm_scan': FM_UNIVERSE,
        'fm_cherry_picks': FM_CHERRY_PICKS,
        'daily_only': DAILY_ONLY,
        'klmn_adr': KLMN_ADR_COMPONENT,
        'airline_play': AIRLINE_PLAY_SYMBOLS,
        'etf': ETF_SYMBOLS,
    }

    list_key = list_name.lower()
    if list_key not in specialty_lists:
        available = ', '.join(specialty_lists.keys())
        raise ValueError(f"Unknown specialty list '{list_name}'. Available: {available}")

    return specialty_lists[list_key]


def get_specialty_info():
    """
    Get information about available specialty symbol lists.

    Returns:
        dict: Dictionary with list names as keys and symbol counts as values
    """
    return {
        'klmn_800': len(KLMN_800_SYMBOLS),
        'fm_scan': len(FM_UNIVERSE),
        'fm_cherry_picks': len(FM_CHERRY_PICKS),
        'daily_only': len(DAILY_ONLY),
        'klmn_adr': len(KLMN_ADR_COMPONENT),
        'airline_play': len(AIRLINE_PLAY_SYMBOLS),
        'etf': len(ETF_SYMBOLS),
    }


def get_available_specialty_lists():
    """
    Get list of available specialty list names.

    Returns:
        list: List of available specialty list names
    """
    return ['klmn_800', 'fm_scan', 'fm_cherry_picks', 'daily_only', 'klmn_adr', 'airline_play', 'etf']


def validate_specialty_symbols(symbols, list_name='klmn_800'):
    """
    Validate that symbols exist in the specified specialty list.

    Args:
        symbols (list): List of symbols to validate
        list_name (str): Specialty list to validate against

    Returns:
        tuple: (valid_symbols, invalid_symbols)
    """
    specialty_symbols = set(get_specialty_list(list_name))
    symbols_set = set(symbols)

    valid_symbols = list(symbols_set.intersection(specialty_symbols))
    invalid_symbols = list(symbols_set.difference(specialty_symbols))

    return valid_symbols, invalid_symbols


def get_klmn_800_breakdown():
    """
    Get breakdown of KLMN 800 components.

    Returns:
        dict: Breakdown showing FM Universe vs Daily Only
    """
    return {
        'total_symbols': len(KLMN_800_SYMBOLS),
        'fm_universe': len(FM_UNIVERSE),
        'daily_only': len(DAILY_ONLY),
        'etf_count': len(ETF_SYMBOLS),
        'airline_count': len(AIRLINE_PLAY_SYMBOLS),
        'adr_count': len(KLMN_ADR_COMPONENT),
        'cherry_pick_count': len(FM_CHERRY_PICKS),
        'composition': f"{len(FM_UNIVERSE)} FM Universe + {len(DAILY_ONLY)} Daily Only",
    }


def get_symbol_count(list_name):
    """
    Get count of symbols in specified specialty list.

    Args:
        list_name (str): Name of the specialty list

    Returns:
        int: Number of symbols in the specialty list
    """
    return len(get_specialty_list(list_name))


def is_symbol_in_klmn_800(symbol):
    """
    Check if symbol is in the KLMN 800 universe.

    Args:
        symbol (str): Symbol to check

    Returns:
        bool: True if symbol is in KLMN 800, False otherwise
    """
    return symbol.upper() in KLMN_800_SYMBOLS


# Usage examples for testing
if __name__ == "__main__":
    print("Symbol Universe Repository")
    print("=" * 60)

    # Show specialty list information
    info = get_specialty_info()
    print("Available specialty lists:")
    for list_name, count in info.items():
        status = "[OK]" if count > 0 else "[empty]"
        print(f"  {list_name}: {count:,} symbols {status}")

    # Show breakdown
    breakdown = get_klmn_800_breakdown()
    print(f"\nUniverse Breakdown:")
    print(f"  Total: {breakdown['total_symbols']:,} symbols")
    print(f"  Composition: {breakdown['composition']}")
    print(f"  ETFs: {breakdown['etf_count']}")
    print(f"  Airlines: {breakdown['airline_count']}")
    print(f"  ADRs: {breakdown['adr_count']}")
    print(f"  Cherry Picks: {breakdown['cherry_pick_count']}")

    # Verify no overlap and no missing
    fm_set = set(FM_UNIVERSE)
    daily_set = set(DAILY_ONLY)
    full_set = set(KLMN_800_SYMBOLS)
    overlap = fm_set & daily_set
    print(f"\nIntegrity Checks:")
    print(f"  FM + Daily Only = {len(fm_set) + len(daily_set)} (should equal {len(full_set)})")
    print(f"  Overlap: {len(overlap)} (should be 0)")
    if overlap:
        print(f"  WARNING - Overlapping symbols: {sorted(overlap)}")

    # Verify protected groups are in FM_UNIVERSE
    # Note: Most ETFs intentionally moved to DAILY_ONLY (2026-03-16). Only JETS kept in FM.
    jets_in_fm = 'JETS' in fm_set
    airline_in_fm = set(AIRLINE_PLAY_SYMBOLS) - fm_set
    adr_in_fm = set(KLMN_ADR_COMPONENT) - fm_set
    cherry_in_fm = set(FM_CHERRY_PICKS) - fm_set
    print(f"  JETS in FM: {jets_in_fm} (should be True)")
    print(f"  Airlines missing from FM: {len(airline_in_fm)} (should be 0)")
    print(f"  ADRs missing from FM: {len(adr_in_fm)} (should be 0)")
    print(f"  Cherry picks missing from FM: {len(cherry_in_fm)} (should be 0)")

    # Verify no duplicates within lists
    fm_dupes = len(FM_UNIVERSE) - len(fm_set)
    daily_dupes = len(DAILY_ONLY) - len(daily_set)
    full_dupes = len(KLMN_800_SYMBOLS) - len(full_set)
    print(f"  FM duplicates: {fm_dupes} (should be 0)")
    print(f"  Daily Only duplicates: {daily_dupes} (should be 0)")
    print(f"  Full universe duplicates: {full_dupes} (should be 0)")
