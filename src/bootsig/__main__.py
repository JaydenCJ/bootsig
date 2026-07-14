"""Allow ``python -m bootsig`` to behave exactly like the ``bootsig`` script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
