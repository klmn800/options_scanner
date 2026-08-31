#!/usr/bin/env python3
"""
News Sentiment Tool (news_sentiment.py)
---------------------------------------
Fetches financial news from Alpha Vantage, stores articles and per-symbol
sentiment, and computes relevance-weighted sentiment summaries.

Primary use: automatic enrichment of flow_watchlist_daily entries when new
alerts fire.  Also usable from the command line for ad-hoc research.

Replaces:
  - strategies/news_collector/ (3-tier rotation system, 6 files)
  - tools/news_collector.py (manual CLI collector)
  - data/av_news_symbol.py (weekend backfill script)

Usage Examples:
  # Enrich a single symbol (stores articles + prints summary)
  python tools/news_sentiment.py --symbol NVDA

  # Multiple symbols
  python tools/news_sentiment.py --symbols NVDA,GOOG,MSTR

  # Topic-based research (earnings, technology, etc.)
  python tools/news_sentiment.py --topic technology

  # Custom lookback and date range
  python tools/news_sentiment.py --symbol NVDA --lookback 7
  python tools/news_sentiment.py --symbol NVDA --from 2026-01-30 --to 2026-02-06

  # Dry run (no API calls)
  python tools/news_sentiment.py --symbol NVDA --dry-run

  # Check remaining API budget
  python tools/news_sentiment.py --budget

Author: Ben (with Claude Code assistance)
Created: 2026-02-07
"""

import os
import sys
import json
import sqlite3
import logging
import argparse
from datetime import timedelta
from pathlib import Path

# Add parent directory for imports
sys.path.append(str(Path(__file__).parent.parent))

from core.alphavantage_api import AlphaVantageNewsClient
from tools.timezone_utils import now_eastern, eastern_isoformat
from tools.decimal_formatter import clean_database_row


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Symbols that lack Alpha Vantage news endpoints (indices, volatility products)
NEWS_EXCLUDED_SYMBOLS = frozenset({
    'VIX', 'SPX', 'NDX', 'RUT', 'DJX',
    'VIXW', 'SPY', 'QQQ', 'IWM', 'DIA',  # ETFs that return market-wide noise
})

# Default collection parameters
DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_ARTICLE_LIMIT = 50

# Sentiment label buckets -- Alpha Vantage returns 5 labels, we collapse to 3
_BULLISH_LABELS = {'Bullish', 'Somewhat-Bullish'}
_BEARISH_LABELS = {'Bearish', 'Somewhat-Bearish'}
_NEUTRAL_LABELS = {'Neutral'}

# Autofix alarm tuning for 'news_enrichment_all_failed' (see enrich_watchlist_batch).
#
# The alarm exists to catch SYSTEMIC failure — API down, bad key, IP ban. Flow
# Monitor cycles usually enrich exactly one symbol, so a 1-symbol batch that hits
# one transient timeout is a "100% failure rate" that carries no information.
# Firing on it spawned false-positive batch-fix sessions on 2026-02-09 (5x),
# 2026-04-01 (3x) and 2026-07-28 (1x) — every occurrence a single-symbol batch.
#
# Two independent triggers replace the old bare `attempted > 0` check:
#   1. One batch of >= AUTOFIX_MIN_ATTEMPTED symbols failed entirely — a sample
#      large enough to stand on its own.
#   2. AUTOFIX_MAX_CONSECUTIVE_ALL_FAILED batches in a row failed entirely,
#      whatever their size — this is what catches a genuine outage during FM's
#      1-symbol cycles, which trigger 1 alone would never see.
# A 2026-02-09 fix set threshold 1 alone; it was lost before the 2026-04-13
# repo rebuild. Keep both triggers together — trigger 1 without trigger 2 trades
# false positives for blindness to real outages.
AUTOFIX_MIN_ATTEMPTED = 2
AUTOFIX_MAX_CONSECUTIVE_ALL_FAILED = 3

