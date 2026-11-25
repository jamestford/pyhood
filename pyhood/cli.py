"""Account commands: `pyhood positions`, `orders`, `buying-power`, `quote`,
`options`, and `pyhood buy`, `sell`, `buy-option`, `sell-option` and `cancel`.

The first five are read-only and answer the questions asked most often
without a script. They exist for AI agents first: a model asked "what did
I buy?" otherwise writes a script, and the scripts fail in the same few
ways, by formatting a price that is None on an unfilled order, or by
reading a UTC timestamp as local time. Here those are handled once. Each
takes `--json` for exact values in place of the table.

The commands that place an order work in two steps. Run once, a command
only describes what it would do and prints a confirmation code. Run again
with that code, it does it. See `confirmation_code`. `cancel` acts at
once: it can only remove one named order.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import sys
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from pyhood.exceptions import AuthError, OrderError, PyhoodError

DEFAULT_ORDER_DAYS = 30

# States in which an order can still fill, and so can still be cancelled.
OPEN_STATES = frozenset({"queued", "unconfirmed", "confirmed", "partially_filled"})


class UsageError(Exception):
    """The command was asked for something that does not exist, such as an
    account the user does not have. Reported plainly, with exit status 2."""


ACCOUNT_NAMES = {
    "individual": "Individual",
    "ira_roth": "Roth IRA",
    "ira_traditional": "Traditional IRA",
}


def account_name(account: dict) -> str:
    """'Roth IRA' for 'ira_roth'; the nickname too if the account has one."""
    kind = account.get("brokerage_account_type") or ""
    name = ACCOUNT_NAMES.get(kind, kind.replace("_", " ").capitalize() or "Account")
    nickname = account.get("nickname")
    return f"{name} ({nickname})" if nickname else name


def masked(number: str) -> str:
    """An account number with only its last four characters showing."""
    return f"…{number[-4:]}" if number else ""


def find_account(client: Any, selector: str | None) -> tuple[str | None, str]:
    """Turn what was typed after --account into an account number and a label.

    The selector may be the account number, its last four characters, or
    part of the account's type or nickname: 'roth', 'ira', 'individual'.
    None means the default account, which needs no lookup.
    """
    if selector is None:
        return None, ""
    wanted = selector.strip().lower()
    accounts = client.get_all_accounts()
    matches = []
    for account in accounts:
        account_number = account.get("account_number", "")
        texts = (
            account.get("brokerage_account_type") or "", account_name(account),
            account.get("nickname") or "",
        )
        if (
            wanted == account_number.lower()
            or (len(wanted) >= 4 and account_number.lower().endswith(wanted))
            or any(wanted in text.lower() for text in texts)
        ):
            matches.append(account)
    listing = ", ".join(
        f"{account_name(a)} ({masked(a.get('account_number', ''))})" for a in accounts
    )
    if not matches:
        raise UsageError(f"No account matches {selector!r}. Your accounts: {listing}")
    if len(matches) > 1:
        raise UsageError(
            f"{selector!r} matches more than one account. Your accounts: {listing}"
        )
    account = matches[0]
    account_number = account.get("account_number", "")
    return account_number, f"{account_name(account)} ({masked(account_number)})"


def _amount(account: dict, key: str) -> float | None:
    """A money figure from an account record, which holds them as
    {'amount': '123.45', 'currency_code': 'USD'}."""
    value = account.get(key)
    if isinstance(value, dict):
        value = value.get("amount")
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def program() -> str:
    """How to run pyhood from a shell here: `pyhood`, or its full path.

    The commands that pyhood prints for someone to run next have to work as
    printed. An install in its own folder is often not on the PATH, and
    there `pyhood buy ...` would be "command not found".
    """
    here = Path(sys.executable).with_name("pyhood")
    found = shutil.which("pyhood")
    if found is None:
        return str(here) if here.exists() else "pyhood"
    # Another pyhood earlier on the PATH is a different install.
    if here.exists() and Path(found).resolve() != here.resolve():
        return str(here)
    return "pyhood"


# ── Formatting ───────────────────────────────────────────────────────


def plain(value: float) -> str:
    """A number written out in full: '12345.67', '5000000', '0.00001'.

    For anything that has to survive being typed back in, which is every
    number in a command that pyhood prints and in a confirmation code. The
    general 'g' format will not do: it keeps six significant digits, so
    12345.67 comes out as 12345.7 and five million as 5e+06.
    """
    return f"{value:.8f}".rstrip("0").rstrip(".")


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


def order_side(order: Any) -> str:
    """'buy', or 'buy to open' for an option order."""
    if order.instrument_type == "option" and order.position_effect:
        return f"{order.side} to {order.position_effect}"
    return order.side


def _limit(order: Any) -> str:
    """An order's limit price, or 'market'.

    Robinhood records a price on a market order too: the ceiling or floor it
    requires, or a stop buy's stop. That is not a limit anyone chose.
    """
    if order.order_type == "market":
        return "market"
    return money(order.price)


def order_kind(order: Any) -> str:
    """'stock', '$12.00 call 2026-12-11', or '2-leg option' for a spread."""
    if order.instrument_type != "option":
        return order.instrument_type
    if order.strike is not None and order.option_type and order.expiration:
        return f"{money(order.strike)} {order.option_type} {order.expiration}"
    if order.leg_count and order.leg_count > 1:
        return f"{order.leg_count}-leg option"
    return "option"


def table(headers: list[str], rows: list[list[str]], right: set[int] | None = None) -> str:
    """Plain aligned columns. `right` holds the indexes to right-align.

    A cell that is None or empty prints as '-', so a value Robinhood did
    not send never breaks the table or reads as blank.
    """
    right = right or set()
    rows = [["-" if cell is None or cell == "" else str(cell) for cell in row] for row in rows]
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


def accounts(client: Any, as_json_output: bool = False) -> int:
    """The accounts under this login, with what each is worth."""
    found = client.get_all_accounts()
    rows = [
        {
            "account": account_name(a),
            "type": a.get("brokerage_account_type"),
            "account_number": a.get("account_number", ""),
            "value": _amount(a, "total_equity"),
            "cash": _amount(a, "uninvested_cash"),
            "buying_power": _amount(a, "account_buying_power"),
        }
        for a in found
    ]
    if as_json_output:
        print(as_json(rows))
        return 0
    if not rows:
        print("No accounts found.")
        return 1
    print(table(
        ["ACCOUNT", "NUMBER", "VALUE", "CASH", "BUYING POWER"],
        [
            [r["account"], masked(r["account_number"]), money(r["value"]), money(r["cash"]),
             money(r["buying_power"])]
            for r in rows
        ],
        right={2, 3, 4},
    ))
    print(
        f"\nOther commands use the first account unless told otherwise, as in: "
        f"{program()} positions --account roth"
    )
    return 0


def positions(client: Any, account: str | None = None, as_json_output: bool = False) -> int:
    """What an account holds: stocks, then options."""
    account_number, label = find_account(client, account)
    if account_number:
        stocks = client.get_positions(account_number=account_number)
        options = client.get_option_positions(account_number=account_number)
    else:
        stocks = client.get_positions()
        options = client.get_option_positions()

    if as_json_output:
        print(as_json({"stocks": stocks, "options": options}))
        return 0
    if label:
        print(f"{label}\n")
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
    open_only: bool = False,
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
    if open_only:
        found = [o for o in found if o.status in OPEN_STATES]
    # created_at is None only if Robinhood sent an unreadable timestamp.
    found.sort(key=lambda o: o.created_at.timestamp() if o.created_at else 0.0, reverse=True)

    if as_json_output:
        print(as_json(found))
        return 0

    kind = "open orders" if open_only else "orders"
    scope = f"All {kind}" if since is None else f"{kind.capitalize()} since {since}"
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
            local_time(o.created_at), order_side(o), o.symbol, order_kind(o), number(o.quantity),
            _limit(o), money(getattr(o, "stop_price", None)),
            number(o.filled_quantity), money(o.average_price), o.status, o.order_id,
        ]
        for o in found
    ]
    print(table(
        ["PLACED", "SIDE", "SYMBOL", "TYPE", "ORDERED", "LIMIT", "STOP", "FILLED",
         "AVG PRICE", "STATUS", "ORDER ID"],
        rows, right={4, 5, 6, 7, 8},
    ))
    print(
        "\nFILLED is the quantity that actually traded and AVG PRICE the price it "
        "traded at. An order that never filled shows 0 and '-'. A STOP is the price "
        "that sets the order off; with no LIMIT it then trades at market. Option "
        "prices are per share."
    )
    return 0


def buying_power(
    client: Any, account: str | None = None, as_json_output: bool = False,
) -> int:
    """Cash available to trade with."""
    account_number, label = find_account(client, account)
    amount = client.get_buying_power(account_number=account_number) if account_number else (
        client.get_buying_power()
    )
    if as_json_output:
        print(as_json({"buying_power": amount}))
    else:
        print(f"Buying power{f' in {label}' if label else ''}: {money(amount)}")
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


def _days_until(expiration: str) -> int | None:
    try:
        return (date.fromisoformat(expiration) - date.today()).days
    except ValueError:
        return None


def _expiry(expiration: str) -> str:
    """'2026-12-18 (24 days)'."""
    days = _days_until(expiration)
    if days is None:
        return expiration
    when = "today" if days == 0 else f"{days} day{'' if days == 1 else 's'}"
    return f"{expiration} ({when})"


def _nearest(values: list[Any], target: Any, count: int, key: Callable[[Any], float]) -> list[Any]:
    """The `count` values closest to `target`, in their original order."""
    chosen = sorted(values, key=lambda v: abs(key(v) - target))[:count]
    return [v for v in values if any(v is c for c in chosen)]


def options(
    client: Any,
    symbol: str,
    expires: str | None = None,
    option_type: str | None = None,
    strikes: int = 10,
    as_json_output: bool = False,
) -> int:
    """Expiration dates for a symbol, or the contracts for one of them."""
    symbol = symbol.upper()
    expirations = client.get_options_expirations(symbol)

    if expires is None:
        if as_json_output:
            print(as_json(expirations))
            return 0
        if not expirations:
            print(f"No options are listed for {symbol}.")
            return 1
        print(f"{symbol} option expirations (today is {date.today():%Y-%m-%d})")
        print(table(
            ["EXPIRES", "DAYS AWAY"],
            [[e, str(_days_until(e)) if _days_until(e) is not None else "-"] for e in expirations],
            right={1},
        ))
        print(f"\nTo see the contracts for one: {program()} options {symbol} --expires YYYY-MM-DD")
        return 0

    if expires not in expirations:
        return _no_such_expiration(symbol, expires, expirations)

    chain = client.get_options_chain(symbol, expires, option_type)
    spot = client.get_quote(symbol).price
    groups = [("call", chain.calls), ("put", chain.puts)]
    groups = [
        (kind, _nearest(sorted(found, key=lambda c: c.strike), spot, strikes, lambda c: c.strike))
        for kind, found in groups
        if option_type in (None, kind)
    ]

    if as_json_output:
        print(as_json({
            "symbol": symbol, "price": spot, "expiration": expires,
            **{f"{kind}s": found for kind, found in groups},
        }))
        return 0

    print(f"{symbol} is at {money(spot)}. Options expiring {_expiry(expires)}.")
    print("Prices are per share. One contract is 100 shares, so $2.50 costs $250.")
    for kind, found in groups:
        print(f"\n{kind.upper()}S, the {len(found)} strikes nearest the price")
        print(table(
            ["STRIKE", "BID", "ASK", "MARK", "DELTA", "IV", "VOLUME", "OPEN INT"],
            [
                [
                    money(c.strike), money(c.bid), money(c.ask), money(c.mark),
                    "-" if c.delta is None else f"{c.delta:+.3f}",
                    "-" if c.iv is None else f"{c.iv:.1%}",
                    number(c.volume), number(c.open_interest),
                ]
                for c in found
            ],
            right={0, 1, 2, 3, 4, 5, 6, 7},
        ))
    return 0


def _no_such_expiration(symbol: str, expires: str, expirations: list[str]) -> int:
    print(f"{symbol} has no options expiring {expires}.", file=sys.stderr)
    if expirations:
        target = date.fromisoformat(expires).toordinal()
        near = _nearest(expirations, target, 5, lambda e: date.fromisoformat(e).toordinal())
        print(f"The nearest expirations are: {', '.join(near)}", file=sys.stderr)
    return 1


# ── Research ─────────────────────────────────────────────────────────


def earnings(
    client: Any, symbols: list[str], days: int = 90, as_json_output: bool = False,
) -> int:
    """The next earnings report for each symbol."""
    found = {s.upper(): client.get_earnings(s.upper(), lookahead_days=days) for s in symbols}
    if as_json_output:
        print(as_json(found))
        return 0
    when = {"am": "before the open", "pm": "after the close"}
    rows = [
        [symbol, e.date, when.get(e.timing or "", "-"),
         "-" if e.eps_estimate is None else f"{e.eps_estimate:.2f}",
         "-" if e.eps_actual is None else f"{e.eps_actual:.2f}"]
        if e else [symbol, f"none in the next {days} days", "", "", ""]
        for symbol, e in found.items()
    ]
    print(table(["SYMBOL", "REPORTS", "WHEN", "EPS ESTIMATE", "EPS ACTUAL"], rows, right={3, 4}))
    return 0


def ratings(client: Any, symbols: list[str], as_json_output: bool = False) -> int:
    """Analysts' buy, hold and sell counts and price targets."""
    found = [client.get_ratings(s.upper()) for s in symbols]
    if as_json_output:
        print(as_json(found))
        return 0
    print(table(
        ["SYMBOL", "BUY", "HOLD", "SELL", "BUY %", "TARGET LOW", "TARGET MEAN", "TARGET HIGH"],
        [
            [r.symbol, str(r.num_buy), str(r.num_hold), str(r.num_sell),
             f"{r.buy_pct:.0f}%" if r.total else "-", money(r.price_target_low),
             money(r.price_target_mean), money(r.price_target_high)]
            for r in found
        ],
        right={1, 2, 3, 4, 5, 6, 7},
    ))
    return 0


