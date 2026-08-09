"""Entry point for `python -m pyhood`.

See :mod:`pyhood.onboarding` for the commands.
"""

import sys

from pyhood.onboarding import main

if __name__ == "__main__":
    sys.exit(main())
