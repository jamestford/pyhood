# Demo recordings

**Not currently used.** The README embedded three terminal recordings for a while and they were removed — they did not read well on the page. The tapes are kept because regenerating a recording is one command, so bringing them back later costs nothing.

They are recorded with [VHS](https://github.com/charmbracelet/vhs) from the tapes here, so they can be regenerated when output changes rather than being re-shot by hand.

```bash
brew install vhs
vhs assets/demo/install.tape
PYHOOD_VENV=/path/to/venv vhs assets/demo/setup-stocks.tape
PYHOOD_VENV=/path/to/venv vhs assets/demo/setup-crypto.tape
```

Run them from the repository root — the tapes write to `assets/` relative to the working directory.

| Tape | Output | Needs |
|---|---|---|
| `install.tape` | `assets/install.gif` | Nothing. Builds a fresh environment in `/tmp` and installs from PyPI. |
| `setup-stocks.tape` | `assets/setup-stocks.gif` | A stored session (`pyhood setup login`) for the verification half. |
| `setup-crypto.tape` | `assets/setup-crypto.gif` | Registered crypto credentials (`pyhood setup crypto`) for the verification half. |

## What is real, and what is not

Everything on screen is genuine command output. Nothing is retyped or edited in post. Two things are staged, and both are stated on screen in the recording rather than hidden:

- **The credentials in the setup halves are fabricated.** `HOME` is redirected to a throwaway directory, so no real credential, key or home path appears. The crypto key pair is generated for real and discarded.
- **`HOME` is restored for the verification halves**, which run against real credentials. The visible comment line (`# with a session stored…`) marks the transition.

`setup-stocks.tape` stops at the password prompt with Ctrl-C, because the rest of a first login is device approval in the mobile app and cannot be scripted. `setup-crypto.tape` passes `--no-verify` because the key it generates is never registered with Robinhood; without that flag, `setup crypto` makes a signed call to confirm the pair works.

## Keep it that way

Both verification scripts are restricted to data that is safe to publish — quotes, an options chain, market hours, fee tier, pair counts, a holdings count. No positions, balances or account numbers. This repository has published real account numbers once already; if you extend the examples, do not widen what the recordings show.

`install.tape` adds `-q` to the install — visibly, on screen. Unfiltered pip output is roughly 25 lines of dependency resolution that scrolls the commands away and multiplies the file size; the README documents the command without `-q`, because a real user wants to see what pip is doing.

## Optimising

VHS output is not optimised. Run gifsicle over anything with a lot of scrolling output:

```bash
gifsicle -O3 --lossy=60 -o assets/install.gif assets/install.gif
```

That took the install recording from 964 KB to 119 KB with no visible loss on terminal text.
