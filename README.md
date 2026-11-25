# pyhood

<div align="center">
<img src="https://raw.githubusercontent.com/jamestford/pyhood/main/assets/logo-tight.png" alt="pyhood logo" width="200">

**Let your AI agent work your Robinhood account, with a preview before every order.**
</div>

[![CI](https://github.com/jamestford/pyhood/actions/workflows/ci.yml/badge.svg)](https://github.com/jamestford/pyhood/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyhood.svg)](https://pypi.org/project/pyhood/)
[![Docs](https://img.shields.io/badge/docs-jamestford.github.io%2Fpyhood-blue)](https://jamestford.github.io/pyhood)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/jamestford/pyhood/blob/main/LICENSE)
[![Security](https://github.com/jamestford/pyhood/actions/workflows/security.yml/badge.svg)](https://github.com/jamestford/pyhood/actions/workflows/security.yml)

pyhood lets an AI agent read your Robinhood account and place orders for you. You ask in plain language. The agent runs pyhood. Before anything is sent to Robinhood, you see exactly what it will be and say yes or no.

It works with any agent that can run commands on your computer.

> pyhood is an unofficial client and is not affiliated with Robinhood. Use responsibly. This project is not financial advice.

## What you can ask

Once it is set up, talk to your agent the way you would to a person:

| You say | What happens |
|---|---|
| "What do I own, and how is it doing?" | It lists your positions with cost, value and profit or loss |
| "What did I buy this month?" | It lists your orders, with what filled and at what price |
| "How much can I spend?" | It reads your buying power |
| "What's in my Roth IRA?" | It shows that account's positions |
| "When does Apple report earnings, and what do analysts think?" | It gives the date, the ratings and the price targets |
| "Show me AAPL calls expiring next month" | It shows the contracts near the stock's price, with bid, ask and delta |
| "Buy 10 shares of AAPL at $350 or better" | It shows you a preview and waits for your yes |
| "Buy one of those $350 calls for $2.50" | It shows you a preview and waits for your yes |
| "Sell my AAPL if it drops to $340" | It previews a stop order and waits for your yes |
| "Sell my AAPL if it falls 10% from its high" | It previews a trailing stop and waits for your yes |
| "Put $50 into Apple" | It previews a $50 order and waits for your yes |
| "Move $500 to my bank" | It previews the withdrawal and waits for your yes |
| "Buy $50 of bitcoin... how much is that?" then "buy 0.0008 BTC" | It previews the order with Robinhood's fee and waits for your yes |
| "Cancel that order" | It cancels it and tells you what happened |
| "Save my latest statement" | It saves the PDF into a folder only you can read |

## Get started

There are three steps. Your agent does the first, you do the second.

### 1. Ask your agent to install it

Paste this into your agent:

```text
Install pyhood for me. Follow the install steps in https://raw.githubusercontent.com/jamestford/pyhood/main/AGENTS.md
```

That file is written for AI agents. It tells yours to put pyhood in a folder of its own, `~/pyhood`, to stop and hand you the login, and not to install anything else.

<details>
<summary><strong>What the file tells your agent to do</strong></summary>

1. If `~/pyhood/bin/pyhood` already exists, say so and skip the install.
2. Check that [uv](https://docs.astral.sh/uv/getting-started/installation/) is installed, and stop to ask you if it is not.
3. Run `uv venv --managed-python --python 3.14 ~/pyhood`
4. Run `uv pip install --python ~/pyhood/bin/python pyhood`
5. Run `~/pyhood/bin/pyhood version` to check it.
6. Ask you to log in yourself. It must never ask for your password or type it.
7. Run `~/pyhood/bin/pyhood verify`, which reads live prices and changes nothing.
8. Read `~/pyhood/AGENTS.md`, the instructions that came with the install.

It is also told not to use `pip`, `sudo` or `--break-system-packages`, and not to install anything but pyhood. You can [read the file](https://github.com/jamestford/pyhood/blob/main/AGENTS.md) yourself, or follow the same steps [by hand](https://jamestford.github.io/pyhood/getting-started/).

</details>

The install creates one folder, `~/pyhood`, with pyhood in it. uv is a free tool for installing Python programs (`brew install uv` on macOS). It also downloads a copy of Python for pyhood to run on, which it keeps in its own folder. Nothing is installed system-wide, and your other Python setups are not touched.

### 2. Log in yourself

Your agent will stop and ask you to run this in your own terminal:

```bash
~/pyhood/bin/pyhood setup login
```

It asks for your Robinhood username and password, then waits for you to approve the login in the Robinhood app on your phone. Your password is not stored and your agent never sees it. What is saved is a session, in `~/.pyhood/session.json`, readable only by you. pyhood renews that session on its own, so you should rarely need to log in again.

Then tell your agent you are logged in.

### 3. Open your agent in the pyhood folder

From now on, start your agent in `~/pyhood`:

```bash
cd ~/pyhood
```

The install put a file called `AGENTS.md` in that folder. Many agents read a file of that name when they start, and this one tells them how to use pyhood. There is nothing else to configure.

If your agent reads a different file, such as `CLAUDE.md`, or you want to work from another folder, put this one line in the file it does read:

```text
pyhood is installed at ~/pyhood. Run `~/pyhood/bin/pyhood guide` before using it.
```

## What an order looks like

```text
You:    buy 1 share of F with a limit price of $5

Agent:  Here is the preview:

          Buy 1 F, limit $5.00, good for day
          Estimated cost:  $5.00
          F now:           $11.95 (bid $11.92, ask $11.95)
          Buying power:    $500.00

        Your limit is 58% below the current price, so this is unlikely
        to fill. Want me to place it?

You:    yes

Agent:  Placed. Buy 1 F at a $5.00 limit, status: queued.

You:    cancel that order

Agent:  Cancelled: buy 1 F, limit $5.00.
```

The agent did not work that preview out for itself. pyhood produced it, from your live account, and the agent passed it on.

## How you stay in control

**Every order and every transfer is previewed first.** When the agent asks pyhood to buy or sell, pyhood sends nothing. It replies with what the order would be, what it would cost, the current price, and anything that looks wrong: a cost above your buying power, a sale of more than you hold, or a price far from the market.

**An order can only be placed with a code from its preview.** The preview ends with a short code. The order goes through only when the agent repeats the same request with that code. The code belongs to that exact order: change the stock, the amount or the price, and it stops working. So what gets placed is what you were shown.

**Nothing is assumed.** An order needs a price, or an explicit instruction to buy at the market. Options need every term spelled out. Orders last for the day unless you say otherwise.

**You log in, not the agent.** The agent never needs your password.

**Cancelling is immediate.** When you say cancel, it cancels. Getting out of an order should not take two steps.

### What this does not protect against

These are guardrails against mistakes. They are not a lock.

- **An agent that ignores its instructions can still place an order.** The code makes it produce a preview first. It does not force the agent to show you the preview or to wait for your answer. That part depends on the agent following the instructions pyhood gives it.
- **Your saved login is a file on your computer.** An agent that can run commands can read it. In testing, a model that had been given no instructions printed that file to look at it.

So give this only to an agent you would trust with the account, and start with small orders.

## What it covers

| | From your agent or the command line | From Python |
|---|---|---|
| Positions, orders, buying power, quotes | Yes | Yes |
| IRA and other accounts | Yes | Yes |
| Price history, earnings dates, analyst ratings, news, movers | Yes | Yes |
| Dividends, transfer history, statements and tax forms | Yes | Yes |
| Watchlists | Yes | Yes |
| Option expirations and contracts | Yes | Yes |
| Buy and sell stock, including stop orders and trailing stops | Yes, with a preview | Yes |
| Buy and sell single options | Yes, with a preview | Yes |
| Cancel an order | Yes | Yes |
| Orders by dollar amount, and option spreads | Yes, with a preview | Yes |
| Crypto prices, holdings, and buying and selling | Yes, with a preview | Yes |
| Futures quotes, contracts, orders and profit and loss | Yes | Yes |
| Preview a futures order: margin, fees and whether Robinhood would accept it | Yes | Yes |
| Deposits and withdrawals to a linked bank | Yes, with a preview | Yes |

Everything here is a command, so the agent rarely needs to write code. For something no command covers, such as a calculation across several results, it writes a short script, and `pyhood guide python` tells it how.

**Futures can be read and previewed, but not traded.** `pyhood futures buy` and `sell` show the margin an order ties up, its fees, and whether Robinhood would accept it, all as Robinhood reports them. They cannot place the order: pyhood has not seen the request that submits one, and will not guess at it with your money.

**What has been run against Robinhood for real.** Tests that pass against made-up responses are not proof, and three of the orders below were refused by Robinhood the first time they were sent, with every test passing. So here is what has actually been placed, by a local model, with a real account:

| Placed for real, then cancelled | Not placed yet |
|---|---|
| Buy and sell stock at a limit | Any order in an IRA |
| Buy stock at market, and by dollar amount | Selling an option |
| Stop orders, at market and with a limit | A trailing stop that buys |
| A trailing stop that sells | Selling crypto, and crypto at market |
| Buy an option to open | A withdrawal, and cancelling a transfer |
| An option spread | |
| Buy crypto at a limit | |
| A deposit from a bank | |

Every read command has been run for real too, and so has saving a statement. The orders on the right go through the same code as those on the left, but until one has been sent, treat its first use as a test: start small, and far from the market price.

**What it has been tested with:** a local model, Qwen3.6 35B, running in the [Pi](https://github.com/earendil-works/pi) agent. Given the one-line install request above and nothing else, it fetched the instructions and installed pyhood with no errors. Asked to buy, it previewed and waited.

## Using it without an agent

Everything the agent does, you can do yourself. To type `pyhood` instead of `~/pyhood/bin/pyhood`, link it into a folder on your PATH:

```bash
ln -s ~/pyhood/bin/pyhood ~/.local/bin/pyhood
```

```bash
pyhood positions             # what you hold, with profit and loss
pyhood orders                # orders from the last 30 days
pyhood buying-power          # cash available to trade with
pyhood quote AAPL MSFT       # current prices
pyhood options AAPL          # option expiration dates
pyhood earnings AAPL         # next earnings date
pyhood buy AAPL 10 --limit 350    # preview; add the code it prints to place it
pyhood cancel ORDER_ID       # cancel an open order
```

Add `--json` to any of the first six for exact values, and `--account roth` to work in another account. The [command line page](https://jamestford.github.io/pyhood/cli/) covers every command and option.

To upgrade pyhood later:

```bash
uv pip install --python ~/pyhood/bin/python --upgrade pyhood
```

## For developers

pyhood is also a typed Python library, and the command line is a thin layer over it.

```python
import pyhood
from pyhood.client import PyhoodClient

client = PyhoodClient(pyhood.login())  # uses the saved session; no credentials in code

quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")

for position in client.get_positions():
    print(position.symbol, position.quantity, position.unrealized_pl)
```

Save that as `script.py` and run it with `pyhood run script.py`, which uses the Python pyhood is installed in. To add pyhood to a project that has its own environment, `pip install pyhood` there. It needs Python 3.10 or newer.

What sets it apart from other Robinhood libraries:

- **It stays logged in.** After the first approved login, pyhood renews the session with a refresh token: no password, no approval prompt, nobody at the keyboard. Unattended scripts do not die when a session expires.
- **Typed results.** Methods return dataclasses, not raw dictionaries. A value Robinhood does not send is `None`, never a made-up `0`. A wrong field name raises an error that lists the right ones.
- **Checked against the live API.** The tests mock Robinhood, so a script in the repository also runs every parser against a real account and reports any field Robinhood does not send. That audit has found and fixed more than a dozen fields that were silently empty.
- **Session stored as JSON, owner-only,** not as a pickle.

Against [robin_stocks](https://github.com/jmfernandes/robin_stocks) and its maintained fork [robin_stocks_v2](https://github.com/DhruvaBansal00/robin_stocks_v2):

| Capability | pyhood | robin_stocks | robin_stocks_v2 |
|---|---:|---:|---:|
| Command line an AI agent can drive, with order previews | Yes | No | No |
| Silent session refresh without credentials | Yes | No | No |
| JSON session storage | Yes | No, uses pickle | Yes |
| IRA / retirement accounts | Yes | No | No |
| Official Crypto Trading API | Yes | No | No |
| Futures contracts and quotes | Yes | No | Yes |
| Futures positions | Yes | No | Stubbed |
| IPO access | Yes | No | Yes |
| Typed dataclass responses | Yes | No | Partial |
| Index options: SPX, NDX, VIX, RUT, XSP | Yes | Partial | Yes |
| Minimum Python version | 3.10 | 3.9 | 3.10 |

Moving from another library? There are function-by-function guides for [robin_stocks](https://github.com/jamestford/pyhood/blob/main/docs/migrating-from-robin-stocks.md) and [pyrh](https://github.com/jamestford/pyhood/blob/main/docs/migrating-from-pyrh.md).

## Documentation

- [Getting started](https://jamestford.github.io/pyhood/getting-started/): installing by hand, with uv or pip
- [Command line](https://jamestford.github.io/pyhood/cli/): every command and option
- [Setup](https://jamestford.github.io/pyhood/setup/): logging in, and the key pair for crypto
- [Authentication](https://jamestford.github.io/pyhood/authentication/): how sessions are kept alive, and what the errors mean
- [Options](https://jamestford.github.io/pyhood/options/), [crypto](https://jamestford.github.io/pyhood/crypto/), [futures](https://jamestford.github.io/pyhood/futures/) and [accounts](https://jamestford.github.io/pyhood/account/), including IRAs
- [Rate limits](https://jamestford.github.io/pyhood/rate-limits/)
- [Changelog](https://github.com/jamestford/pyhood/blob/main/CHANGELOG.md)

## Contributing

Contributions are welcome, especially reports of how pyhood behaves with different agents and models, endpoint coverage, and tests for behaviour verified against the live API.

Please do not open pull requests whose tests place real trades.

## Acknowledgments

pyhood stands on the work of the community that mapped Robinhood's unofficial API:

- [robin_stocks](https://github.com/jmfernandes/robin_stocks) by [Josh Fernandes](https://github.com/jmfernandes), the most widely used Python Robinhood library.
- [pyrh](https://github.com/robinhood-unofficial/pyrh), an early client that helped establish OAuth token refresh patterns.
- [Robinhood](https://github.com/sanko/Robinhood) by [Sanko](https://github.com/sanko), early unofficial endpoint documentation.

## License

MIT
