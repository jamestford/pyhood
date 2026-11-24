# Command Line

The `pyhood` command answers the most common questions about an account without any code, and sets up and checks your login.

The account commands are **read-only**. The order commands change your account, and work in two steps: a preview, then a confirmation.

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
| `--open` | Only orders that can still fill, which are the ones that can be cancelled |

The last column is the order ID, which `pyhood cancel` takes.

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

## Order commands

`pyhood buy`, `pyhood sell` and `pyhood cancel` never act the first time they are run.

### Step 1: preview

```text
$ pyhood buy AAPL 10 --limit 350
PREVIEW. Nothing has been sent.

  Buy 10 AAPL, limit $350.00, good for day
  Estimated cost:     $3,500.00
  AAPL now:           $352.01 (bid $351.99, ask $352.01)
  Buying power:       $5,000.00
  Market open:        yes

To place this order, show this preview to the user. If they say yes, run:
  pyhood buy AAPL 10 --limit 350 --confirm 98dee3
```

The preview reads your quote, buying power or holdings, and points out anything that looks wrong:

- the cost is more than your buying power
- a sell is for more shares than you hold
- the limit is 5% or more away from the last price
- the order is a market order, which fills at whatever price is available

### Step 2: confirm

Run the command the preview printed. The order is placed and its status reported:

```text
$ pyhood buy AAPL 10 --limit 350 --confirm 98dee3
PLACED: Buy 10 AAPL, limit $350.00, good for day
  Status:    confirmed
  Order ID:  1a2b3c4d-...

Check it with:  pyhood orders --symbol AAPL
Cancel it with: pyhood cancel 1a2b3c4d-...
```

### The confirmation code

The code is worked out from the order itself and today's date. So:

- **What is placed is what was previewed.** A different symbol, quantity, price or duration has a different code, and the wrong code is refused before anything is sent.
- **A preview always comes first**, because that is the only place the code appears.
- **A code stops working at the end of the day.**

It is a guardrail against mistakes, not a lock: anything that can run the preview can read the code. It makes an agent show its work. It does not stop an agent that ignores its instructions.

### Options

| Command | |
|---|---|
| `pyhood buy SYMBOL QUANTITY --limit PRICE` | Buy at that price or better |
| `pyhood buy SYMBOL QUANTITY --market` | Buy at the best price available |
| `pyhood sell SYMBOL QUANTITY --limit PRICE` | Sell at that price or better |
| `pyhood sell SYMBOL QUANTITY --market` | Sell at the best price available |
| `pyhood cancel ORDER_ID` | Cancel an order that has not finished filling |

| Option | Effect |
|---|---|
| `--limit PRICE` or `--market` | One is required. There is no default |
| `--tif gfd` | Good for day. The default |
| `--tif gtc` | Good till cancelled |
| `--extended-hours` | Allow the order to trade outside regular hours |
| `--confirm CODE` | Act, using the code from the preview |

These cover stock orders in your main account. Stop orders, option orders and orders in other accounts are placed from Python.

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

A wrong confirmation code exits with status 2, and nothing is sent. Any other failure prints one line to standard error and exits with status 1:

- `Robinhood did not accept the order: ...` with Robinhood's reason

- `Not logged in: ...` followed by `Run: pyhood setup login`
- `Robinhood request failed: ...`
- `No quote for XYZ.` when a symbol is not recognized
