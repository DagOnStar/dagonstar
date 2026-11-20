"""``TaskType.VOLUME``: create or destroy one ad-hoc file-system volume as a task.

A *create* volume task starts one volume of a registered ad-hoc provider
(:mod:`dagon.adhoc`) when it runs, optionally stages files and directories
into it, and exposes it to the rest of the workflow through the ordinary
``workflow://`` schema.  If the volume task ``Abc`` creates the volume ``xyz``,
then::

    workflow:///Abc/xyz/inputs/data.csv

is the file ``inputs/data.csv`` *inside the volume*.  The reference keeps the
meaning the schema gives every reference - ``<workflow>/<task>/<path>``, where
``<path>`` is relative to the producer task's data space - because the volume
appears in the volume task's scratch directory under its own name.  The
difference is only in how the data reaches a consumer:

* a command task that refers to the volume is bound to it (it receives the
  ``DAGON_ADHOC_*`` environment and, for preload providers, the interception
  library) and its reference is rewritten to the location inside the volume:
  nothing is copied, so every sibling task shares the same data;
* a structured task (native, web, LLM, FaaS, IoT, agentic, meta) reads the
  path through the scratch-directory link, which exists for POSIX volumes and
  in portable emulation; structured tasks cannot read preload, client, or
  object volumes and are refused at dependency discovery.

The volume is released (its provider stopped) when no task refers to it any
longer: reference counting is the scratch-directory garbage collector's
(:meth:`dagon.task.Task.decrement_reference_count`), applied to the volume
whatever the ``remove_dir`` setting.  A *destroy* volume task releases a volume
explicitly after every other task that uses it, and first stages selected files
and directories out of it into its own scratch directory, where later tasks
refer to them with ordinary ``workflow:///<destroy task>/<path>`` references.

Streams (:mod:`dagon.streaming`) between tasks bound to a volume whose provider
supports them (DAGonFS, CAPIO, Hercules, DynoStore, and adapters that declare
``supports_streaming``) use the usual query: ``workflow:///P/frames?stream=xyz``
binds the producer ``P`` and the consumer to the volume ``xyz`` and runs them
concurrently.

Staging into and out of a volume runs in a helper process
(``python -m dagon.volume stage``) that receives the volume's task
environment, so preload providers intercept its file calls exactly as they
intercept a bound task's.  Specifications, checkpoints, JSON, CWL, and FAIR
records are credential-free: provider options whose names look like
credentials are refused, and DynoStore's token is read only by its client from
the variable it names.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import dagon
from dagon.runtime_env import runner_environment
from dagon.shell import quote
from dagon.streaming import iter_command_references, parse_reference
from dagon.task import Task, TaskType

SCHEMA_VERSION = 1
ACTIONS = ("create", "destroy")
RELEASE_MODES = ("auto", "end")
ITEM_KINDS = ("auto", "file", "directory")
_REFERENCE = "workflow://"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SECRET = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|PRIVATE)", re.I)
# Keys whose value is the *name* of a variable holding a credential, never the credential.
_VARIABLE_NAME_KEYS = ("token_env",)
_OBJECT_NAMESPACE = uuid.UUID("0d3c7a52-61f4-5b0e-8f63-1c5a4d2e9b77")


class VolumeError(RuntimeError):
    """A volume task could not be planned, created, staged, or released."""


# -- helpers -----------------------------------------------------------------

def safe_volume_path(value: Any, label: str, allow_empty: bool = False) -> str:
    """A relative ``/``-separated path without ``..`` (shell globs are allowed)."""
    if not isinstance(value, str):
        raise ValueError("volume %s must be a string path: %r" % (label, value))
    text = value.replace("\\", "/")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise ValueError("volume %s must be relative: %r" % (label, value))
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("volume %s must not contain '..': %r" % (label, value))
    if not parts and not allow_empty:
        raise ValueError("volume %s must not be empty" % label)
    return "/".join(parts)


def object_key(volume: str, relative: str) -> str:
    """Deterministic object key of *relative* inside an object-store volume."""
    return str(uuid.uuid5(_OBJECT_NAMESPACE, "%s/%s" % (volume, relative.strip("/"))))


def reject_secret_options(value: Any, label: str = "options") -> None:
    """Refuse provider options that look like credentials (names only, recursively)."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("volume %s keys must be strings" % label)
            if _SECRET.search(key) and key not in _VARIABLE_NAME_KEYS:
                raise ValueError("volume %s %r looks like a credential; credentials come from the "
                                 "environment, never from the task specification" % (label, key))
            reject_secret_options(item, label)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_secret_options(item, label)


