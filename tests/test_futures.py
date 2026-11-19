"""Tests for futures trading — contracts, quotes, orders, P&L."""

import pytest
import responses

from pyhood import urls
from pyhood.client import PyhoodClient
from pyhood.exceptions import APIError, SymbolNotFoundError
from pyhood.http import Session
from pyhood.models import FuturesContract, FuturesOrder, FuturesPnL, FuturesQuote

BASE = "https://api.robinhood.com"


@pytest.fixture
def client():
    """Create a client with a mock authenticated session."""
    session = Session(timeout=5)
    session.set_auth("Bearer", "test-token")
    return PyhoodClient(session=session)


# ── Contract tests ───────────────────────────────────────────────────

PRODUCT_ID = "476e059e-79c2-4bd8-810a-af471f78abed"

# The product (/ES) a contract (/ESH26) belongs to, as the live API sent it
# on 2026-11-19. Tick size, underlying and asset class live here, not on the
# contract.
PRODUCT_RESPONSE = {
    "id": PRODUCT_ID,
    "symbol": "/ES:XCME",
    "displaySymbol": "/ES",
    "simpleName": "E-mini S&P 500 Index Futures",
    "exchange": "XCME",
    "priceIncrements": "0.25",
    "rhdProductGroup": "RHD_PRODUCT_GROUP_STOCK_INDEX",
    "underlyingAsset": "PRODUCT_UNDERLYING_ASSET_INDICES",
    "futureSubType": "PRODUCT_FUTURE_SUBTYPE_FINANCIAL",
    "delivery": "PRODUCT_DELIVERY_CASH",
}


def contract_response(symbol: str, contract_id: str, multiplier: str = "50") -> dict:
    """A contract in the live shape: a `result` envelope with camelCase keys."""
    return {
        "result": {
            "id": contract_id,
            "productId": PRODUCT_ID,
            "symbol": f"/{symbol}:XCME",
            "displaySymbol": f"/{symbol}",
            "description": "E-mini S&P 500 Index Futures, Mar-26",
            "multiplier": multiplier,
            "expirationMmy": "202603",
            "expiration": "2026-03-20",
            "tradability": "FUTURES_TRADABILITY_TRADABLE",
            "state": "FUTURES_STATE_ACTIVE",
            "settlementDate": "2026-03-20",
        },
    }


def add_contract(symbol: str, contract_id: str, multiplier: str = "50") -> None:
    responses.add(
        responses.GET, urls.futures_contract_url(symbol),
        json=contract_response(symbol, contract_id, multiplier), status=200,
    )


def add_product(status: int = 200) -> None:
    responses.add(
        responses.GET, f"{urls.FUTURES_PRODUCTS}{PRODUCT_ID}/",
        json=PRODUCT_RESPONSE if status == 200 else {}, status=status,
    )


class TestGetFuturesContract:
    @responses.activate
    def test_single_contract(self, client):
        add_contract("ESH26", "abc-123")
        add_product()

        contract = client.get_futures_contract("ESH26")
        assert isinstance(contract, FuturesContract)
        assert contract.symbol == "ESH26"
        assert contract.name == "E-mini S&P 500 Index Futures, Mar-26"
        assert contract.contract_id == "abc-123"
        assert contract.expiration == "2026-03-20"
        assert contract.multiplier == 50.0

    @responses.activate
    def test_tick_size_underlying_and_asset_class_come_from_the_product(self, client):
        """The contract record has none of the three. The parser used to read
        `tick_size`, `underlying_symbol` and `asset_class` from it, which the
        API never sends, so they were always 0 and empty."""
        add_contract("ESH26", "abc-123")
        add_product()

        contract = client.get_futures_contract("ESH26")
        assert contract.tick_size == 0.25
        assert contract.underlying == "ES"  # '/ES' normalized
        assert contract.asset_class == "stock_index"  # prefix stripped

    @responses.activate
    def test_failed_product_lookup_leaves_them_unknown(self, client):
        """The contract is still returned, with None rather than a zero tick
        size that looks real."""
        add_contract("ESH26", "abc-123")
        add_product(status=404)

        contract = client.get_futures_contract("ESH26")
        assert contract.contract_id == "abc-123"
        assert contract.tick_size is None
        assert contract.underlying == ""
        assert contract.asset_class == ""

    @responses.activate
    def test_contract_case_insensitive(self, client):
        add_contract("ESH26", "abc-123")
        add_product()

        contract = client.get_futures_contract("esh26")
        assert contract.symbol == "ESH26"

    @responses.activate
    def test_contract_not_found(self, client):
        responses.add(
            responses.GET,
            urls.futures_contract_url("FAKE99"),
            json={},
            status=200,
        )
        with pytest.raises(SymbolNotFoundError):
            client.get_futures_contract("FAKE99")


