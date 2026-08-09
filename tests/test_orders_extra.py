"""Tests for spreads, fractional orders and CSV export.

Order-placement tests assert the request payload. Confirming a spread or a
fractional order against the live API would mean opening a real position with
real money, which has not been done.
"""

import csv
import json

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.exceptions import OrderError
from pyhood.http import Session

BASE = "https://api.robinhood.com"


@pytest.fixture
def client():
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return PyhoodClient(session=session)


def _mock_account():
    responses.add(
        responses.GET, urls.ACCOUNTS,
        json={"results": [{"url": f"{BASE}/accounts/12345/", "account_number": "12345"}]},
        status=200,
    )


def _mock_option_lookup(count=2):
    for i in range(count):
        responses.add(
            responses.GET, urls.OPTIONS_INSTRUMENTS,
            json={"results": [{"id": f"opt-{i}", "url": f"{urls.OPTIONS_INSTRUMENTS}opt-{i}/"}]},
            status=200,
        )


class TestOptionSpread:
    LEGS = [
        {"strike": 100.0, "expiration": "2026-09-18", "option_type": "call",
         "side": "buy", "effect": "open"},
        {"strike": 105.0, "expiration": "2026-09-18", "option_type": "call",
         "side": "sell", "effect": "open"},
    ]

    def test_requires_two_legs(self, client):
        with pytest.raises(OrderError, match="at least two legs"):
            client.order_option_spread("AAPL", 1, 1.50, [self.LEGS[0]], "debit")

    def test_rejects_leg_missing_keys(self, client):
        bad = [self.LEGS[0], {"strike": 105.0, "side": "sell"}]
        with pytest.raises(OrderError, match="missing"):
            client.order_option_spread("AAPL", 1, 1.50, bad, "debit")

    @responses.activate
    def test_builds_multi_leg_payload(self, client):
        _mock_account()
        _mock_option_lookup(2)
        responses.add(
            responses.POST, urls.OPTIONS_ORDERS,
            json={"id": "spread-1", "state": "queued",
                  "created_at": "2026-08-09T12:00:00Z"},
            status=201,
        )

        order = client.order_option_spread("AAPL", 1, 1.50, self.LEGS, "debit")

        body = json.loads(responses.calls[-1].request.body)
        assert len(body["legs"]) == 2
        assert body["direction"] == "debit"
        assert body["type"] == "limit"
        assert body["price"] == "1.5"
        assert [leg["side"] for leg in body["legs"]] == ["buy", "sell"]
        assert all(leg["ratio_quantity"] == 1 for leg in body["legs"])
        assert order.order_id == "spread-1"

    @responses.activate
    def test_custom_leg_ratio(self, client):
        _mock_account()
        _mock_option_lookup(2)
        responses.add(
            responses.POST, urls.OPTIONS_ORDERS, json={"id": "s-2"}, status=201,
        )

        legs = [dict(self.LEGS[0], ratio=1), dict(self.LEGS[1], ratio=2)]
        client.order_option_spread("AAPL", 1, 1.50, legs, "credit")

        body = json.loads(responses.calls[-1].request.body)
        assert [leg["ratio_quantity"] for leg in body["legs"]] == [1, 2]

    @responses.activate
    def test_rejected_order_raises(self, client):
        _mock_account()
        _mock_option_lookup(2)
        responses.add(
            responses.POST, urls.OPTIONS_ORDERS,
            json={"detail": "Not enough buying power"}, status=400,
        )

        with pytest.raises(OrderError, match="Not enough buying power"):
            client.order_option_spread("AAPL", 1, 1.50, self.LEGS, "debit")


