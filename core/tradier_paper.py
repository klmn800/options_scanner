#!/usr/bin/env python3
"""
Tradier Paper Broker
====================
Sandbox-only broker client for paper trading. Wraps a `TradierAPI` instance
configured with `sandbox=True` and exposes the order / account / position
endpoints needed by the paper trading platform (docs/_local/paper_trading/PHASE_1_PLAN.md).

Safety:
    Constructor asserts `self.api.sandbox is True`. If `tradier_sandbox.api_key`
    is missing or empty, refuses to instantiate. This is the only class in the
    codebase that places orders against Tradier; restricting it to sandbox
    guarantees we cannot place a live order through this path.

Reuses `TradierAPI._make_request()` so order calls inherit the rate limiter
(`trading_limiter`, 60 req/min) and the existing error handling.

Reads/writes: none directly. All persistence happens in `tools/paper_trading.py`.
Dependencies: core/tradier_api.py
"""

import logging
import re
import time

from core.tradier_api import TradierAPI

logger = logging.getLogger(__name__)

SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1"

# Tradier order tags: letters, digits, hyphen only; max 255 chars.
# Any other char gets mapped to '-'. Underscores in particular fail with
# "Invalid parameter, tag: contains invalid characters."
_TAG_INVALID_CHAR_RE = re.compile(r'[^A-Za-z0-9-]')


def sanitize_tag(tag):
    """Make a tag safe for Tradier's order endpoint.

    Returns the sanitized tag, or None if the input was empty.
    Idempotent: sanitize(sanitize(x)) == sanitize(x).
    """
    if not tag:
        return None
    return _TAG_INVALID_CHAR_RE.sub('-', tag)[:255]


