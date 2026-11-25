"""The guide `pyhood guide` prints: how to use pyhood, written for an AI agent.

An agent meeting pyhood for the first time needs four things: how to run
it, how to log in, which methods exist, and what the results look like.
Left to find them out, it reads source files, guesses field names and
installs things. This puts the answers in one command.

Only the prose is written by hand. Method signatures and model fields are
read from the code when the guide is printed, so they describe the
installed version and cannot fall out of date.
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
from typing import Any

# Read-only methods worth knowing about, in the order an agent tends to
# need them. Every name is checked against PyhoodClient by the tests.
READ_METHODS: tuple[str, ...] = (
    "get_positions",
    "get_option_positions",
    "get_buying_power",
    "get_all_accounts",
    "get_stock_orders",
    "get_option_orders",
    "get_order",
    "get_quote",
    "get_quotes",
    "get_fundamentals",
    "get_stock_historicals",
    "get_options_expirations",
    "get_options_chain",
    "get_earnings",
    "get_news",
    "get_ratings",
    "get_movers",
    "get_dividends",
    "get_watchlists",
    "get_watchlist",
    "is_market_open",
)

# Methods that place, change or cancel orders, or move money.
WRITE_METHODS: tuple[str, ...] = (
    "buy_stock",
    "sell_stock",
    "buy_option",
    "sell_option",
    "cancel_order",
)

# Models whose fields are listed, by class name in pyhood.models.
MODELS: tuple[str, ...] = (
    "Position",
    "OptionPosition",
    "Order",
    "Quote",
    "OptionContract",
    "OptionsChain",
    "Earnings",
    "Watchlist",
)

COMMANDS = """\
pyhood {version}: a Python client for Robinhood
==============================================

This guide is for an AI agent. It describes the installed version.

RULES
  1. pyhood is installed. Do not install it or its dependencies, and do
     not import it from a source folder.
  2. Never ask for, read or type a password or API key. Login is saved.
@@RULE_THREE@@
  4. Do not guess command, field or method names. The commands are all
     listed below.

@@PLACING_HEAD@@

      pyhood buy AAPL 10 --limit 350
      pyhood sell AAPL 10 --limit 360
      pyhood buy AAPL 10 --market
      pyhood buy AAPL --dollars 50 --market
      pyhood sell AAPL 10 --stop 340 --market --tif gtc
      pyhood sell AAPL 10 --trail-percent 5 --market --tif gtc
      pyhood buy-option AAPL --expires 2026-12-18 --strike 350 --call --contracts 1 --limit 2.50
      pyhood sell-option AAPL --expires 2026-12-18 --strike 350 --call --contracts 1 --limit 3.00
      pyhood spread AAPL --expires 2026-12-18 --leg buy:call:350 --leg sell:call:360 --contracts 1 --debit 2.50
      pyhood crypto buy BTC 0.001 --limit 59000
      pyhood crypto sell BTC 0.001 --market

@@PLACING_STEPS@@
  An order needs --limit PRICE or --market; there is no default.
  Orders are good for the day unless you add --tif gtc.
  --stop PRICE makes a stop order: it waits until the price reaches PRICE,
  then places the --market or --limit order. A stop meant as protection
  needs --tif gtc, or it expires at the end of the day.
  --trail-percent or --trail-amount makes a trailing stop, which follows
  the price that far behind. It is always a --market order.
  Option prices are per share and a contract is 100 shares: --limit 2.50
  on 1 contract is $250. A crypto quantity is in the coin, not dollars:
  0.001 BTC is a thousandth of a bitcoin. Look up real expirations and
  strikes with `pyhood options` first; do not guess them. buy-option opens
  a position and sell-option closes one unless you add --to open or
  --to close.
  --dollars buys or sells an amount of money's worth, as a market order.
  A spread is two to four legs, each SIDE:TYPE:STRIKE, for one net price:
  --debit is the most to pay and --credit the least to accept, per share.

