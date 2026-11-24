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
from pyhood.exceptions import APIError, AuthError
from pyhood.models import OptionPosition, Order, Position, Quote

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
        assert cancelled.split()[-3:] == ["0", "-", "cancelled"]
        filled = next(line for line in lines if line.endswith("filled"))
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
         {"since": None, "symbol": None, "everything": False, "as_json_output": False}),
        (["orders", "--since", "2026-11-01", "--symbol", "ant", "--json"], cli.orders,
         {"since": "2026-11-01", "symbol": "ant", "everything": False, "as_json_output": True}),
        (["orders", "--all"], cli.orders,
         {"since": None, "symbol": None, "everything": True, "as_json_output": False}),
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

    assert args.command in ("positions", "orders", "buying-power", "quote")
