# Migrating from pyrh

A method-by-method map from [pyrh](https://github.com/robinhood-unofficial/pyrh) to pyhood.

pyrh's last commit was August 2024. Its open issues include requests for [options support](https://github.com/robinhood-unofficial/pyrh/issues/201) (open since 2020) and [fractional shares](https://github.com/robinhood-unofficial/pyrh/issues/200), both of which pyhood implements.

Three differences shape everything below.

**One quote object instead of thirty accessors.** pyrh exposes a method per field: `ask_price()`, `bid_price()`, `last_trade_price()`, `previous_close()`, each making its own request. pyhood fetches a `Quote` once and you read attributes off it.

**Three order methods instead of thirteen.** pyrh has `place_market_buy_order`, `place_limit_buy_order`, `place_stop_loss_buy_order`, `place_stop_limit_buy_order` and the four selling equivalents. pyhood has `buy_stock()`, `sell_stock()` and `order_stock()`; the order type follows from which arguments you pass.

**Sessions renew without you.** pyrh re-authenticates with stored credentials. pyhood persists the refresh token, so `pyhood.refresh()` needs no password and triggers no device approval prompt.

```python
# pyrh
from pyrh import Robinhood
rh = Robinhood()
rh.login(username="you@email.com", password="...")
price = float(rh.last_trade_price("AAPL")[0][0])

# pyhood
import pyhood
from pyhood.client import PyhoodClient
client = PyhoodClient(pyhood.login())
price = client.get_quote("AAPL").price
```

---

## Authentication

| pyrh | pyhood |
| --- | --- |
| `Robinhood()` then `rh.login(username, password)` | `pyhood.login(username, password)` |
| `rh.logout()` | `pyhood.logout()` |
| re-login with stored credentials | `pyhood.refresh()`, no credentials, no device approval |
| `rh.get_url(url)` | `client._session.get(url)` for anything unwrapped |

`pyhood.login()` with no arguments reuses the cached session and falls back to `refresh()` before ever asking for credentials. There is also a guided command:

```bash
pyhood setup login
```

## Quotes

pyrh's per-field accessors all collapse into one `Quote`:

```python
quote = client.get_quote("AAPL")
```

| pyrh | pyhood |
| --- | --- |
| `quote_data(symbol)` / `get_quote(symbol)` | `client.get_quote(symbol)` |
| `quotes_data(symbols)` / `get_quote_list(...)` | `client.get_quotes(symbols)`, returns `dict[str, Quote]` |
| `last_trade_price(symbol)` | `quote.price` |
| `ask_price(symbol)` | `quote.ask` |
| `bid_price(symbol)` | `quote.bid` |
| `previous_close(symbol)` | `quote.prev_close` |
| `symbol(symbol)` | `quote.symbol` |
| `last_updated_at(symbol)` / `last_updated_at_datetime(symbol)` | `quote.timestamp`, already a `datetime` |
| `get_historical_quotes(...)` | `client.get_stock_historicals(symbol, interval, span, bounds)` |
| `get_stock_marketdata(...)` | `client.get_quotes(symbols)` |
| `print_quote(symbol)` / `print_quotes(symbols)` | no equivalent, print the fields you want |

`Quote` also carries `change_pct`, `volume`, `pe_ratio`, `market_cap`, `high_52w` and `low_52w`.

Not carried over: `ask_size`, `bid_size`, `adjusted_previous_close` and `previous_close_date` have no field on `Quote`. Reach for the raw endpoint through the session if you need them.

## Research

| pyrh | pyhood |
| --- | --- |
| `fundamentals(symbol)` / `get_fundamentals(symbol)` | `client.get_fundamentals(symbol)` |
| `get_news(symbol)` | `client.get_news(symbol)` |
| `get_popularity(symbol)` | `client.get_popularity(symbol)` |
| `get_tickers_by_tag(tag)` | `client.get_tags(tag)` |

`get_news()` returns typed `NewsArticle` objects, and resolves the instrument IDs in `related_instruments` to ticker symbols. Pass `resolve_symbols=False` to skip the lookup.

## Options

This is [pyrh #201](https://github.com/robinhood-unofficial/pyrh/issues/201), open since 2020.

| pyrh | pyhood |
| --- | --- |
| `get_options(stock, expiration_dates, option_type)` | `client.get_options_chain(symbol, expiration, option_type=None)` |
| `get_option_chainid(symbol)` | not needed, resolved internally |
| `get_option_marketdata(...)` / `get_option_quote(...)` | contracts in the chain already carry market data |
| `options_owned()` | `client.get_option_positions()` |
| — | `client.get_options_expirations(symbol)` |
| — | `client.order_option()`, `client.order_option_spread()` |

```python
expiration = client.get_options_expirations("AAPL")[0]
chain = client.get_options_chain("AAPL", expiration)

for call in chain.calls[:5]:
    print(call.strike, call.mark, call.delta, call.iv)
```

Each `OptionContract` carries `strike`, `mark`, `bid`, `ask`, `iv`, `delta`, `gamma`, `theta`, `vega`, `volume` and `open_interest`. Index options work the same way.

## Orders

pyrh's twelve order methods become three, with the order type determined by arguments:

| pyrh | pyhood |
| --- | --- |
| `place_market_buy_order(...)` | `client.buy_stock(symbol, quantity)` |
| `place_market_sell_order(...)` | `client.sell_stock(symbol, quantity)` |
| `place_limit_buy_order(...)` | `client.buy_stock(symbol, quantity, price=...)` |
| `place_limit_sell_order(...)` | `client.sell_stock(symbol, quantity, price=...)` |
| `place_stop_loss_buy_order(...)` | `client.buy_stock(symbol, quantity, stop_price=...)` |
| `place_stop_loss_sell_order(...)` | `client.sell_stock(symbol, quantity, stop_price=...)` |
| `place_stop_limit_buy_order(...)` | `client.buy_stock(symbol, quantity, price=..., stop_price=...)` |
| `place_stop_limit_sell_order(...)` | `client.sell_stock(symbol, quantity, price=..., stop_price=...)` |
| `place_buy_order(...)` / `place_sell_order(...)` | `client.order_stock(symbol, quantity, side=...)` |
| `submit_buy_order(...)` / `submit_sell_order(...)` | same |
| `place_order(...)` | `client.order_stock(...)` |
| `cancel_order(order_id)` | `client.cancel_order(order_id)` |
| `get_open_orders()` | `client.get_stock_orders()`, filter on `order.status` |
| `order_history()` | `client.get_stock_orders(start_date=...)` |

```python
client.buy_stock("AAPL", 1)                      # market
client.buy_stock("AAPL", 1, price=150.00)        # limit
client.sell_stock("AAPL", 1, stop_price=140.00)  # stop
```

Also available and absent from pyrh: `buy_stock_by_price()` and `sell_stock_by_price()` for dollar-amount fractional orders ([pyrh #200](https://github.com/robinhood-unofficial/pyrh/issues/200)), trailing stops via `trail_amount=` or `trail_percent=`, extended and 24-hour sessions via `market_hours=`, and `cancel_all_stock_orders()`.

Orders that Robinhood rejects now raise `OrderError` rather than returning a blank object, which matters because rejections arrive as field-level validation errors carrying no `detail` key.

## Account and portfolio

| pyrh | pyhood |
| --- | --- |
| `get_account()` | `client.get_all_accounts()` |
| `user()` | `client.get_user_profile()` |
| `positions()` / `securities_owned()` | `client.get_positions()` |
| `portfolio()` | `client.get_buying_power()`, `client.get_positions()`, `client.get_portfolio_performance()` |
| `dividends()` | `client.get_dividends()` |
| `get_watchlists()` | `client.get_watchlists()` |
| `investment_profile()` | not ported |

`get_positions()` returns `Position` objects with `quantity`, `average_cost`, `current_price`, `equity`, `unrealized_pl` and `unrealized_pl_pct` already computed.

## What pyhood adds

None of these exist in pyrh:

- **Futures** contracts, quotes, orders, positions and P&L
- **The official Crypto Trading API**, key-pair authenticated, separate from the unofficial endpoints
- **IRA and retirement accounts**, discoverable and tradable via `account_number=`
- **Banking**, ACH transfers, documents and statements
- **IPO Access**
- **A stock screener** (`pyhood.screener.StockScreener`), which is [pyrh #309](https://github.com/robinhood-unofficial/pyrh/issues/309)
- **Interest, fees and transfers**
- **`is_market_open()`**, aware of extended and 24-hour sessions

## Things to know

**Sessions are stored as JSON**, owner-only at `~/.pyhood/session.json`, created `0600` inside a `0700` directory.

**`get_portfolio_historicals()` raises `APIError`.** Robinhood retired `/portfolios/historicals/` and it now returns 404 for every parameter combination. `get_portfolio_performance()` calls the endpoint that replaced it, returning the chart view model unmapped, because its y values are returns rather than equity.

**Fractional orders are unverified end to end.** The payload and the rounding are covered by tests, but a fractional order is a market order and executes immediately, so the fill has never been exercised.

Questions about anything not covered here are welcome in [Discussions](https://github.com/jamestford/pyhood/discussions).
