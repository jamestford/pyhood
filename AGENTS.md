# Instructions for AI agents

## If you were asked to install pyhood

Do these steps in order. If one fails, stop and tell the user what happened. Do not improvise around a failure.

1. **Install it.** Run `curl -LsSf https://raw.githubusercontent.com/jamestford/pyhood/main/install.sh | sh`. It creates the folder `~/pyhood` and installs pyhood into it. If pyhood is already installed there, it upgrades it. If it says uv is missing, stop and ask the user to install uv: https://docs.astral.sh/uv/getting-started/installation/ (`brew install uv` on macOS). Do not install it yourself without asking.
2. **Check it.** Run `~/pyhood/bin/pyhood version`. It should print a version number.
3. **Open the authorization window for the user.** Run `~/pyhood/bin/pyhood authorize --window`, and allow it two minutes. If pyhood is already authorized, it says so and you go to step 4. Otherwise a terminal window titled "pyhood Authorization" opens on the user's screen. Tell the user to type their Robinhood username and password in that window, and to approve the request in the Robinhood app on their phone. The command waits for them.
   - If it says the user has not finished, run it again. It does not open a second window.
   - If it says the authorization did not finish, ask the user what happened before running it again.
   - If it says Robinhood asked for a different check, stop. Tell the user what it said. Do not run it again: Robinhood chose a check that pyhood cannot do, and more attempts will not change that.
   - If it says it could not open a window, tell the user to run `~/pyhood/bin/pyhood authorize` themselves, in their own terminal, and to tell you when they have.
   - Never ask for, read or type their password. Do not run `authorize` without `--window`: it needs a terminal, and you do not have one.
4. **Confirm it works.** Run `~/pyhood/bin/pyhood verify`. It reads live prices and changes nothing.
5. **Read the instructions that came with the install.** Read `~/pyhood/AGENTS.md` and follow it from now on. Tell the user to start you in the `~/pyhood` folder next time, so that you read that file automatically.

If you cannot run the script, these two commands are what it runs:

```bash
uv venv --managed-python --python 3.14 ~/pyhood
uv pip install --python ~/pyhood/bin/python pyhood
```

Rules for the install:

- Do not use `pip`, `sudo` or `--break-system-packages`.
- Do not install anything other than pyhood, and do not install pyhood anywhere but `~/pyhood`.
- Do not run pyhood from a copy of this repository.

On Windows the script does not run: use the two commands, and the commands are in `~\pyhood\Scripts\` rather than `~/pyhood/bin/`. No window can be opened there, so the user runs `authorize` themselves.

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

`main` is protected, so every change lands through a pull request. Once `pytest` and `ruff check .` pass, do all of these steps without asking first:

1. **Branch.** `fix/short-name` for a fix, `feat/short-name` for a feature.
2. **Commit.** Use a conventional subject, such as `fix: show orders in every account`, and a short body that says what was wrong and what changes. Add no `Co-Authored-By` line.
3. **Push and open the pull request.** Give it the same title as the commit. In the body, say what was wrong, what changes, and how it was checked. If it was not checked against a real account, say so.
4. **Merge.** When every check has passed, squash-merge it. If a check fails, fix the cause. Do not merge around a failing check.
5. **Release.** Every merge is released, as soon as it is merged, however small the change. Nothing waits for a later release.

To release:

1. **Open a release pull request** from a `release/X.Y.Z` branch, titled `chore: release X.Y.Z`. Raise the last number for fixes and the middle one for a feature. Set the version in `pyhood/__init__.py` and `pyproject.toml`, and date the `[Unreleased]` section of the changelog.
2. **Check the wheel.** Build it, install it into a clean environment, and run `pyhood version` there. It should print the new version.
3. **Merge it** when every check has passed.
4. **Publish a GitHub release** tagged `vX.Y.Z` on `main`. Write the notes for a user: what changed and why, with an example of the new output. Publishing the release is what sends the package to PyPI.
5. **Confirm it.** Check that the "Publish to PyPI" run succeeded.

Stop and tell the user if a step fails in a way you cannot fix. Never ask for, read or type a PyPI password or token: publishing runs in GitHub Actions and needs none.
