"""Tests for PyhoodClient — quotes, options, positions, earnings."""

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.exceptions import OrderError, SymbolNotFoundError
from pyhood.http import Session
from pyhood.models import (
    ACHTransfer,
    BankAccount,
    Dividend,
    Document,
    Market,
    MarketHours,
    Mover,
    NewsArticle,
    NotificationSettings,
    OptionContract,
    OptionsChain,
    Order,
    PortfolioCandle,
    Quote,
    Rating,
    StockSplit,
    UserProfile,
    Watchlist,
)

BASE = "https://api.robinhood.com"


@pytest.fixture
def client():
    """Create a client with a mock authenticated session."""
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return PyhoodClient(session=session)


class TestGetQuote:
    @responses.activate
    def test_single_quote(self, client):
        responses.add(
            responses.GET,
            f"{urls.QUOTES}AAPL/",
            json={
                "symbol": "AAPL",
                "last_trade_price": "195.50",
                "previous_close": "193.00",
                "bid_price": "195.40",
                "ask_price": "195.60",
                "last_trade_volume": "50000000",
            },
            status=200,
        )

        quote = client.get_quote("AAPL")
        assert isinstance(quote, Quote)
        assert quote.symbol == "AAPL"
        assert quote.price == 195.50
        assert quote.prev_close == 193.00
        assert quote.change_pct == 1.30
        assert quote.bid == 195.40
        assert quote.ask == 195.60

    @responses.activate
    def test_quote_case_insensitive(self, client):
        responses.add(
            responses.GET,
            f"{urls.QUOTES}AAPL/",
            json={
                "symbol": "AAPL",
                "last_trade_price": "195.50",
                "previous_close": "193.00",
            },
            status=200,
        )
        quote = client.get_quote("aapl")
        assert quote.symbol == "AAPL"

    @responses.activate
    def test_quote_not_found(self, client):
        responses.add(
            responses.GET,
            f"{urls.QUOTES}FAKESYMBOL/",
            json={},
            status=200,
        )
        with pytest.raises(SymbolNotFoundError):
            client.get_quote("FAKESYMBOL")


class TestGetQuotes:
    @responses.activate
    def test_batch_quotes(self, client):
        responses.add(
            responses.GET,
            urls.QUOTES,
            json={
                "results": [
                    {
                        "symbol": "AAPL",
                        "last_trade_price": "195.50",
                        "previous_close": "193.00",
                        "bid_price": "195.40",
                        "ask_price": "195.60",
                        "last_trade_volume": "50000000",
                    },
                    {
                        "symbol": "MSFT",
                        "last_trade_price": "420.00",
                        "previous_close": "418.00",
                        "bid_price": "419.90",
                        "ask_price": "420.10",
                        "last_trade_volume": "30000000",
                    },
                ]
            },
            status=200,
        )

        quotes = client.get_quotes(["AAPL", "MSFT"])
        assert len(quotes) == 2
        assert "AAPL" in quotes
        assert "MSFT" in quotes
        assert quotes["AAPL"].price == 195.50
        assert quotes["MSFT"].price == 420.00

    @responses.activate
    def test_batch_with_null_results(self, client):
        responses.add(
            responses.GET,
            urls.QUOTES,
            json={
                "results": [
                    {
                        "symbol": "AAPL",
                        "last_trade_price": "195.50",
                        "previous_close": "193.00",
                    },
                    None,  # Some symbols return null
                ]
            },
            status=200,
        )

        quotes = client.get_quotes(["AAPL", "INVALID"])
        assert len(quotes) == 1
        assert "AAPL" in quotes


