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

INTRO = """\
pyhood {version}: a Python client for Robinhood
==============================================

This guide is for an AI agent. It describes the installed version.

RULES
  1. pyhood is installed. Do not install it or its dependencies, and do
     not import it from a source folder.
  2. Never ask for, read or type a password or API key. Login is saved.
  3. Never place an order or move money without showing the user exactly
     what will happen first and getting a yes. See PLACING ORDERS.
     Cancel an order only when the user asks you to.
  4. Do not guess field or method names. They are all listed below.

QUICK ANSWERS (no script needed, all read-only)
  Try these first. They cover most questions about an account.

      pyhood positions            what the account holds, with profit and loss
      pyhood orders               orders from the last 30 days, newest first
      pyhood orders --since 2026-01-01    or --all, or --symbol AAPL
      pyhood buying-power         cash available to trade with
      pyhood quote AAPL MSFT      current prices; add --fundamentals for more
      pyhood options AAPL         the expiration dates of AAPL's options
      pyhood options AAPL --expires 2026-12-18    the contracts for that date

  Each prints a table. Add --json for exact values. Times in the tables
  are local; in --json and in scripts they are UTC.

PLACING ORDERS (two steps, every time)
  Step 1. Preview. This sends nothing:

      pyhood buy AAPL 10 --limit 350
      pyhood sell AAPL 10 --limit 360
      pyhood buy AAPL 10 --market
      pyhood buy-option AAPL --expires 2026-12-18 --strike 350 --call --contracts 1 --limit 2.50
      pyhood sell-option AAPL --expires 2026-12-18 --strike 350 --call --contracts 1 --limit 3.00

  The preview shows the order, its cost, the current price and any
  problem with it, and ends with the exact command that would place it,
  including a confirmation code.

  Step 2. Show the whole preview to the user and ask. Only if they say
  yes, run the command the preview printed, unchanged.

  Do not invent a code and do not change an order after previewing it: a
  code works for one exact order on one day, and anything else is refused.
  If the user changes their mind about quantity or price, preview again.
  An order needs --limit PRICE or --market; there is no default.
  Orders are good for the day unless you add --tif gtc.
  Option prices are per share and a contract is 100 shares: --limit 2.50
  on 1 contract is $250. Look up real expirations and strikes with
  `pyhood options` first; do not guess them. buy-option opens a position
  and sell-option closes one unless you add --to open or --to close.

CANCELLING AN ORDER (one step)
      pyhood orders --open        the orders that can still be cancelled, with IDs
      pyhood cancel ORDER_ID      cancels that order at once

  There is no preview and no code: the user asking you to cancel is the
  yes. Cancel the order they mean and tell them what the command reported.
  Never cancel an order they did not ask you to cancel.

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


def _intro(version: str) -> str:
    """The hand-written part, with the path note ahead of the first command."""
    # Not str.format: the examples contain f-strings, whose braces it would read.
    text = INTRO.replace("{version}", version)
    note = _path_note()
    if note:
        text = text.replace("QUICK ANSWERS", f"{note}\nQUICK ANSWERS", 1)
    return text


def render() -> str:
    """Build the guide for the installed version."""
    from pyhood import __version__

    return "\n".join(part for part in (
        _intro(__version__),
        _methods("READING (safe to call freely)", READ_METHODS),
        _models(),
        _methods(
            "ORDERS FROM A SCRIPT (prefer the commands under PLACING ORDERS, which\n"
            "preview first; these send at once, so ask the user first)",
            WRITE_METHODS,
        ),
        OUTRO,
    ) if part)


def main() -> int:
    sys.stdout.write(render())
    return 0
