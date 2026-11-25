# Command Line

The `pyhood` command answers the most common questions about an account without any code, and sets up and checks your login.

The account commands are **read-only**. The order commands change your account. Placing an order takes two steps, unless you have turned confirmation off: a first step that shows the order and sends nothing, then a second that places it. Cancelling one takes a single step.

## Account commands

### `pyhood accounts`

The accounts under your login, such as an individual account and an IRA, with what each is worth.

```text
ACCOUNT     NUMBER      VALUE       CASH  BUYING POWER
Individual  …2223   $7,785.45    $168.85       $168.85
Roth IRA    …5556   $7,000.00  $7,000.00     $7,000.00
```

Account numbers show only their last four characters. `--json` gives them in full.

### `--account`

`positions`, `orders` and `buying-power` cover every account under your login. Add `--account` to see one. An order uses the first account unless it names another the same way. Name an account by part of its type, such as `roth`, `ira` or `individual`, or by the last four characters of its number.

```bash
pyhood positions --account roth
pyhood buy AAPL 10 --limit 350 --account roth
```

It works on `positions`, `orders`, `buying-power`, `buy`, `sell`, `buy-option` and `sell-option`. If what you type fits no account, or more than one, the command stops and lists your accounts. It does not guess.

### `pyhood positions`

What you hold: stocks, then options, with cost, value and unrealized profit or loss.

```text
STOCKS
SYMBOL  SHARES  AVG COST    PRICE      VALUE  UNREALIZED P/L   P/L %
AAPL        10   $340.00  $352.01  $3,520.10        +$120.10  +3.53%
TOTAL                              $3,520.10        +$120.10
```

With more than one account, such as an individual account and an IRA, each is listed under its own heading:

```text
Individual (…2223)

STOCKS
SYMBOL  SHARES  AVG COST    PRICE      VALUE  UNREALIZED P/L   P/L %
AAPL        10   $340.00  $352.01  $3,520.10        +$120.10  +3.53%
TOTAL                              $3,520.10        +$120.10

Roth IRA (…5556)

No open positions.
```

A stock held in two accounts shows as two positions, because each is sold from its own account. `--account roth` shows one account. With `--json`, `stocks` and `options` are the first account's and `accounts` lists them all.

Option prices are per share; one contract is 100 shares.

### `pyhood orders`

Stock and option orders in every account, newest first. With more than one account, an ACCOUNT column says which each order is in.

```text
Orders since 2026-10-25 (times are EST; today is 2026-11-24)
PLACED                SIDE  SYMBOL  TYPE   ORDERED    LIMIT     STOP  FILLED  AVG PRICE  STATUS
2026-11-19 12:36 EST  buy   AAPL    stock       10  $350.00        -      10    $349.80  filled
2026-11-19 11:31 EST  buy   AAPL    stock       10  $340.00        -       0          -  cancelled
2026-11-18 10:02 EST  sell  AAPL    stock       10        -  $330.00       0          -  cancelled
```

| Option | Effect |
|---|---|
| *(none)* | Orders from the last 30 days |
| `--since YYYY-MM-DD` | Orders placed on or after that date |
| `--all` | Every order on record |
| `--symbol AAPL` | Orders for one symbol only |
| `--open` | Only orders that can still fill, which are the ones that can be cancelled |
| `--account roth` | One account's orders only |

The last column is the order ID, which `pyhood cancel` takes.

An option order reads as a trade in a contract: `buy to open` under `SIDE`, and the contract, such as `$12.00 call 2026-12-11`, under `TYPE`. A spread shows as `2-leg option`.

`ORDERED` is what was asked for and `FILLED` is what actually traded. They differ on a partial fill, such as an IPO Access allocation. An order that never filled shows `0` and `-`.

### `pyhood buying-power`

The cash available to trade with. With one account it is one line. With more than one, such as an individual account and an IRA, each account has its own row:

```text
ACCOUNT     NUMBER  BUYING POWER
Individual  …2223        $168.85
Roth IRA    …5556      $7,000.00
```