class TestLiveApiShapes:
    """Payloads captured from the live API on 2026-08-09.

    The pre-existing fixtures in this file used a flat, snake_case shape that
    the API does not return; every contract and quote call failed in practice
    while those tests passed. These reproduce what the endpoints actually send.
    """

    CONTRACT_RESPONSE = {
        "result": {
            "id": "ade3740f-b580-470d-87b8-6e1a350be133",
            "productId": "476e059e-79c2-4bd8-810a-af471f78abed",
            "symbol": "/ESZ26:XCME",
            "displaySymbol": "/ESZ26",
            "description": "E-mini Standard and Poor's 500 Stock Price Index Futures, Dec-26",
            "multiplier": "50",
            "expirationMmy": "202612",
            "expiration": "2026-12-18",
            "tradability": "FUTURES_TRADABILITY_TRADABLE",
            "state": "FUTURES_STATE_ACTIVE",
            "settlementDate": "2026-12-18",
        },
    }

    QUOTE_RESPONSE = {
        "status": "SUCCESS",
        "data": [{
            "status": "SUCCESS",
            "data": {
                "ask_price": "7887.75",
                "ask_size": 1,
                "bid_price": "7807",
                "bid_size": 2,
                "last_trade_price": "7846.25",
                "symbol": "/ESZ26:XCME",
                "instrument_id": "ade3740f-b580-470d-87b8-6e1a350be133",
                "state": "active",
            },
        }],
    }

    @responses.activate
    def test_contract_result_envelope(self, client):
        responses.add(
            responses.GET, urls.futures_contract_url("ESZ26"),
            json=self.CONTRACT_RESPONSE, status=200,
        )
        add_product()

        c = client.get_futures_contract("ESZ26")
        assert c.contract_id == "ade3740f-b580-470d-87b8-6e1a350be133"
        assert c.symbol == "ESZ26"  # '/ESZ26:XCME' normalized
        assert c.name.startswith("E-mini Standard")
        assert c.expiration == "2026-12-18"
        assert c.multiplier == 50.0
        assert c.status == "active"  # 'FUTURES_STATE_ACTIVE' normalized

    @responses.activate
    def test_quote_nested_data_envelope(self, client):
        responses.add(
            responses.GET, urls.futures_contract_url("ESZ26"),
            json=self.CONTRACT_RESPONSE, status=200,
        )
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=self.QUOTE_RESPONSE, status=200,
        )

        q = client.get_futures_quote("ESZ26")
        assert q.symbol == "ESZ26"
        assert q.last_price == 7846.25
        assert q.bid == 7807.0
        assert q.ask == 7887.75
        assert q.contract_id == "ade3740f-b580-470d-87b8-6e1a350be133"

    @responses.activate
    def test_quote_by_id_skips_contract_lookup(self, client):
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=self.QUOTE_RESPONSE, status=200,
        )

        q = client.get_futures_quote_by_id(
            "ade3740f-b580-470d-87b8-6e1a350be133", symbol="ESZ26",
        )
        assert q.last_price == 7846.25
        # Only the quote call — no contract resolution
        assert len(responses.calls) == 1

    @responses.activate
    def test_missing_contract_still_raises(self, client):
        """An empty envelope must raise, not yield a blank contract."""
        responses.add(
            responses.GET, urls.futures_contract_url("BOGUS1"),
            json={"result": {}}, status=200,
        )

        with pytest.raises(SymbolNotFoundError):
            client.get_futures_contract("BOGUS1")

    @responses.activate
    def test_quote_with_no_data_raises(self, client):
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json={"status": "SUCCESS", "data": []}, status=200,
        )

        with pytest.raises(SymbolNotFoundError):
            client.get_futures_quote_by_id("some-id")

    @responses.activate
    def test_order_info_finds_and_misses(self, client):
        responses.add(
            responses.GET, f"{BASE}/futures/accounts/",
            json={"results": [{"id": "acct-1"}]}, status=200,
        )
        responses.add(
            responses.GET, urls.futures_orders_url("acct-1"),
            json={"results": [
                {"id": "order-1", "symbol": "/ESZ26", "side": "buy",
                 "type": "market", "quantity": "1", "state": "filled"},
            ]}, status=200,
        )

        found = client.get_futures_order_info("order-1", account_id="acct-1")
        assert found is not None and found.order_id == "order-1"

    @responses.activate
    def test_order_info_returns_none_when_absent(self, client):
        responses.add(
            responses.GET, urls.futures_orders_url("acct-1"),
            json={"results": []}, status=200,
        )

        assert client.get_futures_order_info("nope", account_id="acct-1") is None