# Consecutive all-failed batch counter. Process-local by design: Flow Monitor
# runs as one long-lived process across the trading day, so this spans its
# cycles. Resets on any successful enrichment and on process restart.
_consecutive_all_failed_batches = 0


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _get_root_dir():
    """Get the project root directory."""
    return str(Path(__file__).parent.parent)


def _load_config():
    """Load config.json from project root."""
    config_path = os.path.join(_get_root_dir(), 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)


def _get_db_path():
    """Return the production database path."""
    return os.path.join(_get_root_dir(), 'data', 'datalake.db')


def _get_cache_dir():
    """Return the cache directory path."""
    return os.path.join(_get_root_dir(), 'cache')


def create_av_client(config=None):
    """Create an AlphaVantageNewsClient instance.

    Uses a single API key with the built-in rate limiter (25 calls/day,
    persisted to disk, auto-resets at midnight Eastern).

    Callers processing multiple symbols should create ONE client and pass it
    to fetch/enrich functions via the ``av_client`` parameter so the
    per-minute rate limiter stays alive across calls.
    """
    if config is None:
        config = _load_config()
    return AlphaVantageNewsClient(config, _get_cache_dir())


# Keep old name for any internal callers
_create_av_client = create_av_client


# ---------------------------------------------------------------------------
# Core: Fetch news from Alpha Vantage
# ---------------------------------------------------------------------------

def fetch_symbol_news(symbol, lookback_days=DEFAULT_LOOKBACK_DAYS,
                      limit=DEFAULT_ARTICLE_LIMIT, av_client=None):
    """Fetch news articles for a single symbol from Alpha Vantage.

    Args:
        symbol: Stock ticker (e.g. 'NVDA')
        lookback_days: How many days back to request (default 3)
        limit: Max articles to return (default 50)
        av_client: Optional pre-initialized AlphaVantageNewsClient

    Returns:
        dict with 'articles' list and metadata, or None if failed/excluded
    """
    if symbol in NEWS_EXCLUDED_SYMBOLS:
        logging.debug("Skipping excluded symbol: {}".format(symbol))
        return None

    if av_client is None:
        av_client = _create_av_client()

    # Check budget before spending a call
    stats = av_client.api.get_usage_stats()
    if not stats['can_make_request']:
        logging.warning("Daily API budget exhausted ({} calls used)".format(
            stats['daily_requests_used']))
        return None

    time_from = (now_eastern() - timedelta(days=lookback_days)).strftime('%Y%m%dT%H%M')

    logging.debug("Fetching news for {} (lookback: {} days, limit: {})".format(
        symbol, lookback_days, limit))

    news_data = av_client.get_symbol_news(
        symbol=symbol,
        time_from=time_from,
        limit=limit,
        max_age_seconds=300  # 5-minute cache for rapid re-queries
    )

    if news_data and news_data.get('articles'):
        logging.debug("Retrieved {} articles for {}".format(
            len(news_data['articles']), symbol))
    else:
        logging.debug("No articles returned for {}".format(symbol))

    return news_data


def fetch_topic_news(topic, lookback_days=DEFAULT_LOOKBACK_DAYS,
                     limit=DEFAULT_ARTICLE_LIMIT, av_client=None):
    """Fetch news articles by topic from Alpha Vantage.

    Args:
        topic: Topic string (e.g. 'technology', 'earnings', 'economy_macro')
        lookback_days: How many days back to request
        limit: Max articles to return
        av_client: Optional pre-initialized AlphaVantageNewsClient

    Returns:
        dict with 'articles' list and metadata, or None if failed
    """
    if av_client is None:
        av_client = _create_av_client()

    stats = av_client.api.get_usage_stats()
    if not stats['can_make_request']:
        logging.warning("Daily API budget exhausted ({} calls used)".format(
            stats['daily_requests_used']))
        return None

    time_from = (now_eastern() - timedelta(days=lookback_days)).strftime('%Y%m%dT%H%M')

    logging.info("Fetching topic news for '{}' (lookback: {} days)".format(
        topic, lookback_days))

    news_data = av_client.get_topic_news(
        topic=topic,
        time_from=time_from,
        limit=limit,
        max_age_seconds=300
    )

    return news_data


