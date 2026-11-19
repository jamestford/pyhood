# Robinhood API Endpoints Reference

Robinhood does not publish official API documentation for stocks/options. This reference is based on reverse engineering and live testing. Endpoints may change without notice.

Base URL: `https://api.robinhood.com`

## Batch Limits

| Endpoint | Max Batch | Limiting Factor | Safe Default |
|----------|-----------|-----------------|--------------|
| `/fundamentals/` | 100 symbols | Hard count limit | 100 |
| `/quotes/` | ~1,220 symbols | URL length (~5,700 chars) | 1,000 |
| `/marketdata/options/` | ~17 instruments | URL length | 17 |

---

## Market Data

### GET /quotes/

Current price data for one or many symbols.

```
GET /quotes/?symbols=AAPL,MSFT,TSLA
GET /quotes/AAPL/
```

**Batch:** ✅ Up to ~1,220 symbols (comma-separated)

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Ticker symbol |
| `last_trade_price` | string | Current/last trade price |
| `previous_close` | string | Previous day's close |
| `bid_price` | string | Current bid |
| `ask_price` | string | Current ask |
| `bid_size` | int | Bid size |
| `ask_size` | int | Ask size |
| `last_extended_hours_trade_price` | string | After-hours price |
| `updated_at` | string | Timestamp |
| `instrument` | string | Instrument URL |

The quote has no volume. Today's volume is `volume` on `/fundamentals/`.

---

### GET /fundamentals/

Fundamental data including valuation, 52-week range, and company info.

```
GET /fundamentals/?symbols=AAPL,MSFT,TSLA
GET /fundamentals/AAPL/
```

**Batch:** ✅ Up to 100 symbols (comma-separated)

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `high_52_weeks` | string | 52-week high price |
| `high_52_weeks_date` | string | Date of 52-week high |
| `low_52_weeks` | string | 52-week low price |
| `low_52_weeks_date` | string | Date of 52-week low |
| `market_cap` | string | Market capitalization |
| `pb_ratio` | string | Price-to-book ratio |
| `pe_ratio` | string | Price-to-earnings ratio |
| `shares_outstanding` | string | Total shares outstanding |
| `float` | string | Public float |
| `dividend_yield` | string | Dividend yield |
| `volume` | string | Today's volume |
| `average_volume` | string | Average daily volume |
| `average_volume_2_weeks` | string | 2-week average volume |
| `average_volume_30_days` | string | 30-day average volume |
| `open` | string | Today's open price |
| `high` | string | Today's high |
| `low` | string | Today's low |
| `sector` | string | Company sector |
| `industry` | string | Company industry |
| `description` | string | Company description |
| `ceo` | string | CEO name |
| `headquarters_city` | string | HQ city |
| `headquarters_state` | string | HQ state |
| `num_employees` | int | Employee count |
| `year_founded` | int | Year founded |

---

### GET /marketdata/historicals/

Historical OHLCV candle data.

```
GET /marketdata/historicals/?symbols=AAPL&interval=day&span=year&bounds=regular
```

**Batch:** ❌ Single symbol only

**Parameters:**

| Param | Values |
|-------|--------|
| `symbols` | Single ticker |
| `interval` | `5minute`, `10minute`, `hour`, `day`, `week` |
| `span` | `day`, `week`, `month`, `3month`, `year`, `5year` |
| `bounds` | `regular`, `extended`, `trading` |

**Valid Combinations (verified):**

| Interval | day | week | month | 3month | year | 5year |
|----------|-----|------|-------|--------|------|-------|
| `5minute` | 39 candles | 195 candles | ❌ | ❌ | ❌ | ❌ |
| `10minute` | 39 candles | 195 candles | ❌ | ❌ | ❌ | ❌ |
| `hour` | 6 candles | 30 candles | 120 candles | 357 candles | ❌ | ❌ |
| `day` | ❌ | 5 candles | 20 candles | 60 candles | 251 candles | **1,255 candles** |
| `week` | ❌ | ❌ | 4 candles | 13 candles | 52 candles | **261 candles** |

Invalid combinations return HTTP 400. Maximum data: **5 years of daily candles (1,255 data points)**.

**Returns (per candle):**

| Field | Type | Description |
|-------|------|-------------|
| `begins_at` | string | Candle start timestamp |
| `open_price` | string | Open price |
| `close_price` | string | Close price |
| `high_price` | string | High price |
| `low_price` | string | Low price |
| `volume` | int | Volume |
| `session` | string | Trading session (`reg`, `pre`, `post`) |
| `interpolated` | bool | Whether data was interpolated |

---

### GET /marketdata/earnings/

Earnings calendar with EPS estimates and actuals.

```
GET /marketdata/earnings/?symbol=AAPL
```

