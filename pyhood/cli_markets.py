"""Crypto and futures commands: `pyhood crypto ...` and `pyhood futures ...`.

Crypto goes through Robinhood's official Crypto Trading API, which has its
own client and its own credentials (`pyhood setup crypto`). Buying and
selling work as stock orders do: a first step that sends nothing and prints a
confirmation code, then the same command with the code.

Futures can be read here: quotes, contract details, orders and realized
profit and loss. A futures order can be estimated, with Robinhood's own
margin, fees and verdict, but not placed: pyhood has not seen the request
that submits one.
"""

from __future__ import annotations

import re
import sys
import time
from collections.abc import Callable
from typing import Any

from pyhood.cli import (
    NOT_PLACED,
    UsageError,
    _ask_to_confirm,
    _wrong_code,
    as_json,
    confirmation_code,
    local_time,
    money,
    number,
    percent,
    plain,
    program,
    signed_money,
    table,
)
from pyhood.exceptions import PyhoodError

# States in which a crypto order can still fill, and so can be cancelled.
CRYPTO_OPEN_STATES = frozenset({"open", "partially_filled"})


def pair(symbol: str) -> str:
    """'BTC-USD' for 'btc' or 'BTC-USD'. Robinhood quotes crypto in dollars."""
    symbol = symbol.strip().upper()
    return symbol if "-" in symbol else f"{symbol}-USD"


def quantity_text(quantity: float) -> str:
    """A quantity as the API wants it: plain digits, never 1e-05."""
    return plain(quantity)


# ── Crypto: reading ──────────────────────────────────────────────────


def crypto_quote(client: Any, symbols: list[str], as_json_output: bool = False) -> int:
    """Best bid and ask for one or more coins."""
    wanted = [pair(s) for s in symbols]
    quotes = {q.symbol: q for q in client.get_best_bid_ask(*wanted)}
    missing = [s for s in wanted if s not in quotes]
    if as_json_output:
        print(as_json({s: quotes[s] for s in wanted if s in quotes}))
    elif quotes:
        print(table(
            ["SYMBOL", "BID", "ASK", "AS OF"],
            [[s, money(quotes[s].bid), money(quotes[s].ask), local_time(quotes[s].timestamp)]
             for s in wanted if s in quotes],
            right={1, 2},
        ))
        print(
            "\nRobinhood charges a fee on each crypto trade, on top of these prices. "
            f"To see it: {program()} crypto buy BTC 0.001 --market --ask"
        )
    for s in missing:
        print(f"No quote for {s}.", file=sys.stderr)
    return 1 if missing else 0


def crypto_holdings(client: Any, as_json_output: bool = False) -> int:
    """The coins the account holds, valued at the current bid."""
    account = client.get_account()
    holdings = [h for h in client.get_holdings(account.account_number) if h.quantity]
    quotes = {}
    if holdings:
        found = client.get_best_bid_ask(*[pair(h.asset_code) for h in holdings])
        quotes = {q.symbol: q for q in found}
    rows = []
    for h in holdings:
        q = quotes.get(pair(h.asset_code))
        price = q.bid if q else None
        rows.append({
            "asset": h.asset_code, "quantity": h.quantity, "available": h.available_quantity,
            "price": price, "value": None if price is None else h.quantity * price,
        })
    if as_json_output:
        print(as_json({"buying_power": account.buying_power, "holdings": rows}))
        return 0
    if rows:
        print(table(
            ["ASSET", "QUANTITY", "AVAILABLE", "PRICE", "VALUE"],
            [[r["asset"], number(r["quantity"]), number(r["available"]), money(r["price"]),
              money(r["value"])] for r in rows],
            right={1, 2, 3, 4},
        ))
        known = [r["value"] for r in rows if r["value"] is not None]
        print(f"\nTotal value: {money(sum(known))}")
    else:
        print("No crypto holdings.")
    print(f"Crypto buying power: {money(account.buying_power)}")
    return 0


def crypto_orders(client: Any, open_only: bool = False, as_json_output: bool = False) -> int:
    """Crypto orders, newest first."""
    account = client.get_account()
    found = sorted(
        client.get_orders(account.account_number),
        key=lambda o: o.created_at.timestamp() if o.created_at else 0.0, reverse=True,
    )
    if open_only:
        found = [o for o in found if o.status in CRYPTO_OPEN_STATES]
    if as_json_output:
        print(as_json(found))
        return 0
    if not found:
        print("No open crypto orders." if open_only else "No crypto orders.")
        return 0
    print(table(
        ["PLACED", "SIDE", "SYMBOL", "TYPE", "ORDERED", "LIMIT", "FILLED", "AVG PRICE", "FEE",
         "STATUS", "ORDER ID"],
        [[local_time(o.created_at), o.side, o.symbol, o.order_type, number(o.quantity),
          money(o.price), number(o.filled_quantity), money(o.average_filled_price),
          money(o.fee), o.status, o.order_id] for o in found],
        right={4, 5, 6, 7, 8},
    ))
    return 0


