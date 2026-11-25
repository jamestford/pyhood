"""Spreads and bank transfers: `pyhood spread`, `banks`, `deposit`,
`withdraw` and `cancel-transfer`."""

import argparse

import pytest

from pyhood import cli, cli_spreads, cli_transfers, onboarding
from pyhood.exceptions import APIError, OrderError
from pyhood.models import ACHTransfer, BankAccount, OptionContract, OptionsChain, Order, Quote


@pytest.fixture(autouse=True)
def on_the_path(monkeypatch):
    for module in (cli, cli_spreads, cli_transfers):
        monkeypatch.setattr(module, "program", lambda: "pyhood")


def code_from(output):
    return output.split("--confirm ")[-1].split()[0]


# ── Spreads ──────────────────────────────────────────────────────────


def contract(strike, kind, mark):
    return OptionContract("F", kind, strike, "2026-12-11", mark,
                          bid=round(mark - 0.02, 2), ask=round(mark + 0.02, 2))


class SpreadClient:
    MARKS = {12.0: 0.31, 12.5: 0.13, 13.0: 0.04}

    def __init__(self, buying_power=500.0, reject=None):
        self.buying_power, self.reject = buying_power, reject
        self.writes, self.reads = [], []

    def get_all_accounts(self):
        return [{"account_number": "111122223", "brokerage_account_type": "individual"},
                {"account_number": "444455556", "brokerage_account_type": "ira_roth"}]

    def get_options_expirations(self, symbol):
        self.reads.append("expirations")
        return ["2026-12-04", "2026-12-11", "2026-12-18"]

    def get_options_chain(self, symbol, expiration, option_type=None):
        self.reads.append("chain")
        return OptionsChain(
            symbol, expiration,
            calls=[contract(k, "call", m) for k, m in self.MARKS.items()],
            puts=[contract(k, "put", m) for k, m in self.MARKS.items()],
        )

    def get_quote(self, symbol):
        return Quote(symbol, 11.95, 11.65, 2.58)

    def get_buying_power(self, account_number=None):
        return self.buying_power

    def is_market_open(self):
        return True

    def order_option_spread(self, symbol, quantity, price, legs, **kwargs):
        self.writes.append((symbol, quantity, price, legs, kwargs))
        if self.reject:
            raise OrderError(self.reject)
        return Order("spread-1", symbol, "buy", "limit", quantity, price, "queued",
                     instrument_type="option", leg_count=len(legs))

    def get_order(self, order_id):
        return Order(order_id, "F", "buy", "limit", 1.0, 0.2, "queued",
                     instrument_type="option", leg_count=2)


def legs(*texts):
    return [cli_spreads.leg(t) for t in texts]


DEBIT_SPREAD = dict(symbol="F", expires="2026-12-11", legs=None, contracts=1, debit=0.25)


class TestLegs:
    def test_a_leg_is_side_type_strike(self):
        assert cli_spreads.leg("buy:call:350") == {
            "side": "buy", "option_type": "call", "strike": 350.0, "expiration": None,
        }
        assert cli_spreads.leg("SELL:PUT:12.5:2026-12-18")["expiration"] == "2026-12-18"

    @pytest.mark.parametrize("text", [
        "buy:call", "hold:call:350", "buy:straddle:350", "buy:call:abc", "buy:call:0",
        "buy:call:350:12/18/2026", "buy call 350",
    ])
    def test_a_malformed_leg_is_refused(self, text):
        with pytest.raises(argparse.ArgumentTypeError):
            cli_spreads.leg(text)


