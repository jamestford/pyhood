"""hood — A modern, reliable Python client for the Robinhood API."""

__version__ = "0.1.0"

from pyhood.auth import login, logout, refresh
from pyhood.backtest import Backtester, BacktestResult
from pyhood.client import PyhoodClient
from pyhood.crypto import CryptoClient

__all__ = [
    "login", "logout", "refresh", "PyhoodClient", "CryptoClient",
    "Backtester", "BacktestResult"
]
