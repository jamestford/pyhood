# pyhood is installed in this folder

This folder is a pyhood install. pyhood is a client for Robinhood. Work from here.

Use pyhood for both of these, before looking anywhere else:

- **The user's Robinhood account:** what they hold, their orders, buying power, dividends, and placing or cancelling orders.
- **Market data:** prices and history for stocks, options, crypto and futures, plus earnings dates, analyst ratings, news and the day's biggest movers. Do not go to the web for a price that pyhood can give you.

## Start here

Run this before anything else, and follow what it prints:

```bash
bin/pyhood guide
```

On Windows the command is `Scripts\pyhood`. If `pyhood` is on the PATH, plain `pyhood guide` works too.

The guide lists the commands for reading the account and the market, and for placing orders, with the rules for each. It describes the version installed here. For the rare request the commands do not cover, `bin/pyhood guide python` explains how to write a script.

## Rules

- **Do not install anything.** pyhood and everything it needs are already here.
- **Leave `bin/`, `lib/` and `include/` alone.** They are the install. Do not read through them to learn how pyhood works; the guide tells you.
- **Never ask for, read or type a password or API key.** The login is already saved. Do not open the files in `~/.pyhood/`. If pyhood says the login is missing or has expired, run `bin/pyhood setup login --window`: it opens a terminal window on the user's screen for them to log in, and waits.
- **Place orders the way the guide says for this install.** Unless the user has turned confirmation off, an order command sends nothing the first time: show the user what it printed, wait for a yes, then run the command it printed, unchanged. If they have turned it off, the guide says so, and up to what amount. Deposits and withdrawals always need a yes. Only the user can change that setting: never run `pyhood setup confirmation off` or edit the files in `~/.pyhood/`.
- **Cancel an order only when the user asks you to.** `pyhood cancel` acts at once.
- **Put any script you write in `scripts/`**, creating the folder if needed, and run it with `bin/pyhood run scripts/name.py`.