def news(client: Any, symbol: str, count: int = 5, as_json_output: bool = False) -> int:
    """Recent headlines for a symbol."""
    articles = client.get_news(symbol.upper())[:count]
    if as_json_output:
        print(as_json(articles))
        return 0
    if not articles:
        print(f"No news for {symbol.upper()}.")
        return 0
    for article in articles:
        try:
            stamp = datetime.fromisoformat(article.published_at.replace("Z", "+00:00"))
            published = local_time(stamp)
        except (ValueError, AttributeError):
            published = article.published_at or "-"
        print(f"{published}  {article.source}")
        print(f"  {article.title}")
        print(f"  {article.url}\n")
    return 0


def movers(client: Any, down: bool = False, as_json_output: bool = False) -> int:
    """The S&P 500 stocks that have moved most today."""
    found = client.get_movers("down" if down else "up")
    if as_json_output:
        print(as_json(found))
        return 0
    print(f"S&P 500, biggest moves {'down' if down else 'up'} today")
    print(table(
        ["SYMBOL", "PRICE", "CHANGE", "CHANGE %"],
        [[m.symbol, money(m.price), signed_money(m.price_change), percent(m.price_change_pct)]
         for m in found],
        right={1, 2, 3},
    ))
    return 0


HISTORY_INTERVALS = {
    "week": "day", "month": "day", "3month": "day", "year": "week", "5year": "week",
}


