# Options Chains

## Fetching a Chain

```python
chain = client.get_options_chain("AAPL", expiration="2026-04-17")

print(f"Symbol:     {chain.symbol}")
print(f"Expiration: {chain.expiration}")
print(f"Calls:      {len(chain.calls)}")
print(f"Puts:       {len(chain.puts)}")
```

## Exploring Contracts

Each contract is an `OptionContract` dataclass with full Greeks:

```python
for call in chain.calls:
    print(
        f"  {call.strike:>8.2f} call | "
        f"Mark: ${call.mark:.2f} | "
        f"IV: {call.iv:.0%} | "
        f"Delta: {call.delta:+.2f} | "
        f"Vol: {call.volume:,} | "
        f"OI: {call.open_interest:,}"
    )
```

### Available Fields

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | Underlying ticker |
| `option_type` | `str` | `"call"` or `"put"` |
| `strike` | `float` | Strike price |
| `expiration` | `str` | Expiration date (YYYY-MM-DD) |
| `mark` | `float` | Mid-market price |
| `bid` / `ask` | `float` | Bid and ask prices |
| `iv` | `float` | Implied volatility (decimal, e.g., 0.35 = 35%) |
| `delta` | `float` | Delta |
| `gamma` | `float` | Gamma |
| `theta` | `float` | Theta (daily decay) |
| `vega` | `float` | Vega |
| `volume` | `int` | Day's trading volume |
| `open_interest` | `int` | Open interest |

### Computed Properties

```python
# Volume / Open Interest ratio — useful for unusual activity detection
print(f"Vol/OI: {call.vol_oi_ratio:.2f}")

# Cost per contract (mark × 100)
print(f"Cost: ${call.cost_per_contract:.2f}")
```

## Filtering by Type

```python
# Calls only
chain = client.get_options_chain("AAPL", expiration="2026-04-17", option_type="call")

# Puts only
chain = client.get_options_chain("AAPL", expiration="2026-04-17", option_type="put")
```

## Getting Available Expirations

```python
expirations = client.get_options_expirations("AAPL")
print(expirations)
# ['2026-03-21', '2026-03-28', '2026-04-04', '2026-04-17', ...]
```

## Trading Options in IRA Accounts

pyhood supports options trading in IRA accounts. Pass `account_number` to `buy_option` or `sell_option`:

```python
order = client.buy_option(
    symbol="NKE", strike=55.0, expiration="2026-04-02",
    option_type="call", quantity=3, price=1.60,
    account_number="YOUR_IRA_ACCOUNT",
)
```

IRA accounts are limited to Level 2 options: long calls, long puts, covered calls, and cash-secured puts. Spreads and multi-leg strategies are not available. See [Account docs](account.md#ira--retirement-accounts) for details.

## Viewing Option Positions

Use `get_option_positions()` to get fully resolved option positions with live market data, P&L, and Greeks:

```python
positions = client.get_option_positions()

for p in positions:
    print(
        f"{p.symbol} ${p.strike} {p.option_type} exp {p.expiration} | "
        f"qty: {p.quantity} | "
        f"cost: ${p.cost_basis:.0f} | "
        f"value: ${p.current_value:.0f} | "
        f"P&L: ${p.unrealized_pl:.2f} ({p.unrealized_pl_pct:+.1f}%) | "
        f"delta: {p.delta:.3f} | IV: {p.iv:.1%}"
    )
```

For IRA accounts, pass `account_number`:

```python
positions = client.get_option_positions(account_number="YOUR_IRA_ACCOUNT")
```

### OptionPosition Fields

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | Underlying ticker |
| `option_type` | `str` | `"call"` or `"put"` |
| `strike` | `float` | Strike price |
| `expiration` | `str` | Expiration date (YYYY-MM-DD) |
| `quantity` | `int` | Number of contracts |
| `average_open_price` | `float` | Average entry price per share |
| `cost_basis` | `float` | Total cost basis |
| `current_mark` | `float` | Current mid-market price per share |
| `current_value` | `float` | Current total value (mark × qty × 100) |
| `unrealized_pl` | `float` | Unrealized P&L in dollars |
| `unrealized_pl_pct` | `float` | Unrealized P&L as percentage |
| `strategy` | `str` | Strategy type (e.g. `"long_call"`) |
| `delta` | `float` | Position delta |
| `iv` | `float` | Implied volatility (decimal) |
| `theta` | `float` | Theta (daily decay) |

## Example: Find High Vol/OI Calls

```python
chain = client.get_options_chain("AAPL", expiration="2026-04-17", option_type="call")

unusual = [c for c in chain.calls if c.vol_oi_ratio > 2.0 and c.open_interest > 500]

for c in sorted(unusual, key=lambda x: x.vol_oi_ratio, reverse=True):
    print(f"  {c.strike} call | Vol/OI: {c.vol_oi_ratio:.1f} | Vol: {c.volume:,} | OI: {c.open_interest:,}")
```
