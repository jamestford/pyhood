"""pyhood — A modern, reliable Python client for the Robinhood API."""

__version__ = "0.16.0"

# The two checks below turn the errors a misplaced install produces into
# ones that say what to do. This file must stay importable on old Pythons
# for the first check to be reached, so nothing above or inside it may use
# syntax newer than Python 3.6.
import sys as _sys

if _sys.version_info < (3, 10):  # noqa: UP036 - the point is to run on older Pythons
    raise ImportError(
        f"pyhood requires Python 3.10 or newer, and this is Python "
        f"{_sys.version_info[0]}.{_sys.version_info[1]} ({_sys.executable}). "
        "If pyhood is already installed, run the script with `pyhood run "
        "script.py`, which uses the right Python. Otherwise install it: "
        "https://jamestford.github.io/pyhood/getting-started/"
    )

try:
    from pyhood.auth import login, logout, refresh
    from pyhood.client import PyhoodClient
    from pyhood.crypto import CryptoClient
except ModuleNotFoundError as _error:
    if _error.name in ("requests", "dotenv", "nacl", "cryptography"):
        raise ImportError(
            f"pyhood's dependency '{_error.name}' is not installed for this "
            f"Python ({_sys.executable}). This usually means pyhood is being "
            "imported from a source folder instead of an install. Do not "
            "install the dependency by hand. If pyhood is already installed, "
            "run the script with `pyhood run script.py`. Otherwise install "
            "pyhood itself: https://jamestford.github.io/pyhood/getting-started/"
        ) from _error
    raise

__all__ = [
    "login", "logout", "refresh", "PyhoodClient", "CryptoClient",
]