class TestGetFuturesPositions:
    """Route and envelope verified live 2026-08-09; record shape unobserved."""

    @responses.activate
    def test_empty_positions(self, client):
        responses.add(
            responses.GET, urls.futures_positions_url("acct-1"),
            json={"results": []}, status=200,
        )

        assert client.get_futures_positions(account_id="acct-1") == []

    @responses.activate
    def test_positions_returned_unmapped(self, client):
        responses.add(
            responses.GET, urls.futures_positions_url("acct-1"),
            json={"results": [{"id": "pos-1", "anything": "preserved"}]}, status=200,
        )

        pos = client.get_futures_positions(account_id="acct-1")
        assert pos == [{"id": "pos-1", "anything": "preserved"}]

    @responses.activate
    def test_positions_follow_pagination(self, client):
        responses.add(
            responses.GET, urls.futures_positions_url("acct-1"),
            json={"results": [{"id": "p1"}], "next": f"{BASE}/ceres/v1/next-page/"},
            status=200,
        )
        responses.add(
            responses.GET, f"{BASE}/ceres/v1/next-page/",
            json={"results": [{"id": "p2"}], "next": None}, status=200,
        )

        assert [p["id"] for p in client.get_futures_positions("acct-1")] == ["p1", "p2"]

    @responses.activate
    def test_account_auto_discovered(self, client):
        responses.add(
            responses.GET, f"{BASE}/ceres/v1/accounts/",
            json={"results": [{"id": "auto-acct", "accountType": "FUTURES"}]},
            status=200,
        )
        responses.add(
            responses.GET, urls.futures_positions_url("auto-acct"),
            json={"results": []}, status=200,
        )

        assert client.get_futures_positions() == []


class TestGetFuturesContracts:
    @responses.activate
    def test_batch_contracts(self, client):
        add_contract("ESH26", "abc-123", multiplier="50")
        add_contract("NQH26", "def-456", multiplier="20")
        add_product()

        results = client.get_futures_contracts(["ESH26", "NQH26"])
        assert len(results) == 2
        assert "ESH26" in results
        assert "NQH26" in results
        assert results["ESH26"].multiplier == 50.0
        assert results["NQH26"].multiplier == 20.0

    @responses.activate
    def test_batch_partial_failure(self, client):
        add_contract("ESH26", "abc-123")
        add_product()
        responses.add(
            responses.GET,
            urls.futures_contract_url("FAKE99"),
            json={},
            status=200,
        )

        results = client.get_futures_contracts(["ESH26", "FAKE99"])
        assert len(results) == 1
        assert "ESH26" in results


