# Robinhood IRA API — Reverse Engineering Notes

**Date:** 2026-03-23
**Account:** Roth IRA (ira_roth)
**Account Number:** <IRA_ACCOUNT_NUMBER>
**Status:** ✅ Fully working — stock and option orders confirmed

---

## 1. Discovery: Finding the IRA Account

### Problem
The standard `/accounts/` endpoint only returns the individual margin account (<INDIVIDUAL_ACCOUNT_NUMBER>).
The IRA account is **invisible** to `/accounts/` — no query parameter (`type`, `brokerage_account_type`, `all`, `include_retirement`, `page_size`, etc.) makes it appear.

### Solution
The IRA account is discoverable via the **Bonfire API**:

```
GET https://bonfire.robinhood.com/accounts/unified/
```

This returns a `results` array with **all** accounts (individual + IRA). Each entry includes:
- `account_number` / `rhs_account_number`
- `brokerage_account_type` (e.g., `"individual"`, `"ira_roth"`)
- `account_buying_power`, `uninvested_cash`, `options_buying_power`
- `equities.rhs_account_number` — the account number for order routing
- Full portfolio equity, market value, etc.

### Direct Access
Once you know the account number, you can access it directly through the standard API:

```
GET https://api.robinhood.com/accounts/<IRA_ACCOUNT_NUMBER>/
```

This returns the full account object (same schema as individual accounts), including:
- `type`: `"cash"` (IRA accounts are always cash, no margin)
- `brokerage_account_type`: `"ira_roth"`
- `buying_power`: `"7210.0000"`
- `option_level`: `"option_level_2"` (after enabling; `null` by default)
- `cash_balances` (not `margin_balances` — IRA uses cash balances)

---

## 2. IRA Account Properties

| Field | Value | Notes |
|-------|-------|-------|
| `account_number` | `<IRA_ACCOUNT_NUMBER>` | |
| `type` | `cash` | No margin on IRA |
| `brokerage_account_type` | `ira_roth` | |
| `option_level` | `option_level_2` (max) | Level 3 capped to 2 |
| `buying_power` | `7210.0000` | |
| `is_default` | `false` | Individual is default |
| `is_original` | `false` | |
| `sweep_enabled` | `false` | |
| `margin_balances` | `null` | Cash account only |
| `cash_balances` | `{...}` | Has cash balance block |

### Key Differences from Individual Account
- `type` is `"cash"` not `"margin"`
- `margin_balances` is `null`; uses `cash_balances` instead
- `option_level` maxes at `option_level_2` (long puts/calls, covered calls/puts — no spreads, no naked)
- `option_trading_on_expiration_enabled` defaults to `false`
- `is_default` is `false` (individual account is default)

---

## 3. Enabling Options on IRA

By default, `option_level` is `null` (options not enabled).

### Enable via PATCH
```
PATCH https://api.robinhood.com/accounts/<IRA_ACCOUNT_NUMBER>/
Content-Type: application/json

{"option_level": "option_level_3"}
```

The server **caps it to `option_level_2`** for IRA accounts. This is the maximum allowed.

**option_level_2 allows:**
- Buy calls (long calls)
- Buy puts (long puts)
- Sell covered calls
- Sell cash-secured puts

**option_level_2 does NOT allow:**
- Vertical spreads
- Iron condors
- Naked options

---

## 4. Placing Stock Orders on IRA

Standard `/orders/` endpoint works. Just use the IRA account URL:

```python
payload = {
    'account': 'https://api.robinhood.com/accounts/<IRA_ACCOUNT_NUMBER>/',
    'instrument': instrument_url,
    'symbol': 'AAPL',
    'type': 'limit',
    'time_in_force': 'gfd',
    'trigger': 'immediate',
    'price': '150.00',
    'quantity': '1.00000000',
    'side': 'buy',
    'ref_id': str(uuid.uuid4()),
}

r = session.post('https://api.robinhood.com/orders/', json=payload,
                  headers={'Content-Type': 'application/json'})
```

**Important:** Must send `Content-Type: application/json` header explicitly when posting JSON. The default pyhood session header is `application/x-www-form-urlencoded`.

---

## 5. Placing Option Orders on IRA

Standard `/options/orders/` endpoint works with the IRA account URL:

```python
payload = {
    'account': 'https://api.robinhood.com/accounts/<IRA_ACCOUNT_NUMBER>/',
    'direction': 'debit',  # REQUIRED for options (not 'side')
    'legs': [{
        'position_effect': 'open',
        'side': 'buy',
        'ratio_quantity': 1,
        'option': option_instrument_url,
    }],
    'price': '1.50',
    'quantity': '1',
    'time_in_force': 'gtc',
    'trigger': 'immediate',
    'type': 'limit',
    'override_day_trade_checks': False,
    'override_dtbp_checks': False,
    'ref_id': str(uuid.uuid4()),
}

r = session.post('https://api.robinhood.com/options/orders/', json=payload,
                  headers={'Content-Type': 'application/json'})
```

