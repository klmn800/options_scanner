#!/usr/bin/env python3
"""
Alpha Vantage API Client (alphavantage_api.py) - News & Sentiment Data
----------------------------------------------------------------------
Alpha Vantage API interface with rate limiting, caching, and news sentiment analysis.
Follows the same patterns as tradier_api.py for consistency.

Features:
- News sentiment API with comprehensive filtering
- Rate limiting (5 requests/minute, 25 requests/day for free tier)
- Intelligent caching to maximize API efficiency
- Batch news retrieval with symbol prioritization
- Sentiment analysis and data aggregation
- Database storage integration

Author: Ben (with assistance from Claude)
Date: 2025-09-19
"""

import os
import sys
import json
import time
import logging
import requests
import traceback
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from tools.timezone_utils import now_eastern, eastern_timestamp_string, eastern_isoformat, eastern_date_string

# Rate limit constants (per minute/day)
NEWS_RATE_LIMIT_PER_MINUTE = 5
NEWS_RATE_LIMIT_PER_DAY = 25

# Transient-network retry policy (added 2026-07-28)
# A single read timeout used to hard-fail the whole call. Because Flow Monitor
# cycles usually enrich exactly one symbol, that one blip became a 100% batch
# failure and tripped the news_enrichment_all_failed alarm (see 2026-07-28
# 12:48 read timeout). One retry recovers the common case. Held at 1 because
# every attempt spends a slot of the NEWS_RATE_LIMIT_PER_DAY budget.
TRANSIENT_RETRY_ATTEMPTS = 1
TRANSIENT_RETRY_BACKOFF_SEC = 3

