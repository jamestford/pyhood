"""Tests for IPO Access.

The list and cards payloads below were captured from the live API on
2026-08-09. The summary, order-entry, allocation and trade-receipt endpoints
return 404 unless an offering is live, so their populated shapes could not be
observed — those tests assert routing and pass-through only, deliberately
making no claim about response structure.
"""

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.http import Session

AAPL_ID = "450dfc6d-5510-4d40-abfb-f633b7d9be3e"


@pytest.fixture
def client():
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return PyhoodClient(session=session)


# Captured live 2026-08-09 — an account with no offerings available
EMPTY_LIST_RESPONSE = {
    "empty_state": {
        "title": "No new IPOs available",
        "subtitle_markdown": "This list gets updated whenever a new IPO becomes available.",
    },
    "learn_tab": {"sections": [{"section_type": "video", "section_data": {}}]},
}

# Captured live 2026-08-09
CARDS_RESPONSE = {
    "results": [{
        "instrument_id": AAPL_ID,
        "name": "Apple",
        "title": "AAPL",
        "subtitle": "",
        "accent_color": {"light": "fg", "dark": "fg"},
        "action": {"action_type": "deeplink", "action_data": {}},
    }],
}


class TestIpoAccessList:
    @responses.activate
    def test_empty_state(self, client):
        responses.add(
            responses.GET, urls.IPO_ACCESS_LIST, json=EMPTY_LIST_RESPONSE, status=200,
        )

        data = client.get_ipo_access_list()
        assert "empty_state" in data
        assert data["empty_state"]["title"] == "No new IPOs available"

    @responses.activate
    def test_has_ipo_offerings_false_when_empty(self, client):
        responses.add(
            responses.GET, urls.IPO_ACCESS_LIST, json=EMPTY_LIST_RESPONSE, status=200,
        )

        assert client.has_ipo_offerings() is False

    @responses.activate
    def test_has_ipo_offerings_true_when_populated(self, client):
        responses.add(
            responses.GET, urls.IPO_ACCESS_LIST,
            json={"sections": [{"offering": "something"}]}, status=200,
        )

        assert client.has_ipo_offerings() is True


class TestIpoAccessCards:
    @responses.activate
    def test_single_id(self, client):
        responses.add(
            responses.GET, urls.ipo_access_cards_url(AAPL_ID),
            json=CARDS_RESPONSE, status=200,
        )

        cards = client.get_ipo_access_cards(AAPL_ID)
        assert len(cards) == 1
        assert cards[0]["instrument_id"] == AAPL_ID
        assert cards[0]["name"] == "Apple"

    @responses.activate
    def test_multiple_ids_are_comma_joined(self, client):
        url = urls.ipo_access_cards_url([AAPL_ID, "other-id"])
        assert f"{AAPL_ID},other-id" in url

        responses.add(responses.GET, url, json=CARDS_RESPONSE, status=200)
        assert client.get_ipo_access_cards([AAPL_ID, "other-id"])

    @responses.activate
    def test_missing_results_yields_empty_list(self, client):
        responses.add(
            responses.GET, urls.ipo_access_cards_url(AAPL_ID), json={}, status=200,
        )

        assert client.get_ipo_access_cards(AAPL_ID) == []


class TestIpoAccessViewModels:
    """Routing only — these shapes are unobserved (404 without a live offering)."""

    @responses.activate
    def test_summary_routes_to_instrument(self, client):
        responses.add(
            responses.GET, urls.ipo_access_summary_url("inst-1"),
            json={"anything": 1}, status=200,
        )

        assert client.get_ipo_access_summary("inst-1") == {"anything": 1}
        assert "summary/inst-1/" in responses.calls[0].request.url

    @responses.activate
    def test_order_entry_includes_account_number(self, client):
        responses.add(
            responses.GET,
            urls.ipo_access_order_entry_url("inst-1", "12345"),
            json={"context": {}}, status=200,
        )

        client.get_ipo_access_order_entry("inst-1", account_number="12345")
        assert "account_number=12345" in responses.calls[0].request.url

    @responses.activate
    def test_order_entry_without_account_number(self, client):
        responses.add(
            responses.GET, urls.ipo_access_order_entry_url("inst-1"),
            json={"context": {}}, status=200,
        )

        client.get_ipo_access_order_entry("inst-1")
        assert "account_number" not in responses.calls[0].request.url

    @responses.activate
    def test_allocation_and_receipt_route(self, client):
        responses.add(
            responses.GET, urls.ipo_access_allocation_results_url("inst-1"),
            json={"a": 1}, status=200,
        )
        responses.add(
            responses.GET, urls.ipo_access_trade_receipt_url("order-1"),
            json={"b": 2}, status=200,
        )

        assert client.get_ipo_access_allocation_results("inst-1") == {"a": 1}
        assert client.get_ipo_access_trade_receipt("order-1") == {"b": 2}


class TestIpoAccessOrders:
    ORDERS = {
        "results": [
            {
                "id": "ipo-order", "state": "filled", "side": "buy",
                "type": "limit", "quantity": "10",
                "created_at": "2026-03-01T12:00:00Z",
                "is_ipo_access_order": True,
            },
            {
                "id": "normal-order", "state": "filled", "side": "buy",
                "type": "market", "quantity": "5",
                "created_at": "2026-03-02T12:00:00Z",
            },
        ],
    }

    @responses.activate
    def test_filters_to_ipo_orders(self, client):
        for _ in range(2):
            responses.add(responses.GET, urls.ORDERS, json=self.ORDERS, status=200)

        orders = client.get_ipo_access_orders()
        assert [o.order_id for o in orders] == ["ipo-order"]

    @responses.activate
    def test_no_ipo_orders_returns_empty(self, client):
        responses.add(
            responses.GET, urls.ORDERS,
            json={"results": [self.ORDERS["results"][1]]}, status=200,
        )

        assert client.get_ipo_access_orders() == []

    @responses.activate
    def test_start_date_is_forwarded(self, client):
        for _ in range(2):
            responses.add(responses.GET, urls.ORDERS, json=self.ORDERS, status=200)

        client.get_ipo_access_orders(start_date="2026-01-01")
        assert "created_at%5Bgte%5D" in responses.calls[0].request.url
