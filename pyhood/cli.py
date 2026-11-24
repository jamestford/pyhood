"""Read-only account commands: `pyhood positions`, `orders`, `buying-power`, `quote`.

These answer the questions asked most often without a script. They exist
for AI agents first: a model asked "what did I buy?" otherwise writes a
script, and the scripts fail in the same few ways, by formatting a price
that is None on an unfilled order, or by reading a UTC timestamp as local
time. Here those are handled once.

Every command is read-only, and takes `--json` for exact values in place
of the table.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from pyhood.exceptions import AuthError, PyhoodError

DEFAULT_ORDER_DAYS = 30


# ── Formatting ───────────────────────────────────────────────────────


def money(value: float | None) -> str:
    """'$1,234.56', '-$5.00', or '-' when the value is unknown."""
    if value is None:
        return "-"
    return f"-${-value:,.2f}" if value < 0 else f"${value:,.2f}"


def signed_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"+{money(value)}" if value > 0 else money(value)


def large_money(value: float | None) -> str:
    """A market cap: '$5.12T', '$830.40B', '$12.50M'."""
    if value is None:
        return "-"
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= size:
            return f"${value / size:,.2f}{suffix}"
    return money(value)


def number(value: float | None) -> str:
    """A quantity without trailing zeros, or '-' when unknown."""
    return "-" if value is None else f"{value:,.6f}".rstrip("0").rstrip(".")


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value:+.2f}%"


def local_time(value: datetime | None) -> str:
    """A timestamp in this machine's time zone. The API's are UTC."""
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M %Z")


def table(headers: list[str], rows: list[list[str]], right: set[int] | None = None) -> str:
    """Plain aligned columns. `right` holds the indexes to right-align."""
    right = right or set()
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]

    def line(cells: list[str]) -> str:
        return "  ".join(
            cell.rjust(widths[i]) if i in right else cell.ljust(widths[i])
            for i, cell in enumerate(cells)
        ).rstrip()

    return "\n".join([line(headers), *(line(row) for row in rows)])


def as_json(value: Any) -> str:
    """JSON with dataclasses as objects and times as ISO-8601, UTC as sent."""

    def default(item: Any) -> Any:
        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            return dataclasses.asdict(item)
        if isinstance(item, datetime):
            return item.isoformat()
        raise TypeError(f"cannot serialize {type(item).__name__}")

    return json.dumps(value, indent=2, default=default)


# ── Commands ─────────────────────────────────────────────────────────


def positions(client: Any, as_json_output: bool = False) -> int:
    """What the account holds: stocks, then options."""
    stocks = client.get_positions()
    options = client.get_option_positions()

    if as_json_output:
        print(as_json({"stocks": stocks, "options": options}))
        return 0
    if not stocks and not options:
        print("No open positions.")
        return 0

    if stocks:
        rows = [
            [
                p.symbol, number(p.quantity), money(p.average_cost), money(p.current_price),
                money(p.equity), signed_money(p.unrealized_pl), percent(p.unrealized_pl_pct),
            ]
            for p in stocks
        ]
        rows.append([
            "TOTAL", "", "", "", money(sum(p.equity for p in stocks)),
            signed_money(sum(p.unrealized_pl for p in stocks)), "",
        ])
        print("STOCKS")
        print(table(
            ["SYMBOL", "SHARES", "AVG COST", "PRICE", "VALUE", "UNREALIZED P/L", "P/L %"],
            rows, right={1, 2, 3, 4, 5, 6},
        ))

    if options:
        rows = [
            [
                f"{p.symbol} {p.expiration} ${number(p.strike)} {p.option_type}",
                number(p.quantity), money(p.average_open_price), money(p.current_mark),
                money(p.current_value), signed_money(p.unrealized_pl),
                percent(p.unrealized_pl_pct),
            ]
            for p in options
        ]
        if stocks:
            print()
        print("OPTIONS (prices are per share; one contract is 100 shares)")
        print(table(
            ["CONTRACT", "CONTRACTS", "AVG COST", "MARK", "VALUE", "UNREALIZED P/L", "P/L %"],
            rows, right={1, 2, 3, 4, 5, 6},
        ))
    return 0


def orders(
    client: Any,
    since: str | None = None,
    symbol: str | None = None,
    everything: bool = False,
    as_json_output: bool = False,
) -> int:
    """Stock and option orders, newest first."""
    if everything:
        since = None
    elif since is None:
        since = (datetime.now() - timedelta(days=DEFAULT_ORDER_DAYS)).strftime("%Y-%m-%d")

    found = client.get_stock_orders(start_date=since) + client.get_option_orders(start_date=since)
    if symbol:
        found = [o for o in found if o.symbol.upper() == symbol.upper()]
    # created_at is None only if Robinhood sent an unreadable timestamp.
    found.sort(key=lambda o: o.created_at.timestamp() if o.created_at else 0.0, reverse=True)

    if as_json_output:
        print(as_json(found))
        return 0

    scope = "All orders" if since is None else f"Orders since {since}"
    if symbol:
        scope += f" for {symbol.upper()}"
    if not found:
        print(f"{scope}: none.")
        if since is not None:
            print("Use --since YYYY-MM-DD or --all for older orders.")
        return 0

    zone = datetime.now().astimezone().strftime("%Z")
    print(f"{scope} (times are {zone}; today is {datetime.now():%Y-%m-%d})")
    rows = [
        [
            local_time(o.created_at), o.side, o.symbol, o.instrument_type, number(o.quantity),
            money(o.price), number(o.filled_quantity), money(o.average_price), o.status,
        ]
        for o in found
    ]
    print(table(
        ["PLACED", "SIDE", "SYMBOL", "TYPE", "ORDERED", "LIMIT", "FILLED", "AVG PRICE", "STATUS"],
        rows, right={4, 5, 6, 7},
    ))
    print(
        "\nFILLED is the quantity that actually traded and AVG PRICE the price it "
        "traded at. An order that never filled shows 0 and '-'. Option prices are "
        "per share."
    )
    return 0


def buying_power(client: Any, as_json_output: bool = False) -> int:
    """Cash available to trade with."""
    amount = client.get_buying_power()
    if as_json_output:
        print(as_json({"buying_power": amount}))
    else:
        print(f"Buying power: {money(amount)}")
    return 0


def quote(
    client: Any,
    symbols: list[str],
    fundamentals: bool = False,
    as_json_output: bool = False,
) -> int:
    """Current prices for one or more stocks."""
    wanted = [s.upper() for s in symbols]
    quotes = client.get_quotes(wanted, include_fundamentals=fundamentals)
    missing = [s for s in wanted if s not in quotes]

    if as_json_output:
        print(as_json({s: quotes[s] for s in wanted if s in quotes}))
    elif quotes:
        headers = ["SYMBOL", "PRICE", "CHANGE", "PREV CLOSE", "BID", "ASK"]
        right = {1, 2, 3, 4, 5}
        if fundamentals:
            headers += ["VOLUME", "P/E", "MARKET CAP", "52W LOW", "52W HIGH"]
            right |= {6, 7, 8, 9, 10}
        rows = []
        for s in wanted:
            if s not in quotes:
                continue
            q = quotes[s]
            row = [
                q.symbol, money(q.price), percent(q.change_pct), money(q.prev_close),
                money(q.bid), money(q.ask),
            ]
            if fundamentals:
                row += [
                    number(q.volume), "-" if q.pe_ratio is None else f"{q.pe_ratio:.2f}",
                    large_money(q.market_cap), money(q.low_52w), money(q.high_52w),
                ]
            rows.append(row)
        print(table(headers, rows, right=right))
        newest = max((q.timestamp for q in quotes.values() if q.timestamp), default=None)
        if newest:
            print(f"\nAs of {local_time(newest)}.")

    for s in missing:
        print(f"No quote for {s}.", file=sys.stderr)
    return 1 if missing else 0


# ── Running one ──────────────────────────────────────────────────────


def run(command: Callable[..., int], **kwargs: Any) -> int:
    """Log in with the saved session and run a command, reporting failures plainly."""
    import pyhood
    from pyhood.client import PyhoodClient

    try:
        client = PyhoodClient(pyhood.login())
        return command(client, **kwargs)
    except AuthError as e:
        print(f"Not logged in: {e}", file=sys.stderr)
        print("Run: pyhood setup login", file=sys.stderr)
        return 1
    except PyhoodError as e:
        print(f"Robinhood request failed: {e}", file=sys.stderr)
        return 1