CANCELLING AN ORDER (one step)
      pyhood orders --open        the orders that can still be cancelled, with IDs
      pyhood cancel ORDER_ID      cancels that order at once
      pyhood crypto cancel ORDER_ID    the same for a crypto order; its IDs
                                  are in the crypto orders list
      pyhood cancel-transfer TRANSFER_ID    a bank transfer that is still pending

  There is no first step and no code: the user asking you to cancel is
  the yes. Cancel the order they mean and tell them what the command reported.
  Never cancel an order they did not ask you to cancel.

LOOKING THINGS UP (read-only, nothing to confirm)

    The account
      pyhood accounts             the accounts under this login: individual, IRA
      pyhood positions            what each account holds, with profit and loss
      pyhood orders               orders from the last 30 days, newest first
      pyhood orders --since 2026-01-01    or --all, or --symbol AAPL, or --open
      pyhood buying-power         cash available to trade with, in each account
      pyhood dividends            dividends paid and pending
      pyhood transfers            money moved in, out and between accounts
      pyhood banks                the bank accounts linked for transfers
      pyhood documents            statements, trade confirmations and tax forms
      pyhood document DOCUMENT_ID    save one as a PDF, in a private folder

    The market
      pyhood quote AAPL MSFT      current prices; add --fundamentals for more
      pyhood history AAPL         past prices; --span week, month, 3month, year, 5year
      pyhood options AAPL         the expiration dates of AAPL's options
      pyhood options AAPL --expires 2026-12-18    the contracts for that date
      pyhood earnings AAPL MSFT    when each next reports earnings
      pyhood ratings AAPL         analyst buy, hold and sell counts, price targets
      pyhood news AAPL            recent headlines, with links
      pyhood movers               the S&P 500's biggest rises today; --down for falls

    Crypto (its own login: if it is not set up, tell the user to run
    `pyhood setup crypto` themselves)
      pyhood crypto quote BTC ETH    best bid and ask
      pyhood crypto holdings      the coins held, and crypto buying power
      pyhood crypto orders        crypto orders; --open for those still open

    Futures. Name the product, such as ES for the S&P 500, NQ for the
    Nasdaq, CL for crude oil or GC for gold, and pyhood finds the current
    contract. Do not guess contract codes like ESZ26. pyhood cannot place
    a futures order: buy and sell only estimate one, and the user places
    it in the Robinhood app.
      pyhood futures buy MES 1 --limit 5000    estimate: margin, fees, verdict
      pyhood futures quote ES     last, bid, ask and the session's range
      pyhood futures contract ES    the product's contracts and their dates
      pyhood futures contract ESZ26    what one point and one tick are worth
      pyhood futures orders       futures orders, with realized profit and loss
      pyhood futures positions    open futures positions

    Watchlists
      pyhood watchlists           your watchlists and what is on them
      pyhood watch F GM           add stocks to a watchlist; --list NAME to pick one
      pyhood unwatch F            take stocks off a watchlist

  Each prints a table. Add --json for exact values. Times in the tables
  are local; in --json and in scripts they are UTC.
  positions, orders and buying-power cover every account; add --account
  with part of an account's name from `pyhood accounts`, such as
  --account roth, to see one. An order uses the first account unless it
  names another the same way: buy, sell, buy-option and sell-option all
  take --account. An account spends only its own cash and sells only its
  own holdings: money in an IRA cannot pay for an order in another account.
  watch and unwatch change a watchlist at once. No money is involved, so
  there is nothing to confirm.

ANYTHING ELSE
  The commands above cover most requests. For something they do not, such
  as futures orders or a calculation over several results, write
  a Python script. First run:

      pyhood guide python

  It lists the methods and the fields of what they return.
"""

SCRIPTS = """\
pyhood {version}: writing a script
==================================

For what the commands in `pyhood guide` do not cover. The rules there apply
here too: never ask for a password, and never place an order or move money
without showing the user what will happen and getting a yes.

RUNNING A SCRIPT
  For anything the commands above do not cover, write Python and run it:

      pyhood run script.py

  That uses the Python pyhood is installed in. A bare `python` may be a
  different one that cannot import pyhood. For a one-liner:

      pyhood run -c "import pyhood; print(pyhood.__version__)"

  Other commands:
      pyhood setup      show whether a login is saved
      pyhood verify     read live prices, to prove the login works
      pyhood guide      print this guide