class TestSpread:
    def order(self, **changes):
        return {**DEBIT_SPREAD, "legs": legs("buy:call:12", "sell:call:13"), **changes}

    def test_without_a_code_it_previews_and_sends_nothing(self, capsys):
        client = SpreadClient()

        assert cli_spreads.spread(client, **self.order()) == 0

        out = capsys.readouterr().out
        assert client.writes == []
        assert "Open 1 F spread for a debit of $0.25 per share, good for day" in out
        assert "buy  $12.00 call 2026-12-11   mark $0.31 (bid $0.29, ask $0.33)" in out
        assert "sell $13.00 call 2026-12-11   mark $0.04 (bid $0.02, ask $0.06)" in out
        assert "Estimated cost:     $25.00 (1 spread x 100 shares x $0.25)" in out
        # Bought at 0.31 and sold at 0.04: 0.27. To trade at once, pay the
        # ask of one and take the bid of the other: 0.33 less 0.02.
        assert "about $0.27 debit at the marks, $0.31 debit to trade at once" in out
        assert (
            "pyhood spread F --expires 2026-12-11 --leg buy:call:12 --leg sell:call:13 "
            f"--contracts 1 --debit 0.25 --confirm {code_from(out)}"
        ) in out

    def test_the_printed_command_places_exactly_the_previewed_spread(self, capsys):
        client = SpreadClient()
        cli_spreads.spread(client, **self.order())
        code = code_from(capsys.readouterr().out)

        assert cli_spreads.spread(client, **self.order(), confirm=code, settle_seconds=0) == 0

        symbol, quantity, price, sent_legs, kwargs = client.writes[0]
        assert (symbol, quantity, price) == ("F", 1, 0.25)
        assert kwargs == {"direction": "debit", "time_in_force": "gfd"}
        assert sent_legs == [
            {"strike": 12.0, "expiration": "2026-12-11", "option_type": "call", "side": "buy",
             "effect": "open"},
            {"strike": 13.0, "expiration": "2026-12-11", "option_type": "call",
             "side": "sell", "effect": "open"},
        ]
        assert capsys.readouterr().out.startswith("PLACED: Open 1 F spread")

    @pytest.mark.parametrize("changes", [
        {"contracts": 10},
        {"debit": 2.5},
        {"debit": None, "credit": 0.25},
        {"legs": legs("buy:call:12", "sell:call:12.5")},
        {"legs": legs("sell:call:12", "buy:call:13")},
        {"legs": legs("buy:put:12", "sell:put:13")},
        {"expires": "2026-12-18"},
        {"effect": "close"},
        {"account": "roth"},
        {"time_in_force": "gtc"},
    ])
    def test_a_code_for_one_spread_will_not_place_another(self, capsys, changes):
        client = SpreadClient()
        cli_spreads.spread(client, **self.order())
        code = code_from(capsys.readouterr().out)
        client.reads.clear()

        result = cli_spreads.spread(client, **self.order(**changes), confirm=code,
                                    settle_seconds=0)

        assert result == 2
        assert client.writes == [] and client.reads == []

    def test_legs_in_another_order_are_the_same_spread(self, capsys):
        client = SpreadClient()
        cli_spreads.spread(client, **self.order())
        code = code_from(capsys.readouterr().out)

        swapped = self.order(legs=legs("sell:call:13", "buy:call:12"))
        assert cli_spreads.spread(client, **swapped, confirm=code, settle_seconds=0) == 0

    def test_legs_the_wrong_way_round_are_pointed_out(self, capsys):
        """Sell the dear one and buy the cheap one, and a debit spread is a
        credit spread. That is the mistake to catch."""
        cli_spreads.spread(SpreadClient(), **self.order(legs=legs("sell:call:12", "buy:call:13")))

        out = capsys.readouterr().out
        assert "about $0.27 credit at the marks" in out
        assert "At current prices this spread is a credit, not a debit" in out

    def test_a_price_far_from_the_marks_is_pointed_out(self, capsys):
        cli_spreads.spread(SpreadClient(buying_power=99999.0), **self.order(debit=25.0))
        assert "9159% above the spread's price at the marks, $0.27" in capsys.readouterr().out

    def test_a_credit_spread(self, capsys):
        order = self.order(legs=legs("sell:put:12.5", "buy:put:12"), debit=None, credit=0.10)
        order["legs"][0]["strike"], order["legs"][1]["strike"] = 12.0, 12.5
        client = SpreadClient()
        client.MARKS = {12.0: 0.31, 12.5: 0.13}

        cli_spreads.spread(client, **order)

        out = capsys.readouterr().out
        assert "for a credit of $0.10 per share" in out
        assert "Estimated credit:   $10.00" in out
        assert "Buying power" not in out
        assert out.splitlines()[-1].split(" --confirm ")[0].endswith("--credit 0.1")

    def test_a_leg_with_its_own_expiration(self, capsys):
        order = self.order(legs=legs("buy:call:12:2026-12-18", "sell:call:12"))

        cli_spreads.spread(SpreadClient(), **order)

        out = capsys.readouterr().out
        assert "buy  $12.00 call 2026-12-18" in out and "sell $12.00 call 2026-12-11" in out
        assert "--leg buy:call:12:2026-12-18 --leg sell:call:12 " in out

    def test_a_contract_that_does_not_exist_gives_no_code(self, capsys):
        client = SpreadClient()

        assert cli_spreads.spread(client, **self.order(legs=legs("buy:call:12",
                                                                 "sell:call:12.34"))) == 1

        captured = capsys.readouterr()
        assert "F has no $12.34 call expiring 2026-12-11." in captured.err
        assert "--confirm" not in captured.out

    @pytest.mark.parametrize(("changes", "message"), [
        ({"legs": legs("buy:call:12")}, "two to four legs"),
        ({"legs": legs(*["buy:call:12"] * 5)}, "two to four legs"),
        ({"legs": legs("buy:call:12", "sell:call:12")}, "same contract"),
        ({"debit": None}, "--debit PRICE or --credit PRICE"),
        ({"credit": 0.1}, "--debit PRICE or --credit PRICE"),
    ])
    def test_what_is_not_a_spread(self, changes, message):
        with pytest.raises(cli.UsageError, match=message):
            cli_spreads.spread(SpreadClient(), **self.order(**changes))

    def test_a_rejected_spread_reports_robinhoods_reason(self, capsys):
        client = SpreadClient(reject="Spread order failed: not approved for spreads")
        cli_spreads.spread(client, **self.order())
        code = code_from(capsys.readouterr().out)

        assert cli_spreads.spread(client, **self.order(), confirm=code, settle_seconds=0) == 1
        assert "not approved for spreads" in capsys.readouterr().err


