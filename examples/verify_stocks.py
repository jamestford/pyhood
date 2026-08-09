"""Check that your session works, by reading live market data.

    python examples/verify_stocks.py

Read-only: quotes, an options chain and market hours. Places no orders and
touches no account data. If this prints prices, pyhood is authenticated and
working.

Set up a session first with:

    pyhood setup login
"""

import sys

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

    expiration = client.get_options_expirations("AAPL")[0]
    chain = client.get_options_chain("AAPL", expiration)
    call = chain.calls[len(chain.calls) // 2]
    print("\nOptions")
    print(f"    AAPL {call.expiration} ${call.strike:g}C   mark ${call.mark:.2f}"
          f"   delta {call.delta:+.3f}   IV {call.iv:.1%}")

    print(f"\nMarket open: {client.is_market_open()}")
    print("\nSession works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
