"""Check the watchlist methods against your account.

    python examples/verify_watchlists.py [list name]

Lists your watchlists, then adds one stock to a list and removes it again,
reading the list back after each step. It asks before changing anything;
answer anything but "y" to stop after the read-only part.

The list defaults to 'My First List'. The stock is the first of a few
well-known tickers that is not already on it, so nothing you put there is
touched.

Set up a session first with:

    pyhood authorize
"""

import sys
import time

import pyhood
from pyhood.client import PyhoodClient
from pyhood.exceptions import AuthError, SymbolNotFound

CANDIDATES = ("F", "T", "KO", "PFE", "GE")


def main() -> int:
    try:
        session = pyhood.login()
    except AuthError as e:
        print(f"Not authenticated: {e}")
        print("Run: pyhood authorize")
        return 1

    client = PyhoodClient(session)
    name = sys.argv[1] if len(sys.argv) > 1 else "My First List"

    print("Watchlists")
    for watchlist in client.get_watchlists():
        print(f"    {watchlist.name:30} {len(watchlist.symbols):>4} symbols")

    try:
        before = client.get_watchlist(name)
    except SymbolNotFound as e:
        print(e)
        return 1

    symbol = next((s for s in CANDIDATES if s not in before.symbols), None)
    if symbol is None:
        print(f"Every test ticker is already on {name!r}, so there is nothing "
              "safe to add and remove.")
        return 1

    question = f"\nAdd {symbol} to {name!r}, then remove it again? [y/N] "
    if input(question).strip().lower() != "y":
        print("Stopped. Nothing changed.")
        return 0

    client.add_to_watchlist([symbol], name)
    time.sleep(1)
    added = symbol in client.get_watchlist(name).symbols
    print(f"    add_to_watchlist:      {'ok' if added else 'FAILED'}"
          f" ({symbol} {'is' if added else 'is not'} on the list)")

    client.remove_from_watchlist([symbol], name)
    time.sleep(1)
    after = client.get_watchlist(name)
    removed = symbol not in after.symbols
    print(f"    remove_from_watchlist: {'ok' if removed else 'FAILED'}"
          f" ({symbol} {'is gone' if removed else 'is still there'})")

    unchanged = sorted(after.symbols) == sorted(before.symbols)
    print(f"    list back as it was:   {'ok' if unchanged else 'NO, check it in the app'}")
    return 0 if added and removed and unchanged else 1


if __name__ == "__main__":
    sys.exit(main())