# ── Crypto: orders ───────────────────────────────────────────────────


def crypto_order(
    client: Any,
    side: str,
    symbol: str,
    quantity: float,
    limit: float | None = None,
    confirm: str | None = None,
    settle_seconds: float = 2.0,
) -> int:
    """Show a crypto order, or place it when given its confirmation code.

    `quantity` is in the coin, not dollars: 0.001 is a thousandth of a
    bitcoin. `limit` of None is a market order.
    """
    symbol = pair(symbol)
    asset = symbol.split("-")[0]
    kind = "market" if limit is None else plain(limit)
    code = confirmation_code("crypto", side, symbol, quantity_text(quantity), kind)
    command = f"{program()} crypto {side} {asset} {quantity_text(quantity)} " + (
        "--market" if limit is None else f"--limit {plain(limit)}"
    )
    if confirm is not None and confirm != code:
        return _wrong_code()

    terms = "at market" if limit is None else f"limit {money(limit)}"
    summary = f"{side.capitalize()} {quantity_text(quantity)} {asset}, {terms}"
    account = client.get_account()

    if confirm is not None:
        config = {"asset_quantity": quantity_text(quantity)}
        if limit is not None:
            config["limit_price"] = plain(limit)
        try:
            order = client.place_order(
                account.account_number, side, "market" if limit is None else "limit",
                symbol, config,
            )
        except PyhoodError as e:
            print(f"Robinhood did not accept the order: {e}", file=sys.stderr)
            return 1
        if settle_seconds:
            time.sleep(settle_seconds)
        try:
            order = client.get_order(account.account_number, order.order_id)
        except PyhoodError:
            pass
        print(f"PLACED: {summary}")
        print(f"  Status:    {order.status}")
        if order.filled_quantity:
            print(f"  Filled:    {number(order.filled_quantity)} at "
                  f"{money(order.average_filled_price)}")
        print(f"  Order ID:  {order.order_id}")
        print(f"\nCheck it with:  {program()} crypto orders")
        if order.status in CRYPTO_OPEN_STATES:
            print(f"Cancel it with: {program()} crypto cancel {order.order_id}")
        return 0

    # Matched by symbol, not taken as the first returned: a lookup that
    # ignores its filter would otherwise hand back another coin's rules.
    try:
        listed = client.get_trading_pairs(symbol)
    except PyhoodError:
        listed = []  # Robinhood answers an unknown symbol with an error
    rules = next((p for p in listed if p.symbol == symbol), None)
    if rules is None:
        raise UsageError(
            f"Robinhood has no trading pair {symbol}. Check the coin's symbol with: "
            f"{program()} crypto quote {asset}"
        )
    if not rules.api_tradable:
        raise UsageError(
            f"{symbol} cannot be traded through Robinhood's Crypto API, though it may "
            "be tradable in the app."
        )
    if rules.max_order_size and quantity > rules.max_order_size:
        raise UsageError(
            f"The largest {asset} order is {quantity_text(rules.max_order_size)}. "
            f"You asked for {quantity_text(quantity)}."
        )

    # 'ask' is what a buyer pays and 'bid' what a seller gets.
    estimate = client.get_estimated_price(symbol, "ask" if side == "buy" else "bid", quantity)
    market_price = estimate.ask_price if side == "buy" else estimate.bid_price
    value = quantity * (limit if limit is not None else market_price)

    print(f"{NOT_PLACED}\n")
    print(f"  {summary}")
    if side == "buy":
        print(f"  {'Estimated cost:':<20}{money(value + estimate.fee)} "
              f"({money(value)} plus a fee of about {money(estimate.fee)})")
    else:
        print(f"  {'Estimated proceeds:':<20}{money(value - estimate.fee)} "
              f"({money(value)} less a fee of about {money(estimate.fee)})")
    print(f"  {asset + ' now:':<20}{money(market_price)} to {side}")

    warnings = []
    if side == "buy":
        print(f"  {'Buying power:':<20}{money(account.buying_power)}")
        if value + estimate.fee > account.buying_power:
            warnings.append(
                "The estimated cost is more than your crypto buying power. Robinhood "
                "is likely to reject this order."
            )
    else:
        held = sum(
            h.available_quantity for h in client.get_holdings(account.account_number, asset)
            if h.asset_code == asset
        )
        print(f"  {'You hold:':<20}{number(held)} {asset} available")
        if quantity > held:
            warnings.append(
                f"You have {number(held)} {asset} available, less than this order sells. "
                "Robinhood is likely to reject it."
            )
    if rules.min_order_amount and value < rules.min_order_amount:
        warnings.append(
            f"This order is worth about {money(value)}, under Robinhood's minimum of "
            f"{money(rules.min_order_amount)} for {asset}. It is likely to be rejected."
        )
    if limit is None:
        warnings.append(
            "A market order fills at the best price available when it arrives, "
            "which can differ from the price above. Crypto trades at all hours."
        )
    elif market_price:
        gap = (limit - market_price) / market_price * 100
        if abs(gap) >= 5:
            warnings.append(
                f"The limit is {abs(gap):.1f}% {'above' if gap > 0 else 'below'} "
                f"the current price of {money(market_price)}."
            )
    if limit is not None:
        warnings.append("A crypto limit order stays open until it fills or you cancel it.")
    for warning in warnings:
        print(f"\n  Note: {warning}")

    _ask_to_confirm(command, code, value)
    return 0


