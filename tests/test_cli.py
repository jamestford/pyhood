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
    BankAccount,
    Candle,
    Dividend,
    Document,
    Earnings,
    Mover,
    NewsArticle,
    OptionContract,
    OptionPosition,
    OptionsChain,
    Order,
    Position,
    Quote,
    Rating,
    UnifiedTransfer,
    Watchlist,
)
from pyhood.settings import Settings

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


def option_order_row(**fields):
    """A single-leg option order as the parser now returns it."""
    base = dict(
        order_id="order-3", symbol="NKE", side="buy", instrument_type="option",
        quantity=1.0, price=1.2, average_price=1.22, filled_quantity=1.0,
        leg_count=1, position_effect="open", option_type="call", strike=65.0,
        expiration="2026-12-18",
    )
    return stock_order(**{**base, **fields})


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

    ACCOUNTS = [
        {"account_number": "111122223", "brokerage_account_type": "individual", "nickname": "",
         "total_equity": {"amount": "7785.45", "currency_code": "USD"},
         "uninvested_cash": {"amount": "168.85", "currency_code": "USD"},
         "account_buying_power": {"amount": "168.85", "currency_code": "USD"}},
        {"account_number": "444455556", "brokerage_account_type": "ira_roth", "nickname": "",
         "total_equity": {"amount": "7000.00", "currency_code": "USD"},
         "uninvested_cash": {"amount": "7000.00", "currency_code": "USD"},
         "account_buying_power": {"amount": "7000.00", "currency_code": "USD"}},
    ]

    def get_all_accounts(self):
        self.calls.append(("get_all_accounts",))
        return [dict(a) for a in self.ACCOUNTS]

    # What the fake is given is in the first account. `roth_stocks`,
    # `roth_options` and `roth_orders` are in the second, which Robinhood only
    # returns when that account is named.
    roth_stocks = ()
    roth_options = ()
    roth_orders = ()

    def get_positions(self, account_number=None):
        if account_number:
            self.calls.append(("get_positions", account_number))
        return list(self.roth_stocks) if account_number == "444455556" else self.stocks

    def get_option_positions(self, account_number=None):
        return list(self.roth_options) if account_number == "444455556" else self.options


    def get_stock_orders(self, start_date=None, account_number=None):
        if account_number in (None, "111122223"):
            self.calls.append(("get_stock_orders", start_date))
            return list(self.stock_orders)
        self.asked_accounts = getattr(self, "asked_accounts", []) + [account_number]
        return list(self.roth_orders) if account_number == "444455556" else []

    def get_option_orders(self, start_date=None, account_number=None):
        if account_number in (None, "111122223"):
            self.calls.append(("get_option_orders", start_date))
            return list(self.option_orders)
        return []

    # The second account's own figure. None means every account answers with
    # `buying_power`, which is all a test of one account needs.
    roth_buying_power = None

    def get_buying_power(self, account_number=None):
        if account_number:
            self.calls.append(("get_buying_power", account_number))
        if account_number == "444455556" and self.roth_buying_power is not None:
            return self.roth_buying_power
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

    def one_account(self, **held):
        client = FakeClient(**held)
        client.ACCOUNTS = FakeClient.ACCOUNTS[:1]
        return client

    def test_table_has_every_position_and_a_total(self, capsys):
        assert cli.positions(self.one_account(stocks=self.STOCKS)) == 0

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

        cli.positions(self.one_account(options=[option]))

        out = capsys.readouterr().out
        assert "NKE 2026-12-18 $65 call" in out
        assert "+$56.00" in out
        assert "per share" in out
        assert "STOCKS" not in out

    def test_nothing_held(self, capsys):
        assert cli.positions(self.one_account()) == 0
        assert capsys.readouterr().out.strip() == "No open positions."

    def test_json(self, capsys):
        cli.positions(self.one_account(stocks=self.STOCKS), as_json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert set(data) == {"stocks", "options"}
        assert data["options"] == []
        assert data["stocks"][1]["symbol"] == "ANT"
        assert data["stocks"][1]["average_cost"] == 97.13

    ROTH_STOCKS = [Position("VTI", 20.0, 300.0, 350.0, 7000.0, 1000.0, 16.67)]

    def test_every_account_is_listed_under_its_own_heading(self, capsys):
        """Asked "what do I hold", an agent would otherwise see the first
        account alone and never learn of a holding in an IRA."""
        client = FakeClient(stocks=self.STOCKS)
        client.roth_stocks = self.ROTH_STOCKS

        assert cli.positions(client) == 0

        out = capsys.readouterr().out
        first, second = out.index("Individual (…2223)"), out.index("Roth IRA (…5556)")
        assert first == 0 and first < out.index("ANT") < second < out.index("VTI")
        assert "111122223" not in out and "444455556" not in out
        # Each account has its own total: the two are not added up.
        totals = [line for line in out.splitlines() if line.startswith("TOTAL")]
        assert len(totals) == 2
        assert "$7,619.64" in totals[0] and "$7,000.00" in totals[1]
        assert client.calls == [("get_all_accounts",), ("get_positions", "111122223"),
                                ("get_positions", "444455556")]

    def test_an_account_holding_nothing_still_has_its_heading(self, capsys):
        cli.positions(FakeClient(stocks=self.STOCKS))

        out = capsys.readouterr().out
        assert out.rstrip().endswith("Roth IRA (…5556)\n\nNo open positions.")

    def test_json_lists_every_account(self, capsys):
        client = FakeClient(stocks=self.STOCKS)
        client.roth_stocks = self.ROTH_STOCKS

        cli.positions(client, as_json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert [p["symbol"] for p in data["stocks"]] == ["TSLA", "ANT"]
        assert [(a["account"], a["account_number"]) for a in data["accounts"]] == [
            ("Individual", "111122223"), ("Roth IRA", "444455556"),
        ]
        assert [p["symbol"] for p in data["accounts"][1]["stocks"]] == ["VTI"]
        assert data["accounts"][1]["options"] == []

    def test_positions_still_list_if_the_accounts_cannot_be_read(self, capsys):
        client = FakeClient(stocks=self.STOCKS)

        def broken():
            raise APIError("503 Service Unavailable")

        client.get_all_accounts = broken

        assert cli.positions(client) == 0
        out = capsys.readouterr().out
        assert out.startswith("STOCKS") and "ANT" in out


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

    def test_a_stop_order_shows_its_stop(self, capsys):
        """Without it a stop market order reads as a plain market order."""
        stop = stock_order(
            order_id="order-3", side="sell", status="confirmed", price=None,
            stop_price=40.0, average_price=None, filled_at=None, filled_quantity=0.0,
        )

        cli.orders(FakeClient(stock_orders=[stop, stock_order()]))

        lines = capsys.readouterr().out.splitlines()
        assert lines[1].split()[4:8] == ["TYPE", "ORDERED", "LIMIT", "STOP"]
        row = next(line for line in lines if line.endswith("order-3"))
        assert row.split()[-6:] == ["-", "$40.00", "0", "-", "confirmed", "order-3"]
        plain = next(line for line in lines if line.endswith("order-1"))
        assert plain.split()[-5] == "-"  # no stop

    def test_a_market_order_does_not_show_its_collar_as_a_limit(self, capsys):
        """Robinhood records the price ceiling it requires on a market order."""
        market = stock_order(order_id="order-4", order_type="market", price=11.94)

        cli.orders(FakeClient(stock_orders=[market]))

        row = next(line for line in capsys.readouterr().out.splitlines()
                   if line.endswith("order-4"))
        assert "market" in row.split()
        assert "$11.94" not in row

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
        assert client.calls == [("get_all_accounts",), ("get_stock_orders", expected),
                                ("get_option_orders", expected)]

        client = FakeClient()
        cli.orders(client, since="2026-01-01")
        assert client.calls[1] == ("get_stock_orders", "2026-01-01")

        client = FakeClient()
        cli.orders(client, since="2026-01-01", everything=True)
        assert client.calls[1] == ("get_stock_orders", None)

    ROTH_ORDER = stock_order(
        order_id="order-roth", symbol="F", status="queued", quantity=1.0, price=5.0,
        created_at=datetime(2026, 11, 20, 3, 41, 56, tzinfo=UTC), filled_at=None,
        average_price=None, filled_quantity=0.0, account_number="444455556",
    )

    def test_an_order_in_another_account_is_shown(self, capsys):
        """Robinhood's order list holds the default account's orders only. An
        order placed in a Roth IRA was missing from `pyhood orders`, so the
        command the placing step said to check it with showed nothing."""
        client = FakeClient(stock_orders=[stock_order()])
        client.roth_orders = [self.ROTH_ORDER]

        cli.orders(client)

        out = capsys.readouterr().out
        lines = out.splitlines()
        assert "in your 2 accounts" in lines[0]
        assert lines[1].split()[:2] == ["PLACED", "ACCOUNT"]
        roth = next(line for line in lines if line.endswith("order-roth"))
        assert "Roth IRA" in roth
        assert roth.split()[-2:] == ["queued", "order-roth"]
        mine = next(line for line in lines if line.endswith("order-1"))
        assert "Individual" in mine
        assert client.asked_accounts == ["444455556"]

    def test_open_orders_include_other_accounts(self, capsys):
        client = FakeClient(stock_orders=[stock_order()])
        client.roth_orders = [self.ROTH_ORDER]

        cli.orders(client, open_only=True)

        out = capsys.readouterr().out
        assert "order-roth" in out
        assert "order-1" not in out

    def test_account_narrows_to_one_account(self, capsys):
        client = FakeClient(stock_orders=[stock_order()])
        client.roth_orders = [self.ROTH_ORDER]

        cli.orders(client, account="roth")

        out = capsys.readouterr().out
        assert "in Roth IRA (…5556)" in out.splitlines()[0]
        assert "ACCOUNT" not in out.splitlines()[1]
        assert "order-roth" in out and "order-1" not in out

    def test_with_one_account_nothing_changes(self, capsys):
        client = FakeClient(stock_orders=[stock_order()])
        client.ACCOUNTS = client.ACCOUNTS[:1]

        cli.orders(client)

        out = capsys.readouterr().out
        assert "accounts" not in out.splitlines()[0]
        assert "ACCOUNT" not in out.splitlines()[1]
        assert not hasattr(client, "asked_accounts")

    def test_the_orders_still_list_if_the_accounts_cannot_be_read(self, capsys):
        client = FakeClient(stock_orders=[stock_order()])

        def broken():
            raise APIError("503 Service Unavailable")

        client.get_all_accounts = broken

        assert cli.orders(client) == 0
        assert "order-1" in capsys.readouterr().out

    def test_stock_and_option_orders_are_merged_newest_first(self, capsys):
        option = option_order_row(
            order_id="order-3", created_at=datetime(2026, 11, 19, 17, 0, tzinfo=UTC),
        )

        cli.orders(FakeClient(stock_orders=[CANCELLED, stock_order()], option_orders=[option]))

        rows = capsys.readouterr().out.splitlines()[2:5]
        assert [row.split()[-1] for row in rows] == ["order-1", "order-3", "order-2"]
        assert ["stock" in row for row in rows] == [True, False, True]

    def test_an_option_order_reads_as_a_trade_in_a_contract(self, capsys):
        """Robinhood calls it a 'debit' of an 'option'. It is a buy to open
        of a particular call."""
        cli.orders(FakeClient(option_orders=[option_order_row()]))

        row = capsys.readouterr().out.splitlines()[2]
        assert "  buy to open  NKE     $65.00 call 2026-12-18  " in row
        assert "debit" not in row and "credit" not in row

    def test_a_spread_is_named_by_its_legs(self, capsys):
        spread = option_order_row(
            leg_count=2, strike=None, option_type=None, expiration=None,
        )

        cli.orders(FakeClient(option_orders=[spread]))

        assert "  buy to open  NKE     2-leg option  " in capsys.readouterr().out

    def test_an_option_order_with_no_leg_detail_still_prints(self, capsys):
        bare = stock_order(order_id="order-3", symbol="NKE", instrument_type="option")

        cli.orders(FakeClient(option_orders=[bare]))

        assert "  buy   NKE     option  " in capsys.readouterr().out

    def test_symbol_filter(self, capsys):
        other = stock_order(order_id="order-4", symbol="AAPL")

        cli.orders(FakeClient(stock_orders=[stock_order(), other]), symbol="aapl")

        out = capsys.readouterr().out
        assert "for AAPL" in out.splitlines()[0]
        assert "ANT" not in out

    def test_none_found_says_how_to_look_further_back(self, capsys):
        cli.orders(FakeClient(), since="2026-11-01")
        out = capsys.readouterr().out
        assert "Orders since 2026-11-01 in your 2 accounts: none." in out
        assert "--all" in out

        cli.orders(FakeClient(), everything=True)
        assert capsys.readouterr().out.strip() == "All orders in your 2 accounts: none."

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

    def one_account(self):
        client = FakeClient()
        client.ACCOUNTS = FakeClient.ACCOUNTS[:1]
        return client

    def two_accounts(self):
        client = FakeClient()
        client.roth_buying_power = 7000.0
        return client

    def test_buying_power(self, capsys):
        assert cli.buying_power(self.one_account()) == 0
        assert capsys.readouterr().out.strip() == "Buying power: $168.85"

        cli.buying_power(self.one_account(), as_json_output=True)
        assert json.loads(capsys.readouterr().out) == {"buying_power": 168.85}

    def test_buying_power_shows_every_account(self, capsys):
        """Asked "how much cash do I have", an agent ran this and answered
        with the individual account alone: the IRA's cash was never shown."""
        client = self.two_accounts()

        assert cli.buying_power(client) == 0

        out = capsys.readouterr().out
        rows = out.splitlines()
        assert rows[0].split() == ["ACCOUNT", "NUMBER", "BUYING", "POWER"]
        assert rows[1].split() == ["Individual", "…2223", "$168.85"]
        assert rows[2].split() == ["Roth", "IRA", "…5556", "$7,000.00"]
        assert "111122223" not in out and "444455556" not in out
        # Each account is asked by number, and the two are not added up.
        assert client.calls == [("get_all_accounts",), ("get_buying_power", "111122223"),
                                ("get_buying_power", "444455556")]
        assert "7,168.85" not in out
        assert "only its own buying power" in out
        assert "--account roth" in out

    def test_buying_power_json_lists_every_account(self, capsys):
        cli.buying_power(self.two_accounts(), as_json_output=True)

        assert json.loads(capsys.readouterr().out) == {
            "buying_power": 168.85,
            "accounts": [
                {"account": "Individual", "account_number": "111122223",
                 "buying_power": 168.85},
                {"account": "Roth IRA", "account_number": "444455556",
                 "buying_power": 7000.0},
            ],
        }

    def test_buying_power_still_answers_if_the_accounts_cannot_be_read(self, capsys):
        client = FakeClient()

        def broken():
            raise APIError("503 Service Unavailable")

        client.get_all_accounts = broken

        assert cli.buying_power(client) == 0
        assert capsys.readouterr().out.strip() == "Buying power: $168.85"

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
        assert "pyhood is not authorized" in err
        assert "authorize\n" in err and "authorize --window" in err

    def test_api_failure_is_one_line_not_a_traceback(self, monkeypatch, capsys):
        import pyhood

        def failing(client, **kwargs):
            raise APIError("503 Service Unavailable")

        monkeypatch.setattr(pyhood, "login", lambda: object())
        monkeypatch.setattr("pyhood.client.PyhoodClient", lambda session: object())

        assert cli.run(failing) == 1
        assert "Robinhood request failed: 503 Service Unavailable" in capsys.readouterr().err

    @pytest.mark.parametrize(("argv", "command", "kwargs"), [
        (["positions"], cli.positions, {"account": None, "as_json_output": False}),
        (["positions", "--json", "--account", "roth"], cli.positions,
         {"account": "roth", "as_json_output": True}),
        (["orders"], cli.orders,
         {"since": None, "symbol": None, "everything": False, "open_only": False,
          "as_json_output": False, "account": None}),
        (["orders", "--since", "2026-11-01", "--symbol", "ant", "--json"], cli.orders,
         {"since": "2026-11-01", "symbol": "ant", "everything": False, "open_only": False,
          "as_json_output": True, "account": None}),
        (["orders", "--all", "--open", "--account", "roth"], cli.orders,
         {"since": None, "symbol": None, "everything": True, "open_only": True,
          "as_json_output": False, "account": "roth"}),
        (["buying-power"], cli.buying_power, {"account": None, "as_json_output": False}),
        (["accounts"], cli.accounts, {"as_json_output": False}),
        (["earnings", "AAPL", "NVDA", "--days", "30"], cli.earnings,
         {"symbols": ["AAPL", "NVDA"], "days": 30, "as_json_output": False}),
        (["ratings", "AAPL"], cli.ratings, {"symbols": ["AAPL"], "as_json_output": False}),
        (["news", "AAPL", "--count", "3", "--json"], cli.news,
         {"symbol": "AAPL", "count": 3, "as_json_output": True}),
        (["movers", "--down"], cli.movers, {"down": True, "as_json_output": False}),
        (["history", "AAPL", "--span", "year"], cli.history,
         {"symbol": "AAPL", "span": "year", "as_json_output": False}),
        (["dividends", "--symbol", "KO"], cli.dividends,
         {"symbol": "KO", "as_json_output": False}),
        (["transfers"], cli.transfers, {"as_json_output": False}),
        (["documents", "--type", "1099", "--year", "2026"], cli.documents,
         {"kind": "1099", "year": 2026, "as_json_output": False}),
        (["watchlists"], cli.watchlists, {"as_json_output": False}),
        (["watch", "F", "GM"], cli.watch,
         {"symbols": ["F", "GM"], "list_name": "My First List", "remove": False}),
        (["unwatch", "F", "--list", "Tech"], cli.watch,
         {"symbols": ["F"], "list_name": "Tech", "remove": True}),
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

    def get_buying_power(self, account_number=None):
        self.reads.append("get_buying_power")
        if account_number:
            self.calls.append(("get_buying_power", account_number))
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
        assert out.startswith("NOT PLACED. This order needs your confirmation.")
        assert "Buy 10 AAPL, limit $350.00, good for day" in out
        assert "Estimated cost:     $3,500.00" in out
        assert "Buying power:       $5,000.00" in out
        assert "show this to the user" in out
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
    """A cancel is one step. It names one order and can only remove it, and
    someone who wants out of an order should not wait on a second command."""

    OPEN = stock_order(
        order_id="order-9", status="confirmed", quantity=40.0, price=90.0,
        average_price=None, filled_at=None, filled_quantity=0.0,
    )

    def test_it_cancels_at_once_and_says_what_it_cancelled(self, capsys):
        client = OrderClient(existing=self.OPEN)

        assert cli.cancel(client, "order-9", settle_seconds=0) == 0

        assert client.writes == [("cancel", "order-9")]
        out = capsys.readouterr().out
        assert out.startswith("CANCELLED: buy 40 ANT, limit $90.00, placed 2026-11-19")
        assert "NOT PLACED" not in out and "--confirm" not in out

    def test_a_stop_order_is_described_with_its_stop(self, capsys):
        stop = stock_order(
            order_id="order-9", side="sell", status="confirmed", quantity=1.0, price=None,
            stop_price=40.0, average_price=None, filled_at=None, filled_quantity=0.0,
        )

        cli.cancel(OrderClient(existing=stop), "order-9", settle_seconds=0)

        out = capsys.readouterr().out
        assert out.startswith("CANCELLED: sell 1 ANT, stop $40.00 then at market, placed")

    def test_an_order_that_filled_before_the_cancel_landed_says_so(self, capsys):
        client = OrderClient(existing=self.OPEN, after_cancel="filled")

        cli.cancel(client, "order-9", settle_seconds=0)

        out = capsys.readouterr().out
        assert "CANCELLED" not in out
        assert "the order is now filled" in out
        assert "pyhood orders --symbol ANT" in out

    def test_a_part_that_already_filled_is_reported_as_not_undone(self, capsys):
        part_filled = stock_order(
            order_id="order-9", status="partially_filled", quantity=40.0, price=90.0,
            average_price=89.5, filled_quantity=15.0,
        )
        client = OrderClient(existing=part_filled)
        client.cancel_order = lambda order_id: (
            client.writes.append(("cancel", order_id)),
            setattr(client, "existing", stock_order(
                order_id="order-9", status="cancelled", quantity=40.0, price=90.0,
                average_price=89.5, filled_quantity=15.0,
            )),
        )

        assert cli.cancel(client, "order-9", settle_seconds=0) == 0

        out = capsys.readouterr().out
        assert out.startswith("CANCELLED: buy 40 ANT")
        assert "15 had already filled at $89.50 and is not undone" in out

    def test_a_finished_order_is_left_alone(self, capsys):
        client = OrderClient(existing=stock_order(order_id="order-1"))  # filled

        assert cli.cancel(client, "order-1", settle_seconds=0) == 1

        assert "already filled, so there is nothing to cancel" in capsys.readouterr().out
        assert client.writes == []

    def test_an_order_that_stays_open_is_a_failure(self, capsys):
        client = OrderClient(existing=self.OPEN, after_cancel="confirmed")

        assert cli.cancel(client, "order-9", settle_seconds=0, attempts=2) == 1
        assert "Cancel requested, but the order is now confirmed" in capsys.readouterr().out

    def test_an_unknown_order_id_changes_nothing(self):
        client = OrderClient(existing=None)

        with pytest.raises(OrderError, match="not found"):
            cli.cancel(client, "no-such-order", settle_seconds=0)
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
         {"side": "buy", "symbol": "AAPL", "quantity": 10.0, "limit": 350.0, "stop": None,
          "time_in_force": "gfd", "extended_hours": False, "account": None, "confirm": None,
          "dollars": None, "trail_percent": None, "trail_amount": None}),
        (["sell", "AAPL", "10", "--stop", "340", "--limit", "338", "--account", "roth"],
         {"side": "sell", "symbol": "AAPL", "quantity": 10.0, "limit": 338.0, "stop": 340.0,
          "time_in_force": "gfd", "extended_hours": False, "account": "roth", "confirm": None,
          "dollars": None, "trail_percent": None, "trail_amount": None}),
        (["buy", "AAPL", "--dollars", "50", "--market"],
         {"side": "buy", "symbol": "AAPL", "quantity": None, "limit": None, "stop": None,
          "time_in_force": "gfd", "extended_hours": False, "account": None, "confirm": None,
          "dollars": 50.0, "trail_percent": None, "trail_amount": None}),
        (["sell", "AAPL", "10", "--trail-percent", "5", "--market", "--tif", "gtc"],
         {"side": "sell", "symbol": "AAPL", "quantity": 10.0, "limit": None, "stop": None,
          "time_in_force": "gtc", "extended_hours": False, "account": None, "confirm": None,
          "dollars": None, "trail_percent": 5.0, "trail_amount": None}),
        (["sell", "ant", "0.5", "--market", "--tif", "gtc", "--extended-hours",
          "--confirm", "abc123"],
         {"side": "sell", "symbol": "ant", "quantity": 0.5, "limit": None, "stop": None,
          "time_in_force": "gtc", "extended_hours": True, "account": None,
          "confirm": "abc123", "dollars": None, "trail_percent": None, "trail_amount": None}),
    ])
    def test_buy_and_sell(self, monkeypatch, argv, kwargs):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        assert onboarding.main(argv) == 0
        # An order goes through the user's confirmation setting on its way.
        assert seen == [(cli.place_or_ask,
                         {"order_command": cli.stock_order, "ask": False, **kwargs})]

    def test_cancel(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main(["cancel", "order-9"])
        assert seen == [(cli.cancel, {"order_id": "order-9"})]

    def test_cancel_takes_no_confirmation_code(self):
        """It did in 0.17.0. A cancel is now one step."""
        with pytest.raises(SystemExit) as stop:
            onboarding.main(["cancel", "order-9", "--confirm", "abc123"])
        assert stop.value.code == 2

    @pytest.mark.parametrize("argv", [
        ["buy", "AAPL", "10"],                              # neither --limit nor --market
        ["buy", "AAPL", "10", "--limit", "350", "--market"],  # both
        ["buy", "AAPL", "0", "--limit", "350"],
        ["buy", "AAPL", "-5", "--limit", "350"],
        ["buy", "AAPL", "ten", "--limit", "350"],
        ["buy", "AAPL", "nan", "--limit", "350"],
        ["buy", "AAPL", "10", "--limit", "0"],
        ["sell", "AAPL", "10", "--stop", "340"],              # a stop still needs a price
        ["sell", "AAPL", "10", "--stop", "0", "--market"],
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
        self.existing = option_order_row(
            order_id="option-order", symbol=args[0], side=side, quantity=float(args[4]),
            price=args[5], status="queued", average_price=None, filled_at=None,
            filled_quantity=0.0, position_effect=kwargs.get("position_effect"),
            option_type=args[3], strike=args[1], expiration=args[2],
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
        assert out.startswith("NOT PLACED. This order needs your confirmation.")
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
        waiting = option_order_row(
            order_id="option-order", symbol="F", quantity=2.0, price=0.30, status="queued",
            average_price=None, filled_at=None, filled_quantity=0.0, strike=12.0,
            expiration="2026-12-11",
        )

        cli.cancel(OptionClient(existing=waiting), "option-order", settle_seconds=0)

        out = capsys.readouterr().out
        assert out.startswith(
            "CANCELLED: buy to open 2 F $12.00 call 2026-12-11, limit $0.30 per share, placed"
        )


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
        assert seen == [(cli.place_or_ask, {
            "order_command": cli.option_order, "ask": False,
            "side": "buy", "symbol": "F", "expiration": "2026-12-11", "strike": 12.0,
            "option_type": "call", "contracts": 2, "limit": 0.30, "effect": None,
            "time_in_force": "gfd", "account": None, "confirm": None,
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


# ── Numbers survive being typed back in ──────────────────────────────


class TestPlainNumbers:
    """Every number in a printed command and in a confirmation code is
    written in full. The 'g' format they used keeps six significant
    digits, so a limit of 12345.67 was printed as 12345.7: the command the
    preview said to run was for a different price, and was refused."""

    @pytest.mark.parametrize(("value", "text"), [
        (12345.67, "12345.67"), (5000000.0, "5000000"), (0.00001, "0.00001"),
        (350.0, "350"), (0.3, "0.3"), (1234567.0, "1234567"), (59250.75, "59250.75"),
    ])
    def test_written_in_full(self, value, text):
        assert cli.plain(value) == text
        assert float(cli.plain(value)) == value

    def test_a_long_price_round_trips_through_the_printed_command(self, capsys):
        client = OrderClient(buying_power=10_000_000.0, price=12345.0, bid=12344.0, ask=12346.0)

        cli.stock_order(client, "buy", "BRK", 3, limit=12345.67)
        out = capsys.readouterr().out
        printed = out.splitlines()[-1].split()

        assert printed[printed.index("--limit") + 1] == "12345.67"
        code = printed[printed.index("--confirm") + 1]
        assert cli.stock_order(client, "buy", "BRK", 3, limit=float("12345.67"), confirm=code,
                               settle_seconds=0) == 0
        assert client.writes[0][3]["price"] == 12345.67

    def test_orders_that_differ_past_the_sixth_digit_have_different_codes(self, capsys):
        """Under the old format 1234567 and 1234568 shares were the same
        text, so a code for one would have placed the other."""
        client = OrderClient(buying_power=1e12)
        cli.stock_order(client, "buy", "AAPL", 1234567, limit=350.0)
        code = code_from(capsys.readouterr().out)

        assert cli.stock_order(client, "buy", "AAPL", 1234568, limit=350.0, confirm=code,
                               settle_seconds=0) == 2
        assert cli.stock_order(client, "buy", "AAPL", 1234567, limit=350.004, confirm=code,
                               settle_seconds=0) == 2
        assert client.writes == []


class TestDollarOrders:
    def client(self, **kwargs):
        client = OrderClient(buying_power=500.0, **kwargs)
        client.by_price = []
        client.buy_stock_by_price = lambda s, d, **k: (
            client.by_price.append(("buy", s, d, k)), client._place("buy", s, d, **k))[1]
        client.sell_stock_by_price = lambda s, d, **k: (
            client.by_price.append(("sell", s, d, k)), client._place("sell", s, d, **k))[1]
        return client

    def test_preview_shows_the_shares_it_comes_to(self, capsys):
        cli.stock_order(self.client(), "buy", "aapl", dollars=50.0)

        out = capsys.readouterr().out
        assert "Buy $50.00 of AAPL, at market, good for day" in out
        assert "Estimated cost:     $50.00" in out
        assert "About:              0.142816 shares at $350.10" in out
        assert "pyhood buy AAPL --dollars 50 --market --confirm" in out

    def test_it_is_placed_by_dollar_amount(self, capsys):
        client = self.client()
        cli.stock_order(client, "buy", "AAPL", dollars=50.0)
        code = code_from(capsys.readouterr().out)

        assert cli.stock_order(client, "buy", "AAPL", dollars=50.0, confirm=code,
                               settle_seconds=0) == 0
        assert client.by_price == [("buy", "AAPL", 50.0, {"time_in_force": "gfd"})]

    def test_a_code_for_shares_will_not_place_dollars(self, capsys):
        client = self.client()
        cli.stock_order(client, "buy", "AAPL", 50, limit=None)
        code = code_from(capsys.readouterr().out)

        assert cli.stock_order(client, "buy", "AAPL", dollars=50.0, confirm=code,
                               settle_seconds=0) == 2
        assert client.by_price == []

    @pytest.mark.parametrize(("kwargs", "message"), [
        ({"dollars": 50.0, "limit": 300.0}, "is a market order"),
        ({"dollars": 50.0, "stop": 300.0}, "is a market order"),
        ({"dollars": 0.5}, "smallest order by dollar amount is \\$1"),
        ({"dollars": 50.0, "extended_hours": True}, "regular hours only"),
        ({"dollars": 50.0, "quantity": 2}, "but not both"),
        ({}, "but not both"),
    ])
    def test_what_a_dollar_order_cannot_be(self, kwargs, message):
        with pytest.raises(cli.UsageError, match=message):
            cli.stock_order(self.client(), "buy", "AAPL", **kwargs)

    def test_selling_dollars_checks_what_is_held(self, capsys):
        client = self.client(stocks=[Position("AAPL", 0.1, 300.0, 350.0, 35.0, 5.0, 16.7)])

        cli.stock_order(client, "sell", "AAPL", dollars=50.0)

        out = capsys.readouterr().out
        assert "Sell $50.00 of AAPL" in out
        assert "fewer than this order sells" in out

    def test_a_fraction_of_a_share_with_a_limit_is_pointed_out(self, capsys):
        cli.stock_order(self.client(), "buy", "AAPL", 0.5, limit=340.0)
        assert "only as a market order" in capsys.readouterr().out

        cli.stock_order(self.client(), "buy", "AAPL", 2, limit=340.0)
        assert "only as a market order" not in capsys.readouterr().out


class TestTrailingStops:
    HELD = [Position("ANT", 95.0, 97.13, 82.0, 7790.0, -1437.0, -15.6)]

    def client(self, **kwargs):
        return OrderClient(stocks=self.HELD, price=82.0, bid=81.9, ask=82.1, **kwargs)

    def test_a_percentage_trail(self, capsys):
        client = self.client()

        cli.stock_order(client, "sell", "ANT", 10, trail_percent=5.0, time_in_force="gtc")

        out = capsys.readouterr().out
        assert "Sell 10 ANT, trailing stop 5% below the price, then at market" in out
        assert "Stop starts at:     $77.90, and follows the price from there" in out
        assert "Estimated proceeds: $779.00" in out
        assert "pyhood sell ANT 10 --trail-percent 5 --market --tif gtc --confirm" in out

        cli.stock_order(client, "sell", "ANT", 10, trail_percent=5.0, time_in_force="gtc",
                        confirm=code_from(out), settle_seconds=0)
        assert client.writes == [("sell", "ANT", 10, {
            "price": None, "time_in_force": "gtc", "extended_hours": False,
            "trail_percent": 5.0,
        })]

    def test_a_dollar_trail(self, capsys):
        cli.stock_order(self.client(), "sell", "ANT", 10, trail_amount=4.0)

        out = capsys.readouterr().out
        assert "trailing stop $4.00 below the price" in out
        assert "Stop starts at:     $78.00" in out
        assert "pyhood sell ANT 10 --trail-amount 4 --market --confirm" in out

    def test_a_buy_trails_above_the_price(self, capsys):
        cli.stock_order(self.client(buying_power=9999.0), "buy", "ANT", 1, trail_percent=10.0)

        out = capsys.readouterr().out
        assert "trailing stop 10% above the price" in out
        assert "Stop starts at:     $90.20" in out

    def test_a_sell_carries_no_warning_that_it_may_be_refused(self, capsys):
        """A trailing stop sell was placed live on 2026-11-24."""
        cli.stock_order(self.client(), "sell", "ANT", 10, trail_percent=5.0)

        out = capsys.readouterr().out
        assert "may reject" not in out
        assert "lasts for today only" in out

    def test_a_buy_says_it_has_not_been_placed_before(self, capsys):
        """Better to hear that before saying yes than after."""
        cli.stock_order(self.client(), "buy", "ANT", 10, trail_percent=10.0)

        assert "has not yet been placed through pyhood" in capsys.readouterr().out

    def test_a_code_for_one_trail_will_not_place_another(self, capsys):
        client = self.client()
        cli.stock_order(client, "sell", "ANT", 10, trail_percent=5.0)
        code = code_from(capsys.readouterr().out)

        for other in ({"trail_percent": 50.0}, {"trail_amount": 5.0}, {}):
            assert cli.stock_order(client, "sell", "ANT", 10, **other, confirm=code,
                                   settle_seconds=0) == 2
        assert client.writes == []

    @pytest.mark.parametrize(("kwargs", "message"), [
        ({"trail_percent": 5.0, "limit": 70.0}, "is a market order"),
        ({"trail_percent": 5.0, "stop": 70.0}, "is a market order"),
        ({"trail_percent": 5.0, "trail_amount": 3.0}, "one of them"),
        ({"trail_percent": 100.0}, "under 100"),
    ])
    def test_what_a_trailing_stop_cannot_be(self, kwargs, message):
        with pytest.raises(cli.UsageError, match=message):
            cli.stock_order(self.client(), "sell", "ANT", 10, **kwargs)

    def test_a_refusal_reports_robinhoods_reason(self, capsys):
        client = self.client(reject="Order rejected: trailing stops are not available")
        cli.stock_order(client, "sell", "ANT", 10, trail_percent=5.0)
        code = code_from(capsys.readouterr().out)

        assert cli.stock_order(client, "sell", "ANT", 10, trail_percent=5.0, confirm=code,
                               settle_seconds=0) == 1
        assert "trailing stops are not available" in capsys.readouterr().err


class TestDocuments:
    DOCS = [
        Document("doc-1", "account_statement", "2026-10-31"),
        Document("doc-2", "1099", "2026-02-10"),
        Document("doc-3", "trade_confirm", "2026-11-19"),
        Document("doc-4", "account_statement", "2025-12-31"),
    ]

    def client(self):
        client = FakeClient()
        client.get_documents = lambda: list(self.DOCS)
        client.saved = []
        client.download_document = lambda document_id, to: (
            client.saved.append((document_id, to)),
            __import__("pathlib").Path(to) / "2026-10-31_account_statement.pdf",
        )[1]
        return client

    def test_listed_newest_first_with_ids(self, capsys):
        cli.documents(self.client())

        rows = capsys.readouterr().out.splitlines()
        assert [row.split() for row in rows[1:5]] == [
            ["2026-11-19", "trade_confirm", "doc-3"],
            ["2026-10-31", "account_statement", "doc-1"],
            ["2026-02-10", "1099", "doc-2"],
            ["2025-12-31", "account_statement", "doc-4"],
        ]
        assert "pyhood document DOCUMENT_ID" in rows[-1]

    def test_filtered_by_part_of_a_type_and_by_year(self, capsys):
        cli.documents(self.client(), kind="statement", year=2026)
        out = capsys.readouterr().out
        assert "doc-1" in out
        assert "doc-4" not in out and "doc-2" not in out

        cli.documents(self.client(), kind="K-1")
        assert capsys.readouterr().out.strip() == "No documents match."

    def test_json_has_no_download_links(self, capsys):
        """A link is a way to fetch the document. The ID is enough."""
        cli.documents(self.client(), as_json_output=True)
        assert json.loads(capsys.readouterr().out)[0] == {
            "date": "2026-11-19", "type": "trade_confirm", "id": "doc-3",
        }

    def test_saving_one_says_where_it_went(self, capsys):
        client = self.client()

        assert cli.document(client, "doc-1", to="papers") == 0

        assert client.saved == [("doc-1", "papers")]
        out = capsys.readouterr().out
        assert out.startswith("Saved papers/2026-10-31_account_statement.pdf")
        assert "readable only by you" in out

    def test_command_line(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main(["document", "doc-1", "--to", "papers"])
        onboarding.main(["document", "doc-1"])
        assert seen == [
            (cli.document, {"document_id": "doc-1", "to": "papers"}),
            (cli.document, {"document_id": "doc-1", "to": "documents"}),
        ]


# ── Accounts ─────────────────────────────────────────────────────────


class TestAccounts:
    def test_lists_each_account_with_its_number_masked(self, capsys):
        assert cli.accounts(FakeClient()) == 0

        out = capsys.readouterr().out
        rows = out.splitlines()
        assert rows[1].split() == ["Individual", "…2223", "$7,785.45", "$168.85", "$168.85"]
        assert rows[2].split()[:3] == ["Roth", "IRA", "…5556"]
        assert "111122223" not in out and "444455556" not in out
        assert "positions, orders and buying-power cover every account" in out
        assert "pyhood buy AAPL 1 --limit 350 --account roth" in out

    def test_json_gives_the_numbers_in_full(self, capsys):
        cli.accounts(FakeClient(), as_json_output=True)

        data = json.loads(capsys.readouterr().out)
        assert data[1] == {
            "account": "Roth IRA", "type": "ira_roth", "account_number": "444455556",
            "value": 7000.0, "cash": 7000.0, "buying_power": 7000.0,
        }

    @pytest.mark.parametrize("selector", [
        "roth", "ROTH", "ira", "Roth IRA", "ira_roth", "5556", "444455556",
    ])
    def test_an_account_can_be_named_several_ways(self, selector):
        number, label = cli.find_account(FakeClient(), selector)
        assert number == "444455556"
        assert label == "Roth IRA (…5556)"

    def test_no_selector_means_the_default_and_no_lookup(self):
        client = FakeClient()
        assert cli.find_account(client, None) == (None, "")
        assert client.calls == []

    def test_an_account_that_does_not_exist_lists_the_ones_that_do(self):
        with pytest.raises(cli.UsageError) as error:
            cli.find_account(FakeClient(), "401k")
        assert "No account matches '401k'" in str(error.value)
        assert "Individual (…2223), Roth IRA (…5556)" in str(error.value)

    def test_a_selector_that_fits_two_accounts_is_refused(self):
        """Guessing which account an order goes to is not acceptable."""
        client = FakeClient()
        client.ACCOUNTS = [
            *FakeClient.ACCOUNTS,
            {"account_number": "777788889", "brokerage_account_type": "ira_traditional",
             "nickname": ""},
        ]
        with pytest.raises(cli.UsageError, match="more than one account"):
            cli.find_account(client, "ira")
        assert cli.find_account(client, "traditional")[0] == "777788889"

    def test_three_digits_are_too_few_to_name_an_account(self):
        with pytest.raises(cli.UsageError):
            cli.find_account(FakeClient(), "556")

    def test_positions_and_buying_power_read_the_named_account(self, capsys):
        client = FakeClient(buying_power=7000.0)

        cli.positions(client, account="roth")
        cli.buying_power(client, account="roth")

        out = capsys.readouterr().out
        assert ("get_positions", "444455556") in client.calls
        assert ("get_buying_power", "444455556") in client.calls
        assert out.startswith("Roth IRA (…5556)")
        assert "Buying power in Roth IRA (…5556): $7,000.00" in out

    def test_usage_errors_exit_2_without_a_traceback(self, monkeypatch, capsys):
        import pyhood

        monkeypatch.setattr(pyhood, "login", lambda: object())
        monkeypatch.setattr("pyhood.client.PyhoodClient", lambda session: FakeClient())

        assert cli.run(cli.positions, account="401k") == 2
        assert "No account matches '401k'" in capsys.readouterr().err


class TestOrdersInAnAccount:
    def test_a_stock_order_goes_to_the_named_account(self, capsys):
        client = OrderClient(buying_power=7000.0)

        cli.stock_order(client, "buy", "AAPL", 10, limit=350.0, account="roth")

        out = capsys.readouterr().out
        assert "Buy 10 AAPL, limit $350.00, good for day, in Roth IRA (…5556)" in out
        assert ("get_buying_power", "444455556") in client.calls
        assert out.splitlines()[-1].split(" --confirm ")[0].endswith("--limit 350 --account roth")

        cli.stock_order(client, "buy", "AAPL", 10, limit=350.0, account="roth",
                        confirm=code_from(out), settle_seconds=0)
        assert client.writes[0][3]["account_number"] == "444455556"

    def test_a_code_for_one_account_will_not_place_in_another(self, capsys):
        client = OrderClient(buying_power=7000.0)
        cli.stock_order(client, "buy", "AAPL", 10, limit=350.0)
        code = code_from(capsys.readouterr().out)

        assert cli.stock_order(client, "buy", "AAPL", 10, limit=350.0, account="roth",
                               confirm=code, settle_seconds=0) == 2
        assert client.writes == []

    def test_an_order_names_no_account_unless_asked(self, capsys):
        client = OrderClient(buying_power=7000.0)
        cli.stock_order(client, "buy", "AAPL", 10, limit=350.0)
        code = code_from(capsys.readouterr().out)

        cli.stock_order(client, "buy", "AAPL", 10, limit=350.0, confirm=code, settle_seconds=0)

        assert "account_number" not in client.writes[0][3]
        assert ("get_all_accounts",) not in client.calls

    def test_an_option_order_goes_to_the_named_account(self, capsys):
        client = OptionClient(buying_power=7000.0)
        order = dict(side="buy", symbol="F", expiration="2026-12-11", strike=12.0,
                     option_type="call", contracts=1, limit=0.30, account="roth")

        cli.option_order(client, **order)
        out = capsys.readouterr().out
        assert "good for day, in Roth IRA (…5556)" in out

        cli.option_order(client, **order, confirm=code_from(out), settle_seconds=0)
        assert client.writes[0][2]["account_number"] == "444455556"


class TestStopOrders:
    HELD = [Position("ANT", 95.0, 97.13, 82.0, 7790.0, -1437.0, -15.6)]

    def client(self, **kwargs):
        return OrderClient(stocks=self.HELD, price=82.0, bid=81.9, ask=82.1, **kwargs)

    def test_a_stop_market_order(self, capsys):
        client = self.client()

        cli.stock_order(client, "sell", "ANT", 10, limit=None, stop=70.0)

        out = capsys.readouterr().out
        assert "Sell 10 ANT, stop $70.00 then at market, good for day" in out
        assert "Estimated proceeds: $700.00" in out  # at the stop, not today's price
        assert "pyhood sell ANT 10 --stop 70 --market --confirm" in out

        cli.stock_order(client, "sell", "ANT", 10, limit=None, stop=70.0,
                        confirm=code_from(out), settle_seconds=0)
        assert client.writes == [("sell", "ANT", 10, {
            "price": None, "time_in_force": "gfd", "extended_hours": False,
            "stop_price": 70.0,
        })]

    def test_a_stop_limit_order(self, capsys):
        client = self.client()

        cli.stock_order(client, "sell", "ANT", 10, limit=69.0, stop=70.0, time_in_force="gtc")

        out = capsys.readouterr().out
        assert "Sell 10 ANT, stop $70.00 then limit $69.00, good till cancelled" in out
        assert "pyhood sell ANT 10 --stop 70 --limit 69 --tif gtc --confirm" in out
        assert "today only" not in out

    def test_a_stop_that_would_trigger_at_once_is_pointed_out(self, capsys):
        cli.stock_order(self.client(), "sell", "ANT", 10, limit=None, stop=90.0)
        assert "already at or above the last price of $82.00" in capsys.readouterr().out

        cli.stock_order(self.client(buying_power=9999.0), "buy", "ANT", 1, limit=None, stop=80.0)
        assert "already at or below the last price of $82.00" in capsys.readouterr().out

    def test_a_stop_good_only_for_today_is_pointed_out(self, capsys):
        """A stop that quietly expires at the close protects nothing."""
        cli.stock_order(self.client(), "sell", "ANT", 10, limit=None, stop=70.0)
        assert "This stop lasts for today only. Add --tif gtc" in capsys.readouterr().out

    def test_a_code_without_the_stop_will_not_place_the_stop_order(self, capsys):
        client = self.client()
        cli.stock_order(client, "sell", "ANT", 10, limit=69.0)
        plain = code_from(capsys.readouterr().out)

        assert cli.stock_order(client, "sell", "ANT", 10, limit=69.0, stop=70.0,
                               confirm=plain, settle_seconds=0) == 2
        assert client.writes == []

    def test_an_ordinary_order_sends_no_stop(self, capsys):
        client = self.client()
        cli.stock_order(client, "sell", "ANT", 10, limit=85.0)
        cli.stock_order(client, "sell", "ANT", 10, limit=85.0,
                        confirm=code_from(capsys.readouterr().out), settle_seconds=0)

        assert "stop_price" not in client.writes[0][3]


# ── Research, money and watchlists ───────────────────────────────────


class ResearchClient(FakeClient):
    def get_earnings(self, symbol, lookahead_days=14):
        self.calls.append(("get_earnings", symbol, lookahead_days))
        if symbol == "AAPL":
            return Earnings("AAPL", "2027-01-28", timing="pm", eps_estimate=2.92)
        return None

    def get_ratings(self, symbol):
        return Rating(symbol, num_buy=29, num_hold=13, num_sell=7,
                      published_at="2026-11-07T01:49:36Z", price_target_high=425.0,
                      price_target_low=250.0, price_target_mean=348.5199)

    def get_news(self, symbol):
        return [
            NewsArticle(title=f"Headline {n}", source="Zacks", url=f"https://example.com/{n}",
                        published_at="2026-11-24T21:08:30Z")
            for n in range(1, 9)
        ]

    def get_movers(self, direction="up"):
        self.calls.append(("get_movers", direction))
        return [Mover("ADI", price_change=-65.14, price_change_pct=-17.2, price=313.59),
                Mover("OLD", price_change=None, price_change_pct=-1.5)]

    def get_stock_historicals(self, symbol, interval="day", span="year"):
        self.calls.append(("get_stock_historicals", symbol, interval, span))
        return [
            Candle(symbol, "2026-11-17T00:00:00Z", 352.83, 351.91, 355.36, 349.67, 37407537),
            Candle(symbol, "2026-11-23T00:00:00Z", 347.87, 349.08, 352.60, 345.44, 58588703),
        ]

    DIVIDENDS = [
        Dividend("KO", 4.85, 0.485, "2026-10-01", "2026-09-15", "paid"),
        Dividend("KO", 4.85, 0.485, "2027-01-02", "2026-12-15", "pending"),
        Dividend("T", 2.78, 0.2775, "2026-11-02", "2026-10-10", "paid"),
    ]

    def get_dividends(self):
        return list(self.DIVIDENDS)

    def get_dividends_by_symbol(self, symbol):
        return [d for d in self.DIVIDENDS if d.symbol == symbol]

    TRANSFERS = [
        # A deposit, as Robinhood records one: the Robinhood account 'pulls'
        # from the bank, so the bank is the receiving end of the request.
        UnifiedTransfer("t1", 500.0, direction="pull", transfer_type="originated_ach",
                        state="completed", description=None,
                        originating_account_id="acct-1",
                        originating_account_type="rhs_account",
                        receiving_account_id="bank-1",
                        receiving_account_type="ach_relationship",
                        created_at="2024-12-29T10:00:00Z", completed_at=None),
        UnifiedTransfer("t2", 7000.0, direction="push", transfer_type="internal",
                        state="completed", description="IRA Contribution",
                        originating_account_id="acct-1",
                        originating_account_type="rhs_account",
                        receiving_account_id="acct-2",
                        receiving_account_type="rhs_roth_ira",
                        created_at="2026-03-23T10:00:00Z", completed_at=None),
    ]
    banks_fail = False

    def get_unified_transfers(self):
        return list(self.TRANSFERS)

    def get_bank_accounts(self):
        if self.banks_fail:
            raise APIError("no banks today")
        return [BankAccount("bank-1", "Pat Example", "savings", "Rainy day", "approved",
                            "https://api.robinhood.com/ach/relationships/bank-1/",
                            last_four="1234")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lists = {"My First List": ["AAPL", "F"], "Empty": []}
        self.stuck = set()

    def get_watchlists(self):
        return [Watchlist(name, list(symbols), id=name) for name, symbols in self.lists.items()]

    def get_watchlist(self, name="My First List"):
        return Watchlist(name, list(self.lists[name]), id=name)

    def add_to_watchlist(self, symbols, name="My First List"):
        self.calls.append(("add_to_watchlist", symbols, name))
        self.lists[name] += [s for s in symbols if s not in self.stuck]

    def remove_from_watchlist(self, symbols, name="My First List"):
        self.calls.append(("remove_from_watchlist", symbols, name))
        self.lists[name] = [s for s in self.lists[name] if s not in symbols]


class TestResearch:
    def test_earnings(self, capsys):
        client = ResearchClient()

        cli.earnings(client, ["aapl", "NVDA"], days=30)

        rows = capsys.readouterr().out.splitlines()
        assert rows[1].split() == ["AAPL", "2027-01-28", "after", "the", "close", "2.92", "-"]
        assert rows[2].startswith("NVDA    none in the next 30 days")
        assert ("get_earnings", "AAPL", 30) in client.calls

    def test_ratings_show_counts_and_price_targets(self, capsys):
        cli.ratings(ResearchClient(), ["AAPL"])

        assert capsys.readouterr().out.splitlines()[1].split() == [
            "AAPL", "29", "13", "7", "59%", "$250.00", "$348.52", "$425.00",
        ]

    def test_news_is_cut_to_the_count_with_local_times(self, capsys):
        cli.news(ResearchClient(), "AAPL", count=2)

        out = capsys.readouterr().out
        assert out.count("Headline") == 2
        assert "2026-11-24 16:08 EST  Zacks" in out
        assert "https://example.com/1" in out

    def test_movers(self, capsys):
        client = ResearchClient()

        cli.movers(client, down=True)

        rows = capsys.readouterr().out.splitlines()
        assert rows[0] == "S&P 500, biggest moves down today"
        assert rows[2].split() == ["ADI", "$313.59", "-$65.14", "-17.20%"]
        assert rows[3].split() == ["OLD", "-", "-", "-1.50%"]  # no price sent
        assert client.calls == [("get_movers", "down")]

    @pytest.mark.parametrize(("span", "interval"), [
        ("week", "day"), ("month", "day"), ("3month", "day"), ("year", "week"),
        ("5year", "week"),
    ])
    def test_history_picks_a_row_size_to_suit_the_span(self, span, interval):
        client = ResearchClient()
        cli.history(client, "aapl", span=span)
        assert client.calls == [("get_stock_historicals", "AAPL", interval, span)]

    def test_history_table_and_change_over_the_period(self, capsys):
        cli.history(ResearchClient(), "AAPL", span="week")

        out = capsys.readouterr().out
        assert out.startswith("AAPL, the last week, one row a day")
        assert "2026-11-17  $352.83  $355.36  $349.67  $351.91  37,407,537" in out
        assert "Over the period: $352.83 to $349.08, -1.06%." in out

    def test_dividends_newest_first_with_the_paid_total(self, capsys):
        cli.dividends(ResearchClient())

        rows = capsys.readouterr().out.splitlines()
        assert [row.split()[0] for row in rows[1:4]] == ["2027-01-02", "2026-11-02", "2026-10-01"]
        assert rows[-1] == "Paid in total: $7.63"  # the pending one is not counted

    def test_dividends_for_one_symbol_and_for_none(self, capsys):
        cli.dividends(ResearchClient(), symbol="t")
        assert capsys.readouterr().out.count("2026-") == 1

        cli.dividends(ResearchClient(), symbol="NVDA")
        assert capsys.readouterr().out.strip() == "No dividends for NVDA on record."

    def test_a_transfer_says_what_it_was_and_where_the_money_went(self, capsys):
        """It used to print Robinhood's terms: 'pull', 'rhs_account',
        'ach_relationship'. A deposit read as money leaving."""
        cli.transfers(ResearchClient())

        out = capsys.readouterr().out
        rows = out.splitlines()
        assert rows[0].split() == ["CREATED", "AMOUNT", "WHAT", "FROM", "TO", "STATE",
                                   "TRANSFER", "ID"]
        contribution = [cell.strip() for cell in rows[1].split("  ") if cell.strip()]
        assert contribution == ["2026-03-23", "$7,000.00", "IRA Contribution",
                                "Individual account", "Roth IRA", "completed", "t2"]
        deposit = [cell.strip() for cell in rows[2].split("  ") if cell.strip()]
        assert deposit == ["2024-12-29", "$500.00", "deposit", "Savings …1234 (Rainy day)",
                           "Individual account", "completed", "t1"]
        for term in ("pull", "push", "rhs_", "ach_relationship", "originated_ach"):
            assert term not in out

    def test_a_withdrawal_goes_from_robinhood_to_the_bank(self):
        withdrawal = UnifiedTransfer(
            "t3", 50.0, direction="push", transfer_type="originated_ach", state="pending",
            originating_account_id="acct-1", originating_account_type="rhs_account",
            receiving_account_id="bank-9", receiving_account_type="ach_relationship",
        )

        assert cli.transfer_route(withdrawal, {}) == ("withdrawal", "Individual account", "Bank")

    def test_a_direction_never_seen_is_shown_as_sent_with_no_guess(self):
        odd = UnifiedTransfer(
            "t4", 50.0, direction="sweep", originating_account_type="rhs_account",
            receiving_account_type="ach_relationship",
        )

        assert cli.transfer_route(odd, {}) == ("sweep", None, None)

    def test_an_account_type_never_seen_is_still_readable(self):
        odd = UnifiedTransfer(
            "t5", 50.0, direction="push", originating_account_type="rhs_account",
            receiving_account_type="rhs_joint_account",
        )

        assert cli.transfer_route(odd, {})[2] == "Joint account"

    def test_a_pending_bank_transfer_shows_how_to_cancel_it(self, capsys):
        client = ResearchClient()
        client.TRANSFERS = [UnifiedTransfer(
            "t6", 1.0, direction="pull", transfer_type="originated_ach", state="pending",
            originating_account_id="acct-1", originating_account_type="rhs_account",
            receiving_account_id="bank-1", receiving_account_type="ach_relationship",
            created_at="2026-11-24T21:35:00-05:00",
        )]

        cli.transfers(client)

        out = capsys.readouterr().out
        assert out.splitlines()[1].split()[-2:] == ["pending", "t6"]
        assert "cancel-transfer TRANSFER_ID" in out

    def test_nothing_pending_means_no_cancel_hint(self, capsys):
        cli.transfers(ResearchClient())

        assert "cancel-transfer" not in capsys.readouterr().out

    def test_the_table_survives_the_bank_list_failing(self, capsys):
        client = ResearchClient()
        client.banks_fail = True

        assert cli.transfers(client) == 0

        assert "deposit" in capsys.readouterr().out

    def test_every_new_command_has_json(self, capsys):
        client = ResearchClient()
        for command, args in (
            (cli.earnings, (["AAPL"],)), (cli.ratings, (["AAPL"],)), (cli.news, ("AAPL",)),
            (cli.movers, ()), (cli.history, ("AAPL",)), (cli.dividends, ()),
            (cli.transfers, ()), (cli.watchlists, ()),
        ):
            assert command(client, *args, as_json_output=True) == 0
            json.loads(capsys.readouterr().out)


class TestWatchlists:
    def test_watchlists_are_listed_with_their_symbols(self, capsys):
        cli.watchlists(ResearchClient())

        out = capsys.readouterr().out
        assert "My First List (2 symbols)\n  AAPL, F" in out
        assert "Empty (0 symbols)" in out

    def test_watch_adds_and_confirms_by_reading_back(self, capsys):
        client = ResearchClient()

        assert cli.watch(client, ["gm", "ko"]) == 0

        assert ("add_to_watchlist", ["GM", "KO"], "My First List") in client.calls
        assert capsys.readouterr().out.strip() == "Added GM, KO to 'My First List'."

    def test_unwatch_removes(self, capsys):
        client = ResearchClient()

        assert cli.watch(client, ["F"], remove=True) == 0

        assert client.lists["My First List"] == ["AAPL"]
        assert capsys.readouterr().out.strip() == "Removed F from 'My First List'."

    def test_a_symbol_that_did_not_take_is_reported(self, capsys):
        client = ResearchClient()
        client.stuck = {"GM"}

        assert cli.watch(client, ["GM", "KO"]) == 1

        captured = capsys.readouterr()
        assert "Added KO to 'My First List'." in captured.out
        assert "GM is not on 'My First List' after the request." in captured.err


class TestTable:
    def test_a_missing_value_prints_as_a_dash(self):
        assert cli.table(["A", "B"], [["x", None], ["", "y"]]).splitlines() == [
            "A  B", "x  -", "-  y",
        ]


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
    # Written for the default settings, whatever this computer has saved:
    # this runs while tests are collected, before any fixture.
    text = guide._for_setting(guide.COMMANDS, Settings())
    section = text[text.index("PLACING ORDERS ("):text.index("ANYTHING ELSE")]
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

    assert args.command in COMMANDS_IN_THE_GUIDE


COMMANDS_IN_THE_GUIDE = {
    "spread", "banks", "deposit", "withdraw", "cancel-transfer", "documents", "document",
    "accounts", "positions", "orders", "buying-power", "quote", "options", "earnings",
    "ratings", "news", "movers", "history", "dividends", "transfers", "watchlists", "watch",
    "unwatch", "buy", "sell", "buy-option", "sell-option", "cancel", "crypto", "futures",
}


def test_the_guide_mentions_every_account_command():
    """A command an agent is never told about is one it will not use."""
    named = {shlex.split(line)[1] for line in guide_command_lines()}
    assert COMMANDS_IN_THE_GUIDE - named == set()
