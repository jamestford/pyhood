"""Check that your Crypto API key pair works.

    pyhood verify crypto

This file runs the same check, for anyone working from a clone of the
repository:

    python examples/verify_crypto.py

Read-only: account, holdings, quotes and tradability. Places no orders and
moves no funds. If this prints a fee tier and prices, the key pair is
registered and signing correctly.

Set up credentials first with:

    pyhood setup crypto
"""

import sys

from pyhood.verify import verify_crypto

if __name__ == "__main__":
    sys.exit(verify_crypto())