class TestGetOptionsChain:
    @responses.activate
    def test_options_chain(self, client):
        responses.add(
            responses.GET,
            urls.OPTIONS_INSTRUMENTS,
            json={
                "results": [
                    {
                        "id": "opt-1",
                        "url": "https://api.robinhood.com/options/instruments/opt-1/",
                        "type": "call",
                        "strike_price": "200.00",
                        "expiration_date": "2026-04-17",
                    },
                    {
                        "id": "opt-2",
                        "url": "https://api.robinhood.com/options/instruments/opt-2/",
                        "type": "put",
                        "strike_price": "190.00",
                        "expiration_date": "2026-04-17",
                    },
                ],
                "next": None,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            urls.OPTIONS_MARKET_DATA,
            json={
                "results": [
                    {
                        "instrument_id": "opt-1",
                        "adjusted_mark_price": "3.50",
                        "bid_price": "3.40",
                        "ask_price": "3.60",
                        "implied_volatility": "0.35",
                        "delta": "0.45",
                        "gamma": "0.02",
                        "theta": "-0.05",
                        "vega": "0.15",
                        "volume": "5000",
                        "open_interest": "2000",
                    },
                    {
                        "instrument_id": "opt-2",
                        "adjusted_mark_price": "2.10",
                        "bid_price": "2.00",
                        "ask_price": "2.20",
                        "implied_volatility": "0.30",
                        "delta": "-0.35",
                        "gamma": "0.01",
                        "theta": "-0.04",
                        "vega": "0.12",
                        "volume": "3000",
                        "open_interest": "1500",
                    },
                ]
            },
            status=200,
        )

        chain = client.get_options_chain("AAPL", expiration="2026-04-17")
        assert isinstance(chain, OptionsChain)
        assert chain.symbol == "AAPL"
        assert len(chain.calls) == 1
        assert len(chain.puts) == 1

        call = chain.calls[0]
        assert isinstance(call, OptionContract)
        assert call.strike == 200.0
        assert call.mark == 3.50
        assert call.iv == 0.35
        assert call.delta == 0.45
        assert call.volume == 5000
        assert call.open_interest == 2000
        assert call.vol_oi_ratio == 2.5
        assert call.cost_per_contract == 350.0

        put = chain.puts[0]
        assert put.strike == 190.0
        assert put.option_type == "put"


class TestIndexOptions:
    """Tests for index options (SPX, NDX, etc.) support."""

    def test_resolve_chain_symbol_index(self, client):
        assert client._resolve_chain_symbol("SPX") == "SPXW"
        assert client._resolve_chain_symbol("NDX") == "NDXP"
        assert client._resolve_chain_symbol("VIX") == "VIXW"
        assert client._resolve_chain_symbol("RUT") == "RUTW"
        assert client._resolve_chain_symbol("XSP") == "XSP"

    def test_resolve_chain_symbol_equity(self, client):
        assert client._resolve_chain_symbol("AAPL") == "AAPL"
        assert client._resolve_chain_symbol("SPY") == "SPY"

    def test_is_index(self, client):
        assert client._is_index("SPX") is True
        assert client._is_index("spx") is True
        assert client._is_index("AAPL") is False

    @responses.activate
    def test_index_options_expirations(self, client):
        """Index expirations use /indexes/ + tradable_chain_ids (plural)."""
        responses.add(
            responses.GET,
            urls.INDEXES,
            json={
                "results": [
                    {
                        "id": "idx-1",
                        "symbol": "SPX",
                        "tradable_chain_ids": ["chain-b", "chain-a"],
                    }
                ]
            },
            status=200,
        )
        responses.add(
            responses.GET,
            urls.OPTIONS_CHAINS,
            json={
                "results": [
                    {
                        "id": "chain-a",
                        "expiration_dates": ["2026-04-17", "2026-04-24"],
                    }
                ]
            },
            status=200,
        )

        expirations = client.get_options_expirations("SPX")
        assert expirations == ["2026-04-17", "2026-04-24"]

        # Verify /indexes/ was called instead of /instruments/
        assert urls.INDEXES in responses.calls[0].request.url
        # Verify chain lookup used first sorted chain ID
        assert "chain-a" in responses.calls[1].request.url

    @responses.activate
    def test_index_options_chain(self, client):
        """Index chain passes mapped chain_symbol (SPXW) to instruments endpoint."""
        responses.add(
            responses.GET,
            urls.OPTIONS_INSTRUMENTS,
            json={
                "results": [
                    {
                        "id": "spx-opt-1",
                        "url": "https://api.robinhood.com/options/instruments/spx-opt-1/",
                        "type": "call",
                        "strike_price": "5800.00",
                        "expiration_date": "2026-04-17",
                    },
                ],
                "next": None,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            urls.OPTIONS_MARKET_DATA,
            json={
                "results": [
                    {
                        "instrument_id": "spx-opt-1",
                        "adjusted_mark_price": "42.50",
                        "bid_price": "42.00",
                        "ask_price": "43.00",
                        "implied_volatility": "0.18",
                        "delta": "0.50",
                        "gamma": "0.001",
                        "theta": "-0.80",
                        "vega": "2.50",
                        "volume": "12000",
                        "open_interest": "45000",
                    },
                ]
            },
            status=200,
        )

        chain = client.get_options_chain("SPX", expiration="2026-04-17")
        assert isinstance(chain, OptionsChain)
        assert chain.symbol == "SPX"
        assert len(chain.calls) == 1
        assert chain.calls[0].strike == 5800.0
        assert chain.calls[0].mark == 42.50

        # Verify chain_symbol was mapped to SPXW
        instruments_request = responses.calls[0].request
        assert "chain_symbol=SPXW" in instruments_request.url


class TestGetEarnings:
    @responses.activate
    def test_upcoming_earnings(self, client):
        from datetime import datetime, timedelta
        future = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")

        responses.add(
            responses.GET,
            urls.EARNINGS,
            json={
                "results": [
                    {
                        "report": {"date": future, "timing": "pm"},
                        "eps": {"estimate": "1.50", "actual": None},
                    }
                ]
            },
            status=200,
        )

        earnings = client.get_earnings("AAPL")
        assert earnings is not None
        assert earnings.symbol == "AAPL"
        assert earnings.date == future
        assert earnings.timing == "pm"
        assert earnings.eps_estimate == 1.50
        assert earnings.eps_actual is None

    @responses.activate
    def test_no_upcoming_earnings(self, client):
        responses.add(
            responses.GET,
            urls.EARNINGS,
            json={
                "results": [
                    {
                        "report": {"date": "2020-01-01", "timing": "am"},
                        "eps": {"estimate": "1.00", "actual": "1.10"},
                    }
                ]
            },
            status=200,
        )

        earnings = client.get_earnings("AAPL")
        assert earnings is None

    @responses.activate
    def test_empty_earnings(self, client):
        responses.add(
            responses.GET,
            urls.EARNINGS,
            json={"results": []},
            status=200,
        )

        earnings = client.get_earnings("AAPL")
        assert earnings is None


class TestGetBuyingPower:
    @responses.activate
    def test_buying_power(self, client):
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={
                "results": [{"buying_power": "15432.50"}],
                "next": None,
            },
            status=200,
        )

        power = client.get_buying_power()
        assert power == 15432.50

    @responses.activate
    def test_buying_power_empty(self, client):
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={"results": [], "next": None},
            status=200,
        )

        power = client.get_buying_power()
        assert power == 0.0


