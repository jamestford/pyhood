"""The confirmation setting: whether an order asks before it is placed.

On, the default, every order takes two steps. Off, an order is sent at
once unless it is worth more than an amount the user sets. Only a person
at a terminal can loosen it.
"""

import json

import pytest

from pyhood import cli, guide, onboarding, settings
from pyhood.settings import Settings
from tests.test_cli import OrderClient


def turn_off(above=5000.0):
    settings.save(Settings(confirmation=False, above=above))


# ── The saved setting ────────────────────────────────────────────────


class TestSettings:
    def test_with_nothing_saved_every_order_asks(self):
        chosen = settings.load()

        assert chosen == Settings(confirmation=True, above=5000.0)
        assert chosen.asks(1.0)

    def test_what_is_saved_is_read_back_and_only_the_user_can_read_the_file(self, own_settings):
        turn_off(above=250.0)

        assert settings.load() == Settings(confirmation=False, above=250.0)
        assert own_settings.stat().st_mode & 0o777 == 0o600

    @pytest.mark.parametrize("content", [
        "", "not json", "[]", '{"confirmation": "off"}', '{"confirmation": 0}',
        '{"confirmation": null}', '{"confirm_above": 100}',
    ])
    def test_a_file_that_does_not_plainly_say_off_leaves_confirmation_on(
        self, own_settings, content,
    ):
        """A damaged or hand-edited file must never be what turns it off."""
        own_settings.write_text(content)

        assert settings.load().confirmation is True

    @pytest.mark.parametrize("amount", ["-1", '"5000"', "true", "null"])
    def test_an_amount_that_is_not_a_number_falls_back_to_the_default(
        self, own_settings, amount,
    ):
        own_settings.write_text(f'{{"confirmation": false, "confirm_above": {amount}}}')

        assert settings.load().above == 5000.0

    def test_off_asks_only_above_the_amount(self):
        chosen = Settings(confirmation=False, above=5000.0)

        assert not chosen.asks(4999.99)
        assert not chosen.asks(5000.0)  # 'above' means more than
        assert chosen.asks(5000.01)

    def test_an_order_whose_worth_is_unknown_asks(self):
        assert Settings(confirmation=False).asks(None)


# ── Placing orders under each setting ────────────────────────────────


class TestConfirmationOn:
    def test_an_order_asks_and_sends_nothing(self, capsys):
        client = OrderClient()

        assert cli.place_or_ask(client, cli.stock_order, side="buy", symbol="AAPL",
                                quantity=10, limit=350.0) == 0

        assert client.writes == []
        out = capsys.readouterr().out
        assert out.startswith("NOT PLACED. This order needs your confirmation.")
        assert "--confirm" in out


