"""Check that your Crypto API key pair works.

    python examples/verify_crypto.py

Read-only: account, holdings, quotes and tradability. Places no orders and
moves no funds. If this prints a fee tier and prices, the key pair is
registered and signing correctly.

Set up credentials first with:

    pyhood setup crypto
"""

import sys

from pyhood.crypto import CryptoClient, credentials_source
from pyhood.exceptions import APIError

SYMBOLS = ("BTC-USD", "ETH-USD")


def main() -> int:
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
    for quote in client.get_best_bid_ask(*SYMBOLS):
        print(f"    {quote.symbol:9} bid ${quote.bid:>12,.2f}   ask ${quote.ask:>12,.2f}")

    pairs = {p.symbol: p for p in client.get_trading_pairs()}
    tradable = sum(1 for p in pairs.values() if p.api_tradable)
    print(f"\nTrading pairs: {len(pairs)} total, {tradable} tradable through the API")

    holdings = client.get_holdings(account.account_number)
    print(f"Holdings: {len(holdings)}")

    print("\nCredentials work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
