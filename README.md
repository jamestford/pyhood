# pyhood

<div align="center">
<img src="assets/logo-tight.png" alt="pyhood logo" width="200">

**A modern Python client for the Robinhood API, built for scripts that need to stay authenticated.**
</div>

[![CI](https://github.com/jamestford/pyhood/actions/workflows/ci.yml/badge.svg)](https://github.com/jamestford/pyhood/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyhood.svg)](https://pypi.org/project/pyhood/)
[![Docs](https://img.shields.io/badge/docs-jamestford.github.io%2Fpyhood-blue)](https://jamestford.github.io/pyhood)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Security](https://github.com/jamestford/pyhood/actions/workflows/security.yml/badge.svg)](https://github.com/jamestford/pyhood/actions/workflows/security.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

pyhood is a modern, typed, maintained Python client for Robinhood. It supports stocks, options, retirement accounts, futures, banking, documents, research endpoints, and Robinhood's official Crypto Trading API. It is built for automation: authenticate once, persist a session safely, and renew it later without a password, device approval prompt, or human in the loop.

> pyhood is an unofficial client and is not affiliated with Robinhood. Use responsibly. This project is not financial advice.

## Install

```bash
pip install pyhood
```

## Quick Start

```python
import pyhood
from pyhood.client import PyhoodClient

# First login may require device approval in the Robinhood mobile app.
session = pyhood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,
)

client = PyhoodClient(session)

quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")

positions = client.get_positions()
buying_power = client.get_buying_power()
```

After the first approved login, pyhood can refresh the session without credentials:

```python
import pyhood

session = pyhood.refresh()
client = PyhoodClient(session)
```

## Why pyhood exists

pyhood began with a specific problem: unattended Robinhood scripts should not die just because a session expired.

The original Python Robinhood client, [robin_stocks](https://github.com/jmfernandes/robin_stocks), made Robinhood automation accessible to a large community and remains the best-known library in this space. But Robinhood's authentication flow has changed over time, and many users now run into the same failure mode: a script works for a few days, the session expires, and the next login waits for a device approval no one is there to tap. pyhood fixes that workflow. After the first approved login, pyhood stores refresh-token session data as JSON and can renew the session with:

```python
session = pyhood.refresh()
```

No username. No password. No device approval prompt.

That makes pyhood a better fit for cron jobs, scheduled portfolio scripts, dashboards, and automated trading systems that need to keep running without a human nearby.

## Why use pyhood?

- **Silent session refresh** - renew Robinhood sessions without credentials or device approval after the first login.
- **Typed responses** - dataclass responses and type hints instead of guessing through raw dictionaries.
- **Retirement accounts** - discover and trade in Traditional and Roth IRA accounts.
- **Official crypto API** - use Robinhood's official Crypto Trading API with API keys.
- **Futures support** - futures contracts, quotes, orders, positions, and P&L helpers.
- **Options-first coverage** - equity and index options, chains, Greeks, volume, open interest, and order helpers.
- **Safer session storage** - JSON session persistence instead of `pickle`.
- **Rate limiting and retries** - request throttling and retry behavior built in.
- **Clear auth errors** - explicit exceptions for timeouts, MFA, expired tokens, and device approval failures.
- **Maintained test suite** - CI across Python 3.10 through 3.13.

## How pyhood compares

Against [robin_stocks](https://github.com/jmfernandes/robin_stocks) and the actively maintained fork [robin_stocks_v2](https://github.com/DhruvaBansal00/robin_stocks_v2):

| Capability | pyhood | robin_stocks | robin_stocks_v2 |
|---|---:|---:|---:|
| Silent session refresh without credentials | Yes | No | No |
| JSON session storage | Yes | No, uses pickle | Yes |
| IRA / retirement accounts | Yes | No | No |
| Official Crypto Trading API | Yes | No | No |
| Futures contracts and quotes | Yes | No | Yes |
| Futures positions | Yes | No | Stubbed |
| IPO access | Yes | No | Yes |
| Typed dataclass responses | Yes | No | Partial |
| Index options: SPX, NDX, VIX, RUT, XSP | Yes | Partial | Yes |
| Order history date filtering | Yes | Yes | Yes |
| Minimum Python version | 3.10 | 3.9 | 3.10 |

Migrating from `robin_stocks`? See the [migration guide](docs/migrating-from-robin-stocks.md) for a function-by-function map.

## Authentication

Robinhood requires device approval on first login. After that, pyhood keeps the session alive automatically.

### First Login

1. Open the Robinhood mobile app.
2. Call `pyhood.login()`.
3. Approve the device prompt in the app.
4. pyhood saves the session to `~/.pyhood/session.json`.

```python
import pyhood

session = pyhood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,
)
```

### Staying Authenticated

```python
# Reuses cached session data.
session = pyhood.login(username="you@email.com", password="your_password")

# Or refresh explicitly with no credentials.
session = pyhood.refresh()
```

Access sessions have been observed to last several days. When the access token expires, pyhood refreshes it using the stored refresh token.

Device approval is only needed again if the refresh token itself expires or Robinhood invalidates the session.

### Error Handling

```python
from pyhood.exceptions import (
    AuthError,
    DeviceApprovalRequiredError,
    LoginTimeoutError,
    MFARequiredError,
    TokenExpiredError,
)

try:
    session = pyhood.login(username="...", password="...", timeout=90)
except LoginTimeoutError:
    print("Open Robinhood and approve the device, then try again.")
except MFARequiredError:
    code = input("Enter the code from SMS/email: ")
    session = pyhood.login(username="...", password="...", mfa_code=code)
except AuthError as e:
    print(f"Login failed: {e}")
```

### Rate Limits

Robinhood aggressively rate-limits authentication attempts.

If login fails:

- Do not retry immediately.
- Wait at least 5 minutes.
- Multiple failed attempts can temporarily lock API access.
- Each new login attempt may generate a new device approval request.

See the [rate limits documentation](https://jamestford.github.io/pyhood/rate-limits/) for details.

## Common Examples

### Options Chain

```python
chain = client.get_options_chain("SPX", expiration="2026-04-17")

for option in chain.calls:
    print(
        option.strike,
        option.implied_volatility,
        option.delta,
        option.open_interest,
    )
```

### IRA Trading

```python
accounts = client.get_all_accounts()

order = client.buy_option(
    symbol="NKE",
    strike=55.0,
    expiration="2026-04-02",
    option_type="call",
    quantity=3,
    price=1.60,
    account_number="YOUR_IRA_ACCOUNT",
)
```

See the [account documentation](https://jamestford.github.io/pyhood/account/) for IRA account discovery and limitations.

### Crypto Trading

```python
from pyhood.crypto import CryptoClient

crypto = CryptoClient(
    api_key="rh-api-...",
    private_key_base64="...",
)

quotes = crypto.get_best_bid_ask("BTC-USD", "ETH-USD")
account = crypto.get_account()

order = crypto.place_order(
    account_number=account.account_number,
    side="buy",
    order_type="market",
    symbol="BTC-USD",
    order_config={"asset_quantity": "0.001"},
)
```

Generate API keys at [robinhood.com/account/crypto](https://robinhood.com/account/crypto). See the [crypto documentation](https://jamestford.github.io/pyhood/crypto/) for details.

### Futures

```python
contract = client.get_futures_contract("ESH26")
quote = client.get_futures_quote("ESH26")
pnl = client.calculate_futures_pnl()

print(contract.name, quote.last_price, pnl)
```

See the [futures documentation](https://jamestford.github.io/pyhood/futures/) for details.

### Portfolio and Documents

```python
history = client.get_portfolio_historicals(
    account_number="123456",
    interval="day",
    span="year",
)

docs = client.get_documents(doc_type="account_statement")
```

## Feature Status

| Area | Status |
|---|---|
| Stocks and options market data | Functional |
| Equity and index options | Functional |
| Stock and option order management | Functional |
| Authentication with automatic refresh | Functional |
| Official crypto trading API | Functional |
| Futures contracts, quotes, orders, and P&L | Functional |
| IRA / retirement accounts | Functional |
| Banking, ACH transfers, and dividends | Functional |
| Watchlists | Functional |
| Markets and trading hours | Functional |
| Research, news, ratings, movers, and popularity | Functional |
| Portfolio and option historicals | Functional |
| Documents and statements | Functional |
| Day trades, margin calls, and deposit schedules | Functional |

## Documentation

- [Full documentation](https://jamestford.github.io/pyhood)
- [Migration guide](docs/migrating-from-robin-stocks.md)
- [Account documentation](https://jamestford.github.io/pyhood/account/)
- [Crypto documentation](https://jamestford.github.io/pyhood/crypto/)
- [Futures documentation](https://jamestford.github.io/pyhood/futures/)
- [Rate limits](https://jamestford.github.io/pyhood/rate-limits/)

## Contributing

Contributions are welcome, especially:

- endpoint coverage
- typed response models
- migration examples from `robin_stocks`
- documentation improvements
- tests for live-verified behavior

Please avoid opening pull requests that place real trades in tests.

## Acknowledgments

pyhood stands on the shoulders of the community that mapped Robinhood's unofficial API:

- [robin_stocks](https://github.com/jmfernandes/robin_stocks) by [Josh Fernandes](https://github.com/jmfernandes), the most widely used Python Robinhood library.
- [pyrh](https://github.com/robinhood-unofficial/pyrh), an early client that helped establish OAuth token refresh patterns.
- [Robinhood](https://github.com/sanko/Robinhood) by [Sanko](https://github.com/sanko), early unofficial endpoint documentation.

Those projects made Robinhood accessible to Python developers. pyhood continues that work with a focus on reliability, typed interfaces, and unattended automation.

## License

MIT
