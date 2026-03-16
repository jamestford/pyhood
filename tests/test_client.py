"""Tests for HoodClient — quotes, options, positions, earnings."""

import pytest
import responses

from hood import urls
from hood.client import HoodClient
from hood.exceptions import SymbolNotFoundError
from hood.http import Session
from hood.models import OptionContract, OptionsChain, Quote


BASE = "https://api.robinhood.com"


@pytest.fixture
def client():
    """Create a client with a mock authenticated session."""
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return HoodClient(session=session)


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
                        "type": "call",
                        "strike_price": "200.00",
                        "expiration_date": "2026-04-17",
                    },
                    {
                        "id": "opt-2",
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