**Batch:** ❌ Single symbol

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `report.date` | string | Earnings date (YYYY-MM-DD) |
| `report.timing` | string | `am` or `pm` |
| `eps.estimate` | string | Consensus EPS estimate |
| `eps.actual` | string | Actual EPS (after report) |

---

### GET /midlands/ratings/

Analyst ratings and price targets.

```
GET /midlands/ratings/?symbol=AAPL
```

**Batch:** ❌ Single symbol

---

### GET /midlands/news/

Recent news articles for a symbol.

```
GET /midlands/news/?symbol=AAPL
```

**Batch:** ❌ Single symbol

---

## Indexes

### GET /indexes/

Instrument lookup for index symbols (SPX, NDX, VIX, RUT, XSP). Used instead of `/instruments/` when fetching index option chains.

```
GET /indexes/?symbol=SPX
```

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Index instrument UUID |
| `symbol` | string | Index symbol |
| `tradable_chain_ids` | list | Options chain IDs (plural — indexes can have multiple chains) |

---

### GET /marketdata/indexes/values/v1/{id}/

Market data (quote) for an index instrument.

```
GET /marketdata/indexes/values/v1/{index_id}/
```

**Returns:** Same fields as `/marketdata/quotes/` — `last_trade_price`, `bid_price`, `ask_price`, etc.

---

## Options

### GET /options/chains/

Available options expiration dates for a symbol.

```
GET /options/chains/?equity_instrument_ids={instrument_id}
GET /options/chains/?ids={chain_id}
```

!!! warning
    For **equity options**: use `equity_instrument_ids` param. Get the instrument ID from `/instruments/?symbol=AAPL` first.
    For **index options**: use `ids` param with a chain ID from `/indexes/?symbol=SPX` → `tradable_chain_ids[0]`.

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `expiration_dates` | list | Available expiration dates |
| `symbol` | string | Underlying symbol |
| `trade_value_multiplier` | string | Contract multiplier (usually 100) |

---

### GET /options/instruments/

Option contracts filtered by symbol, expiration, and type.

```
GET /options/instruments/?chain_symbol=AAPL&expiration_dates=2026-04-17&state=active&type=call
GET /options/instruments/?chain_symbol=SPXW&expiration_dates=2026-04-17&state=active&type=call
```

!!! note
    For index options, use the mapped chain symbol: SPX → `SPXW`, NDX → `NDXP`, VIX → `VIXW`, RUT → `RUTW`. pyhood handles this mapping automatically.

**Returns (per contract):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Option instrument ID |
| `url` | string | Full instrument URL |
| `strike_price` | string | Strike price |
| `expiration_date` | string | Expiration date |
| `type` | string | `call` or `put` |
| `state` | string | `active`, `expired` |

---

### GET /marketdata/options/

Market data and Greeks for option instruments.

```
GET /marketdata/options/?instruments={url1},{url2},...
```

!!! warning
    Pass **full instrument URLs**, not IDs. Max ~17 per request.

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `adjusted_mark_price` | string | Mid-market price |
| `bid_price` | string | Bid price |
| `ask_price` | string | Ask price |
| `implied_volatility` | string | IV (decimal, e.g., 0.35 = 35%) |
| `delta` | string | Delta |
| `gamma` | string | Gamma |
| `theta` | string | Theta |
| `vega` | string | Vega |
| `rho` | string | Rho |
| `volume` | int | Day's volume |
| `open_interest` | int | Open interest |
| `chance_of_profit_long` | string | Estimated chance of profit (long) |
| `chance_of_profit_short` | string | Estimated chance of profit (short) |

---

## Discovery & Lists

### GET /midlands/movers/sp500/

Top 10 S&P 500 daily movers.

```
GET /midlands/movers/sp500/?direction=up
GET /midlands/movers/sp500/?direction=down
```

**Returns:** 10 stocks with `symbol`, `price_movement`, `description`

---

### GET /midlands/tags/tag/{tag}/

Pre-built stock lists by category.

```
GET /midlands/tags/tag/upcoming-earnings/
```

**Available tags:**

