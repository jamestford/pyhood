# Futures Trading

Pyhood provides access to Robinhood's futures trading API, including contract details,
real-time quotes, order history, and P&L calculation.

## Quick Start

```python
from pyhood import login, PyhoodClient

login("user@example.com", "password")
client = PyhoodClient()

# Get a futures contract
contract = client.get_futures_contract("ESH26")
print(f"{contract.name} — multiplier: {contract.multiplier}")

# Get a real-time quote
quote = client.get_futures_quote("ESH26")
print(f"Last: {quote.last_price}  Bid: {quote.bid}  Ask: {quote.ask}")

# Get filled orders and calculate P&L
orders = client.get_filled_futures_orders()
total_pnl = client.calculate_futures_pnl(orders=orders)
print(f"Realized P&L: ${total_pnl:.2f}")
```

## Methods

### `get_futures_account_id()`

Auto-discovers the futures account ID by filtering Ceres accounts for
`accountType == 'FUTURES'`.

**Returns:** `str` — the futures account ID.

**Raises:** `APIError` if no futures account exists.

### `get_futures_contract(symbol)`

Get contract details for a single futures symbol. Makes two requests: one for
the contract and one for the product it belongs to (`/ES` for `/ESH26`), which
is where the tick size, underlying and asset class are kept.

**Parameters:**

- `symbol` (str): Futures symbol, e.g. `'ESH26'` (E-mini S&P 500 March 2026).

**Returns:** `FuturesContract` with fields:

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | str | Contract symbol |
| `name` | str | Human-readable name |
| `contract_id` | str | Robinhood internal ID |
| `expiration` | str | Expiration date (YYYY-MM-DD) |
| `tick_size` | float \| None | Minimum price increment |
| `multiplier` | float | Contract multiplier |
| `status` | str | Contract state (e.g. 'active') |
| `underlying` | str | Product symbol (e.g. 'ES') |
| `asset_class` | str | Product group (e.g. 'stock_index', 'energy', 'metals') |

If the product lookup fails, the contract is still returned, with `tick_size`
set to `None` and `underlying` and `asset_class` empty.

### `get_futures_contracts(symbols)`

Batch version — fetches contracts for multiple symbols. Skips failures silently.

**Parameters:**

- `symbols` (list[str]): List of futures symbols.

**Returns:** `dict[str, FuturesContract]` mapping symbol to contract.

### `get_futures_quote(symbol, include_fundamentals=False)`

Get a real-time quote for a futures symbol. Resolves the symbol to a contract ID
internally.

**Parameters:**

- `symbol` (str): Futures symbol.
- `include_fundamentals` (bool): Also fetch the session's high, low, previous
  close and volume. Robinhood's futures quote does not include them, so they
  are `None` without this. Costs one more request.

**Returns:** `FuturesQuote` with fields:

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | str | Contract symbol |
| `last_price` | float | Last trade price |
| `bid` | float | Current bid |
| `ask` | float | Current ask |
| `high` | float \| None | Session high, with `include_fundamentals=True` |
| `low` | float \| None | Session low, with `include_fundamentals=True` |
| `prev_close` | float \| None | Previous close, with `include_fundamentals=True` |
| `volume` | int \| None | Trading volume, with `include_fundamentals=True` |
| `contract_id` | str | Robinhood contract ID |

Robinhood does not publish open interest for futures.

### `get_futures_quotes(symbols, include_fundamentals=False)`

Batch version — fetches quotes for multiple symbols. Skips failures silently.

**Returns:** `dict[str, FuturesQuote]`

### `get_futures_orders(account_id=None)`

Get all historical futures orders with automatic cursor-based pagination.

**Parameters:**

- `account_id` (str, optional): Futures account ID. Auto-discovered if not provided.

**Returns:** `list[FuturesOrder]`

### `get_filled_futures_orders(account_id=None)`

Same as `get_futures_orders()` but filtered to only filled orders.

### `calculate_futures_pnl(orders=None, account_id=None)`

Calculate total realized P&L across futures orders. Only counts CLOSING orders
to avoid double-counting.

**Parameters:**

- `orders` (list[FuturesOrder], optional): Pre-fetched orders. If None, fetches filled orders.
- `account_id` (str, optional): Used to fetch orders if `orders` is None.

**Returns:** `float` — total realized P&L.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/arsenal/v1/futures/contracts/symbol/{symbol}/` | Contract details |
| `/marketdata/futures/quotes/v1/` | Real-time quotes (by contract ID) |
| `/ceres/v1/accounts/` | Futures account discovery |
| `/ceres/v1/accounts/{id}/orders/` | Order history (cursor-paginated) |

## Notes

- Futures endpoints require the `Rh-Contract-Protected: true` header (set automatically).
- The futures account is separate from the standard brokerage account — it has its own
  account ID discovered via the Ceres API.
- Order pagination uses cursor-based pagination (same `next` URL pattern as standard
  Robinhood pagination).
- P&L is nested inside orders at `order.legs[0].executions[0].settlement.realized_pnl`.
  The `_extract_futures_pnl()` method handles this.
- Futures symbols follow the format: root + month code + year digits
  (e.g. `ESH26` = E-mini S&P 500, March 2026).