class AlphaVantageRateLimiter:
    """Manages Alpha Vantage API request timing to stay within rate limits"""

    def __init__(self, requests_per_minute=5, requests_per_day=25, cache_dir="./cache", key_index=None):
        self.requests_per_minute = requests_per_minute
        self.requests_per_day = requests_per_day
        self.interval = 60 / requests_per_minute  # seconds between requests
        self.last_request_time = 0
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Use per-key usage file if key_index is provided
        if key_index is not None:
            self.usage_file = self.cache_dir / "alphavantage_daily_usage_key{}.json".format(key_index)
        else:
            self.usage_file = self.cache_dir / "alphavantage_daily_usage.json"

        # Load persisted daily counter
        self.daily_request_count = 0
        self.daily_reset_time = None
        self.load_daily_counter()
        self.reset_daily_counter()

    def load_daily_counter(self):
        """Load daily counter from persistent storage"""
        try:
            if self.usage_file.exists():
                with open(self.usage_file, 'r') as f:
                    data = json.load(f)
                    self.daily_request_count = data.get('daily_request_count', 0)
                    self.daily_reset_time = datetime.fromisoformat(data.get('daily_reset_time', '2000-01-01T00:00:00'))
                    logging.debug("Loaded daily counter: {} requests".format(self.daily_request_count))
        except Exception as e:
            logging.debug("Could not load daily counter: {}".format(e))
            self.daily_request_count = 0
            self.daily_reset_time = None

    def save_daily_counter(self):
        """Save daily counter to persistent storage"""
        try:
            data = {
                'daily_request_count': self.daily_request_count,
                'daily_reset_time': self.daily_reset_time.isoformat() if self.daily_reset_time else None,
                'last_updated': now_eastern().isoformat()
            }
            with open(self.usage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.debug("Could not save daily counter: {}".format(e))

    def reset_daily_counter(self):
        """Reset daily counter at midnight Eastern"""
        current_time = now_eastern()
        if self.daily_reset_time is None or current_time.date() > self.daily_reset_time.date():
            self.daily_request_count = 0
            self.daily_reset_time = current_time
            self.save_daily_counter()
            logging.debug("Alpha Vantage daily request counter reset ({} calls available)".format(self.requests_per_day))

    def can_make_request(self):
        """Check if we can make a request without exceeding limits"""
        self.reset_daily_counter()
        return self.daily_request_count < self.requests_per_day

    def wait_if_needed(self):
        """Wait if necessary to comply with rate limits"""
        self.reset_daily_counter()

        # Check daily limit
        if self.daily_request_count >= self.requests_per_day:
            logging.warning("Alpha Vantage daily rate limit reached ({})".format(self.requests_per_day))
            return False

        # Check per-minute limit
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.interval:
            sleep_time = self.interval - time_since_last
            logging.debug("Alpha Vantage rate limiting: Waiting {:.2f} seconds".format(sleep_time))
            time.sleep(sleep_time)

        self.last_request_time = time.time()
        self.daily_request_count += 1
        self.save_daily_counter()  # Persist the updated count

        logging.debug("Alpha Vantage API call {} of {} today".format(
            self.daily_request_count, self.requests_per_day))

        return True


class AlphaVantageCache:
    """Simple file-based caching for Alpha Vantage API responses"""

    def __init__(self, cache_dir):
        """Initialize the cache with directory path"""
        self.cache_dir = Path(cache_dir)
        self.news_dir = self.cache_dir / 'alphavantage_news'
        self.sentiment_dir = self.cache_dir / 'alphavantage_sentiment'

        # Create cache directories
        for directory in [self.news_dir, self.sentiment_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, data_type, identifier, suffix=None):
        """Get file path for cached data"""
        if data_type == 'news_symbol':
            if suffix:
                return self.news_dir / "{}_{}.json".format(identifier, suffix)
            else:
                return self.news_dir / "{}.json".format(identifier)
        elif data_type == 'news_topic':
            if suffix:
                return self.news_dir / "topic_{}_{}.json".format(identifier, suffix)
            else:
                return self.news_dir / "topic_{}.json".format(identifier)
        elif data_type == 'sentiment_summary':
            return self.sentiment_dir / "{}_summary.json".format(identifier)
        elif data_type == 'news_batch':
            return self.news_dir / "batch_{}.json".format(identifier)
        else:
            # Fallback for unknown types
            return self.cache_dir / "{}_{}.json".format(data_type, identifier)

    def is_cache_valid(self, cache_path, max_age_seconds):
        """Check if cached data is still valid"""
        if not cache_path.exists():
            return False

        file_age = time.time() - cache_path.stat().st_mtime
        return file_age < max_age_seconds

    def save_to_cache(self, data_type, identifier, data, suffix=None):
        """Save data to cache file"""
        cache_path = self.get_cache_path(data_type, identifier, suffix)

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': time.time(),
                    'eastern_time': eastern_isoformat(),
                    'data': data
                }, f, indent=2)
            logging.debug("Cached Alpha Vantage {} data for {}".format(data_type, identifier))
            return True
        except Exception as e:
            logging.error("Failed to cache Alpha Vantage {} data for {}: {}".format(data_type, identifier, e))
            return False

    def load_from_cache(self, data_type, identifier, max_age_seconds, suffix=None):
        """Load data from cache if valid"""
        cache_path = self.get_cache_path(data_type, identifier, suffix)

        if self.is_cache_valid(cache_path, max_age_seconds):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                logging.debug("Loaded Alpha Vantage {} data for {} from cache".format(data_type, identifier))
                return cached['data']
            except Exception as e:
                logging.error("Failed to load Alpha Vantage {} cache for {}: {}".format(data_type, identifier, e))

        return None