# ── Bank transfers ───────────────────────────────────────────────────


SAVINGS = BankAccount("bank-1", "Pat Example", "savings", "Rainy day", "approved",
                      "https://api.robinhood.com/ach/relationships/bank-1/", last_four="1234")
CHECKING = BankAccount("bank-2", "Pat Example", "checking", "Bills", "approved",
                       "https://api.robinhood.com/ach/relationships/bank-2/", last_four="9876")
PENDING = BankAccount("bank-3", "Pat Example", "checking", "New", "pending",
                      "https://api.robinhood.com/ach/relationships/bank-3/", last_four="5555")


class BankClient:
    def __init__(self, banks=(SAVINGS,), withdrawable="168.85", reject=None, transfers=()):
        self.banks, self.withdrawable, self.reject = list(banks), withdrawable, reject
        self.transfers = {t.id: t for t in transfers}
        self.writes = []
        self.reads = []

    def get_bank_accounts(self):
        self.reads.append("banks")
        return self.banks

    def get_all_accounts(self):
        return [{"account_number": "111122223",
                 "withdrawable_cash": {"amount": self.withdrawable, "currency_code": "USD"}}]

    def initiate_transfer(self, amount, direction, url):
        self.writes.append((amount, direction, url))
        if self.reject:
            raise APIError(self.reject)
        return ACHTransfer("xfer-1", amount, direction, "pending",
                           created_at="2026-11-24T22:00:00Z",
                           expected_landing_date="2026-11-30")

    def get_transfers(self):
        return list(self.transfers.values())

    def cancel_transfer(self, transfer_id):
        self.writes.append(("cancel", transfer_id))
        old = self.transfers[transfer_id]
        self.transfers[transfer_id] = ACHTransfer(
            old.id, old.amount, old.direction, "cancelled", created_at=old.created_at,
        )
        return {}