class TradierPaperBroker:
    """Sandbox-only Tradier broker.

    Construct with a parsed `config` dict (the contents of `config.json`).
    Reads `config['tradier_sandbox']` for credentials.
    """

    def __init__(self, config):
        sandbox_cfg = config.get('tradier_sandbox') or {}
        token = sandbox_cfg.get('api_key')
        account_id = sandbox_cfg.get('account_id')

        if not token:
            raise ValueError(
                "tradier_sandbox.api_key is missing or empty in config.json. "
                "Paste a paper-trading token from https://web.tradier.com/user/api."
            )
        if not account_id:
            raise ValueError(
                "tradier_sandbox.account_id is missing or empty in config.json."
            )

        self.api = TradierAPI(token, sandbox=True)
        # Defense in depth — TradierAPI may evolve, this guarantees URL is sandbox
        assert self.api.sandbox is True, "TradierPaperBroker requires sandbox=True"
        assert self.api.base_url == SANDBOX_BASE_URL, (
            "TradierPaperBroker requires sandbox base URL; got {}".format(self.api.base_url)
        )
        self.account_id = account_id

    # ── Account / Balance ────────────────────────────────────────────

    def get_balances(self):
        """GET /accounts/{id}/balances — returns Tradier balances dict.

        Tradier response shape: {'balances': {...}}. We return the full
        response so callers see the wrapper (helps with raw_response_json
        storage). Use `.get('balances', resp)` to unwrap.
        """
        endpoint = "accounts/{}/balances".format(self.account_id)
        return self.api._make_request('GET', endpoint, self.api.standard_data_limiter)

    def get_positions(self):
        """GET /accounts/{id}/positions — Tradier-authoritative position view.

        Tradier returns `{'positions': 'null'}` (yes, the string) when empty,
        or `{'positions': {'position': [{...}, ...]}}` when populated.
        Normalize to a list of position dicts (possibly empty).
        """
        endpoint = "accounts/{}/positions".format(self.account_id)
        resp = self.api._make_request('GET', endpoint, self.api.standard_data_limiter)
        if not resp:
            return []
        positions = resp.get('positions')
        if not positions or positions == 'null':
            return []
        if isinstance(positions, dict):
            pos = positions.get('position')
            if pos is None:
                return []
            if isinstance(pos, list):
                return pos
            return [pos]
        return []

    # ── Orders ───────────────────────────────────────────────────────

    def get_orders(self, status_filter=None):
        """GET /accounts/{id}/orders — list all orders.

        Args:
            status_filter: optional set/list of statuses to keep (e.g. {'open', 'partially_filled'}).
        """
        endpoint = "accounts/{}/orders".format(self.account_id)
        params = {'includeTags': 'true'}
        resp = self.api._make_request('GET', endpoint, self.api.standard_data_limiter, params=params)
        if not resp:
            return []
        orders = resp.get('orders')
        if not orders or orders == 'null':
            return []
        order_list = []
        if isinstance(orders, dict):
            o = orders.get('order')
            if o is None:
                return []
            order_list = o if isinstance(o, list) else [o]
        if status_filter:
            wanted = {s.lower() for s in status_filter}
            order_list = [o for o in order_list if (o.get('status') or '').lower() in wanted]
        return order_list

    def get_order(self, order_id):
        """GET /accounts/{id}/orders/{order_id} — single order detail."""
        endpoint = "accounts/{}/orders/{}".format(self.account_id, order_id)
        params = {'includeTags': 'true'}
        resp = self.api._make_request('GET', endpoint, self.api.standard_data_limiter, params=params)
        if not resp:
            return None
        order = resp.get('order')
        if order == 'null':
            return None
        return order

    def cancel_order(self, order_id):
        """DELETE /accounts/{id}/orders/{order_id}.

        TradierAPI._make_request supports only GET/POST, so we call the
        underlying session directly. Reuses the same rate limiter and
        response handler.
        """
        endpoint = "accounts/{}/orders/{}".format(self.account_id, order_id)
        url = "{}/{}".format(self.api.base_url, endpoint)
        self.api.trading_limiter.wait_if_needed()
        self.api.total_requests += 1
        self.api.requests_by_method.setdefault('DELETE', 0)
        self.api.requests_by_method['DELETE'] += 1
        try:
            response = self.api.session.delete(url)
        except Exception as e:
            logger.error("DELETE %s failed: %s", url, e)
            return None
        if response.status_code == 200:
            return response.json()
        logger.error(
            "Cancel order failed for %s: %s - %s",
            order_id, response.status_code, response.text[:200]
        )
        return None

    # ── Order Placement ──────────────────────────────────────────────

    def place_equity_order(self, symbol, side, qty, type_, duration='day',
                           price=None, stop=None, preview=False, tag=None,
                           source_event_id=None):
        """POST /accounts/{id}/orders (class=equity).

        Args:
            symbol: ticker, e.g. 'SPY'
            side: 'buy' / 'sell' / 'sell_short' / 'buy_to_cover'
            qty: shares (int)
            type_: 'market' / 'limit' / 'stop' / 'stop_limit'
            duration: 'day' / 'gtc' / 'pre' / 'post'
            price: limit price, required if type_ is 'limit' or 'stop_limit'
            stop: stop price, required if type_ is 'stop' or 'stop_limit'
            preview: True to validate only (Tradier returns cost/commission preview)
            tag: optional Tradier order tag (Tradier max 255 chars, alphanumeric+`-_`)
            source_event_id: not sent to Tradier — caller persists separately

        Returns:
            Tradier response dict (typically {'order': {'id': ..., 'status': 'ok', ...}})
            or {'order': {..., 'status': 'rejected', 'reason': ...}}.
        """
        endpoint = "accounts/{}/orders".format(self.account_id)
        data = {
            'class': 'equity',
            'symbol': symbol.upper(),
            'side': side,
            'quantity': int(qty),
            'type': type_,
            'duration': duration,
        }
        if price is not None:
            data['price'] = price
        if stop is not None:
            data['stop'] = stop
        if preview:
            data['preview'] = 'true'
        if tag:
            data['tag'] = sanitize_tag(tag)
        return self.api._make_request('POST', endpoint, self.api.trading_limiter, data=data)

    def place_option_order(self, underlying, option_symbol, side, qty, type_,
                           duration='day', price=None, stop=None, preview=False,
                           tag=None, source_event_id=None):
        """POST /accounts/{id}/orders (class=option).

        Args:
            underlying: underlying ticker (e.g. 'SPY')
            option_symbol: OCC option symbol (e.g. 'SPY260619C00500000')
            side: 'buy_to_open' / 'sell_to_open' / 'buy_to_close' / 'sell_to_close'
            qty: contracts (int)
            type_: 'market' / 'limit' / 'stop' / 'stop_limit'
            duration: 'day' / 'gtc'
            price: limit price, required if type_ is 'limit' or 'stop_limit'
            stop: stop price, required if type_ is 'stop' or 'stop_limit'
            preview: True to validate only
            tag: optional Tradier order tag
            source_event_id: not sent to Tradier; caller persists separately

        Returns: Tradier response dict.
        """
        endpoint = "accounts/{}/orders".format(self.account_id)
        data = {
            'class': 'option',
            'symbol': underlying.upper(),
            'option_symbol': option_symbol.upper(),
            'side': side,
            'quantity': int(qty),
            'type': type_,
            'duration': duration,
        }
        if price is not None:
            data['price'] = price
        if stop is not None:
            data['stop'] = stop
        if preview:
            data['preview'] = 'true'
        if tag:
            data['tag'] = sanitize_tag(tag)
        return self.api._make_request('POST', endpoint, self.api.trading_limiter, data=data)

    # ── Quotes (delegated) ───────────────────────────────────────────

    def get_quote(self, symbol):
        """Single-symbol quote via the underlying TradierAPI."""
        resp = self.api.get_quotes(symbol)
        if not resp:
            return None
        quotes = resp.get('quotes') or {}
        q = quotes.get('quote')
        if q is None:
            return None
        if isinstance(q, list):
            return q[0] if q else None
        return q

    def get_option_quote(self, option_symbol):
        """OCC-symbol quote. Tradier accepts OCC symbols on /markets/quotes."""
        return self.get_quote(option_symbol)