class AlphaVantageAPI:
    """Core Alpha Vantage API client with rate limiting and error handling"""

    def __init__(self, api_key, cache_dir="./cache", key_index=None):
        """Initialize the API client with authentication key"""
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"

        # Set up rate limiter with persistent storage (per-key tracking)
        self.rate_limiter = AlphaVantageRateLimiter(
            NEWS_RATE_LIMIT_PER_MINUTE,
            NEWS_RATE_LIMIT_PER_DAY,
            cache_dir,
            key_index
        )

        # Request tracking
        self.total_requests = 0
        self.requests_by_function = {}
        self.server_rate_limited = False  # Set when AV returns 'Information' response

        # Set up session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Options-Scanner/1.0'
        })

    def _handle_response(self, response):
        """Process API response and handle errors"""
        import os
        # DIAGNOSTIC ENHANCEMENT: Track all API responses for zero articles pattern investigation
        diag_log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(diag_log_dir, exist_ok=True)

        # Log ALL non-200 responses for pattern detection
        if response.status_code != 200:
            diag_error_file = os.path.join(diag_log_dir, 'av_non_200_responses.jsonl')
            try:
                import json as json_module
                from datetime import datetime
                error_record = {
                    'timestamp': datetime.now().isoformat(),
                    'status_code': response.status_code,
                    'response_text': response.text[:500],  # First 500 chars
                    'headers': dict(response.headers)
                }
                with open(diag_error_file, 'a', encoding='utf-8') as f:
                    f.write(json_module.dumps(error_record) + '\n')
                logging.warning("Alpha Vantage non-200 response logged to: {}".format(diag_error_file))
            except Exception as e:
                logging.error("Failed to log non-200 response: {}".format(e))

        if response.status_code == 200:
            try:
                data = response.json()

                # Check for API error messages
                if 'Error Message' in data:
                    logging.error("Alpha Vantage API error: {}".format(data['Error Message']))
                    # DIAGNOSTIC: Log error message responses
                    diag_file = os.path.join(diag_log_dir, 'av_error_messages.jsonl')
                    try:
                        import json as json_module
                        from datetime import datetime
                        with open(diag_file, 'a', encoding='utf-8') as f:
                            f.write(json_module.dumps({
                                'timestamp': datetime.now().isoformat(),
                                'error': data['Error Message'],
                                'full_response': data
                            }) + '\n')
                    except Exception as e:
                        logging.error("Failed to log error message: {}".format(e))
                    return None
                elif 'Note' in data:
                    logging.warning("Alpha Vantage API note: {}".format(data['Note']))
                    # DIAGNOSTIC: Log note/rate limit responses
                    diag_file = os.path.join(diag_log_dir, 'av_api_notes.jsonl')
                    try:
                        import json as json_module
                        from datetime import datetime
                        with open(diag_file, 'a', encoding='utf-8') as f:
                            f.write(json_module.dumps({
                                'timestamp': datetime.now().isoformat(),
                                'note': data['Note'],
                                'full_response': data
                            }) + '\n')
                    except Exception as e:
                        logging.error("Failed to log API note: {}".format(e))
                    return None
                elif 'Information' in data:
                    self.server_rate_limited = True
                    logging.warning("Alpha Vantage API information (rate limit): {}".format(
                        data['Information'][:200]))
                    # DIAGNOSTIC: Log 'Information' responses (IP-level rate limiting)
                    diag_file = os.path.join(diag_log_dir, 'av_api_notes.jsonl')
                    try:
                        import json as json_module
                        from datetime import datetime
                        with open(diag_file, 'a', encoding='utf-8') as f:
                            f.write(json_module.dumps({
                                'timestamp': datetime.now().isoformat(),
                                'information': data['Information'],
                                'local_call_count': self.rate_limiter.daily_request_count,
                                'last_success_ago_sec': round(time.time() - self.last_request_time, 1) if self.last_request_time else None,
                                'full_response': data
                            }) + '\n')
                    except Exception as e:
                        logging.error("Failed to log API information: {}".format(e))
                    return None

                # DIAGNOSTIC: Log when feed is present but empty (zero articles pattern investigation)
                if 'feed' in data and len(data.get('feed', [])) == 0:
                    logging.debug("Alpha Vantage API returned empty feed - Response structure: {} total keys, feed=[], items={}".format(
                        len(data.keys()),
                        data.get('items', 'Not in response')
                    ))
                    # Log EVERY empty feed response (not just first) with timestamp
                    import json as json_module
                    from datetime import datetime
                    diag_file = os.path.join(diag_log_dir, 'av_empty_feed_responses.jsonl')
                    try:
                        with open(diag_file, 'a', encoding='utf-8') as f:
                            f.write(json_module.dumps({
                                'timestamp': datetime.now().isoformat(),
                                'response_keys': list(data.keys()),
                                'items': data.get('items', 'Not available'),
                                'sentiment_score_definition': data.get('sentiment_score_definition', 'Not available'),
                                'full_response': data
                            }) + '\n')
                        logging.debug("Empty feed response logged to: {}".format(diag_file))
                    except Exception as e:
                        logging.error("Failed to log empty feed response: {}".format(e))

                return data
            except json.JSONDecodeError as e:
                logging.error("Alpha Vantage response JSON decode error: {}".format(e))
                # DIAGNOSTIC: Log JSON decode errors
                diag_file = os.path.join(diag_log_dir, 'av_json_decode_errors.jsonl')
                try:
                    import json as json_module
                    from datetime import datetime
                    with open(diag_file, 'a', encoding='utf-8') as f:
                        f.write(json_module.dumps({
                            'timestamp': datetime.now().isoformat(),
                            'error': str(e),
                            'response_text': response.text[:500]
                        }) + '\n')
                except Exception:
                    pass  # Silent fail on diagnostic logging
                return None
        elif response.status_code == 429:
            logging.warning("Alpha Vantage rate limit exceeded")
            return None
        else:
            logging.error("Alpha Vantage API error {}: {}".format(
                response.status_code, response.text[:200]))
            return None

    def _make_request(self, params):
        """Make an API request with rate limiting and error handling.

        Transient network failures (read/connect timeouts, dropped connections)
        get TRANSIENT_RETRY_ATTEMPTS retries; every other failure mode returns
        None on the first attempt. Each attempt spends a daily-budget slot and
        re-runs the rate-limit gate, so the retry count is deliberately small.
        Rate-limit responses ('Information'/'Note') come back through
        _handle_response as None and are NOT retried.
        """
        self.server_rate_limited = False  # Reset per request

        # Add API key to parameters
        full_params = dict(params)
        full_params['apikey'] = self.api_key
        function_name = params.get('function', 'unknown')

        for attempt in range(TRANSIENT_RETRY_ATTEMPTS + 1):
            # Check if we can make the request
            if not self.rate_limiter.can_make_request():
                logging.warning("Alpha Vantage daily rate limit reached")
                return None

            # Wait if needed for rate limiting
            if not self.rate_limiter.wait_if_needed():
                return None

            # Track the request
            self.total_requests += 1
            self.requests_by_function[function_name] = self.requests_by_function.get(function_name, 0) + 1

            try:
                response = self.session.get(self.base_url, params=full_params, timeout=30)
                return self._handle_response(response)

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < TRANSIENT_RETRY_ATTEMPTS:
                    logging.warning("Alpha Vantage transient network error on {} "
                                    "(attempt {}/{}): {} — retrying in {}s".format(
                                        function_name, attempt + 1,
                                        TRANSIENT_RETRY_ATTEMPTS + 1, e,
                                        TRANSIENT_RETRY_BACKOFF_SEC))
                    time.sleep(TRANSIENT_RETRY_BACKOFF_SEC)
                    continue
                logging.error("Alpha Vantage request failed after {} attempts: {}".format(
                    TRANSIENT_RETRY_ATTEMPTS + 1, e))
                return None

            except requests.exceptions.RequestException as e:
                logging.error("Alpha Vantage request failed: {}".format(e))
                return None

        return None

    def get_news_sentiment(self, tickers=None, topics=None, time_from=None, time_to=None,
                          sort='LATEST', limit=1000):
        """Get news sentiment data with flexible filtering

        Args:
            tickers: String or list of ticker symbols (e.g., 'AAPL' or ['AAPL', 'MSFT'])
            topics: String or list of topics (e.g., 'earnings' or ['earnings', 'technology'])
            time_from: Start time in YYYYMMDDTHHMM format
            time_to: End time in YYYYMMDDTHHMM format
            sort: Sort order ('LATEST', 'EARLIEST', 'RELEVANCE')
            limit: Number of articles to return (1-1000)

        Returns:
            Dict with news sentiment data or None if failed
        """
        params = {
            'function': 'NEWS_SENTIMENT',
            'sort': sort,
            'limit': limit
        }

        # Handle tickers parameter
        if tickers:
            if isinstance(tickers, list):
                params['tickers'] = ','.join(tickers)
            else:
                params['tickers'] = tickers

        # Handle topics parameter
        if topics:
            if isinstance(topics, list):
                params['topics'] = ','.join(topics)
            else:
                params['topics'] = topics

        # Handle time range
        if time_from:
            params['time_from'] = time_from
        if time_to:
            params['time_to'] = time_to

        return self._make_request(params)

    def get_usage_stats(self):
        """Get current API usage statistics"""
        return {
            'total_requests': self.total_requests,
            'requests_by_function': dict(self.requests_by_function),
            'daily_requests_used': self.rate_limiter.daily_request_count,
            'daily_requests_remaining': NEWS_RATE_LIMIT_PER_DAY - self.rate_limiter.daily_request_count,
            'can_make_request': self.rate_limiter.can_make_request()
        }


