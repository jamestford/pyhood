"""The read-only account commands: positions, orders, buying-power, quote.

A local model given `pyhood guide` and asked about recent purchases wrote
a script that crashed formatting the price of a cancelled order, which is
None, and then reported UTC order times as local ones. It did both twice
in two runs. The commands exist so those are handled once, here.
"""

import json
import shlex
import time
from datetime import datetime, timedelta, timezone

import pytest

from pyhood import cli, guide, onboarding
from pyhood.exceptions import APIError, AuthError, OrderError
from pyhood.models import (
    OptionContract,
    OptionPosition,
    OptionsChain,
    Order,
    Position,
    Quote,
)

UTC = timezone.utc

# The tables show local time, pinned below with tzset, which Windows lacks.
pytestmark = pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset")


@pytest.fixture(autouse=True)
def eastern_time(monkeypatch):
    """Local time is what the tables show, so pin it."""
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture(autouse=True)
def on_the_path(monkeypatch):
    """Printed commands read `pyhood ...`, as on an install that is on the PATH."""
    monkeypatch.setattr(cli, "program", lambda: "pyhood")


def stock_order(**fields):
    base = dict(
        order_id="order-1", symbol="ANT", side="buy", order_type="limit", quantity=41.0,
        price=95.0, status="filled",
        created_at=datetime(2026, 11, 19, 17, 36, 28, tzinfo=UTC),
        filled_at=datetime(2026, 11, 19, 18, 8, 42, tzinfo=UTC),
        time_in_force="gfd", average_price=95.0, fees=0.0, filled_quantity=41.0,
    )
    return Order(**{**base, **fields})


CANCELLED = stock_order(
    order_id="order-2", quantity=40.0, price=90.0, status="cancelled",
    created_at=datetime(2026, 11, 19, 16, 31, 52, tzinfo=UTC),
    filled_at=None, average_price=None, filled_quantity=0.0,
)


class FakeClient:
    """Stands in for PyhoodClient, recording how it was called."""

    def __init__(self, stocks=(), options=(), stock_orders=(), option_orders=(),
                 quotes=None, buying_power=168.85):
        self.stocks, self.options = list(stocks), list(options)
        self.stock_orders, self.option_orders = list(stock_orders), list(option_orders)
        self.quotes = quotes or {}
        self.buying_power = buying_power
        self.calls = []

    def get_positions(self):
        return self.stocks

    def get_option_positions(self):
        return self.options

    def get_stock_orders(self, start_date=None):
        self.calls.append(("get_stock_orders", start_date))
        return list(self.stock_orders)

    def get_option_orders(self, start_date=None):
        self.calls.append(("get_option_orders", start_date))
        return list(self.option_orders)

    def get_buying_power(self):
        return self.buying_power

    def get_quotes(self, symbols, include_fundamentals=False):
        self.calls.append(("get_quotes", symbols, include_fundamentals))
        return {s: q for s, q in self.quotes.items() if s in symbols}


# ── Formatting ───────────────────────────────────────────────────────


class TestFormatting:
    def test_none_is_a_dash_never_a_crash(self):
        assert cli.money(None) == "-"
        assert cli.signed_money(None) == "-"
        assert cli.number(None) == "-"
        assert cli.percent(None) == "-"
        assert cli.large_money(None) == "-"
        assert cli.local_time(None) == "-"

    def test_money(self):
        assert cli.money(1234.5) == "$1,234.50"
        assert cli.money(-1593.27) == "-$1,593.27"
        assert cli.money(0) == "$0.00"
        assert cli.signed_money(12.5) == "+$12.50"
        assert cli.signed_money(-12.5) == "-$12.50"

    def test_number_drops_trailing_zeros_but_keeps_fractions(self):
        assert cli.number(95.0) == "95"
        assert cli.number(0.011629) == "0.011629"
        assert cli.number(23626606) == "23,626,606"
        assert cli.number(0.0) == "0"

    def test_large_money(self):
        assert cli.large_money(5_115_479_722_000) == "$5.12T"
        assert cli.large_money(830_400_000_000) == "$830.40B"
        assert cli.large_money(12_500_000) == "$12.50M"
        assert cli.large_money(950_000) == "$950,000.00"

    def test_times_are_converted_from_utc_to_local(self):
        """17:36 UTC is 12:36 in New York, not 5:36 PM."""
        placed = datetime(2026, 11, 19, 17, 36, tzinfo=UTC)
        assert cli.local_time(placed) == "2026-11-19 12:36 EST"


# ── positions ────────────────────────────────────────────────────────