# ---------------------------------------------------------------------------
# Core: Store raw articles and sentiment in database
# ---------------------------------------------------------------------------

def store_news_data(symbol, news_data, db_path=None):
    """Store fetched articles and per-symbol sentiment in the database.

    Writes to two tables:
      - news_articles: one row per unique article (deduped by URL)
      - news_symbol_sentiment: one row per (article, symbol) pair

    Args:
        symbol: The symbol that was queried (for logging)
        news_data: Dict returned by fetch_symbol_news / fetch_topic_news
        db_path: Database path (defaults to production datalake.db)

    Returns:
        dict: {'articles_stored': int, 'sentiment_stored': int}
    """
    if db_path is None:
        db_path = _get_db_path()

    result = {'articles_stored': 0, 'sentiment_stored': 0}

    if not news_data or not news_data.get('articles'):
        return result

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            for article in news_data['articles']:
                try:
                    # Parse article date from time_published (YYYYMMDDTHHMM)
                    time_published = article.get('time_published', '')
                    article_date = 'unknown'
                    if len(time_published) >= 8:
                        d = time_published[:8]
                        article_date = '{}-{}-{}'.format(d[:4], d[4:6], d[6:8])

                    # Decimal-format the overall sentiment score
                    cleaned = clean_database_row({
                        'overall_sentiment_score': article.get('overall_sentiment_score', 0.0)
                    })

                    # Collect mentioned symbols for the JSON column
                    mentioned = [t['ticker'] for t in article.get('ticker_sentiment', [])]

                    cursor.execute("""
                        INSERT OR IGNORE INTO news_articles (
                            article_url, title, summary, source, authors,
                            time_published, article_date, time_collected,
                            overall_sentiment_score, overall_sentiment_label,
                            symbols_mentioned
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        article['url'],
                        article.get('title', ''),
                        article.get('summary', ''),
                        article.get('source', ''),
                        json.dumps(article.get('authors', [])),
                        time_published,
                        article_date,
                        eastern_isoformat(),
                        cleaned['overall_sentiment_score'],
                        article.get('overall_sentiment_label', 'Neutral'),
                        json.dumps(mentioned)
                    ))

                    if cursor.rowcount > 0:
                        result['articles_stored'] += 1

                    # Store per-symbol sentiment for each ticker mentioned
                    for ts in article.get('ticker_sentiment', []):
                        try:
                            cleaned_sent = clean_database_row({
                                'relevance_score': ts.get('relevance_score', 0.0),
                                'symbol_sentiment_score': ts.get('ticker_sentiment_score', 0.0),
                            })

                            cursor.execute("""
                                INSERT OR REPLACE INTO news_symbol_sentiment (
                                    article_url, symbol, article_date,
                                    relevance_score, symbol_sentiment_score,
                                    symbol_sentiment_label, time_collected
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                article['url'],
                                ts['ticker'],
                                article_date,
                                cleaned_sent['relevance_score'],
                                cleaned_sent['symbol_sentiment_score'],
                                ts.get('ticker_sentiment_label', 'Neutral'),
                                eastern_isoformat()
                            ))
                            result['sentiment_stored'] += 1

                        except Exception as e:
                            logging.debug("Failed to store sentiment for {}: {}".format(
                                ts.get('ticker', '?'), e))

                except Exception as e:
                    logging.debug("Failed to store article {}: {}".format(
                        article.get('url', '?'), e))

            conn.commit()

    except Exception as e:
        logging.error("Database error storing news for {}: {}".format(symbol, e))

    return result


# ---------------------------------------------------------------------------
# Core: Compute relevance-weighted sentiment summary
# ---------------------------------------------------------------------------

