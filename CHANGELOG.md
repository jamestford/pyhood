# Changelog

All notable changes to pyhood will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **SNDK earnings edge case** — `get_earnings()` now handles `eps: null` payloads without raising an exception
- **Equity options expiration fallback** — `get_options_expirations()` now falls back to an equity instrument's `tradable_chain_id` when the standard chain lookup returns no expiration dates
- This fixes real-world symbol-specific failures like SNDK in downstream scanners

## [0.6.0] - 2026-03-29

### Added
- **Research & Discovery** — Analyst ratings, news, market movers, and trending stocks
  - `get_ratings(symbol)` returns buy/hold/sell analyst consensus with computed percentages
  - `get_news(symbol)` returns news articles with source, summary, and related instruments
  - `get_movers(direction)` returns S&P 500 top movers (up or down)
  - `get_tags(tag)` returns symbols for discovery tags (100-most-popular, top-movers, etf, etc.)
  - `get_popularity(symbol)` returns how many Robinhood users hold a stock
  - `get_splits(symbol)` returns stock split history
  - Typed models: `Rating`, `NewsArticle`, `Mover`, `StockSplit`
- **Portfolio Historicals** — Track portfolio value over time
  - `get_portfolio_historicals(account_number, interval, span, bounds)` returns equity/market value candles
  - Typed model: `PortfolioCandle`
- **Option Historicals** — Historical pricing for option contracts
  - `get_option_historicals(option_id, interval, span)` returns OHLCV candles
  - Reuses existing `Candle` model
- **Documents & Statements** — Account documents, trade confirmations, tax docs
  - `get_documents(doc_type)` with optional type filtering
  - Typed model: `Document`
- **Day Trades / Margin / Deposit Schedules**
  - `get_day_trades(account_id)` returns recent day trade history
  - `get_margin_calls()` returns active margin calls
  - `get_deposit_schedules()` returns recurring ACH deposit schedules
- 15 new tests (212 total)

## [0.5.0] - 2026-03-29

### Added
- **Banking / ACH Support** — Query and manage bank accounts and transfers
  - `get_bank_accounts()` lists all linked bank accounts with status
  - `get_transfers()` returns full ACH transfer history (deposits & withdrawals)
  - `initiate_transfer()` starts a new deposit or withdrawal
  - `cancel_transfer()` cancels a pending transfer
  - Typed models: `BankAccount`, `ACHTransfer`
- **Watchlist Support** — Manage Robinhood watchlists programmatically
  - `get_watchlists()` returns all watchlists with their symbols
  - `get_watchlist(name)` fetches a single watchlist by name
  - `add_to_watchlist()` and `remove_from_watchlist()` for modifying lists
  - Typed model: `Watchlist`
- **Dividend History** — Query past and pending dividend payments
  - `get_dividends()` returns all dividend records with symbol resolution
  - `get_dividends_by_symbol()` filters to a specific ticker
  - Typed model: `Dividend`
- **Markets / Trading Hours** — Exchange info and schedules
  - `get_markets()` lists all available exchanges (NYSE, NASDAQ, etc.)
  - `get_market_hours(market, date)` returns open/close times for a specific date
  - Typed models: `Market`, `MarketHours`
- **User Profile & Notification Settings**
  - `get_user_profile()` returns username, email, name
  - `get_notification_settings()` and `update_notification_settings()` for managing preferences
  - Typed models: `UserProfile`, `NotificationSettings`
- 18 new tests covering all new features (197 total)

## [0.4.2] - 2026-03-28

### Added
- **Index Options Support** — SPX, NDX, VIX, RUT, and XSP index options now work with all options methods
  - `get_options_expirations()` uses `/indexes/` endpoint and `tradable_chain_ids` for index symbols
  - `get_options_chain()` and `_get_option_id()` map index symbols to Robinhood's chain symbols (SPX → SPXW, NDX → NDXP, VIX → VIXW, RUT → RUTW)
  - `buy_option()` / `sell_option()` work with index symbols transparently
  - New `INDEX_CHAIN_SYMBOLS` constant and `_is_index()` / `_resolve_chain_symbol()` helpers
  - 5 new tests covering symbol mapping, index expirations, and index chain fetching

## [0.4.0] - 2026-03-28

### Added
- **Futures Trading Support** — Full access to Robinhood's futures trading API
  - `get_futures_contract()` and `get_futures_contracts()` for contract details (symbol, expiration, tick size, multiplier)
  - `get_futures_quote()` and `get_futures_quotes()` for real-time bid/ask/last prices
  - `get_futures_orders()` and `get_filled_futures_orders()` with automatic cursor-based pagination
  - `get_futures_account_id()` for auto-discovering the futures account via Ceres API
  - `calculate_futures_pnl()` for aggregating realized P&L across closing orders
  - Typed models: `FuturesContract`, `FuturesQuote`, `FuturesOrder`, `FuturesPnL`
  - Handles `Rh-Contract-Protected` header automatically
  - 21 new tests covering contracts, quotes, account discovery, orders, pagination, and P&L

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
- **Security: Bandit scan** — All medium+ issues resolved (B608, B307)
- Bandit security scan now passes with zero medium+ issues

## [0.3.0] - 2026-03-23

### Added
- **IRA/Retirement Account Support** — Trade stocks and options in Traditional and Roth IRAs
  - `get_all_accounts()` discovers all accounts including IRA via bonfire endpoint
  - `account_number` parameter on all order methods (`buy_option`, `sell_option`, `buy_stock`, `sell_stock`, `order_option`, `order_stock`)
  - `account_number` parameter on `get_buying_power()` and `get_positions()`
  - Direct account URL construction bypasses Robinhood's `/accounts/` blind spot for IRA
  - Full documentation with examples and IRA limitations
- **Fundamental Data** — `get_fundamentals()` and `get_fundamentals_batch()` with PE, market cap, 52w range
- **Stock Universe Screener** — `get_all_instruments()` for full Robinhood symbol list
- **Batch Historicals** — `get_stock_historicals_batch()` for multi-symbol OHLCV in one call

### Fixed
- **Options order direction** — Use `direction` field instead of `side` in option order payload (matches Robinhood's actual API)
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
