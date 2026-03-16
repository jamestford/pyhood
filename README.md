# hood

A modern, reliable Python client for the Robinhood API.

Built for automated trading — with auth that doesn't break, proper error handling, and sane defaults.

## Why hood?

[robin_stocks](https://github.com/jmfernandes/robin_stocks) by [Josh Fernandes](https://github.com/jmfernandes) was the original Python library for Robinhood and served the community well. But it's effectively unmaintained — 300+ open issues, no releases since 2023, and auth that silently fails.

**hood** started from that foundation and rebuilds it for reliability:

- 🔐 **Auth that works** — Login timeouts, automatic token refresh, clear failure modes (no more infinite hangs)
- 🏷️ **Type hints everywhere** — Full type annotations, dataclass responses, IDE-friendly
- 🛡️ **Built-in rate limiting** — Never get throttled
- 📊 **Options-first** — Deep options chain support with Greeks, unusual activity detection
- 🧪 **Tested** — Actual tests, CI/CD, not "it works on my machine"

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

Robinhood requires **device approval** on first login and whenever your session token expires (~24 hours).

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

### Subsequent Logins

Once authenticated, hood reuses the cached token automatically:

```python
# Uses cached token — no device approval needed
session = hood.login(username="you@email.com", password="your_password")
```

The cached session lasts ~24 hours. When it expires, you'll need to approve again.

### Error Handling

hood raises specific exceptions so you know exactly what went wrong:

```python
from hood.exceptions import (
    LoginTimeoutError,        # Timed out waiting for device approval
    DeviceApprovalRequiredError,  # Approval prompt sent but not completed
    MFARequiredError,         # SMS/email code needed — pass mfa_code parameter
    AuthError,                # Generic auth failure
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
- See [RATE_LIMITS.md](RATE_LIMITS.md) for details

## Install

```bash
pip install hood
```

## Status

🚧 **Early development** — Core auth + market data modules are functional. Options trading and full order management in progress.

## Acknowledgments

This project builds on the work done by [Josh Fernandes](https://github.com/jmfernandes) and the [robin_stocks](https://github.com/jmfernandes/robin_stocks) community. Their library made Robinhood accessible to Python developers for years and laid the groundwork that hood continues from.

## License

MIT
