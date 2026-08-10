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

pyhood needs **Python 3.10 or newer**. We recommend installing it into a virtual environment rather than your system Python:

```bash
python3.14 -m venv pyhood-env
source pyhood-env/bin/activate
python -m pip install --upgrade pip
python -m pip install pyhood
```
Substitute whichever interpreter you have — `python3.12`, `python3.13`, `python3.14` are all tested. On Windows the activate line is `pyhood-env\Scripts\activate`.

**Name the version explicitly.** A virtual environment inherits the version of the interpreter that creates it, and `python3` on macOS is still 3.9. Using bare `python3` there produces a 3.9 environment where the install fails with `no matching distribution found` — which reads like the package doesn't exist rather than a version problem. 

## Set Up Stocks, Options and Futures

```bash
pyhood setup login                 # store a session
python examples/verify_stocks.py   # confirm it works
```

`setup login` prompts for your username and password, then waits for you to approve the device in the Robinhood mobile app. The password is read without echoing and is never stored — only the resulting tokens are saved, to `~/.pyhood/session.json`, readable only by you.

[`examples/verify_stocks.py`](examples/verify_stocks.py) is a read-only check: if it prints prices, you are authenticated and working.

## Set Up Crypto

```bash
pyhood setup crypto                # generate and register a key pair
python examples/verify_crypto.py   # confirm it works
```

Robinhood does not issue you a key pair for the Crypto Trading API — you generate one and register the public half. `setup crypto` runs that exchange, writes both parts to `~/.pyhood/crypto.env` at mode `0600`, and then makes one signed read-only call to confirm Robinhood accepts them. The private key goes straight from generation to disk and is never displayed.

[`examples/verify_crypto.py`](examples/verify_crypto.py) re-runs that check any time, and reports which source your credentials resolve from — useful when a stale `export` is shadowing the file.

Run `pyhood setup` at any time to see what is configured. See [Setup](#setup) for the full walkthrough.

## Quick Start

Once `pyhood setup login` has stored a session, no credentials appear in your code at all:

```python
import pyhood
from pyhood.client import PyhoodClient

# Reuses the stored session, refreshing it if the access token has expired.
session = pyhood.login()

client = PyhoodClient(session)

quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")

positions = client.get_positions()
buying_power = client.get_buying_power()
```

`login()` with no arguments tries the cached session, then the refresh token. To force a refresh explicitly:

```python
session = pyhood.refresh()
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

## Setup

pyhood uses two unrelated kinds of credential, and `pyhood setup` configures either one.

| Command | Credential | Stored at |
|---|---|---|
| `pyhood setup login` | Session tokens for the main API — stocks, options, futures | `~/.pyhood/session.json` |
| `pyhood setup crypto` | Ed25519 key pair for the Crypto Trading API | `~/.pyhood/crypto.env` |
| `pyhood setup` | — | reports what is configured |

Both files are created `0600` inside a `0700` directory, with the mode applied at creation so the contents are never briefly readable by others.

**`setup login`** tries the stored session first — a valid or refreshable one needs no password at all. Only when that fails does it prompt for your username and password, handling MFA and device approval. The password is read without echoing and is never stored; only the resulting tokens are written.

**`setup crypto`** generates an Ed25519 key pair on your machine, prints only the public half for you to register with Robinhood, then reads the API key Robinhood issues and writes both to disk. The private key goes straight from generation to file — it is never displayed. Afterwards it makes one signed read-only call to confirm Robinhood actually accepts the pair, which is the step that catches a mistyped or placeholder key immediately rather than at your first order.

**`setup`** with no target reports what is configured — where credentials came from, file permissions, and whether the private key is a real Ed25519 key. It shows lengths and validity, never values, and makes no network calls.

```
$ pyhood setup
Session (main API — stocks, options, futures)
    /Users/you/.pyhood/session.json (refreshable, saved 1.2h ago)

Crypto API (official Crypto Trading API)
    source: file
    /Users/you/.pyhood/crypto.env
    api key: 43 chars
    private key: valid Ed25519, 32 bytes
```

Secrets are only ever read interactively. There are deliberately no `--password` or `--api-key` options: arguments are visible to every process on the machine via `ps` and are recorded by your shell.

## Authentication

Robinhood requires device approval on first login. After that, pyhood keeps the session alive automatically.

### First Login

Run `pyhood setup login` and approve the device prompt in the Robinhood mobile app when it appears. The session is saved to `~/.pyhood/session.json`.

To log in from code instead:

```python
import pyhood

session = pyhood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,
)
```

Prefer the setup command where you can — a password written into a script tends to end up committed.

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

# Credentials are read from ~/.pyhood/crypto.env or the environment
crypto = CryptoClient()

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

**Getting API keys.** Robinhood does not issue you a key pair — you generate one and register only the public half. The setup command walks through it:

```bash
pyhood setup crypto
```

It generates the key pair, shows you the **public** key to paste at [robinhood.com/account/crypto](https://robinhood.com/account/crypto) → API Trading → Add key, reads the **API key** Robinhood issues back, writes both to `~/.pyhood/crypto.env` at mode `0600`, and then makes one signed read-only call to confirm the pair works. The private key is never displayed.

If you would rather do it by hand, the file is a plain env file:

```
# ~/.pyhood/crypto.env  (chmod 600)
RH_CRYPTO_API_KEY=the-key-robinhood-issued
RH_CRYPTO_PRIVATE_KEY=the-private-key-you-generated
```

The private key is the credential — anyone holding it can trade your crypto, and unlike a session token it cannot be refreshed, only revoked. Environment variables take precedence over this file, so a stale export will silently shadow it; `pyhood setup` reports which source is in use.

Only pairs with `api_tradable` set can be ordered through the API — a pair can be tradable in the app but not here. See the [crypto documentation](https://jamestford.github.io/pyhood/crypto/) for details.

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
performance = client.get_portfolio_performance()

docs = client.get_documents(doc_type="account_statement")
```

`get_portfolio_historicals()` raises `APIError` — Robinhood retired that endpoint. `get_portfolio_performance()` returns the chart view model that replaced it, unmapped, since its y values are returns rather than equity.

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
| Option historicals and portfolio performance | Functional |
| Guided credential setup (`pyhood setup`) | Functional |
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
