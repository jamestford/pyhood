# pyhood

<div align="center">
<img src="assets/logo-tight.png" alt="pyhood logo" width="200">

**A modern, reliable Python client for the Robinhood API.**
</div>

[![CI](https://github.com/jamestford/pyhood/actions/workflows/ci.yml/badge.svg)](https://github.com/jamestford/pyhood/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyhood.svg)](https://pypi.org/project/pyhood/)
[![Docs](https://img.shields.io/badge/docs-jamestford.github.io%2Fpyhood-blue)](https://jamestford.github.io/pyhood)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-79%25-yellow.svg)](#)
[![Security](https://github.com/jamestford/pyhood/actions/workflows/security.yml/badge.svg)](https://github.com/jamestford/pyhood/actions/workflows/security.yml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

A modern, reliable Python client for the Robinhood API.

Built for automated trading — with auth that doesn't break, proper error handling, and sane defaults.

## Why pyhood?

- 🪙 **Dual API support** — The only Python library that wraps both Robinhood's unofficial stocks/options API and their official Crypto Trading API. One library, full coverage.

- 🔐 **Auth that just works** — Login with timeouts, automatic token refresh, and session persistence. Authenticate once, stay connected for days. No more scripts that hang forever waiting for device approval.
- 🔄 **Automatic token refresh** — pyhood uses OAuth refresh tokens to renew your session silently — no credentials, no device approval, no human in the loop. Built for unattended automation.
- 🏷️ **Type hints everywhere** — Full type annotations, dataclass responses, IDE-friendly. No more guessing what's in a dict.
- 🛡️ **Built-in rate limiting** — Automatic request throttling and retry logic so you don't get locked out.
- 📊 **Options-first** — Deep options chain support with Greeks, volume/OI analysis, and earnings integration. Supports both equity and index options (SPX, NDX, VIX, RUT).
- 📈 **Futures trading** — Contract details, real-time quotes, order history, and P&L calculation for Robinhood futures.
- 🏦 **IRA/Retirement accounts** — Trade stocks and options in Traditional and Roth IRAs. The only Python Robinhood library with retirement account support.
- 💰 **Banking & dividends** — Query ACH transfers, linked bank accounts, and dividend history.
- 📋 **Watchlists** — Create, manage, and modify your Robinhood watchlists programmatically.
- 🧪 **Tested and maintained** — 197 tests, CI across Python 3.10-3.13, linted with ruff. If it breaks, we know immediately.

## Quick Start

```python
import pyhood
from pyhood.client import PyhoodClient

# Login (with timeout — never hangs)
session = pyhood.login(username="you@email.com", password="...", timeout=90)
client = PyhoodClient(session)

# Stock data
quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")

# Options chains (works for equities and indexes)
chain = client.get_options_chain("SPX", expiration="2026-04-17")
for option in chain.calls:
    print(f"  {option.strike} call | IV: {option.iv:.0%} | Delta: {option.delta:.2f}")

# Account
positions = client.get_positions()
balance = client.get_buying_power()
```

## IRA Trading

pyhood can discover and trade in IRA/retirement accounts — something no other Python Robinhood library supports.

```python
# Discover all accounts (including IRA)
accounts = client.get_all_accounts()

# Check IRA buying power
bp = client.get_buying_power(account_number="YOUR_IRA_ACCOUNT")

# Buy options in your Roth IRA
order = client.buy_option(
    symbol="NKE", strike=55.0, expiration="2026-04-02",
    option_type="call", quantity=3, price=1.60,
    account_number="YOUR_IRA_ACCOUNT",
)
```

See the [Account documentation](https://jamestford.github.io/pyhood/account/) for details on IRA account discovery and limitations.

## Authentication

Robinhood requires **device approval** on first login. After that, pyhood keeps your session alive automatically.

### First Login

1. Have the **Robinhood mobile app** open on your phone
2. Call `pyhood.login()` — it will trigger a device approval request
3. Tap **"Yes, it's me"** in the Robinhood app when prompted
4. pyhood saves the session token to `~/.pyhood/session.json` for reuse

```python
import pyhood

# First login — will wait up to 90s for you to approve on phone
session = pyhood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,  # seconds to wait for device approval
)
```

### Staying Authenticated

Once you've approved the device, pyhood handles the rest:

```python
# Reuses cached session — no approval needed
session = pyhood.login(username="you@email.com", password="your_password")

# Or refresh explicitly — no credentials needed at all
session = pyhood.refresh()
```

Sessions last several days (observed 5-8 days). When the access token expires, pyhood automatically refreshes it using the stored refresh token — **no device approval, no credentials, no human interaction**. This is what makes pyhood safe for automated scripts and cron jobs.

Device approval is only needed again if the refresh token itself expires (typically much longer than the access token).

### Error Handling

pyhood raises specific exceptions so you know exactly what went wrong:

```python
from pyhood.exceptions import (
    LoginTimeoutError,            # Timed out waiting for device approval
    DeviceApprovalRequiredError,  # Approval prompt sent but not completed
    MFARequiredError,             # SMS/email code needed — pass mfa_code parameter
    TokenExpiredError,            # Refresh token expired — full re-login needed
    AuthError,                    # Generic auth failure
)

try:
    session = pyhood.login(username="...", password="...", timeout=90)
except LoginTimeoutError:
    print("Open Robinhood app and approve the device, then try again")
except MFARequiredError:
    code = input("Enter the code from SMS/email: ")
    session = pyhood.login(username="...", password="...", mfa_code=code)
except AuthError as e:
    print(f"Login failed: {e}")
```

### ⚠️ Rate Limits

Robinhood aggressively rate-limits authentication. If login fails:

- **Do NOT retry immediately** — wait at least 5 minutes
- 2-3 failed attempts will lock out your account's API access for 5-10 minutes
- Each login attempt generates a new device approval — old approvals don't carry over
- See the [Rate Limits](https://jamestford.github.io/pyhood/rate-limits/) documentation for details

## Install

```bash
pip install pyhood
```

## Crypto Trading (Official API)

pyhood also supports Robinhood's **official** Crypto Trading API — no device approval needed, just API keys.

```python
from pyhood.crypto import CryptoClient

# API key auth — generate keys at robinhood.com/account/crypto
crypto = CryptoClient(api_key="rh-api-...", private_key_base64="...")

# Market data
quotes = crypto.get_best_bid_ask("BTC-USD", "ETH-USD")
price = crypto.get_estimated_price("BTC-USD", "buy", 0.001)

# Historical OHLCV data
candles = crypto.get_historicals("BTC-USD", interval="hour", span="week")
for c in candles:
    print(f"{c.begins_at}  O:{c.open_price}  H:{c.high_price}  L:{c.low_price}  C:{c.close_price}")

# Account & holdings
account = crypto.get_account()
holdings = crypto.get_holdings(account.account_number, "BTC")

# Place an order
order = crypto.place_order(
    account_number=account.account_number,
    side="buy",
    order_type="market",
    symbol="BTC-USD",
    order_config={"asset_quantity": "0.001"},
)
```

Generate your API keys at [robinhood.com/account/crypto](https://robinhood.com/account/crypto). See the [Crypto documentation](https://jamestford.github.io/pyhood/crypto/) for full details.

## Futures Trading

pyhood supports Robinhood's futures API — contracts, quotes, orders, and P&L tracking.

```python
client = PyhoodClient(session)

# Contract details
contract = client.get_futures_contract("ESH26")
print(f"{contract.name} — multiplier: {contract.multiplier}")

# Real-time quote
quote = client.get_futures_quote("ESH26")
print(f"Last: {quote.last_price}  Bid: {quote.bid}  Ask: {quote.ask}")

# P&L across all closed futures trades
pnl = client.calculate_futures_pnl()
print(f"Realized P&L: ${pnl:.2f}")
```

See the [Futures documentation](https://jamestford.github.io/pyhood/futures/) for full details.

## Banking & Dividends

```python
# Check linked bank accounts
accounts = client.get_bank_accounts()

# View transfer history
transfers = client.get_transfers()

# Initiate a deposit
transfer = client.initiate_transfer(
    amount=500.00,
    direction="deposit",
    ach_relationship_url=accounts[0].url,
)

# Dividend history
dividends = client.get_dividends()
aapl_divs = client.get_dividends_by_symbol("AAPL")
```

## Watchlists

```python
# Get all watchlists
watchlists = client.get_watchlists()

# Get a specific watchlist
default = client.get_watchlist("Default")
print(default.symbols)  # ['AAPL', 'MSFT', ...]

# Add / remove symbols
client.add_to_watchlist(["NVDA", "TSLA"])
client.remove_from_watchlist(["TSLA"])
```

## Markets & Trading Hours

```python
# List available exchanges
markets = client.get_markets()

# Check if NYSE is open on a specific date
hours = client.get_market_hours("XNYS", "2026-03-30")
print(f"Open: {hours.is_open}, {hours.opens_at} — {hours.closes_at}")
```

## Development Status
- ✅ Stocks/options market data (unofficial API) — functional (equity + index options)
- ✅ Futures trading (contracts, quotes, orders, P&L) — functional
- ✅ Crypto trading (official API) — functional
- ✅ Authentication with automatic token refresh — functional
- ✅ Full order management for stocks/options — functional
- ✅ Banking (ACH transfers, deposits/withdrawals) — functional
- ✅ Watchlists (create/manage) — functional
- ✅ Dividends (query history) — functional
- ✅ Markets/Trading Hours (exchange schedules) — functional
- ✅ User profile & notification settings — functional

## Acknowledgments

pyhood stands on the shoulders of the community that figured out Robinhood's unofficial API:

- [**robin_stocks**](https://github.com/jmfernandes/robin_stocks) by [Josh Fernandes](https://github.com/jmfernandes) — The most widely used Python library for Robinhood. Its auth flow, endpoint mapping, and API patterns laid the groundwork that pyhood builds from.
- [**pyrh**](https://github.com/robinhood-unofficial/pyrh) by [Robinhood Unofficial](https://github.com/robinhood-unofficial) — An early Python client that pioneered OAuth token refresh and session management patterns for the Robinhood API.
- [**Robinhood**](https://github.com/sanko/Robinhood) by [Sanko](https://github.com/sanko) — The original unofficial API documentation that mapped out Robinhood's endpoints and made all of these libraries possible.

These projects made Robinhood accessible to developers. pyhood continues that mission with a focus on reliability and automation.

## License

MIT