def _json_copy(value: Any, label: str) -> Any:
    try:
        return json.loads(json.dumps(value, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ValueError("volume %s must be JSON-serializable: %s" % (label, exc)) from exc


def _sha256_path(path: Path) -> str:
    """SHA-256 of a file, or of a directory tree (relative names and file digests)."""
    digest = hashlib.sha256()
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file():
                digest.update(item.relative_to(path).as_posix().encode("utf-8") + b"\0")
                digest.update(_sha256_path(item).encode("ascii"))
        return digest.hexdigest()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _link(target: str, link: str) -> bool:
    """Create *link* to the directory *target* (symlink, or a junction on Windows)."""
    try:
        if os.path.lexists(link):
            if os.path.islink(link) or os.path.isfile(link):
                os.unlink(link)
            else:
                return False
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        if sys.platform == "win32":  # pragma: no cover - exercised on Windows CI only
            try:
                import _winapi  # type: ignore[import-not-found]
                _winapi.CreateJunction(target, link)
                return True
            except (ImportError, OSError):
                return False
        return False


# -- stores used by the staging helper ----------------------------------------

def _write_all(path: str, data: bytes) -> None:
    with open(path, "wb", buffering=0) as stream:
        view = memoryview(data)
        while view:
            view = view[stream.write(view):]


def _read_all(path: str) -> bytes:
    with open(path, "rb", buffering=0) as stream:
        chunks = []
        while True:
            chunk = stream.read(4 << 20)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


def _local_files(root: str) -> Iterable[Tuple[str, str]]:
    """``(relative, absolute)`` for every file below the local directory *root*."""
    for directory, _, files in os.walk(root):
        for name in sorted(files):
            absolute = os.path.join(directory, name)
            yield os.path.relpath(absolute, root).replace(os.sep, "/"), absolute


class VolumeStore:
    """How the staging helper reads and writes a volume.  Subclasses implement I/O."""

    def put_file(self, local: str, relative: str) -> None:
        raise NotImplementedError

    def put_tree(self, local: str, relative: str) -> None:
        self.mkdir(relative)
        for name, absolute in _local_files(local):
            self.put_file(absolute, (relative + "/" + name).strip("/"))

    def mkdir(self, relative: str) -> None:
        """Create a directory (no-op for stores without directories)."""

    def get(self, relative: str, local: str) -> None:
        """Copy the file or directory *relative* to the local path *local*."""
        raise NotImplementedError


class PosixVolumeStore(VolumeStore):
    """A volume reached with ordinary file calls: a mount, a preloaded prefix, or emulation.

    Directories are created one component at a time and files are written and
    read without ``stat``, because some interposers (DAGonFS preload) do not
    intercept it; a directory is recognised when opening it as a file fails.
    """

    def __init__(self, root: str) -> None:
        self.root = root.rstrip("/") or "/"

    def _path(self, relative: str) -> str:
        return self.root + ("/" + relative if relative else "")

    def mkdir(self, relative: str) -> None:
        current = self.root
        if not os.path.isdir(current):
            os.makedirs(current, exist_ok=True)
        for part in [item for item in relative.split("/") if item]:
            current += "/" + part
            try:
                os.mkdir(current)
            except FileExistsError:
                pass

    def put_file(self, local: str, relative: str) -> None:
        self.mkdir(relative.rpartition("/")[0])
        with open(local, "rb") as stream:
            _write_all(self._path(relative), stream.read())

    def get(self, relative: str, local: str) -> None:
        source = self._path(relative)
        try:
            data = _read_all(source)
        except (IsADirectoryError, PermissionError) as exc:
            if not os.path.isdir(source):
                raise exc
            os.makedirs(local, exist_ok=True)
            for name in sorted(os.listdir(source)):
                self.get((relative + "/" + name).strip("/"), os.path.join(local, name))
            return
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        with open(local, "wb") as stream:
            stream.write(data)


class DagonFSNativeVolumeStore(VolumeStore):
    """A DAGonFS native-socket volume through ``dagonfs.native.Client``.

    Writing uses ``makedirs`` and ``write_bytes``, reading ``read_bytes``.
    Staging a directory *out* needs a listing call; it is used when the client
    offers ``listdir`` and refused otherwise.
    """

    def __init__(self, socket_path: str, python_path: Optional[str] = None) -> None:
        if python_path and python_path not in sys.path:
            sys.path.insert(0, python_path)
        try:
            import importlib
            native = importlib.import_module("dagonfs.native")
        except ImportError as exc:
            raise VolumeError("the DAGonFS native frontend needs DAGonFS's Python client "
                              "(set python_path, exported as DAGONFS_PYTHON)") from exc
        self.client = native.Client(socket_path)

    def mkdir(self, relative: str) -> None:
        if relative:
            self.client.makedirs("/" + relative)

    def put_file(self, local: str, relative: str) -> None:
        self.mkdir(relative.rpartition("/")[0])
        with open(local, "rb") as stream:
            self.client.write_bytes("/" + relative, stream.read())

    def get(self, relative: str, local: str) -> None:
        try:
            data = self.client.read_bytes("/" + relative)
        except (IsADirectoryError, OSError) as exc:
            listdir = getattr(self.client, "listdir", None)
            if listdir is None:
                raise VolumeError("cannot stage the DAGonFS native path /%s out: it is not a readable file "
                                  "and this client has no directory listing" % relative) from exc
            os.makedirs(local, exist_ok=True)
            for name in sorted(listdir("/" + relative)):
                self.get((relative + "/" + name).strip("/"), os.path.join(local, name))
            return
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        with open(local, "wb") as stream:
            stream.write(data)


class ObjectVolumeStore(VolumeStore):
    """An object-store volume (DynoStore): one object per file, keyed by :func:`object_key`.

    A directory staged in also stores a manifest object listing its files, so
    that it can be staged out again.  Objects written by tasks themselves are
    addressed by their keys and are not listed in a manifest.
    """

    def __init__(self, client: Any, volume: str) -> None:
        self.client = client
        self.volume = volume

    def _manifest_key(self, relative: str) -> str:
        return object_key(self.volume, "\0directory/" + relative)

    def put_file(self, local: str, relative: str) -> None:
        with open(local, "rb") as stream:
            self.client.put_bytes(stream.read(), object_key(self.volume, relative))

    def put_tree(self, local: str, relative: str) -> None:
        names = []
        for name, absolute in _local_files(local):
            self.put_file(absolute, (relative + "/" + name).strip("/"))
            names.append(name)
        manifest = json.dumps({"v": 1, "files": names}, sort_keys=True).encode("utf-8")
        self.client.put_bytes(manifest, self._manifest_key(relative))

    def get(self, relative: str, local: str) -> None:
        manifest_key = self._manifest_key(relative)
        if self.client.exists(manifest_key):
            manifest = json.loads(self.client.get_bytes(manifest_key).decode("utf-8"))
            for name in manifest.get("files", []):
                name = safe_volume_path(name, "manifest entry")
                target = os.path.join(local, *name.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as stream:
                    stream.write(self.client.get_bytes(object_key(self.volume, (relative + "/" + name).strip("/"))))
            return
        data = self.client.get_bytes(object_key(self.volume, relative))
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        with open(local, "wb") as stream:
            stream.write(data)


def open_store(spec: Mapping[str, Any]) -> VolumeStore:
    """Open the store of a helper specification through its adapter."""
    access = spec.get("access")
    if access in ("posix", "preload"):
        return PosixVolumeStore(str(spec["location"]))
    module_name, _, qualname = str(spec.get("adapter", "")).partition(":")
    try:
        import importlib
        adapter: Any = importlib.import_module(module_name)
        for part in qualname.split("."):
            adapter = getattr(adapter, part)
    except (ImportError, AttributeError, ValueError) as exc:
        raise VolumeError("volume adapter %s is not importable" % spec.get("adapter")) from exc
    opener = getattr(adapter, "open_volume_store", None)
    if opener is None:
        raise VolumeError("adapter %s cannot stage data with %s access" % (spec.get("adapter"), access))
    return opener(spec)


def run_operations(spec: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Run the ``put``/``get`` operations of *spec*; return a credential-free report."""
    store = open_store(spec)
    report = []
    for operation in spec.get("operations", []):
        kind = operation["op"]
        if kind == "put":
            source = str(operation["source"])
            target = safe_volume_path(operation["target"], "target")
            if os.path.isdir(source):
                store.put_tree(source, target)
                item = "directory"
            elif os.path.isfile(source):
                store.put_file(source, target)
                item = "file"
            else:
                raise VolumeError("stage-in source does not exist: %s" % source)
            report.append({"op": "put", "target": target, "type": item,
                           "sha256": _sha256_path(Path(source))})
        elif kind == "get":
            source = safe_volume_path(operation["source"], "source", allow_empty=True)
            target = str(operation["target"])
            store.get(source, target)
            report.append({"op": "get", "source": source,
                           "type": "directory" if os.path.isdir(target) else "file",
                           "sha256": _sha256_path(Path(target))})
        else:
            raise VolumeError("unknown volume operation %r" % kind)
    return report


# -- references ----------------------------------------------------------------

def volume_reference(workflow: Any, text: str) -> Optional[Tuple["VolumeTask", str]]:
    """``(owner, relative)`` when *text* names a path inside a volume task's volume.

    ``workflow://<workflow>/<owner>/<volume>[/<relative>]`` where ``<owner>`` is
    a *create* volume task of *workflow* and ``<volume>`` its volume name.
    """
    try:
        reference = parse_reference(text, dagon.Workflow.SCHEMA)
    except ValueError:
        return None
    if reference.workflow not in ("", workflow.name):
        return None
    owner = workflow.find_task_by_name(workflow.name, reference.task)
    if not isinstance(owner, VolumeTask) or owner.action != "create":
        return None
    head, _, rest = reference.path.partition("/")
    if head != owner.volume_name:
        return None
    if reference.stream:
        raise ValueError("%s: a stream is produced by a command task, not by volume task %s; write "
                         "workflow:///<producer>/<path>?stream=%s" % (text, owner.name, owner.volume_name))
    return owner, safe_volume_path(rest, "reference path", allow_empty=True)


def _descendants(task: Any) -> set:
    seen, pending = set(), list(task.nexts)
    while pending:
        current = pending.pop()
        if current not in seen:
            seen.add(current)
            pending.extend(current.nexts)
    return seen


def plan_volumes(workflow: Any) -> None:
    """Bind volume users, add volume edges, and check volume references.

    Called by :meth:`dagon.Workflow.make_dependencies` after ``workflow://``
    discovery when the workflow contains a volume task.  It

    * binds every command task that refers to a volume (and both endpoints of a
      ``?stream=<volume>`` reference) to that volume and records the rewrite of
      each reference;
    * makes every such task depend on the creating volume task;
    * counts users that hold no textual reference, so that the volume is
      released only after them;
    * refuses structured readers of volumes they cannot reach;
    * orders a destroy task after every other user of its volume.
    """
    owners = [task for task in workflow.tasks if isinstance(task, VolumeTask) and task.action == "create"]
    by_volume = {owner.volume_name: owner for owner in owners}
    for owner in owners:
        owner.extra_users = set()
    for task in workflow.tasks:
        task.volume_references = {}
    for task in workflow.tasks:
        command = getattr(task, "command", None)
        if isinstance(task, VolumeTask) or not isinstance(command, str) or _REFERENCE not in command:
            continue
        for _, _, text in iter_command_references(command, dagon.Workflow.SCHEMA):
            found = volume_reference(workflow, text)
            if found is not None:
                owner, relative = found
                if not getattr(task, "stream_capable", False):
                    continue  # structured tasks read through the scratch link (checked below)
                owner.filesystem.bind(task)
                task.volume_references[text] = (owner, relative)
                continue
            reference = parse_reference(text, dagon.Workflow.SCHEMA)
            if reference.stream and reference.stream_filesystem in by_volume:
                owner = by_volume[reference.stream_filesystem]
                producer = workflow.find_task_by_name(reference.workflow or workflow.name, reference.task)
                if producer is None:
                    continue  # reported by stream planning
                for endpoint in (producer, task):
                    if isinstance(endpoint, VolumeTask):
                        continue  # reported by stream planning
                    owner.filesystem.bind(endpoint)
                    owner._add_user(endpoint)
    for owner in owners:
        for user in list(owner.attached):
            owner.filesystem.bind(user)
            owner._add_user(user)
    # Structured readers reach a volume only through the scratch link.
    for owner in owners:
        filesystem = owner.filesystem
        reachable = workflow.portable_emulation or filesystem.access == "posix"
        for task in owner.nexts:
            if getattr(task, "stream_capable", True) or isinstance(task, VolumeTask):
                continue
            if owner in task.__dict__.get("explicit_prevs", []):
                continue
            if not reachable:
                raise ValueError("%s task %s cannot read volume %s of %s: its %s access has no POSIX path; use a "
                                 "command task bound to the volume, or stage the data out with a destroy volume task"
                                 % (type(task).__name__, task.name, owner.volume_name, owner.name, filesystem.access))
    # Destroy tasks run after every other user of their volume.
    destroyers: Dict[Any, Any] = {}
    for task in workflow.tasks:
        if not isinstance(task, VolumeTask) or task.action != "destroy":
            continue
        owner = task.resolve_target()
        if owner in destroyers:
            raise ValueError("volume %s is destroyed by both %s and %s" % (owner.volume_name, destroyers[owner].name,
                                                                           task.name))
        destroyers[owner] = task
        owner.filesystem.bind(task)
        later = _descendants(task)
        users = (set(owner.nexts) | set(owner.filesystem.tasks)) - {owner, task}
        for user in sorted(users, key=lambda item: item.name):
            if user in later:
                raise ValueError("task %s uses volume %s but runs after %s, which destroys it"
                                 % (user.name, owner.volume_name, task.name))
            if user not in task.prevs:
                task.add_dependency_to(user)


# -- the task ---------------------------------------------------------------------

class VolumeTask(Task):
    """Create (or destroy) one ad-hoc file-system volume shared through ``workflow://``.

    :param name: task name; with ``action="create"`` it is also the first
        component of every reference to the volume, ``workflow:///<name>/<volume>/...``
    :param provider: registered ad-hoc provider (``dagonfs``, ``hercules``,
        ``capio``, ``dynostore``, or a pluggable adapter) or adapter class;
        create only.  BeeOND volumes exist only inside a Slurm allocation and
        are refused: use ``Workflow.create_adhoc_filesystem("beeond")``
    :param volume: create: the volume name (default: the task name when the
        task is added to a workflow), unique in
        the workflow; destroy: the reference ``workflow:///<create task>/<volume>``
    :param action: ``"create"`` (default) or ``"destroy"``
    :param stage_in: create only: ``{path in the volume: source}``, where the
        source is a ``workflow://`` reference to another task's scratch
        directory or an existing local path, or ``{"path": source, "type":
        "file"|"directory"}``
    :param stage_out: destroy only: ``{path in this task's scratch: source}``,
        where the source is a path in the volume, the reference
        ``workflow:///<create task>/<volume>/<path>``, or a descriptor as above
    :param options: provider options (JSON, credential-free) passed to the
        adapter, for example ``{"frontend": "native", "ranks": 4}``
    :param export: developer-chosen variable carrying the volume path in every
        bound task (see :func:`dagon.adhoc.check_export_name`)
    :param release: ``"auto"`` (default) releases the volume when its last
        reference is gone; ``"end"`` keeps it until a destroy task or the end
        of the workflow
    """

    stream_capable = False
    task_type = TaskType.VOLUME
    is_volume_task = True

    def __init__(self, name: str, provider: Any = None, volume: Optional[str] = None, action: str = "create",
                 stage_in: Optional[Mapping[str, Any]] = None, stage_out: Optional[Mapping[str, Any]] = None,
                 options: Optional[Mapping[str, Any]] = None, export: Optional[str] = None,
                 release: str = "auto", working_dir: Optional[str] = None,
                 transversal_workflow: Optional[str] = None, globusendpoint: Optional[str] = None,
                 **unknown: Any) -> None:
        if unknown:
            raise ValueError("unknown volume-task option(s): %s; provider options go in options={...}"
                             % ", ".join(sorted(unknown)))
        if action not in ACTIONS:
            raise ValueError("volume-task action must be 'create' or 'destroy'")
        if release not in RELEASE_MODES:
            raise ValueError("volume-task release must be 'auto' or 'end'")
        self.action = action
        self.release = release
        self.options = _json_copy(dict(options or {}), "options")
        reject_secret_options(self.options)
        if export is not None:
            from dagon.adhoc import check_export_name
            check_export_name(export)
        self.export = export
        self.provider = provider
        self.stage_in: Dict[str, Dict[str, str]] = {}
        self.stage_out: Dict[str, Dict[str, str]] = {}
        self.target: Optional[str] = None
        if action == "create":
            if stage_out:
                raise ValueError("stage_out belongs to a destroy volume task")
            if provider is None or provider == "":
                raise ValueError("a create volume task needs a provider")
            if self._provider_name(provider) == "beeond":
                raise ValueError("BeeOND volumes exist only inside a Slurm allocation and cannot be created by a "
                                 "volume task; use Workflow.create_adhoc_filesystem('beeond') with Slurm tasks")
            volume_name = volume if volume is not None else re.sub(r"[^A-Za-z0-9._-]", "_", str(name))
            if not isinstance(volume_name, str) or not _NAME.match(volume_name):
                raise ValueError("volume names may contain letters, digits, '.', '_' and '-'")
            self.volume_name = volume_name
            # Without an explicit name the volume is named after the task when it joins a workflow.
            self._volume_from_name = volume is None
            for target, source in (stage_in or {}).items():
                self.stage_in[safe_volume_path(target, "stage_in path")] = self._descriptor(source, "stage_in")
            references = [item["path"] for item in self.stage_in.values() if item["path"].startswith(_REFERENCE)]
            command = "dagon-volume create %s" % self.volume_name
        else:
            if stage_in:
                raise ValueError("stage_in belongs to a create volume task")
            if options or provider is not None or export is not None:
                raise ValueError("a destroy volume task takes no provider, options, or export: "
                                 "they belong to the create task")
            if not isinstance(volume, str) or not volume.startswith(_REFERENCE):
                raise ValueError("a destroy volume task names its volume as workflow:///<create task>/<volume>")
            parsed = parse_reference(volume)
            if parsed.query or "/" in parsed.path.strip("/") or not parsed.path.strip("/"):
                raise ValueError("a destroy volume task names its volume as workflow:///<create task>/<volume>, "
                                 "not %s" % volume)
            self._volume_from_name = False
            self.target = volume.rstrip("/")
            self.volume_name = parsed.path.strip("/")
            prefix = self.target + "/"
            for target, source in (stage_out or {}).items():
                descriptor = self._descriptor(source, "stage_out")
                location = descriptor["path"]
                if location.startswith(_REFERENCE):
                    if not location.startswith(prefix) and location != self.target:
                        raise ValueError("stage_out source %s is not inside %s" % (location, self.target))
                    location = location[len(prefix):] if location.startswith(prefix) else ""
                descriptor["path"] = safe_volume_path(location, "stage_out source", allow_empty=True)
                self.stage_out[safe_volume_path(target, "stage_out path")] = descriptor
            references = [self.target]
            command = "dagon-volume destroy"
        self.filesystem: Any = None
        self.attached: List[Any] = []
        self.extra_users: set = set()
        self.released: Optional[str] = None
        self.staged: List[Dict[str, Any]] = []
        self.link_path: Optional[str] = None
        self._volume_lock = threading.RLock()
        self._volume_owner: Optional["VolumeTask"] = None
        Task.__init__(self, name, " ".join([command] + references), working_dir=working_dir,
                      transversal_workflow=transversal_workflow, globusendpoint=globusendpoint)

    # -- specification ---------------------------------------------------------

    @staticmethod
    def _provider_name(provider: Any) -> str:
        if isinstance(provider, type):
            return str(getattr(provider, "provider", provider.__name__)).lower()
        return str(provider).lower()

    @staticmethod
    def _descriptor(source: Any, label: str) -> Dict[str, str]:
        if isinstance(source, Mapping):
            if not set(source) <= {"path", "type"} or not isinstance(source.get("path"), str):
                raise ValueError("invalid %s descriptor %r: use {'path': ..., 'type': ...}" % (label, source))
            kind = source.get("type", "auto")
            location = source["path"]
        elif isinstance(source, str):
            kind, location = "auto", source
        else:
            raise ValueError("%s values are paths or descriptors, not %r" % (label, source))
        if kind not in ITEM_KINDS:
            raise ValueError("%s type must be one of %s" % (label, ", ".join(ITEM_KINDS)))
        if not location:
            raise ValueError("%s source must not be empty" % label)
        if location.startswith(_REFERENCE):
            if " " in location:
                raise ValueError("a workflow:// reference ends at a space: %r" % location)
            reference = parse_reference(location)
            if reference.stream:
                raise ValueError("%s cannot read a stream: %s" % (label, location))
            safe_volume_path(reference.path, "%s reference path" % label, allow_empty=label == "stage_out")
        elif label == "stage_in":
            location = str(Path(location).expanduser().resolve())
        return {"path": location, "type": kind}

    def portable_spec(self) -> Dict[str, Any]:
        """The credential-free, JSON-serializable specification."""
        spec: Dict[str, Any] = {"schema_version": SCHEMA_VERSION, "action": self.action,
                                "volume": self.target if self.action == "destroy" else self.volume_name,
                                "release": self.release}
        if self.action == "create":
            provider = self.provider
            if isinstance(provider, type):
                provider = "%s:%s" % (provider.__module__, provider.__qualname__)
            spec.update({"provider": str(provider), "options": self.options,
                         "stage_in": self.stage_in})
            if self.export is not None:
                spec["export"] = self.export
        else:
            spec["stage_out"] = self.stage_out
        return _json_copy(spec, "specification")

    @staticmethod
    def spec_digest(spec: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def as_json(self) -> Dict[str, Any]:
        task = super().as_json()
        task.update({"type": "volume", "volume": self.portable_spec()})
        return task

    # -- workflow membership ------------------------------------------------------

    def set_workflow(self, workflow: Any) -> None:
        super().set_workflow(workflow)
        if workflow is None or self.action != "create" or self.filesystem is not None:
            return
        if self._volume_from_name:
            self.volume_name = re.sub(r"[^A-Za-z0-9._-]", "_", str(self.name))
            self.command = " ".join(["dagon-volume create %s" % self.volume_name] + self.command.split()[3:])
        provider = self.provider
        if isinstance(provider, str) and ":" in provider:
            # A class recorded in JSON as module:qualname.
            import importlib
            module_name, _, qualname = provider.partition(":")
            loaded: Any = importlib.import_module(module_name)
            for part in qualname.split("."):
                loaded = getattr(loaded, part)
            provider = loaded
        from dagon.adhoc import BeeOND
        if isinstance(provider, type) and issubclass(provider, BeeOND):
            raise ValueError("BeeOND volumes cannot be created by a volume task")
        self.filesystem = workflow.create_adhoc_filesystem(provider, name=self.volume_name, scope="volume",
                                                          owner=self, export=self.export, **self.options)
        self.filesystem.bind(self)

    def attach(self, *tasks: Any) -> "VolumeTask":
        """Bind *tasks* to this volume without a ``workflow://`` reference; return this task.

        Each attached task depends on this task and keeps the volume alive until
        it finishes, exactly like a task that refers to the volume.
        """
        if self.action != "create":
            raise ValueError("only a create volume task can attach tasks")
        for task in tasks:
            if task is self:
                continue
            if task not in self.attached:
                self.attached.append(task)
        return self

    def _add_user(self, task: Any) -> None:
        """Count a user that holds no textual reference to this task."""
        if task is self:
            return
        if self not in task.prevs:
            task.add_dependency_to(self)
        command = getattr(task, "command", "") or ""
        if any(owner is self for owner, _ in getattr(task, "volume_references", {}).values()):
            return
        if "workflow:///%s/" % self.name in command or \
                "workflow://%s/%s/" % (self.workflow.name, self.name) in command:
            return
        if task not in self.extra_users:
            self.extra_users.add(task)
            self.increment_reference_count()
        listeners = self.workflow.__dict__.setdefault("_volume_listeners", set())
        if id(self) not in listeners:
            listeners.add(id(self))
            self.workflow.add_listener("on_task_end", self._user_ended)

    def _user_ended(self, task: Any) -> None:
        with self._volume_lock:
            if task not in self.extra_users or task.status is not dagon.Status.FINISHED:
                return
            self.extra_users.discard(task)
        self.decrement_reference_count()

    def resolve_target(self) -> "VolumeTask":
        """The create task whose volume this destroy task releases."""
        found = volume_reference(self.workflow, self.target or "")
        if found is None:
            raise ValueError("%s: %s does not name the volume of a create volume task in workflow %s"
                             % (self.name, self.target, self.workflow.name))
        self._volume_owner = found[0]
        return found[0]

    # -- volume lifecycle ------------------------------------------------------------

    @property
    def emulated(self) -> bool:
        return bool(self.workflow is not None and self.workflow.is_portable_emulation())

    def volume_root(self) -> str:
        """Where the volume lives for the staging helper."""
        return self.filesystem.volume_location("", emulated=self.emulated)

    def _environment(self, filesystem: Any) -> Dict[str, str]:
        """Environment of the staging helper: the bound environment of *filesystem*."""
        if self.emulated:
            extra = filesystem.portable_environment(self)
            for key in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES"):
                extra.pop(key, None)
            return runner_environment(extra)
        environment = runner_environment(filesystem.task_environment(self))
        for key, value in filesystem.path_environment(self).items():
            environment[key] = ":".join(item for item in (str(value), environment.get(key, "")) if item)
        return environment

    def _helper_spec(self, filesystem: Any, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        adapter = "%s:%s" % (type(filesystem).__module__, type(filesystem).__qualname__)
        parameters = {} if self.emulated else dict(filesystem.volume_parameters())
        for key in parameters:
            if _SECRET.search(key):
                raise ValueError("volume parameters must not carry credentials (%s)" % key)
        return {"v": SCHEMA_VERSION, "volume": filesystem.name, "provider": filesystem.provider,
                "access": "posix" if self.emulated else filesystem.access, "adapter": adapter,
                "location": filesystem.volume_location("", emulated=self.emulated),
                "parameters": parameters, "operations": operations}

    def _run_helper(self, filesystem: Any, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        spec = self._helper_spec(filesystem, operations)
        metadata = Path(self.working_dir, ".dagon")
        metadata.mkdir(parents=True, exist_ok=True)
        spec_path = metadata / "volume_operations.json"
        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_path = metadata / "volume_report.json"
        completed = subprocess.run([sys.executable, "-m", "dagon.volume", "stage", str(spec_path),
                                    "--report", str(report_path)],
                                   cwd=self.working_dir, env=self._environment(filesystem),
                                   text=True, capture_output=True)
        metadata.joinpath("volume_stdout.txt").write_text(completed.stdout, encoding="utf-8")
        metadata.joinpath("volume_stderr.txt").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise VolumeError("%s: volume staging failed: %s" % (self.name, completed.stderr.strip()[-2000:]))
        return json.loads(report_path.read_text(encoding="utf-8"))

    def _source(self, location: str) -> str:
        if not location.startswith(_REFERENCE):
            return location
        reference = parse_reference(location)
        if volume_reference(self.workflow, location) is not None:
            raise VolumeError("%s: stage_in cannot read another volume (%s); copy between volumes with a "
                              "command task bound to both" % (self.name, location))
        producer = self.workflow.find_task_by_name(reference.workflow or self.workflow.name, reference.task)
        if producer is None or producer.working_dir is None:
            raise VolumeError("%s: stage_in producer is unavailable: %s" % (self.name, location))
        return os.path.join(producer.working_dir, *[part for part in reference.path.split("/") if part])

    def _create_link(self) -> None:
        """Expose the volume as ``<scratch>/<volume>`` where it has a POSIX path."""
        root = self.filesystem.volume_location("", emulated=self.emulated)
        if self.emulated or self.filesystem.access == "posix":
            link = os.path.join(self.working_dir, self.volume_name)
            if _link(root, link):
                self.link_path = link

    def release_volume(self, reason: str, raise_errors: bool = False) -> None:
        """Stop this task's volume once (idempotent); *reason* is recorded."""
        if self.action != "create" or self.filesystem is None:
            return
        with self._volume_lock:
            if self.released is not None:
                return
            self.released = reason
        error = None
        try:
            if self.filesystem.started:
                self.filesystem.stop()
        except Exception as exc:
            error = exc
            self.workflow.logger.error("%s: volume %s was not released cleanly: %s", self.name, self.volume_name, exc)
        if self.emulated:
            # Emulation mirrors a real release: the data is no longer at the volume path.
            emulated = self.filesystem.emulated_path()
            if os.path.isdir(emulated):
                retired = emulated + "-released"
                shutil.rmtree(retired, ignore_errors=True)
                shutil.move(emulated, retired)
        record = self.workflow.checkpoints.get(self.checkpoint_key())
        if isinstance(record, dict):
            record.setdefault("volume", {})["released"] = reason if error is None else "failed: " + reason
        self.workflow.logger.debug("%s: volume %s released (%s)", self.name, self.volume_name, reason)
        if error is not None and raise_errors:
            raise VolumeError("%s: volume %s could not be stopped: %s" % (self.name, self.volume_name, error))

    # -- reference counting (the scratch garbage collector, applied to the volume) -------

    def decrement_reference_count(self) -> None:
        with self._volume_lock:
            self.reference_count = self.reference_count - 1
            count = self.reference_count
        if count == 0 and self.action == "create" and self.release == "auto" and self.status_executed():
            self.release_volume("no task refers to it")
        if count == 0 and self.remove_scratch_dir is True:
            self.on_garbage()
            if self.workflow.checkpoint_file is not None:
                with open(self.workflow.checkpoint_file, "w") as stream:
                    stream.write(json.dumps(self.workflow.checkpoints, sort_keys=True, indent=4))

    def status_executed(self) -> bool:
        record = self.workflow.checkpoints.get(self.checkpoint_key(), {}) if self.workflow else {}
        return record.get("code") == 0

    def remove_reference_workflow(self) -> None:
        super().remove_reference_workflow()
        if self.action == "create" and self.release == "auto" and self.reference_count <= 0:
            self.release_volume("no task refers to it")

    # -- checkpoint ---------------------------------------------------------------------

    def _users(self) -> List[Any]:
        users = set(self.nexts) | set(self.extra_users)
        if self.filesystem is not None:
            users |= set(self.filesystem.tasks)
        users.discard(self)
        return sorted(users, key=lambda item: item.name)

    def reuse_checkpoint(self) -> bool:
        """Reuse only a recorded success of the same specification.

        Volumes are not persistent: a create task is reused only when every
        task that uses its volume has completed as well, so nothing needs it.
        A destroy task is reused only when its staged-out data still matches.
        """
        checkpoint = self.workflow.checkpoints.get(self.checkpoint_key(), {})
        if checkpoint.get("task_type") != "volume" or checkpoint.get("schema_version") != SCHEMA_VERSION or \
                checkpoint.get("code") != 0:
            return False
        if bool(checkpoint.get("emulated")) != self.emulated:
            return False
        if checkpoint.get("spec_sha256") != self.spec_digest(self.portable_spec()):
            return False
        working_dir = checkpoint.get("working_dir")
        if not isinstance(working_dir, str) or not os.path.isdir(working_dir):
            return False
        if self.action == "create":
            for user in self._users():
                if self.workflow.checkpoints.get(user.checkpoint_key(), {}).get("code") != 0:
                    return False
        else:
            for item in checkpoint.get("staged", []):
                target = Path(working_dir, item.get("target", ""))
                if not target.exists() or _sha256_path(target) != item.get("sha256"):
                    return False
        self.working_dir, self.fair_checkpoint_reused = working_dir, True
        return True

    # -- execution ---------------------------------------------------------------------

    def execute(self) -> None:
        self.released = None
        if self.reuse_checkpoint():
            if self.action == "create":
                self.released = "checkpoint reused: no task needs the volume"
            self.remove_reference_workflow()
            return
        self.create_working_dir()
        spec = self.portable_spec()
        checkpoint = self.initialize_checkpoint()
        checkpoint.update({"schema_version": SCHEMA_VERSION, "task_type": "volume", "action": self.action,
                           "spec_sha256": self.spec_digest(spec), "emulated": self.emulated})
        Path(self.working_dir, ".dagon", "volume_spec.json").write_text(
            json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if self.action == "create":
            self._execute_create(checkpoint)
        else:
            self._execute_destroy(checkpoint)
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            self.remove_reference_workflow()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)

    def _execute_create(self, checkpoint: Dict[str, Any]) -> None:
        filesystem = self.filesystem
        checkpoint["volume"] = {"name": self.volume_name, "provider": filesystem.provider,
                                "access": filesystem.access}
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            if self.workflow.dry:
                return
            try:
                filesystem.start()
            except Exception:
                self.failure_phase = "adhoc"
                raise
            try:
                if self.emulated:
                    emulated = filesystem.emulated_path()
                    # A new volume starts empty, as a started provider does.
                    shutil.rmtree(emulated, ignore_errors=True)
                    os.makedirs(emulated, exist_ok=True)
                self._create_link()
                operations = []
                for target, descriptor in sorted(self.stage_in.items()):
                    source = self._source(descriptor["path"])
                    if descriptor["type"] == "directory" and not os.path.isdir(source) or \
                            descriptor["type"] == "file" and not os.path.isfile(source):
                        raise VolumeError("%s: stage_in %s is not a %s: %s"
                                          % (self.name, target, descriptor["type"], source))
                    operations.append({"op": "put", "source": source, "target": target})
                if operations:
                    self.staged = self._run_helper(filesystem, operations)
            except Exception:
                self.failure_phase = self.failure_phase or "staging"
                checkpoint["code"] = 1
                self.release_volume("creation failed")
                raise
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        self.workflow._fire_event("on_task_execute_start", self)
        checkpoint.update({"code": 0, "staged": self.staged})
        checkpoint["volume"]["link"] = bool(self.link_path)

    def _execute_destroy(self, checkpoint: Dict[str, Any]) -> None:
        owner = self._volume_owner or self.resolve_target()
        self.workflow._fire_event("on_task_execute_start", self)
        if self.workflow.dry:
            return
        if owner.released is not None:
            raise VolumeError("%s: volume %s was already released (%s)" % (self.name, owner.volume_name,
                                                                         owner.released))
        operations = []
        for target, descriptor in sorted(self.stage_out.items()):
            operations.append({"op": "get", "source": descriptor["path"],
                               "target": os.path.join(self.working_dir, *target.split("/"))})
        try:
            if operations:
                self.staged = self._run_helper(owner.filesystem, operations)
                for item, (target, descriptor) in zip(self.staged, sorted(self.stage_out.items())):
                    item["target"] = target
                    if descriptor["type"] != "auto" and item["type"] != descriptor["type"]:
                        raise VolumeError("%s: stage_out %s is a %s, not a %s"
                                          % (self.name, target, item["type"], descriptor["type"]))
        except Exception:
            self.failure_phase = "staging"
            checkpoint["code"] = 1
            raise
        try:
            owner.release_volume("destroyed by %s" % self.name, raise_errors=True)
        except VolumeError:
            self.failure_phase = "adhoc"
            checkpoint["code"] = 1
            raise
        checkpoint.update({"code": 0, "staged": self.staged, "volume": {"name": owner.volume_name,
                                                                         "released": True}})

    # -- provenance -------------------------------------------------------------------

    def get_execution_metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {"model": "volume", "action": self.action, "volume": self.volume_name}
        owner = self if self.action == "create" else self._volume_owner
        if owner is not None and owner.filesystem is not None:
            metadata["adhoc_filesystem"] = owner.filesystem.metadata()
        if self.staged:
            metadata["staged"] = [dict(item) for item in self.staged]
        if self.action == "create":
            metadata["released"] = self.released
            metadata["users"] = [task.name for task in self._users()]
        return metadata

    # -- CWL --------------------------------------------------------------------------

    def _producers(self) -> List[Tuple[str, str, str, Any]]:
        """(reference, workflow, relative path, producer) for every staged-in reference."""
        found = []
        for descriptor in self.stage_in.values():
            location = descriptor["path"]
            if location.startswith(_REFERENCE):
                reference = parse_reference(location)
                workflow_name = reference.workflow or self.workflow.name
                found.append((location, workflow_name, reference.path,
                              self.workflow.find_task_by_name(workflow_name, reference.task)))
        return found

    def output_kind(self, relative: str) -> Optional[str]:
        """CWL type of a path this task's step produces, when declared."""
        items = self.stage_out.items() if self.action == "destroy" else \
            [(self.volume_name + "/" + target, descriptor) for target, descriptor in self.stage_in.items()]
        for target, descriptor in items:
            if target == relative and descriptor["type"] != "auto":
                return "Directory" if descriptor["type"] == "directory" else "File"
        return None

    def input_kind(self, reference: str) -> str:
        for descriptor in self.stage_in.values():
            if descriptor["path"] == reference:
                return "Directory" if descriptor["type"] == "directory" else "File"
        return "File"


def volume_reference_text(owner: VolumeTask, relative: str) -> str:
    """Shell text that replaces a volume reference in a command."""
    return owner.filesystem.volume_reference_text(relative, emulated=owner.emulated)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m dagon.volume stage SPEC [--report FILE]`` and ``key VOLUME PATH``."""
    import argparse
    parser = argparse.ArgumentParser(prog="python -m dagon.volume")
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="run the put/get operations of a volume task")
    stage.add_argument("spec")
    stage.add_argument("--report")
    key = commands.add_parser("key", help="print the object key of a path in an object-store volume")
    key.add_argument("volume")
    key.add_argument("path")
    options = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if options.command == "key":
        print(object_key(options.volume, safe_volume_path(options.path, "path")))
        return 0
    try:
        with open(options.spec, encoding="utf-8") as stream:
            spec = json.load(stream)
        report = run_operations(spec)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print("dagon.volume: %s" % exc, file=sys.stderr)
        return 2
    if options.report:
        with open(options.report, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
    return 0


__all__ = ["VolumeTask", "VolumeError", "VolumeStore", "PosixVolumeStore", "DagonFSNativeVolumeStore",
           "ObjectVolumeStore", "object_key", "plan_volumes", "volume_reference", "run_operations",
           "safe_volume_path", "main"]


if __name__ == "__main__":
    sys.exit(main())
