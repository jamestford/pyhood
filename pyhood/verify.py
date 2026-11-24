"""Read-only checks that a saved login works: `pyhood verify`.

These read live market data and place no orders. If they print prices,
pyhood is installed, authenticated and talking to Robinhood.
"""

from __future__ import annotations

from datetime import datetime

STOCK_SYMBOLS = ("AAPL", "MSFT", "NVDA")
CRYPTO_SYMBOLS = ("BTC-USD", "ETH-USD")


def verify_stocks() -> int:
    """Check the main session: quotes, an options chain and market hours."""
    import pyhood
    from pyhood.client import PyhoodClient
    from pyhood.exceptions import AuthError

    try:
        session = pyhood.login()
    except AuthError as e:
        print(f"Not authenticated: {e}")
        print("Run: pyhood setup login")
        return 1

    client = PyhoodClient(session)

    print("Quotes")
    for symbol in STOCK_SYMBOLS:
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


def verify_crypto() -> int:
    """Check the Crypto API key pair: account, quotes, pairs and holdings."""
    from pyhood.crypto import CryptoClient, credentials_source
    from pyhood.exceptions import APIError

    try:
        client = CryptoClient()
    except FileNotFoundError as e:
        print(f"No crypto credentials: {e}")
        print("Run: pyhood setup crypto")
        return 1

    print(f"Credentials source: {credentials_source()}")

    try:
        account = client.get_account()
    except APIError as e:
        print(f"\nRobinhood rejected the credentials: {e}")
        print("The public key may not be registered, or the API key may be wrong.")
        print("Run: pyhood setup crypto --force")
        return 1

    print(f"Account status: {account.status}   fee: {account.fee_tier}"
          f"   API tradable: {account.api_tradable}")

    print("\nQuotes")
    for quote in client.get_best_bid_ask(*CRYPTO_SYMBOLS):
        print(f"    {quote.symbol:9} bid ${quote.bid:>12,.2f}   ask ${quote.ask:>12,.2f}")

    pairs = {p.symbol: p for p in client.get_trading_pairs()}
    tradable = sum(1 for p in pairs.values() if p.api_tradable)
    print(f"\nTrading pairs: {len(pairs)} total, {tradable} tradable through the API")

    holdings = client.get_holdings(account.account_number)
    print(f"Holdings: {len(holdings)}")

    print("\nCredentials work.")
    return 0
