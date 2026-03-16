"""hood — A modern, reliable Python client for the Robinhood API."""

__version__ = "0.1.0"

from hood.auth import login, logout
from hood.client import HoodClient

__all__ = ["login", "logout", "HoodClient"]