class TestStockOrders:
    @responses.activate
    def test_buy_stock_market(self, client):
        """Test placing a market buy order for stock."""
        # Mock account endpoint
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={"results": [{"url": f"{BASE}/accounts/12345/", "account_number": "12345"}]},
            status=200,
        )

        # Mock instrument endpoint
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/", "symbol": "AAPL"}]},
            status=200,
        )

        # Mock order placement
        responses.add(
            responses.POST,
            urls.ORDERS,
            json={
                "id": "order-12345",
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "quantity": "10",
                "state": "pending",
                "created_at": "2024-01-01T12:00:00Z",
            },
            status=201,
        )

        order = client.buy_stock("AAPL", 10)
        assert isinstance(order, Order)
        assert order.order_id == "order-12345"
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.order_type == "market"
        assert order.quantity == 10
        assert order.price is None
        assert order.status == "pending"
        assert order.instrument_type == "stock"

    @responses.activate
    def test_buy_stock_limit(self, client):
        """Test placing a limit buy order for stock."""
        # Mock account endpoint
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={"results": [{"url": f"{BASE}/accounts/12345/", "account_number": "12345"}]},
            status=200,
        )

        # Mock instrument endpoint
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/", "symbol": "AAPL"}]},
            status=200,
        )

        # Mock order placement
        responses.add(
            responses.POST,
            urls.ORDERS,
            json={
                "id": "order-12345",
                "symbol": "AAPL",
                "side": "buy",
                "type": "limit",
                "quantity": "5",
                "price": "150.00",
                "state": "pending",
                "created_at": "2024-01-01T12:00:00Z",
            },
            status=201,
        )

        order = client.buy_stock("AAPL", 5, price=150.00)
        assert isinstance(order, Order)
        assert order.order_id == "order-12345"
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.order_type == "limit"
        assert order.quantity == 5
        assert order.price == 150.00
        assert order.status == "pending"
        assert order.instrument_type == "stock"

    @responses.activate
    def test_sell_stock_market(self, client):
        """Test placing a market sell order for stock."""
        # Mock account endpoint
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={"results": [{"url": f"{BASE}/accounts/12345/", "account_number": "12345"}]},
            status=200,
        )

        # Mock instrument endpoint
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/", "symbol": "TSLA"}]},
            status=200,
        )

        # Mock order placement
        responses.add(
            responses.POST,
            urls.ORDERS,
            json={
                "id": "order-54321",
                "symbol": "TSLA",
                "side": "sell",
                "type": "market",
                "quantity": "20",
                "state": "filled",
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:05:00Z",
                "average_filled_price": "200.50",
            },
            status=201,
        )

        order = client.sell_stock("TSLA", 20)
        assert isinstance(order, Order)
        assert order.order_id == "order-54321"
        assert order.symbol == "TSLA"
        assert order.side == "sell"
        assert order.order_type == "market"
        assert order.quantity == 20
        assert order.price is None
        assert order.status == "filled"
        assert order.instrument_type == "stock"


class TestOptionOrders:
    @responses.activate
    def test_buy_option(self, client):
        """Test placing a buy order for option."""
        # Mock account endpoint
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={"results": [{"url": f"{BASE}/accounts/12345/", "account_number": "12345"}]},
            status=200,
        )

        # Mock option instrument search
        responses.add(
            responses.GET,
            urls.OPTIONS_INSTRUMENTS,
            json={"results": [
                {"url": f"{BASE}/options/instruments/opt123/", "chain_symbol": "AAPL"},
            ]},
            status=200,
        )

        # Mock option order placement
        responses.add(
            responses.POST,
            urls.OPTIONS_ORDERS,
            json={
                "id": "opt-order-123",
                "direction": "buy",
                "type": "limit",
                "quantity": "2",
                "price": "5.50",
                "state": "pending",
                "created_at": "2024-01-01T12:00:00Z",
            },
            status=201,
        )

        order = client.buy_option("AAPL", 150.0, "2024-12-20", "call", 2, 5.50)
        assert isinstance(order, Order)
        assert order.order_id == "opt-order-123"
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.order_type == "limit"
        assert order.quantity == 2
        assert order.price == 5.50
        assert order.status == "pending"
        assert order.instrument_type == "option"

    @responses.activate
    def test_sell_option(self, client):
        """Test placing a sell order for option."""
        # Mock account endpoint
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={"results": [{"url": f"{BASE}/accounts/12345/", "account_number": "12345"}]},
            status=200,
        )

        # Mock option instrument search
        responses.add(
            responses.GET,
            urls.OPTIONS_INSTRUMENTS,
            json={"results": [
                {"url": f"{BASE}/options/instruments/opt456/", "chain_symbol": "SPY"},
            ]},
            status=200,
        )

        # Mock option order placement
        responses.add(
            responses.POST,
            urls.OPTIONS_ORDERS,
            json={
                "id": "opt-order-456",
                "direction": "sell",
                "type": "limit",
                "quantity": "1",
                "price": "3.25",
                "state": "pending",
                "created_at": "2024-01-01T12:00:00Z",
            },
            status=201,
        )

        order = client.sell_option("SPY", 400.0, "2024-12-20", "put", 1, 3.25)
        assert isinstance(order, Order)
        assert order.order_id == "opt-order-456"
        assert order.symbol == "SPY"
        assert order.side == "sell"
        assert order.order_type == "limit"
        assert order.quantity == 1
        assert order.price == 3.25
        assert order.status == "pending"
        assert order.instrument_type == "option"