def crypto_cancel(
    client: Any, order_id: str, settle_seconds: float = 1.0, attempts: int = 5,
) -> int:
    """Cancel an open crypto order, at once, and say what became of it."""
    account = client.get_account()
    order = client.get_order(account.account_number, order_id)
    limit = "at market" if order.price is None else f"limit {money(order.price)}"
    summary = (
        f"{order.side} {quantity_text(order.quantity)} {order.symbol}, {limit}, "
        f"placed {local_time(order.created_at)}"
    )
    if order.status not in CRYPTO_OPEN_STATES:
        print(f"Order {order_id} is already {order.status}, so there is nothing to cancel.")
        print(f"  {summary}")
        return 1
    client.cancel_order(order_id)
    for _ in range(attempts):
        if settle_seconds:
            time.sleep(settle_seconds)
        order = client.get_order(account.account_number, order_id)
        if order.status not in CRYPTO_OPEN_STATES:
            break
    if order.status in ("canceled", "cancelled"):
        print(f"CANCELLED: {summary}")
        if order.filled_quantity:
            print(f"  {number(order.filled_quantity)} had already filled and is not undone.")
        return 0
    print(f"Cancel requested, but the order is now {order.status}: {summary}")
    return 0 if order.status not in CRYPTO_OPEN_STATES else 1


# ── Futures: reading ─────────────────────────────────────────────────

# A contract code ends in a month letter and a two-digit year: ESZ26. A
# product, ES, does not.
CONTRACT_CODE = re.compile(r"^[A-Z0-9]+[FGHJKMNQUVXZ]\d{2}$")


def front_contract(client: Any, typed: str) -> tuple[str, str]:
    """Turn what was typed into a contract code, and a note if it was a product.

    'ESZ26' is returned as it is. 'ES' becomes the product's nearest active
    contract, since nobody can be expected to know which month is current.
    """
    symbol = typed.upper().lstrip("/")
    if CONTRACT_CODE.match(symbol):
        return symbol, ""
    contracts = client.get_futures_product_contracts(symbol)
    if not contracts:
        raise UsageError(f"{symbol} has no active futures contracts.")
    front = contracts[0]
    return front.symbol, f"{symbol}: the nearest contract is {front.symbol}, " \
                         f"expiring {front.expiration}."


def futures_quote(client: Any, symbols: list[str], as_json_output: bool = False) -> int:
    """Quotes for futures contracts, such as ESZ26, with the session's range.

    A product, such as ES, is quoted by its nearest contract.
    """
    resolved = [front_contract(client, s) for s in symbols]
    wanted = [symbol for symbol, _ in resolved]
    notes = [note for _, note in resolved if note]
    quotes = client.get_futures_quotes(wanted, include_fundamentals=True)
    missing = [s for s in wanted if s not in quotes]
    if as_json_output:
        print(as_json(quotes))
    elif quotes:
        rows = []
        for s in wanted:
            if s not in quotes:
                continue
            q = quotes[s]
            change = None
            if q.prev_close:
                change = (q.last_price - q.prev_close) / q.prev_close * 100
            rows.append([
                q.symbol, number(q.last_price), percent(change), number(q.bid), number(q.ask),
                number(q.high), number(q.low), number(q.prev_close), number(q.volume),
            ])
        for note in notes:
            print(note)
        print(table(
            ["SYMBOL", "LAST", "CHANGE", "BID", "ASK", "HIGH", "LOW", "PREV CLOSE", "VOLUME"],
            rows, right={1, 2, 3, 4, 5, 6, 7, 8},
        ))
        print(
            "\nPrices are in the contract's own points. For what a point is worth: "
            f"{program()} futures contract {wanted[0]}"
        )
    for s in missing:
        print(f"No futures quote for {s}.", file=sys.stderr)
    return 1 if missing else 0