EVERY SCRIPT STARTS WITH

      import pyhood
      from pyhood.client import PyhoodClient

      client = PyhoodClient(pyhood.login())

  pyhood.login() takes no arguments here: it loads the saved login and
  renews it if needed. If it raises AuthError, stop and tell the user to
  run `pyhood setup login` themselves.

EXAMPLE: what do I own, and what did I buy this month?

      for p in client.get_positions():
          print(p.symbol, p.quantity, f"{p.average_cost:.2f}", p.unrealized_pl)

      for o in client.get_stock_orders(start_date="2026-11-01"):
          if not o.filled_quantity:
              continue  # never filled: average_price and filled_at are None
          print(o.created_at, o.side, o.symbol, o.filled_quantity,
                f"{o.average_price:.2f}", o.status)

RESULTS
  Methods return dataclasses, or lists of them. print() one to see every
  field and value.
  None means unknown, not zero. Formatting None fails: f"{x:.2f}" raises
  TypeError when x is None. Check first, as the example does. On an Order,
  average_price and filled_at are None until the order fills.
  Times (created_at, filled_at, timestamp) are UTC, not local time. Call
  .astimezone() on one before showing it to the user.
  Asking for a field that does not exist raises an AttributeError that
  lists the real fields.
"""

OUTRO = """\
MORE
  Details of one method:
      pyhood run -c "from pyhood.client import PyhoodClient; help(PyhoodClient.get_quote)"
  Every method:
      pyhood run -c "from pyhood.client import PyhoodClient; help(PyhoodClient)"
  Crypto uses a separate client: `from pyhood.crypto import CryptoClient`.
  Docs: https://jamestford.github.io/pyhood
