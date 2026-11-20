"""Data model, errors, and credential-safety helpers for meta-tasks.

A *meta-task* runs a complete workflow written for another workflow engine
(Nextflow, Snakemake, Parsl, StreamFlow, a CWL runner, ...) as one DAGonStar
task.  The engine is an unmodified external program; an adapter translates the
engine-neutral contract defined here into that engine's own command line and
parameter files.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

#: Version of the meta-task specification, checkpoint record, and result document.
SCHEMA_VERSION = 1

#: Names usable as engine parameters (Nextflow ``params.x``, Snakemake
#: ``config["x"]``, Python keyword arguments, CWL input identifiers).
NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Key fragments that mark a value as a credential.  Specifications are
#: persisted (JSON, CWL, checkpoints, FAIR), so secrets must never be declared
#: in them; engines inherit credentials from the parent process environment.
SECRET_FRAGMENTS = ("password", "passwd", "secret", "token", "authorization", "api_key", "apikey",
                    "private_key", "credential", "signed_url", "access_key")

INPUT_KINDS = ("value", "file", "directory")
OUTPUT_KINDS = ("file", "directory")
STAGING_MODES = ("copy", "symlink")


class MetaTaskError(RuntimeError):
    """Base class of every meta-task error; ``phase`` names the failed lifecycle step."""

    phase = "execution"


class MetaValidationError(MetaTaskError, ValueError):
    """The specification is invalid; raised before any side effect."""

    phase = "validation"


class MetaEngineUnavailableError(MetaTaskError):
    """The engine executable or library is not installed on this host."""

    phase = "engine"


class MetaStagingError(MetaTaskError):
    """An input could not be resolved or staged into the task scratch directory."""

    phase = "staging"


class MetaEngineFailedError(MetaTaskError):
    """The external engine ran and returned a non-zero exit status."""

    phase = "execution"

    def __init__(self, message: str, returncode: Optional[int] = None) -> None:
        super().__init__(message)
        self.returncode = returncode


class MetaTimeoutError(MetaEngineFailedError):
    """The external engine exceeded the task timeout and was terminated."""


class MetaOutputError(MetaTaskError):
    """A declared output is missing or escapes the task scratch directory."""

    phase = "outputs"


def is_secret_name(name: str) -> bool:
    lowered = str(name).lower()
    if lowered.endswith("_env"):
        # ``token_env = "MY_TOKEN"`` names a variable; it does not hold a value.
        return False
    return any(fragment in lowered for fragment in SECRET_FRAGMENTS)


def reject_secrets(value: Any, label: str) -> None:
    """Raise :class:`MetaValidationError` when *value* declares a credential-like key."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            if is_secret_name(str(key)):
                raise MetaValidationError(
                    "meta-task %s.%s looks like a credential; credentials must come from the parent "
                    "process environment, never from the task specification" % (label, key))
            reject_secrets(child, label + "." + str(key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            reject_secrets(child, label)


def json_copy(value: Any, label: str) -> Any:
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise MetaValidationError("meta-task %s must be JSON-serializable" % label) from exc


def safe_relative(value: Any, label: str) -> str:
    """Return *value* as a POSIX relative path that cannot leave its base directory."""
    if not isinstance(value, str) or not value:
        raise MetaValidationError("meta-task %s must be a non-empty relative path" % label)
    item = Path(value.replace("\\", "/"))
    if item.is_absolute() or value.startswith(("/", "\\")) or ".." in item.parts or re.match(r"^[A-Za-z]:", value):
        raise MetaValidationError("meta-task %s must be relative and stay inside scratch: %s" % (label, value))
    return item.as_posix()


def inside(root: Path, candidate: Path) -> bool:
    """Return True when *candidate* resolves to *root* or a path below it."""
    root_resolved = Path(os.path.realpath(str(root)))
    resolved = Path(os.path.realpath(str(candidate)))
    return resolved == root_resolved or root_resolved in resolved.parents


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    """Digest of a directory: sorted relative POSIX paths and file contents.

    Symbolic links are followed; metadata such as modification time is not
    part of the identity, so a byte-identical tree has the same digest.
    """
    digest = hashlib.sha256()
    for item in sorted(p for p in Path(path).rglob("*") if p.is_file()):
        relative = item.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8") + b"\0" + sha256_file(item).encode("ascii") + b"\n")
    return digest.hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_tree(path) if Path(path).is_dir() else sha256_file(path)


@dataclass(frozen=True)
class EngineCapabilities:
    """What an adapter can do; the task validates the specification against it."""

    #: ``workflow`` may name something that is not a local path (for example a
    #: Nextflow pipeline ``owner/repository`` resolved by the engine itself).
    remote_workflows: bool = False
    #: Directory inputs can be passed to the engine.
    directory_inputs: bool = True
    #: The engine reports named outputs, so outputs may use ``engine_output``.
    named_outputs: bool = False
    #: Format of the engine-native parameter document written by the adapter.
    parameter_format: str = "json"


@dataclass
class MetaInput:
    """One resolved input binding, as the adapter sees it."""

    name: str
    kind: str
    value: Any
    reference: Optional[str] = None
    sha256: Optional[str] = None

    @property
    def path(self) -> Optional[str]:
        return self.value if self.kind in ("file", "directory") else None


@dataclass
class MetaRunContext:
    """Everything an adapter needs to prepare one engine invocation.

    ``workdir`` is the task scratch directory, ``run_dir`` the engine working
    directory below it, and ``metadata_dir`` the ``.dagon`` directory where
    adapters write their engine-native parameter files.  ``parameters`` maps
    every input name to the value the engine receives: absolute local paths for
    file and directory inputs, JSON values otherwise.
    """

    engine: str
    workflow: str
    workdir: Path
    run_dir: Path
    metadata_dir: Path
    inputs: List[MetaInput]
    outputs: Dict[str, Dict[str, Any]]
    engine_options: Dict[str, Any]
    environment: Dict[str, str]
    timeout: Optional[float]
    python: str
    emulated: bool = False

    @property
    def parameters(self) -> Dict[str, Any]:
        return {item.name: item.value for item in self.inputs}

    def write_json(self, name: str, document: Any) -> Path:
        """Write *document* to ``.dagon/<name>`` atomically and return its path."""
        target = self.metadata_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(str(temporary), str(target))
        return target

    def option(self, name: str, default: Any = None) -> Any:
        return self.engine_options.get(name, default)

    def arguments(self) -> List[str]:
        """Return the validated extra ``arguments`` engine option."""
        extra = self.engine_options.get("arguments", [])
        if not isinstance(extra, list) or not all(isinstance(item, str) for item in extra):
            raise MetaValidationError("meta-task engine option 'arguments' must be a list of strings")
        return list(extra)


@dataclass
class EngineInvocation:
    """An engine command prepared by an adapter: an argument vector, never a shell string."""

    argv: List[str]
    cwd: Path
    environment: Dict[str, str] = field(default_factory=dict)
    #: Files written by the adapter (relative to ``workdir``), recorded as provenance.
    generated_files: List[str] = field(default_factory=list)


@dataclass
class EngineResult:
    """What happened when the engine ran."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    #: Output name -> local path reported by the engine itself (CWL runners).
    reported_outputs: Dict[str, str] = field(default_factory=dict)
    #: Sanitized engine-specific facts (run name, session id, ...).
    metadata: Dict[str, Any] = field(default_factory=dict)
