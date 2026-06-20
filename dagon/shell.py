"""Helpers for safer shell command construction."""

import shlex
from typing import Iterable


def quote(value: object) -> str:
    """Return a POSIX-shell-safe representation of *value*."""
    return shlex.quote(str(value))


def join_command(parts: Iterable[object]) -> str:
    """Join command parts into a POSIX-shell-safe command string."""
    return " ".join(quote(part) for part in parts)