class TestPositions:
    STOCKS = [
        Position("TSLA", 0.011629, 472.10, 381.95, 4.44, -1.05, -19.09),
        Position("ANT", 95.0, 97.13, 80.16, 7615.20, -1611.80, -17.47),
    ]

    def test_table_has_every_position_and_a_total(self, capsys):
        assert cli.positions(FakeClient(stocks=self.STOCKS)) == 0

        out = capsys.readouterr().out
        assert "STOCKS" in out
        assert "ANT" in out and "$97.13" in out and "-$1,611.80" in out and "-17.47%" in out
        assert "0.011629" in out
        total = next(line for line in out.splitlines() if line.startswith("TOTAL"))
        assert "$7,619.64" in total and "-$1,612.85" in total
        assert "OPTIONS" not in out

    def test_options_are_listed_with_their_contract(self, capsys):
        option = OptionPosition(
            symbol="NKE", option_type="call", strike=65.0, expiration="2026-12-18",
            quantity=2, average_open_price=1.22, cost_basis=244.0, current_mark=1.5,
            current_value=300.0, unrealized_pl=56.0, unrealized_pl_pct=22.95,
            strategy="long_call",
        )

        cli.positions(FakeClient(options=[option]))

        out = capsys.readouterr().out
        assert "NKE 2026-12-18 $65 call" in out
        assert "+$56.00" in out
        assert "per share" in out
        assert "STOCKS" not in out

    def test_nothing_held(self, capsys):
        assert cli.positions(FakeClient()) == 0
        assert capsys.readouterr().out.strip() == "No open positions."

    def test_json(self, capsys):
        cli.positions(FakeClient(stocks=self.STOCKS), as_json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data["options"] == []
        assert data["stocks"][1]["symbol"] == "ANT"
        assert data["stocks"][1]["average_cost"] == 97.13


# ── orders ───────────────────────────────────────────────────────────


class TestOrders:
    def test_an_unfilled_order_prints_instead_of_crashing(self, capsys):
        """Its average_price is None, which is what broke the model's script."""
        assert cli.orders(FakeClient(stock_orders=[stock_order(), CANCELLED])) == 0

        lines = capsys.readouterr().out.splitlines()
        cancelled = next(line for line in lines if "cancelled" in line)
        assert cancelled.split()[-4:] == ["0", "-", "cancelled", "order-2"]
        filled = next(line for line in lines if line.split()[-2:] == ["filled", "order-1"])
        assert "$95.00" in filled

    def test_times_are_local_and_the_header_says_so(self, capsys):
        cli.orders(FakeClient(stock_orders=[stock_order()]))

        out = capsys.readouterr().out
        assert "2026-11-19 12:36 EST" in out  # 17:36 UTC
        assert "17:36" not in out
        header = out.splitlines()[0]
        assert "times are" in header
        assert f"today is {datetime.now():%Y-%m-%d}" in header

    def test_covers_the_last_30_days_unless_told_otherwise(self):
        client = FakeClient()
        cli.orders(client)
        expected = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        assert client.calls == [("get_stock_orders", expected), ("get_option_orders", expected)]

        client = FakeClient()
        cli.orders(client, since="2026-01-01")
        assert client.calls[0] == ("get_stock_orders", "2026-01-01")

        client = FakeClient()
        cli.orders(client, since="2026-01-01", everything=True)
        assert client.calls[0] == ("get_stock_orders", None)

    def test_stock_and_option_orders_are_merged_newest_first(self, capsys):
        option = stock_order(
            order_id="order-3", symbol="NKE", side="debit", instrument_type="option",
            quantity=1.0, price=1.2, average_price=1.22, filled_quantity=1.0,
            created_at=datetime(2026, 11, 19, 17, 0, tzinfo=UTC),
        )

        cli.orders(FakeClient(stock_orders=[CANCELLED, stock_order()], option_orders=[option]))

        rows = capsys.readouterr().out.splitlines()[2:5]
        assert [row.split()[4] for row in rows] == ["ANT", "NKE", "ANT"]
        assert [row.split()[5] for row in rows] == ["stock", "option", "stock"]

    def test_symbol_filter(self, capsys):
        other = stock_order(order_id="order-4", symbol="AAPL")

        cli.orders(FakeClient(stock_orders=[stock_order(), other]), symbol="aapl")

        out = capsys.readouterr().out
        assert "for AAPL" in out.splitlines()[0]
        assert "ANT" not in out

    def test_none_found_says_how_to_look_further_back(self, capsys):
        cli.orders(FakeClient(), since="2026-11-01")
        out = capsys.readouterr().out
        assert "Orders since 2026-11-01: none." in out
        assert "--all" in out

        cli.orders(FakeClient(), everything=True)
        assert capsys.readouterr().out.strip() == "All orders: none."

    def test_json_keeps_exact_values_utc_times_and_nulls(self, capsys):
        cli.orders(FakeClient(stock_orders=[stock_order(), CANCELLED]), as_json_output=True)

        newest, older = json.loads(capsys.readouterr().out)
        assert newest["created_at"] == "2026-11-19T17:36:28+00:00"
        assert newest["average_price"] == 95.0
        assert older["average_price"] is None
        assert older["filled_at"] is None
        assert older["filled_quantity"] == 0.0


# ── buying-power and quote ───────────────────────────────────────────


class TestBuyingPowerAndQuote:
    QUOTES = {
        "AAPL": Quote(
            symbol="AAPL", price=352.01, prev_close=349.08, change_pct=0.84, bid=351.99,
            ask=352.01, volume=23626606, pe_ratio=38.88, market_cap=5_115_479_722_000,
            high_52w=360.83, low_52w=243.42,
            timestamp=datetime(2026, 11, 24, 20, 25, tzinfo=UTC),
        ),
    }

    def test_buying_power(self, capsys):
        assert cli.buying_power(FakeClient()) == 0
        assert capsys.readouterr().out.strip() == "Buying power: $168.85"

        cli.buying_power(FakeClient(), as_json_output=True)
        assert json.loads(capsys.readouterr().out) == {"buying_power": 168.85}

    def test_quote(self, capsys):
        client = FakeClient(quotes=self.QUOTES)

        assert cli.quote(client, ["aapl"]) == 0

        out = capsys.readouterr().out
        assert client.calls == [("get_quotes", ["AAPL"], False)]
        assert "$352.01" in out and "+0.84%" in out
        assert "VOLUME" not in out
        assert "As of 2026-11-24 15:25 EST." in out

    def test_quote_with_fundamentals(self, capsys):
        client = FakeClient(quotes=self.QUOTES)

        cli.quote(client, ["AAPL"], fundamentals=True)

        out = capsys.readouterr().out
        assert client.calls == [("get_quotes", ["AAPL"], True)]
        assert "23,626,606" in out and "38.88" in out and "$5.12T" in out

    def test_unknown_symbol_is_reported_and_fails(self, capsys):
        assert cli.quote(FakeClient(quotes=self.QUOTES), ["AAPL", "NOPE"]) == 1

        captured = capsys.readouterr()
        assert "AAPL" in captured.out
        assert "No quote for NOPE." in captured.err


# ── Running a command ────────────────────────────────────────────────


class TestRun:
    def test_not_logged_in_says_how_to_log_in(self, monkeypatch, capsys):
        import pyhood

        def no_session():
            raise AuthError("no saved session")

        monkeypatch.setattr(pyhood, "login", no_session)

        assert cli.run(cli.positions) == 1
        err = capsys.readouterr().err
        assert "Not logged in" in err and "pyhood setup login" in err

    def test_api_failure_is_one_line_not_a_traceback(self, monkeypatch, capsys):
        import pyhood

        def failing(client, **kwargs):
            raise APIError("503 Service Unavailable")

        monkeypatch.setattr(pyhood, "login", lambda: object())
        monkeypatch.setattr("pyhood.client.PyhoodClient", lambda session: object())

        assert cli.run(failing) == 1
        assert "Robinhood request failed: 503 Service Unavailable" in capsys.readouterr().err

    @pytest.mark.parametrize(("argv", "command", "kwargs"), [
        (["positions"], cli.positions, {"as_json_output": False}),
        (["positions", "--json"], cli.positions, {"as_json_output": True}),
        (["orders"], cli.orders,
         {"since": None, "symbol": None, "everything": False, "open_only": False,
          "as_json_output": False}),
        (["orders", "--since", "2026-11-01", "--symbol", "ant", "--json"], cli.orders,
         {"since": "2026-11-01", "symbol": "ant", "everything": False, "open_only": False,
          "as_json_output": True}),
        (["orders", "--all", "--open"], cli.orders,
         {"since": None, "symbol": None, "everything": True, "open_only": True,
          "as_json_output": False}),
        (["buying-power"], cli.buying_power, {"as_json_output": False}),
        (["quote", "AAPL", "MSFT", "--fundamentals"], cli.quote,
         {"symbols": ["AAPL", "MSFT"], "fundamentals": True, "as_json_output": False}),
    ])
    def test_command_line_reaches_the_right_command(self, monkeypatch, argv, command, kwargs):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        assert onboarding.main(argv) == 0
        assert seen == [(command, kwargs)]

    def test_a_bad_date_is_refused_with_the_format(self, capsys):
        with pytest.raises(SystemExit) as stop:
            onboarding.main(["orders", "--since", "yesterday"])

        assert stop.value.code == 2
        assert "YYYY-MM-DD" in capsys.readouterr().err


# ── buy, sell and cancel: preview, then confirm ──────────────────────


class OrderClient(FakeClient):
    """A client that records every call that would change the account."""

    def __init__(self, *, price=350.0, bid=349.9, ask=350.1, market_open=True,
                 reject=None, existing=None, after_cancel="cancelled", **kwargs):
        super().__init__(**kwargs)
        self.price, self.bid, self.ask = price, bid, ask
        self.market_open = market_open
        self.reject = reject
        self.existing = existing
        self.after_cancel = after_cancel
        self.writes = []
        self.reads = []

    def get_quote(self, symbol):
        self.reads.append("get_quote")
        return Quote(symbol=symbol, price=self.price, prev_close=345.0, change_pct=1.45,
                     bid=self.bid, ask=self.ask)

    def get_buying_power(self):
        self.reads.append("get_buying_power")
        return self.buying_power

    def is_market_open(self):
        return self.market_open

    def _place(self, side, symbol, quantity, **kwargs):
        self.writes.append((side, symbol, quantity, kwargs))
        if self.reject:
            raise OrderError(self.reject)
        self.existing = stock_order(
            order_id="new-order", symbol=symbol, side=side, quantity=quantity,
            price=kwargs.get("price"), status="confirmed", average_price=None,
            filled_at=None, filled_quantity=0.0,
        )
        return self.existing

    def buy_stock(self, symbol, quantity, **kwargs):
        return self._place("buy", symbol, quantity, **kwargs)

    def sell_stock(self, symbol, quantity, **kwargs):
        return self._place("sell", symbol, quantity, **kwargs)

    def get_order(self, order_id):
        self.reads.append("get_order")
        if self.existing is None:
            raise OrderError(f"Order {order_id} not found")
        return self.existing

    def cancel_order(self, order_id):
        self.writes.append(("cancel", order_id))
        self.existing = stock_order(
            order_id=order_id, status=self.after_cancel, quantity=40.0, price=90.0,
            average_price=None, filled_at=None, filled_quantity=0.0,
        )
        return {}


def code_from(output):
    """The confirmation code a preview printed."""
    return output.split("--confirm ")[-1].split()[0]


class TestConfirmationCode:
    def test_same_action_same_code(self):
        assert cli.confirmation_code("buy", "AAPL", "10") == cli.confirmation_code(
            "buy", "AAPL", "10",
        )
        assert len(cli.confirmation_code("buy", "AAPL", "10")) == 6

    def test_any_difference_changes_it(self):
        base = cli.confirmation_code("buy", "AAPL", "10", "350.0000", "gfd", False)
        different = [
            ("sell", "AAPL", "10", "350.0000", "gfd", False),
            ("buy", "MSFT", "10", "350.0000", "gfd", False),
            ("buy", "AAPL", "100", "350.0000", "gfd", False),
            ("buy", "AAPL", "10", "35.0000", "gfd", False),
            ("buy", "AAPL", "10", "market", "gfd", False),
            ("buy", "AAPL", "10", "350.0000", "gtc", False),
            ("buy", "AAPL", "10", "350.0000", "gfd", True),
        ]
        codes = {cli.confirmation_code(*parts) for parts in different}
        assert base not in codes
        assert len(codes) == len(different)

    def test_a_code_does_not_work_the_next_day(self, monkeypatch):
        today = cli.confirmation_code("buy", "AAPL", "10")

        class Tomorrow(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(days=1)

        monkeypatch.setattr(cli, "datetime", Tomorrow)
        assert cli.confirmation_code("buy", "AAPL", "10") != today


class TestStockOrder:
    def test_without_a_code_it_previews_and_sends_nothing(self, capsys):
        client = OrderClient(buying_power=5000.0)

        assert cli.stock_order(client, "buy", "aapl", 10, limit=350.0) == 0

        out = capsys.readouterr().out
        assert client.writes == []
        assert out.startswith("PREVIEW. Nothing has been sent.")
        assert "Buy 10 AAPL, limit $350.00, good for day" in out
        assert "Estimated cost:     $3,500.00" in out
        assert "Buying power:       $5,000.00" in out
        assert "show this preview to the user" in out
        assert f"pyhood buy AAPL 10 --limit 350 --confirm {code_from(out)}" in out

    def test_the_printed_command_places_exactly_the_previewed_order(self, capsys):
        client = OrderClient(buying_power=5000.0)
        cli.stock_order(client, "buy", "AAPL", 10, limit=350.0, time_in_force="gtc")
        code = code_from(capsys.readouterr().out)

        result = cli.stock_order(
            client, "buy", "AAPL", 10, limit=350.0, time_in_force="gtc",
            confirm=code, settle_seconds=0,
        )

        assert result == 0
        assert client.writes == [
            ("buy", "AAPL", 10, {"price": 350.0, "time_in_force": "gtc",
                                 "extended_hours": False}),
        ]
        out = capsys.readouterr().out
        assert out.startswith("PLACED: Buy 10 AAPL, limit $350.00, good till cancelled")
        assert "Order ID:  new-order" in out
        assert "pyhood cancel new-order" in out

    @pytest.mark.parametrize("changed", [
        {"quantity": 100},
        {"symbol": "MSFT"},
        {"limit": 35.0},
        {"limit": None},
        {"side": "sell"},
        {"time_in_force": "gtc"},
        {"extended_hours": True},
    ])
    def test_a_code_for_one_order_will_not_place_another(self, capsys, changed):
        """Ten shares previewed must not become a hundred placed."""
        client = OrderClient(buying_power=5000.0)
        order = {"side": "buy", "symbol": "AAPL", "quantity": 10, "limit": 350.0}
        cli.stock_order(client, **order)
        code = code_from(capsys.readouterr().out)
        client.reads.clear()

        result = cli.stock_order(client, **{**order, **changed}, confirm=code, settle_seconds=0)

        assert result == 2
        assert client.writes == []
        assert client.reads == []  # refused before any request
        assert "nothing was sent" in capsys.readouterr().err

    def test_a_made_up_code_is_refused(self, capsys):
        client = OrderClient()

        assert cli.stock_order(client, "buy", "AAPL", 10, limit=350.0, confirm="yes") == 2
        assert client.writes == []

    def test_market_order(self, capsys):
        client = OrderClient(buying_power=5000.0)

        cli.stock_order(client, "buy", "AAPL", 2, limit=None)

        out = capsys.readouterr().out
        assert "Buy 2 AAPL, at market, good for day" in out
        assert "Estimated cost:     $700.20" in out  # the ask, not the last price
        assert "can differ from the quote" in out
        assert "pyhood buy AAPL 2 --market --confirm" in out

        cli.stock_order(client, "buy", "AAPL", 2, limit=None, confirm=code_from(out),
                        settle_seconds=0)
        assert client.writes[0][3]["price"] is None

    def test_buying_more_than_buying_power_is_flagged(self, capsys):
        cli.stock_order(OrderClient(buying_power=168.85), "buy", "AAPL", 10, limit=350.0)
        assert "more than your buying power" in capsys.readouterr().out

    def test_selling_more_than_held_is_flagged(self, capsys):
        client = OrderClient(stocks=[Position("ANT", 95.0, 97.13, 83.0, 7885.0, -1342.0, -14.5)],
                             price=83.0, bid=83.0, ask=83.1)

        cli.stock_order(client, "sell", "ANT", 100, limit=85.0)

        out = capsys.readouterr().out
        assert "Sell 100 ANT, limit $85.00" in out
        assert "Estimated proceeds: $8,500.00" in out
        assert "You hold:           95 ANT" in out
        assert "fewer than this order sells" in out
        assert "Buying power" not in out

    def test_a_limit_far_from_the_price_is_pointed_out(self, capsys):
        cli.stock_order(OrderClient(buying_power=99999.0), "buy", "AAPL", 1, limit=35.0)
        assert "90.0% below the last price of $350.00" in capsys.readouterr().out

        cli.stock_order(OrderClient(buying_power=99999.0), "buy", "AAPL", 1, limit=351.0)
        assert "the last price of" not in capsys.readouterr().out

    def test_a_rejected_order_reports_robinhoods_reason(self, capsys):
        client = OrderClient(reject="Order rejected: You can only purchase 41 shares")
        cli.stock_order(client, "buy", "AAPL", 10, limit=350.0)
        code = code_from(capsys.readouterr().out)

        result = cli.stock_order(client, "buy", "AAPL", 10, limit=350.0, confirm=code,
                                 settle_seconds=0)

        captured = capsys.readouterr()
        assert result == 1
        assert "You can only purchase 41 shares" in captured.err
        assert "PLACED" not in captured.out


class TestCancel:
    OPEN = stock_order(
        order_id="order-9", status="confirmed", quantity=40.0, price=90.0,
        average_price=None, filled_at=None, filled_quantity=0.0,
    )

    def test_without_a_code_it_previews_and_sends_nothing(self, capsys):
        client = OrderClient(existing=self.OPEN)

        assert cli.cancel(client, "order-9") == 0

        out = capsys.readouterr().out
        assert client.writes == []
        assert out.startswith("PREVIEW. Nothing has been sent.")
        assert "Cancel: buy 40 ANT, limit $90.00" in out
        assert f"pyhood cancel order-9 --confirm {code_from(out)}" in out

    def test_with_its_code_it_cancels_and_reports_the_outcome(self, capsys):
        client = OrderClient(existing=self.OPEN)
        cli.cancel(client, "order-9")
        code = code_from(capsys.readouterr().out)

        assert cli.cancel(client, "order-9", confirm=code, settle_seconds=0) == 0

        assert client.writes == [("cancel", "order-9")]
        assert capsys.readouterr().out.startswith("CANCELLED: buy 40 ANT")

    def test_a_code_for_one_order_will_not_cancel_another(self, capsys):
        client = OrderClient(existing=self.OPEN)
        cli.cancel(client, "order-9")
        code = code_from(capsys.readouterr().out)
        client.reads.clear()

        assert cli.cancel(client, "order-8", confirm=code, settle_seconds=0) == 2
        assert client.writes == []
        assert client.reads == []

    def test_an_order_that_filled_before_the_cancel_landed_says_so(self, capsys):
        client = OrderClient(existing=self.OPEN, after_cancel="filled")
        cli.cancel(client, "order-9")
        code = code_from(capsys.readouterr().out)

        cli.cancel(client, "order-9", confirm=code, settle_seconds=0)

        out = capsys.readouterr().out
        assert "CANCELLED" not in out
        assert "the order is now filled" in out

    def test_a_finished_order_has_nothing_to_cancel(self, capsys):
        client = OrderClient(existing=stock_order(order_id="order-1"))  # filled

        assert cli.cancel(client, "order-1") == 1

        out = capsys.readouterr().out
        assert "already filled" in out
        assert "--confirm" not in out
        assert client.writes == []


class TestOpenOrders:
    def test_open_shows_only_orders_that_can_still_fill_with_their_ids(self, capsys):
        waiting = stock_order(order_id="order-9", status="confirmed", average_price=None,
                              filled_at=None, filled_quantity=0.0)

        cli.orders(FakeClient(stock_orders=[stock_order(), CANCELLED, waiting]), open_only=True)

        out = capsys.readouterr().out
        assert out.startswith("Open orders since")
        rows = out.splitlines()[2:3]
        assert rows[0].split()[-2:] == ["confirmed", "order-9"]
        assert "order-1" not in out and "order-2" not in out

    def test_every_order_row_ends_with_its_id(self, capsys):
        cli.orders(FakeClient(stock_orders=[stock_order()]))
        assert capsys.readouterr().out.splitlines()[1].endswith("ORDER ID")


class TestOrderCommandLine:
    @pytest.mark.parametrize(("argv", "kwargs"), [
        (["buy", "AAPL", "10", "--limit", "350"],
         {"side": "buy", "symbol": "AAPL", "quantity": 10.0, "limit": 350.0,
          "time_in_force": "gfd", "extended_hours": False, "confirm": None}),
        (["sell", "ant", "0.5", "--market", "--tif", "gtc", "--extended-hours",
          "--confirm", "abc123"],
         {"side": "sell", "symbol": "ant", "quantity": 0.5, "limit": None,
          "time_in_force": "gtc", "extended_hours": True, "confirm": "abc123"}),
    ])
    def test_buy_and_sell(self, monkeypatch, argv, kwargs):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        assert onboarding.main(argv) == 0
        assert seen == [(cli.stock_order, kwargs)]

    def test_cancel(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main(["cancel", "order-9", "--confirm", "abc123"])
        assert seen == [(cli.cancel, {"order_id": "order-9", "confirm": "abc123"})]

    @pytest.mark.parametrize("argv", [
        ["buy", "AAPL", "10"],                              # neither --limit nor --market
        ["buy", "AAPL", "10", "--limit", "350", "--market"],  # both
        ["buy", "AAPL", "0", "--limit", "350"],
        ["buy", "AAPL", "-5", "--limit", "350"],
        ["buy", "AAPL", "ten", "--limit", "350"],
        ["buy", "AAPL", "nan", "--limit", "350"],
        ["buy", "AAPL", "10", "--limit", "0"],
        ["sell", "AAPL", "10", "--limit", "350", "--tif", "ioc"],
        ["cancel"],
    ])
    def test_an_order_that_is_not_fully_specified_is_refused(self, argv, capsys):
        """No price means no order, not a market order by default."""
        with pytest.raises(SystemExit) as stop:
            onboarding.main(argv)
        assert stop.value.code == 2


# ── options: the chain, and option orders ────────────────────────────


def contract(strike, kind="call", bid=0.28, ask=0.33, mark=0.31, delta=0.5, iv=0.314):
    return OptionContract(
        symbol="F", option_type=kind, strike=strike, expiration="2026-12-11", mark=mark,
        bid=bid, ask=ask, iv=iv, delta=delta, volume=560, open_interest=3547,
    )


class OptionClient(OrderClient):
    EXPIRATIONS = ["2026-11-27", "2026-12-04", "2026-12-11", "2026-12-18", "2027-01-15"]
    STRIKES = [10.0, 11.0, 11.5, 12.0, 12.5, 13.0, 14.0]

    def __init__(self, **kwargs):
        kwargs.setdefault("price", 11.95)
        super().__init__(**kwargs)

    def get_options_expirations(self, symbol):
        self.reads.append("get_options_expirations")
        return list(self.EXPIRATIONS)

    def get_options_chain(self, symbol, expiration, option_type=None):
        self.reads.append("get_options_chain")
        calls = [contract(k) for k in self.STRIKES]
        puts = [contract(k, "put", delta=-0.5) for k in self.STRIKES]
        return OptionsChain(
            symbol=symbol, expiration=expiration,
            calls=calls if option_type in (None, "call") else [],
            puts=puts if option_type in (None, "put") else [],
        )

    def _place_option(self, side, *args, **kwargs):
        self.writes.append((side, args, kwargs))
        if self.reject:
            raise OrderError(self.reject)
        self.existing = stock_order(
            order_id="option-order", symbol=args[0], side=side, quantity=float(args[4]),
            price=args[5], status="queued", average_price=None, filled_at=None,
            filled_quantity=0.0, instrument_type="option",
        )
        return self.existing

    def buy_option(self, *args, **kwargs):
        return self._place_option("buy", *args, **kwargs)

    def sell_option(self, *args, **kwargs):
        return self._place_option("sell", *args, **kwargs)


class TestOptionsChain:
    def test_a_symbol_alone_lists_expirations(self, capsys):
        assert cli.options(OptionClient(), "f") == 0

        out = capsys.readouterr().out
        assert out.startswith("F option expirations (today is ")
        assert "2026-12-11" in out and "2027-01-15" in out
        assert "pyhood options F --expires YYYY-MM-DD" in out

    def test_an_expiration_shows_the_strikes_nearest_the_price(self, capsys):
        assert cli.options(OptionClient(), "F", expires="2026-12-11", strikes=3) == 0

        out = capsys.readouterr().out
        assert "F is at $11.95. Options expiring 2026-12-11" in out
        assert "One contract is 100 shares" in out
        calls = out[out.index("CALLS"):out.index("PUTS")]
        assert [line.split()[0] for line in calls.splitlines()[2:5]] == [
            "$11.50", "$12.00", "$12.50",
        ]
        assert "$10.00" not in out and "$14.00" not in out
        assert "+0.500" in calls and "31.4%" in calls
        assert "-0.500" in out[out.index("PUTS"):]

    def test_calls_only(self, capsys):
        cli.options(OptionClient(), "F", expires="2026-12-11", option_type="call")
        out = capsys.readouterr().out
        assert "CALLS" in out and "PUTS" not in out

    def test_unpublished_greeks_print_as_a_dash(self, capsys):
        client = OptionClient()
        client.get_options_chain = lambda *a, **k: OptionsChain(
            symbol="F", expiration="2026-12-11",
            calls=[contract(12.0, delta=None, iv=None)], puts=[],
        )

        cli.options(client, "F", expires="2026-12-11", option_type="call")

        row = capsys.readouterr().out.splitlines()[-1].split()
        assert row[:6] == ["$12.00", "$0.28", "$0.33", "$0.31", "-", "-"]

    def test_an_expiration_that_does_not_exist_names_the_nearest(self, capsys):
        assert cli.options(OptionClient(), "F", expires="2026-12-25") == 1

        err = capsys.readouterr().err
        assert "F has no options expiring 2026-12-25." in err
        assert "2026-12-18" in err and "2027-01-15" in err

    def test_json(self, capsys):
        cli.options(OptionClient(), "F", expires="2026-12-11", strikes=2, as_json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data["symbol"] == "F" and data["price"] == 11.95
        assert [c["strike"] for c in data["calls"]] == [11.5, 12.0]
        assert len(data["puts"]) == 2


class TestOptionOrder:
    ORDER = dict(side="buy", symbol="F", expiration="2026-12-11", strike=12.0,
                 option_type="call", contracts=2, limit=0.30)

    def test_without_a_code_it_previews_and_sends_nothing(self, capsys):
        client = OptionClient(buying_power=500.0)

        assert cli.option_order(client, **self.ORDER) == 0

        out = capsys.readouterr().out
        assert client.writes == []
        assert out.startswith("PREVIEW. Nothing has been sent.")
        assert (
            "Buy to open 2 contracts of F $12.00 call expiring 2026-12-11, "
            "limit $0.30 per share, good for day"
        ) in out
        # Two contracts of 100 shares at 30 cents: sixty dollars, not sixty cents.
        assert "Estimated cost:     $60.00 (2 contracts x 100 shares x $0.30)" in out
        assert "Contract now:       mark $0.31 (bid $0.28, ask $0.33)" in out
        assert "Delta, IV:          +0.500, 31.4%" in out
        assert "Buying power:       $500.00" in out
        assert (
            "pyhood buy-option F --expires 2026-12-11 --strike 12 --call --contracts 2 "
            f"--limit 0.3 --confirm {code_from(out)}"
        ) in out

    def test_the_printed_command_places_exactly_the_previewed_order(self, capsys):
        client = OptionClient(buying_power=500.0)
        cli.option_order(client, **self.ORDER)
        code = code_from(capsys.readouterr().out)

        assert cli.option_order(client, **self.ORDER, confirm=code, settle_seconds=0) == 0

        assert client.writes == [
            ("buy", ("F", 12.0, "2026-12-11", "call", 2, 0.30),
             {"position_effect": "open", "time_in_force": "gfd"}),
        ]
        out = capsys.readouterr().out
        assert out.startswith("PLACED: Buy to open 2 contracts of F $12.00 call")
        assert "pyhood cancel option-order" in out

    @pytest.mark.parametrize("changed", [
        {"contracts": 20},
        {"strike": 12.5},
        {"option_type": "put"},
        {"expiration": "2026-12-18"},
        {"limit": 3.0},
        {"side": "sell"},
        {"effect": "close"},
        {"symbol": "GM"},
        {"time_in_force": "gtc"},
    ])
    def test_a_code_for_one_order_will_not_place_another(self, capsys, changed):
        client = OptionClient(buying_power=500.0)
        cli.option_order(client, **self.ORDER)
        code = code_from(capsys.readouterr().out)
        client.reads.clear()

        result = cli.option_order(client, **{**self.ORDER, **changed}, confirm=code,
                                  settle_seconds=0)

        assert result == 2
        assert client.writes == []
        assert client.reads == []

    def test_a_buy_opens_and_a_sell_closes_unless_told_otherwise(self, capsys):
        held = OptionPosition(
            symbol="F", option_type="call", strike=12.0, expiration="2026-12-11",
            quantity=2, average_open_price=0.25, cost_basis=50.0, current_mark=0.31,
            current_value=62.0, unrealized_pl=12.0, unrealized_pl_pct=24.0,
            strategy="long_call",
        )
        client = OptionClient(options=[held])

        cli.option_order(client, **{**self.ORDER, "side": "sell"})

        out = capsys.readouterr().out
        assert "Sell to close 2 contracts" in out
        assert "Estimated proceeds: $60.00" in out
        assert "You hold:           2 of this contract" in out
        assert "fewer than this order sells" not in out
        assert "--to" not in out.splitlines()[-1]

    def test_selling_to_close_more_than_held_is_flagged(self, capsys):
        cli.option_order(OptionClient(), **{**self.ORDER, "side": "sell"})

        out = capsys.readouterr().out
        assert "You hold 0 of this contract, fewer than this order sells" in out
        assert "needs --to open" in out

    def test_selling_to_open_is_explicit_and_explained(self, capsys):
        client = OptionClient()

        cli.option_order(client, **{**self.ORDER, "side": "sell", "effect": "open"})

        out = capsys.readouterr().out
        assert "Sell to open 2 contracts" in out
        assert "Selling to open writes a contract" in out
        assert "fewer than this order sells" not in out
        assert out.splitlines()[-1].split(" --confirm ")[0].endswith("--limit 0.3 --to open")

        cli.option_order(client, **{**self.ORDER, "side": "sell", "effect": "open"},
                         confirm=code_from(out), settle_seconds=0)
        assert client.writes[0][0] == "sell"
        assert client.writes[0][2]["position_effect"] == "open"

    def test_a_limit_far_from_the_mark_is_pointed_out(self, capsys):
        cli.option_order(OptionClient(buying_power=99999.0), **{**self.ORDER, "limit": 31.0})

        out = capsys.readouterr().out
        # 31.00 where 0.31 was meant: a hundred times the price.
        assert "Estimated cost:     $6,200.00" in out
        assert "9900% above the contract's mark of $0.31" in out

    def test_more_than_buying_power_is_flagged(self, capsys):
        cli.option_order(OptionClient(buying_power=10.0), **self.ORDER)
        assert "more than your buying power" in capsys.readouterr().out

    def test_a_strike_that_does_not_exist_names_the_nearest(self, capsys):
        client = OptionClient()

        assert cli.option_order(client, **{**self.ORDER, "strike": 12.34}) == 1

        captured = capsys.readouterr()
        assert "F has no $12.34 call expiring 2026-12-11." in captured.err
        assert "$12.00" in captured.err and "$12.50" in captured.err
        assert "--confirm" not in captured.out
        assert client.writes == []

    def test_an_expiration_that_does_not_exist_names_the_nearest(self, capsys):
        assert cli.option_order(OptionClient(), **{**self.ORDER, "expiration": "2026-12-25"}) == 1
        assert "The nearest expirations are:" in capsys.readouterr().err

    def test_a_rejected_order_reports_robinhoods_reason(self, capsys):
        client = OptionClient(buying_power=500.0, reject="Option order rejected: not approved")
        cli.option_order(client, **self.ORDER)
        code = code_from(capsys.readouterr().out)

        assert cli.option_order(client, **self.ORDER, confirm=code, settle_seconds=0) == 1
        assert "not approved" in capsys.readouterr().err

    def test_cancelling_an_option_order_says_it_is_one(self, capsys):
        waiting = stock_order(
            order_id="option-order", symbol="F", side="debit", quantity=2.0, price=0.30,
            status="queued", average_price=None, filled_at=None, filled_quantity=0.0,
            instrument_type="option",
        )

        cli.cancel(OptionClient(existing=waiting), "option-order")

        assert "Cancel: debit 2 F option contracts, limit $0.30" in capsys.readouterr().out


class TestOptionCommandLine:
    def test_options(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main(["options", "F", "--expires", "2026-12-11", "--put", "--strikes", "4"])
        assert seen == [(cli.options, {
            "symbol": "F", "expires": "2026-12-11", "option_type": "put", "strikes": 4,
            "as_json_output": False,
        })]

    def test_buy_option(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main([
            "buy-option", "F", "--expires", "2026-12-11", "--strike", "12", "--call",
            "--contracts", "2", "--limit", "0.30",
        ])
        assert seen == [(cli.option_order, {
            "side": "buy", "symbol": "F", "expiration": "2026-12-11", "strike": 12.0,
            "option_type": "call", "contracts": 2, "limit": 0.30, "effect": None,
            "time_in_force": "gfd", "confirm": None,
        })]

    def test_sell_option_to_open(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main([
            "sell-option", "F", "--strike", "12", "--put", "--expires", "2026-12-11",
            "--limit", "0.36", "--contracts", "1", "--to", "open", "--tif", "gtc",
            "--confirm", "abc123",
        ])
        kwargs = seen[0][1]
        assert kwargs["side"] == "sell" and kwargs["effect"] == "open"
        assert kwargs["option_type"] == "put" and kwargs["confirm"] == "abc123"

    BASE = ["buy-option", "F", "--expires", "2026-12-11", "--strike", "12", "--call",
            "--contracts", "1", "--limit", "0.30"]

    @pytest.mark.parametrize("drop", ["--expires", "--strike", "--call", "--contracts", "--limit"])
    def test_every_term_of_the_contract_is_required(self, drop):
        """Nothing about an option order is filled in by default."""
        argv = list(self.BASE)
        index = argv.index(drop)
        del argv[index:index + (1 if drop == "--call" else 2)]

        with pytest.raises(SystemExit) as stop:
            onboarding.main(argv)
        assert stop.value.code == 2

    @pytest.mark.parametrize("argv", [
        BASE + ["--put"],                                   # a call and a put
        [*BASE[:-1], "0"],                                  # no price
        [*BASE[:-3], "1.5", "--limit", "0.30"],             # half a contract
        [*BASE[:-3], "0", "--limit", "0.30"],
        [*BASE[:3], "12/11/2026", *BASE[4:]],               # not a date
        BASE + ["--to", "roll"],
    ])
    def test_malformed_option_orders_are_refused(self, argv):
        with pytest.raises(SystemExit) as stop:
            onboarding.main(argv)
        assert stop.value.code == 2


# ── Printed commands work where they are printed ─────────────────────


class TestProgram:
    """An install in its own folder is often not on the PATH. A command
    pyhood prints for someone to run next must still work as printed."""

    @pytest.fixture
    def install(self, tmp_path, monkeypatch):
        monkeypatch.undo()  # drop the autouse stand-in; this tests the real one
        bin_dir = tmp_path / "pyhood" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "python").write_text("")
        (bin_dir / "pyhood").write_text("")
        monkeypatch.setattr(cli.sys, "executable", str(bin_dir / "python"))
        return bin_dir / "pyhood"

    def test_on_the_path_it_is_just_pyhood(self, install, monkeypatch):
        monkeypatch.setattr(cli.shutil, "which", lambda name: str(install))
        assert cli.program() == "pyhood"

    def test_off_the_path_it_is_the_full_path(self, install, monkeypatch):
        monkeypatch.setattr(cli.shutil, "which", lambda name: None)
        assert cli.program() == str(install)

    def test_a_different_install_on_the_path_does_not_count(self, install, monkeypatch, tmp_path):
        other = tmp_path / "elsewhere" / "pyhood"
        other.parent.mkdir()
        other.write_text("")
        monkeypatch.setattr(cli.shutil, "which", lambda name: str(other))
        assert cli.program() == str(install)

    def test_the_preview_prints_a_command_that_runs_here(self, install, monkeypatch, capsys):
        monkeypatch.setattr(cli.shutil, "which", lambda name: None)

        cli.stock_order(OrderClient(buying_power=5000.0), "buy", "AAPL", 10, limit=350.0)

        assert f"  {install} buy AAPL 10 --limit 350 --confirm " in capsys.readouterr().out

    def test_the_guide_says_so_only_when_it_matters(self, install, monkeypatch):
        monkeypatch.setattr(cli.shutil, "which", lambda name: None)
        text = guide.render()
        assert "THE COMMAND" in text and str(install) in text

        monkeypatch.setattr(cli.shutil, "which", lambda name: str(install))
        assert "THE COMMAND" not in guide.render()


# ── The guide's commands are real ────────────────────────────────────


def guide_command_lines():
    """Each `pyhood ...` line in the guide's quick answers, without its note."""
    section = guide.INTRO[guide.INTRO.index("QUICK ANSWERS"):guide.INTRO.index("RUNNING A SCRIPT")]
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("pyhood ")]
    # The command ends where the run of spaces before its description begins.
    return [line.split("    ")[0].strip() for line in lines]


def test_the_guide_lists_the_commands():
    assert len(guide_command_lines()) >= 5


@pytest.mark.parametrize("line", guide_command_lines())
def test_every_command_in_the_guide_parses(line):
    """A command the guide shows must be one pyhood accepts."""
    argv = shlex.split(line)[1:]

    args = onboarding.build_parser().parse_args(argv)

    assert args.command in (
        "positions", "orders", "buying-power", "quote", "options", "buy", "sell",
        "buy-option", "sell-option", "cancel",
    )