class TestOrderManagement:
    @responses.activate
    def test_get_stock_orders(self, client):
        """Test getting all stock orders."""
        responses.add(
            responses.GET,
            urls.ORDERS,
            json={
                "results": [
                    {
                        "id": "order-1",
                        "symbol": "AAPL",
                        "side": "buy",
                        "type": "limit",
                        "quantity": "10",
                        "price": "150.00",
                        "state": "filled",
                        "created_at": "2024-01-01T12:00:00Z",
                        "updated_at": "2024-01-01T12:05:00Z",
                        "average_filled_price": "149.50",
                        "fees": "1.25",
                    },
                    {
                        "id": "order-2",
                        "symbol": "TSLA",
                        "side": "sell",
                        "type": "market",
                        "quantity": "5",
                        "state": "pending",
                        "created_at": "2024-01-01T13:00:00Z",
                    }
                ],
                "next": None,
            },
            status=200,
        )

        orders = client.get_stock_orders()
        assert len(orders) == 2
        assert all(isinstance(order, Order) for order in orders)

        order1 = orders[0]
        assert order1.order_id == "order-1"
        assert order1.symbol == "AAPL"
        assert order1.side == "buy"
        assert order1.quantity == 10
        assert order1.average_price == 149.50
        assert order1.fees == 1.25

        order2 = orders[1]
        assert order2.order_id == "order-2"
        assert order2.symbol == "TSLA"
        assert order2.side == "sell"
        assert order2.status == "pending"

    @responses.activate
    def test_get_order(self, client):
        """Test getting a specific order by ID."""
        responses.add(
            responses.GET,
            f"{urls.ORDERS}order-123/",
            json={
                "id": "order-123",
                "symbol": "NVDA",
                "side": "buy",
                "type": "limit",
                "quantity": "8",
                "price": "800.00",
                "stop_price": "750.00",
                "state": "pending",
                "created_at": "2024-01-01T12:00:00Z",
                "time_in_force": "gtc",
                "trigger": "stop",
            },
            status=200,
        )

        order = client.get_order("order-123")
        assert isinstance(order, Order)
        assert order.order_id == "order-123"
        assert order.symbol == "NVDA"
        assert order.side == "buy"
        assert order.quantity == 8
        assert order.price == 800.00
        assert order.stop_price == 750.00
        assert order.time_in_force == "gtc"
        assert order.trigger == "stop"

    @responses.activate
    def test_cancel_order(self, client):
        """Test cancelling an order."""
        responses.add(
            responses.POST,
            f"{urls.ORDERS}order-123/cancel/",
            json={"id": "order-123", "state": "cancelled"},
            status=200,
        )

        result = client.cancel_order("order-123")
        assert result["id"] == "order-123"
        assert result["state"] == "cancelled"

    @responses.activate
    def test_order_error_handling(self, client):
        """Test order error handling."""
        # Mock account endpoint
        responses.add(
            responses.GET,
            urls.ACCOUNTS,
            json={"results": [{"url": f"{BASE}/accounts/12345/", "account_number": "12345"}]},
            status=200,
        )

        # Mock instrument endpoint
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/", "symbol": "AAPL"}]},
            status=200,
        )

        # Mock order placement with error
        responses.add(
            responses.POST,
            urls.ORDERS,
            json={"detail": "Insufficient buying power"},
            status=400,
        )

        with pytest.raises(OrderError, match="Insufficient buying power"):
            client.buy_stock("AAPL", 100000, price=150.00)


class TestStockHistoricals:
    @responses.activate
    def test_get_stock_historicals(self, client):
        responses.add(
            responses.GET,
            urls.HISTORICALS,
            json={
                "results": [
                    {
                        "symbol": "AAPL",
                        "historicals": [
                            {
                                "begins_at": "2026-03-10T00:00:00Z",
                                "open_price": "250.00",
                                "close_price": "252.00",
                                "high_price": "253.50",
                                "low_price": "249.00",
                                "volume": 50000000,
                                "session": "reg",
                                "interpolated": False,
                            },
                            {
                                "begins_at": "2026-03-11T00:00:00Z",
                                "open_price": "252.00",
                                "close_price": "255.00",
                                "high_price": "256.00",
                                "low_price": "251.00",
                                "volume": 48000000,
                                "session": "reg",
                                "interpolated": False,
                            },
                        ],
                    }
                ]
            },
            status=200,
        )

        candles = client.get_stock_historicals("AAPL", interval="day", span="week")
        assert len(candles) == 2
        assert candles[0].symbol == "AAPL"
        assert candles[0].open_price == 250.00
        assert candles[0].close_price == 252.00
        assert candles[0].high_price == 253.50
        assert candles[0].low_price == 249.00
        assert candles[0].volume == 50000000
        assert candles[1].close_price == 255.00

    @responses.activate
    def test_get_stock_historicals_batch(self, client):
        responses.add(
            responses.GET,
            urls.HISTORICALS,
            json={
                "results": [
                    {
                        "symbol": "AAPL",
                        "historicals": [
                            {
                                "begins_at": "2026-03-10T00:00:00Z",
                                "open_price": "250.00",
                                "close_price": "252.00",
                                "high_price": "253.00",
                                "low_price": "249.00",
                                "volume": 50000000,
                            },
                        ],
                    },
                    {
                        "symbol": "MSFT",
                        "historicals": [
                            {
                                "begins_at": "2026-03-10T00:00:00Z",
                                "open_price": "420.00",
                                "close_price": "422.00",
                                "high_price": "425.00",
                                "low_price": "418.00",
                                "volume": 30000000,
                            },
                        ],
                    },
                ]
            },
            status=200,
        )

        result = client.get_stock_historicals_batch(["AAPL", "MSFT"])
        assert "AAPL" in result
        assert "MSFT" in result
        assert len(result["AAPL"]) == 1
        assert result["AAPL"][0].close_price == 252.00
        assert result["MSFT"][0].close_price == 422.00

    def test_invalid_interval(self, client):
        with pytest.raises(ValueError, match="interval must be"):
            client.get_stock_historicals("AAPL", interval="invalid")

    def test_invalid_span(self, client):
        with pytest.raises(ValueError, match="span must be"):
            client.get_stock_historicals("AAPL", span="invalid")

    def test_invalid_bounds(self, client):
        with pytest.raises(ValueError, match="bounds must be"):
            client.get_stock_historicals("AAPL", bounds="invalid")

    def test_extended_bounds_requires_day_span(self, client):
        with pytest.raises(ValueError, match="extended/trading"):
            client.get_stock_historicals("AAPL", bounds="extended", span="week")

    @responses.activate
    def test_empty_historicals(self, client):
        responses.add(
            responses.GET,
            urls.HISTORICALS,
            json={"results": [{"symbol": "AAPL", "historicals": []}]},
            status=200,
        )
        candles = client.get_stock_historicals("AAPL")
        assert candles == []