# ── Quote tests ──────────────────────────────────────────────────────


def quote_envelope(body: dict | None) -> dict:
    """The futures marketdata envelope, shared by quotes and fundamentals."""
    data = [{"status": "SUCCESS", "data": body}] if body is not None else []
    return {"status": "SUCCESS", "data": data}


# Quote and fundamentals bodies with the keys the live API sent on 2026-11-19.
QUOTE_BODY = {
    "ask_price": "5750.50",
    "ask_size": 1,
    "ask_venue_timestamp": "2026-03-02T15:30:00Z",
    "bid_price": "5750.00",
    "bid_size": 2,
    "bid_venue_timestamp": "2026-03-02T15:30:00Z",
    "instrument_id": "abc-123",
    "last_trade_price": "5750.25",
    "last_trade_size": 1,
    "last_trade_venue_timestamp": "2026-03-02T15:30:00Z",
    "out_of_band": False,
    "state": "active",
    "symbol": "/ESH26:XCME",
    "updated_at": "2026-03-02T15:30:00Z",
}

FUNDAMENTALS_BODY = {
    "instrument_id": "abc-123",
    "open": "5745.00",
    "high": "5780.00",
    "low": "5720.00",
    "previous_close_price": "5740.00",
    "volume": "1500000",
}


class TestGetFuturesQuote:
    @responses.activate
    def test_single_quote(self, client):
        add_contract("ESH26", "abc-123")
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=quote_envelope(QUOTE_BODY), status=200,
        )

        quote = client.get_futures_quote("ESH26")
        assert isinstance(quote, FuturesQuote)
        assert quote.symbol == "ESH26"
        assert quote.last_price == 5750.25
        assert quote.bid == 5750.00
        assert quote.ask == 5750.50
        assert quote.contract_id == "abc-123"
        # The contract lookup and the quote. A quote needs only the contract
        # ID, so it does not fetch the product.
        assert len(responses.calls) == 2

    @responses.activate
    def test_session_fields_are_none_unless_asked_for(self, client):
        """The quote carries no high, low, previous close or volume. The
        parser used to read `high_price`, `low_price`, `previous_close` and
        `volume` from it, so they were always 0."""
        add_contract("ESH26", "abc-123")
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=quote_envelope(QUOTE_BODY), status=200,
        )

        quote = client.get_futures_quote("ESH26")
        assert quote.high is None
        assert quote.low is None
        assert quote.prev_close is None
        assert quote.volume is None

    @responses.activate
    def test_include_fundamentals_fills_the_session_fields(self, client):
        add_contract("ESH26", "abc-123")
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=quote_envelope(QUOTE_BODY), status=200,
        )
        responses.add(
            responses.GET, urls.FUTURES_FUNDAMENTALS,
            json=quote_envelope(FUNDAMENTALS_BODY), status=200,
        )

        quote = client.get_futures_quote("ESH26", include_fundamentals=True)
        assert quote.last_price == 5750.25
        assert quote.high == 5780.00
        assert quote.low == 5720.00
        assert quote.prev_close == 5740.00
        assert quote.volume == 1500000
        assert responses.calls[-1].request.params == {"ids": "abc-123"}

    @responses.activate
    def test_quote_by_id_takes_include_fundamentals(self, client):
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=quote_envelope(QUOTE_BODY), status=200,
        )
        responses.add(
            responses.GET, urls.FUTURES_FUNDAMENTALS,
            json=quote_envelope(FUNDAMENTALS_BODY), status=200,
        )

        quote = client.get_futures_quote_by_id("abc-123", include_fundamentals=True)
        assert quote.volume == 1500000
        assert len(responses.calls) == 2

    @responses.activate
    def test_quotes_passes_include_fundamentals_through(self, client):
        add_contract("ESH26", "abc-123")
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=quote_envelope(QUOTE_BODY), status=200,
        )
        responses.add(
            responses.GET, urls.FUTURES_FUNDAMENTALS,
            json=quote_envelope(FUNDAMENTALS_BODY), status=200,
        )

        quotes = client.get_futures_quotes(["ESH26"], include_fundamentals=True)
        assert quotes["ESH26"].high == 5780.00

    @responses.activate
    def test_quote_no_results(self, client):
        add_contract("ESH26", "abc-123")
        responses.add(
            responses.GET, urls.FUTURES_QUOTES,
            json=quote_envelope(None), status=200,
        )

        with pytest.raises(SymbolNotFoundError):
            client.get_futures_quote("ESH26")


