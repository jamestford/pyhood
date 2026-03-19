"""Tests for PyhoodClient — quotes, options, positions, earnings."""

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.exceptions import OrderError, SymbolNotFoundError
from pyhood.http import Session
from pyhood.models import OptionContract, OptionsChain, Order, Quote

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