The figures are not added up, because an account spends only its own cash: money in an IRA cannot pay for an order in another account. `--account roth` shows one account. With `--json`, `buying_power` is the first account's and `accounts` lists them all.

### `pyhood quote SYMBOL [SYMBOL ...]`

Price, change, previous close, bid and ask for each symbol. Add `--fundamentals` for volume, P/E, market cap and the 52-week range, at the cost of one more request.

### `pyhood dividends`

Dividends paid and pending, newest first, with the total paid. `--symbol KO` shows one stock's.

### `pyhood transfers`

Money moved in, out and between your accounts, newest first. It cannot make a transfer.

```text
CREATED     AMOUNT     WHAT              FROM                       TO                  STATE      TRANSFER ID
2026-11-24  $100.00    deposit           Savings …1234 (Rainy day)  Individual account  pending    1a2b3c4d-...
2026-03-23  $7,000.00  IRA Contribution  Individual account         Roth IRA            completed  5e6f7a8b-...
```

A transfer with a bank is a `deposit` or a `withdrawal`, and the bank is named by its type, last four digits and nickname. The ID is what `pyhood cancel-transfer` takes, which works while a bank transfer is still pending. `--json` gives Robinhood's own record of each transfer.

## Market commands

### `pyhood history SYMBOL`

Past prices: open, high, low, close and volume, with the change over the period. `--span` takes `week`, `month` (the default), `3month`, `year` or `5year`. The first three give one row a day, the last two one a week.

### `pyhood earnings SYMBOL [SYMBOL ...]`

When each company next reports, whether before the open or after the close, and the estimate. `--days N` sets how far ahead to look; the default is 90.

### `pyhood ratings SYMBOL [SYMBOL ...]`

Analysts' buy, hold and sell counts, and their low, mean and high price targets.

### `pyhood news SYMBOL`

Recent headlines with their source, time and link. `--count N` sets how many; the default is 5.

### `pyhood movers`

The S&P 500 stocks that have risen most today, with price and change. `--down` shows the biggest falls.

## Watchlists

```bash
pyhood watchlists              # your lists and what is on them
pyhood watch F GM              # add to 'My First List'
pyhood watch NVDA --list Tech  # add to another list
pyhood unwatch F               # take off
```

`watch` and `unwatch` act at once. No money is involved, so there is nothing to confirm. Each reads the list back afterwards and tells you if a symbol did not take.

## Options

### `pyhood documents`

Statements, trade confirmations and tax forms, newest first.

```text
DATE        TYPE               DOCUMENT ID
2026-10-31  account_statement  1a2b3c4d-...
2026-02-10  1099               5e6f7a8b-...
```

`--type` narrows by any part of a type's name, such as `statement`, `confirm`, `1099` or `5498`. `--year 2026` narrows by year.

### `pyhood document DOCUMENT_ID`

Saves one document as a PDF, named for its date and type, such as `2026-10-31_account_statement.pdf`. It goes into a `documents` folder where you are, or wherever `--to FOLDER` says.

A statement shows your account details, so the folder and the file are readable only by you. Nothing in your account changes.

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

## Crypto

Crypto goes through Robinhood's official Crypto Trading API, which has its own credentials. Set them up once with `pyhood setup crypto`. A coin can be written `BTC` or `BTC-USD`.

```bash
pyhood crypto quote BTC ETH    # best bid and ask
pyhood crypto holdings         # the coins you hold, and crypto buying power
pyhood crypto orders           # crypto orders, newest first; --open for open ones
```

### Buying and selling

`pyhood crypto buy` and `pyhood crypto sell` work in the same two steps as stock orders. The quantity is in the coin, not in dollars.

```text
$ pyhood crypto buy BTC 0.001 --limit 50000
NOT PLACED. This order needs your confirmation.

  Buy 0.001 BTC, limit $50,000.00
  Estimated cost:     $50.57 ($50.00 plus a fee of about $0.57)
  BTC now:            $60,000.00 to buy
  Buying power:       $500.00

  Note: The limit is 16.7% below the current price of $60,000.00.

  Note: A crypto limit order stays open until it fills or you cancel it.

To place this order, show this to the user. If they say yes, run:
  pyhood crypto buy BTC 0.001 --limit 50000 --confirm 4c1f0e
```

