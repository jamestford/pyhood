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
print(f"Updated:    {quote.timestamp}")
```

The `Quote` object is a frozen dataclass — fully typed, IDE-friendly, and immutable.

### Volume, P/E, market cap and the 52-week range

Robinhood's quote does not include these. They come from the fundamentals
endpoint, so `volume`, `pe_ratio`, `market_cap`, `high_52w` and `low_52w` are
`None` on a plain quote. Pass `include_fundamentals=True` to fill them, at the
cost of one more request:

```python
quote = client.get_quote("AAPL", include_fundamentals=True)

print(f"Volume:     {quote.volume:,}")
print(f"PE Ratio:   {quote.pe_ratio}")
print(f"Market Cap: {quote.market_cap:,.0f}")
print(f"52w Range:  ${quote.low_52w:.2f} to ${quote.high_52w:.2f}")
```

Any of them can still be `None` when Robinhood has no figure, such as the P/E
of a company with no earnings.

## Batch Quotes

Fetch multiple symbols in a single batched request:

```python
quotes = client.get_quotes(["AAPL", "MSFT", "NVDA", "TSLA"])

for symbol, quote in quotes.items():
    print(f"{symbol}: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")
```

Symbols are batched 1,000 to a request. `get_quotes()` takes
`include_fundamentals=True` too. Fundamentals come 100 symbols to a request, so
that adds one request per 100 symbols.

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
