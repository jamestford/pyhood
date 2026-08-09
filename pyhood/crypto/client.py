"""CryptoClient — Robinhood Crypto Trading API v2 client.

Handles authentication, rate limiting, pagination, and typed responses.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import requests

from pyhood.crypto.auth import sign_request
from pyhood.crypto.credentials import load_credentials
from pyhood.crypto.models import (
    CryptoAccount,
    CryptoCandle,
    CryptoHolding,
    CryptoOrder,
    CryptoQuote,
    EstimatedPrice,
    TradingPair,
)
from pyhood.crypto.urls import (
    CRYPTO_ACCOUNTS,
    CRYPTO_BASE,
    CRYPTO_BEST_BID_ASK,
    CRYPTO_ESTIMATED_PRICE,
    CRYPTO_HOLDINGS,
    CRYPTO_ORDERS,
    CRYPTO_TRADING_PAIRS,
)
from pyhood.exceptions import APIError, AuthError, RateLimitError

logger = logging.getLogger("pyhood.crypto")


class TokenBucket:
    """Rate limiting using token bucket algorithm.

    Robinhood Crypto API allows 100 requests/minute with 300 burst capacity.
    """

    def __init__(self, rate: float = 100, capacity: float = 300):
        self.rate = rate / 60.0  # Convert to tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate limited."""
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def wait_time(self) -> float:
        """Return seconds to wait until 1 token is available."""
        return max(0, (1 - self.tokens) / self.rate)


