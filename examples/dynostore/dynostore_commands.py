"""Safe command builders for the external DynoStore command-line client."""

import shlex
from typing import Iterable


SERVER_ENV = "DYNOSTORE_SERVER"


def _quote_args(arguments: Iterable[str]) -> str:
    return " ".join(shlex.quote(str(argument)) for argument in arguments)


def dynostore_command(*arguments: str) -> str:
    """Build a task command without embedding a server address or credential."""
    prefix = (
        'test -n "${DYNOSTORE_SERVER:-}" || '
        '{ echo "DYNOSTORE_SERVER is required" >&2; exit 2; }; '
        'python3 -m dynostore.cli --server "$DYNOSTORE_SERVER"'
    )
    return prefix + " " + _quote_args(arguments)


def upload_catalog(source: str, catalog: str) -> str:
    """Build the DynoStore client command for uploading one named object."""
    return dynostore_command("put", source, "--catalog=" + catalog)


def download_catalog(catalog: str, destination: str) -> str:
    """Build the historical DAGonStore client command for catalog retrieval."""
    return dynostore_command("get_catalog", catalog, destination)
