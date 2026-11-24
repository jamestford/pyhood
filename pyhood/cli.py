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
            local_time(o.created_at), o.side, o.symbol, o.instrument_type, number(o.quantity),
            money(o.price), number(o.filled_quantity), money(o.average_price), o.status,
            o.order_id,
        ]
        for o in found
    ]
    print(table(
        ["PLACED", "SIDE", "SYMBOL", "TYPE", "ORDERED", "LIMIT", "FILLED", "AVG PRICE",
         "STATUS", "ORDER ID"],
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
    quantity: float,
    limit: float | None = None,
    time_in_force: str = "gfd",
    extended_hours: bool = False,
    confirm: str | None = None,
    settle_seconds: float = 2.0,
) -> int:
    """Preview a stock order, or place it when given its confirmation code.

    `limit` of None is a market order.
    """
    symbol = symbol.upper()
    kind = "market" if limit is None else f"{limit:.4f}"
    code = confirmation_code(side, symbol, f"{quantity:g}", kind, time_in_force, extended_hours)
    command = f"{program()} {side} {symbol} {quantity:g} " + (
        "--market" if limit is None else f"--limit {limit:g}"
    )
    if time_in_force != "gfd":
        command += f" --tif {time_in_force}"
    if extended_hours:
        command += " --extended-hours"

    # Checked before anything else, so a wrong code costs no requests.
    if confirm is not None and confirm != code:
        return _wrong_code()

    terms = "at market" if limit is None else f"limit {money(limit)}"
    duration = "good for day" if time_in_force == "gfd" else "good till cancelled"
    summary = f"{side.capitalize()} {number(quantity)} {symbol}, {terms}, {duration}"
    if extended_hours:
        summary += ", extended hours"

    if confirm is not None:
        place = client.buy_stock if side == "buy" else client.sell_stock
        try:
            order = place(
                symbol, quantity, price=limit, time_in_force=time_in_force,
                extended_hours=extended_hours,
            )
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
    reference = limit
    if reference is None:
        reference = (quote_now.ask if side == "buy" else quote_now.bid) or quote_now.price
    value = quantity * reference

    print("PREVIEW. Nothing has been sent.\n")
    print(f"  {summary}")
    label = "Estimated cost:" if side == "buy" else "Estimated proceeds:"
    print(f"  {label:<20}{money(value)}")
    print(f"  {symbol + ' now:':<20}{money(quote_now.price)} "
          f"(bid {money(quote_now.bid)}, ask {money(quote_now.ask)})")

    warnings = []
    if side == "buy":
        available = client.get_buying_power()
        print(f"  {'Buying power:':<20}{money(available)}")
        if value > available:
            warnings.append(
                "The estimated cost is more than your buying power. Robinhood is "
                "likely to reject this order."
            )
    else:
        held = sum(p.quantity for p in client.get_positions() if p.symbol.upper() == symbol)
        print(f"  {'You hold:':<20}{number(held)} {symbol}")
        if quantity > held:
            warnings.append(
                f"You hold {number(held)} {symbol}, fewer than this order sells. "
                "Robinhood is likely to reject it."
            )
    print(f"  {'Market open:':<20}{'yes' if client.is_market_open() else 'no'}")

    if limit is None:
        warnings.append(
            "A market order fills at the best price available when it arrives, "
            "which can differ from the quote above."
        )
    elif quote_now.price:
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
        "option", side, effect, symbol, expiration, f"{strike:g}", option_type, contracts,
        f"{limit:.4f}", time_in_force,
    )
    command = (
        f"{program()} {side}-option {symbol} --expires {expiration} --strike {strike:g} "
        f"--{option_type} --contracts {contracts} --limit {limit:g}"
    )
    if effect != default_effect:
        command += f" --to {effect}"
    if time_in_force != "gfd":
        command += f" --tif {time_in_force}"

    if confirm is not None and confirm != code:
        return _wrong_code()

    plural = "contract" if contracts == 1 else "contracts"
    name = f"{symbol} {money(strike)} {option_type} expiring {expiration}"
    duration = "good for day" if time_in_force == "gfd" else "good till cancelled"
    summary = (
        f"{side.capitalize()} to {effect} {contracts} {plural} of {name}, "
        f"limit {money(limit)} per share, {duration}"
    )

    if confirm is not None:
        place = client.buy_option if side == "buy" else client.sell_option
        try:
            order = place(
                symbol, strike, expiration, option_type, contracts, limit,
                position_effect=effect, time_in_force=time_in_force,
            )
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
        available = client.get_buying_power()
        print(f"  {'Buying power:':<20}{money(available)}")
        if value > available:
            warnings.append(
                "The estimated cost is more than your buying power. Robinhood is "
                "likely to reject this order."
            )
    else:
        held = sum(
            p.quantity for p in client.get_option_positions()
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
    limit = "at market" if order.price is None else f"limit {money(order.price)}"
    what = order.symbol
    if order.instrument_type == "option":
        what += " option " + ("contract" if order.quantity == 1 else "contracts")
    summary = (
        f"{order.side} {number(order.quantity)} {what}, {limit}, "
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
    except AuthError as e:
        print(f"Not logged in: {e}", file=sys.stderr)
        print(f"Run: {program()} setup login", file=sys.stderr)
        return 1
    except PyhoodError as e:
        print(f"Robinhood request failed: {e}", file=sys.stderr)
        return 1
