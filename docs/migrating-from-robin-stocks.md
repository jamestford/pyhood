# Migrating from robin_stocks

A function-by-function map from [robin_stocks](https://github.com/jmfernandes/robin_stocks) to pyhood.

Two differences shape everything below:

**pyhood is object-oriented.** robin_stocks is a module of free functions holding a global session. pyhood gives you a `PyhoodClient` you call methods on. This is the one change you cannot avoid.

**pyhood returns typed objects.** robin_stocks returns dicts (and often lists of dicts). pyhood returns dataclasses with annotated fields, so `quote["last_trade_price"]` becomes `quote.price`, and your editor can tell you what exists.

```python
# robin_stocks
import robin_stocks.robinhood as r
r.login(username, password)
price = float(r.get_latest_price("AAPL")[0])

# pyhood
import pyhood
from pyhood.client import PyhoodClient
pyhood.login(username, password)
client = PyhoodClient()
price = client.get_quote("AAPL").price
```

After the first login, pyhood reuses the cached session and refreshes it silently — `pyhood.refresh()` needs no credentials and no device approval. That is the main reason people move.

---

## Authentication

| robin_stocks | pyhood |
| --- | --- |
| `login(username, password)` | `pyhood.login(username, password)` |
| `logout()` | `pyhood.logout()` |
| — | `pyhood.refresh()` — renew a session with no credentials, no device approval |
| `generate_device_token()` | `from pyhood.auth import generate_device_token` |

`login()` with no arguments reuses a cached session and falls back to `refresh()` before ever asking for credentials.

## Quotes and market data

| robin_stocks | pyhood |
| --- | --- |
| `get_latest_price(symbol)` | `client.get_quote(symbol).price` |
| `get_quotes(symbols)` | `client.get_quotes(symbols)` |
| `get_stock_quote_by_symbol(symbol)` | `client.get_quote(symbol)` |
| `get_fundamentals(symbols)` | `client.get_fundamentals(symbol)` / `get_fundamentals_batch(symbols)` |
| `get_stock_historicals(symbols, ...)` | `client.get_stock_historicals(symbol, ...)` / `get_stock_historicals_batch(symbols, ...)` |
| `get_instruments_by_symbols(symbols)` | `client.get_all_instruments(symbols)` |
| `get_news(symbol)` | `client.get_news(symbol)` |
| `get_ratings(symbol)` | `client.get_ratings(symbol)` |
| `get_earnings(symbol)` | `client.get_earnings(symbol)` |
| `get_splits(symbol)` | `client.get_splits(symbol)` |
| `get_top_movers_sp(direction)` | `client.get_movers(direction)` |
| `get_all_stocks_from_market_tag(tag)` | `client.get_tags(tag)` |
| `get_popularity(symbol)` | `client.get_popularity(symbol)` |

## Account and positions

| robin_stocks | pyhood |
| --- | --- |
| `load_account_profile()` | `client.get_all_accounts()` |
| `load_user_profile()` / `build_user_profile()` | `client.get_user_profile()` |
| `get_all_positions()` | `client.get_positions(nonzero=False)` |
| `get_open_stock_positions()` | `client.get_positions()` |
| `build_holdings()` | `client.get_positions()` — returns typed `Position` objects |
| `get_all_option_positions()` | `client.get_option_positions(nonzero=False)` |
| `get_open_option_positions()` | `client.get_option_positions()` |
| `get_historical_portfolio(...)` | `client.get_portfolio_historicals(...)` |
| `get_day_trades()` | `client.get_day_trades()` |
| `get_margin_calls()` | `client.get_margin_calls()` |
| `get_documents()` | `client.get_documents()` |
| — | `client.get_all_accounts()` — includes IRA accounts, which `/accounts/` never returns |

Position and order methods take `account_number=` to target a specific account, including retirement accounts.

## Orders — stocks

pyhood collapses robin_stocks' many `order_buy_*` / `order_sell_*` variants into three methods. Order type follows from which arguments you pass: omit `price` for a market order, pass `price` for a limit order, pass `stop_price` for a stop.

| robin_stocks | pyhood |
| --- | --- |
| `order_buy_market(symbol, qty)` | `client.buy_stock(symbol, qty)` |
| `order_sell_market(symbol, qty)` | `client.sell_stock(symbol, qty)` |
| `order_buy_limit(symbol, qty, price)` | `client.buy_stock(symbol, qty, price=price)` |
| `order_sell_limit(symbol, qty, price)` | `client.sell_stock(symbol, qty, price=price)` |
| `order_buy_stop_loss(symbol, qty, stop)` | `client.buy_stock(symbol, qty, stop_price=stop)` |
| `order_sell_stop_loss(symbol, qty, stop)` | `client.sell_stock(symbol, qty, stop_price=stop)` |
| `order_buy_stop_limit(symbol, qty, price, stop)` | `client.buy_stock(symbol, qty, price=price, stop_price=stop)` |
| `order_sell_stop_limit(symbol, qty, price, stop)` | `client.sell_stock(symbol, qty, price=price, stop_price=stop)` |
| `order(...)` | `client.order_stock(symbol, qty, side, ...)` |
| `get_all_stock_orders()` | `client.get_stock_orders()` |
| `get_stock_order_info(order_id)` | `client.get_order(order_id)` |
| `cancel_stock_order(order_id)` | `client.cancel_order(order_id)` |
| `cancel_all_stock_orders()` | `client.cancel_all_stock_orders()` |

Trailing stops and fractional orders:

| robin_stocks | pyhood |
| --- | --- |
| `order_buy_trailing_stop(symbol, qty, trailAmount)` | `client.buy_stock(symbol, qty, trail_amount=amt)` — see note |
| `order_sell_trailing_stop(symbol, qty, trailAmount)` | `client.sell_stock(symbol, qty, trail_amount=amt)` — see note |
| `order_trailing_stop(..., trailType='percentage')` | `client.buy_stock(..., trail_percent=pct)` — see note |
| `order_buy_fractional_by_price(symbol, dollars)` | `client.buy_stock_by_price(symbol, dollars)` |
| `order_sell_fractional_by_price(symbol, dollars)` | `client.sell_stock_by_price(symbol, dollars)` |
| `order_buy_fractional_by_quantity(symbol, qty)` | `client.buy_stock(symbol, qty)` — fractional quantities are accepted |

**A note on `order_form_version`.** Robinhood versions its order form and refuses orders from clients sending an old value or none, with:

```
Your app version is missing important stock trading updates.
You can still place orders on the web.
```

This reads like a client-version block but is not — it means the *order form* version. pyhood sends the current value (`7`, captured from the web client). robin_stocks does not send this field at all, so its market orders, fractional orders and trailing stops are subject to this rejection.

If that message reappears, Robinhood has moved to a newer form version: raise `ORDER_FORM_VERSION` in `pyhood/client.py`. pyhood's error message says so explicitly rather than failing opaquely.

Order history takes `start_date=` to avoid paging through years of orders:

```python
client.get_stock_orders(start_date="2026-01-01")
```

## Orders — options

| robin_stocks | pyhood |
| --- | --- |
| `order_buy_option_limit(...)` | `client.buy_option(symbol, strike, expiration, option_type, qty, price)` |
| `order_sell_option_limit(...)` | `client.sell_option(symbol, strike, expiration, option_type, qty, price)` |
| `get_all_option_orders()` | `client.get_option_orders()` |
| `get_option_order_info(order_id)` | `client.get_order(order_id)` |
| `cancel_option_order(order_id)` | `client.cancel_order(order_id)` |

Spreads and bulk cancel:

| robin_stocks | pyhood |
| --- | --- |
| `order_option_spread(direction, price, symbol, qty, spread)` | `client.order_option_spread(symbol, qty, price, legs, direction)` |
| `order_option_credit_spread(...)` | `client.order_option_spread(..., direction="credit")` |
| `order_option_debit_spread(...)` | `client.order_option_spread(..., direction="debit")` |
| `cancel_all_option_orders()` | `client.cancel_all_option_orders()` |

Each leg is a dict with `strike`, `expiration`, `option_type`, `side` and `effect`, plus an optional `ratio`:

```python
client.order_option_spread("AAPL", 1, 1.50, direction="debit", legs=[
    {"strike": 100.0, "expiration": "2026-09-18", "option_type": "call",
     "side": "buy", "effect": "open"},
    {"strike": 105.0, "expiration": "2026-09-18", "option_type": "call",
     "side": "sell", "effect": "open"},
])
```

## Extended and 24-hour sessions

pyhood accepts a `market_hours` argument on stock orders, which robin_stocks exposes the same way:

| robin_stocks | pyhood |
| --- | --- |
| `order(..., market_hours='extended_hours')` | `client.buy_stock(..., market_hours="extended_hours")` |
| `order(..., market_hours='all_day_hours')` | `client.buy_stock(..., market_hours="all_day_hours")` |

Valid values are `regular_hours`, `extended_hours` and `all_day_hours`. Robinhood rejects an order whose session disagrees with its `extended_hours` flag, so pyhood derives the flag from the session rather than letting the two drift apart.

Omitting the argument sends no field and preserves the previous behaviour.

## Options chains and contracts

| robin_stocks | pyhood |
| --- | --- |
| `get_chains(symbol)` | `client.get_options_expirations(symbol)`, then `get_options_chain(symbol, expiration)` |
| `find_tradable_options(symbol, expiration, type)` | `client.get_options_chain(symbol, expiration, option_type=type)` |
| `find_options_by_expiration(symbol, exp)` | `client.get_options_chain(symbol, exp)` |
| `find_options_by_strike(symbol, strike)` | filter the chain — see below |
| `find_options_by_expiration_and_strike(symbol, exp, strike)` | filter the chain — see below |
| `get_option_historicals(...)` | `client.get_option_historicals(...)` |

**`expiration` is required.** pyhood fetches one expiration at a time rather than the whole chain, and there is no `strike` filter — filter the contracts yourself:

```python
chain = client.get_options_chain("AAPL", "2026-09-18")
at_strike = [c for c in chain.calls if c.strike == 200.0]
```

The chain separates `chain.calls` and `chain.puts` rather than returning one mixed list; `option_type="call"` limits which of the two is populated.

To scan every expiration, loop over `get_options_expirations(symbol)`. This is more calls than robin_stocks' `find_options_by_strike`, which searched across expirations for you.

Chain results carry Greeks, volume and open interest as typed fields. Index options (SPX, NDX, VIX, RUT, XSP) work through the same method.

## Banking and transfers

| robin_stocks | pyhood |
| --- | --- |
| `get_linked_bank_accounts()` | `client.get_bank_accounts()` |
| `get_bank_transfers()` | `client.get_transfers()` |
| `deposit_funds_to_robinhood_account(...)` | `client.initiate_transfer(amount, "deposit", ach_relationship_url)` |
| `withdrawl_funds_to_bank_account(...)` | `client.initiate_transfer(amount, "withdraw", ach_relationship_url)` |
| `get_card_transactions()` | `client.get_card_transactions()` |
| `get_dividends()` | `client.get_dividends()` |
| `get_dividends_by_instrument(...)` | `client.get_dividends_by_symbol(symbol)` |

| `get_interest_payments()` | `client.get_interest_payments()` |
| `get_margin_interest()` | `client.get_margin_interest()` |
| `get_unified_transfers()` | `client.get_unified_transfers()` |
| `unlink_bank_account(id)` | `client.unlink_bank_account(id)` |
| — | `client.get_subscription_fees()` — Gold subscription charges |

`get_wire_transfers()` has no pyhood equivalent: the `/wire/transfers` endpoint robin_stocks calls returns 404, so there is nothing to wrap.

## Exporting

| robin_stocks | pyhood |
| --- | --- |
| `export_completed_stock_orders(dir)` | `client.export_stock_orders(path)` |
| `export_completed_option_orders(dir)` | `client.export_option_orders(path)` |

Both accept a file path or a directory, and take `start_date=` to bound the range.

## Watchlists

| robin_stocks | pyhood |
| --- | --- |
| `get_all_watchlists()` | `client.get_watchlists()` |
| `get_watchlist_by_name(name)` | `client.get_watchlist(name)` |
| `post_symbols_to_watchlist(symbols, name)` | `client.add_to_watchlist(symbols, name)` |
| `delete_symbols_from_watchlist(symbols, name)` | `client.remove_from_watchlist(symbols, name)` |

## Markets

| robin_stocks | pyhood |
| --- | --- |
| `get_markets()` | `client.get_markets()` |
| `get_market_hours(market, date)` | `client.get_market_hours(market, date)` |
| `get_market_today_hours(market)` | `client.get_market_hours(market)` |

## Crypto

robin_stocks uses the same unofficial endpoints as the rest of its API. pyhood uses Robinhood's **official Crypto Trading API**, which authenticates with an Ed25519 key pair generated in your Robinhood settings — separate credentials from your login.

```python
from pyhood.crypto import CryptoClient
crypto = CryptoClient(api_key=..., private_key_base64=...)
crypto.get_best_bid_ask(["BTC-USD"])
```

| robin_stocks | pyhood (`CryptoClient`) |
| --- | --- |
| `get_crypto_quote(symbol)` | `crypto.get_best_bid_ask([symbol])` |
| `get_crypto_positions()` | `crypto.get_holdings()` |
| `get_crypto_currency_pairs()` | `crypto.get_trading_pairs()` |
| `get_all_crypto_orders()` | `crypto.get_orders()` |
| `get_crypto_order_info(id)` | `crypto.get_order(id)` |
| `order_buy_crypto_by_quantity(...)` | `crypto.place_order(...)` |
| `cancel_crypto_order(id)` | `crypto.cancel_order(id)` |
| — | `crypto.get_estimated_price(...)` |

Because the credentials and the endpoints differ, crypto is the one area where migration is a rewrite rather than a rename.

## What pyhood adds

No robin_stocks equivalent exists for these:

- `pyhood.refresh()` — silent session renewal
- `client.get_all_accounts()` and `account_number=` — IRA and retirement account support
- `CryptoClient` — the official Crypto Trading API
- `client.get_futures_*()` — futures contracts, quotes, positions, orders and P&L
- `client.get_ipo_access_*()` — IPO Access offerings, eligibility and allocations

## Getting help

If a function you rely on is not covered here, [open an issue](https://github.com/jamestford/pyhood/issues) with the robin_stocks call you are replacing. Gaps in this guide are bugs in it.