| Tag | ~Count | Description |
|-----|--------|-------------|
| `100-most-popular` | 100 | Top 100 stocks on Robinhood |
| `top-movers` | 20 | Daily movers |
| `most-popular-under-25` | 24 | Retail-popular cheap stocks |
| `upcoming-earnings` | 70 | Earnings in next 2 weeks |
| `new-on-robinhood` | 172 | Recently added |
| `large-cap` | 88 | Large cap stocks |
| `mid-cap` | 16 | Mid cap stocks |
| `small-cap` | 104 | Small cap stocks |
| `etf` | 500 | ETFs |
| `technology` | 500 | Tech sector |
| `finance` | 500 | Financial sector |
| `energy` | 386 | Energy sector |
| `healthcare` | 212 | Healthcare sector |
| `real-estate` | 453 | Real estate sector |
| `banking` | 441 | Banking sector |
| `retail` | 500 | Retail sector |
| `manufacturing` | 495 | Manufacturing sector |
| `insurance` | 293 | Insurance sector |
| `utilities` | 222 | Utilities sector |
| `food` | 219 | Food sector |
| `media` | 192 | Media sector |
| `reit` | 203 | REITs |
| `automotive` | 175 | Automotive sector |
| `entertainment` | 138 | Entertainment sector |
| `china` | 104 | Chinese stocks |
| `aerospace` | 99 | Aerospace sector |
| `gold` | 69 | Gold-related |
| `oil` | 66 | Oil-related |
| `e-commerce` | 53 | E-commerce |
| `travel` | 47 | Travel sector |
| `silver` | 34 | Silver-related |
| `social-media` | 13 | Social media companies |

**Returns:** `instruments` (list of instrument URLs), `name`, `description`

---

## Instruments

### GET /instruments/

List or search all instruments.

```
GET /instruments/?active_instruments_only=true    # All tradeable (~4,909 stocks)
GET /instruments/?query=apple                      # Search by name
GET /instruments/?symbol=AAPL                      # Exact symbol lookup
```

**Paginated:** ✅ 100 per page

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Instrument UUID |
| `url` | string | Full instrument URL |
| `symbol` | string | Ticker symbol |
| `name` | string | Full company name |
| `simple_name` | string | Short company name |
| `tradeable` | bool | Currently tradeable |
| `state` | string | `active`, `inactive` |
| `type` | string | `stock`, `etp`, `adr` |
| `tradable_chain_id` | string | Options chain ID (if available) |
| `market` | string | Market URL |
| `country` | string | Country code |
| `list_date` | string | IPO / listing date |

---

## Account

### GET /positions/

Current stock positions.

```
GET /positions/?nonzero=true
```

**Returns:** `quantity`, `average_buy_price`, `instrument`, `created_at`

### GET /options/aggregate_positions/

Current option positions.

### GET /portfolios/

Portfolio summary with total value.

### GET /accounts/

Account details with buying power and cash balances.

### GET /orders/

Stock order history (paginated).

### GET /options/orders/

Options order history (paginated).

### GET /midlands/lists/default/

Your watchlists: the lists you created and the Robinhood lists you follow.

**Returns:** `results`, a list of list records with `id`, `display_name`, `item_count`, `owner_type` (`custom` or `robinhood`) and `allowed_object_types`. The records do not include the lists' items.

`GET /midlands/lists/` is not the same thing. It returns 400 without an `owner_type` parameter.

### GET /midlands/lists/items/

The items on one list.

```
GET /midlands/lists/items/?list_id={list_id}&load_all_attributes=false
```

**Returns:** `results`, one per item, with `symbol`, `name`, `object_id` and `object_type` (`instrument`, `currency_pair`, ...).

Without `load_all_attributes=false` every item also carries live prices, and the request is rejected with 400 for an options watchlist.

### POST /midlands/lists/items/

Add or remove items. The JSON body maps a list ID to its changes:

```json
{"<list_id>": [{"object_type": "instrument", "object_id": "<instrument_id>", "operation": "create"}]}
```

`operation` is `create` to add and `delete` to remove.

### GET /dividends/

Dividend payment history.

---

## Profile

### GET /user/

Basic account information (user ID, URLs).

### GET /user/investment_profile/

| Field | Type | Description |
|-------|------|-------------|
| `total_net_worth` | string | Self-reported net worth |
| `annual_income` | string | Self-reported income |
| `risk_tolerance` | string | Risk preference |
| `investment_experience` | string | Experience level |

---

## Futures

### GET /arsenal/v1/futures/contracts/symbol/{symbol}/

Contract details for a single futures symbol.

```
GET /arsenal/v1/futures/contracts/symbol/ESH26/
```

!!! note
    Requires `Rh-Contract-Protected: true` header (set automatically by pyhood).

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
The contract, inside a `result` envelope:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Contract UUID |
| `productId` | string | UUID of the product the contract belongs to |
| `symbol` | string | Symbol with exchange (e.g. `/ESH26:XCME`) |
| `displaySymbol` | string | Symbol (e.g. `/ESH26`) |
| `description` | string | Human-readable name |
| `expiration` | string | Expiration date (YYYY-MM-DD) |
| `multiplier` | string | Contract multiplier |
| `state` | string | e.g. `FUTURES_STATE_ACTIVE` |
| `tradability` | string | e.g. `FUTURES_TRADABILITY_TRADABLE` |

The contract has no tick size, underlying or asset class. Those are on its product.

---

### GET /arsenal/v1/futures/products/{product_id}/

