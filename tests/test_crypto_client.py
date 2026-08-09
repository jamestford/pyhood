"""Tests for crypto client module."""

import json
from datetime import datetime

import pytest
import responses

from pyhood.crypto.auth import generate_keypair
from pyhood.crypto.client import CryptoClient, TokenBucket
from pyhood.crypto.models import (
    CryptoAccount,
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


class TestTokenBucket:
    """Test rate limiting token bucket implementation."""

    def test_initial_state(self):
        """Test token bucket starts with full capacity."""
        bucket = TokenBucket(rate=100, capacity=300)
        assert bucket.tokens == 300
        assert bucket.consume(1) is True
        assert bucket.tokens == 299

    def test_rate_limiting(self):
        """Test rate limiting when tokens exhausted."""
        bucket = TokenBucket(rate=100, capacity=2)

        # Consume all tokens
        assert bucket.consume(1) is True
        assert bucket.consume(1) is True
        assert bucket.consume(1) is False  # Should be rate limited

        # Should suggest wait time
        wait_time = bucket.wait_time()
        assert wait_time > 0

    def test_token_replenishment(self):
        """Test tokens replenish over time."""
        bucket = TokenBucket(rate=60, capacity=2)  # 1 token per second

        # Exhaust tokens
        bucket.consume(2)
        assert bucket.consume(1) is False

        # Mock time passing
        bucket.last_update -= 1.1  # 1.1 seconds ago
        assert bucket.consume(1) is True  # Should have 1 token replenished


class TestCryptoClient:
    """Test crypto client functionality."""

    def setup_method(self):
        """Set up test client with mock credentials."""
        self.api_key = "test-api-key"
        self.private_key, _ = generate_keypair()
        self.client = CryptoClient(self.api_key, self.private_key, timeout=5)
        self.client.rate_limiter.tokens = 999999
        self.client.rate_limiter.capacity = 999999

    # Shape captured from the live API on 2026-08-09. Fees arrive as a
    # `fee_tier_status` object; there is no `fee_tier` key.
    ACCOUNT_PAYLOAD = {
        "account_number": "12345",
        "buying_power": "1000.50",
        "buying_power_currency": "USD",
        "status": "active",
        "account_type": "individual",
        "is_api_tradable": True,
        "fee_tier_status": {
            "fee_ratio": 0.0095,
            "thirty_day_volume": 0.0,
            "next_fee_tier_ratio": 0.0025,
            "next_fee_tier_threshold": 50000.0,
        },
    }

    @responses.activate
    def test_get_account(self):
        """Test getting crypto account information."""
        responses.add(
            responses.GET, CRYPTO_ACCOUNTS, json=self.ACCOUNT_PAYLOAD, status=200,
        )

        account = self.client.get_account()

        assert isinstance(account, CryptoAccount)
        assert account.account_number == "12345"
        assert account.buying_power == 1000.50
        assert account.status == "active"
        assert account.api_tradable is True

    @responses.activate
    def test_fee_tier_is_read_from_fee_tier_status(self):
        """The old code read a `fee_tier` key the API never sends."""
        responses.add(
            responses.GET, CRYPTO_ACCOUNTS, json=self.ACCOUNT_PAYLOAD, status=200,
        )

        account = self.client.get_account()

        assert account.fee_ratio == 0.0095
        assert account.fee_tier == "0.95%"
        assert account.thirty_day_volume == 0.0
        assert account.next_fee_tier_ratio == 0.0025
        assert account.next_fee_tier_threshold == 50000.0

    @responses.activate
    def test_missing_fee_tier_status_does_not_raise(self):
        responses.add(
            responses.GET, CRYPTO_ACCOUNTS,
            json={"account_number": "12345", "buying_power": "0", "status": "active"},
            status=200,
        )

        account = self.client.get_account()

        assert account.fee_tier == ""
        assert account.fee_ratio == 0.0

    @responses.activate
    def test_get_account_list_response(self):
        """Test getting account when API returns a list."""
        responses.add(
            responses.GET, CRYPTO_ACCOUNTS, json=[self.ACCOUNT_PAYLOAD], status=200,
        )

        account = self.client.get_account()

        assert isinstance(account, CryptoAccount)
        assert account.account_number == "12345"

    @responses.activate
    def test_get_trading_pairs(self):
        """Fields captured live 2026-08-09.

        The API names these asset_code/quote_code/quote_increment/
        asset_increment and reports availability as `status` plus
        `is_api_tradable` — not `tradable`, `base_currency`, or
        `price_increment` as previously assumed.
        """
        responses.add(
            responses.GET,
            CRYPTO_TRADING_PAIRS,
            json={
                "results": [{
                    "asset_code": "BTC",
                    "quote_code": "USD",
                    "quote_increment": "0.01",
                    "asset_increment": "0.000001",
                    "max_order_size": "100.0",
                    "status": "tradable",
                    "symbol": "BTC-USD",
                    "is_api_tradable": True,
                }, {
                    "asset_code": "BILL",
                    "quote_code": "USD",
                    "quote_increment": "0.000001",
                    "asset_increment": "0.1",
                    "max_order_size": "9900000.0",
                    "status": "tradable",
                    "symbol": "BILL-USD",
                    "is_api_tradable": False,
                }]
            },
            status=200
        )

        pairs = self.client.get_trading_pairs()

        assert len(pairs) == 2
        btc = pairs[0]
        assert isinstance(btc, TradingPair)
        assert btc.symbol == "BTC-USD"
        assert btc.base_currency == "BTC"
        assert btc.quote_currency == "USD"
        assert btc.price_increment == 0.01
        assert btc.quantity_increment == 0.000001
        assert btc.tradable is True
        assert btc.api_tradable is True

        # tradable in the app but not through the API
        assert pairs[1].tradable is True
        assert pairs[1].api_tradable is False

    @responses.activate
    def test_get_best_bid_ask(self):
        """Test getting best bid/ask quotes."""
        responses.add(
            responses.GET,
            CRYPTO_BEST_BID_ASK,
            json={
                "results": [{
                    "symbol": "BTC-USD",
                    "bid": "45000.00",
                    "ask": "45100.00",
                    "timestamp": "2023-10-30T12:00:00Z",
                }]
            },
            status=200
        )

        quotes = self.client.get_best_bid_ask("BTC-USD")

        assert len(quotes) == 1
        quote = quotes[0]
        assert isinstance(quote, CryptoQuote)
        assert quote.symbol == "BTC-USD"
        assert quote.bid == 45000.00
        assert quote.ask == 45100.00
        assert isinstance(quote.timestamp, datetime)

    @responses.activate
    def test_get_estimated_price(self):
        """Test getting estimated price for a trade."""
        responses.add(
            responses.GET,
            CRYPTO_ESTIMATED_PRICE,
            json={
                "symbol": "BTC-USD",
                "side": "buy",
                "quantity": "0.001",
                "bid_price": "45000.00",
                "ask_price": "45100.00",
                "fee": "1.50",
            },
            status=200
        )

        price = self.client.get_estimated_price("BTC-USD", "buy", 0.001)

        assert isinstance(price, EstimatedPrice)
        assert price.symbol == "BTC-USD"
        assert price.side == "buy"
        assert price.quantity == 0.001
        assert price.bid_price == 45000.00
        assert price.ask_price == 45100.00
        assert price.fee == 1.50

    def test_get_historicals_is_retired(self):
        """The Crypto Trading API has no historicals endpoint (2026-08-09).

        Every candidate path returns 404 and it is absent from Robinhood's
        published spec. The old tests mocked an endpoint that does not exist.
        """
        from pyhood.exceptions import APIError

        with pytest.raises(APIError, match="no historicals endpoint"):
            self.client.get_historicals("BTC-USD")

    @responses.activate
    def test_get_holdings(self):
        """Test getting crypto holdings."""
        responses.add(
            responses.GET,
            CRYPTO_HOLDINGS,
            json={
                "results": [{
                    "asset_code": "BTC",
                    "quantity": "0.001",
                    "available_quantity": "0.0009",
                }]
            },
            status=200
        )

        holdings = self.client.get_holdings("12345", "BTC")

        assert len(holdings) == 1
        holding = holdings[0]
        assert isinstance(holding, CryptoHolding)
        assert holding.asset_code == "BTC"
        assert holding.quantity == 0.001
        assert holding.available_quantity == 0.0009

    @responses.activate
    def test_place_order(self):
        """Payload and response shape captured live 2026-08-09.

        The API reports `state`, `filled_asset_quantity`, `average_price` and
        `fee_charged`, and keeps size and price inside `{type}_order_config`.
        """
        responses.add(
            responses.POST,
            CRYPTO_ORDERS,
            json={
                "symbol": "BTC-USD",
                "client_order_id": "client-123",
                "side": "buy",
                "type": "limit",
                "id": "order-123",
                "account_number": "12345",
                "state": "open",
                "filled_asset_quantity": "0.000000000000000000",
                "executions": [],
                "average_price": None,
                "created_at": "2026-08-09T16:42:33.494640-04:00",
                "updated_at": "2026-08-09T16:42:34.198331-04:00",
                "fee_charged": 0.0,
                "limit_order_config": {
                    "asset_quantity": "0.000100000000000000",
                    "limit_price": "32548.380000000000000000",
                },
            },
            status=200
        )

        order = self.client.place_order(
            account_number="12345",
            side="buy",
            order_type="limit",
            symbol="BTC-USD",
            order_config={"asset_quantity": "0.0001", "limit_price": "32548.38"},
        )

        assert isinstance(order, CryptoOrder)
        assert order.order_id == "order-123"
        assert order.status == "open"
        assert order.quantity == 0.0001
        assert order.price == 32548.38
        assert order.filled_quantity == 0.0
        assert order.remaining_quantity == 0.0001
        assert order.fee == 0.0
        assert order.average_filled_price is None

        # account_number belongs in the query string, not the body
        request = responses.calls[-1].request
        assert "account_number=12345" in request.url
        body = json.loads(request.body)
        assert "account_number" not in body
        assert body["limit_order_config"] == {
            "asset_quantity": "0.0001", "limit_price": "32548.38",
        }
        assert body["client_order_id"]

    @responses.activate
    def test_get_order(self):
        """A cancelled order reports state, not status."""
        responses.add(
            responses.GET,
            f"{CRYPTO_ORDERS}order-123/",
            json={
                "symbol": "BTC-USD",
                "client_order_id": "client-123",
                "side": "buy",
                "type": "limit",
                "id": "order-123",
                "state": "canceled",
                "filled_asset_quantity": "0.0",
                "average_price": None,
                "fee_charged": 0.0,
                "created_at": "2026-08-09T16:42:33.494640-04:00",
                "updated_at": "2026-08-09T16:43:47.340423-04:00",
                "limit_order_config": {
                    "asset_quantity": "0.0001", "limit_price": "32548.38",
                },
            },
            status=200
        )

        order = self.client.get_order("12345", "order-123")

        assert order.order_id == "order-123"
        assert order.status == "canceled"
        assert order.price == 32548.38
    @responses.activate
    def test_get_orders(self):
        """Test getting all orders."""
        responses.add(
            responses.GET,
            CRYPTO_ORDERS,
            json={
                "results": [{
                    "id": "order-123",
                    "client_order_id": None,
                    "side": "buy",
                    "type": "market",
                    "symbol": "BTC-USD",
                    "status": "filled",
                    "price": None,
                    "quantity": "0.001",
                    "filled_quantity": "0.001",
                    "remaining_quantity": "0.0",
                    "average_filled_price": "45000.00",
                    "fee": "1.50",
                    "created_at": "2023-10-30T12:00:00Z",
                    "updated_at": "2023-10-30T12:01:00Z",
                }]
            },
            status=200
        )

        orders = self.client.get_orders("12345")

        assert len(orders) == 1
        order = orders[0]
        assert isinstance(order, CryptoOrder)
        assert order.order_id == "order-123"
        assert order.client_order_id is None

    @responses.activate
    def test_cancel_order(self):
        """Test cancelling an order."""
        responses.add(
            responses.POST,
            f"{CRYPTO_ORDERS}order-123/cancel/",
            json={"status": "cancelled"},
            status=200
        )

        result = self.client.cancel_order("order-123")
        assert result["status"] == "cancelled"

    @responses.activate
    def test_pagination(self):
        """Test handling of paginated responses."""
        # First page
        responses.add(
            responses.GET,
            CRYPTO_TRADING_PAIRS,
            json={
                "results": [{
                    "symbol": "BTC-USD",
                    "tradable": True,
                    "min_order_size": "0.000001",
                    "max_order_size": "100.0",
                    "price_increment": "0.01",
                    "quantity_increment": "0.000001",
                    "base_currency": "BTC",
                    "quote_currency": "USD",
                }],
                "next": f"{CRYPTO_TRADING_PAIRS}?cursor=page2"
            },
            status=200
        )

        # Second page
        responses.add(
            responses.GET,
            f"{CRYPTO_TRADING_PAIRS}?cursor=page2",
            json={
                "results": [{
                    "symbol": "ETH-USD",
                    "tradable": True,
                    "min_order_size": "0.000001",
                    "max_order_size": "1000.0",
                    "price_increment": "0.01",
                    "quantity_increment": "0.000001",
                    "base_currency": "ETH",
                    "quote_currency": "USD",
                }],
                "next": None
            },
            status=200
        )

        pairs = self.client.get_trading_pairs()

        assert len(pairs) == 2
        assert pairs[0].symbol == "BTC-USD"
        assert pairs[1].symbol == "ETH-USD"

    @responses.activate
    def test_auth_error(self):
        """Test authentication error handling."""
        responses.add(
            responses.GET,
            CRYPTO_ACCOUNTS,
            json={"error": "Invalid authentication"},
            status=401
        )

        with pytest.raises(AuthError, match="Authentication failed"):
            self.client.get_account()

    @responses.activate
    def test_api_error(self):
        """Test API error handling."""
        responses.add(
            responses.GET,
            CRYPTO_ACCOUNTS,
            json={"message": "Bad request"},
            status=400
        )

        with pytest.raises(APIError, match="Bad request"):
            self.client.get_account()

    @responses.activate
    def test_rate_limit_error(self):
        """Test rate limiting by server."""
        responses.add(
            responses.GET,
            CRYPTO_ACCOUNTS,
            headers={"Retry-After": "60"},
            status=429,
        )

        with pytest.raises(RateLimitError):
            self.client.make_request("GET", "/api/v2/crypto/trading/accounts/", retries=0)

    def test_invalid_private_key(self):
        """Test client with invalid private key."""
        client = CryptoClient("test-key", "invalid-key")

        with pytest.raises(AuthError, match="Failed to sign request"):
            client.make_request("GET", "/test")

    def test_client_rate_limiter(self):
        """Test client's built-in rate limiter."""
        # Create client with very restrictive rate limits for testing
        client = CryptoClient(self.api_key, self.private_key)
        client.rate_limiter = TokenBucket(rate=1, capacity=1)  # 1 req/min, 1 burst

        # First request should work
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, f"{CRYPTO_BASE}/test", json={})
            client.make_request("GET", "/test", retries=0)

        # Second request should be rate limited (before HTTP is even attempted)
        with pytest.raises(RateLimitError):
            client.make_request("GET", "/test", retries=0)
