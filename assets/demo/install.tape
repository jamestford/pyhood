# Records assets/install.gif — installing pyhood.
#
# Regenerate from the repository root:
#
#     vhs assets/demo/install.tape
#
# Nothing is staged. No PATH is manipulated in the hidden block, so the
# interpreters resolve exactly as they would for a viewer typing these lines —
# `python3` on macOS is the built-in 3.9, which is why the environment is
# created with an explicit `python3.14`. A 3.9 environment cannot install
# pyhood, and pip reports "no matching distribution" rather than a version
# error, so the cause is easy to misread.
#
# The two hidden environment variables are purely cosmetic:
# VIRTUAL_ENV_DISABLE_PROMPT suppresses the shell prompt decoration and
# PIP_PROGRESS_BAR=off stops animated bars from inflating the frame count.
# Neither changes what the commands do or what pip resolves.
#
# The install uses -q, which IS visible on screen. Unfiltered pip output is
# ~25 lines of dependency resolution that scrolls the actual commands away
# and triples the file size. The README documents the command without -q,
# because a real user wants to see what pip is doing.
#
# The GIF is optimised afterwards:
#
#     gifsicle -O3 --lossy=60 -o assets/install.gif assets/install.gif

Output "assets/install.gif"

Set Shell "bash"
Set FontSize 17
Set Width 1180
Set Height 470
Set Padding 25
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Set WindowBar Colorful
Set BorderRadius 9

Hide
Type 'export PS1="$ " VIRTUAL_ENV_DISABLE_PROMPT=1 PIP_PROGRESS_BAR=off'
Enter
Type 'rm -rf /tmp/pyhood-install && mkdir -p /tmp/pyhood-install && cd /tmp/pyhood-install'
Enter
Type "clear"
Enter
Show

Sleep 1.2s
Type "python3.14 -m venv pyhood-env"
Sleep 700ms
Enter
Sleep 3.5s

Type "source pyhood-env/bin/activate"
Sleep 700ms
Enter
Sleep 2s

Type "python -m pip install --upgrade pip"
Sleep 700ms
Enter
Sleep 7s

Type "python -m pip install -q pyhood"
Sleep 700ms
Enter
Sleep 12s

Type "python -c 'import pyhood; print(pyhood.__version__)'"
Sleep 700ms
Enter
Sleep 4s