class TestSettings:
    @responses.activate
    def test_get_user_profile(self, client):
        responses.add(
            responses.GET,
            urls.USER,
            json={
                "id": "user-001",
                "username": "jford",
                "email": "james@example.com",
                "first_name": "James",
                "last_name": "Ford",
                "created_at": "2020-01-15T10:00:00Z",
            },
            status=200,
        )

        profile = client.get_user_profile()
        assert isinstance(profile, UserProfile)
        assert profile.username == "jford"
        assert profile.email == "james@example.com"
        assert profile.first_name == "James"
        assert profile.last_name == "Ford"

    @responses.activate
    def test_get_notification_settings(self, client):
        responses.add(
            responses.GET,
            urls.NOTIFICATION_SETTINGS,
            json={
                "market_open": True,
                "dividends": True,
                "transfers": False,
                "price_movements": True,
            },
            status=200,
        )

        settings = client.get_notification_settings()
        assert isinstance(settings, NotificationSettings)
        assert settings.is_enabled("market_open") is True
        assert settings.is_enabled("transfers") is False
        assert settings.is_enabled("nonexistent") is False

    @responses.activate
    def test_update_notification_settings(self, client):
        responses.add(
            responses.POST,
            urls.NOTIFICATION_SETTINGS,
            json={
                "market_open": False,
                "dividends": True,
                "transfers": False,
                "price_movements": True,
            },
            status=200,
        )

        settings = client.update_notification_settings(market_open=False)
        assert isinstance(settings, NotificationSettings)
        assert settings.is_enabled("market_open") is False


class TestBanking:
    @responses.activate
    def test_get_bank_accounts(self, client):
        responses.add(
            responses.GET,
            urls.ACH_RELATIONSHIPS,
            json={
                "results": [
                    {
                        "id": "bank-001",
                        "bank_account_holder_name": "Chase",
                        "bank_account_type": "checking",
                        "bank_account_nickname": "My Checking",
                        "state": "approved",
                        "url": f"{BASE}/ach/relationships/bank-001/",
                    },
                ],
                "next": None,
            },
            status=200,
        )

        accounts = client.get_bank_accounts()
        assert len(accounts) == 1
        assert isinstance(accounts[0], BankAccount)
        assert accounts[0].id == "bank-001"
        assert accounts[0].bank_name == "Chase"
        assert accounts[0].account_type == "checking"
        assert accounts[0].state == "approved"

    @responses.activate
    def test_get_transfers(self, client):
        responses.add(
            responses.GET,
            urls.ACH_TRANSFERS,
            json={
                "results": [
                    {
                        "id": "xfer-001",
                        "amount": "500.00",
                        "direction": "deposit",
                        "state": "completed",
                        "created_at": "2026-03-01T10:00:00Z",
                        "expected_landing_date": "2026-03-03",
                        "ach_relationship": f"{BASE}/ach/relationships/bank-001/",
                    },
                    {
                        "id": "xfer-002",
                        "amount": "200.00",
                        "direction": "withdraw",
                        "state": "pending",
                        "created_at": "2026-03-28T10:00:00Z",
                        "expected_landing_date": "2026-03-31",
                        "ach_relationship": f"{BASE}/ach/relationships/bank-001/",
                    },
                ],
                "next": None,
            },
            status=200,
        )

        transfers = client.get_transfers()
        assert len(transfers) == 2
        assert isinstance(transfers[0], ACHTransfer)
        assert transfers[0].amount == 500.00
        assert transfers[0].direction == "deposit"
        assert transfers[0].state == "completed"
        assert transfers[1].direction == "withdraw"
        assert transfers[1].state == "pending"

    @responses.activate
    def test_initiate_transfer(self, client):
        responses.add(
            responses.POST,
            urls.ACH_TRANSFERS,
            json={
                "id": "xfer-003",
                "amount": "1000.00",
                "direction": "deposit",
                "state": "pending",
                "created_at": "2026-03-29T10:00:00Z",
                "expected_landing_date": "2026-04-01",
                "ach_relationship": f"{BASE}/ach/relationships/bank-001/",
            },
            status=201,
        )

        transfer = client.initiate_transfer(
            amount=1000.00,
            direction="deposit",
            ach_relationship_url=f"{BASE}/ach/relationships/bank-001/",
        )
        assert isinstance(transfer, ACHTransfer)
        assert transfer.amount == 1000.00
        assert transfer.direction == "deposit"
        assert transfer.state == "pending"

    @responses.activate
    def test_cancel_transfer(self, client):
        responses.add(
            responses.POST,
            f"{urls.ACH_TRANSFERS}xfer-003/cancel/",
            json={"id": "xfer-003", "state": "cancelled"},
            status=200,
        )

        result = client.cancel_transfer("xfer-003")
        assert result["state"] == "cancelled"