def futures_contract(client: Any, symbol: str, as_json_output: bool = False) -> int:
    """What a futures contract is: its size, tick and expiration.

    Given a product, such as ES, lists the product's active contracts.
    """
    typed = symbol.upper().lstrip("/")
    if not CONTRACT_CODE.match(typed):
        contracts = client.get_futures_product_contracts(typed)
        if as_json_output:
            print(as_json(contracts))
            return 0
        if not contracts:
            print(f"{typed} has no active futures contracts.")
            return 1
        first = contracts[0]
        print(f"{typed} ({first.asset_class.replace('_', ' ') or '-'}), "
              f"{number(first.multiplier)} dollars per point")
        print(table(["CONTRACT", "EXPIRES"], [[c.symbol, c.expiration] for c in contracts]))
        print(f"\nThe first is the nearest. For one contract's details: "
              f"{program()} futures contract {first.symbol}")
        return 0
    contract = client.get_futures_contract(typed)
    if as_json_output:
        print(as_json(contract))
        return 0
    print(f"{contract.symbol}: {contract.name}")
    print(f"  {'Expires:':<16}{contract.expiration or '-'}")
    print(f"  {'Multiplier:':<16}{number(contract.multiplier)} "
          "(dollars per point)")
    tick = contract.tick_size
    worth = "" if tick is None else f" ({money(tick * contract.multiplier)} a contract)"
    print(f"  {'Smallest move:':<16}{number(tick)}{worth}")
    print(f"  {'Product:':<16}{contract.underlying or '-'} "
          f"({contract.asset_class.replace('_', ' ') or '-'})")
    print(f"  {'Status:':<16}{contract.status}")
    return 0


# What Robinhood's check says when it refuses, in plain words. These two
# have been seen; any other is printed in Robinhood's own words.
FUTURES_CHECK_RESULTS = {
    "VALIDATE_ORDER_RESULT_FAILURE_INSUFFICIENT_BP": "not enough buying power",
    "VALIDATE_ORDER_RESULT_FAILURE_INVALID_TICK": "the price is not one the contract trades at",
}


