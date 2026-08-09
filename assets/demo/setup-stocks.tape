# Records assets/setup-stocks.gif — session credentials, then verifying them.
#
# Regenerate from the repository root:
#
#     PYHOOD_VENV=/path/to/venv vhs assets/demo/setup-stocks.tape
#
# Requires vhs (brew install vhs), a virtualenv with pyhood installed, and a
# stored session for the verification half.
#
# The first half runs against a throwaway HOME, so the login prompts are real
# but no credential is entered — the recording stops at the password prompt,
# which is where device approval would take over. HOME is then restored for
# the verification half. Both transitions are stated on screen rather than
# hidden, and verify_stocks.py reads only public market data.

Output "assets/setup-stocks.gif"

Set Shell "bash"
Set FontSize 17
Set Width 1180
Set Height 560
Set Padding 25
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set WindowBar Colorful
Set BorderRadius 9

Hide
Type 'export PS1="$ " REAL_HOME="$HOME"'
Enter
Type 'export PATH="$PYHOOD_VENV/bin:$PATH"'
Enter
Type 'export HOME=/tmp/pyhood-demo'
Enter
Type 'rm -rf /tmp/pyhood-demo && mkdir -p /tmp/pyhood-demo'
Enter
Type "clear"
Enter
Show

# ── Log in ───────────────────────────────────────────────────────────
Sleep 1.2s
Type "# this recording stops at the password prompt; nothing is entered"
Sleep 500ms
Enter
Sleep 1s
Type "pyhood setup login"
Sleep 700ms
Enter
Sleep 5.5s

Type "you@example.com"
Sleep 1.5s
Enter
Sleep 3.5s

# Ctrl-C at the password prompt: the real flow continues to device approval.
Ctrl+C
Sleep 4.5s

Hide
Type 'export HOME="$REAL_HOME"'
Enter
Type "clear"
Enter
Show

# ── Verify it works ──────────────────────────────────────────────────
Sleep 1s
Type "# with a session stored, this confirms it works:"
Sleep 500ms
Enter
Sleep 1s
Type "python examples/verify_stocks.py"
Sleep 700ms
Enter
Sleep 7s
