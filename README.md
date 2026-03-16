# hood

[![CI](https://github.com/jamestford/hood/actions/workflows/ci.yml/badge.svg)](https://github.com/jamestford/hood/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-jamestford.github.io%2Fhood-blue)](https://jamestford.github.io/hood)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-79%25-yellow.svg)](#)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A modern, reliable Python client for the Robinhood API.

Built for automated trading — with auth that doesn't break, proper error handling, and sane defaults.

## Why hood?

- 🔐 **Auth that just works** — Login with timeouts, automatic token refresh, and session persistence. Authenticate once, stay connected for days. No more scripts that hang forever waiting for device approval.
- 🔄 **Automatic token refresh** — hood uses OAuth refresh tokens to renew your session silently — no credentials, no device approval, no human in the loop. Built for unattended automation.
- 🏷️ **Type hints everywhere** — Full type annotations, dataclass responses, IDE-friendly. No more guessing what's in a dict.
- 🛡️ **Built-in rate limiting** — Automatic request throttling and retry logic so you don't get locked out.
- 📊 **Options-first** — Deep options chain support with Greeks, volume/OI analysis, and earnings integration.
- 🧪 **Tested and maintained** — 58+ tests, CI across Python 3.10-3.13, linted with ruff. If it breaks, we know immediately.

## Quick Start

```python
import hood
from hood.client import HoodClient

# Login (with timeout — never hangs)
session = hood.login(username="you@email.com", password="...", timeout=90)
client = HoodClient(session)

# Stock data
quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")

# Options chains
chain = client.get_options_chain("AAPL", expiration="2026-04-17")
for option in chain.calls:
    print(f"  {option.strike} call | IV: {option.iv:.0%} | Delta: {option.delta:.2f}")

# Account
positions = client.get_positions()
balance = client.get_buying_power()
```

## Authentication

Robinhood requires **device approval** on first login. After that, hood keeps your session alive automatically.

### First Login

1. Have the **Robinhood mobile app** open on your phone
2. Call `hood.login()` — it will trigger a device approval request
3. Tap **"Yes, it's me"** in the Robinhood app when prompted
4. hood saves the session token to `~/.hood/session.json` for reuse

```python
import hood

# First login — will wait up to 90s for you to approve on phone
session = hood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,  # seconds to wait for device approval
)
```

### Staying Authenticated

Once you've approved the device, hood handles the rest:

```python
# Reuses cached session — no approval needed
session = hood.login(username="you@email.com", password="your_password")

# Or refresh explicitly — no credentials needed at all
session = hood.refresh()
```

Sessions last several days (observed 5-8 days). When the access token expires, hood automatically refreshes it using the stored refresh token — **no device approval, no credentials, no human interaction**. This is what makes hood safe for automated scripts and cron jobs.

Device approval is only needed again if the refresh token itself expires (typically much longer than the access token).

### Error Handling

hood raises specific exceptions so you know exactly what went wrong:

```python
from hood.exceptions import (
    LoginTimeoutError,            # Timed out waiting for device approval
    DeviceApprovalRequiredError,  # Approval prompt sent but not completed
    MFARequiredError,             # SMS/email code needed — pass mfa_code parameter
    TokenExpiredError,            # Refresh token expired — full re-login needed
    AuthError,                    # Generic auth failure
)

try:
    session = hood.login(username="...", password="...", timeout=90)
except LoginTimeoutError:
    print("Open Robinhood app and approve the device, then try again")
except MFARequiredError:
    code = input("Enter the code from SMS/email: ")
    session = hood.login(username="...", password="...", mfa_code=code)
except AuthError as e:
    print(f"Login failed: {e}")
```

### ⚠️ Rate Limits

Robinhood aggressively rate-limits authentication. If login fails:

- **Do NOT retry immediately** — wait at least 5 minutes
- 2-3 failed attempts will lock out your account's API access for 5-10 minutes
- Each login attempt generates a new device approval — old approvals don't carry over
- See the [Rate Limits](https://jamestford.github.io/hood/rate-limits/) documentation for details

## Install

```bash
pip install hood
```

## Status

🚧 **Early development** — Core auth, token refresh, and market data modules are functional. Options trading and full order management in progress.

## Acknowledgments

hood stands on the shoulders of the community that figured out Robinhood's unofficial API:

- [**robin_stocks**](https://github.com/jmfernandes/robin_stocks) by [Josh Fernandes](https://github.com/jmfernandes) — The most widely used Python library for Robinhood. Its auth flow, endpoint mapping, and API patterns laid the groundwork that hood builds from.
- [**pyrh**](https://github.com/robinhood-unofficial/pyrh) by [Robinhood Unofficial](https://github.com/robinhood-unofficial) — An early Python client that pioneered OAuth token refresh and session management patterns for the Robinhood API.
- [**Robinhood**](https://github.com/sanko/Robinhood) by [Sanko](https://github.com/sanko) — The original unofficial API documentation that mapped out Robinhood's endpoints and made all of these libraries possible.

These projects made Robinhood accessible to developers. hood continues that mission with a focus on reliability and automation.

## License

MIT
