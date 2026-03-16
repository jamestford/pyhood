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

## Example: Find High Vol/OI Calls

```python
chain = client.get_options_chain("AAPL", expiration="2026-04-17", option_type="call")

unusual = [c for c in chain.calls if c.vol_oi_ratio > 2.0 and c.open_interest > 500]

for c in sorted(unusual, key=lambda x: x.vol_oi_ratio, reverse=True):
    print(f"  {c.strike} call | Vol/OI: {c.vol_oi_ratio:.1f} | Vol: {c.volume:,} | OI: {c.open_interest:,}")
```