The product a contract belongs to, such as `/ES` for `/ESH26`.

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Product UUID |
| `displaySymbol` | string | Product symbol (e.g. `/ES`) |
| `simpleName` | string | Human-readable name |
| `exchange` | string | Exchange MIC (e.g. `XCME`) |
| `priceIncrements` | string | Minimum price increment (e.g. `0.25`) |
| `rhdProductGroup` | string | e.g. `RHD_PRODUCT_GROUP_STOCK_INDEX`, `RHD_PRODUCT_GROUP_ENERGY` |
| `underlyingAsset` | string | e.g. `PRODUCT_UNDERLYING_ASSET_INDICES` |
| `delivery` | string | `PRODUCT_DELIVERY_CASH` or `PRODUCT_DELIVERY_PHYSICAL` |
| `activeFuturesContractId` | string | UUID of the front contract |

---

### GET /marketdata/futures/quotes/v1/

Real-time quotes for futures contracts.

```
GET /marketdata/futures/quotes/v1/?ids={contract_id}
```

**Parameters:**

| Param | Description |
|-------|-------------|
| `ids` | Contract UUID (from contract lookup) |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
The quote, inside a `{"status", "data": [{"status", "data": {...}}]}` envelope:

| Field | Type | Description |
|-------|------|-------------|
| `last_trade_price` | string | Last trade price |
| `last_trade_size` | int | Last trade size |
| `bid_price` | string | Current bid |
| `bid_size` | int | Bid size |
| `ask_price` | string | Current ask |
| `ask_size` | int | Ask size |
| `instrument_id` | string | Contract UUID |
| `symbol` | string | Symbol with exchange |
| `updated_at` | string | Timestamp |

The quote has no high, low, previous close or volume. Those are on the fundamentals endpoint. Open interest is on neither.

---

### GET /marketdata/futures/fundamentals/v1/

Session figures for futures contracts.

```
GET /marketdata/futures/fundamentals/v1/?ids={contract_id}
```

**Returns:**

The same envelope as the quote, holding:

| Field | Type | Description |
|-------|------|-------------|
| `instrument_id` | string | Contract UUID |
| `open` | string | Session open |
| `high` | string | Session high |
| `low` | string | Session low |
| `previous_close_price` | string | Previous close |
| `volume` | string | Trading volume |

---

### GET /ceres/v1/accounts/

Futures account discovery. Filter by `accountType == 'FUTURES'` to find the futures account ID.

```
GET /ceres/v1/accounts/
```

**Returns:** List of accounts with `id`, `accountType` fields.

---

### GET /ceres/v1/accounts/{account_id}/orders/

Historical futures orders with cursor-based pagination.

```
GET /ceres/v1/accounts/{account_id}/orders/
```

**Paginated:** Yes (cursor-based, uses `next` URL)

**Returns (per order):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Order UUID |
| `symbol` | string | Futures symbol |
| `side` | string | `buy` or `sell` |
| `type` | string | Order type |
| `quantity` | string | Number of contracts |
| `price` | string | Order price |
| `state` | string | `filled`, `pending`, `cancelled` |
| `created_at` | string | Timestamp |
| `opening_strategy` | string | Set on opening orders |
| `closing_strategy` | string | Set on closing orders |
| `legs[].executions[].settlement.realized_pnl` | string | P&L (nested, closing orders only) |

---

## Debit Card (Cash Management)

### GET https://minerva.robinhood.com/history/transactions/

Debit card transaction history. Uses a different base URL (`minerva.robinhood.com`) but the same OAuth bearer token.

```
GET https://minerva.robinhood.com/history/transactions/
GET https://minerva.robinhood.com/history/transactions/?type=pending
```

**Parameters:**

| Param | Values | Description |
|-------|--------|-------------|
| `type` | `pending`, `settled` | Filter by transaction state |

**Paginated:** ✅ Standard `next`/`previous` pagination

**Returns (per transaction):**

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Transaction UUID |
| `description` | string | Transaction description |
| `amount` | string | Dollar amount |
| `category` | string | Transaction category |
| `direction` | string | `debit` or `credit` |
| `state` | string | `completed`, `pending` |
| `initiated_at` | string | Timestamp when initiated |
| `completed_at` | string | Timestamp when settled |
| `merchant` | object | Merchant details (includes `name`) |

!!! warning
    This is an undocumented internal API. It may change without notice. Requires an active Cash Management / debit card on the account.

---

## Authentication

### POST /oauth2/token/

Login (password grant) or refresh (refresh_token grant).

See [Authentication](authentication.md) for details.

### POST /oauth2/revoke_token/

Logout and revoke tokens.

---

## Markets

### GET /markets/

List of available markets (NYSE, NASDAQ, etc.).

### GET /markets/{market}/hours/{date}/

Market hours for a specific date. Returns open/close times and whether the market is open.