class TestFractionalOrders:
    def _mock_prereqs(self, price="200.00"):
        _mock_account()
        responses.add(
            responses.GET, f"{urls.QUOTES}AAPL/",
            json={"symbol": "AAPL", "last_trade_price": price,
                  "previous_close": price},
            status=200,
        )
        responses.add(
            responses.GET, urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc/", "symbol": "AAPL"}]},
            status=200,
        )
        responses.add(
            responses.POST, urls.ORDERS,
            json={"id": "frac-1", "state": "queued", "side": "buy",
                  "type": "market", "quantity": "0.5"},
            status=201,
        )

    @responses.activate
    def test_dollars_convert_to_shares(self, client):
        self._mock_prereqs("200.00")

        client.buy_stock_by_price("AAPL", 100.0)

        body = responses.calls[-1].request.body
        assert "quantity=0.5" in str(body)  # $100 / $200

    @responses.activate
    def test_uses_gfd_by_default(self, client):
        self._mock_prereqs()

        client.buy_stock_by_price("AAPL", 100.0)

        assert "time_in_force=gfd" in str(responses.calls[-1].request.body)

    def test_below_one_dollar_rejected(self, client):
        with pytest.raises(OrderError, match="at least \\$1"):
            client.buy_stock_by_price("AAPL", 0.5)

    @responses.activate
    def test_zero_price_rejected(self, client):
        _mock_account()
        responses.add(
            responses.GET, f"{urls.QUOTES}AAPL/",
            json={"symbol": "AAPL", "last_trade_price": "0", "previous_close": "0"},
            status=200,
        )

        with pytest.raises(OrderError, match="Cannot price"):
            client.buy_stock_by_price("AAPL", 100.0)


class TestCsvExport:
    ORDERS = {"results": [
        {"id": "o-1", "state": "filled", "side": "buy", "type": "market",
         "quantity": "10", "average_price": "150.00",
         "created_at": "2026-03-01T12:00:00Z", "updated_at": "2026-03-01T12:01:00Z"},
        {"id": "o-2", "state": "cancelled", "side": "sell", "type": "limit",
         "quantity": "5", "created_at": "2026-03-02T12:00:00Z"},
    ]}

    @responses.activate
    def test_writes_only_filled_orders(self, client, tmp_path):
        responses.add(responses.GET, urls.ORDERS, json=self.ORDERS, status=200)

        out = client.export_stock_orders(tmp_path / "orders.csv")

        rows = list(csv.DictReader(out.open()))
        assert [r["order_id"] for r in rows] == ["o-1"]
        assert rows[0]["side"] == "buy"

    @responses.activate
    def test_directory_gets_default_filename(self, client, tmp_path):
        responses.add(responses.GET, urls.ORDERS, json=self.ORDERS, status=200)

        out = client.export_stock_orders(tmp_path)

        assert out.name == "stock_orders.csv"
        assert out.exists()

    @responses.activate
    def test_datetimes_are_serialized(self, client, tmp_path):
        responses.add(responses.GET, urls.ORDERS, json=self.ORDERS, status=200)

        out = client.export_stock_orders(tmp_path / "o.csv")

        row = next(csv.DictReader(out.open()))
        assert row["created_at"].startswith("2026-03-01T12:00:00")

    @responses.activate
    def test_empty_export_still_writes_header(self, client, tmp_path):
        responses.add(responses.GET, urls.ORDERS, json={"results": []}, status=200)

        out = client.export_stock_orders(tmp_path / "empty.csv")

        assert out.read_text().strip().startswith("order_id,symbol,side")


class TestTrailingStopServerLimits:
    """Server-side limits confirmed against the live API on 2026-08-09."""

    def test_trailing_stop_limit_rejected_client_side(self, client):
        """Robinhood: 'Trailing stop limit orders not supported.'"""
        with pytest.raises(OrderError, match="trailing stop limit"):
            client.buy_stock("AAPL", 1, price=100.0, trail_percent=10.0)

    @responses.activate
    def test_app_version_gate_gets_explanatory_error(self, client):
        """A stale order_form_version points the reader at the constant to bump."""
        _mock_account()
        responses.add(
            responses.GET, f"{urls.QUOTES}AAPL/",
            json={"symbol": "AAPL", "last_trade_price": "100.00",
                  "previous_close": "100.00"},
            status=200,
        )
        responses.add(
            responses.GET, urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc/", "symbol": "AAPL"}]},
            status=200,
        )
        responses.add(
            responses.POST, urls.ORDERS,
            json={"non_field_errors": [
                "Your app version is missing important stock trading updates. "
                "You can still place orders on the web."
            ]},
            status=400,
        )

        with pytest.raises(OrderError, match="outdated order form version"):
            client.buy_stock("AAPL", 1, trail_percent=50.0)

    @responses.activate
    def test_field_errors_are_not_swallowed(self, client):
        """A rejection with only field errors must raise, not return a blank Order."""
        _mock_account()
        responses.add(
            responses.GET, urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc/", "symbol": "AAPL"}]},
            status=200,
        )
        responses.add(
            responses.POST, urls.ORDERS,
            json={"quantity": ["Enter a valid number."]}, status=400,
        )

        with pytest.raises(OrderError, match="rejected"):
            client.buy_stock("AAPL", 1, price=50.0)


