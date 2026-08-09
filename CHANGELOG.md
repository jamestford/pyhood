# Changelog

All notable changes to pyhood will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Position P&L was wrong, reporting gains on losing positions** — `get_positions()` read `average_buy_price`, which Robinhood returns as `0` for settled positions. Cost basis therefore came out as zero and `unrealized_pl` degenerated to equity. It now falls back to `clearing_average_cost` and prefers the broker's own `clearing_cost_basis`, matching what the app displays. Caught by comparing pyhood's output against the Robinhood web UI for the same position.
- `get_positions()` no longer fetches each instrument to resolve a symbol — the positions payload already carries it, saving a request per position.

### Fixed
- **Market orders, fractional orders and trailing stops were all rejected** — Robinhood refuses orders that omit `order_form_version`, responding "Your app version is missing important stock trading updates". Despite the wording this is the *order form* version, not a client version. pyhood now sends `7`. Any value from 2 upward is accepted; `1` and omission are refused. robin_stocks sends `4` on ordinary stock orders, which works — but omits it on `order_trailing_stop`, so trailing stops fail there.
- **Rejected orders were reported as successful** — `order_stock()` and `order_option()` only treated a response as an error when it carried a `detail` or `error` key, but Robinhood returns field-level validation errors (`{"field": ["message"]}`) that have neither. Any such rejection returned an `Order` with a blank id and no exception, so callers believed the order was placed. Both now raise when the response has no `id`.
- Trailing stop rejections now raise a specific `OrderError` explaining that Robinhood gates the feature to its own app versions, rather than surfacing the raw server text.
- Passing both a `price` and a trail is rejected up front — Robinhood does not support trailing stop limit orders.

### Added
- **`is_market_open()`** — whether trading is open right now, for the regular or extended session. Uses the New York trading date rather than the UTC date, so it stays correct during the evening. Orders placed while closed are queued rather than rejected, which is easy to mistake for a hang.
- **Extended and 24-hour trading sessions** — `market_hours` on `buy_stock()`, `sell_stock()` and `order_stock()`, accepting `regular_hours`, `extended_hours` or `all_day_hours`. `extended_hours` is derived from it, since Robinhood rejects orders where the two disagree.
- **Interest, fees and transfers** — `get_interest_payments()`, `get_margin_interest()`, `get_subscription_fees()`, `get_unified_transfers()`. All verified against live data except margin interest, where the endpoint is confirmed but the account has no charges to observe.
- **Trailing stop orders** — `buy_stock(..., trail_amount=)` / `trail_percent=`, and the same on `sell_stock()` and `order_stock()`. Posted as JSON, since the nested `trailing_peg` cannot survive form encoding. **Robinhood currently rejects these from third-party clients** — see Fixed below.
- **Fractional orders by dollar amount** — `buy_stock_by_price()` and `sell_stock_by_price()`.
- **Multi-leg option spreads** — `order_option_spread()` for debit and credit spreads, with per-leg ratios.
- **`cancel_all_option_orders()`** — mirrors the existing stock version.
- **CSV export** — `export_stock_orders()` and `export_option_orders()`, accepting a file or directory path.
- **`unlink_bank_account()`** — irreversible; not exercised against a live account.
- Migration guide from robin_stocks, with every referenced method verified to exist.

Order-placement additions are verified by asserting the request payload, not by placing live orders.

### Changed
- Promoted from `Development Status :: 3 - Alpha` to `4 - Beta` on PyPI — 259 tests, CI across Python 3.10-3.13, and ten releases
- PyPI keywords now include `robinhood-api`, `robin_stocks`, `robin-stocks` and `pyrh`, so the package is findable by people searching for the libraries they are migrating from

## [0.10.0] - 2026-08-09

### Fixed
- **Futures contracts and quotes never worked** — `get_futures_contract()` raised `SymbolNotFound` for every valid symbol, and `get_futures_quote()` failed with it
  - The contract endpoint wraps its body in a `result` envelope with camelCase keys; the parser expected a flat snake_case object
  - The quotes endpoint returns `data[0].data`; the parser read a non-existent `results` list
  - Field mapping corrected: `description` (not `simple_name`), `expiration` (not `expiration_date`); `/ESZ26:XCME` is normalized to `ESZ26` and `FUTURES_STATE_ACTIVE` to `active`
  - `tick_size`, `underlying` and `asset_class` are not returned by the endpoint and now default rather than being read from absent keys
  - Existing tests used a fabricated response shape, so the whole futures surface failed in practice while CI stayed green
  - Verified live against ES, NQ and MES contracts