class TestWatchlists:
    @responses.activate
    def test_get_watchlists(self, client):
        responses.add(
            responses.GET,
            urls.WATCHLISTS_V2,
            json={
                "results": [
                    {
                        "display_name": "Default",
                        "url": f"{BASE}/midlands/lists/abc123/",
                        "items": [
                            {"symbol": "AAPL"},
                            {"symbol": "MSFT"},
                        ],
                    },
                    {
                        "display_name": "Tech Stocks",
                        "url": f"{BASE}/midlands/lists/def456/",
                        "items": [
                            {"symbol": "NVDA"},
                        ],
                    },
                ],
                "next": None,
            },
            status=200,
        )

        watchlists = client.get_watchlists()
        assert len(watchlists) == 2
        assert isinstance(watchlists[0], Watchlist)
        assert watchlists[0].name == "Default"
        assert watchlists[0].symbols == ["AAPL", "MSFT"]
        assert watchlists[1].name == "Tech Stocks"
        assert watchlists[1].symbols == ["NVDA"]

    @responses.activate
    def test_get_watchlist_by_name(self, client):
        responses.add(
            responses.GET,
            urls.WATCHLISTS_V2,
            json={
                "results": [
                    {
                        "display_name": "Default",
                        "url": f"{BASE}/midlands/lists/abc123/",
                        "items": [{"symbol": "AAPL"}],
                    },
                ],
                "next": None,
            },
            status=200,
        )

        wl = client.get_watchlist("Default")
        assert wl.name == "Default"
        assert wl.symbols == ["AAPL"]

    @responses.activate
    def test_get_watchlist_not_found(self, client):
        responses.add(
            responses.GET,
            urls.WATCHLISTS_V2,
            json={"results": [], "next": None},
            status=200,
        )

        with pytest.raises(SymbolNotFoundError):
            client.get_watchlist("Nonexistent")

    @responses.activate
    def test_add_to_watchlist(self, client):
        responses.add(
            responses.GET,
            urls.WATCHLISTS_V2,
            json={
                "results": [
                    {
                        "display_name": "Default",
                        "url": f"{BASE}/midlands/lists/abc123/",
                        "items": [{"symbol": "AAPL"}],
                    },
                ],
                "next": None,
            },
            status=200,
        )
        responses.add(
            responses.POST,
            f"{BASE}/midlands/lists/abc123/items/",
            json={"symbol": "TSLA"},
            status=201,
        )

        results = client.add_to_watchlist(["TSLA"])
        assert len(results) == 1

    @responses.activate
    def test_remove_from_watchlist(self, client):
        responses.add(
            responses.GET,
            urls.WATCHLISTS_V2,
            json={
                "results": [
                    {
                        "display_name": "Default",
                        "url": f"{BASE}/midlands/lists/abc123/",
                        "items": [{"symbol": "AAPL"}],
                    },
                ],
                "next": None,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/midlands/lists/abc123/items/",
            json={
                "results": [
                    {"id": "item-001", "symbol": "AAPL"},
                    {"id": "item-002", "symbol": "MSFT"},
                ],
                "next": None,
            },
            status=200,
        )
        responses.add(
            responses.DELETE,
            f"{BASE}/midlands/lists/abc123/items/item-001/",
            body="",
            status=200,
        )

        client.remove_from_watchlist(["AAPL"])
        # Verify the DELETE was called
        assert any(
            call.request.method == "DELETE" for call in responses.calls
        )


class TestGetMarkets:
    @responses.activate
    def test_get_markets(self, client):
        responses.add(
            responses.GET,
            urls.MARKETS,
            json={
                "results": [
                    {
                        "mic": "XNYS",
                        "name": "New York Stock Exchange",
                        "city": "New York",
                        "country": "US",
                        "acronym": "NYSE",
                        "timezone": "US/Eastern",
                        "url": f"{BASE}/markets/XNYS/",
                    },
                    {
                        "mic": "XNAS",
                        "name": "NASDAQ",
                        "city": "New York",
                        "country": "US",
                        "acronym": "NASDAQ",
                        "timezone": "US/Eastern",
                        "url": f"{BASE}/markets/XNAS/",
                    },
                ],
                "next": None,
            },
            status=200,
        )

        markets = client.get_markets()
        assert len(markets) == 2
        assert isinstance(markets[0], Market)
        assert markets[0].mic == "XNYS"
        assert markets[0].name == "New York Stock Exchange"
        assert markets[0].city == "New York"
        assert markets[1].mic == "XNAS"
        assert markets[1].acronym == "NASDAQ"

    @responses.activate
    def test_get_market_hours_open_day(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/markets/XNYS/hours/2026-03-30/",
            json={
                "date": "2026-03-30",
                "is_open": True,
                "opens_at": "2026-03-30T13:30:00Z",
                "closes_at": "2026-03-30T20:00:00Z",
                "extended_opens_at": "2026-03-30T13:00:00Z",
                "extended_closes_at": "2026-03-30T22:00:00Z",
            },
            status=200,
        )

        hours = client.get_market_hours("XNYS", "2026-03-30")
        assert isinstance(hours, MarketHours)
        assert hours.date == "2026-03-30"
        assert hours.is_open is True
        assert hours.opens_at == "2026-03-30T13:30:00Z"
        assert hours.closes_at == "2026-03-30T20:00:00Z"
        assert hours.extended_opens_at == "2026-03-30T13:00:00Z"

    @responses.activate
    def test_get_market_hours_closed_day(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/markets/XNYS/hours/2026-03-29/",
            json={
                "date": "2026-03-29",
                "is_open": False,
                "opens_at": None,
                "closes_at": None,
                "extended_opens_at": None,
                "extended_closes_at": None,
            },
            status=200,
        )

        hours = client.get_market_hours("XNYS", "2026-03-29")
        assert hours.is_open is False
        assert hours.opens_at == ""
        assert hours.closes_at == ""


class TestGetDividends:
    @responses.activate
    def test_get_dividends(self, client):
        responses.add(
            responses.GET,
            urls.DIVIDENDS,
            json={
                "results": [
                    {
                        "id": "div-001",
                        "amount": "1.25",
                        "rate": "0.25",
                        "payable_date": "2026-03-15",
                        "record_date": "2026-03-01",
                        "state": "paid",
                        "instrument": f"{BASE}/instruments/abc123/",
                    },
                    {
                        "id": "div-002",
                        "amount": "0.88",
                        "rate": "0.22",
                        "payable_date": "2026-06-15",
                        "record_date": "2026-06-01",
                        "state": "pending",
                        "instrument": f"{BASE}/instruments/def456/",
                    },
                ],
                "next": None,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/abc123/",
            json={"symbol": "AAPL"},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/def456/",
            json={"symbol": "MSFT"},
            status=200,
        )

        dividends = client.get_dividends()
        assert len(dividends) == 2
        assert isinstance(dividends[0], Dividend)
        assert dividends[0].symbol == "AAPL"
        assert dividends[0].amount == 1.25
        assert dividends[0].rate == 0.25
        assert dividends[0].state == "paid"
        assert dividends[0].payable_date == "2026-03-15"
        assert dividends[1].symbol == "MSFT"
        assert dividends[1].state == "pending"

    @responses.activate
    def test_get_dividends_empty(self, client):
        responses.add(
            responses.GET,
            urls.DIVIDENDS,
            json={"results": [], "next": None},
            status=200,
        )
        assert client.get_dividends() == []

    @responses.activate
    def test_get_dividends_by_symbol(self, client):
        responses.add(
            responses.GET,
            urls.DIVIDENDS,
            json={
                "results": [
                    {
                        "id": "div-001",
                        "amount": "1.25",
                        "rate": "0.25",
                        "payable_date": "2026-03-15",
                        "record_date": "2026-03-01",
                        "state": "paid",
                        "instrument": f"{BASE}/instruments/abc123/",
                    },
                    {
                        "id": "div-002",
                        "amount": "0.88",
                        "rate": "0.22",
                        "payable_date": "2026-06-15",
                        "record_date": "2026-06-01",
                        "state": "paid",
                        "instrument": f"{BASE}/instruments/abc123/",
                    },
                ],
                "next": None,
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/abc123/",
            json={"symbol": "AAPL"},
            status=200,
        )

        dividends = client.get_dividends_by_symbol("AAPL")
        assert len(dividends) == 2
        assert all(d.symbol == "AAPL" for d in dividends)

        # Non-matching symbol returns empty
        dividends = client.get_dividends_by_symbol("TSLA")
        assert dividends == []


class TestRatings:
    @responses.activate
    def test_get_ratings(self, client):
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/", "symbol": "AAPL"}]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{urls.RATINGS}abc123/",
            json={
                "summary": {
                    "num_buy_ratings": 25,
                    "num_hold_ratings": 8,
                    "num_sell_ratings": 2,
                },
                "instrument_id": "abc123",
            },
            status=200,
        )

        rating = client.get_ratings("AAPL")
        assert isinstance(rating, Rating)
        assert rating.symbol == "AAPL"
        assert rating.num_buy == 25
        assert rating.num_hold == 8
        assert rating.num_sell == 2
        assert rating.total == 35
        assert rating.buy_pct == pytest.approx(71.43, abs=0.01)


class TestNews:
    @responses.activate
    def test_get_news(self, client):
        responses.add(
            responses.GET,
            urls.NEWS,
            json={
                "results": [
                    {
                        "title": "Apple Reports Record Quarter",
                        "source": "Reuters",
                        "url": "https://reuters.com/article/1",
                        "published_at": "2026-03-29T10:00:00Z",
                        "summary": "Apple beat expectations...",
                        "related_instruments": [{"symbol": "AAPL"}],
                    },
                    {
                        "title": "Tech Stocks Rally",
                        "source": "Bloomberg",
                        "url": "https://bloomberg.com/article/2",
                        "published_at": "2026-03-29T09:00:00Z",
                        "summary": "Tech sector gains...",
                        "related_instruments": [
                            {"symbol": "AAPL"},
                            {"symbol": "MSFT"},
                        ],
                    },
                ],
            },
            status=200,
        )

        articles = client.get_news("AAPL")
        assert len(articles) == 2
        assert isinstance(articles[0], NewsArticle)
        assert articles[0].title == "Apple Reports Record Quarter"
        assert articles[0].source == "Reuters"
        assert articles[1].related_instruments == ["AAPL", "MSFT"]

    @responses.activate
    def test_get_news_empty(self, client):
        responses.add(
            responses.GET,
            urls.NEWS,
            json={"results": []},
            status=200,
        )
        assert client.get_news("XYZ") == []


class TestMovers:
    @responses.activate
    def test_get_movers(self, client):
        responses.add(
            responses.GET,
            urls.MOVERS_SP500,
            json={
                "results": [
                    {
                        "instrument_url": f"{BASE}/instruments/abc123/",
                        "price_movement": {
                            "market_hours_last_movement_pct": "3.45",
                        },
                    },
                ],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/abc123/",
            json={"symbol": "NVDA"},
            status=200,
        )

        movers = client.get_movers("up")
        assert len(movers) == 1
        assert isinstance(movers[0], Mover)
        assert movers[0].symbol == "NVDA"
        assert movers[0].price_change_pct == 3.45


class TestTags:
    @responses.activate
    def test_get_tags(self, client):
        responses.add(
            responses.GET,
            f"{urls.TAGS}100-most-popular/",
            json={
                "instruments": [
                    f"{BASE}/instruments/aaa/",
                    f"{BASE}/instruments/bbb/",
                ],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/aaa/",
            json={"symbol": "AAPL"},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/bbb/",
            json={"symbol": "MSFT"},
            status=200,
        )

        symbols = client.get_tags("100-most-popular")
        assert symbols == ["AAPL", "MSFT"]


class TestPopularity:
    @responses.activate
    def test_get_popularity(self, client):
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/"}]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/abc123/popularity/",
            json={"num_open_positions": 150432},
            status=200,
        )

        count = client.get_popularity("AAPL")
        assert count == 150432


class TestSplits:
    @responses.activate
    def test_get_splits(self, client):
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/"}]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/abc123/splits/",
            json={
                "results": [
                    {
                        "instrument": f"{BASE}/instruments/abc123/",
                        "execution_date": "2020-08-31",
                        "multiplier": "4.00",
                        "divisor": "1.00",
                    },
                ],
            },
            status=200,
        )

        splits = client.get_splits("AAPL")
        assert len(splits) == 1
        assert isinstance(splits[0], StockSplit)
        assert splits[0].execution_date == "2020-08-31"
        assert splits[0].multiplier == 4.0

    @responses.activate
    def test_get_splits_empty(self, client):
        responses.add(
            responses.GET,
            urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc123/"}]},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{BASE}/instruments/abc123/splits/",
            json={"results": []},
            status=200,
        )
        assert client.get_splits("BRK.A") == []


class TestPortfolioHistoricals:
    @responses.activate
    def test_get_portfolio_historicals(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/portfolios/historicals/123456/",
            json={
                "equity_historicals": [
                    {
                        "begins_at": "2026-03-28T00:00:00Z",
                        "adjusted_open_equity": "15000.00",
                        "adjusted_close_equity": "15200.00",
                        "open_equity": "15000.00",
                        "close_equity": "15200.00",
                        "open_market_value": "14000.00",
                        "close_market_value": "14200.00",
                    },
                ],
            },
            status=200,
        )

        candles = client.get_portfolio_historicals(
            account_number="123456",
        )
        assert len(candles) == 1
        assert isinstance(candles[0], PortfolioCandle)
        assert candles[0].adjusted_close_equity == 15200.00
        assert candles[0].close_market_value == 14200.00


class TestOptionHistoricals:
    @responses.activate
    def test_get_option_historicals(self, client):
        responses.add(
            responses.GET,
            f"{urls.OPTIONS_HISTORICALS}opt-123/",
            json={
                "data_points": [
                    {
                        "begins_at": "2026-03-28T00:00:00Z",
                        "open_price": "5.00",
                        "close_price": "5.25",
                        "high_price": "5.50",
                        "low_price": "4.90",
                        "volume": "1200",
                    },
                ],
            },
            status=200,
        )

        candles = client.get_option_historicals("opt-123")
        assert len(candles) == 1
        assert candles[0].close_price == 5.25
        assert candles[0].volume == 1200


class TestDocuments:
    @responses.activate
    def test_get_documents(self, client):
        responses.add(
            responses.GET,
            urls.DOCUMENTS,
            json={
                "results": [
                    {
                        "id": "doc-001",
                        "type": "account_statement",
                        "date": "2026-03-01",
                        "url": f"{BASE}/documents/doc-001/",
                        "download_url": f"{BASE}/documents/doc-001/download/",
                    },
                    {
                        "id": "doc-002",
                        "type": "trade_confirm",
                        "date": "2026-03-15",
                        "url": f"{BASE}/documents/doc-002/",
                        "download_url": f"{BASE}/documents/doc-002/download/",
                    },
                ],
                "next": None,
            },
            status=200,
        )

        docs = client.get_documents()
        assert len(docs) == 2
        assert isinstance(docs[0], Document)
        assert docs[0].type == "account_statement"
        assert docs[1].type == "trade_confirm"

    @responses.activate
    def test_get_documents_filtered(self, client):
        responses.add(
            responses.GET,
            urls.DOCUMENTS,
            json={
                "results": [
                    {
                        "id": "doc-001",
                        "type": "account_statement",
                        "date": "2026-03-01",
                    },
                ],
                "next": None,
            },
            status=200,
        )

        docs = client.get_documents(doc_type="account_statement")
        assert len(docs) == 1


class TestDayTrades:
    @responses.activate
    def test_get_day_trades(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/accounts/acct-123/recent_day_trades/",
            json={
                "equity_day_trades": [
                    {"symbol": "AAPL", "day": "2026-03-28"},
                    {"symbol": "TSLA", "day": "2026-03-28"},
                ],
            },
            status=200,
        )

        trades = client.get_day_trades(account_id="acct-123")
        assert len(trades) == 2
        assert trades[0]["symbol"] == "AAPL"


class TestMarginCalls:
    @responses.activate
    def test_get_margin_calls_empty(self, client):
        responses.add(
            responses.GET,
            urls.MARGIN_CALLS,
            json={"results": [], "next": None},
            status=200,
        )
        assert client.get_margin_calls() == []


class TestDepositSchedules:
    @responses.activate
    def test_get_deposit_schedules(self, client):
        responses.add(
            responses.GET,
            urls.ACH_DEPOSIT_SCHEDULES,
            json={
                "results": [
                    {
                        "id": "sched-001",
                        "amount": "100.00",
                        "frequency": "weekly",
                    },
                ],
                "next": None,
            },
            status=200,
        )

        schedules = client.get_deposit_schedules()
        assert len(schedules) == 1
        assert schedules[0]["frequency"] == "weekly"
