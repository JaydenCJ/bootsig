"""Exception hierarchy for bootsig.

Everything bootsig raises on purpose derives from :class:`BootsigError`, so
the CLI can turn any expected failure into a single readable stderr line and
exit code 2 — never a raw traceback. The subclasses exist so callers (and
tests) can distinguish "your file is broken" from "your flags are wrong"
from "these two runs cannot be aligned".
"""

from __future__ import annotations


class BootsigError(Exception):
    """Base class for every error bootsig raises deliberately."""


class UsageError(BootsigError):
    """A parameter or flag combination is invalid (alpha out of range, ...)."""


class DataError(BootsigError):
    """A run file could not be parsed into a usable metric series.

    Carries the offending ``path`` and, when known, the 1-based ``line``
    number, and prefixes both onto the message so the CLI needs no extra
    formatting logic.
    """

    def __init__(self, message: str, *, path: "str | None" = None, line: "int | None" = None):
        prefix = ""
        if path is not None:
            prefix = f"{path}: " if line is None else f"{path}:{line}: "
        super().__init__(prefix + message)
        self.path = path
        self.line = line


class PairingError(BootsigError):
    """Two runs could not be aligned example-by-example for a paired test."""
