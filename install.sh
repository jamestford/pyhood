#!/bin/sh
# Installs pyhood, a Robinhood client for AI agents.
#
#     curl -LsSf https://raw.githubusercontent.com/jamestford/pyhood/main/install.sh | sh
#
# What it does, in order:
#
#   1. Finds uv, the tool pyhood is installed with. If uv is missing, it asks
#      before installing it.
#   2. Creates ~/pyhood and installs pyhood into it. If pyhood is already
#      there, it upgrades it.
#   3. Links the command into ~/.local/bin, so that `pyhood` works anywhere.
#   4. Asks you to log in to Robinhood and authorize pyhood, then reads live
#      prices to check it works.
#
# It never uses sudo. It installs pyhood, and uv only if you say yes. Your
# password goes to Robinhood and is not stored.
#
# Run without a terminal, as an AI agent would, it installs pyhood and leaves
# the authorizing to you. It never asks for a password it cannot ask you for.
#
# The same steps by hand: https://jamestford.github.io/pyhood/getting-started/

set -eu

PYTHON_VERSION=3.14
UV_INSTALLER=https://astral.sh/uv/install.sh
UV_DOCS=https://docs.astral.sh/uv/getting-started/installation/
BY_HAND=https://jamestford.github.io/pyhood/getting-started/

say() {
    printf '%s\n' "$*"
}

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

# A path as a person would type it, with ~ for the home folder.
short() {
    case "$1" in
        "$HOME"/*) printf '~%s\n' "${1#"$HOME"}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

# True when a person can be asked something. Standard input is no guide:
# under `curl ... | sh` it is the script itself.
has_terminal() {
    (exec </dev/tty) 2>/dev/null
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    # uv's own installer puts it here, which a shell opened before the
    # install does not have on its PATH yet.
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$candidate" ]; then
            say "$candidate"
            return 0
        fi
    done
    return 1
}

ensure_uv() {
    if UV=$(find_uv); then
        return 0
    fi
    say "pyhood is installed with uv, a free tool for installing Python programs."
    say "uv is not on this computer."
    if ! has_terminal; then
        fail "Install uv first ($UV_DOCS), then run this again. Nothing was installed."
    fi
    printf 'Install uv now? [y/N] '
    read -r answer </dev/tty || answer=
    case "$answer" in
        y | Y | yes | Yes | YES) ;;
        *) fail "Nothing was installed. To install uv yourself, see $UV_DOCS" ;;
    esac
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf "$UV_INSTALLER" | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$UV_INSTALLER" | sh
    else
        fail "Neither curl nor wget is here to fetch uv with. See $UV_DOCS"
    fi
    UV=$(find_uv) || fail "uv was installed but cannot be found. Open a new terminal and run this again."
}

install_pyhood() {
    if [ -x "$BIN/pyhood" ]; then
        installed=$("$BIN/pyhood" version 2>/dev/null || say "pyhood")
        say "$installed is already installed in $(short "$DIR"). Upgrading it."
        "$UV" pip install --python "$BIN/python" --upgrade "$SPEC"
        return 0
    fi
    if [ -e "$DIR" ] && [ ! -f "$DIR/pyvenv.cfg" ]; then
        if [ ! -d "$DIR" ] || [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
            fail "$(short "$DIR") already exists and is not a pyhood install. Move it aside, then run this again. Nothing was changed."
        fi
    fi
    say "Installing pyhood into $(short "$DIR")."
    if [ ! -f "$DIR/pyvenv.cfg" ]; then
        "$UV" venv --managed-python --python "$PYTHON_VERSION" "$DIR"
    fi
    "$UV" pip install --python "$BIN/python" "$SPEC"
    [ -x "$BIN/pyhood" ] || fail "The install finished but $(short "$BIN/pyhood") is missing. See $BY_HAND"
}

# Sets COMMAND to what the user types to run pyhood.
link_command() {
    COMMAND=$(short "$BIN/pyhood")
    link_dir="$HOME/.local/bin"
    link="$link_dir/pyhood"

    if [ -L "$link" ]; then
        if [ "$(readlink "$link")" != "$BIN/pyhood" ]; then
            say "Left $(short "$link") alone: it links to another pyhood."
            return 0
        fi
    elif [ -e "$link" ]; then
        say "Left $(short "$link") alone: it is a file of its own, not a link."
        return 0
    else
        mkdir -p "$link_dir"
        ln -s "$BIN/pyhood" "$link"
    fi

    case ":$PATH:" in
        *":$link_dir:"*) ;;
        *)
            NOT_ON_PATH=$(short "$link_dir")
            return 0
            ;;
    esac
    if [ "$(command -v pyhood 2>/dev/null || true)" = "$link" ]; then
        COMMAND=pyhood
    else
        say "Another pyhood comes first on your PATH, so this one is run by its full name."
    fi
}

# Sets LOGGED_IN to yes when pyhood was authorized and that was checked.
log_in() {
    LOGGED_IN=no
    if ! has_terminal; then
        # Nobody to ask. An earlier install's authorization may still work.
        if "$BIN/pyhood" verify >/dev/null 2>&1; then
            LOGGED_IN=yes
        fi
        return 0
    fi
    say ""
    if ! "$BIN/pyhood" authorize </dev/tty; then
        say ""
        say "pyhood is installed, but it is not authorized yet. When you are ready:"
        say "    $COMMAND authorize"
        exit 1
    fi
    say ""
    if ! "$BIN/pyhood" verify; then
        say ""
        say "pyhood is installed and authorized, but the check did not pass. Run it again with:"
        say "    $COMMAND verify"
        exit 1
    fi
    LOGGED_IN=yes
}

finish() {
    installed=$("$BIN/pyhood" version 2>/dev/null || say "pyhood")
    say ""
    if [ "$LOGGED_IN" = yes ]; then
        say "$installed is installed in $(short "$DIR"), and it is authorized."
    else
        say "$installed is installed in $(short "$DIR"). It is not authorized yet."
        say ""
        say "If you are an AI agent, open the authorization window on the user's screen:"
        say "    $COMMAND authorize --window"
        say "If you are a person, authorize it yourself, in your own terminal. It asks for"
        say "your Robinhood username and password, then for an approval in the app:"
        say "    $COMMAND authorize"
        say "Then check it, which reads live prices and changes nothing:"
        say "    $COMMAND verify"
    fi
    if [ -n "$NOT_ON_PATH" ]; then
        say ""
        say "To type just \`pyhood\`, add $NOT_ON_PATH to your PATH. Until then, use $COMMAND."
    fi
    say ""
    say "Next, open your AI agent in the pyhood folder and ask it something:"
    say "    cd $(short "$DIR")"
    say "For example: \"What is Tesla trading at?\""
}

main() {
    [ -n "${HOME:-}" ] || fail "HOME is not set, so there is nowhere to install pyhood."
    case "$(uname -s 2>/dev/null || true)" in
        MINGW* | MSYS* | CYGWIN*)
            fail "This script is for macOS and Linux. On Windows, follow the steps at $BY_HAND"
            ;;
    esac

    DIR="$HOME/pyhood"
    BIN="$DIR/bin"
    # What to install. Tests set this to a wheel built from a checkout.
    SPEC="${PYHOOD_INSTALL_SPEC:-pyhood}"
    NOT_ON_PATH=

    ensure_uv
    install_pyhood
    link_command
    log_in
    finish
}

# Everything above only defines functions. Calling main on the last line
# means a download cut off partway runs nothing.
main "$@"