def futures_order(
    client: Any,
    side: str,
    symbol: str,
    quantity: int,
    limit: float | None = None,
    stop: float | None = None,
    time_in_force: str = "gfd",
    as_json_output: bool = False,
) -> int:
    """Estimate a futures order: what it ties up, what it costs, and whether
    Robinhood would take it. It cannot be placed from here.

    The margin, fees and verdict are Robinhood's own, from the two requests
    its order ticket makes before it lets an order be submitted.
    """
    if limit is not None and stop is not None:
        raise UsageError(
            "Robinhood offers limit, market and stop orders on futures, not a stop "
            "with a limit. Give --stop PRICE --market, or --limit PRICE."
        )
    code, note = front_contract(client, symbol)
    contract = client.get_futures_contract(code)
    check = client.check_futures_order(
        code, side, quantity, limit_price=limit, stop_price=stop, time_in_force=time_in_force,
    )
    if as_json_output:
        print(as_json(check))
        return 0
    quote = client.get_futures_quotes([code]).get(code)

    if stop is not None:
        terms = f"stop {number(stop)} then at market"
    elif limit is not None:
        terms = f"limit {number(limit)}"
    else:
        terms = "at market"
    duration = "good for day" if time_in_force == "gfd" else "good till cancelled"
    plural = "contract" if quantity == 1 else "contracts"

    print("ESTIMATE ONLY. pyhood cannot place futures orders. Nothing has been sent.\n")
    if note:
        print(f"  {note}")
    print(f"  {side.capitalize()} {quantity} {code} {plural}, {terms}, {duration}")
    if contract.name:
        print(f"  {'Contract:':<22}{contract.name}, expires {contract.expiration or '-'}")
    price = stop if stop is not None else limit if limit is not None else (
        quote.last_price if quote else None
    )
    if price is not None and contract.multiplier:
        print(
            f"  {'Position size:':<22}{money(quantity * contract.multiplier * price)} "
            f"({quantity} x {money(contract.multiplier)} a point x {number(price)})"
        )
    if quote:
        print(f"  {code + ' now:':<22}{number(quote.last_price)} "
              f"(bid {number(quote.bid)}, ask {number(quote.ask)})")
    print(f"  {'Margin required:':<22}{money(check.margin_required)}")
    fees = money(check.fees)
    if check.fees is not None and check.commission is not None:
        fees += f", including {money(check.commission)} commission"
    print(f"  {'Fees:':<22}{fees}")
    if check.buying_power_effect is not None:
        print(f"  {'Buying power effect:':<22}{signed_money(check.buying_power_effect)}")
    if check.buying_power_after is not None:
        print(f"  {'Buying power after:':<22}{signed_money(check.buying_power_after)}")

    if check.accepted is False:
        reason = FUTURES_CHECK_RESULTS.get(check.result) or (
            check.result.removeprefix("VALIDATE_ORDER_RESULT_").removeprefix("FAILURE_")
            .replace("_", " ").lower()
        )
        verdict = f"it would refuse this order: {reason}."
    elif check.accepted:
        verdict = "it would accept this order."
    else:
        verdict = f"{check.result or 'nothing'}, which pyhood cannot read."
    print(f"  {'Robinhood says:':<22}{verdict}")

    warnings = []
    tick = contract.tick_size
    for label, value in (("limit", limit), ("stop", stop)):
        if value is not None and tick:
            steps = value / tick
            if abs(steps - round(steps)) > 1e-6:
                warnings.append(
                    f"{code} moves in steps of {number(tick)}, and the {label} of "
                    f"{number(value)} is not one of them."
                )
    if limit is None and stop is None:
        warnings.append(
            "A market order trades at once at the best price available. Futures trade "
            "nearly around the clock."
        )
    if stop is not None and time_in_force == "gfd":
        warnings.append("This stop lasts for today's session only. Add --tif gtc to keep it.")
    for warning in warnings:
        print(f"\n  Note: {warning}")

    print(
        "\nThis is an estimate only, and there is no step that places it. To place this "
        "order, use the Robinhood app or Robinhood Legend."
    )
    return 0


def futures_orders(client: Any, as_json_output: bool = False) -> int:
    """Futures orders, with realized profit and loss on the ones that closed a position."""
    found = sorted(client.get_futures_orders(), key=lambda o: o.created_at or "", reverse=True)
    if as_json_output:
        print(as_json(found))
        return 0
    if not found:
        print("No futures orders.")
        return 0
    print(table(
        ["CREATED", "SIDE", "SYMBOL", "TYPE", "QUANTITY", "PRICE", "STATUS", "OPENS/CLOSES",
         "REALIZED P/L"],
        [[(o.created_at or "")[:16].replace("T", " "), o.side, o.symbol, o.order_type,
          number(o.quantity), number(o.price), o.status, o.direction.lower(),
          signed_money(o.realized_pnl)] for o in found],
        right={4, 5, 8},
    ))
    total = sum(o.realized_pnl for o in found if o.realized_pnl is not None)
    print(f"\nRealized profit and loss, all orders shown: {signed_money(total)}")
    return 0


def futures_positions(client: Any, as_json_output: bool = False) -> int:
    """Open futures positions, as Robinhood sends them."""
    found = client.get_futures_positions()
    if not found and not as_json_output:
        print("No open futures positions.")
        return 0
    # pyhood has never seen an open futures position, so it does not map
    # these onto fields it would be guessing at.
    print(as_json(found))
    return 0


# ── Running one ──────────────────────────────────────────────────────


def run_crypto(command: Callable[..., int], **kwargs: Any) -> int:
    """Open the crypto client and run a command, reporting failures plainly."""
    from pyhood.crypto import CryptoClient

    try:
        client = CryptoClient()
    except (FileNotFoundError, ValueError) as e:
        print(f"Crypto is not set up: {e}", file=sys.stderr)
        print(f"Run: {program()} setup crypto", file=sys.stderr)
        return 1
    try:
        return command(client, **kwargs)
    except UsageError as e:
        print(e, file=sys.stderr)
        return 2
    except PyhoodError as e:
        print(f"Robinhood request failed: {e}", file=sys.stderr)
        return 1
