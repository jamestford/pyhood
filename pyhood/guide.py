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
  3. Never place, change or cancel an order, or move money, without
     showing the user the exact call first and getting a yes.
  4. Do not guess field or method names. They are all listed below.

RUNNING IT
  Write a Python script and run it with:

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
          print(p.symbol, p.quantity, p.average_cost, p.unrealized_pl)

      for o in client.get_stock_orders(start_date="2026-11-01"):
          print(o.created_at, o.side, o.symbol, o.filled_quantity,
                o.average_price, o.status)

RESULTS
  Methods return dataclasses, or lists of them. print() one to see every
  field and value. A field that is None is unknown, not zero: check for
  None before doing arithmetic or formatting with it.
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


def render() -> str:
    """Build the guide for the installed version."""
    from pyhood import __version__

    return "\n".join((
        INTRO.format(version=__version__),
        _methods("READING (safe to call freely)", READ_METHODS),
        _models(),
        _methods("ORDERS (ask the user first, every time)", WRITE_METHODS),
        OUTRO,
    ))


def main() -> int:
    sys.stdout.write(render())
    return 0