class TestBanks:
    def test_listed_by_nickname_with_only_the_last_four_digits(self, capsys):
        cli_transfers.banks(BankClient(banks=[SAVINGS, PENDING]))

        rows = capsys.readouterr().out.splitlines()
        assert rows[1].split() == ["Rainy", "day", "savings", "1234", "approved"]
        assert rows[2].split()[-1] == "pending"

    def test_the_only_bank_needs_no_naming(self):
        assert cli_transfers.find_bank(BankClient(), None) is SAVINGS

    @pytest.mark.parametrize(("selector", "bank"), [
        ("savings", SAVINGS), ("rainy", SAVINGS), ("1234", SAVINGS), ("Bills", CHECKING),
        ("9876", CHECKING),
    ])
    def test_one_of_several_is_picked_by_name_type_or_digits(self, selector, bank):
        assert cli_transfers.find_bank(BankClient(banks=[SAVINGS, CHECKING]), selector) is bank

    def test_with_several_banks_one_must_be_named(self):
        with pytest.raises(cli.UsageError, match="Say which bank with --bank"):
            cli_transfers.find_bank(BankClient(banks=[SAVINGS, CHECKING]), None)

    def test_a_bank_that_is_not_approved_cannot_be_used(self):
        with pytest.raises(cli.UsageError, match="No bank matches 'new'"):
            cli_transfers.find_bank(BankClient(banks=[SAVINGS, PENDING]), "new")
        with pytest.raises(cli.UsageError, match="No approved bank account"):
            cli_transfers.find_bank(BankClient(banks=[PENDING]), None)

    def test_a_selector_fitting_two_banks_is_refused(self):
        both = BankClient(banks=[SAVINGS, CHECKING])
        with pytest.raises(cli.UsageError, match="More than one bank matches"):
            cli_transfers.find_bank(both, "i")  # in 'savings' and in 'Bills'


class TestTransfer:
    def test_a_withdrawal_previews_and_sends_nothing(self, capsys):
        client = BankClient()

        assert cli_transfers.transfer(client, "withdraw", 50.0) == 0

        out = capsys.readouterr().out
        assert client.writes == []
        assert out.startswith("NOT SENT. This transfer needs your confirmation.")
        assert "Withdraw $50.00 from Robinhood to Savings …1234 (Rainy day)" in out
        assert "Withdrawable cash:  $168.85" in out
        assert "more than your withdrawable cash" not in out
        assert f"pyhood withdraw 50 --confirm {code_from(out)}" in out

    def test_the_printed_command_makes_exactly_that_transfer(self, capsys):
        client = BankClient()
        cli_transfers.transfer(client, "withdraw", 50.0)
        code = code_from(capsys.readouterr().out)

        assert cli_transfers.transfer(client, "withdraw", 50.0, confirm=code) == 0

        assert client.writes == [(50.0, "withdraw", SAVINGS.url)]
        out = capsys.readouterr().out
        assert out.startswith("SENT: Withdraw $50.00 from Robinhood to Savings …1234")
        assert "Expected by:  2026-11-30" in out
        assert "pyhood cancel-transfer xfer-1" in out

    @pytest.mark.parametrize(("direction", "amount", "bank"), [
        ("withdraw", 500.0, None),      # ten times the amount
        ("deposit", 50.0, None),        # the other way
        ("withdraw", 50.0, "bills"),    # another bank
        ("withdraw", 50.01, None),
    ])
    def test_a_code_for_one_transfer_will_not_make_another(self, capsys, direction, amount,
                                                           bank):
        client = BankClient(banks=[SAVINGS, CHECKING])
        cli_transfers.transfer(client, "withdraw", 50.0, bank="savings")
        code = code_from(capsys.readouterr().out)

        result = cli_transfers.transfer(client, direction, amount, bank=bank or "savings",
                                        confirm=code)

        assert result == 2
        assert client.writes == []

    def test_more_than_withdrawable_is_pointed_out(self, capsys):
        cli_transfers.transfer(BankClient(), "withdraw", 5000.0)
        assert "more than your withdrawable cash" in capsys.readouterr().out

    def test_a_large_amount_is_printed_in_full(self, capsys):
        cli_transfers.transfer(BankClient(), "withdraw", 5000000.0)
        assert "pyhood withdraw 5000000 --confirm" in capsys.readouterr().out

    def test_a_deposit_says_where_the_money_comes_from(self, capsys):
        cli_transfers.transfer(BankClient(), "deposit", 25.0)

        out = capsys.readouterr().out
        assert "Deposit $25.00 from Savings …1234 (Rainy day) into Robinhood" in out
        assert "takes this from your bank account" in out
        assert "Withdrawable" not in out

    def test_fractions_of_a_cent_are_refused(self):
        with pytest.raises(cli.UsageError, match="more than two decimal places"):
            cli_transfers.transfer(BankClient(), "withdraw", 50.005)

    def test_a_rejected_transfer_reports_robinhoods_reason(self, capsys):
        client = BankClient(reject="Insufficient funds")
        cli_transfers.transfer(client, "withdraw", 50.0)
        code = code_from(capsys.readouterr().out)

        assert cli_transfers.transfer(client, "withdraw", 50.0, confirm=code) == 1
        assert "Insufficient funds" in capsys.readouterr().err


