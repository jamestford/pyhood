"""Option spreads: `pyhood spread`.

A spread is two to four option contracts traded together for one net
price. It asks and is confirmed as a single-leg option order is.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from typing import Any

from pyhood.cli import (
    NOT_PLACED,
    OPEN_STATES,
    UsageError,
    _ask_to_confirm,
    _expiry,
    _no_such_expiration,
    _wrong_code,
    confirmation_code,
    find_account,
    money,
    plain,
    program,
)
from pyhood.exceptions import OrderError, PyhoodError


def leg(text: str) -> dict[str, Any]:
    """An argparse type: 'buy:call:350' or 'sell:put:340:2026-12-18'.

    The parts are side, call or put, strike, and optionally an expiration
    for a leg that differs from the spread's --expires.
    """
    parts = text.strip().lower().split(":")
    if len(parts) not in (3, 4):
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a leg. Write SIDE:TYPE:STRIKE, as in buy:call:350"
        )
    side, option_type, strike = parts[:3]
    if side not in ("buy", "sell"):
        raise argparse.ArgumentTypeError(f"a leg's side is buy or sell, not {side!r}")
    if option_type not in ("call", "put"):
        raise argparse.ArgumentTypeError(f"a leg is a call or a put, not {option_type!r}")
    try:
        price = float(strike)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{strike!r} is not a strike price") from None
    if not price > 0:
        raise argparse.ArgumentTypeError("a strike price must be greater than zero")
    expiration = None
    if len(parts) == 4:
        try:
            date.fromisoformat(parts[3])
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"{parts[3]!r} is not a date in YYYY-MM-DD form"
            ) from None
        expiration = parts[3]
    return {"side": side, "option_type": option_type, "strike": price,
            "expiration": expiration}


def _leg_text(item: dict[str, Any], shared: str) -> str:
    text = f"{item['side']}:{item['option_type']}:{plain(item['strike'])}"
    return text if item["expiration"] == shared else f"{text}:{item['expiration']}"


def spread(
    client: Any,
    symbol: str,
    expires: str,
    legs: list[dict[str, Any]],
    contracts: int,
    debit: float | None = None,
    credit: float | None = None,
    effect: str = "open",
    time_in_force: str = "gfd",
    account: str | None = None,
    confirm: str | None = None,
    settle_seconds: float = 2.0,
) -> int:
    """Show a spread, or place it when given its confirmation code.

    `debit` is the most to pay and `credit` the least to accept, per share
    of the spread: one spread is 100 shares.
    """
    symbol = symbol.upper()
    if (debit is None) == (credit is None):
        raise UsageError("Give --debit PRICE or --credit PRICE, one of them.")
    if not 2 <= len(legs) <= 4:
        raise UsageError("A spread has two to four legs. Give --leg once for each.")
    legs = [{**item, "expiration": item["expiration"] or expires} for item in legs]
    described = sorted(
        (item["expiration"], item["option_type"], item["strike"], item["side"]) for item in legs
    )
    if len({d[:3] for d in described}) != len(described):
        raise UsageError("Two legs name the same contract.")

    direction = "debit" if debit is not None else "credit"
    price: float = debit if debit is not None else credit  # type: ignore[assignment]
    code = confirmation_code(
        "spread", symbol, described, contracts, direction, plain(price), effect,
        time_in_force, (account or "").strip().lower(),
    )
    command = f"{program()} spread {symbol} --expires {expires}"
    for item in legs:
        command += f" --leg {_leg_text(item, expires)}"
    command += f" --contracts {contracts} --{direction} {plain(price)}"
    if effect != "open":
        command += f" --to {effect}"
    if time_in_force != "gfd":
        command += f" --tif {time_in_force}"
    if account:
        command += f" --account {account}"

    if confirm is not None and confirm != code:
        return _wrong_code()

    account_number, account_label = find_account(client, account)
    plural = "spread" if contracts == 1 else "spreads"
    duration = "good for day" if time_in_force == "gfd" else "good till cancelled"
    summary = (
        f"{effect.capitalize()} {contracts} {symbol} {plural} for a {direction} of "
        f"{money(price)} per share, {duration}"
    )
    if account_label:
        summary += f", in {account_label}"

    if confirm is not None:
        options: dict[str, Any] = {"direction": direction, "time_in_force": time_in_force}
        if account_number:
            options["account_number"] = account_number
        order_legs = [
            {"strike": item["strike"], "expiration": item["expiration"],
             "option_type": item["option_type"], "side": item["side"], "effect": effect}
            for item in legs
        ]
        try:
            order = client.order_option_spread(symbol, contracts, price, order_legs, **options)
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
        print(f"  Order ID:  {order.order_id}")
        print(f"\nCheck it with:  {program()} orders --symbol {symbol}")
        if order.status in OPEN_STATES:
            print(f"Cancel it with: {program()} cancel {order.order_id}")
        return 0

    # Every leg has to be a real contract before a code is given out.
    expirations = client.get_options_expirations(symbol)
    chains: dict[str, Any] = {}
    priced = []
    for item in legs:
        when = item["expiration"]
        if when not in expirations:
            return _no_such_expiration(symbol, when, expirations)
        if when not in chains:
            chains[when] = client.get_options_chain(symbol, when)
        listed = chains[when].calls if item["option_type"] == "call" else chains[when].puts
        contract = next((c for c in listed if abs(c.strike - item["strike"]) < 0.0005), None)
        if contract is None:
            near = sorted(listed, key=lambda c: abs(c.strike - item["strike"]))[:6]
            print(
                f"{symbol} has no {money(item['strike'])} {item['option_type']} expiring {when}.",
                file=sys.stderr,
            )
            if near:
                strikes = ", ".join(money(c.strike) for c in sorted(near, key=lambda c: c.strike))
                print(f"The nearest strikes are: {strikes}", file=sys.stderr)
            return 1
        priced.append((item, contract))

    # What the spread is worth now, as a debit: paid for the legs bought,
    # less received for the legs sold. Negative means it pays a credit.
    def net(buy_field: str, sell_field: str) -> float:
        return sum(
            getattr(c, buy_field) if item["side"] == "buy" else -getattr(c, sell_field)
            for item, c in priced
        )

    at_marks = net("mark", "mark")
    to_take_now = net("ask", "bid")  # paying every ask, accepting every bid
    value = contracts * 100 * price
    spot = client.get_quote(symbol).price

    def as_price(amount: float) -> str:
        return f"{money(abs(amount))} {'debit' if amount >= 0 else 'credit'}"

    print(f"{NOT_PLACED}\n")
    print(f"  {summary}")
    for item, c in priced:
        print(
            f"    {item['side']:<4} {money(item['strike'])} {item['option_type']} "
            f"{item['expiration']}   mark {money(c.mark)} (bid {money(c.bid)}, "
            f"ask {money(c.ask)})"
        )
    label = "Estimated cost:" if direction == "debit" else "Estimated credit:"
    print(f"  {label:<20}{money(value)} ({contracts} {plural} x 100 shares x {money(price)})")
    print(f"  {'Spread now:':<20}about {as_price(at_marks)} at the marks, "
          f"{as_price(to_take_now)} to trade at once")
    print(f"  {symbol + ' now:':<20}{money(spot)}")
    nearest = min(item["expiration"] for item in legs)
    print(f"  {'Expires:':<20}{_expiry(nearest)}")

    warnings = []
    if direction == "debit":
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
    print(f"  {'Market open:':<20}{'yes' if client.is_market_open() else 'no'}")

    now_direction = "debit" if at_marks >= 0 else "credit"
    if now_direction != direction and abs(at_marks) >= 0.01:
        warnings.append(
            f"At current prices this spread is a {now_direction}, not a {direction}. "
            "Check which leg is bought and which is sold."
        )
    elif abs(at_marks) >= 0.01:
        gap = (price - abs(at_marks)) / abs(at_marks) * 100
        if abs(gap) >= 20:
            warnings.append(
                f"The {direction} of {money(price)} is {abs(gap):.0f}% "
                f"{'above' if gap > 0 else 'below'} the spread's price at the marks, "
                f"{money(abs(at_marks))}."
            )
    if direction == "credit" or any(item["side"] == "sell" for item in legs):
        warnings.append(
            "A spread includes a contract you sell. Robinhood needs approval for "
            "spreads, and may reject the order."
        )
    for warning in warnings:
        print(f"\n  Note: {warning}")

    _ask_to_confirm(command, code, value)
    return 0