class TestConfirmationOff:
    def test_an_order_under_the_amount_is_sent_at_once(self, capsys):
        turn_off()
        client = OrderClient()

        assert cli.place_or_ask(client, cli.stock_order, side="buy", symbol="AAPL",
                                quantity=10, limit=350.0, settle_seconds=0) == 0

        assert [(w[0], w[1], w[2]) for w in client.writes] == [("buy", "AAPL", 10)]
        out = capsys.readouterr().out
        assert out.startswith(
            "Confirmation is off and this order is not above $5,000.00, so it is sent at once."
        )
        assert "PLACED: Buy 10 AAPL, limit $350.00, good for day" in out
        assert "NOT PLACED" not in out
        assert "--confirm" not in out

    def test_it_still_shows_what_the_order_is_and_any_warning(self, capsys):
        """The checks are the same ones the step that asks would show."""
        turn_off()
        client = OrderClient(buying_power=100.0)

        cli.place_or_ask(client, cli.stock_order, side="buy", symbol="AAPL", quantity=10,
                         limit=350.0, settle_seconds=0)

        out = capsys.readouterr().out
        assert "Estimated cost:     $3,500.00" in out
        assert "more than your buying power" in out
        assert out.index("more than your buying power") < out.index("PLACED:")

    def test_an_order_above_the_amount_still_asks(self, capsys):
        turn_off(above=1000.0)
        client = OrderClient()

        assert cli.place_or_ask(client, cli.stock_order, side="buy", symbol="AAPL",
                                quantity=10, limit=350.0) == 0

        assert client.writes == []
        out = capsys.readouterr().out
        assert out.startswith("NOT PLACED. This order needs your confirmation.")
        assert "Confirmation is off, but an order above $1,000.00 still asks." in out
        assert "--confirm" in out

    def test_the_code_from_an_order_that_asked_places_it(self, capsys):
        turn_off(above=1000.0)
        client = OrderClient()
        order = dict(side="buy", symbol="AAPL", quantity=10, limit=350.0)
        cli.place_or_ask(client, cli.stock_order, **order)
        code = capsys.readouterr().out.split("--confirm ")[1].split()[0]

        cli.place_or_ask(client, cli.stock_order, confirm=code, settle_seconds=0, **order)

        assert len(client.writes) == 1

    def test_a_sale_is_measured_the_same_way(self, capsys):
        """Selling too much by mistake is as bad as buying too much."""
        turn_off(above=1000.0)
        client = OrderClient()

        cli.place_or_ask(client, cli.stock_order, side="sell", symbol="AAPL", quantity=10,
                         limit=360.0)

        assert client.writes == []
        assert "NOT PLACED" in capsys.readouterr().out

    def test_ask_makes_an_order_ask_whatever_its_size(self, capsys):
        turn_off()
        client = OrderClient()

        cli.place_or_ask(client, cli.stock_order, ask=True, side="buy", symbol="AAPL",
                         quantity=1, limit=350.0)

        assert client.writes == []
        assert capsys.readouterr().out.startswith("NOT PLACED.")

    def test_a_wrong_code_is_still_refused(self, capsys):
        turn_off()
        client = OrderClient()

        assert cli.place_or_ask(client, cli.stock_order, side="buy", symbol="AAPL",
                                quantity=10, limit=350.0, confirm="000000") == 2

        assert client.writes == []

    def test_an_order_robinhood_refuses_is_reported_and_not_called_placed(self, capsys):
        turn_off()
        client = OrderClient(reject="Not enough buying power.")

        assert cli.place_or_ask(client, cli.stock_order, side="buy", symbol="AAPL",
                                quantity=10, limit=350.0, settle_seconds=0) == 1

        captured = capsys.readouterr()
        assert "PLACED:" not in captured.out
        assert "Robinhood did not accept the order" in captured.err

    def test_an_option_order_is_measured_by_its_whole_cost(self, capsys):
        """Two contracts at $30.00 a share is $6,000, not $30."""
        from tests.test_cli import OptionClient

        turn_off()
        client = OptionClient()

        cli.place_or_ask(client, cli.option_order, side="buy", symbol="F",
                         expiration="2026-12-11", strike=12.0, option_type="call",
                         contracts=2, limit=30.0)

        assert client.writes == []
        assert "NOT PLACED" in capsys.readouterr().out


class TestTransfersAlwaysAsk:
    def test_the_command_line_does_not_send_transfers_through_the_setting(self, monkeypatch):
        """Money leaving Robinhood is not an order that can be cancelled."""
        from pyhood import cli_transfers

        turn_off()
        seen = []
        monkeypatch.setattr(cli, "run", lambda fn, **kw: seen.append((fn, kw)) or 0)

        onboarding.main(["withdraw", "500"])

        assert seen[0][0] is cli_transfers.transfer
        with pytest.raises(SystemExit):
            onboarding.build_parser().parse_args(["withdraw", "500", "--ask"])


class TestTheCommandLine:
    @pytest.mark.parametrize("argv", [
        ["buy", "AAPL", "10", "--limit", "350", "--ask"],
        ["buy-option", "F", "--expires", "2026-12-11", "--strike", "12", "--call",
         "--contracts", "1", "--limit", "0.30", "--ask"],
        ["spread", "F", "--expires", "2026-12-11", "--leg", "buy:call:12", "--leg",
         "sell:call:13", "--contracts", "1", "--debit", "0.25", "--ask"],
        ["crypto", "buy", "BTC", "0.001", "--limit", "50000", "--ask"],
    ])
    def test_every_order_command_takes_ask(self, argv):
        assert onboarding.build_parser().parse_args(argv).ask is True


# ── Changing the setting ─────────────────────────────────────────────


def setup(values, answer="yes", at_terminal=True):
    lines = []
    status = onboarding.setup_confirmation(
        values, prompt=lambda _: answer, out=lines.append, at_terminal=lambda: at_terminal,
    )
    return status, "\n".join(lines)