### Confirmed Working (201 response)
- **Buy to open puts** (long_put strategy) ✅
- Order was accepted with `state: "unconfirmed"` then processed normally
- Cancel via `POST /options/orders/{id}/cancel/` works (200)

### Key Differences for Option Orders
- Use `direction` instead of `side` (unlike stock orders)
  - `"debit"` for buy orders
  - `"credit"` for sell orders (covered calls, CSPs)
- The `account` field is the full URL: `https://api.robinhood.com/accounts/<IRA_ACCOUNT_NUMBER>/`

---

## 6. Querying IRA Positions & Orders

### Positions
```
GET https://api.robinhood.com/positions/?account_number=<IRA_ACCOUNT_NUMBER>
```

### Option Positions
```
GET https://api.robinhood.com/options/aggregate_positions/?account_numbers=<IRA_ACCOUNT_NUMBER>
```

### Option Orders
```
GET https://api.robinhood.com/options/orders/?account_numbers=<IRA_ACCOUNT_NUMBER>
```

### Portfolio
```
GET https://api.robinhood.com/portfolios/<IRA_ACCOUNT_NUMBER>/
```

All standard endpoints work with the IRA account number as a filter parameter.

**Note:** `GET /accounts/<IRA_ACCOUNT_NUMBER>/positions/` returns 404. Use the query param approach.

---

## 7. Endpoints Summary

| Purpose | Endpoint | Method |
|---------|----------|--------|
| **Discover all accounts** | `GET bonfire.robinhood.com/accounts/unified/` | GET |
| **IRA account details** | `GET api.robinhood.com/accounts/<IRA_ACCOUNT_NUMBER>/` | GET |
| **Enable options** | `PATCH api.robinhood.com/accounts/<IRA_ACCOUNT_NUMBER>/` | PATCH |
| **IRA portfolio** | `GET api.robinhood.com/portfolios/<IRA_ACCOUNT_NUMBER>/` | GET |
| **IRA positions** | `GET api.robinhood.com/positions/?account_number=<IRA_ACCOUNT_NUMBER>` | GET |
| **IRA option positions** | `GET api.robinhood.com/options/aggregate_positions/?account_numbers=<IRA_ACCOUNT_NUMBER>` | GET |
| **Place stock order** | `POST api.robinhood.com/orders/` | POST (with account URL in body) |
| **Place option order** | `POST api.robinhood.com/options/orders/` | POST (with account URL in body) |
| **IRA option orders** | `GET api.robinhood.com/options/orders/?account_numbers=<IRA_ACCOUNT_NUMBER>` | GET |

---

## 8. Integration Notes for pyhood

### What Needs Changing
1. **`_get_account_url()`** in `client.py` — Currently calls `/accounts/` which doesn't return IRA accounts. Two options:
   - Use `bonfire.robinhood.com/accounts/unified/` to discover all accounts
   - Accept explicit account number and construct URL directly: `f"https://api.robinhood.com/accounts/{account_number}/"`

2. **`order_option()`** — Uses `side` field where RH actually expects `direction` for options. The current code has `"side": credit_or_debit` which happens to work because the API accepts both for the individual account, but should be `"direction"` for correctness.

3. **Content-Type** — The default session header is `application/x-www-form-urlencoded`. When posting JSON, need to override to `application/json`.

4. **Account parameter** — Add `account_number` param to `order_option()`, `order_stock()`, and position-fetching methods.

### Minimal Changes for IRA Support
```python
# In client.py

def get_all_accounts(self) -> list[dict]:
    """Get all accounts including IRA via bonfire endpoint."""
    r = self._session.get('https://bonfire.robinhood.com/accounts/unified/')
    return r.get('results', [])

def _get_account_url(self, account_number: str | None = None) -> str:
    if account_number:
        return f"https://api.robinhood.com/accounts/{account_number}/"
    # Default to first account from standard endpoint
    data = self._session.get_paginated(urls.ACCOUNTS)
    if not data:
        raise OrderError("No accounts found")
    return data[0].get("url", "")
```

---

## 9. Limitations

- **Option Level 2 max** — IRA accounts cannot get level 3. No spreads, no naked options.
- **Cash account only** — No margin, no instant deposits (1K max early access vs 48K on individual)
- **No futures** — `has_futures_account: false`
- The `/accounts/` endpoint **never returns IRA accounts** — must use bonfire or direct URL
- DRIP not enabled by default (`eligible_for_drip: false`)
