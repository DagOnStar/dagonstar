"""Recursive, immutable handling of structured ``workflow://`` references."""
import copy
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Tuple


_REFERENCE = re.compile(r"workflow://[^\s\"'\],}]+")


@dataclass(frozen=True)
class ReferenceOccurrence:
    path: Tuple[Any, ...]
    raw: str


def walk_workflow_references(value: Any, path: Tuple[Any, ...] = ()) -> Iterable[ReferenceOccurrence]:
    if isinstance(value, str):
        for match in _REFERENCE.finditer(value):
            yield ReferenceOccurrence(path, match.group(0).rstrip(".;:|)&"))
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from walk_workflow_references(child, path + (key,))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from walk_workflow_references(child, path + (index,))


def references(value: Any) -> Iterable[str]:
    for occurrence in walk_workflow_references(value):
        yield occurrence.raw


def replace_references(value: Any, resolver: Callable[[str], str]) -> Any:
    """Return a deep replacement; the logical task specification is never mutated."""
    if isinstance(value, str):
        return _REFERENCE.sub(lambda match: resolver(match.group(0).rstrip(".;:|)&")) +
                              match.group(0)[len(match.group(0).rstrip(".;:|)&")):], value)
    if isinstance(value, dict):
        return {key: replace_references(child, resolver) for key, child in value.items()}
    if isinstance(value, list):
        return [replace_references(child, resolver) for child in value]
    if isinstance(value, tuple):
        return [replace_references(child, resolver) for child in value]
    return copy.deepcopy(value)