"""


def _annotation(value: object) -> str:
    """An annotation as it reads in the source, without quotes."""
    return value if isinstance(value, str) else getattr(value, "__name__", str(value))


def _signature(method_name: str) -> str:
    from pyhood.client import PyhoodClient

    signature = inspect.signature(getattr(PyhoodClient, method_name))
    parameters = []
    for name, parameter in signature.parameters.items():
        if name == "self":
            continue
        text = name
        if parameter.annotation is not parameter.empty:
            text += f": {_annotation(parameter.annotation)}"
        if parameter.default is not parameter.empty:
            text += f" = {parameter.default!r}"
        parameters.append(text)
    arrow = ""
    if signature.return_annotation is not signature.empty:
        arrow = f" -> {_annotation(signature.return_annotation)}"
    return f"client.{method_name}({', '.join(parameters)}){arrow}"


def _summary(method_name: str) -> str:
    from pyhood.client import PyhoodClient

    doc = inspect.getdoc(getattr(PyhoodClient, method_name)) or ""
    return doc.split("\n\n")[0].replace("\n", " ").strip()


def _methods(title: str, names: tuple[str, ...]) -> str:
    lines = [title]
    for name in names:
        lines.append(f"  {_signature(name)}")
        summary = _summary(name)
        if summary:
            lines.append(f"      {summary}")
    return "\n".join(lines) + "\n"


def _models() -> str:
    from pyhood import models

    lines = ["FIELDS"]
    for name in MODELS:
        cls = getattr(models, name)
        fields = ", ".join(f.name for f in dataclasses.fields(cls))
        lines.append(f"  {name}: {fields}")
    return "\n".join(lines) + "\n"


def _path_note() -> str:
    """Say how to run pyhood when the bare command would not reach it."""
    from pyhood.cli import program

    command = program()
    if command == "pyhood":
        return ""
    return (
        "THE COMMAND\n"
        "  `pyhood` on its own does not run this install from here. Wherever\n"
        "  this guide says `pyhood`, type this instead:\n\n"
        f"      {command}\n"
    )


def _with_path_note(text: str, before: str) -> str:
    """Put the note on how to run pyhood ahead of the first command shown."""
    note = _path_note()
    return text.replace(before, f"{note}\n{before}", 1) if note else text


# The parts of the guide that depend on the user's confirmation setting.
RULE_THREE_ON = """\
  3. Never place an order or move money without showing the user exactly
     what will happen first and getting a yes. See PLACING ORDERS. That
     includes deposits and withdrawals.
     Cancel an order only when the user asks you to."""

RULE_THREE_OFF = """\
  3. This user has turned confirmation off. An order worth up to {above}
     is placed as soon as you run it, so run only what the user asked
     for, exactly as they asked, and then tell them what was placed.
     An order above {above}, and any deposit or withdrawal, still asks
     first. See PLACING ORDERS. Only the user can change this setting.
     Cancel an order only when the user asks you to."""

PLACING_HEAD_ON = """\
PLACING ORDERS (two steps, every time)
  Step 1. Run the order with no --confirm. This sends nothing:"""

PLACING_HEAD_OFF = """\
PLACING ORDERS (confirmation is off: one step, up to {above})
  Run the order. It is sent to Robinhood at once:"""

PLACING_STEPS_ON = """\
  Moving money between the user's bank and Robinhood works the same way:

      pyhood withdraw 500
      pyhood deposit 500

  It prints NOT PLACED, then the order, its cost, the current price and
  any problem with it, and ends with the exact command that would place
  it, including a confirmation code.

  Step 2. Show all of that to the user and ask. Only if they say yes, run
  the command it printed, unchanged.

  Do not invent a code and do not change an order after showing it: a
  code works for one exact order on one day, and anything else is refused.
  If the user changes their mind about quantity or price, start again."""

PLACING_STEPS_OFF = """\
  It prints PLACED, the order's status and its ID. Tell the user what was
  placed and anything it warned about. Check the quantity and price
  before you run it: there is no second step to catch a mistake.

  An order worth more than {above} is not sent. It prints NOT PLACED and
  a command with a confirmation code: show that to the user and ask, and
  only on a yes run the command it printed, unchanged.
  Add --ask to make any order ask first. Use it when you are not sure
  what the user wants, or when they say to check with them.

  Moving money between the user's bank and Robinhood always asks first:

      pyhood withdraw 500
      pyhood deposit 500

  Show what it prints to the user, and only on a yes run the command it
  printed, with its code, unchanged."""


def _for_setting(text: str, chosen: Any = None) -> str:
    """Fill in the parts of the guide that follow the confirmation setting.

    `chosen` is the settings to write the guide for; the saved ones if None.
    """
    from pyhood import settings

    chosen = chosen or settings.load()
    on = chosen.confirmation
    above = f"${chosen.above:,.0f}" if chosen.above == int(chosen.above) else (
        f"${chosen.above:,.2f}"
    )
    parts = {
        "@@RULE_THREE@@": RULE_THREE_ON if on else RULE_THREE_OFF,
        "@@PLACING_HEAD@@": PLACING_HEAD_ON if on else PLACING_HEAD_OFF,
        "@@PLACING_STEPS@@": PLACING_STEPS_ON if on else PLACING_STEPS_OFF,
    }
    for marker, part in parts.items():
        text = text.replace(marker, part.replace("{above}", above))
    return text


def render(topic: str | None = None) -> str:
    """Build the guide for the installed version.

    With no topic, the commands: what an agent needs for nearly every
    request, and short enough to be read whole. With 'python', the
    reference for writing a script: methods, fields and an example.
    """
    from pyhood import __version__

    # Not str.format: the examples contain f-strings, whose braces it would read.
    if topic == "python":
        return "\n".join((
            _with_path_note(SCRIPTS.replace("{version}", __version__), "RUNNING A SCRIPT"),
            _methods("READING (safe to call freely)", READ_METHODS),
            _models(),
            _methods(
                "ORDERS FROM A SCRIPT (prefer the commands in `pyhood guide`, which\n"
                "follow the user's confirmation setting; these send at once)",
                WRITE_METHODS,
            ),
            OUTRO,
        ))
    return _with_path_note(
        _for_setting(COMMANDS.replace("{version}", __version__)), "PLACING ORDERS (",
    )


def main(topic: str | None = None) -> int:
    sys.stdout.write(render(topic))
    return 0