class TestServerSideOrderConstraints:
    """Constraints confirmed against the live API on 2026-08-09.

    | order type | whole shares | fractional |
    | limit      | accepted     | rejected — "cannot include fractional shares" |
    | market     | app-version gate | app-version gate |

    Fractional trading is therefore unreachable: it needs a market order, and
    market orders are gated. These tests pin the error handling so the
    constraints stay documented in code.
    """

    def _mock_quote(self, symbol="AAPL", price="200.00"):
        responses.add(
            responses.GET, f"{urls.QUOTES}{symbol}/",
            json={"symbol": symbol, "last_trade_price": price,
                  "previous_close": price, "ask_price": price, "bid_price": price},
            status=200,
        )

    @responses.activate
    def test_fractional_limit_rejection_surfaces(self, client):
        _mock_account()
        responses.add(
            responses.GET, urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc/", "symbol": "AAPL"}]},
            status=200,
        )
        responses.add(
            responses.POST, urls.ORDERS,
            json={"non_field_errors": [
                "Limit order quantity cannot include fractional shares."
            ]},
            status=400,
        )

        with pytest.raises(OrderError, match="fractional shares"):
            client.buy_stock("AAPL", 0.003, price=200.0)

    @responses.activate
    def test_market_order_sends_collar_price(self, client):
        """Market orders must carry a collar price or Robinhood rejects them."""
        _mock_account()
        responses.add(
            responses.GET, urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc/", "symbol": "AAPL"}]},
            status=200,
        )
        self._mock_quote()
        responses.add(
            responses.POST, urls.ORDERS,
            json={"id": "m-1", "state": "queued"}, status=201,
        )

        order = client.buy_stock("AAPL", 1)

        body = str(responses.calls[-1].request.body)
        assert "price=200.0" in body
        assert "ask_price=200.0" in body
        assert "bid_price=200.0" in body
        # The collar is a protocol detail, not a limit the caller set
        assert order.price is None


class TestMarketHoursSession:
    """Extended / 24-hour session support, confirmed live 2026-08-09.

    A limit order with market_hours=all_day_hours and extended_hours=True
    reached business-logic validation ("Not enough shares to sell"), meaning
    it passed every structural check.
    """

    def _mock_prereqs(self):
        _mock_account()
        responses.add(
            responses.GET, urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc/", "symbol": "AAPL"}]},
            status=200,
        )
        responses.add(
            responses.POST, urls.ORDERS,
            json={"id": "mh-1", "state": "queued"}, status=201,
        )

    @responses.activate
    def test_all_day_hours_sets_extended_flag(self, client):
        self._mock_prereqs()

        client.buy_stock("AAPL", 1, price=100.0, market_hours="all_day_hours")

        body = str(responses.calls[-1].request.body)
        assert "market_hours=all_day_hours" in body
        assert "extended_hours=True" in body

    @responses.activate
    def test_regular_hours_clears_extended_flag(self, client):
        self._mock_prereqs()

        client.buy_stock("AAPL", 1, price=100.0, market_hours="regular_hours",
                         extended_hours=True)

        body = str(responses.calls[-1].request.body)
        assert "extended_hours=False" in body

    @responses.activate
    def test_omitted_session_sends_no_field(self, client):
        self._mock_prereqs()

        client.buy_stock("AAPL", 1, price=100.0)

        assert "market_hours" not in str(responses.calls[-1].request.body)

    def test_invalid_session_rejected(self, client):
        with pytest.raises(OrderError, match="market_hours must be one of"):
            client.buy_stock("AAPL", 1, price=100.0, market_hours="overnight")


class TestOrderFormVersion:
    """Confirmed live 2026-08-09: without this field Robinhood refuses the
    order with "Your app version is missing important stock trading updates".
    Sending 7 (or 6) is accepted; 1 is not. Captured from the web client.
    """

    @responses.activate
    def test_order_payload_carries_form_version(self, client):
        _mock_account()
        responses.add(
            responses.GET, urls.INSTRUMENTS,
            json={"results": [{"url": f"{BASE}/instruments/abc/", "symbol": "AAPL"}]},
            status=200,
        )
        responses.add(
            responses.POST, urls.ORDERS, json={"id": "o-1", "state": "queued"},
            status=201,
        )

        client.buy_stock("AAPL", 1, price=100.0)

        assert "order_form_version=7" in str(responses.calls[-1].request.body)