# ── Account tests ────────────────────────────────────────────────────


class TestGetFuturesAccountId:
    @responses.activate
    def test_discover_account(self, client):
        responses.add(
            responses.GET,
            urls.FUTURES_ACCOUNTS,
            json={
                "results": [
                    {"id": "stock-001", "accountType": "MARGIN"},
                    {"id": "futures-001", "accountType": "FUTURES"},
                ],
            },
            status=200,
        )

        account_id = client.get_futures_account_id()
        assert account_id == "futures-001"

    @responses.activate
    def test_no_futures_account(self, client):
        responses.add(
            responses.GET,
            urls.FUTURES_ACCOUNTS,
            json={
                "results": [
                    {"id": "stock-001", "accountType": "MARGIN"},
                ],
            },
            status=200,
        )

        with pytest.raises(APIError, match="No futures account found"):
            client.get_futures_account_id()


# ── Order tests ──────────────────────────────────────────────────────


SAMPLE_ORDER = {
    "id": "order-001",
    "symbol": "ESH26",
    "side": "buy",
    "type": "limit",
    "quantity": "2",
    "price": "5750.00",
    "state": "filled",
    "created_at": "2026-03-15T10:30:00Z",
    "closing_strategy": "CLOSING",
    "legs": [{
        "executions": [{
            "settlement": {
                "realized_pnl": "1250.00",
            },
        }],
    }],
}

SAMPLE_OPENING_ORDER = {
    "id": "order-002",
    "symbol": "ESH26",
    "side": "buy",
    "type": "market",
    "quantity": "1",
    "price": "5700.00",
    "state": "filled",
    "created_at": "2026-03-14T09:00:00Z",
    "opening_strategy": "OPENING",
    "legs": [{
        "executions": [{
            "settlement": {
                "realized_pnl": "0",
            },
        }],
    }],
}


class TestGetFuturesOrders:
    @responses.activate
    def test_fetch_all_orders(self, client):
        # Mock account discovery
        responses.add(
            responses.GET,
            urls.FUTURES_ACCOUNTS,
            json={
                "results": [{"id": "futures-001", "accountType": "FUTURES"}],
            },
            status=200,
        )
        # Mock orders
        responses.add(
            responses.GET,
            urls.futures_orders_url("futures-001"),
            json={
                "results": [SAMPLE_ORDER, SAMPLE_OPENING_ORDER],
                "next": None,
            },
            status=200,
        )

        orders = client.get_futures_orders()
        assert len(orders) == 2
        assert isinstance(orders[0], FuturesOrder)
        assert orders[0].order_id == "order-001"
        assert orders[0].symbol == "ESH26"
        assert orders[0].status == "filled"
        assert orders[0].realized_pnl == 1250.0

    @responses.activate
    def test_fetch_with_pagination(self, client):
        page2_url = urls.futures_orders_url("futures-001") + "?cursor=page2"
        # Mock account
        responses.add(
            responses.GET,
            urls.FUTURES_ACCOUNTS,
            json={
                "results": [{"id": "futures-001", "accountType": "FUTURES"}],
            },
            status=200,
        )
        # Page 1
        responses.add(
            responses.GET,
            urls.futures_orders_url("futures-001"),
            json={
                "results": [SAMPLE_ORDER],
                "next": page2_url,
            },
            status=200,
        )
        # Page 2
        responses.add(
            responses.GET,
            page2_url,
            json={
                "results": [SAMPLE_OPENING_ORDER],
                "next": None,
            },
            status=200,
        )

        orders = client.get_futures_orders()
        assert len(orders) == 2

    @responses.activate
    def test_fetch_with_explicit_account(self, client):
        responses.add(
            responses.GET,
            urls.futures_orders_url("my-account"),
            json={
                "results": [SAMPLE_ORDER],
                "next": None,
            },
            status=200,
        )

        orders = client.get_futures_orders(account_id="my-account")
        assert len(orders) == 1
        assert orders[0].account_id == "my-account"


