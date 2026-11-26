"""Show what Robinhood asks for during a login, without showing any values.

Run it with the installed pyhood, in a terminal of your own:

    ~/pyhood/bin/python scripts/login_trace.py

It logs in the same way `pyhood authorize` does, and prints one line for each
request: the address with IDs removed, the HTTP status, and the names and
types of the fields in the answer. The only values it prints are the ones that
say which kind of approval Robinhood wants and how far it has got. It never
prints a token, a password, an ID, a phone number or an email address.

If the login succeeds, the authorization is saved exactly as `pyhood
authorize` saves it.
"""

from __future__ import annotations

import getpass
import re
import sys
import time
from typing import Any

import requests

WAIT = 240

# Values that say what kind of approval is wanted. Everything else is shown
# as a field name and a type only.
SHOWN = {
    "type",
    "status",
    "challenge_status",
    "workflow_status",
    "result",
    "state_name",
    "sequence",
    "flow",
    "mfa_required",
    "mfa_type",
    "remaining_attempts",
    "remaining_retries",
    "detail",
    "error",
    "error_description",
}

ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{20,}|[0-9a-fA-F]{16,}")
START = time.monotonic()


def shape(value: Any, depth: int = 0) -> Any:
    """The names and types in a response, with values left out."""
    if isinstance(value, dict):
        if depth >= 4:
            return "{...}"
        described = {}
        for key, item in value.items():
            if key in SHOWN and isinstance(item, (str, int, bool)) and not ID.search(str(item)):
                # Digits in a sentence could be part of a phone number.
                described[key] = re.sub(r"\d{2,}", "#", item) if isinstance(item, str) else item
            else:
                described[key] = shape(item, depth + 1)
        return described
    if isinstance(value, list):
        return [shape(value[0], depth + 1)] if value else []
    return type(value).__name__


def trace(original: Any) -> Any:
    def request(self: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
        response = original(self, method, url, **kwargs)
        path = ID.sub("<id>", url.split("robinhood.com", 1)[-1])
        try:
            body = shape(response.json())
        except ValueError:
            body = f"(not JSON, {len(response.text)} characters)"
        print(f"[{time.monotonic() - START:5.0f}s] {method} {path} -> {response.status_code}")
        print(f"         {body}")
        return response

    return request


def main() -> int:
    from pyhood import __version__, login

    print(f"pyhood {__version__} login trace. No values are shown.")
    print("")
    username = input("Robinhood email or username: ").strip()
    password = getpass.getpass("Password (nothing shows as you type): ")
    if not username or not password:
        print("Nothing was entered, so nothing was sent.")
        return 1

    requests.Session.request = trace(requests.Session.request)  # type: ignore[method-assign]
    print("")
    print(f"Open the Robinhood app on your phone now. Waiting up to {WAIT} seconds.")
    print("")
    try:
        login(username, password, timeout=WAIT)
    except KeyboardInterrupt:
        print("")
        print("Stopped. Nothing was saved.")
        return 1
    except Exception as error:  # noqa: BLE001 - the point is to report whatever happens
        print("")
        print(f"The login ended with {type(error).__name__}: {error}")
        return 1
    print("")
    print("Authorized. The authorization is saved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
