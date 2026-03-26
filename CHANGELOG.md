# Changelog

All notable changes to pyhood will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.2] - 2026-03-26

### Added
- **`get_option_positions()` method** — Fully resolved option positions with live market data
  - Returns `OptionPosition` dataclass with symbol, strike, expiry, type, quantity, cost basis, current value, P&L, and Greeks
  - Uses `/options/aggregate_positions/` endpoint with leg resolution
  - Fetches live market data for mark price, delta, IV, theta
  - Supports `account_number` filter for IRA accounts
  - No more raw API calls needed to check option holdings

## [0.3.1] - 2026-03-23

### Fixed
- **Security: SQL injection warnings** — Replaced f-string SQL construction with string concatenation in autoresearch memory module (B608)
- **Security: eval() removal** — Replaced `eval()` with safe namespace dict lookup and `ast.parse` for strategy resolution in autoresearch runner (B307)
- Bandit security scan now passes with zero medium+ issues

## [0.3.0] - 2026-03-23

### Added
- **IRA/Retirement Account Support** — Trade stocks and options in Traditional and Roth IRAs
  - `get_all_accounts()` discovers all accounts including IRA via bonfire endpoint
  - `account_number` parameter on all order methods (`buy_option`, `sell_option`, `buy_stock`, `sell_stock`, `order_option`, `order_stock`)
  - `account_number` parameter on `get_buying_power()` and `get_positions()`
  - Direct account URL construction bypasses Robinhood's `/accounts/` blind spot for IRA
  - Full documentation with examples and IRA limitations
- **Autoresearch Engine** — Automated trading strategy discovery and optimization
  - Persistent SQLite memory for experiment tracking and caching
  - Cross-validation with train/validation/test splits
  - Continuous overnight mode (`run_overnight.py`)
  - Multi-ticker parallel strategy testing
  - JSONL audit trail for reproducibility
- **Market Regime Classifier** — 200-SMA based bull/bear/recovery/correction detection
- **Slippage Modeling** — Realistic transaction cost simulation in backtester
- **5 New Strategies** — Full 9-strategy catalog with benchmarks
- **Fundamental Data** — `get_fundamentals()` and `get_fundamentals_batch()` with PE, market cap, 52w range
- **Stock Universe Screener** — `get_all_instruments()` for full Robinhood symbol list
- **Batch Historicals** — `get_stock_historicals_batch()` for multi-symbol OHLCV in one call

### Fixed
- **Options order direction** — Use `direction` field instead of `side` in option order payload (matches Robinhood's actual API)
- **Ticker-scoped experiment keys** — Fixed isolation bug in autoresearch
- **Ruff lint cleanup** — All E501, F821, N818 violations resolved

### Changed
- CI dependencies bumped: actions/checkout v6, actions/setup-python v6, actions/upload-artifact v7, github/codeql-action v4

## [0.2.0] - 2026-03-18

### Added
- **Crypto Trading API** — Full support for Robinhood's official Crypto Trading API (v2)
  - ED25519 API key authentication (no device approval needed)
  - `CryptoClient` with all endpoints: accounts, market data, holdings, orders
  - Typed models: `CryptoAccount`, `CryptoQuote`, `CryptoHolding`, `CryptoOrder`, `TradingPair`, `EstimatedPrice`
  - Token bucket rate limiting (100 req/min, 300 burst)
- **Stock/Options Order Management** — buy, sell, cancel stocks and options
  - Market, limit, stop, stop-limit orders
  - Options with position effects and legs format
  - Order listing and cancellation
- **Stock Historicals** — OHLCV candle data up to 5 years
  - Single and batch symbol fetching
  - Intervals: 5min, 10min, hour, day, week
- **Backtesting Engine** — Test strategies against historical data
  - 3 built-in strategies: EMA crossover, RSI mean reversion, Bollinger breakout
  - Full scorecard: Sharpe, drawdown, win rate, profit factor, alpha
  - Strategy comparison and ranking tools
  - Pure Python — no pandas/numpy required

### Fixed
- **Options expirations** — Fixed `get_options_expirations()` to use `equity_instrument_ids` (symbol param returned unfiltered results)
- **Options market data** — Fixed `get_options_chain()` to pass full instrument URLs (IDs were rejected with 400)
- **Market data batch size** — Reduced to 17 per request (Robinhood rejects larger batches)

## [0.1.0] - 2026-03-16

### Added
- **Authentication** — Login with configurable timeouts, device approval handling, MFA support
- **Token Refresh** — `pyhood.refresh()` renews sessions via OAuth refresh tokens — no credentials or device approval needed
- **Auto-refresh on login** — `pyhood.login()` automatically tries refresh before falling back to full re-login
- **Stock Quotes** — `get_quote()` and `get_quotes()` with typed `Quote` dataclass responses
- **Options Chains** — `get_options_chain()` with full Greeks (IV, delta, gamma, theta, vega), volume/OI
- **Earnings** — `get_earnings()` with lookahead window
- **Account** — `get_positions()` with P/L calculations, `get_buying_power()`
- **Error Handling** — Full exception hierarchy: `LoginTimeoutError`, `TokenExpiredError`, `DeviceApprovalRequiredError`, `MFARequiredError`, `RateLimitError`, `APIError`, `SymbolNotFoundError`
- **Rate Limiting** — Built-in 250ms request throttling, automatic retry on 429
- **HTTP Session** — Managed session with pagination, retries, auth header management
- **Token Storage** — Persistent session at `~/.pyhood/session.json` with device token reuse
- **Type Hints** — Full annotations on all public APIs, frozen dataclasses
- **CI/CD** — GitHub Actions on Python 3.10-3.13, ruff linting, 58 tests
- **Security Scanning** — CodeQL, Bandit, pip-audit on every push
- **Documentation** — MkDocs Material site at jamestford.github.io/pyhood
- **Published on PyPI** — `pip install pyhood`

[0.1.0]: https://github.com/jamestford/pyhood/releases/tag/v0.1.0