class TestGetFilledFuturesOrders:
    @responses.activate
    def test_filters_to_filled_only(self, client):
        pending_order = {
            "id": "order-003",
            "symbol": "ESH26",
            "side": "buy",
            "type": "limit",
            "quantity": "1",
            "price": "5600.00",
            "state": "pending",
            "created_at": "2026-03-16T10:00:00Z",
            "legs": [],
        }
        responses.add(
            responses.GET,
            urls.FUTURES_ACCOUNTS,
            json={
                "results": [{"id": "futures-001", "accountType": "FUTURES"}],
            },
            status=200,
        )
        responses.add(
            responses.GET,
            urls.futures_orders_url("futures-001"),
            json={
                "results": [SAMPLE_ORDER, pending_order],
                "next": None,
            },
            status=200,
        )

        orders = client.get_filled_futures_orders()
        assert len(orders) == 1
        assert orders[0].status == "filled"


# ── P&L tests ────────────────────────────────────────────────────────


class TestExtractFuturesPnl:
    def test_extract_pnl_from_closing_order(self):
        pnl = PyhoodClient._extract_futures_pnl(SAMPLE_ORDER)
        assert isinstance(pnl, FuturesPnL)
        assert pnl.realized_pnl == 1250.0
        assert pnl.direction == "CLOSING"
        assert pnl.order_id == "order-001"

    def test_extract_pnl_from_opening_order(self):
        pnl = PyhoodClient._extract_futures_pnl(SAMPLE_OPENING_ORDER)
        assert isinstance(pnl, FuturesPnL)
        assert pnl.realized_pnl == 0.0
        assert pnl.direction == "OPENING"

    def test_extract_pnl_empty_legs(self):
        order = {"id": "x", "legs": []}
        pnl = PyhoodClient._extract_futures_pnl(order)
        assert pnl is None

    def test_extract_pnl_no_legs(self):
        order = {"id": "x"}
        pnl = PyhoodClient._extract_futures_pnl(order)
        assert pnl is None

    def test_extract_pnl_no_executions(self):
        order = {"id": "x", "legs": [{"executions": []}]}
        pnl = PyhoodClient._extract_futures_pnl(order)
        assert pnl is None


class TestCalculateFuturesPnl:
    def test_aggregate_pnl_closing_only(self, client):
        orders = [
            FuturesOrder(
                order_id="1", symbol="ESH26", side="buy", order_type="limit",
                quantity=1, price=5750.0, status="filled",
                direction="CLOSING", realized_pnl=500.0,
            ),
            FuturesOrder(
                order_id="2", symbol="ESH26", side="sell", order_type="limit",
                quantity=1, price=5700.0, status="filled",
                direction="OPENING", realized_pnl=0.0,
            ),
            FuturesOrder(
                order_id="3", symbol="NQH26", side="sell", order_type="limit",
                quantity=2, price=20000.0, status="filled",
                direction="CLOSING", realized_pnl=750.0,
            ),
        ]
        total = client.calculate_futures_pnl(orders=orders)
        assert total == 1250.0

    def test_aggregate_pnl_no_closing_orders(self, client):
        orders = [
            FuturesOrder(
                order_id="1", symbol="ESH26", side="buy", order_type="limit",
                quantity=1, price=5750.0, status="filled",
                direction="OPENING", realized_pnl=0.0,
            ),
        ]
        total = client.calculate_futures_pnl(orders=orders)
        assert total == 0.0

    def test_aggregate_pnl_empty(self, client):
        total = client.calculate_futures_pnl(orders=[])
        assert total == 0.0