class AlphaVantageNewsClient:
    """High-level client that combines API calls with caching and data processing"""

    def __init__(self, config, cache_dir, key_index=None):
        """Initialize with config and cache directory"""
        self.config = config
        self.cache = AlphaVantageCache(cache_dir)

        # Initialize API client
        api_key = self.config.get('alpha_vantage', {}).get('api_key')
        if not api_key:
            raise ValueError("Alpha Vantage API key not found in configuration")

        self.api = AlphaVantageAPI(api_key, cache_dir, key_index)

        # Configuration from config.json
        self.rate_limit_per_minute = self.config.get('alpha_vantage', {}).get('rate_limit_per_minute', 5)
        self.rate_limit_per_day = self.config.get('alpha_vantage', {}).get('rate_limit_per_day', 25)

    def get_symbol_news(self, symbol, limit=1000, max_age_seconds=3600,
                       time_from=None, time_to=None):
        """Get news articles for a specific symbol with caching

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            limit: Number of articles to return (default 1000 for max efficiency)
            max_age_seconds: Cache age limit (default 1 hour)
            time_from: Optional start time filter
            time_to: Optional end time filter

        Returns:
            Dict with articles and metadata or None if failed
        """
        # Check cache first
        cache_suffix = "limit_{}".format(limit)
        if time_from:
            cache_suffix += "_from_{}".format(time_from)

        cached_data = self.cache.load_from_cache('news_symbol', symbol, max_age_seconds, cache_suffix)

        if cached_data:
            return cached_data

        logging.debug("Fetching news for {} (limit={})".format(symbol, limit))

        # Make API request
        response = self.api.get_news_sentiment(
            tickers=symbol,
            limit=limit,
            time_from=time_from,
            time_to=time_to
        )

        if response and 'feed' in response:
            # Process and enhance the response
            processed_data = self._process_news_response(response, symbol)

            # Cache the results
            self.cache.save_to_cache('news_symbol', symbol, processed_data, cache_suffix)
            return processed_data

        # DIAGNOSTIC: Log when API returns a response without 'feed' key
        # This catches unrecognized response formats (e.g. 'Information' key)
        if response is not None:
            logging.warning("Alpha Vantage returned response without 'feed' for {}: keys={}".format(
                symbol, list(response.keys()) if isinstance(response, dict) else type(response).__name__))

        return None

    def get_topic_news(self, topic, limit=100, max_age_seconds=1800,
                      time_from=None, time_to=None):
        """Get news articles for a specific topic with caching

        Args:
            topic: Topic name (e.g., 'earnings', 'technology')
            limit: Number of articles to return
            max_age_seconds: Cache age limit (default 30 minutes)
            time_from: Optional start time filter
            time_to: Optional end time filter

        Returns:
            Dict with articles and metadata or None if failed
        """
        # Check cache first
        cache_suffix = "limit_{}".format(limit)
        if time_from:
            cache_suffix += "_from_{}".format(time_from)

        cached_data = self.cache.load_from_cache('news_topic', topic, max_age_seconds, cache_suffix)

        if cached_data:
            return cached_data

        logging.info("Fetching topic news for '{}' (limit={})".format(topic, limit))

        # Make API request
        response = self.api.get_news_sentiment(
            topics=topic,
            limit=limit,
            time_from=time_from,
            time_to=time_to
        )

        if response and 'feed' in response:
            # Process and enhance the response
            processed_data = self._process_news_response(response, topic, is_topic=True)

            # Cache the results
            self.cache.save_to_cache('news_topic', topic, processed_data, cache_suffix)
            return processed_data

        return None

    def get_batch_symbol_news(self, symbols, max_symbols_per_day=None):
        """Get news for multiple symbols efficiently within daily rate limits

        Args:
            symbols: List of symbols to fetch news for
            max_symbols_per_day: Override default daily limit calculation

        Returns:
            Dict with symbol -> news data mapping
        """
        if not symbols:
            return {}

        # Calculate how many symbols we can fetch today
        usage_stats = self.api.get_usage_stats()
        remaining_requests = usage_stats['daily_requests_remaining']

        if max_symbols_per_day:
            max_fetchable = min(max_symbols_per_day, remaining_requests)
        else:
            max_fetchable = remaining_requests

        logging.info("Batch news fetch: {} symbols requested, {} API calls remaining".format(
            len(symbols), remaining_requests))

        if max_fetchable <= 0:
            logging.warning("No Alpha Vantage API calls remaining today")
            return {}

        # Prioritize symbols (could be enhanced with significance scoring)
        symbols_to_fetch = symbols[:max_fetchable]

        if len(symbols_to_fetch) < len(symbols):
            logging.warning("Rate limited: fetching {} of {} symbols".format(
                len(symbols_to_fetch), len(symbols)))

        results = {}

        # Fetch news for each symbol
        for i, symbol in enumerate(symbols_to_fetch, 1):
            logging.info("Fetching news for {} ({}/{})".format(symbol, i, len(symbols_to_fetch)))

            news_data = self.get_symbol_news(symbol, limit=1000, max_age_seconds=3600)

            if news_data:
                results[symbol] = news_data
                articles_count = news_data.get('article_count', 0)
                logging.info("Retrieved {} articles for {}".format(articles_count, symbol))
            else:
                logging.warning("No news data retrieved for {}".format(symbol))
                results[symbol] = None

        # Create batch summary
        batch_summary = {
            'timestamp': eastern_isoformat(),
            'symbols_requested': len(symbols),
            'symbols_fetched': len(symbols_to_fetch),
            'symbols_with_data': len([s for s in results.values() if s is not None]),
            'total_articles': sum(
                (data.get('article_count', 0) if data else 0)
                for data in results.values()
            ),
            'api_calls_used': len(symbols_to_fetch),
            'api_calls_remaining': usage_stats['daily_requests_remaining'] - len(symbols_to_fetch)
        }

        # Save batch results to cache
        batch_id = eastern_date_string() + "_" + str(int(time.time()))
        self.cache.save_to_cache('news_batch', batch_id, {
            'summary': batch_summary,
            'results': results
        })

        logging.info("Batch fetch complete: {} articles from {} symbols".format(
            batch_summary['total_articles'], batch_summary['symbols_with_data']))

        return {
            'summary': batch_summary,
            'results': results
        }

    def _process_news_response(self, response, identifier, is_topic=False):
        """Process raw API response into structured format"""
        try:
            feed = response.get('feed', [])

            # DIAGNOSTIC: Log when API returns empty feed (zero articles pattern investigation)
            if len(feed) == 0:
                logging.debug("Alpha Vantage returned EMPTY FEED for {}: Response keys: {}, items: {}".format(
                    identifier,
                    list(response.keys()),
                    response.get('items', 'Not available')
                ))

            processed = {
                'identifier': identifier,
                'type': 'topic' if is_topic else 'symbol',
                'timestamp': eastern_isoformat(),
                'article_count': len(feed),
                'sentiment_score_overall': response.get('sentiment_score_definition', 'Not available'),
                'items': response.get('items', 'Not available'),
                'articles': [],
                'sentiment_summary': self._calculate_sentiment_summary(feed)
            }

            # Process each article
            for article in feed:
                processed_article = {
                    'title': article.get('title', ''),
                    'url': article.get('url', ''),
                    'time_published': article.get('time_published', ''),
                    'authors': article.get('authors', []),
                    'summary': article.get('summary', ''),
                    'source': article.get('source', ''),
                    'category_within_source': article.get('category_within_source', ''),
                    'overall_sentiment_score': article.get('overall_sentiment_score', 0),
                    'overall_sentiment_label': article.get('overall_sentiment_label', 'Neutral'),
                    'ticker_sentiment': article.get('ticker_sentiment', [])
                }

                processed['articles'].append(processed_article)

            return processed

        except Exception as e:
            logging.error("Error processing Alpha Vantage news response: {}".format(e))
            return None

    def _calculate_sentiment_summary(self, articles):
        """Calculate aggregate sentiment metrics from articles"""
        if not articles:
            return {}

        try:
            sentiment_scores = []
            sentiment_labels = {}

            for article in articles:
                score = article.get('overall_sentiment_score')
                label = article.get('overall_sentiment_label', 'Neutral')

                if score is not None:
                    try:
                        sentiment_scores.append(float(score))
                    except (ValueError, TypeError):
                        pass

                sentiment_labels[label] = sentiment_labels.get(label, 0) + 1

            summary = {
                'total_articles': len(articles),
                'articles_with_scores': len(sentiment_scores)
            }

            if sentiment_scores:
                summary.update({
                    'average_sentiment_score': sum(sentiment_scores) / len(sentiment_scores),
                    'min_sentiment_score': min(sentiment_scores),
                    'max_sentiment_score': max(sentiment_scores)
                })

            if sentiment_labels:
                summary['sentiment_distribution'] = sentiment_labels
                summary['dominant_sentiment'] = max(sentiment_labels.items(), key=lambda x: x[1])[0]

            return summary

        except Exception as e:
            logging.error("Error calculating sentiment summary: {}".format(e))
            return {}

    def get_usage_stats(self):
        """Get current API usage statistics"""
        return self.api.get_usage_stats()