The first step differs from a stock order's in three ways:

- **It shows Robinhood's fee**, as part of what a buy costs and taken off what a sale brings in. The fee comes from Robinhood's own estimate for that order.
- **It checks the coin can be traded through the API.** Some coins trade in the app but not here, and those are refused.
- **It points out an order under Robinhood's minimum**, which is a dollar value, about ten cents.

`pyhood crypto cancel ORDER_ID` cancels an open crypto order at once.

## Futures

Futures can be read, and an order estimated, but not placed. Name a product, such as `ES` for the E-mini S&P 500, `NQ` for the Nasdaq, `CL` for crude oil or `GC` for gold, and pyhood uses its nearest contract. You do not have to know which month is current.

```bash
pyhood futures quote ES NQ      # last, bid, ask, and the session's high, low and volume
pyhood futures contract ES      # the product's contracts and when each expires
pyhood futures contract ESZ26   # one contract: what a point and a tick are worth
pyhood futures orders           # orders, with realized profit and loss
pyhood futures positions        # open positions
```

```text
$ pyhood futures quote ES
ES: the nearest contract is ESZ26, expiring 2026-12-18.
SYMBOL      LAST  CHANGE      BID       ASK   HIGH       LOW  PREV CLOSE  VOLUME
ESZ26   7,206.75  -0.15%  7,206.5  7,206.75  7,224  7,205.75     7,217.5   4,172
```

A contract can also be named in full, by product, month and year: `ESZ26` is `ES` for December 2026.

`pyhood futures positions` prints what Robinhood sends without arranging it into columns. pyhood has not seen an open futures position, and does not guess at field names.

### Estimating a futures order

```text
$ pyhood futures buy MES 1 --limit 5000
ESTIMATE ONLY. pyhood cannot place futures orders. Nothing has been sent.

  MES: the nearest contract is MESZ26, expiring 2026-12-18.
  Buy 1 MESZ26 contract, limit 5,000, good for day
  Contract:             Micro E-mini S&P 500 Stock Price Index Futures, Dec-26, expires 2026-12-18
  Position size:        $25,000.00 (1 x $5.00 a point x 5,000)
  MESZ26 now:           7,179.5 (bid 7,179.25, ask 7,179.5)
  Margin required:      $2,863.30
  Fees:                 $0.86, including $0.50 commission
  Buying power effect:  -$2,864.16
  Buying power after:   -$2,809.95
  Robinhood says:       it would refuse this order: not enough buying power.

This is an estimate only, and there is no step that places it. To place this order, use the Robinhood app or Robinhood Legend.
```

| Option | Effect |
|---|---|
| `--limit PRICE` | A limit order, with the price in the contract's points |
| `--market` | A market order |
| `--stop PRICE --market` | A stop order: it waits for the price, then trades at market |
| `--tif gtc` | Good till cancelled. The default is good for day |
| `--json` | The check as Robinhood reported it |

The margin, the fees and the verdict are Robinhood's own. They come from the two requests its order ticket makes before it lets you submit an order, and neither places anything. Position size is worked out by pyhood: contracts, times dollars per point, times the price.

There is no `--confirm`, because there is nothing to confirm. pyhood has not seen the request that submits a futures order, so it does not send one. Robinhood offers limit, market and stop orders on futures, and no stop with a limit.

## Order commands