def compute_sentiment_summary(symbol, news_data):
    """Compute a relevance-weighted sentiment summary for a symbol.

    How relevance weighting works:
    ─────────────────────────────
    Alpha Vantage assigns each article a relevance_score (0.0 to 1.0)
    indicating how central the symbol is to that article.  An article
    focused entirely on NVDA gets relevance ~1.0, while a market roundup
    that mentions NVDA in passing gets ~0.3.

    We weight each article's sentiment_score by its relevance so that
    focused, symbol-specific articles dominate the summary:

        weighted_score = sum(score_i * relevance_i) / sum(relevance_i)

    Example:
        Article A: score=+0.40, relevance=0.95  (NVDA earnings analysis)
        Article B: score=-0.10, relevance=0.30  (broad market selloff mention)

        weighted = (0.40*0.95 + -0.10*0.30) / (0.95 + 0.30)
                 = (0.38 - 0.03) / 1.25
                 = +0.28  (Bullish, dominated by the focused article)

        simple avg = (0.40 + -0.10) / 2 = +0.15  (would underweight Article A)

    Args:
        symbol: Stock ticker to compute summary for
        news_data: Dict returned by fetch_symbol_news (must have 'articles')

    Returns:
        dict with three fields ready for flow_watchlist_daily:
          - news_sentiment_score: float (relevance-weighted avg, 2 decimal places)
          - news_sentiment_label: str (e.g. "Bullish 3/Bearish 1/Neutral 2")
          - news_article_count: int (total articles with sentiment for this symbol)

        Returns None if no sentiment data available for this symbol.
    """
    if not news_data or not news_data.get('articles'):
        return None

    # Collect per-symbol sentiment data from articles that mention this symbol
    scores = []       # (sentiment_score, relevance_score) tuples
    label_counts = {'Bullish': 0, 'Bearish': 0, 'Neutral': 0}

    for article in news_data['articles']:
        for ts in article.get('ticker_sentiment', []):
            if ts.get('ticker') != symbol:
                continue

            try:
                score = float(ts.get('ticker_sentiment_score', 0.0))
                relevance = float(ts.get('relevance_score', 0.0))
            except (ValueError, TypeError):
                continue

            scores.append((score, relevance))

            # Bucket the label (collapse Somewhat-* into parent category)
            label = ts.get('ticker_sentiment_label', 'Neutral')
            if label in _BULLISH_LABELS:
                label_counts['Bullish'] += 1
            elif label in _BEARISH_LABELS:
                label_counts['Bearish'] += 1
            else:
                label_counts['Neutral'] += 1

    if not scores:
        return None

    # Compute relevance-weighted average sentiment
    total_weight = sum(r for _, r in scores)

    if total_weight > 0:
        weighted_score = sum(s * r for s, r in scores) / total_weight
    else:
        # All relevance scores are 0 — fall back to simple average
        weighted_score = sum(s for s, _ in scores) / len(scores)

    # Format the distribution label: "Bullish 3/Bearish 1/Neutral 2"
    label_parts = []
    for category in ('Bullish', 'Bearish', 'Neutral'):
        count = label_counts[category]
        if count > 0:
            label_parts.append("{} {}".format(category, count))
    distribution_label = '/'.join(label_parts) if label_parts else 'No Data'

    # Apply decimal formatting (2 decimal places for scores)
    cleaned = clean_database_row({'news_sentiment_score': weighted_score})

    return {
        'news_sentiment_score': cleaned['news_sentiment_score'],
        'news_sentiment_label': distribution_label,
        'news_article_count': len(scores),
    }


# ---------------------------------------------------------------------------
# Watchlist integration: called by fm_main.py
# ---------------------------------------------------------------------------

