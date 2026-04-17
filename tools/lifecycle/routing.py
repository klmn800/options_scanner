"""
Archive Routing Logic (routing.py)
-----------------------------------
Determines which sector archive database a symbol should be routed to,
based on its sector and industry classification.

Encodes all routing rules including sector splits (Technology -> 3 DBs,
Consumer Cyclical -> 3 DBs) and special industry overrides.

Used by the onboarding archive picker to suggest a default. The user
always gets final say via the interactive picker.

PRD 0013 — Symbol Lifecycle Management (FR-9)
"""


# Industry -> archive_db overrides (takes priority over sector-based routing)
_INDUSTRY_OVERRIDES = {
    # Industrials sector splits
    'Airlines': 'airlines',

    # Technology sector splits
    'Semiconductors': 'semiconductors',
    'Semiconductor Equipment & Materials': 'semiconductors',
    'Software - Application': 'software',
    'Software - Infrastructure': 'software',

    # Consumer Cyclical sector splits (retail)
    'Internet Retail': 'retail',
    'Specialty Retail': 'retail',
    'Apparel - Retail': 'retail',
    'Apparel - Footwear & Accessories': 'retail',
    'Home Improvement': 'retail',
    'Department Stores': 'retail',
    'Luxury Goods': 'retail',

    # Consumer Cyclical sector splits (travel/leisure)
    'Restaurants': 'travel_leisure',
    'Gambling, Resorts & Casinos': 'travel_leisure',
    'Travel Services': 'travel_leisure',
    'Travel Lodging': 'travel_leisure',
    'Leisure': 'travel_leisure',

    # Financial Services splits
    'Asset Management': 'asset_management',

    # Industries where sector default is usually right but not always.
    # These give the picker a better suggestion than the raw sector fallback.
    'Aerospace & Defense': 'industrials',
    'Uranium': 'energy',
    'Specialty Industrial Machinery': 'industrials',
    'Banks - Diversified': 'financial_services',
    'Advertising Agencies': 'communication_services',
    'Internet Content & Information': 'communication_services',
    'Information Technology Services': 'technology',
    'Solar': 'technology',
    'Credit Services': 'financial_services',
}

# Sector -> default archive_db (for industries not in overrides)
_SECTOR_DEFAULTS = {
    'Basic Materials': 'basic_materials',
    'Communication Services': 'communication_services',
    'Consumer Cyclical': 'consumer_cyclical',
    'Consumer Defensive': 'consumer_defensive',
    'Energy': 'energy',
    'Financial Services': 'financial_services',
    'Healthcare': 'healthcare',
    'Industrials': 'industrials',
    'Real Estate': 'real_estate',
    'Technology': 'technology',
    'Utilities': 'utilities',
}


def determine_archive_db(sector, industry):
    """Determine the suggested archive database for a symbol.

    Args:
        sector: Morningstar sector classification (e.g., 'Technology')
        industry: Morningstar industry classification (e.g., 'Semiconductors')

    Returns:
        str or None: Suggested archive_db name (e.g. 'semiconductors'),
                     or None if sector is unknown.
    """
    if not sector or sector == 'N/A':
        return None

    # Check industry overrides first
    if industry and industry in _INDUSTRY_OVERRIDES:
        return _INDUSTRY_OVERRIDES[industry]

    # Fall back to sector default
    if sector in _SECTOR_DEFAULTS:
        return _SECTOR_DEFAULTS[sector]

    # Unknown sector — normalize as best guess
    return sector.lower().replace(' ', '_')
