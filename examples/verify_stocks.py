"""Check that your session works, by reading live market data.

    python examples/verify_stocks.py

Read-only: quotes, an options chain and market hours. Places no orders and
touches no account data. If this prints prices, pyhood is authenticated and
working.

Set up a session first with:

    pyhood setup login
"""

import sys
from datetime import datetime

import pyhood
from pyhood.client import PyhoodClient
from pyhood.exceptions import AuthError

SYMBOLS = ("AAPL", "MSFT", "NVDA")


def main() -> int:
    try:
        session = pyhood.login()
    except AuthError as e:
        print(f"Not authenticated: {e}")
        print("Run: pyhood setup login")
        return 1

    client = PyhoodClient(session)

    print("Quotes")
    for symbol in SYMBOLS:
        q = client.get_quote(symbol)
        print(f"    {q.symbol:5} ${q.price:>8,.2f} {q.change_pct:+6.2f}%"
              f"   bid ${q.bid:,.2f} / ask ${q.ask:,.2f}")

    # Robinhood stops publishing greeks once a contract reaches its
    # expiration date, so skip today's, and pick the strike nearest the
    # money rather than whichever one sits in the middle of the chain.
    today = datetime.now().strftime("%Y-%m-%d")
    expirations = [e for e in client.get_options_expirations("AAPL") if e > today]
    expiration = expirations[0]
    chain = client.get_options_chain("AAPL", expiration)
    spot = client.get_quote("AAPL").price
    call = min(chain.calls, key=lambda c: abs(c.strike - spot))
    if call.delta is None:
        greeks = "greeks not published"
    else:
        greeks = f"delta {call.delta:+.3f}   IV {call.iv:.1%}"
    print("\nOptions")
    print(f"    AAPL {call.expiration} ${call.strike:g}C   mark ${call.mark:.2f}"
          f"   {greeks}")

    print(f"\nMarket open: {client.is_market_open()}")
    print("\nSession works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
