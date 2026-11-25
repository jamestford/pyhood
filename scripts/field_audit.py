"""Find response fields pyhood reads that Robinhood never sends.

    python scripts/field_audit.py          # problems only
    python scripts/field_audit.py --all    # every method audited

Run it before a release. The unit tests mock Robinhood's responses, so a
parser that reads a field Robinhood does not send passes them as long as
the mock has the same made-up field. This runs the read-only methods
against a live account instead, records every key the parsers ask for, and
reports the ones that were never there.

It is safe to run and safe to paste the output of:

- POST and DELETE are blocked. Only GET requests are made.
- It prints key names and counts, never values. Keys that look like IDs
  are masked.

A field reported MISSING is one of three things: a bug in a parser, a
field Robinhood sends only sometimes (add it to EXPECTED with the reason),
or a fallback for an older response shape.

Methods whose endpoints return nothing for your account, such as dividends
on an account that has never been paid one, cannot be audited. They are
listed at the end.

Set up a session first with:

    pyhood authorize
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import date

import pyhood
from pyhood.client import PyhoodClient
from pyhood.exceptions import AuthError

# Fields the parsers ask for that are legitimately absent, with the reason.
# Keyed by (method, field path).
EXPECTED: dict[tuple[str, str], str] = {
    ("get_stock_orders", "results[].legs"):
        "stock orders have no legs; the check filters option orders out",
    ("get_futures_quote", "data[].data.displaySymbol"):
        "contracts have displaySymbol, quotes have symbol; one helper reads both",
}

# The pagination cursor, absent rather than null on some endpoints' last page.
IGNORED_KEYS = {"next"}

# (method, field path) -> [times asked for, times present, times non-null]
SEEN: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
# (method, path) -> keys actually present at that path
PRESENT: dict[tuple[str, str], set[str]] = defaultdict(set)
ERRORS: list[tuple[str, str, str]] = []
EMPTY: list[str] = []
LABEL = ["?"]

# UUIDs, and any run of six or more letters and digits that has a digit in
# it, which covers account numbers and tokens. Field names survive: they
# use underscores, and the camelCase ones have no digits.
ID_LIKE = re.compile(r"[0-9a-f]{8}-[0-9a-f-]{27}|\b(?=[A-Za-z]*\d)[0-9A-Za-z]{6,}\b")


def mask(text: object) -> str:
    return ID_LIKE.sub("<id>", str(text))


def wrap(value, path):
    if isinstance(value, (Tracked, TrackedList)):
        return value
    if isinstance(value, dict):
        return Tracked(value, path)
    if isinstance(value, list):
        return TrackedList(value, path + "[]")
    return value


class Tracked(dict):
    """A dict that records every key it is asked for."""

    def __init__(self, data, path):
        super().__init__(data)
        self._path = path
        PRESENT[(LABEL[0], path)].update(str(k) for k in data)

    def _child(self, key):
        return f"{self._path}.{key}" if self._path else str(key)

    def _note(self, key):
        if key in IGNORED_KEYS:
            return
        record = SEEN[(LABEL[0], self._child(key))]
        record[0] += 1
        if dict.__contains__(self, key):
            record[1] += 1
            if dict.__getitem__(self, key) is not None:
                record[2] += 1

    def __getitem__(self, key):
        self._note(key)
        return wrap(dict.__getitem__(self, key), self._child(key))

    def get(self, key, default=None):
        self._note(key)
        if dict.__contains__(self, key):
            return wrap(dict.__getitem__(self, key), self._child(key))
        return default

    def __contains__(self, key):
        self._note(key)
        return dict.__contains__(self, key)


class TrackedList(list):
    def __init__(self, data, path):
        super().__init__(data)
        self._path = path

    def __getitem__(self, index):
        value = list.__getitem__(self, index)
        if isinstance(index, slice):
            return TrackedList(value, self._path)
        return wrap(value, self._path)

    def __iter__(self):
        for value in list.__iter__(self):
            yield wrap(value, self._path)


def blocked(*args, **kwargs):
    raise RuntimeError("write blocked by the audit")


def front_quarterly(root: str = "ES") -> str:
    """The next quarterly futures symbol at least a month out, e.g. 'ESZ26'."""
    today = date.today()
    for offset in range(1, 13):
        month = (today.month - 1 + offset) % 12 + 1
        year = today.year + (today.month - 1 + offset) // 12
        if month in (3, 6, 9, 12):
            return f"{root}{'HMUZ'[month // 3 - 1]}{year % 100:02d}"
    raise AssertionError("unreachable")


def run(label, fn, expect_data=True):
    """Call one client method under a label, recording errors."""
    LABEL[0] = label
    try:
        result = fn()
    except Exception as e:  # noqa: BLE001 - report every failure, keep going
        ERRORS.append((label, type(e).__name__, mask(e)[:110]))
        return None
    if expect_data and isinstance(result, (list, dict)) and not result:
        EMPTY.append(label)
    return result


def audit(c: PyhoodClient) -> None:
    today = date.today().isoformat()
    year_start = f"{date.today().year}-01-01"
    future = front_quarterly()

    run("get_quote", lambda: c.get_quote("AAPL", include_fundamentals=True))
    run("get_quotes", lambda: c.get_quotes(["AAPL", "MSFT"], include_fundamentals=True))
    run("get_fundamentals", lambda: c.get_fundamentals("AAPL"))
    run("get_fundamentals_batch", lambda: c.get_fundamentals_batch(["AAPL", "MSFT"]))
    expirations = run("get_options_expirations", lambda: c.get_options_expirations("AAPL")) or []
    chain = None
    if len(expirations) > 2:
        # Not the nearest expiration: greeks are null on expiration day.
        chain = run("get_options_chain", lambda: c.get_options_chain("AAPL", expirations[2]))
    run("get_stock_historicals", lambda: c.get_stock_historicals("AAPL", span="week"))
    run("get_stock_historicals_batch",
        lambda: c.get_stock_historicals_batch(["AAPL", "MSFT"], span="week"))
    for symbol in ("AAPL", "NVDA"):
        run("get_earnings", lambda s=symbol: c.get_earnings(s, lookahead_days=120),
            expect_data=False)
    run("get_ratings", lambda: c.get_ratings("AAPL"))
    run("get_news", lambda: c.get_news("AAPL"))
    run("get_movers", lambda: c.get_movers("up"))
    for symbol in ("AAPL", "NVDA"):
        run("get_splits", lambda s=symbol: c.get_splits(s))
    run("get_portfolio_performance", lambda: c.get_portfolio_performance())
    if chain and chain.calls:
        middle = chain.calls[len(chain.calls) // 2]
        run("get_option_historicals",
            lambda: c.get_option_historicals(middle.option_id, span="week"))
    run("get_documents", lambda: c.get_documents())
    run("get_day_trades", lambda: c.get_day_trades())
    run("get_margin_calls", lambda: c.get_margin_calls())
    run("get_deposit_schedules", lambda: c.get_deposit_schedules())
    run("get_user_profile", lambda: c.get_user_profile())
    run("get_bank_accounts", lambda: c.get_bank_accounts())
    run("get_transfers", lambda: c.get_transfers())
    run("get_card_transactions", lambda: c.get_card_transactions())
    run("get_watchlists", lambda: c.get_watchlists())
    run("get_markets", lambda: c.get_markets())
    run("get_market_hours", lambda: c.get_market_hours("XNYS", today))
    run("is_market_open", lambda: c.is_market_open())
    run("get_dividends", lambda: c.get_dividends())
    run("get_all_accounts", lambda: c.get_all_accounts())
    run("get_positions", lambda: c.get_positions())
    run("get_option_positions", lambda: c.get_option_positions(nonzero=False))
    run("get_buying_power", lambda: c.get_buying_power())
    run("get_stock_orders", lambda: c.get_stock_orders(start_date=year_start))
    run("get_option_orders", lambda: c.get_option_orders())
    run("get_interest_payments", lambda: c.get_interest_payments())
    run("get_margin_interest", lambda: c.get_margin_interest())
    run("get_subscription_fees", lambda: c.get_subscription_fees())
    run("get_unified_transfers", lambda: c.get_unified_transfers())
    run("get_futures_account_id", lambda: c.get_futures_account_id())
    run("get_futures_contract", lambda: c.get_futures_contract(future))
    run("get_futures_quote", lambda: c.get_futures_quote(future, include_fundamentals=True))
    run("get_futures_orders", lambda: c.get_futures_orders())
    run("get_futures_positions", lambda: c.get_futures_positions())


def report(show_all: bool) -> int:
    by_label: dict[str, list[tuple[str, int, int, int]]] = defaultdict(list)
    for (label, key), (asked, present, nonnull) in sorted(SEEN.items()):
        by_label[label].append((key, asked, present, nonnull))

    problems = 0
    print("FIELDS READ BUT NEVER PRESENT")
    for label, rows in by_label.items():
        missing = [r for r in rows if r[2] == 0 and (label, r[0]) not in EXPECTED]
        expected = [r for r in rows if r[2] == 0 and (label, r[0]) in EXPECTED]
        always_null = [r for r in rows if r[2] > 0 and r[3] == 0]
        if not (missing or show_all):
            continue
        print(f"\n{label}  ({len(rows)} fields read)")
        for key, asked, _, _ in missing:
            problems += 1
            path = key.rsplit(".", 1)[0] if "." in key else ""
            have = sorted(mask(k) for k in PRESENT.get((label, path), ()))
            print(f"  MISSING   {mask(key)}  (asked for {asked}x)")
            if have:
                print(f"            keys there: {', '.join(have)[:400]}")
        if show_all:
            for key, _, _, _ in expected:
                print(f"  expected  {key}: {EXPECTED[(label, key)]}")
            for key, _, present, _ in always_null:
                print(f"  null      {mask(key)}  (present {present}x, always null)")
    if not problems:
        print("\n  none")

    print("\nCALLS THAT RAISED")
    for label, kind, message in ERRORS:
        print(f"  {label}: {kind}: {message}")
    if not ERRORS:
        print("  none")

    print("\nNOT AUDITED, NO DATA ON THIS ACCOUNT")
    print(f"  {', '.join(sorted(set(EMPTY))) or 'none'}")

    print(f"\n{len(by_label)} methods audited, {len(SEEN)} fields tracked, "
          f"{problems} missing, {len(ERRORS)} calls raised.")
    return 1 if problems or ERRORS else 0


def main() -> int:
    try:
        session = pyhood.login()
    except AuthError as e:
        print(f"Not authenticated: {e}")
        print("Run: pyhood authorize")
        return 1

    client = PyhoodClient(session)
    real_get = session.get
    session.get = lambda url, params=None, **kw: wrap(real_get(url, params=params, **kw), "")
    session.post = blocked
    session.delete = blocked

    audit(client)
    return report(show_all="--all" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
