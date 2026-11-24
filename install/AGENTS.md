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

The guide lists the commands for reading the account and placing orders, how to run a script, and the rules. It describes the version installed here.

## Rules

- **Do not install anything.** pyhood and everything it needs are already here.
- **Leave `bin/`, `lib/` and `include/` alone.** They are the install. Do not read through them to learn how pyhood works; the guide tells you.
- **Never ask for, read or type a password or API key.** The login is already saved. Do not open the files in `~/.pyhood/`.
- **Never place an order without the user's yes.** `pyhood buy`, `pyhood sell`, `pyhood buy-option` and `pyhood sell-option` preview first. Show the preview, wait for a yes, then run the command the preview printed, unchanged.
- **Cancel an order only when the user asks you to.** `pyhood cancel` acts at once.
- **Put any script you write in `scripts/`**, creating the folder if needed, and run it with `bin/pyhood run scripts/name.py`.
