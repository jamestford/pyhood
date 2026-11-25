"""Check that your session works, by reading live market data.

    pyhood verify

This file runs the same check, for anyone working from a clone of the
repository:

    python examples/verify_stocks.py

Read-only: quotes, an options chain and market hours. Places no orders and
touches no account data. If this prints prices, pyhood is authenticated and
working.

Set up a session first with:

    pyhood authorize
"""

import sys

from pyhood.verify import verify_stocks

if __name__ == "__main__":
    sys.exit(verify_stocks())
