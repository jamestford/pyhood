# Stock Quotes

## Single Quote

```python
quote = client.get_quote("AAPL")

print(f"Symbol:     {quote.symbol}")
print(f"Price:      ${quote.price:.2f}")
print(f"Prev Close: ${quote.prev_close:.2f}")
print(f"Change:     {quote.change_pct:+.1f}%")
print(f"Bid:        ${quote.bid:.2f}")
print(f"Ask:        ${quote.ask:.2f}")
print(f"Volume:     {quote.volume:,}")
```

The `Quote` object is a frozen dataclass — fully typed, IDE-friendly, and immutable.

## Batch Quotes

Fetch multiple symbols in a single batched request:

```python
quotes = client.get_quotes(["AAPL", "MSFT", "NVDA", "TSLA"])

for symbol, quote in quotes.items():
    print(f"{symbol}: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")
```

Symbols are batched in groups of 25 per API call for efficiency.

## Fundamentals

Get PE ratio, market cap, 52-week range, and more:

```python
fundamentals = client.get_fundamentals("AAPL")

print(f"PE Ratio:   {fundamentals.get('pe_ratio')}")
print(f"Market Cap: {fundamentals.get('market_cap')}")
print(f"52w High:   {fundamentals.get('high_52_weeks')}")
print(f"52w Low:    {fundamentals.get('low_52_weeks')}")
```

!!! note
    `get_fundamentals()` currently returns a raw dict. Typed model coming in a future release.

## Earnings

Check for upcoming earnings within a lookahead window:

```python
earnings = client.get_earnings("AAPL", lookahead_days=14)

if earnings:
    print(f"Earnings date: {earnings.date}")
    print(f"Timing:        {earnings.timing}")  # 'am' or 'pm'
    print(f"EPS estimate:  {earnings.eps_estimate}")
```

Returns `None` if no earnings are scheduled within the window.
