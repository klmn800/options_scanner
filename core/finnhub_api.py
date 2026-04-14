#!/usr/bin/env python3
"""
Finnhub API Client (finnhub_api.py) - Earnings Calendar Data
-------------------------------------------------------------
REST API client for Finnhub.io earnings calendar endpoint.
Provides BMO/AMC timing, EPS estimates, and revenue estimates.

Follows the same patterns as tradier_api.py (RateLimiter, Session, error handling).

Features:
- Earnings calendar with BMO/AMC/DMH timing
- Rate limiting (60 requests/minute for free tier)
- 429 retry with exponential backoff
- Date-range chunking for efficient bulk fetches
- KLMN 800 filtering at the client level
- Request counting for diagnostics

Author: Ben (with Claude)
Date: 2026-02-26
"""

import os
import sys
import time
import logging
import requests
from datetime import datetime, timedelta, date

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.symbols_klmn800 import get_specialty_list
from tools.log_utils import beautiful_log


class RateLimiter:
    """Manages API request timing to stay within rate limits"""

    def __init__(self, requests_per_minute=60):
        self.requests_per_minute = requests_per_minute
        self.interval = 60.0 / requests_per_minute
        self.last_request_time = 0

    def wait_if_needed(self):
        """Wait if necessary to comply with rate limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.interval:
            sleep_time = self.interval - time_since_last
            logging.debug("Finnhub rate limiting: waiting {:.2f}s".format(sleep_time))
            time.sleep(sleep_time)

        self.last_request_time = time.time()


class FinnhubAPI:
    """Low-level Finnhub HTTP client with rate limiting and error handling"""

    def __init__(self, api_key, base_url="https://finnhub.io/api/v1", rate_limit_per_minute=60):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.rate_limiter = RateLimiter(rate_limit_per_minute)
        self.session = requests.Session()

        # Request counting
        self.total_requests = 0
        self.requests_this_session = 0

    def _make_request(self, endpoint, params=None):
        """Make an authenticated API request with rate limiting and error handling.

        Args:
            endpoint: API endpoint path (e.g., '/calendar/earnings')
            params: Optional query parameters dict

        Returns:
            dict: Parsed JSON response

        Raises:
            requests.exceptions.RequestException: On unrecoverable HTTP errors
        """
        url = "{}/{}".format(self.base_url, endpoint.lstrip('/'))

        if params is None:
            params = {}
        params['token'] = self.api_key

        self.rate_limiter.wait_if_needed()
        self.total_requests += 1
        self.requests_this_session += 1

        response = self.session.get(url, params=params, timeout=30)
        return self._handle_response(response, url, params)

    def _handle_response(self, response, url, params):
        """Handle HTTP response — parse JSON, retry on 429, raise on errors.

        Args:
            response: requests.Response object
            url: Original request URL (for retry)
            params: Original request params (for retry)

        Returns:
            dict: Parsed JSON response
        """
        if response.status_code == 429:
            # Rate limited — back off and retry once
            retry_after = int(response.headers.get('Retry-After', 5))
            beautiful_log("Finnhub 429 rate limit — waiting {}s before retry".format(retry_after), level='warning')
            time.sleep(retry_after)

            self.rate_limiter.wait_if_needed()
            self.total_requests += 1
            self.requests_this_session += 1

            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 429:
                beautiful_log("Finnhub 429 on retry — aborting request", level='error')
                response.raise_for_status()

        response.raise_for_status()
        return response.json()

    def get_earnings_calendar(self, from_date, to_date, symbol=None):
        """Fetch earnings calendar for a date range.

        Args:
            from_date: Start date (date object or 'YYYY-MM-DD' string)
            to_date: End date (date object or 'YYYY-MM-DD' string)
            symbol: Optional single symbol filter

        Returns:
            list[dict]: List of earnings release dicts with normalized fields
        """
        params = {
            'from': str(from_date),
            'to': str(to_date),
        }
        if symbol:
            params['symbol'] = symbol

        data = self._make_request('calendar/earnings', params)

        # Response structure: {"earningsCalendar": [...], "symbol": ""}
        releases = data.get('earningsCalendar', [])

        # Normalize hour field: "" → "Unknown", pass through bmo/amc/dmh
        for release in releases:
            hour = release.get('hour', '')
            if not hour or hour.strip() == '':
                release['hour'] = 'Unknown'

        return releases


class FinnhubEarningsClient:
    """High-level earnings client — date-range chunking, KLMN filtering, diagnostics"""

    def __init__(self, config):
        """Initialize from config dict (from config.json 'finnhub' section).

        Args:
            config: dict with keys: api_key, base_url (optional), rate_limit_per_minute (optional)
        """
        self.api = FinnhubAPI(
            api_key=config['api_key'],
            base_url=config.get('base_url', 'https://finnhub.io/api/v1'),
            rate_limit_per_minute=config.get('rate_limit_per_minute', 60),
        )
        self.klmn_symbols = set(get_specialty_list('klmn_800'))

    @property
    def total_requests(self):
        return self.api.total_requests

    @property
    def requests_this_session(self):
        return self.api.requests_this_session

    def fetch_earnings_range(self, days_ahead=90, chunk_days=30):
        """Fetch earnings for KLMN 800 symbols over the next N days.

        Splits the date range into ~30-day chunks to stay within Finnhub's
        response size limits. Deduplicates by symbol (keeps first occurrence).

        KNOWN LIMITATION (2026-02-27): The bulk calendar endpoint caps at 1500
        results per API call. With ~4500 total releases per 30-day window, KLMN
        symbols that fall outside the 1500 cut are silently dropped. Verified:
        symbols missing from bulk results (AAON, MDB, NCLH, SEE, NXE, DNN, etc.)
        DO have data when queried per-symbol via fetch_symbol_earnings(). This
        caused ~8 of 11 near-term "Unknown" timing entries on 2026-02-27.
        Prefer fetch_symbol_earnings() for complete coverage.

        Args:
            days_ahead: How many days ahead to scan (default 90)
            chunk_days: Size of each API call's date window (default 30)

        Returns:
            list[dict]: Earnings releases filtered to KLMN 800 symbols.
                Each dict has: symbol, date, hour, epsEstimate, revenueEstimate, etc.
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        all_releases = []
        seen_symbols = set()

        chunk_start = today
        while chunk_start < end_date:
            chunk_end = min(chunk_start + timedelta(days=chunk_days - 1), end_date)

            logging.info("Finnhub: fetching earnings {} to {} ...".format(chunk_start, chunk_end))

            try:
                releases = self.api.get_earnings_calendar(chunk_start, chunk_end)
                chunk_count = 0

                for r in releases:
                    sym = r.get('symbol', '')
                    if sym in self.klmn_symbols and sym not in seen_symbols:
                        seen_symbols.add(sym)
                        all_releases.append(r)
                        chunk_count += 1

                logging.info("  {} total releases, {} KLMN matches (cumulative: {})".format(
                    len(releases), chunk_count, len(all_releases)))

            except requests.exceptions.RequestException as e:
                logging.error("Finnhub API error for chunk {} to {}: {}".format(
                    chunk_start, chunk_end, e))

            chunk_start = chunk_end + timedelta(days=1)

        logging.info("Finnhub fetch complete: {} KLMN symbols found in {} API calls".format(
            len(all_releases), self.api.requests_this_session))

        return all_releases

    def fetch_symbol_earnings(self, symbol):
        """Fetch earnings for a single symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            dict or None: Earnings release dict if found, None otherwise
        """
        today = date.today()
        end_date = today + timedelta(days=90)

        try:
            releases = self.api.get_earnings_calendar(today, end_date, symbol=symbol)
            if releases:
                return releases[0]
        except requests.exceptions.RequestException as e:
            logging.error("Finnhub API error for {}: {}".format(symbol, e))

        return None
