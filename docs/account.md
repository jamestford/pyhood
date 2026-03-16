# Account & Positions

## Buying Power

```python
power = client.get_buying_power()
print(f"Buying power: ${power:,.2f}")
```

## Positions

Get all current stock positions:

```python
positions = client.get_positions()

for pos in positions:
    print(
        f"{pos.symbol:>6} | "
        f"Qty: {pos.quantity:.0f} | "
        f"Avg: ${pos.average_cost:.2f} | "
        f"Now: ${pos.current_price:.2f} | "
        f"P/L: ${pos.unrealized_pl:+.2f} ({pos.unrealized_pl_pct:+.1f}%)"
    )
```

### Position Fields

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | Ticker symbol |
| `quantity` | `float` | Number of shares |
| `average_cost` | `float` | Average purchase price |
| `current_price` | `float` | Current market price |
| `equity` | `float` | Current value (quantity × price) |
| `unrealized_pl` | `float` | Unrealized profit/loss in dollars |
| `unrealized_pl_pct` | `float` | Unrealized P/L as percentage |
| `instrument_type` | `str` | `"stock"` or `"option"` |

### Include Zero Positions

By default, only non-zero positions are returned:

```python
# Include closed positions
all_positions = client.get_positions(nonzero=False)
```
