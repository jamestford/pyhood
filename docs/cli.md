# Command Line

The `pyhood` command answers the most common questions about an account without any code, and sets up and checks your login.

The account commands are **read-only**. The order commands change your account. Placing an order takes two steps: a preview, then a confirmation. Cancelling one takes a single step.

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

An option order reads as a trade in a contract: `buy to open` under `SIDE`, and the contract, such as `$12.00 call 2026-12-11`, under `TYPE`. A spread shows as `2-leg option`.

`ORDERED` is what was asked for and `FILLED` is what actually traded. They differ on a partial fill, such as an IPO Access allocation. An order that never filled shows `0` and `-`.

### `pyhood buying-power`

The cash available to trade with in the main account.

### `pyhood quote SYMBOL [SYMBOL ...]`

Price, change, previous close, bid and ask for each symbol. Add `--fundamentals` for volume, P/E, market cap and the 52-week range, at the cost of one more request.

### `pyhood options SYMBOL`

With only a symbol, the expiration dates of its options. With `--expires`, the contracts for that date nearest the stock's price:

```text
$ pyhood options F --expires 2026-12-11 --strikes 4
F is at $11.95. Options expiring 2026-12-11 (17 days).
Prices are per share. One contract is 100 shares, so $2.50 costs $250.

CALLS, the 4 strikes nearest the price
STRIKE    BID    ASK   MARK   DELTA     IV  VOLUME  OPEN INT
$11.00  $0.89  $1.12  $1.01  +0.901  31.3%     117       209
$11.50  $0.60  $0.66  $0.63  +0.721  34.1%     253     1,558
$12.00  $0.28  $0.33  $0.31  +0.500  31.4%     560     3,547
$12.50  $0.11  $0.14  $0.13  +0.272  31.3%   1,171     1,467
```

| Option | Effect |
|---|---|
| `--expires YYYY-MM-DD` | Show the contracts for that expiration |
| `--call` or `--put` | Show one side only |
| `--strikes N` | How many strikes nearest the price to show. The default is 10 |

Delta and IV print as `-` when Robinhood publishes none, as on a contract's expiration day.

### `--json`

Each account command takes `--json` to print exact values in place of the table:

```bash
pyhood orders --symbol AAPL --json
```

Two differences from the tables:

- **Times are UTC**, as Robinhood sends them, in ISO-8601 form. The tables convert them to your computer's time zone.
- **Unknown values are `null`**, where the tables print `-`.

## Order commands

`pyhood buy` and `pyhood sell` never act the first time they are run.

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

| Option | Effect |
|---|---|
| `--limit PRICE` or `--market` | One is required. There is no default |
| `--tif gfd` | Good for day. The default |
| `--tif gtc` | Good till cancelled |
| `--extended-hours` | Allow the order to trade outside regular hours |
| `--confirm CODE` | Act, using the code from the preview |

### Option orders

`pyhood buy-option` and `pyhood sell-option` work in the same two steps. Every term of the contract is named, and none has a default:

```text
$ pyhood buy-option F --expires 2026-12-11 --strike 12 --call --contracts 1 --limit 0.30
PREVIEW. Nothing has been sent.

  Buy to open 1 contract of F $12.00 call expiring 2026-12-11, limit $0.30 per share, good for day
  Estimated cost:     $30.00 (1 contract x 100 shares x $0.30)
  Contract now:       mark $0.31 (bid $0.28, ask $0.33)
  F now:              $11.95
  Delta, IV:          +0.500, 31.4%
  Expires:            2026-12-11 (17 days)
  Buying power:       $500.00
  Market open:        yes

To place this order, show this preview to the user. If they say yes, run:
  pyhood buy-option F --expires 2026-12-11 --strike 12 --call --contracts 1 --limit 0.3 --confirm fdf2a6
```

| Option | Effect |
|---|---|
| `--expires YYYY-MM-DD` | The contract's expiration. Required |
| `--strike PRICE` | The contract's strike. Required |
| `--call` or `--put` | Required |
| `--contracts N` | How many contracts, each 100 shares. Required |
| `--limit PRICE` | Per share, as option prices are quoted: `2.50` is $250 a contract. Required; there are no market orders for options |
| `--to open` or `--to close` | Whether the order opens a position or closes one. A buy opens and a sell closes unless you say otherwise |
| `--tif gfd` or `--tif gtc` | Good for day (the default) or good till cancelled |

The preview checks that the contract exists and names the nearest expirations or strikes if it does not. It also points out:

- a cost of more than your buying power
- a sell to close of more contracts than you hold
- a sell to open, which writes a contract and takes on its obligation
- a limit 20% or more from the contract's mark, which catches a price typed per contract in place of per share
- a contract that expires today

### Cancelling an order

```text
$ pyhood cancel 1a2b3c4d-...
CANCELLED: buy 10 AAPL, limit $350.00, placed 2026-11-24 16:54 EST

$ pyhood cancel 5e6f7a8b-...
CANCELLED: buy to open 1 F $12.00 call 2026-12-11, limit $0.30 per share, placed 2026-11-24 17:17 EST
```

`pyhood cancel ORDER_ID` acts at once, for stock and option orders alike. There is no preview and no code. A cancel names one order and can only remove it, so there is no symbol, quantity or price to get wrong, and when you want out of an order a second step is time in which it can fill.

- Find the ID with `pyhood orders --open`.
- An order that has already finished is left alone, and the command says so.
- A cancel is a request. If the order filled before it landed, the command reports that in place of `CANCELLED`, and any part that had already filled is not undone.

These cover stock orders and single-leg option orders in your main account. Stop orders, option spreads and orders in other accounts are placed from Python.

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