class TestSetupConfirmation:
    def test_with_no_value_it_shows_the_setting_and_changes_nothing(self, own_settings):
        status, out = setup([])

        assert status == 0
        assert out.startswith("Confirmation is on: every order asks first.")
        assert "setup confirmation above AMOUNT" in out
        assert not own_settings.exists()

    def test_a_person_can_turn_it_off_by_typing_yes(self):
        status, out = setup(["off"])

        assert status == 0
        assert settings.load().confirmation is False
        assert "An order worth up to $5,000.00 is sent to Robinhood as soon as" in out
        assert "Confirmation is off." in out

    def test_anything_but_yes_leaves_it_on(self):
        status, out = setup(["off"], answer="y")

        assert status == 1
        assert settings.load().confirmation is True
        assert "Nothing was changed" in out

    def test_an_agent_cannot_turn_it_off(self, own_settings):
        """Run without a person at the terminal, it changes nothing and
        says who has to do it."""
        status, out = setup(["off"], at_terminal=False)

        assert status == 2
        assert not own_settings.exists()
        assert "only a person can loosen it" in out
        assert "If you are an AI agent: do not try another way." in out
        assert "setup confirmation off" in out

    def test_an_agent_cannot_raise_the_amount(self):
        turn_off(above=100.0)

        status, _ = setup(["above", "1000000"], at_terminal=False)

        assert status == 2
        assert settings.load().above == 100.0

    def test_a_person_can_set_the_amount(self):
        status, out = setup(["above", "$2,500"])

        assert status == 0
        assert settings.load() == Settings(confirmation=True, above=2500.0)
        assert "an order above $2,500.00 still asks" in out
        assert "Confirmation is on, so every order asks first for now." in out

    @pytest.mark.parametrize("amount", ["lots", "-5", "nan", "inf"])
    def test_an_amount_that_makes_no_sense_is_refused(self, amount):
        status, out = setup(["above", amount])

        assert status == 2
        assert settings.load().above == 5000.0

    def test_turning_it_back_on_needs_no_person(self):
        """On is the safe direction, so an agent told to may do it."""
        turn_off(above=250.0)

        status, out = setup(["on"], at_terminal=False)

        assert status == 0
        assert settings.load() == Settings(confirmation=True, above=250.0)

    @pytest.mark.parametrize("values", [["maybe"], ["above"], ["off", "now"], ["on", "5"]])
    def test_anything_else_says_what_to_give(self, values, own_settings):
        status, out = setup(values)

        assert status == 2
        assert "Give on, off, or above AMOUNT." in out
        assert not own_settings.exists()

    def test_the_command_line_reaches_it(self, capsys):
        assert onboarding.main(["setup", "confirmation"]) == 0

        assert capsys.readouterr().out.startswith("Confirmation is on")

    def test_run_by_a_test_it_is_not_at_a_terminal_and_refuses(self, capsys):
        """The real check, not a stand-in: pytest's captured output is no terminal."""
        assert onboarding.main(["setup", "confirmation", "off"]) == 2

        assert settings.load().confirmation is True
        assert "Nothing was changed" in capsys.readouterr().out

    def test_setup_reports_the_setting(self):
        turn_off(above=750.0)
        lines = []

        onboarding.print_status(out=lines.append)

        assert "    off: orders are placed at once, except those above $750.00." in lines


# ── What the agent is told ───────────────────────────────────────────


class TestTheGuideFollowsTheSetting:
    def test_on_it_teaches_the_two_steps(self):
        text = guide.render()

        assert "PLACING ORDERS (two steps, every time)" in text
        assert "Never place an order or move money without showing the user" in text
        assert "confirmation off" not in text
        assert "@@" not in text

    def test_off_it_says_orders_are_placed_at_once_and_up_to_how_much(self):
        turn_off(above=2500.0)

        text = guide.render()

        assert "PLACING ORDERS (confirmation is off: one step, up to $2,500)" in text
        assert "This user has turned confirmation off." in text
        assert "An order worth more than $2,500 is not sent." in text
        assert "Add --ask to make any order ask first." in text
        assert "Moving money between the user's bank and Robinhood always asks first" in text
        assert "Never place an order or move money without showing" not in text
        assert "@@" not in text

    @pytest.mark.parametrize("off", [False, True])
    def test_either_way_it_is_short_enough_to_be_read_whole(self, off):
        if off:
            turn_off()

        lines = guide.render().splitlines()

        assert len(lines) <= 150
        placing = next(n for n, line in enumerate(lines) if line.startswith("PLACING ORDERS"))
        assert placing < 40

    def test_the_settings_file_is_plain_json(self, own_settings):
        turn_off(above=2500.0)

        assert json.loads(own_settings.read_text()) == {
            "confirmation": False, "confirm_above": 2500.0,
        }