def enrich_watchlist_symbol(symbol, storage=None, av_client=None, entry_date=None):
    """Fetch news for a symbol and update its watchlist row with sentiment.

    This is the main integration point called from Flow Monitor after a new
    watchlist entry is created.  It:
      1. Fetches news (3-day lookback, up to 50 articles)
      2. Stores raw articles in news_articles / news_symbol_sentiment
      3. Computes relevance-weighted sentiment summary
      4. Updates the flow_watchlist_daily row with 3 sentiment columns

    Args:
        symbol: Stock ticker to enrich
        storage: FlowMonitorStorage instance (for database writes).
                 If None, uses a direct sqlite3 connection (for CLI/backfill).
        av_client: Optional pre-initialized AV client (for budget sharing)
        entry_date: Target date string (YYYY-MM-DD) for the watchlist row to update.
                    Defaults to today (Eastern) if not provided.

    Returns:
        dict with keys: success (bool), articles_stored, sentiment (dict or None)
    """
    result = {'success': False, 'articles_stored': 0, 'sentiment': None}

    if symbol in NEWS_EXCLUDED_SYMBOLS:
        logging.debug("News enrichment skipped for excluded symbol: {}".format(symbol))
        return result

    # Fetch news from Alpha Vantage
    news_data = fetch_symbol_news(
        symbol,
        lookback_days=DEFAULT_LOOKBACK_DAYS,
        limit=DEFAULT_ARTICLE_LIMIT,
        av_client=av_client
    )

    if not news_data:
        logging.debug("No news data returned for {}".format(symbol))
        return result

    # Store raw articles in database
    db_path = _get_db_path()
    store_result = store_news_data(symbol, news_data, db_path)
    result['articles_stored'] = store_result['articles_stored']

    # Compute sentiment summary
    summary = compute_sentiment_summary(symbol, news_data)
    result['sentiment'] = summary

    if summary:
        # Update the watchlist row with sentiment data
        target_date = entry_date or now_eastern().strftime('%Y-%m-%d')
        update_sql = """
            UPDATE flow_watchlist_daily
            SET news_sentiment_score = ?,
                news_sentiment_label = ?,
                news_article_count = ?
            WHERE symbol = ? AND entry_date = ?
        """
        update_params = (
            summary['news_sentiment_score'],
            summary['news_sentiment_label'],
            summary['news_article_count'],
            symbol,
            target_date
        )

        try:
            if storage is not None:
                # Use FlowMonitorStorage retry logic (called from fm_main.py)
                def update_op(conn):
                    conn.execute(update_sql, update_params)
                    conn.commit()
                    return True
                storage._execute_with_retry(update_op)
            else:
                # Direct connection (CLI / backfill usage)
                db_path = _get_db_path()
                with sqlite3.connect(db_path, timeout=30) as conn:
                    conn.execute(update_sql, update_params)
                    conn.commit()

            result['success'] = True
            logging.debug("News enrichment for {}: score={}, label='{}', articles={}".format(
                symbol,
                summary['news_sentiment_score'],
                summary['news_sentiment_label'],
                summary['news_article_count']
            ))

        except Exception as e:
            logging.error("Failed to update watchlist with sentiment for {}: {}".format(symbol, e))
    else:
        # No sentiment for this specific symbol (articles may mention other tickers)
        result['success'] = True  # Not a failure — just no relevant sentiment
        logging.debug("No symbol-specific sentiment found for {}".format(symbol))

    return result