Out of the box, `pyhood buy` and `pyhood sell` never act the first time they are run. You can change that: see [Turning confirmation off](#turning-confirmation-off).

### Step 1: see the order

```text
$ pyhood buy AAPL 10 --limit 350
NOT PLACED. This order needs your confirmation.

  Buy 10 AAPL, limit $350.00, good for day
  Estimated cost:     $3,500.00
  AAPL now:           $352.01 (bid $351.99, ask $352.01)
  Buying power:       $5,000.00
  Market open:        yes

To place this order, show this to the user. If they say yes, run:
  pyhood buy AAPL 10 --limit 350 --confirm 98dee3
```

This step reads your quote, buying power or holdings, and points out anything that looks wrong:

- the cost is more than your buying power
- a sell is for more shares than you hold
- the limit is 5% or more away from the last price
- the order is a market order, which fills at whatever price is available

### Step 2: confirm

Run the command the first step printed. The order is placed and its status reported:

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

- **What is placed is what was shown.** A different symbol, quantity, price or duration has a different code, and the wrong code is refused before anything is sent.
- **The order is always shown first**, because that is the only place the code appears.
- **A code stops working at the end of the day.**

It is a guardrail against mistakes, not a lock: anything that can run the first step can read the code. It makes an agent show its work. It does not stop an agent that ignores its instructions.

### Turning confirmation off

If you would rather your agent placed orders without asking, turn confirmation off. Run this yourself, in your own terminal:

```text
$ pyhood setup confirmation off
Turning confirmation off means:
  - An order worth up to $5,000.00 is sent to Robinhood as soon as your
    agent runs it. You are not shown it first and are not asked.
  ...
Type yes to turn confirmation off: yes

Confirmation is off. Orders up to $5,000.00 are placed at once.
```

After that an order is placed on the first run:

```text
$ pyhood buy AAPL 10 --limit 350
Confirmation is off and this order is not above $5,000.00, so it is sent at once.

  Buy 10 AAPL, limit $350.00, good for day
  Estimated cost:     $3,500.00
  AAPL now:           $352.01 (bid $351.99, ask $352.01)
  Buying power:       $5,000.00
  Market open:        yes

PLACED: Buy 10 AAPL, limit $350.00, good for day
  Status:    queued
  Order ID:  ...
```

| Command | What it does |
|---|---|
| `pyhood setup confirmation` | Shows the setting |
| `pyhood setup confirmation off` | Orders are placed at once, except above your amount |
| `pyhood setup confirmation above 500` | Sets the amount. An order worth more still asks |
| `pyhood setup confirmation on` | Every order asks first. This is how pyhood starts |

How it behaves:

- **The amount is a backstop.** It starts at $5,000. An order worth more is not refused: it takes the usual two steps, and says why.
- **It measures what the order is worth**: the estimated cost or proceeds the first step shows. Selling counts the same as buying. An option order counts its whole cost, 100 shares a contract.
- **Each order is judged on its own.** Several orders under the amount all go through. It catches a mistake, such as 100 shares for 10. It is not a spending limit.
- **An order whose worth cannot be worked out asks.**
- **`--ask` makes one order ask**, whatever the setting.
- **Bank transfers always ask.** Cancelling never does.
- **Warnings are still printed**, above the line that says the order was placed. By then it has been sent.
- **The agent is told.** `pyhood guide` describes whichever way this install is set, with the amount.

Turning confirmation off, or changing the amount, needs a person at the terminal. Run by an agent, the command changes nothing and tells the agent to ask you. Turning it back on works from anywhere. The setting is kept in `~/.pyhood/settings.json`; an agent that can run commands could edit that file by hand, so this too is a guardrail and not a lock.

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
| `--stop PRICE` | Make it a stop order. See below |
| `--trail-percent PERCENT` or `--trail-amount DOLLARS` | Make it a trailing stop. See below |
| `--account WHICH` | Place it in another account, such as `roth` |
| `--tif gfd` | Good for day. The default |
| `--tif gtc` | Good till cancelled |
| `--extended-hours` | Allow the order to trade outside regular hours |
| `--confirm CODE` | Place the order, using the code the first step printed |
| `--ask` | Ask first for this order, even with confirmation off |

### Orders by dollar amount

`--dollars AMOUNT` in place of a number of shares buys or sells that much money's worth, which is usually a fraction of a share.

```bash
pyhood buy AAPL --dollars 50 --market
```

It is always a market order, in regular hours, of at least $1: Robinhood takes a fraction of a share no other way. The first step shows roughly how many shares the amount comes to.

A buy by dollar amount has been placed for real, with the market closed so that it could be cancelled before it traded. A sell by dollar amount has not.

### Stop orders

`--stop PRICE` makes an order wait. Nothing happens until the stock reaches the stop price; then the `--market` or `--limit` order is placed.

```bash
pyhood sell AAPL 10 --stop 340 --market --tif gtc   # sell if it falls to $340
pyhood sell AAPL 10 --stop 340 --limit 338 --tif gtc   # ... but not below $338
```

The first step points out two things that catch people:

- **A stop that would trigger at once.** A sell stop belongs below the current price and a buy stop above it.
- **A stop that lasts only for today.** Orders are good for the day by default, and a stop meant as protection is no use once it has expired. Add `--tif gtc`.

### Trailing stops

`--trail-percent PERCENT` or `--trail-amount DOLLARS` makes a stop that follows the price, staying that far behind its best level.

```bash
pyhood sell AAPL 10 --trail-percent 5 --market --tif gtc
```

The first step shows where the stop starts. It is always a market order for a number of shares.

A trailing stop that sells has been placed for real. One that buys has not yet, and the first step says so. If Robinhood refuses an order, nothing is placed and the reason is printed.

### Option orders

`pyhood buy-option` and `pyhood sell-option` work in the same two steps. Every term of the contract is named, and none has a default:

```text
$ pyhood buy-option F --expires 2026-12-11 --strike 12 --call --contracts 1 --limit 0.30
NOT PLACED. This order needs your confirmation.

  Buy to open 1 contract of F $12.00 call expiring 2026-12-11, limit $0.30 per share, good for day
  Estimated cost:     $30.00 (1 contract x 100 shares x $0.30)
  Contract now:       mark $0.31 (bid $0.28, ask $0.33)
  F now:              $11.95
  Delta, IV:          +0.500, 31.4%
  Expires:            2026-12-11 (17 days)
  Buying power:       $500.00
  Market open:        yes

To place this order, show this to the user. If they say yes, run:
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

The first step checks that the contract exists and names the nearest expirations or strikes if it does not. It also points out:

- a cost of more than your buying power
- a sell to close of more contracts than you hold
- a sell to open, which writes a contract and takes on its obligation
- a limit 20% or more from the contract's mark, which catches a price typed per contract in place of per share
- a contract that expires today

### Spreads

`pyhood spread` places two to four option contracts as one order, for one net price.

```text
$ pyhood spread F --expires 2026-12-11 --leg buy:call:12 --leg sell:call:13 --contracts 1 --debit 0.25
NOT PLACED. This order needs your confirmation.

  Open 1 F spread for a debit of $0.25 per share, good for day
    buy  $12.00 call 2026-12-11   mark $0.31 (bid $0.29, ask $0.33)
    sell $13.00 call 2026-12-11   mark $0.04 (bid $0.02, ask $0.06)
  Estimated cost:     $25.00 (1 spread x 100 shares x $0.25)
  Spread now:         about $0.27 debit at the marks, $0.31 debit to trade at once
  F now:              $11.95
```

| Option | Effect |
|---|---|
| `--expires YYYY-MM-DD` | The expiration of every leg that does not name its own. Required |
| `--leg SIDE:TYPE:STRIKE` | One contract: `buy:call:350`, `sell:put:340`. Give it two to four times. Add `:YYYY-MM-DD` for a leg with its own expiration |
| `--contracts N` | How many spreads. Required |
| `--debit PRICE` or `--credit PRICE` | The most to pay, or the least to accept, per share. One is required |
| `--to open` or `--to close` | Opening is the default |
| `--tif`, `--account` | As for other orders |

The first step checks that every leg is a real contract, and prices the spread from its legs. It points out:

- **legs the wrong way round.** If you ask for a debit but the legs as written pay a credit, the bought and sold legs are probably swapped.
- **a price 20% or more from what the spread is worth** at the marks.

pyhood has not placed a spread against Robinhood. The order is built the way other clients build it and is covered by tests, but start with one contract.

### Cancelling an order

```text
$ pyhood cancel 1a2b3c4d-...
CANCELLED: buy 10 AAPL, limit $350.00, placed 2026-11-24 16:54 EST

$ pyhood cancel 5e6f7a8b-...
CANCELLED: buy to open 1 F $12.00 call 2026-12-11, limit $0.30 per share, placed 2026-11-24 17:17 EST
```

`pyhood cancel ORDER_ID` acts at once, for stock and option orders alike. There is no first step and no code. A cancel names one order and can only remove it, so there is no symbol, quantity or price to get wrong, and when you want out of an order a second step is time in which it can fill.

- Find the ID with `pyhood orders --open`.
- An order that has already finished is left alone, and the command says so.
- A cancel is a request. If the order filled before it landed, the command reports that in place of `CANCELLED`, and any part that had already filled is not undone.

These cover stock orders by shares or by dollar amount, stop orders and trailing stops, single-leg option orders and spreads, in any of your accounts, and crypto orders. Futures orders cannot be placed, from the command line or from Python. They can be estimated: see [Estimating a futures order](#estimating-a-futures-order).

## Moving money

`pyhood deposit` and `pyhood withdraw` move money between a linked bank account and Robinhood. They always take two steps, whatever your confirmation setting.

```text
$ pyhood withdraw 500
NOT SENT. This transfer needs your confirmation.

  Withdraw $500.00 from Robinhood to Savings …1234 (Rainy day)
  Withdrawable cash:  $1,250.00

  Note: A bank transfer takes a few business days to arrive.

To make this transfer, show this to the user. If they say yes, run:
  pyhood withdraw 500 --confirm 98fafd
```

- **The code is tied to the direction, the amount and the bank.** A code for $50 will not move $500, and a code for a withdrawal will not make a deposit.
- **`pyhood banks`** lists your linked banks by nickname, type and last four digits. With one bank linked there is nothing to choose. With more, add `--bank` and part of a nickname, a type, or the last four digits.
- **A withdrawal of more than your withdrawable cash is pointed out.** Money from a recent sale or deposit takes time to become withdrawable.
- **`pyhood cancel-transfer TRANSFER_ID`** cancels a transfer that has not gone through, at once. The ID is printed when the transfer is made.

pyhood has not made a transfer against Robinhood through these commands. The first step has been run live; the step that sends has only been tested against a stand-in.

## Setup and checks

| Command | What it does |
|---|---|
| `pyhood setup` | Reports what is configured. See [Setup](setup.md) |
| `pyhood authorize` | Asks you to log in, and saves the key Robinhood hands back. `pyhood setup login` is an older name for it |
| `pyhood authorize --window` | For an AI agent: opens a terminal window for the user to log in, and waits. See [Setup](setup.md#authorizing-from-an-ai-agent) |
| `pyhood setup crypto` | Generates and registers a Crypto API key pair |
| `pyhood setup confirmation` | Shows or changes whether orders ask first. See [Turning confirmation off](#turning-confirmation-off) |
| `pyhood verify` | Reads live prices to confirm the saved login works |
| `pyhood verify crypto` | The same for the Crypto API key pair |
| `pyhood version` | Prints the installed version |

## Scripts and agents

| Command | What it does |
|---|---|
| `pyhood run script.py` | Runs a script with the Python pyhood is installed in, so `import pyhood` works however pyhood was installed. `pyhood run -c "..."` works too |
| `pyhood guide` | Prints how to use pyhood, written for an AI agent: these commands and the rules for placing orders. Short enough to be read whole |
| `pyhood guide python` | The reference for writing a script: how to log in, the main methods, and the fields of what they return |

## When a command fails

A wrong confirmation code exits with status 2, and nothing is sent. Any other failure prints one line to standard error and exits with status 1:

- `Robinhood did not accept the order: ...` with Robinhood's reason

- `pyhood is not authorized: ...` followed by `Run: pyhood authorize`
- `Robinhood request failed: ...`
- `No quote for XYZ.` when a symbol is not recognized
