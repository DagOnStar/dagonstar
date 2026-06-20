"""Helpers for safer shell command construction."""

import shlex
from typing import Iterable


def quote(value: object) -> str:
    """Return a POSIX-shell-safe representation of *value*."""
    return shlex.quote(str(value))


def join_command(parts: Iterable[object]) -> str:
    """Join command parts into a POSIX-shell-safe command string."""
    return " ".join(quote(part) for part in parts)


def remote_target(username: object, host: object, path_expression: str) -> str:
    """Build a safe SCP remote target while preserving a shell path expression.

    ``path_expression`` is deliberately kept unquoted because callers use a
    controlled shell variable (for example ``\"$file\"``) that must expand when
    the generated launcher runs.  The user and host portion is quoted as one
    literal shell fragment, so it cannot add SCP options or shell syntax.
    """
    return quote("{}@{}:".format(username, host)) + path_expression