def enrich_watchlist_batch(symbols, storage=None, entry_date=None):
    """Enrich multiple watchlist symbols with news sentiment.

    Called by fm_main.py after update_daily_watchlist() creates new entries.
    Respects the daily API budget (25 calls) — stops enriching when exhausted.

    Args:
        symbols: List of symbols to enrich
        storage: FlowMonitorStorage instance. If None, uses direct sqlite3.
        entry_date: Target date (YYYY-MM-DD) for watchlist rows. Defaults to today.

    Returns:
        dict: {enriched: int, skipped: int, failed: int, budget_exhausted: bool}
    """
    stats = {
        'enriched': 0,
        'skipped': 0,
        'failed': 0,
        'budget_exhausted': False,
        'details': [],  # Per-symbol results: [{symbol, score, label, articles}, ...]
    }

    if not symbols:
        return stats

    # Create a single AV client to share across all calls (shares rate limiter)
    try:
        av_client = _create_av_client()
    except Exception as e:
        logging.error("Failed to create AV client for news enrichment: {}".format(e))
        stats['failed'] = len(symbols)
        return stats

    for symbol in symbols:
        # Check budget before each call
        try:
            usage = av_client.api.get_usage_stats()
            if not usage['can_make_request']:
                logging.warning("News enrichment budget exhausted after {} symbols "
                                "({} remaining)".format(stats['enriched'],
                                                        len(symbols) - stats['enriched'] - stats['skipped']))
                stats['budget_exhausted'] = True
                stats['skipped'] += len(symbols) - stats['enriched'] - stats['skipped'] - stats['failed']
                break
        except Exception:
            pass  # If we can't check, try anyway — the API client will enforce limits

        if symbol in NEWS_EXCLUDED_SYMBOLS:
            stats['skipped'] += 1
            continue

        try:
            result = enrich_watchlist_symbol(symbol, storage, av_client=av_client,
                                                   entry_date=entry_date)
            if result['success']:
                stats['enriched'] += 1
                # Capture per-symbol detail for console display
                sentiment = result.get('sentiment')
                if sentiment:
                    stats['details'].append({
                        'symbol': symbol,
                        'score': sentiment['news_sentiment_score'],
                        'label': sentiment['news_sentiment_label'],
                        'articles': sentiment['news_article_count'],
                    })
                else:
                    stats['details'].append({
                        'symbol': symbol,
                        'score': None,
                        'label': 'No articles',
                        'articles': 0,
                    })
            else:
                # Check if failure was due to server-side rate limiting
                if getattr(av_client.api, 'server_rate_limited', False):
                    stats['budget_exhausted'] = True
                    stats['skipped'] += 1
                    remaining = len(symbols) - stats['enriched'] - stats['skipped'] - stats['failed']
                    if remaining > 0:
                        stats['skipped'] += remaining
                    logging.warning("Alpha Vantage server rate limit detected after {} — "
                                    "skipping remaining symbols".format(symbol))
                    break
                stats['failed'] += 1
        except Exception as e:
            logging.error("News enrichment error for {}: {}".format(symbol, e))
            stats['failed'] += 1

    logging.debug("News enrichment batch complete: {} enriched, {} skipped, {} failed, budget_exhausted={}".format(
        stats['enriched'], stats['skipped'], stats['failed'], stats['budget_exhausted']))

    # AUTOFIX: Queue for batch investigation only when an all-failed batch is
    # actually evidence of a systemic issue (API down, rate limiting, config
    # problem). See AUTOFIX_MIN_ATTEMPTED / AUTOFIX_MAX_CONSECUTIVE_ALL_FAILED
    # for why a bare "everything failed" check is not enough.
    # Budget exhaustion is expected behavior and NOT queued as an error.
    global _consecutive_all_failed_batches

    attempted = len(symbols) - stats['skipped']
    all_failed = attempted > 0 and stats['enriched'] == 0 and stats['failed'] > 0

    if stats['enriched'] > 0:
        _consecutive_all_failed_batches = 0
    elif all_failed:
        _consecutive_all_failed_batches += 1

    systemic = all_failed and (
        attempted >= AUTOFIX_MIN_ATTEMPTED
        or _consecutive_all_failed_batches >= AUTOFIX_MAX_CONSECUTIVE_ALL_FAILED
    )

    if systemic:
        try:
            from tools.autofix import queue_error
            queue_error(
                error_type='news_enrichment_all_failed',
                context={
                    'symbols_attempted': attempted,
                    'symbols_failed': stats['failed'],
                    'symbols_skipped': stats['skipped'],
                    'consecutive_all_failed_batches': _consecutive_all_failed_batches,
                    'budget_exhausted': stats['budget_exhausted'],
                    'trade_date': now_eastern().strftime('%Y-%m-%d'),
                    'hint': 'All news API calls failed. Check Alpha Vantage API status, '
                            'IP rate limiting, or API key validity.',
                },
                severity='WARNING'
            )
        except Exception:
            pass  # Autofix queueing itself should never break the pipeline
    elif all_failed:
        # Below the alarm threshold, but never fail silently — leave a trail so a
        # slow-burn failure is visible in the orchestrator log before it alarms.
        logging.warning("News enrichment: all {} attempted symbol(s) failed "
                        "(consecutive all-failed batches: {}/{}) — below autofix "
                        "threshold, not queued".format(
                            attempted, _consecutive_all_failed_batches,
                            AUTOFIX_MAX_CONSECUTIVE_ALL_FAILED))

    return stats


