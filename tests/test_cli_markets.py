"""The crypto and futures commands: `pyhood crypto ...`, `pyhood futures ...`."""

import json
import time
from datetime import datetime, timezone

import pytest

from pyhood import cli, onboarding
from pyhood import cli_markets as markets
from pyhood.crypto.models import (
    CryptoAccount,
    CryptoHolding,
    CryptoOrder,
    CryptoQuote,
    EstimatedPrice,
    TradingPair,
)
from pyhood.exceptions import APIError, OrderError, SymbolNotFoundError
from pyhood.models import FuturesContract, FuturesOrder, FuturesQuote

UTC = timezone.utc
pytestmark = pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset")


@pytest.fixture(autouse=True)
def eastern_time_on_the_path(monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    monkeypatch.setattr(cli, "program", lambda: "pyhood")
    monkeypatch.setattr(markets, "program", lambda: "pyhood")
    yield
    monkeypatch.undo()
    time.tzset()


def crypto_order_row(**fields):
    base = dict(
        order_id="c-1", client_order_id="x", side="buy", order_type="limit",
        symbol="BTC-USD", status="open", price=30000.0, quantity=0.0001,
        filled_quantity=0.0, remaining_quantity=0.0001, average_filled_price=None, fee=0.0,
        created_at=datetime(2026, 11, 24, 22, 0, tzinfo=UTC),
        updated_at=datetime(2026, 11, 24, 22, 0, tzinfo=UTC),
    )
    return CryptoOrder(**{**base, **fields})


class CryptoFake:
    """Stands in for CryptoClient, recording anything that would change the account."""

    PAIRS = {
        "BTC-USD": TradingPair("BTC-USD", True, None, 20.0, 0.01, 1e-08, "BTC", "USD",
                               api_tradable=True, status="tradable", min_order_amount=0.1),
        "BILL-USD": TradingPair("BILL-USD", True, None, 9900000.0, 1e-06, 0.1, "BILL", "USD",
                                api_tradable=False, status="tradable", min_order_amount=0.1),
    }

    def __init__(self, buying_power=500.0, holdings=(), orders=(), reject=None,
                 after_cancel="canceled"):
        self.buying_power, self.holdings = buying_power, list(holdings)
        self.orders = {o.order_id: o for o in orders}
        self.reject, self.after_cancel = reject, after_cancel
        self.writes, self.reads = [], []

    def get_account(self):
        self.reads.append("get_account")
        return CryptoAccount("crypto-acct", self.buying_power, "active", api_tradable=True)

    def get_best_bid_ask(self, *symbols):
        when = datetime(2026, 11, 24, 23, 10, tzinfo=UTC)
        prices = {"BTC-USD": (59943.0, 59934.21), "ETH-USD": (1681.25, 1681.25)}
        return [CryptoQuote(s, *prices[s], when) for s in symbols if s in prices]

    def get_holdings(self, account_number, *asset_codes):
        return [h for h in self.holdings if not asset_codes or h.asset_code in asset_codes]

    def get_orders(self, account_number):
        return list(self.orders.values())

    def get_order(self, account_number, order_id):
        if order_id not in self.orders:
            raise OrderError(f"Order {order_id} not found")
        return self.orders[order_id]

    def get_trading_pairs(self, *symbols):
        self.reads.append("get_trading_pairs")
        if any(s not in self.PAIRS for s in symbols):
            raise APIError("symbol: Select a valid choice.")
        return [self.PAIRS[s] for s in symbols]

    def get_estimated_price(self, symbol, side, quantity):
        self.reads.append("get_estimated_price")
        return EstimatedPrice(symbol, side, quantity, bid_price=59900.0, ask_price=60000.0,
                              fee=round(quantity * 60000.0 * 0.0095, 2))

    def place_order(self, account_number, side, order_type, symbol, order_config):
        self.writes.append((account_number, side, order_type, symbol, order_config))
        if self.reject:
            raise OrderError(self.reject)
        order = crypto_order_row(order_id="new-crypto", side=side, order_type=order_type,
                                 symbol=symbol)
        self.orders[order.order_id] = order
        return order

    def cancel_order(self, order_id):
        self.writes.append(("cancel", order_id))
        current = self.orders[order_id]
        self.orders[order_id] = crypto_order_row(
            **{**{f: getattr(current, f) for f in (
                "order_id", "side", "order_type", "symbol", "price", "quantity",
                "filled_quantity")}, "status": self.after_cancel},
        )
        return {}


def code_from(output):
    return output.split("--confirm ")[-1].split()[0]


class TestSymbols:
    @pytest.mark.parametrize(("typed", "pair"), [
        ("btc", "BTC-USD"), ("BTC", "BTC-USD"), ("BTC-USD", "BTC-USD"), (" eth ", "ETH-USD"),
    ])
    def test_a_coin_may_be_named_with_or_without_usd(self, typed, pair):
        assert markets.pair(typed) == pair

    def test_small_quantities_are_never_written_in_scientific_notation(self):
        assert markets.quantity_text(0.00001) == "0.00001"
        assert markets.quantity_text(1e-08) == "0.00000001"
        assert markets.quantity_text(2.0) == "2"


class TestCryptoReading:
    def test_quote(self, capsys):
        assert markets.crypto_quote(CryptoFake(), ["btc", "ETH"]) == 0

        out = capsys.readouterr().out
        assert "BTC-USD  $59,943.00  $59,934.21  2026-11-24 18:10 EST" in out
        assert "charges a fee on each crypto trade" in out

    def test_unknown_coin_is_reported(self, capsys):
        assert markets.crypto_quote(CryptoFake(), ["BTC", "NOPE"]) == 1
        assert "No quote for NOPE-USD." in capsys.readouterr().err

    def test_holdings_are_valued_at_the_bid(self, capsys):
        client = CryptoFake(holdings=[CryptoHolding("BTC", 0.5, 0.4), CryptoHolding("ETH", 0, 0)])

        markets.crypto_holdings(client)

        out = capsys.readouterr().out
        assert out.splitlines()[1].split() == ["BTC", "0.5", "0.4", "$59,943.00", "$29,971.50"]
        assert "ETH" not in out  # a zero holding is not a holding
        assert "Total value: $29,971.50" in out
        assert "Crypto buying power: $500.00" in out

    def test_no_holdings(self, capsys):
        markets.crypto_holdings(CryptoFake())
        assert capsys.readouterr().out.splitlines() == [
            "No crypto holdings.", "Crypto buying power: $500.00",
        ]

    def test_orders_and_open_only(self, capsys):
        done = crypto_order_row(order_id="c-0", status="canceled")
        client = CryptoFake(orders=[done, crypto_order_row()])

        markets.crypto_orders(client)
        assert capsys.readouterr().out.count("BTC-USD") == 2

        markets.crypto_orders(client, open_only=True)
        out = capsys.readouterr().out
        assert out.count("BTC-USD") == 1 and out.splitlines()[1].split()[-2:] == ["open", "c-1"]

        markets.crypto_orders(CryptoFake(), open_only=True)
        assert capsys.readouterr().out.strip() == "No open crypto orders."

    def test_json(self, capsys):
        client = CryptoFake(holdings=[CryptoHolding("BTC", 0.5, 0.4)],
                            orders=[crypto_order_row()])
        for command, args in ((markets.crypto_quote, (["BTC"],)), (markets.crypto_holdings, ()),
                              (markets.crypto_orders, ())):
            assert command(client, *args, as_json_output=True) == 0
            json.loads(capsys.readouterr().out)


class TestCryptoOrder:
    def test_without_a_code_it_previews_and_sends_nothing(self, capsys):
        client = CryptoFake()

        assert markets.crypto_order(client, "buy", "btc", 0.001, limit=50000.0) == 0

        out = capsys.readouterr().out
        assert client.writes == []
        assert out.startswith("PREVIEW. Nothing has been sent.")
        assert "Buy 0.001 BTC, limit $50,000.00" in out
        # The fee is part of what it costs, and is shown as such.
        assert "Estimated cost:     $50.57 ($50.00 plus a fee of about $0.57)" in out
        assert "BTC now:            $60,000.00 to buy" in out
        assert "Buying power:       $500.00" in out
        assert "16.7% below the current price" in out
        assert "stays open until it fills or you cancel it" in out
        assert f"pyhood crypto buy BTC 0.001 --limit 50000 --confirm {code_from(out)}" in out

    def test_the_printed_command_places_exactly_the_previewed_order(self, capsys):
        client = CryptoFake()
        markets.crypto_order(client, "buy", "BTC", 0.001, limit=50000.0)
        code = code_from(capsys.readouterr().out)

        assert markets.crypto_order(client, "buy", "BTC", 0.001, limit=50000.0, confirm=code,
                                    settle_seconds=0) == 0

        assert client.writes == [("crypto-acct", "buy", "limit", "BTC-USD",
                                  {"asset_quantity": "0.001", "limit_price": "50000"})]
        out = capsys.readouterr().out
        assert out.startswith("PLACED: Buy 0.001 BTC, limit $50,000.00")
        assert "pyhood crypto cancel new-crypto" in out

    def test_market_order(self, capsys):
        client = CryptoFake()
        markets.crypto_order(client, "buy", "BTC", 0.001)
        out = capsys.readouterr().out
        assert "Buy 0.001 BTC, at market" in out
        assert "Estimated cost:     $60.57" in out
        assert "Crypto trades at all hours" in out

        markets.crypto_order(client, "buy", "BTC", 0.001, confirm=code_from(out),
                             settle_seconds=0)
        assert client.writes[0][2:] == ("market", "BTC-USD", {"asset_quantity": "0.001"})

    @pytest.mark.parametrize("changed", [
        {"quantity": 0.01}, {"symbol": "ETH"}, {"limit": 5000.0}, {"limit": None},
        {"side": "sell"},
    ])
    def test_a_code_for_one_order_will_not_place_another(self, capsys, changed):
        client = CryptoFake()
        order = {"side": "buy", "symbol": "BTC", "quantity": 0.001, "limit": 50000.0}
        markets.crypto_order(client, **order)
        code = code_from(capsys.readouterr().out)
        client.reads.clear()

        assert markets.crypto_order(client, **{**order, **changed}, confirm=code,
                                    settle_seconds=0) == 2
        assert client.writes == [] and client.reads == []

    def test_selling_shows_proceeds_after_the_fee_and_what_is_held(self, capsys):
        client = CryptoFake(holdings=[CryptoHolding("BTC", 0.5, 0.4)])

        markets.crypto_order(client, "sell", "BTC", 0.5, limit=60000.0)

        out = capsys.readouterr().out
        assert "Estimated proceeds: $29,715.00 ($30,000.00 less a fee of about $285.00)" in out
        assert "You hold:           0.4 BTC available" in out
        assert "less than this order sells" in out

    def test_more_than_buying_power_counts_the_fee(self, capsys):
        markets.crypto_order(CryptoFake(buying_power=60.0), "buy", "BTC", 0.001)
        assert "more than your crypto buying power" in capsys.readouterr().out

    def test_an_order_under_the_minimum_is_pointed_out(self, capsys):
        markets.crypto_order(CryptoFake(), "buy", "BTC", 0.000001)
        assert "under Robinhood's minimum of $0.10 for BTC" in capsys.readouterr().out

    def test_a_coin_robinhood_does_not_list_is_refused(self):
        client = CryptoFake()
        with pytest.raises(cli.UsageError, match="no trading pair NOPE-USD"):
            markets.crypto_order(client, "buy", "NOPE", 1)
        assert client.writes == []

    def test_a_coin_the_api_cannot_trade_is_refused(self):
        with pytest.raises(cli.UsageError, match="cannot be traded through Robinhood's Crypto"):
            markets.crypto_order(CryptoFake(), "buy", "BILL", 10)

    def test_more_than_the_largest_order_is_refused(self):
        with pytest.raises(cli.UsageError, match="largest BTC order is 20"):
            markets.crypto_order(CryptoFake(), "buy", "BTC", 21)

    def test_a_rejected_order_reports_robinhoods_reason(self, capsys):
        client = CryptoFake(reject="insufficient buying power")
        markets.crypto_order(client, "buy", "BTC", 0.001)
        code = code_from(capsys.readouterr().out)

        assert markets.crypto_order(client, "buy", "BTC", 0.001, confirm=code,
                                    settle_seconds=0) == 1
        assert "insufficient buying power" in capsys.readouterr().err


class TestCryptoCancel:
    def test_it_cancels_at_once(self, capsys):
        client = CryptoFake(orders=[crypto_order_row()])

        assert markets.crypto_cancel(client, "c-1", settle_seconds=0) == 0

        assert client.writes == [("cancel", "c-1")]
        assert capsys.readouterr().out.startswith(
            "CANCELLED: buy 0.0001 BTC-USD, limit $30,000.00, placed 2026-11-24 17:00 EST"
        )

    def test_a_finished_order_is_left_alone(self, capsys):
        client = CryptoFake(orders=[crypto_order_row(status="filled")])

        assert markets.crypto_cancel(client, "c-1", settle_seconds=0) == 1
        assert client.writes == []
        assert "already filled" in capsys.readouterr().out

    def test_an_order_that_filled_first_says_so(self, capsys):
        client = CryptoFake(orders=[crypto_order_row()], after_cancel="filled")

        markets.crypto_cancel(client, "c-1", settle_seconds=0)
        assert "the order is now filled" in capsys.readouterr().out


class FuturesFake:
    def get_futures_quotes(self, symbols, include_fundamentals=False):
        self.asked = (symbols, include_fundamentals)
        return {s: FuturesQuote(s, 7219.25, bid=7218.75, ask=7219.25, high=7224.0,
                                low=7212.5, prev_close=7217.5, volume=2626)
                for s in symbols if not s.startswith("NOPE")}

    def get_futures_contract(self, symbol):
        return FuturesContract(symbol, "E-mini S&P 500 Index Futures, Dec-26", "id",
                               "2026-12-18", 0.25, 50.0, "active", "ES", "stock_index")

    def get_futures_product_contracts(self, product):
        self.products_asked = getattr(self, "products_asked", []) + [product]
        if product != "ES":
            raise SymbolNotFoundError(f"No futures product {product}")
        return [
            FuturesContract("ESZ26", "E-mini S&P 500, Dec-26", "id-z", "2026-12-18", 0.25,
                            50.0, "active", "ES", "stock_index"),
            FuturesContract("ESH27", "E-mini S&P 500, Mar-27", "id-h", "2027-03-19", 0.25,
                            50.0, "active", "ES", "stock_index"),
        ]

    def get_futures_orders(self):
        return [
            FuturesOrder("f1", "ESZ26", "sell", "limit", 1, 7250.0, "filled",
                         created_at="2026-11-20T15:00:00Z", direction="CLOSING",
                         realized_pnl=125.0),
            FuturesOrder("f0", "ESZ26", "buy", "limit", 1, 7247.5, "filled",
                         created_at="2026-11-20T14:00:00Z", direction="OPENING"),
        ]

    def get_futures_positions(self):
        return []


class TestFutures:
    def test_quote_asks_for_the_session_range(self, capsys):
        client = FuturesFake()

        assert markets.futures_quote(client, ["/esz26"]) == 0

        assert client.asked == (["ESZ26"], True)
        row = capsys.readouterr().out.splitlines()[1].split()
        assert row == ["ESZ26", "7,219.25", "+0.02%", "7,218.75", "7,219.25", "7,224",
                       "7,212.5", "7,217.5", "2,626"]

    def test_a_product_is_quoted_by_its_nearest_contract(self, capsys):
        """Asked what S&P futures were doing, a model guessed three expired
        contract codes. Nobody should have to know which month is current."""
        client = FuturesFake()

        assert markets.futures_quote(client, ["es"]) == 0

        assert client.asked == (["ESZ26"], True)
        out = capsys.readouterr().out
        assert out.startswith("ES: the nearest contract is ESZ26, expiring 2026-12-18.")

    def test_a_contract_code_is_used_as_given_with_no_lookup(self):
        client = FuturesFake()
        markets.futures_quote(client, ["ESH27"])
        assert client.asked == (["ESH27"], True)
        assert not hasattr(client, "products_asked")

    @pytest.mark.parametrize(("typed", "is_contract"), [
        ("ESZ26", True), ("CLF27", True), ("6EH27", True), ("MESM27", True),
        ("ES", False), ("CL", False), ("6E", False), ("GC", False), ("MES", False),
    ])
    def test_telling_a_contract_from_a_product(self, typed, is_contract):
        assert bool(markets.CONTRACT_CODE.match(typed)) is is_contract

    def test_an_unknown_product_is_an_error_not_a_guess(self):
        with pytest.raises(SymbolNotFoundError, match="No futures product NOPE"):
            markets.futures_quote(FuturesFake(), ["NOPE"])

    def test_contract_for_a_product_lists_its_contracts(self, capsys):
        markets.futures_contract(FuturesFake(), "ES")

        out = capsys.readouterr().out
        assert out.startswith("ES (stock index), 50 dollars per point")
        assert "ESZ26     2026-12-18" in out and "ESH27     2027-03-19" in out
        assert "pyhood futures contract ESZ26" in out

    def test_unknown_contract_is_reported(self, capsys):
        assert markets.futures_quote(FuturesFake(), ["ESZ26", "NOPEZ26"]) == 1
        assert "No futures quote for NOPEZ26." in capsys.readouterr().err

    def test_contract_says_what_a_tick_is_worth(self, capsys):
        markets.futures_contract(FuturesFake(), "esz26")

        out = capsys.readouterr().out
        assert "Multiplier:     50 (dollars per point)" in out
        assert "Smallest move:  0.25 ($12.50 a contract)" in out
        assert "Product:        ES (stock index)" in out

    def test_orders_newest_first_with_realized_profit(self, capsys):
        markets.futures_orders(FuturesFake())

        rows = capsys.readouterr().out.splitlines()
        assert rows[1].split()[-2:] == ["closing", "+$125.00"]
        assert rows[2].split()[-2:] == ["opening", "-"]
        assert rows[-1] == "Realized profit and loss, all orders shown: +$125.00"

    def test_no_positions(self, capsys):
        markets.futures_positions(FuturesFake())
        assert capsys.readouterr().out.strip() == "No open futures positions."


class TestCommandLine:
    @pytest.mark.parametrize(("argv", "command", "kwargs"), [
        (["crypto", "quote", "BTC", "ETH"], markets.crypto_quote,
         {"symbols": ["BTC", "ETH"], "as_json_output": False}),
        (["crypto", "holdings", "--json"], markets.crypto_holdings, {"as_json_output": True}),
        (["crypto", "orders", "--open"], markets.crypto_orders,
         {"open_only": True, "as_json_output": False}),
        (["crypto", "buy", "BTC", "0.001", "--limit", "50000"], markets.crypto_order,
         {"side": "buy", "symbol": "BTC", "quantity": 0.001, "limit": 50000.0,
          "confirm": None}),
        (["crypto", "sell", "ETH", "0.5", "--market", "--confirm", "abc123"],
         markets.crypto_order,
         {"side": "sell", "symbol": "ETH", "quantity": 0.5, "limit": None,
          "confirm": "abc123"}),
        (["crypto", "cancel", "c-1"], markets.crypto_cancel, {"order_id": "c-1"}),
    ])
    def test_crypto(self, monkeypatch, argv, command, kwargs):
        seen = []
        monkeypatch.setattr(markets, "run_crypto", lambda fn, **kw: seen.append((fn, kw)) or 0)

        assert onboarding.main(argv) == 0
        assert seen == [(command, kwargs)]

    @pytest.mark.parametrize(("argv", "command", "kwargs"), [
        (["futures", "quote", "ESZ26"], markets.futures_quote,
         {"symbols": ["ESZ26"], "as_json_output": False}),
        (["futures", "contract", "ESZ26"], markets.futures_contract,
         {"symbol": "ESZ26", "as_json_output": False}),
        (["futures", "orders"], markets.futures_orders, {"as_json_output": False}),
        (["futures", "positions"], markets.futures_positions, {"as_json_output": False}),
    ])
    def test_futures(self, monkeypatch, argv, command, kwargs):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        assert onboarding.main(argv) == 0
        assert seen == [(command, kwargs)]

    @pytest.mark.parametrize("argv", [
        ["crypto"],                                   # which crypto command?
        ["crypto", "buy", "BTC", "0.001"],            # no price
        ["crypto", "buy", "BTC", "0", "--market"],
        ["crypto", "buy", "BTC", "0.001", "--limit", "5", "--market"],
        ["futures"],
        ["futures", "buy", "ESZ26", "1"],             # futures are read-only
    ])
    def test_incomplete_or_unsupported_commands_are_refused(self, argv):
        with pytest.raises(SystemExit) as stop:
            onboarding.main(argv)
        assert stop.value.code == 2

    def test_crypto_without_credentials_says_how_to_set_them_up(self, monkeypatch, capsys):
        def missing():
            raise FileNotFoundError("no crypto.env")

        monkeypatch.setattr("pyhood.crypto.CryptoClient", missing)

        assert markets.run_crypto(markets.crypto_holdings) == 1
        err = capsys.readouterr().err
        assert "Crypto is not set up" in err and "pyhood setup crypto" in err