class TestCancelTransfer:
    PENDING = ACHTransfer("xfer-1", 50.0, "withdraw", "pending",
                          created_at="2026-11-24T22:00:00Z")

    def test_a_pending_transfer_is_cancelled_at_once(self, capsys):
        client = BankClient(transfers=[self.PENDING])

        assert cli_transfers.cancel_transfer(client, "xfer-1") == 0

        assert client.writes == [("cancel", "xfer-1")]
        assert capsys.readouterr().out.startswith(
            "CANCELLED: withdraw of $50.00, created 2026-11-24"
        )

    def test_a_finished_transfer_is_left_alone(self, capsys):
        done = ACHTransfer("xfer-1", 50.0, "deposit", "completed",
                           created_at="2026-11-01T00:00:00Z")
        client = BankClient(transfers=[done])

        assert cli_transfers.cancel_transfer(client, "xfer-1") == 1
        assert client.writes == []
        assert "already completed" in capsys.readouterr().out

    def test_an_unknown_id_is_refused(self):
        with pytest.raises(cli.UsageError, match="No transfer has the ID nope"):
            cli_transfers.cancel_transfer(BankClient(), "nope")


class TestCommandLine:
    def test_spread(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main([
            "spread", "F", "--expires", "2026-12-11", "--leg", "buy:call:12", "--leg",
            "sell:call:13", "--contracts", "2", "--debit", "0.25", "--account", "roth",
        ])

        command, kwargs = seen[0]
        assert command is cli.place_or_ask
        assert kwargs == {
            "order_command": cli_spreads.spread, "ask": False,
            "symbol": "F", "expires": "2026-12-11", "contracts": 2, "debit": 0.25,
            "credit": None, "effect": "open", "time_in_force": "gfd", "account": "roth",
            "confirm": None, "legs": legs("buy:call:12", "sell:call:13"),
        }

    @pytest.mark.parametrize(("argv", "command", "kwargs"), [
        (["banks"], cli_transfers.banks, {"as_json_output": False}),
        (["withdraw", "50"], cli_transfers.transfer,
         {"direction": "withdraw", "amount": 50.0, "bank": None, "confirm": None}),
        (["deposit", "25.50", "--bank", "savings", "--confirm", "abc123"],
         cli_transfers.transfer,
         {"direction": "deposit", "amount": 25.5, "bank": "savings", "confirm": "abc123"}),
        (["cancel-transfer", "xfer-1"], cli_transfers.cancel_transfer,
         {"transfer_id": "xfer-1"}),
    ])
    def test_transfers(self, monkeypatch, argv, command, kwargs):
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        assert onboarding.main(argv) == 0
        assert seen == [(command, kwargs)]

    @pytest.mark.parametrize("argv", [
        ["withdraw"], ["withdraw", "0"], ["withdraw", "-5"], ["deposit", "lots"],
        ["spread", "F", "--expires", "2026-12-11", "--leg", "buy:call:12", "--contracts", "1"],
        ["spread", "F", "--leg", "buy:call:12", "--leg", "sell:call:13", "--contracts", "1",
         "--debit", "0.2"],
        ["spread", "F", "--expires", "2026-12-11", "--leg", "buy:call", "--leg",
         "sell:call:13", "--contracts", "1", "--debit", "0.2"],
        ["spread", "F", "--expires", "2026-12-11", "--leg", "buy:call:12", "--leg",
         "sell:call:13", "--contracts", "1", "--debit", "0.2", "--credit", "0.2"],
    ])
    def test_incomplete_commands_are_refused(self, argv):
        with pytest.raises(SystemExit) as stop:
            onboarding.main(argv)
        assert stop.value.code == 2
