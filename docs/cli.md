# Command Line

The `pyhood` command answers the most common questions about an account without any code, and sets up and checks your login.

Every command on this page that touches your account is **read-only**. Orders are placed from Python, not from the command line.

## Account commands

### `pyhood positions`

What the account holds: stocks, then options, with cost, value and unrealized profit or loss.

```text
STOCKS
SYMBOL  SHARES  AVG COST    PRICE      VALUE  UNREALIZED P/L   P/L %
AAPL        10   $340.00  $352.01  $3,520.10        +$120.10  +3.53%
TOTAL                              $3,520.10        +$120.10
```

Option prices are per share; one contract is 100 shares.

### `pyhood orders`

Stock and option orders, newest first.

```text
Orders since 2026-10-25 (times are EST; today is 2026-11-24)
PLACED                SIDE  SYMBOL  TYPE   ORDERED    LIMIT  FILLED  AVG PRICE  STATUS
2026-11-19 12:36 EST  buy   AAPL    stock       10  $350.00      10    $349.80  filled
2026-11-19 11:31 EST  buy   AAPL    stock       10  $340.00       0          -  cancelled
```

| Option | Effect |
|---|---|
| *(none)* | Orders from the last 30 days |
| `--since YYYY-MM-DD` | Orders placed on or after that date |
| `--all` | Every order on record |
| `--symbol AAPL` | Orders for one symbol only |

`ORDERED` is what was asked for and `FILLED` is what actually traded. They differ on a partial fill, such as an IPO Access allocation. An order that never filled shows `0` and `-`.

### `pyhood buying-power`

The cash available to trade with in the main account.

### `pyhood quote SYMBOL [SYMBOL ...]`

Price, change, previous close, bid and ask for each symbol. Add `--fundamentals` for volume, P/E, market cap and the 52-week range, at the cost of one more request.

### `--json`

Each account command takes `--json` to print exact values in place of the table:

```bash
pyhood orders --symbol AAPL --json
```

Two differences from the tables:

- **Times are UTC**, as Robinhood sends them, in ISO-8601 form. The tables convert them to your computer's time zone.
- **Unknown values are `null`**, where the tables print `-`.

## Setup and checks

| Command | What it does |
|---|---|
| `pyhood setup` | Reports what is configured. See [Setup](setup.md) |
| `pyhood setup login` | Logs in and saves a session |
| `pyhood setup crypto` | Generates and registers a Crypto API key pair |
| `pyhood verify` | Reads live prices to confirm the saved login works |
| `pyhood verify crypto` | The same for the Crypto API key pair |
| `pyhood version` | Prints the installed version |

## Scripts and agents

| Command | What it does |
|---|---|
| `pyhood run script.py` | Runs a script with the Python pyhood is installed in, so `import pyhood` works however pyhood was installed. `pyhood run -c "..."` works too |
| `pyhood guide` | Prints how to use pyhood, written for an AI agent: these commands, how to log in, the main methods and the fields they return |

## When a command fails

A failure prints one line to standard error and exits with status 1:

- `Not logged in: ...` followed by `Run: pyhood setup login`
- `Robinhood request failed: ...`
- `No quote for XYZ.` when a symbol is not recognized
