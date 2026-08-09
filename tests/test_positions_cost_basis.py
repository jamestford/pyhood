"""Position cost basis and P&L.

Payload captured live 2026-08-09. average_buy_price is 0 on a settled
position; clearing_average_cost and clearing_cost_basis carry the real
figures and are what the Robinhood app displays. Reading the wrong field
made unrealized_pl equal equity — reporting a gain on a losing position.
"""

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.http import Session

BASE = "https://api.robinhood.com"


@pytest.fixture
def client():
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return PyhoodClient(session=session)


# Captured live: TSLA, down from a 472.10 average cost
SETTLED = {"results": [{
    "symbol": "TSLA",
    "quantity": "0.01162900",
    "average_buy_price": "0.0000",
    "clearing_average_cost": "472.10",
    "clearing_cost_basis": "5.49",
    "instrument": f"{BASE}/instruments/tsla-id/",
}]}


def _mock_quote(symbol, price):
    responses.add(
        responses.GET, f"{urls.QUOTES}{symbol}/",
        json={"symbol": symbol, "last_trade_price": price,
              "previous_close": price},
        status=200,
    )


class TestPositionCostBasis:
    @responses.activate
    def test_falls_back_to_clearing_average_cost(self, client):
        responses.add(responses.GET, urls.POSITIONS, json=SETTLED, status=200)
        _mock_quote("TSLA", "328.55")

        pos = client.get_positions()[0]
        assert pos.average_cost == 472.10

    @responses.activate
    def test_loss_is_reported_as_a_loss(self, client):
        responses.add(responses.GET, urls.POSITIONS, json=SETTLED, status=200)
        _mock_quote("TSLA", "328.55")

        pos = client.get_positions()[0]
        assert pos.unrealized_pl < 0
        assert pos.unrealized_pl == pytest.approx(-1.67, abs=0.02)
        assert pos.unrealized_pl_pct == pytest.approx(-30.4, abs=0.5)

    @responses.activate
    def test_symbol_read_from_payload_without_instrument_fetch(self, client):
        responses.add(responses.GET, urls.POSITIONS, json=SETTLED, status=200)
        _mock_quote("TSLA", "328.55")

        client.get_positions()

        fetched = [c.request.url for c in responses.calls]
        assert not any("instruments/tsla-id" in u for u in fetched)

    @responses.activate
    def test_average_buy_price_wins_when_populated(self, client):
        payload = {"results": [dict(SETTLED["results"][0], average_buy_price="100.00")]}
        responses.add(responses.GET, urls.POSITIONS, json=payload, status=200)
        _mock_quote("TSLA", "328.55")

        assert client.get_positions()[0].average_cost == 100.00

    @responses.activate
    def test_cost_basis_falls_back_to_qty_times_avg(self, client):
        item = dict(SETTLED["results"][0])
        item.pop("clearing_cost_basis")
        responses.add(responses.GET, urls.POSITIONS,
                      json={"results": [item]}, status=200)
        _mock_quote("TSLA", "328.55")

        pos = client.get_positions()[0]
        # 0.011629 * 472.10 = 5.49
        assert pos.unrealized_pl == pytest.approx(-1.67, abs=0.02)