def history(
    client: Any, symbol: str, span: str = "month", as_json_output: bool = False,
) -> int:
    """Past prices for a symbol: one row a day, or a week for the long spans."""
    candles = client.get_stock_historicals(
        symbol.upper(), interval=HISTORY_INTERVALS[span], span=span,
    )
    if as_json_output:
        print(as_json(candles))
        return 0
    if not candles:
        print(f"No price history for {symbol.upper()}.")
        return 1
    every = "week" if HISTORY_INTERVALS[span] == "week" else "day"
    print(f"{symbol.upper()}, the last {span}, one row a {every}")
    print(table(
        ["DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
        [[c.begins_at[:10], money(c.open_price), money(c.high_price), money(c.low_price),
          money(c.close_price), number(c.volume)] for c in candles],
        right={1, 2, 3, 4, 5},
    ))
    first, last = candles[0].open_price, candles[-1].close_price
    if first:
        print(f"\nOver the period: {money(first)} to {money(last)}, "
              f"{percent((last - first) / first * 100)}.")
    return 0


# ── Money in and out ─────────────────────────────────────────────────


def dividends(client: Any, symbol: str | None = None, as_json_output: bool = False) -> int:
    """Dividends paid and pending."""
    found = (
        client.get_dividends_by_symbol(symbol.upper()) if symbol else client.get_dividends()
    )
    found = sorted(found, key=lambda d: d.payable_date or "", reverse=True)
    if as_json_output:
        print(as_json(found))
        return 0
    if not found:
        print(f"No dividends{f' for {symbol.upper()}' if symbol else ''} on record.")
        return 0
    print(table(
        ["PAYABLE", "SYMBOL", "AMOUNT", "PER SHARE", "STATE"],
        [[d.payable_date, d.symbol, money(d.amount), money(d.rate), d.state] for d in found],
        right={2, 3},
    ))
    paid = sum(d.amount for d in found if d.state == "paid")
    print(f"\nPaid in total: {money(paid)}")
    return 0


# What Robinhood calls each end of a transfer, in plain words.
TRANSFER_ENDS = {
    "rhs_account": "Individual account",
    "rhs_roth_ira": "Roth IRA",
    "rhs_traditional_ira": "Traditional IRA",
    "ach_relationship": "Bank",
}
BANK_END = "ach_relationship"


def bank_name(bank: Any) -> str:
    """'Savings …1234 (Rainy day)'."""
    name = (bank.account_type or "account").capitalize()
    if bank.last_four:
        name += f" …{bank.last_four}"
    if bank.account_nickname:
        name += f" ({bank.account_nickname})"
    return name


def _transfer_end(kind: str, account_id: str, banks: dict[str, Any]) -> str | None:
    """One end of a transfer by name: a linked bank, or a Robinhood account."""
    if kind == BANK_END and account_id in banks:
        return bank_name(banks[account_id])
    if kind in TRANSFER_ENDS:
        return TRANSFER_ENDS[kind]
    return kind.removeprefix("rhs_").replace("_", " ").capitalize() if kind else None


def transfer_route(transfer: Any, banks: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """What a transfer is, where the money came from and where it went.

    Robinhood records who asked and in which direction, not where the money
    went. A 'push' sends money from the originating account to the receiving
    one. A 'pull' brings it the other way: a deposit is the Robinhood account
    pulling from the bank, so the bank is the 'receiving' end of the request
    and the source of the money.
    """
    origin = _transfer_end(
        transfer.originating_account_type, transfer.originating_account_id, banks)
    target = _transfer_end(
        transfer.receiving_account_type, transfer.receiving_account_id, banks)
    if transfer.direction == "pull":
        source, destination = target, origin
        from_bank = transfer.receiving_account_type == BANK_END
        to_bank = transfer.originating_account_type == BANK_END
    elif transfer.direction == "push":
        source, destination = origin, target
        from_bank = transfer.originating_account_type == BANK_END
        to_bank = transfer.receiving_account_type == BANK_END
    else:
        # A direction pyhood has not seen. Do not guess which way money went.
        return transfer.direction or "transfer", None, None
    if from_bank:
        what = "deposit"
    elif to_bank:
        what = "withdrawal"
    else:
        what = transfer.description or "transfer"
    return what, source, destination


def transfers(client: Any, as_json_output: bool = False) -> int:
    """Transfers into, out of and between accounts. Read-only."""
    found = sorted(
        client.get_unified_transfers(), key=lambda t: t.created_at or "", reverse=True,
    )
    if as_json_output:
        print(as_json(found))
        return 0
    if not found:
        print("No transfers on record.")
        return 0
    banks: dict[str, Any] = {}
    if any(BANK_END in (t.originating_account_type, t.receiving_account_type) for t in found):
        try:
            banks = {b.id: b for b in client.get_bank_accounts()}
        except PyhoodError:
            pass  # The table still reads; a bank is then just 'Bank'.
    rows = []
    pending = False
    for t in found:
        what, source, destination = transfer_route(t, banks)
        if what in ("deposit", "withdrawal") and t.state == "pending":
            pending = True
        rows.append([
            (t.created_at or "")[:10], money(t.amount), what, source, destination, t.state, t.id,
        ])
    print(table(
        ["CREATED", "AMOUNT", "WHAT", "FROM", "TO", "STATE", "TRANSFER ID"], rows, right={1},
    ))
    if pending:
        print(
            "\nA deposit or withdrawal that is still pending can be cancelled with: "
            f"{program()} cancel-transfer TRANSFER_ID"
        )
    return 0


# ── Documents ────────────────────────────────────────────────────────


def documents(
    client: Any, kind: str | None = None, year: int | None = None,
    as_json_output: bool = False,
) -> int:
    """Statements, trade confirmations and tax forms, newest first."""
    found = sorted(client.get_documents(), key=lambda d: d.date or "", reverse=True)
    if kind:
        found = [d for d in found if kind.lower() in (d.type or "").lower()]
    if year:
        found = [d for d in found if (d.date or "").startswith(str(year))]
    if as_json_output:
        print(as_json([{"date": d.date, "type": d.type, "id": d.id} for d in found]))
        return 0
    if not found:
        print("No documents match.")
        return 0
    print(table(
        ["DATE", "TYPE", "DOCUMENT ID"],
        [[(d.date or "")[:10], d.type, d.id] for d in found],
    ))
    print(f"\nTo save one as a PDF: {program()} document DOCUMENT_ID")
    return 0


def document(client: Any, document_id: str, to: str = "documents") -> int:
    """Save one document as a PDF, in a folder only the user can read."""
    path = client.download_document(document_id, to)
    print(f"Saved {path}")
    print("It shows your account details, so the folder is readable only by you.")
    return 0


# ── Watchlists ───────────────────────────────────────────────────────


def watchlists(client: Any, as_json_output: bool = False) -> int:
    """Your watchlists and what is on them."""
    found = client.get_watchlists()
    if as_json_output:
        print(as_json(found))
        return 0
    if not found:
        print("No watchlists.")
        return 0
    for watchlist in found:
        count = len(watchlist.symbols)
        print(f"{watchlist.name} ({count} {'symbol' if count == 1 else 'symbols'})")
        if watchlist.symbols:
            print(f"  {', '.join(watchlist.symbols)}")
    return 0


def watch(
    client: Any, symbols: list[str], list_name: str = "My First List", remove: bool = False,
) -> int:
    """Add stocks to a watchlist, or take them off. No money is involved."""
    wanted = [s.upper() for s in symbols]
    if remove:
        client.remove_from_watchlist(wanted, list_name)
    else:
        client.add_to_watchlist(wanted, list_name)
    now = {s.upper() for s in client.get_watchlist(list_name).symbols}
    done = [s for s in wanted if (s in now) != remove]
    failed = [s for s in wanted if s not in done]
    if done:
        verb = "Removed" if remove else "Added"
        print(f"{verb} {', '.join(done)} {'from' if remove else 'to'} {list_name!r}.")
    if failed:
        state = "still on" if remove else "not on"
        print(f"{', '.join(failed)} {'is' if len(failed) == 1 else 'are'} {state} "
              f"{list_name!r} after the request.", file=sys.stderr)
    return 1 if failed else 0


# ── Orders: preview, then confirm ────────────────────────────────────


def confirmation_code(*parts: object) -> str:
    """A short code tied to one exact action on one day.

    A command that changes the account runs twice: once to preview, which
    prints this code, and once with the code to act. That guarantees a
    preview was produced before anything is sent, and that what is sent is
    what was previewed: a different symbol, quantity or price gives a
    different code, and so does a different day.

    It is a guardrail against mistakes, not a lock. Anything that can run
    the preview can read the code.
    """
    text = "|".join(str(part) for part in parts) + "|" + datetime.now().strftime("%Y-%m-%d")
    return hashlib.sha256(text.encode()).hexdigest()[:6]


def _wrong_code() -> int:
    print(
        "That confirmation code does not match this order, so nothing was sent.\n"
        "A code belongs to one exact order on one day. Run the command without "
        "--confirm to preview it and get its code.",
        file=sys.stderr,
    )
    return 2


def stock_order(
    client: Any,
    side: str,
    symbol: str,
    quantity: float | None = None,
    limit: float | None = None,
    stop: float | None = None,
    time_in_force: str = "gfd",
    extended_hours: bool = False,
    account: str | None = None,
    confirm: str | None = None,
    settle_seconds: float = 2.0,
    dollars: float | None = None,
    trail_percent: float | None = None,
    trail_amount: float | None = None,
) -> int:
    """Preview a stock order, or place it when given its confirmation code.

    `limit` of None is a market order. `stop` makes it a stop order: it
    waits until the price reaches `stop`, then becomes the market or limit
    order it describes. `dollars` in place of `quantity` buys or sells that
    much money's worth, which is usually a fraction of a share.
    `trail_percent` or `trail_amount` makes a trailing stop: a stop that
    follows the price, staying that far behind its best level.
    """
    symbol = symbol.upper()
    if (quantity is None) == (dollars is None):
        raise UsageError("Give a number of shares, or --dollars AMOUNT, but not both.")
    trailing = trail_percent is not None or trail_amount is not None
    if trailing:
        if trail_percent is not None and trail_amount is not None:
            raise UsageError("Give --trail-percent or --trail-amount, one of them.")
        # Robinhood has no trailing stop limit order, and the stop price
        # is set by the trail.
        if limit is not None or stop is not None or dollars is not None:
            raise UsageError(
                "A trailing stop is a market order for a number of shares: use "
                "--market, with no --limit, --stop or --dollars."
            )
        if trail_percent is not None and trail_percent >= 100:
            raise UsageError("A trail is a percentage under 100.")
    if dollars is not None:
        # Robinhood takes a fraction of a share only as a market order.
        if limit is not None or stop is not None:
            raise UsageError(
                "An order by dollar amount is a market order: use --market, with no "
                "--limit or --stop."
            )
        if extended_hours:
            raise UsageError("An order by dollar amount trades in regular hours only.")
        if dollars < 1:
            raise UsageError("The smallest order by dollar amount is $1.")
    kind = "market" if limit is None else plain(limit)
    trigger = "" if stop is None else plain(stop)
    where = (account or "").strip().lower()
    size = plain(quantity) if dollars is None else f"${dollars:.2f}"
    trail = ""
    if trail_percent is not None:
        trail = f"{plain(trail_percent)}%"
    elif trail_amount is not None:
        trail = f"${plain(trail_amount)}"
    code = confirmation_code(
        side, symbol, size, kind, trigger, time_in_force, extended_hours, where, trail,
    )
    command = f"{program()} {side} {symbol} " + (
        f"{plain(quantity)} " if dollars is None else f"--dollars {plain(dollars)} "
    )
    if stop is not None:
        command += f"--stop {plain(stop)} "
    if trail_percent is not None:
        command += f"--trail-percent {plain(trail_percent)} "
    if trail_amount is not None:
        command += f"--trail-amount {plain(trail_amount)} "
    command += "--market" if limit is None else f"--limit {plain(limit)}"
    if time_in_force != "gfd":
        command += f" --tif {time_in_force}"
    if extended_hours:
        command += " --extended-hours"
    if account:
        command += f" --account {account}"

    # Checked before anything else, so a wrong code costs no requests.
    if confirm is not None and confirm != code:
        return _wrong_code()

    account_number, account_label = find_account(client, account)

    terms = "at market" if limit is None else f"limit {money(limit)}"
    if stop is not None:
        terms = f"stop {money(stop)} then {terms}"
    if trailing:
        behind = f"{plain(trail_percent)}%" if trail_percent is not None else money(trail_amount)
        way = "below" if side == "sell" else "above"
        terms = f"trailing stop {behind} {way} the price, then at market"
    duration = "good for day" if time_in_force == "gfd" else "good till cancelled"
    what = f"{number(quantity)} {symbol}" if dollars is None else f"{money(dollars)} of {symbol}"
    summary = f"{side.capitalize()} {what}, {terms}, {duration}"
    if extended_hours:
        summary += ", extended hours"
    if account_label:
        summary += f", in {account_label}"

    if confirm is not None:
        options: dict[str, Any] = {"time_in_force": time_in_force}
        if account_number:
            options["account_number"] = account_number
        if dollars is not None:
            place = client.buy_stock_by_price if side == "buy" else client.sell_stock_by_price
            size_to_send: float = dollars
        else:
            place = client.buy_stock if side == "buy" else client.sell_stock
            size_to_send = quantity  # type: ignore[assignment]
            options.update(price=limit, extended_hours=extended_hours)
            # Only named when used, so an ordinary order is sent exactly as before.
            if stop is not None:
                options["stop_price"] = stop
            if trail_percent is not None:
                options["trail_percent"] = trail_percent
            if trail_amount is not None:
                options["trail_amount"] = trail_amount
        try:
            order = place(symbol, size_to_send, **options)
        except OrderError as e:
            print(f"Robinhood did not accept the order: {e}", file=sys.stderr)
            return 1
        # The first response is the order as received; a moment later it
        # has been confirmed, filled or rejected.
        if settle_seconds:
            time.sleep(settle_seconds)
        try:
            order = client.get_order(order.order_id)
        except PyhoodError:
            pass
        print(f"PLACED: {summary}")
        print(f"  Status:    {order.status}")
        if order.filled_quantity:
            print(f"  Filled:    {number(order.filled_quantity)} at {money(order.average_price)}")
        print(f"  Order ID:  {order.order_id}")
        print(f"\nCheck it with:  {program()} orders --symbol {symbol}")
        if order.status in OPEN_STATES:
            print(f"Cancel it with: {program()} cancel {order.order_id}")
        return 0

    quote_now = client.get_quote(symbol)
    # What a share is likely to cost or fetch: the limit, else the stop it
    # waits for, else the price on offer now.
    reference = limit if limit is not None else stop
    if reference is None:
        reference = (quote_now.ask if side == "buy" else quote_now.bid) or quote_now.price
    start = None
    if trailing and quote_now.price:
        # Where the stop begins: the trail away from the last price.
        gap = trail_amount if trail_amount is not None else (
            quote_now.price * (trail_percent or 0) / 100
        )
        start = round(quote_now.price - gap if side == "sell" else quote_now.price + gap, 2)
        reference = start
    if dollars is not None:
        value = dollars
        quantity = dollars / reference if reference else 0.0
    else:
        value = quantity * reference  # type: ignore[operator]

    print("PREVIEW. Nothing has been sent.\n")
    print(f"  {summary}")
    label = "Estimated cost:" if side == "buy" else "Estimated proceeds:"
    print(f"  {label:<20}{money(value)}")
    if dollars is not None:
        print(f"  {'About:':<20}{number(round(quantity, 6))} shares at {money(reference)}")
    if start is not None:
        print(f"  {'Stop starts at:':<20}{money(start)}, and follows the price from there")
    print(f"  {symbol + ' now:':<20}{money(quote_now.price)} "
          f"(bid {money(quote_now.bid)}, ask {money(quote_now.ask)})")

    warnings = []
    if side == "buy":
        available = (
            client.get_buying_power(account_number=account_number) if account_number
            else client.get_buying_power()
        )
        print(f"  {'Buying power:':<20}{money(available)}")
        if value > available:
            warnings.append(
                "The estimated cost is more than your buying power. Robinhood is "
                "likely to reject this order."
            )
    else:
        holdings = (
            client.get_positions(account_number=account_number) if account_number
            else client.get_positions()
        )
        held = sum(p.quantity for p in holdings if p.symbol.upper() == symbol)
        print(f"  {'You hold:':<20}{number(held)} {symbol}")
        if quantity > held:
            warnings.append(
                f"You hold {number(held)} {symbol}, fewer than this order sells. "
                "Robinhood is likely to reject it."
            )
    print(f"  {'Market open:':<20}{'yes' if client.is_market_open() else 'no'}")

    if dollars is None and limit is not None and quantity != int(quantity):
        warnings.append(
            "Robinhood takes a fraction of a share only as a market order, so it is "
            "likely to reject this limit order."
        )
    if trailing:
        if start is not None and start <= 0:
            warnings.append("The trail is larger than the price, so the stop starts at nothing.")
        if side == "buy":
            # A trailing stop sell was placed live on 2026-11-24. A buy has
            # not been, and it is sent differently: it carries a price.
            warnings.append(
                "A trailing stop that buys has not yet been placed through pyhood. "
                "Robinhood may reject it; if it does, nothing is placed."
            )
        if time_in_force == "gfd":
            warnings.append(
                "This stop lasts for today only. Add --tif gtc to keep it working "
                "until it triggers or you cancel it."
            )
    if stop is not None and quote_now.price:
        # A sell stop sits below the price and a buy stop above it.
        wrong_side = stop >= quote_now.price if side == "sell" else stop <= quote_now.price
        if wrong_side:
            warnings.append(
                f"The stop of {money(stop)} is already "
                f"{'at or above' if side == 'sell' else 'at or below'} the last price of "
                f"{money(quote_now.price)}, so this order would trigger at once."
            )
        if time_in_force == "gfd":
            warnings.append(
                "This stop lasts for today only. Add --tif gtc to keep it working "
                "until it triggers or you cancel it."
            )
    if limit is None:
        warnings.append(
            "A market order fills at the best price available when it "
            + ("triggers" if stop is not None or trailing else "arrives")
            + ", which can differ from the quote above."
        )
    elif stop is None and quote_now.price:
        gap = (limit - quote_now.price) / quote_now.price * 100
        if abs(gap) >= 5:
            warnings.append(
                f"The limit is {abs(gap):.1f}% {'above' if gap > 0 else 'below'} "
                f"the last price of {money(quote_now.price)}."
            )
    for warning in warnings:
        print(f"\n  Note: {warning}")

    print("\nTo place this order, show this preview to the user. If they say yes, run:")
    print(f"  {command} --confirm {code}")
    return 0


def option_order(
    client: Any,
    side: str,
    symbol: str,
    expiration: str,
    strike: float,
    option_type: str,
    contracts: int,
    limit: float,
    effect: str | None = None,
    time_in_force: str = "gfd",
    account: str | None = None,
    confirm: str | None = None,
    settle_seconds: float = 2.0,
) -> int:
    """Preview a single-leg option order, or place it when given its code.

    `limit` is per share, as option prices are quoted. `effect` is 'open'
    or 'close'; left out, a buy opens and a sell closes.
    """
    symbol = symbol.upper()
    default_effect = "open" if side == "buy" else "close"
    effect = effect or default_effect
    code = confirmation_code(
        "option", side, effect, symbol, expiration, plain(strike), option_type, contracts,
        plain(limit), time_in_force, (account or "").strip().lower(),
    )
    command = (
        f"{program()} {side}-option {symbol} --expires {expiration} --strike {plain(strike)} "
        f"--{option_type} --contracts {contracts} --limit {plain(limit)}"
    )
    if effect != default_effect:
        command += f" --to {effect}"
    if time_in_force != "gfd":
        command += f" --tif {time_in_force}"
    if account:
        command += f" --account {account}"

    if confirm is not None and confirm != code:
        return _wrong_code()

    account_number, account_label = find_account(client, account)
    plural = "contract" if contracts == 1 else "contracts"
    name = f"{symbol} {money(strike)} {option_type} expiring {expiration}"
    duration = "good for day" if time_in_force == "gfd" else "good till cancelled"
    summary = (
        f"{side.capitalize()} to {effect} {contracts} {plural} of {name}, "
        f"limit {money(limit)} per share, {duration}"
    )
    if account_label:
        summary += f", in {account_label}"

    if confirm is not None:
        place = client.buy_option if side == "buy" else client.sell_option
        options: dict[str, Any] = {"position_effect": effect, "time_in_force": time_in_force}
        if account_number:
            options["account_number"] = account_number
        try:
            order = place(symbol, strike, expiration, option_type, contracts, limit, **options)
        except OrderError as e:
            print(f"Robinhood did not accept the order: {e}", file=sys.stderr)
            return 1
        if settle_seconds:
            time.sleep(settle_seconds)
        try:
            order = client.get_order(order.order_id)
        except PyhoodError:
            pass
        print(f"PLACED: {summary}")
        print(f"  Status:    {order.status}")
        if order.filled_quantity:
            print(f"  Filled:    {number(order.filled_quantity)} at {money(order.average_price)}")
        print(f"  Order ID:  {order.order_id}")
        print(f"\nCheck it with:  {program()} orders --symbol {symbol}")
        if order.status in OPEN_STATES:
            print(f"Cancel it with: {program()} cancel {order.order_id}")
        return 0

    expirations = client.get_options_expirations(symbol)
    if expiration not in expirations:
        return _no_such_expiration(symbol, expiration, expirations)
    chain = client.get_options_chain(symbol, expiration, option_type)
    listed = sorted(chain.calls if option_type == "call" else chain.puts, key=lambda c: c.strike)
    contract = next((c for c in listed if abs(c.strike - strike) < 0.0005), None)
    if contract is None:
        near = _nearest(listed, strike, 6, lambda c: c.strike)
        print(
            f"{symbol} has no {money(strike)} {option_type} expiring {expiration}.",
            file=sys.stderr,
        )
        if near:
            print(
                "The nearest strikes are: " + ", ".join(money(c.strike) for c in near),
                file=sys.stderr,
            )
        return 1

    value = contracts * 100 * limit
    spot = client.get_quote(symbol).price

    print("PREVIEW. Nothing has been sent.\n")
    print(f"  {summary}")
    label = "Estimated cost:" if side == "buy" else "Estimated proceeds:"
    print(f"  {label:<20}{money(value)} ({contracts} {plural} x 100 shares x {money(limit)})")
    print(f"  {'Contract now:':<20}mark {money(contract.mark)} "
          f"(bid {money(contract.bid)}, ask {money(contract.ask)})")
    print(f"  {symbol + ' now:':<20}{money(spot)}")
    if contract.delta is not None and contract.iv is not None:
        print(f"  {'Delta, IV:':<20}{contract.delta:+.3f}, {contract.iv:.1%}")
    print(f"  {'Expires:':<20}{_expiry(expiration)}")

    warnings = []
    if side == "buy" and effect == "open":
        available = (
            client.get_buying_power(account_number=account_number) if account_number
            else client.get_buying_power()
        )
        print(f"  {'Buying power:':<20}{money(available)}")
        if value > available:
            warnings.append(
                "The estimated cost is more than your buying power. Robinhood is "
                "likely to reject this order."
            )
    else:
        held_options = (
            client.get_option_positions(account_number=account_number) if account_number
            else client.get_option_positions()
        )
        held = sum(
            p.quantity for p in held_options
            if p.symbol.upper() == symbol and p.expiration == expiration
            and p.option_type == option_type and abs(p.strike - strike) < 0.0005
        )
        print(f"  {'You hold:':<20}{number(held)} of this contract")
        if side == "sell" and effect == "close" and contracts > held:
            warnings.append(
                f"You hold {number(held)} of this contract, fewer than this order sells. "
                "Robinhood is likely to reject it. Selling a contract you do not hold "
                "is selling to open, which needs --to open."
            )
    print(f"  {'Market open:':<20}{'yes' if client.is_market_open() else 'no'}")

    if side == "sell" and effect == "open":
        warnings.append(
            "Selling to open writes a contract: you take on the obligation it "
            "carries until it is bought back or expires. Robinhood needs approval "
            "and collateral for that, and may reject the order."
        )
    if side == "buy" and effect == "close":
        warnings.append("Buying to close is for a contract you sold to open.")
    if contract.mark:
        gap = (limit - contract.mark) / contract.mark * 100
        if abs(gap) >= 20:
            warnings.append(
                f"The limit is {abs(gap):.0f}% {'above' if gap > 0 else 'below'} "
                f"the contract's mark of {money(contract.mark)}."
            )
    if _days_until(expiration) == 0:
        warnings.append("This contract expires today.")
    for warning in warnings:
        print(f"\n  Note: {warning}")

    print("\nTo place this order, show this preview to the user. If they say yes, run:")
    print(f"  {command} --confirm {code}")
    return 0


def cancel(
    client: Any,
    order_id: str,
    settle_seconds: float = 1.0,
    attempts: int = 5,
) -> int:
    """Cancel an open order, and say what became of it.

    One step, unlike placing an order. A cancel names one order and can
    only remove it: there is no symbol, quantity or price to get wrong,
    and when someone wants out of an order a second step is time in which
    it can fill.
    """
    order = client.get_order(order_id)
    limit = "at market" if _limit(order) in ("market", "-") else f"limit {money(order.price)}"
    if getattr(order, "stop_price", None) is not None:
        limit = f"stop {money(order.stop_price)} then {limit}"
    what = order.symbol
    if order.instrument_type == "option":
        # '1 F $12.00 call 2026-12-11', or '2 F 2-leg option' for a spread.
        what += f" {order_kind(order)}"
        limit += " per share"
    summary = (
        f"{order_side(order)} {number(order.quantity)} {what}, {limit}, "
        f"placed {local_time(order.created_at)}"
    )
    if order.status not in OPEN_STATES:
        print(f"Order {order_id} is already {order.status}, so there is nothing to cancel.")
        print(f"  {summary}")
        return 1

    client.cancel_order(order_id)
    # A cancel is a request: the order takes a moment to leave the book,
    # and can fill first.
    for _ in range(attempts):
        if settle_seconds:
            time.sleep(settle_seconds)
        order = client.get_order(order_id)
        if order.status not in OPEN_STATES:
            break
    if order.status == "cancelled":
        print(f"CANCELLED: {summary}")
        if order.filled_quantity:
            print(
                f"  {number(order.filled_quantity)} had already filled at "
                f"{money(order.average_price)} and is not undone."
            )
        return 0
    print(f"Cancel requested, but the order is now {order.status}: {summary}")
    if order.filled_quantity:
        print(f"  Filled: {number(order.filled_quantity)} at {money(order.average_price)}")
    print(f"Check it with:  {program()} orders --symbol {order.symbol}")
    return 0 if order.status not in OPEN_STATES else 1


# ── Running one ──────────────────────────────────────────────────────


def run(command: Callable[..., int], **kwargs: Any) -> int:
    """Log in with the saved session and run a command, reporting failures plainly."""
    import pyhood
    from pyhood.client import PyhoodClient

    try:
        client = PyhoodClient(pyhood.login())
        return command(client, **kwargs)
    except UsageError as e:
        print(e, file=sys.stderr)
        return 2
    except AuthError as e:
        print(f"Not logged in: {e}", file=sys.stderr)
        print(f"Run: {program()} setup login", file=sys.stderr)
        return 1
    except PyhoodError as e:
        print(f"Robinhood request failed: {e}", file=sys.stderr)
        return 1
