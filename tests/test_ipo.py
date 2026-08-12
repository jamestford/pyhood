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


class TestLiveOfferingShapes:
    """Shapes captured from a live offering — RVII on 2026-08-12.

    Before this, four of the IPO endpoints had never been seen against a real
    offering, because they 404 when none exists. RVII was in its order book
    with `ipo_access_status` `price_finalized`, listing the next day. Account
    identifiers and balances are replaced with placeholders.
    """

    INSTRUMENT_ID = "e958d09f-0a47-4468-b1e4-e66b6c3598fa"

    CARD = {
        "instrument_id": INSTRUMENT_ID,
        "name": "Robinhood Ventures Fund II",
        "title": "RVII",
        "subtitle": "$25.00",
        "accent_color": {"light": "fg", "dark": "fg"},
        "action": {
            "action_type": "deeplink",
            "action_data": {"uri": f"robinhood://instrument?id={INSTRUMENT_ID}"},
        },
        "logo_images": {
            "dark": {"@1x": "https://cdn.robinhood.com/app_assets/ipoa/x/night.png"},
            "light": {"@1x": "https://cdn.robinhood.com/app_assets/ipoa/x/day.png"},
        },
    }

    ORDER_ENTRY = {
        "account_number": "ACCOUNT_NUMBER",
        "instrument_id": INSTRUMENT_ID,
        "context": {
            "phase": "price_finalized",
            "instrument_symbol": "RVII",
            "instrument_url": "https://api.robinhood.com/instruments/x/",
            "ipo_access_quote": {"price": "25.00"},
            "ipo_access_cob_deadline": "2026-08-12T23:00:00Z",
            "has_cob_deadline_passed": True,
            "user_is_enrolled": False,
            "account_type": "individual",
            "existing_order": None,
            "available_buying_power": {"currency_code": "USD", "amount": "0.00"},
        },
        "form_state": {
            "form_state_id": "price_finalized2525",
            "form_invalid_alert": {"title": "Price update"},
        },
        "order_entry_view_model": {
            "title": "Request shares",
            "rows": [],
            "limit_options": [],
            "order_summary": {},
            "buying_power_description": "",
            "disclaimer": "",
        },
        "trade_receipt_view_model": None,
        "action_required_view_model": None,
        "ipoa_new_orders_blocked_details": "",
    }

    @responses.activate
    def test_card_carries_ticker_and_price(self, client):
        """`title` is the ticker and `subtitle` the offer price."""
        responses.add(
            responses.GET,
            urls.ipo_access_cards_url(self.INSTRUMENT_ID),
            json={"results": [self.CARD]},
            status=200,
        )

        cards = client.get_ipo_access_cards(self.INSTRUMENT_ID)

        assert len(cards) == 1
        assert cards[0]["title"] == "RVII"
        assert cards[0]["subtitle"] == "$25.00"
        assert cards[0]["instrument_id"] == self.INSTRUMENT_ID

    @responses.activate
    def test_order_entry_context_is_the_useful_part(self, client):
        responses.add(
            responses.GET,
            urls.ipo_access_order_entry_url(self.INSTRUMENT_ID),
            json=self.ORDER_ENTRY,
            status=200,
        )

        vm = client.get_ipo_access_order_entry(self.INSTRUMENT_ID)
        context = vm["context"]

        assert context["phase"] == "price_finalized"
        assert context["instrument_symbol"] == "RVII"
        assert context["has_cob_deadline_passed"] is True
        assert context["user_is_enrolled"] is False
        # No order placed, so there is no receipt yet.
        assert vm["trade_receipt_view_model"] is None

    @responses.activate
    def test_cards_resolve_after_the_book_closes(self, client):
        """The list reverts to its empty state; cards still resolve by ID.

        Both were observed on the same offering minutes apart, which is why
        `has_ipo_offerings()` cannot be used to decide whether to fetch a card.
        """
        responses.add(
            responses.GET, urls.IPO_ACCESS_LIST,
            json={"empty_state": {"title": "No new IPOs available"}}, status=200,
        )
        responses.add(
            responses.GET, urls.ipo_access_cards_url(self.INSTRUMENT_ID),
            json={"results": [self.CARD]}, status=200,
        )

        assert client.has_ipo_offerings() is False
        assert client.get_ipo_access_cards(self.INSTRUMENT_ID)[0]["title"] == "RVII"
