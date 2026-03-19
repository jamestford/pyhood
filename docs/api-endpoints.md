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
| `last_trade_volume` | string | Volume of last trade |
| `last_extended_hours_trade_price` | string | After-hours price |
| `updated_at` | string | Timestamp |
| `instrument` | string | Instrument URL |

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

## Options

### GET /options/chains/

Available options expiration dates for a symbol.

```
GET /options/chains/?equity_instrument_ids={instrument_id}
```

!!! warning
    Use `equity_instrument_ids` param, not `symbol`. Get the instrument ID from `/instruments/?symbol=AAPL` first.

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
```

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
| `most-popular-under-25` | 24 | Retail-popular cheap stocks |
| `upcoming-earnings` | 70 | Earnings in next 2 weeks |
| `new-on-robinhood` | 172 | Recently added |
| `etf` | 500 | ETFs |
| `technology` | 500 | Tech sector |
| `finance` | 500 | Financial sector |
| `energy` | 386 | Energy sector |
| `healthcare` | 212 | Healthcare sector |

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

Your default watchlist.

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