def test_alphavantage_client(config_path="config.json", cache_dir="./cache"):
    """Test the Alpha Vantage news client"""
    print("Alpha Vantage News Client Test")
    print("=" * 40)

    try:
        # Load config
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Initialize client
        client = AlphaVantageNewsClient(config, cache_dir)

        # Test 1: Single symbol news
        print("\n1. Testing single symbol news (NVDA)...")
        nvda_news = client.get_symbol_news('NVDA', limit=100)
        if nvda_news:
            print("   Articles found: {}".format(nvda_news['article_count']))
            print("   Sentiment summary: {}".format(nvda_news.get('sentiment_summary', {})))
        else:
            print("   Failed to get NVDA news")

        # Test 2: Topic news
        print("\n2. Testing topic news (earnings)...")
        earnings_news = client.get_topic_news('earnings', limit=50)
        if earnings_news:
            print("   Articles found: {}".format(earnings_news['article_count']))
            print("   Sentiment summary: {}".format(earnings_news.get('sentiment_summary', {})))
        else:
            print("   Failed to get earnings news")

        # Test 3: Usage stats
        print("\n3. Current usage stats:")
        stats = client.get_usage_stats()
        for key, value in stats.items():
            print("   {}: {}".format(key, value))

        print("\n✅ Alpha Vantage client test completed!")
        return True

    except Exception as e:
        print("❌ Test failed: {}".format(e))
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO,
                       format='%(asctime)s - %(levelname)s - %(message)s')

    # Run test
    test_alphavantage_client()