### Added
- **IPO Access** — read Robinhood's retail IPO allocation program
  - `get_ipo_access_list()` / `has_ipo_offerings()` — current offerings, or the empty state when there are none
  - `get_ipo_access_cards(instrument_ids)` — cards for one or more instruments
  - `get_ipo_access_summary()`, `get_ipo_access_order_entry()`, `get_ipo_access_allocation_results()`, `get_ipo_access_trade_receipt()` — offering view models
  - `get_ipo_access_orders(start_date=...)` — typed `Order` objects for orders flagged `is_ipo_access_order`
  - View models are returned as raw dicts: their structure is deeply nested and offering-dependent, and four of the six endpoints 404 outside a live offering, so their populated shapes are unverified. The list, cards and orders paths are verified against the live API.
  - Requesting shares is not wrapped — an IPO order is an ordinary equity order and the submission payload could not be verified without a live offering
- `get_futures_positions()` — open futures positions. The endpoint (`ceres/v1/accounts/{id}/positions/`) was previously undiscovered; robin_stocks_v2 ships a stub that returns None. Route and `results` envelope verified live; records are returned unmapped because no populated position was observable.
- `get_futures_quote_by_id(contract_id)` — quote a contract directly, skipping the symbol lookup
- `get_futures_order_info(order_id)` — fetch a single futures order by ID

## [0.9.0] - 2026-08-09

### Added
- **`start_date` on order history** — avoid paging through years of orders to reach recent ones (re: [#15](https://github.com/jamestford/pyhood/issues/15))
  - `get_stock_orders(start_date=...)`, `get_option_orders(start_date=...)`, `get_futures_orders(start_date=...)`, `get_filled_futures_orders(start_date=...)`
  - Accepts a `datetime` or ISO-8601 string (`'2026-01-01'` or a full timestamp); naive values are treated as UTC
  - Requested server-side via `created_at[gte]` so the API returns fewer pages, and re-applied client-side so an endpoint that ignores the filter still returns correctly filtered results
  - Server-side filtering is confirmed working on options orders; stock and futures endpoints could not be verified against live data, hence the local fallback
  - Omitting `start_date` preserves existing behaviour exactly — no param is sent
  - 8 new tests (235 total)

### Changed
- **Source distribution reduced from 6.8 MB to 68 KB** — the sdist bundled `assets/`, `docs/` and `.github/`, of which ~6.5 MB was logo source images. It now ships source, tests, README, changelog and licence via an explicit include list. The wheel is unchanged at 46 KB.
- Example account numbers in the IRA documentation and in the `get_positions()` docstring are now placeholders rather than literal values.

## [0.8.1] - 2026-08-09

### Fixed
- **`login()` crashed on Windows** — `AttributeError: module 'signal' has no attribute 'SIGALRM'` (fixes [#16](https://github.com/jamestford/pyhood/issues/16))
  - The login timeout was armed with `signal.SIGALRM`, which exists only on Unix
  - The alarm is now best-effort: skipped when `SIGALRM` is unavailable, so login works on Windows
  - Also skipped when `login()` is called off the main thread, where `signal.signal()` raises `ValueError`
  - Timeouts are still enforced on those platforms by the verification poll loop and per-request HTTP timeouts
  - Alarm setup/teardown moved into a context manager, so the handler is always restored
  - 4 new tests (227 total) simulating a Windows environment and a worker thread

## [0.8.0] - 2026-08-09

### Fixed
- **`get_news()` crashed on every real call** — `AttributeError: 'str' object has no attribute 'get'` (fixes [#17](https://github.com/jamestford/pyhood/issues/17))
  - `related_instruments` entries are bare instrument IDs, but were parsed as dicts
  - IDs are now resolved to ticker symbols via the instruments endpoint, cached per call
  - Dict entries and instrument URLs are also accepted, so the parser tolerates all observed shapes
  - A malformed or non-list `related_instruments`, or a failed lookup, no longer raises
  - Existing tests only ever supplied dicts — the one shape the API does not return — so CI stayed green while the feature was unusable in 0.7.0
  - 6 new tests (222 total), verified against live API data

### Added
- `get_news(symbol, resolve_symbols=True)` — pass `resolve_symbols=False` to skip symbol resolution and get raw instrument IDs back, avoiding one request per unique instrument

## [0.7.0] - 2026-04-09

### Added
- **Debit Card Transactions** — Query Cash Management debit card transaction history (re: [#14](https://github.com/jamestford/pyhood/issues/14))
  - `get_card_transactions(card_type)` returns all debit card transactions, with optional `'pending'`/`'settled'` filter
  - Uses the `minerva.robinhood.com/history/transactions/` endpoint (same auth token)
  - Typed model: `CardTransaction` (id, description, amount, category, direction, state, initiated_at, completed_at, merchant)
  - 3 new tests (217 total)

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
