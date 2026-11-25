# Instructions for AI agents

## If you were asked to install pyhood

Do these steps in order. If one fails, stop and tell the user what happened. Do not improvise around a failure.

1. **Check whether it is already installed.** If `~/pyhood/bin/pyhood` exists, run `~/pyhood/bin/pyhood version`, tell the user pyhood is already installed, and go to step 6.
2. **Check for uv.** Run `uv --version`. If uv is not installed, stop and ask the user to install it: https://docs.astral.sh/uv/getting-started/installation/ (`brew install uv` on macOS). Do not install it yourself without asking.
3. **Create the install folder.** Run `uv venv --managed-python --python 3.14 ~/pyhood`
4. **Install pyhood into it.** Run `uv pip install --python ~/pyhood/bin/python pyhood`
5. **Check it.** Run `~/pyhood/bin/pyhood version`. It should print a version number.
6. **Hand the login to the user.** Run `~/pyhood/bin/pyhood setup`. If it shows a saved session, go to step 7. If not, tell the user to run `~/pyhood/bin/pyhood setup login` themselves, in their own terminal, and to tell you when they have. Do not run it for them. Never ask for, read or type their password.
7. **Confirm the login works.** Run `~/pyhood/bin/pyhood verify`. It reads live prices and changes nothing.
8. **Read the instructions that came with the install.** Read `~/pyhood/AGENTS.md` and follow it from now on. Tell the user to start you in the `~/pyhood` folder next time, so that you read that file automatically.

Rules for the install:

- Do not use `pip`, `sudo` or `--break-system-packages`.
- Do not install anything other than pyhood, and do not install pyhood anywhere but `~/pyhood`.
- Do not run pyhood from a copy of this repository.

On Windows the commands are in `~\pyhood\Scripts\` rather than `~/pyhood/bin/`.

## If you want to use pyhood

Do not run pyhood from a copy of this repository. This is its source code, not an install. It has no dependencies installed, and importing it from here fails.

1. Check whether pyhood is installed: `~/pyhood/bin/pyhood version`, or `pyhood version` if it is on the PATH.
2. If it is, run `~/pyhood/bin/pyhood guide` and follow it. It covers the commands, running scripts, logging in, and the rules for placing orders.
3. If it is not, ask the user whether to install it, then follow the steps above.

Never ask for, read or type a password or API key. Place orders the way `pyhood guide` says for that install: unless the user has turned confirmation off, show them exactly what will be sent first and get a yes. Never turn confirmation off yourself. Cancel an order only when the user asks you to.

## If you are changing pyhood

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" responses
pytest
ruff check .
```

- **Build test mocks from real responses, not from the fields the parser reads.** Parsers here have shipped reading field names Robinhood never sends, with tests that mocked the same made-up names and passed. `python scripts/field_audit.py` checks the parsers against a live account; it makes GET requests only and prints field names, never values.
- **`None` means unknown.** Do not turn a missing or null value into `0` or `""`.
- **No credentials, account numbers or order IDs** in code, tests or docs. Use placeholders.
- **The README is also the PyPI page**, so every link in it must be absolute.
- **`pyhood guide` is generated from the code.** When you add a method an agent should know about, add its name to `pyhood/guide.py`.
- Add an entry to `CHANGELOG.md` under `[Unreleased]`.

### When the change is done

`main` is protected, so every change lands through a pull request. Once `pytest` and `ruff check .` pass, do these steps without asking first:

1. **Branch.** `fix/short-name` for a fix, `feat/short-name` for a feature.
2. **Commit.** Use a conventional subject, such as `fix: show orders in every account`, and a short body that says what was wrong and what changes. Add no `Co-Authored-By` line.
3. **Push and open the pull request.** Give it the same title as the commit. In the body, say what was wrong, what changes, and how it was checked. If it was not checked against a real account, say so.

Stop there. Do not merge the pull request, and do not release, unless the user asks.

A release is its own pull request, from a `release/X.Y.Z` branch, titled `chore: release X.Y.Z`. It sets the version in `pyhood/__init__.py` and `pyproject.toml` and dates the `[Unreleased]` section of the changelog.
