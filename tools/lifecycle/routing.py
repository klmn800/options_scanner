"""
Archive Routing Logic (routing.py)
-----------------------------------
Determines which sector archive database a symbol should be routed to,
based on its sector and industry classification.

Encodes all routing rules including sector splits (Technology → 3 DBs,
Consumer Cyclical → 3 DBs) and special industry overrides.

PRD 0013 — Symbol Lifecycle Management (FR-9)
"""


# Industry -> archive_db overrides (takes priority over sector-based routing)
# These are explicit, unambiguous assignments.
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
}

# Industries where routing is ambiguous (same industry has symbols in different archives).
# The tuple is (default_archive, explanation).
_AMBIGUOUS_INDUSTRIES = {
    'Aerospace & Defense': ('industrials', 'Defense contractors may route to defense.db or nuclear.db'),
    'Uranium': ('energy', 'Uranium miners may route to nuclear.db'),
    'Specialty Industrial Machinery': ('industrials', 'Some nuclear-related machinery routes to nuclear.db'),
    'Banks - Diversified': ('financial_services', 'Large diversified banks may route to asset_management.db'),
    'Advertising Agencies': ('communication_services', 'Some ad agencies route to technology.db'),
    'Internet Content & Information': ('communication_services', 'Some internet companies route to technology.db'),
    'Information Technology Services': ('technology', 'Some IT services route to industrials.db'),
    'Solar': ('technology', 'Solar companies may route to energy.db'),
    'Credit Services': ('financial_services', 'Some credit companies route to technology.db'),
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
    """Determine the archive database for a symbol based on sector/industry.

    Args:
        sector: Morningstar sector classification (e.g., 'Technology')
        industry: Morningstar industry classification (e.g., 'Semiconductors')

    Returns:
        tuple: (archive_db_name, is_ambiguous)
            archive_db_name: str like 'semiconductors', 'technology', etc.
            is_ambiguous: bool — True if the user should confirm the assignment.
    """
    if not sector or sector == 'N/A':
        return (None, True)

    # Check industry overrides first (unambiguous)
    if industry and industry in _INDUSTRY_OVERRIDES:
        return (_INDUSTRY_OVERRIDES[industry], False)

    # Check if industry is ambiguous
    if industry and industry in _AMBIGUOUS_INDUSTRIES:
        default_db, _reason = _AMBIGUOUS_INDUSTRIES[industry]
        return (default_db, True)

    # Fall back to sector default
    if sector in _SECTOR_DEFAULTS:
        return (_SECTOR_DEFAULTS[sector], False)

    # Unknown sector — normalize as best guess
    normalized = sector.lower().replace(' ', '_')
    return (normalized, True)


def get_ambiguity_reason(industry):
    """Get explanation for why an industry's routing is ambiguous.

    Returns:
        str or None: Explanation text, or None if not ambiguous.
    """
    if industry in _AMBIGUOUS_INDUSTRIES:
        return _AMBIGUOUS_INDUSTRIES[industry][1]
    return None


def get_all_archive_routes():
    """Return the full routing configuration for display/debugging.

    Returns:
        dict with keys: industry_overrides, ambiguous, sector_defaults
    """
    return {
        'industry_overrides': dict(_INDUSTRY_OVERRIDES),
        'ambiguous_industries': {k: v[0] for k, v in _AMBIGUOUS_INDUSTRIES.items()},
        'sector_defaults': dict(_SECTOR_DEFAULTS),
    }
