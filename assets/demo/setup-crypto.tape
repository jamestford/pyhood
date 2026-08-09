# Records assets/setup-crypto.gif — Crypto API keys, then verifying them.
#
# Regenerate from the repository root:
#
#     PYHOOD_VENV=/path/to/venv vhs assets/demo/setup-crypto.tape
#
# Requires vhs (brew install vhs), a virtualenv with pyhood installed, and
# registered crypto credentials for the verification half.
#
# The first half runs against a throwaway HOME: the key pair is generated for
# real and discarded, and the API key typed in is fabricated. Because that key
# is never registered with Robinhood, --no-verify skips the live check — the
# flag and the HOME switch are both stated on screen rather than hidden.
#
# verify_crypto.py is read-only and prints no account number: status, fee
# tier, quotes, pair counts and a holdings count. Keep it that way.

Output "assets/setup-crypto.gif"

Set Shell "bash"
Set FontSize 17
Set Width 1180
Set Height 480
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
Type 'export HOME=/tmp/pyhood-crypto-demo'
Enter
Type 'rm -rf /tmp/pyhood-crypto-demo && mkdir -p /tmp/pyhood-crypto-demo'
Enter
Type "clear"
Enter
Show

# ── Generate and store a key pair ────────────────────────────────────
Sleep 1.2s
Type "# --no-verify: this demo key is never registered with Robinhood"
Sleep 500ms
Enter
Sleep 1s
Type "pyhood setup crypto --no-verify"
Sleep 700ms
Enter
Sleep 5s

# Read with getpass, so nothing appears as it is typed.
Type "rh-api-0f3c8e21-demo-key-not-a-real-credential"
Sleep 2s
Enter
Sleep 5s

Hide
Type 'export HOME="$REAL_HOME"'
Enter
Type "clear"
Enter
Show

# ── Verify registered credentials ────────────────────────────────────
Sleep 1s
Type "# with registered keys, this confirms they work:"
Sleep 500ms
Enter
Sleep 1s
Type "python examples/verify_crypto.py"
Sleep 700ms
Enter
Sleep 7s