class CryptoClient:
    """Robinhood Crypto Trading API v2 client.

    Handles ED25519 authentication, rate limiting, and pagination.

    Usage:
        client = CryptoClient(api_key, private_key_base64)
        account = client.get_account()
        quote = client.get_best_bid_ask("BTC-USD")
    """

    def __init__(
        self,
        api_key: str | None = None,
        private_key_base64: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize crypto client with API credentials.

        Args:
            api_key: Robinhood Crypto API key. If omitted, resolved from the
                RH_CRYPTO_API_KEY environment variable or ~/.pyhood/crypto.env.
            private_key_base64: Base64-encoded ED25519 private key. Resolved
                the same way when omitted.
            timeout: Request timeout in seconds

        Raises:
            FileNotFoundError: If credentials cannot be resolved.
        """
        api_key, private_key_base64 = load_credentials(api_key, private_key_base64)
        self.api_key = api_key
        self.private_key_base64 = private_key_base64
        self.timeout = timeout
        self.base_url = CRYPTO_BASE
        self.rate_limiter = TokenBucket()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'pyhood/0.1.0',
            'Content-Type': 'application/json',
        })

    def make_request(
        self,
        method: str,
        path: str,
        body: str = "",
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Crypto API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., '/api/v2/crypto/trading/accounts/')
            body: Request body as JSON string
            params: Query parameters
            retries: Number of retries on rate limit/server errors

        Returns:
            Parsed JSON response

        Raises:
            RateLimitError: Rate limited and no retries left
            AuthError: Authentication failed
            APIError: API returned an error
        """
        # Rate limiting
        if not self.rate_limiter.consume():
            wait_time = self.rate_limiter.wait_time()
            if retries > 0:
                logger.debug(f"Rate limited, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
                return self.make_request(method, path, body, params, retries - 1)
            else:
                raise RateLimitError(f"Rate limited, retry after {wait_time:.1f}s", wait_time)

        # The signature covers the path *including* the query string, so the
        # query is folded in here rather than passed to requests separately —
        # signing the bare path while sending one with a query produced an
        # authentication failure on every parameterised endpoint.
        signed_path = path
        if params:
            query = urlencode(params, doseq=True)
            if query:
                separator = "&" if "?" in signed_path else "?"
                signed_path = f"{signed_path}{separator}{query}"
            params = None

        # Sign request
        try:
            api_key_header, signature, timestamp = sign_request(
                self.api_key, self.private_key_base64, method.upper(), signed_path, body
            )
        except ValueError as e:
            raise AuthError(f"Failed to sign request: {e}") from e

        # Prepare request
        url = self.base_url.rstrip('/') + '/' + signed_path.lstrip('/')
        headers = {
            'x-api-key': api_key_header,
            'x-signature': signature,
            'x-timestamp': timestamp,
        }

        # Make request
        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                headers=headers,
                data=body if body else None,
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            if retries > 0:
                logger.warning(f"Request failed ({e}), retrying...")
                time.sleep(1)
                return self.make_request(method, path, body, params, retries - 1)
            raise APIError(f"Request failed: {e}") from e

        # Handle response
        if response.status_code == 429:
            retry_after = float(response.headers.get('Retry-After', 60))
            if retries > 0:
                logger.warning(f"Rate limited by server, waiting {retry_after}s")
                time.sleep(retry_after)
                return self.make_request(method, path, body, params, retries - 1)
            else:
                raise RateLimitError("Rate limited by server", retry_after)

        if response.status_code == 401:
            raise AuthError("Authentication failed - check API key and signature")

        if response.status_code == 403:
            raise AuthError("Access forbidden - check API permissions")

        if not response.ok:
            try:
                error_data = response.json()
                error_msg = error_data.get('message', f'HTTP {response.status_code}')
            except Exception:
                error_msg = f'HTTP {response.status_code}'
            raise APIError(
                error_msg, response.status_code,
                error_data if "error_data" in locals() else None,
            )

        try:
            return response.json()
        except json.JSONDecodeError as e:
            raise APIError(f"Invalid JSON response: {e}") from e

    def _paginate(
        self, initial_path: str, params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Handle cursor-based pagination for list endpoints.

        Args:
            initial_path: Initial API path
            params: Query parameters

        Returns:
            List of all items across pages
        """
        all_items = []
        path = initial_path
        request_params = params or {}

        while path:
            data = self.make_request('GET', path, params=request_params)

            # Add items from this page
            if 'results' in data:
                all_items.extend(data['results'])
            elif isinstance(data, list):
                all_items.extend(data)
            else:
                all_items.append(data)

            # Get next page URL
            next_url = data.get('next')
            if next_url:
                # Extract path with query string from next URL
                parsed = urlparse(next_url)
                query = f"?{parsed.query}" if parsed.query else ""
                path = f"{parsed.path}{query}"
                # Reset params - pagination URLs include their own query params
                request_params = {}
            else:
                path = None

        return all_items

    # ── Account ──────────────────────────────────────────────────────────

    def get_account(self) -> CryptoAccount:
        """Get crypto trading account information.

        Returns:
            CryptoAccount with account details
        """
        path = CRYPTO_ACCOUNTS.replace(CRYPTO_BASE, '')
        data = self.make_request('GET', path)

        # Handle both single account and list responses
        if isinstance(data, list) and data:
            account_data = data[0]
        elif 'results' in data and data['results']:
            account_data = data['results'][0]
        else:
            account_data = data

        return CryptoAccount(
            account_number=account_data.get('account_number', ''),
            buying_power=float(account_data.get('buying_power', 0)),
            status=account_data.get('status', ''),
            fee_tier=account_data.get('fee_tier', ''),
        )

    # ── Market Data ──────────────────────────────────────────────────────

    def get_trading_pairs(self, *symbols: str) -> list[TradingPair]:
        """Get trading pair information for crypto symbols.

        Args:
            *symbols: Crypto symbols (e.g., 'BTC-USD', 'ETH-USD')

        Returns:
            List of TradingPair objects
        """
        path = CRYPTO_TRADING_PAIRS.replace(CRYPTO_BASE, '')
        params = {}
        if symbols:
            params['symbols'] = ','.join(symbols)

        items = self._paginate(path, params)

        trading_pairs = []
        for item in items:
            trading_pairs.append(TradingPair(
                symbol=item.get('symbol', ''),
                tradable=item.get('tradable', False),
                min_order_size=float(item.get('min_order_size', 0)),
                max_order_size=float(item.get('max_order_size', 0)),
                price_increment=float(item.get('price_increment', 0)),
                quantity_increment=float(item.get('quantity_increment', 0)),
                base_currency=item.get('base_currency', ''),
                quote_currency=item.get('quote_currency', ''),
            ))

        return trading_pairs

    def get_best_bid_ask(self, *symbols: str) -> list[CryptoQuote]:
        """Get best bid/ask prices for crypto symbols.

        Args:
            *symbols: Crypto symbols (e.g., 'BTC-USD', 'ETH-USD')

        Returns:
            List of CryptoQuote objects
        """
        path = CRYPTO_BEST_BID_ASK.replace(CRYPTO_BASE, '')
        # The endpoint takes `symbol` repeated, not a comma-joined `symbols`:
        # sending `symbols=` is rejected with "Malformed symbol parameter".
        params: dict[str, Any] = {}
        if symbols:
            params['symbol'] = list(symbols)

        items = self._paginate(path, params)

        quotes = []
        for item in items:
            from datetime import datetime
            timestamp = datetime.fromisoformat(item.get('timestamp', '').replace('Z', '+00:00'))

            quotes.append(CryptoQuote(
                symbol=item.get('symbol', ''),
                bid=float(item.get('bid', 0) or 0),
                ask=float(item.get('ask', 0) or 0),
                timestamp=timestamp,
            ))

        return quotes

    def get_estimated_price(self, symbol: str, side: str, quantity: float) -> EstimatedPrice:
        """Get estimated price for a crypto trade.

        Args:
            symbol: Crypto symbol (e.g., 'BTC-USD')
            side: 'buy' or 'sell'
            quantity: Trade quantity

        Returns:
            EstimatedPrice object
        """
        path = CRYPTO_ESTIMATED_PRICE.replace(CRYPTO_BASE, '')
        params = {
            'symbol': symbol,
            'side': side,
            'quantity': str(quantity),
        }

        response = self.make_request('GET', path, params=params)
        # The estimate is wrapped in a results list, as with the other
        # marketdata endpoints.
        results = response.get('results') if isinstance(response, dict) else None
        data = results[0] if isinstance(results, list) and results else response

        return EstimatedPrice(
            symbol=data.get('symbol', symbol),
            side=data.get('side', side),
            quantity=float(data.get('quantity', quantity)),
            # The endpoint returns whichever side was asked for, as `bid` or
            # `ask`, and names the fee `est_fee`.
            bid_price=float(data.get('bid', data.get('bid_price', 0)) or 0),
            ask_price=float(data.get('ask', data.get('ask_price', 0)) or 0),
            fee=float(data.get('est_fee', data.get('fee', 0)) or 0),
        )

    # ── Historicals ──────────────────────────────────────────────────────

    def get_historicals(
        self,
        symbol: str,
        interval: str = "hour",
        span: str = "week",
    ) -> list[CryptoCandle]:
        """Deprecated — the Crypto Trading API has no historicals endpoint.

        Raises:
            APIError: Always.

        Verified 2026-08-09: every candidate path returns 404
        (`marketdata/historicals/`, `marketdata/candles/`,
        `trading/historicals/`, on both `/api/v1/` and `/api/v2/`), and the
        endpoint is absent from Robinhood's published OpenAPI spec.

        For crypto price history, use the unofficial endpoints via
        `PyhoodClient` rather than the official Crypto Trading API.
        """
        raise APIError(
            "The Crypto Trading API has no historicals endpoint — every "
            "candidate path returns 404 and it is absent from Robinhood's "
            "published spec. Use the unofficial API for crypto price history."
        )

    def get_holdings(self, account_number: str, *asset_codes: str) -> list[CryptoHolding]:
        """Get crypto holdings for account.

        Args:
            account_number: Crypto account number
            *asset_codes: Asset codes to filter by (e.g., 'BTC', 'ETH')

        Returns:
            List of CryptoHolding objects
        """
        path = CRYPTO_HOLDINGS.replace(CRYPTO_BASE, '')
        params = {'account_number': account_number}
        if asset_codes:
            params['asset_codes'] = ','.join(asset_codes)

        items = self._paginate(path, params)

        holdings = []
        for item in items:
            holdings.append(CryptoHolding(
                asset_code=item.get('asset_code', ''),
                quantity=float(item.get('quantity', 0)),
                available_quantity=float(item.get('available_quantity', 0)),
            ))

        return holdings

    # ── Orders ───────────────────────────────────────────────────────────

    def place_order(
        self,
        account_number: str,
        side: str,
        order_type: str,
        symbol: str,
        order_config: dict[str, Any],
    ) -> CryptoOrder:
        """Place a crypto order.

        Args:
            account_number: Crypto account number
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            symbol: Crypto symbol (e.g., 'BTC-USD')
            order_config: Order-specific configuration

        Returns:
            CryptoOrder object
        """
        path = CRYPTO_ORDERS.replace(CRYPTO_BASE, '')

        payload = {
            'account_number': account_number,
            'side': side,
            'type': order_type,
            'symbol': symbol,
            **order_config,
        }

        body = json.dumps(payload)
        data = self.make_request('POST', path, body=body)

        from datetime import datetime
        created_at = datetime.fromisoformat(data.get('created_at', '').replace('Z', '+00:00'))
        updated_at = datetime.fromisoformat(data.get('updated_at', '').replace('Z', '+00:00'))

        return CryptoOrder(
            order_id=data.get('id', ''),
            client_order_id=data.get('client_order_id'),
            side=data.get('side', side),
            order_type=data.get('type', order_type),
            symbol=data.get('symbol', symbol),
            status=data.get('status', ''),
            price=float(data['price']) if data.get('price') is not None else None,
            quantity=float(data.get('quantity', 0)),
            filled_quantity=float(data.get('filled_quantity', 0)),
            remaining_quantity=float(data.get('remaining_quantity', 0)),
            average_filled_price=(
                float(data['average_filled_price'])
                if data.get('average_filled_price') is not None else None
            ),
            fee=float(data['fee']) if data.get('fee') is not None else None,
            created_at=created_at,
            updated_at=updated_at,
        )

    def get_order(self, account_number: str, order_id: str) -> CryptoOrder:
        """Get a specific crypto order.

        Args:
            account_number: Crypto account number
            order_id: Order ID

        Returns:
            CryptoOrder object
        """
        path = f"{CRYPTO_ORDERS.replace(CRYPTO_BASE, '')}{order_id}/"
        params = {'account_number': account_number}

        data = self.make_request('GET', path, params=params)

        from datetime import datetime
        created_at = datetime.fromisoformat(data.get('created_at', '').replace('Z', '+00:00'))
        updated_at = datetime.fromisoformat(data.get('updated_at', '').replace('Z', '+00:00'))

        return CryptoOrder(
            order_id=data.get('id', order_id),
            client_order_id=data.get('client_order_id'),
            side=data.get('side', ''),
            order_type=data.get('type', ''),
            symbol=data.get('symbol', ''),
            status=data.get('status', ''),
            price=float(data['price']) if data.get('price') is not None else None,
            quantity=float(data.get('quantity', 0)),
            filled_quantity=float(data.get('filled_quantity', 0)),
            remaining_quantity=float(data.get('remaining_quantity', 0)),
            average_filled_price=(
                float(data['average_filled_price'])
                if data.get('average_filled_price') is not None else None
            ),
            fee=float(data['fee']) if data.get('fee') is not None else None,
            created_at=created_at,
            updated_at=updated_at,
        )

    def get_orders(self, account_number: str) -> list[CryptoOrder]:
        """Get all crypto orders for account.

        Args:
            account_number: Crypto account number

        Returns:
            List of CryptoOrder objects
        """
        path = CRYPTO_ORDERS.replace(CRYPTO_BASE, '')
        params = {'account_number': account_number}

        items = self._paginate(path, params)

        orders = []
        for item in items:
            from datetime import datetime
            created_at = datetime.fromisoformat(item.get('created_at', '').replace('Z', '+00:00'))
            updated_at = datetime.fromisoformat(item.get('updated_at', '').replace('Z', '+00:00'))

            orders.append(CryptoOrder(
                order_id=item.get('id', ''),
                client_order_id=item.get('client_order_id'),
                side=item.get('side', ''),
                order_type=item.get('type', ''),
                symbol=item.get('symbol', ''),
                status=item.get('status', ''),
                price=float(item['price']) if item.get('price') is not None else None,
                quantity=float(item.get('quantity', 0)),
                filled_quantity=float(item.get('filled_quantity', 0)),
                remaining_quantity=float(item.get('remaining_quantity', 0)),
                average_filled_price=(
                    float(item['average_filled_price'])
                    if item.get('average_filled_price') is not None else None
                ),
                fee=float(item['fee']) if item.get('fee') is not None else None,
                created_at=created_at,
                updated_at=updated_at,
            ))

        return orders

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a crypto order.

        Args:
            order_id: Order ID to cancel

        Returns:
            API response data
        """
        path = f"{CRYPTO_ORDERS.replace(CRYPTO_BASE, '')}{order_id}/cancel/"

        data = self.make_request('POST', path)
        return data