# ---------------------------------------------------------------------------
# API budget helper
# ---------------------------------------------------------------------------

def get_budget_status(av_client=None):
    """Check remaining Alpha Vantage API budget for today.

    Returns:
        dict: {used: int, remaining: int, can_make_request: bool}
    """
    if av_client is None:
        av_client = _create_av_client()

    usage = av_client.api.get_usage_stats()
    return {
        'used': usage['daily_requests_used'],
        'remaining': usage['daily_requests_remaining'],
        'can_make_request': usage['can_make_request'],
    }


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for ad-hoc news collection and research."""
    parser = argparse.ArgumentParser(
        description="News Sentiment Tool - fetch, store, and analyze financial news",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/news_sentiment.py --symbol NVDA
  python tools/news_sentiment.py --symbols NVDA,GOOG,MSTR
  python tools/news_sentiment.py --topic technology
  python tools/news_sentiment.py --symbol NVDA --from 2026-01-30 --to 2026-02-06
  python tools/news_sentiment.py --symbol NVDA --lookback 7
  python tools/news_sentiment.py --budget
        """
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument('--symbol', help='Single symbol to collect news for')
    source.add_argument('--symbols', help='Comma-separated list of symbols')
    source.add_argument('--topic', help='Topic (technology, earnings, economy_macro, etc.)')
    source.add_argument('--budget', action='store_true', help='Show API budget status and exit')
    source.add_argument('--enrich-date', metavar='YYYY-MM-DD',
                        help='Backfill: fetch news and update flow_watchlist_daily for this date')

    parser.add_argument('--lookback', type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help='Days to look back (default: {})'.format(DEFAULT_LOOKBACK_DAYS))
    parser.add_argument('--limit', type=int, default=DEFAULT_ARTICLE_LIMIT,
                        help='Max articles per query (default: {})'.format(DEFAULT_ARTICLE_LIMIT))
    parser.add_argument('--from', dest='time_from', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to', dest='time_to', help='End date (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without API calls')
    parser.add_argument('--no-store', action='store_true', help='Fetch and display but do not store in database')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    # Logging setup
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    # Budget check
    if args.budget:
        status = get_budget_status()
        print("Alpha Vantage API Budget:")
        print("  Used today:  {}".format(status['used']))
        print("  Remaining:   {}".format(status['remaining']))
        print("  Can request: {}".format(status['can_make_request']))
        return

    # --enrich-date: backfill mode — pull symbols from watchlist and enrich
    if args.enrich_date:
        db_path = _get_db_path()
        with sqlite3.connect(db_path, timeout=30) as conn:
            rows = conn.execute(
                "SELECT symbol FROM flow_watchlist_daily WHERE entry_date = ? ORDER BY symbol",
                (args.enrich_date,)
            ).fetchall()

        if not rows:
            print("No watchlist entries found for {}".format(args.enrich_date))
            return

        symbols = [r[0] for r in rows]
        excluded = [s for s in symbols if s in NEWS_EXCLUDED_SYMBOLS]
        to_enrich = [s for s in symbols if s not in NEWS_EXCLUDED_SYMBOLS]

        print("Watchlist entries for {}: {} symbols ({} to enrich, {} excluded)".format(
            args.enrich_date, len(symbols), len(to_enrich), len(excluded)))
        if excluded:
            print("  Excluded: {}".format(', '.join(sorted(excluded))))
        print()

        if args.dry_run:
            for s in to_enrich:
                print("  [DRY RUN] Would enrich: {}".format(s))
            return

        stats = enrich_watchlist_batch(to_enrich, storage=None, entry_date=args.enrich_date)
        print()
        print("Results: {} enriched, {} skipped, {} failed".format(
            stats['enriched'], stats['skipped'], stats['failed']))
        if stats['budget_exhausted']:
            print("  (API budget exhausted before completing all symbols)")

        status = get_budget_status()
        print("API Budget after: {} used, {} remaining".format(status['used'], status['remaining']))
        return

    # Require at least one source argument
    if not args.symbol and not args.symbols and not args.topic:
        parser.print_help()
        return

    av_client = _create_av_client()

    # Show budget before starting
    status = get_budget_status(av_client)
    print("API Budget: {} used, {} remaining".format(status['used'], status['remaining']))
    print()

    # Convert date formats if provided
    time_from_str = None
    time_to_str = None
    if args.time_from:
        time_from_str = args.time_from.replace('-', '') + 'T0000'
    if args.time_to:
        time_to_str = args.time_to.replace('-', '') + 'T2359'

    # Determine lookback (date range overrides --lookback)
    lookback = args.lookback
    if time_from_str:
        lookback = None  # time_from is explicit, don't also apply lookback

    # Collect symbols to process
    symbols_to_process = []
    if args.symbol:
        symbols_to_process = [args.symbol.upper()]
    elif args.symbols:
        symbols_to_process = [s.strip().upper() for s in args.symbols.split(',')]

    # Symbol-based collection
    if symbols_to_process:
        for symbol in symbols_to_process:
            if args.dry_run:
                print("[DRY RUN] Would fetch news for {} (lookback: {} days)".format(
                    symbol, lookback or 'date range'))
                continue

            # Use explicit time range if provided, otherwise use lookback
            if time_from_str:
                news_data = av_client.get_symbol_news(
                    symbol=symbol, limit=args.limit,
                    max_age_seconds=300,
                    time_from=time_from_str, time_to=time_to_str
                )
            else:
                news_data = fetch_symbol_news(symbol, lookback_days=lookback,
                                              limit=args.limit, av_client=av_client)

            if not news_data or not news_data.get('articles'):
                print("{}: No articles found".format(symbol))
                continue

            article_count = len(news_data['articles'])

            # Store unless --no-store
            if not args.no_store:
                stored = store_news_data(symbol, news_data)
                print("{}: {} articles fetched, {} new stored, {} sentiment records".format(
                    symbol, article_count, stored['articles_stored'], stored['sentiment_stored']))
            else:
                print("{}: {} articles fetched (not stored)".format(symbol, article_count))

            # Always show sentiment summary
            summary = compute_sentiment_summary(symbol, news_data)
            if summary:
                print("  Sentiment: {} (score: {}, {} articles)".format(
                    summary['news_sentiment_label'],
                    summary['news_sentiment_score'],
                    summary['news_article_count']))
            else:
                print("  Sentiment: No symbol-specific sentiment data")

            print()

    # Topic-based collection
    elif args.topic:
        if args.dry_run:
            print("[DRY RUN] Would fetch topic '{}' (lookback: {} days)".format(
                args.topic, lookback or 'date range'))
            return

        if time_from_str:
            news_data = av_client.get_topic_news(
                topic=args.topic, limit=args.limit,
                max_age_seconds=300,
                time_from=time_from_str, time_to=time_to_str
            )
        else:
            news_data = fetch_topic_news(args.topic, lookback_days=lookback,
                                         limit=args.limit, av_client=av_client)

        if not news_data or not news_data.get('articles'):
            print("No articles found for topic '{}'".format(args.topic))
            return

        article_count = len(news_data['articles'])

        if not args.no_store:
            stored = store_news_data(args.topic, news_data)
            print("Topic '{}': {} articles fetched, {} new stored".format(
                args.topic, article_count, stored['articles_stored']))
        else:
            print("Topic '{}': {} articles fetched (not stored)".format(args.topic, article_count))

    # Show final budget
    if not args.dry_run:
        status = get_budget_status(av_client)
        print("API Budget after: {} used, {} remaining".format(status['used'], status['remaining']))


if __name__ == '__main__':
    main()
