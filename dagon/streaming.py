"""Streaming between tasks through an ad-hoc file system.

A consumer task refers to a stream of a producer task with the query
component of a ``workflow://`` reference::

    workflow:///B1/frames?stream            # the streaming resource B1 and B2 share
    workflow:///B1/frames?stream=ramdisk    # a named ad-hoc resource

Everything before ``?`` keeps the meaning defined by the workflow schema
(producer workflow, producer task, path), so dependency discovery, FAIR
edges, and CWL ordering are unchanged.  The query only changes *when* the
consumer may start and *where* the data lives: instead of waiting for the
producer to finish and staging a file, the consumer starts once the producer's
launcher runs, and the reference resolves to a stream location on an ad-hoc
file system both tasks are bound to.

Protocol (provider neutral, rename free).  A stream at ``LOCATION`` holds item
objects and a sequence of markers ``.dagon-stream/000000001``, ... written by
the single producer after the item they name is complete::

    {"v": 1, "seq": 1, "item": "frame-0001.dat", "size": 4096, "sha256": "..."}
    {"v": 1, "seq": 42, "end": true, "status": 0, "items": 41}

A marker is valid only when it is a complete JSON line, so a reader that sees
a marker being written retries.  Items are therefore visible to consumers in
publication order, as soon as they are published, until the end marker.  The
producer's launcher writes the end marker with the command's exit status, so
a failed producer fails its consumers.  The same protocol runs over a POSIX
directory (DAGonFS FUSE3, BeeOND), a preloaded namespace (CAPIO, Hercules,
DAGonFS preload: the helper runs under the task's preload environment), the
DAGonFS native socket, and DynoStore objects; adapters choose the store.

Task-side helpers (``python -m dagon.adhoc stream ...``) and the Python API
(:class:`StreamWriter`, :class:`StreamReader`) locate a stream from the
environment that DAGonStar exports to bound tasks.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

STREAM_QUERY = "stream"
MARKER_DIRECTORY = ".dagon-stream"
STREAM_ROOT = ".dagon-streams"
PROTOCOL_VERSION = 1
_ITEM = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,254}$")
_PATH_PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
_STREAM_NAMESPACE = uuid.UUID("6f1f4a52-8c3b-5d1e-9a57-64a6d4c0de11")


class StreamError(RuntimeError):
    """A stream could not be planned, written, or read."""


class StreamProducerFailed(StreamError):
    """The producer ended the stream with a non-zero status."""


# -- references ------------------------------------------------------------

@dataclass(frozen=True)
class WorkflowReference:
    """A parsed ``workflow://<workflow>/<task>/<path>[?query]`` reference."""

    text: str
    workflow: str
    task: str
    path: str
    query: Tuple[Tuple[str, str], ...] = ()

    @property
    def stream(self) -> bool:
        return any(key == STREAM_QUERY for key, _ in self.query)

    @property
    def stream_filesystem(self) -> Optional[str]:
        for key, value in self.query:
            if key == STREAM_QUERY:
                return value or None
        return None


def parse_reference(reference: str, schema: str = "workflow://") -> WorkflowReference:
    """Parse a reference; the optional query is RFC 3986 ``key[=value]&...``."""
    if not reference.startswith(schema):
        raise ValueError("not a workflow reference: %r" % reference)
    body, _, query_text = reference[len(schema):].partition("?")
    query: List[Tuple[str, str]] = []
    if query_text:
        for pair in query_text.split("&"):
            key, _, value = pair.partition("=")
            query.append((urllib.parse.unquote(key), urllib.parse.unquote(value)))
        if len(query) != 1 or query[0][0] != STREAM_QUERY:
            # Only ``?stream[=name]`` is a query. Anything else keeps its
            # meaning from before queries existed: the "?" belongs to the
            # path (for example a shell glob such as ``out?.txt``).
            body, query = reference[len(schema):], []
    pieces = body.split("/")
    if len(pieces) < 2 or not pieces[1]:
        raise ValueError("workflow reference without a task: %r" % reference)
    return WorkflowReference(reference, pieces[0], pieces[1], "/".join(pieces[2:]), tuple(query))


def is_stream_reference(reference: str) -> bool:
    return "?" in reference and parse_reference(reference).stream


def reject_stream_reference(reference: str, kind: str) -> None:
    """Refuse a streaming reference in a task type that has no command launcher."""
    if "?" in reference:
        parsed = parse_reference(reference)
        if parsed.stream:
            raise ValueError("%s tasks cannot consume streams (%s): streaming needs a command task "
                             "bound to a streaming ad-hoc file system" % (kind, reference))


def stream_reference(producer: str, path: str, filesystem: Optional[str] = None, workflow: str = "") -> str:
    """Build ``workflow://<workflow>/<producer>/<path>?stream[=<filesystem>]``."""
    validate_stream_path(path)
    query = STREAM_QUERY + ("=" + urllib.parse.quote(filesystem, safe="") if filesystem else "")
    return "workflow://%s/%s/%s?%s" % (workflow, producer, path, query)


def validate_stream_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts or any(not _PATH_PART.match(part) for part in parts):
        raise ValueError("stream paths are relative names of letters, digits, '.', '_' and '-' "
                         "(no '..' and no leading '.'): %r" % path)
    return "/".join(parts)


def variable_suffix(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", text).upper()


def iter_command_references(command: str, schema: str = "workflow://") -> Iterator[Tuple[int, int, str]]:
    """Yield ``(start, end, text)`` for every reference, using the legacy space boundary."""
    position = 0
    while True:
        start = command.find(schema, position)
        if start == -1:
            return
        end = command.find(" ", start)
        end = len(command) if end == -1 else end
        yield start, end, command[start:end]
        position = end


# -- planned channels --------------------------------------------------------

@dataclass
class StreamChannel:
    """One producer stream, its resource, and its consumers in one run."""

    producer: Any
    path: str
    filesystem: Any
    run_id: str
    consumers: List[Any] = field(default_factory=list)
    location: str = ""
    emulated: bool = False
    #: File DAGonStar writes on the submission host when the producer task has
    #: ended; readers that can see it stop waiting for a marker that cannot come.
    signal: str = ""

    @property
    def key(self) -> str:
        return variable_suffix("%s_%s" % (self.producer.name, self.path))

    @property
    def relative(self) -> str:
        """Provider-neutral stream name: ``<run>/<workflow>/<producer>/<path>``."""
        return "/".join((self.run_id, variable_safe(self.producer.workflow.name),
                         variable_safe(self.producer.name), self.path))

    def spec(self) -> Dict[str, Any]:
        """Credential-free description exported to the producer and consumers."""
        filesystem = self.filesystem
        access = "posix" if self.emulated else filesystem.access
        adapter = "%s:%s" % (type(filesystem).__module__, type(filesystem).__qualname__)
        parameters = {} if self.emulated else dict(filesystem.stream_parameters())
        for key in parameters:
            if _secret_name(key):
                raise ValueError("stream parameters must not carry credentials (%s)" % key)
        spec = {"v": PROTOCOL_VERSION, "location": self.location, "adhoc": filesystem.name,
                "provider": filesystem.provider, "access": access, "adapter": adapter,
                "producer": self.producer.name, "path": self.path, "parameters": parameters}
        if self.signal:
            spec["signal"] = self.signal
        return spec

    def signal_ended(self, status: int) -> None:
        """Record on the submission host that the producer task ended with *status*."""
        if not self.signal:
            return
        os.makedirs(os.path.dirname(self.signal), exist_ok=True)
        temporary = self.signal + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump({"status": int(status), "time": time.time()}, stream)
        os.replace(temporary, self.signal)

    def producer_environment(self) -> Dict[str, str]:
        environment = {"DAGON_STREAM_%s" % self.key: self.location,
                       "DAGON_STREAM_%s_SPEC" % self.key: json.dumps(self.spec(), sort_keys=True),
                       "DAGON_STREAM_OUT_%s" % variable_suffix(self.path): self.location}
        return environment

    def consumer_environment(self, consumer: Any) -> Dict[str, str]:
        return {"DAGON_STREAM_%s" % self.key: self.location,
                "DAGON_STREAM_%s_SPEC" % self.key: json.dumps(self.spec(), sort_keys=True),
                "DAGON_STREAM_IN_%s" % self.key: self.location}

    def metadata(self) -> Dict[str, Any]:
        return {"producer": self.producer.name, "path": self.path, "adhoc": self.filesystem.name,
                "provider": self.filesystem.provider, "consumers": sorted(c.name for c in self.consumers)}


def variable_safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(text))


def _secret_name(name: str) -> bool:
    return bool(re.search(r"(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API_?KEY|PRIVATE)", name, re.I))


def stream_environment(task: Any) -> Dict[str, str]:
    """Stream variables of *task* as producer and consumer (empty without streams)."""
    environment: Dict[str, str] = {}
    outputs = list(getattr(task, "stream_outputs", {}).values())
    inputs = list(getattr(task, "stream_inputs", []))
    for channel in outputs:
        environment.update(channel.producer_environment())
    for channel in inputs:
        environment.update(channel.consumer_environment(task))
    if len(outputs) == 1:
        environment["DAGON_STREAM_OUT"] = outputs[0].location
    if len(inputs) == 1:
        environment["DAGON_STREAM_IN"] = inputs[0].location
    return environment


# -- stores ----------------------------------------------------------------------

def _marker_name(sequence: int) -> str:
    return "%09d" % sequence


def _parse_marker(payload: Optional[bytes], sequence: int) -> Optional[Dict[str, Any]]:
    """A complete marker, or ``None`` while it is absent or being written."""
    if not payload or not payload.endswith(b"\n"):
        return None
    try:
        marker = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(marker, dict) or marker.get("seq") != sequence:
        raise StreamError("stream marker %d is inconsistent" % sequence)
    return marker


class StreamStore:
    """Where items and markers of one stream live.  Subclasses implement I/O."""

    def prepare(self) -> None:
        """Create the stream namespace (producer side)."""

    def write_item(self, name: str, data: bytes) -> None:
        raise NotImplementedError

    def read_item(self, name: str) -> bytes:
        raise NotImplementedError

    def item_path(self, name: str) -> Optional[str]:
        """A path the task can open directly, when the store has one."""
        return None

    def write_marker(self, sequence: int, payload: bytes) -> None:
        raise NotImplementedError

    def read_marker(self, sequence: int) -> Optional[bytes]:
        """Marker bytes, or ``None`` when it does not exist yet."""
        raise NotImplementedError


def _write_all(path: str, data: bytes) -> None:
    # Unbuffered writes and no stat: the DAGonFS interposer does not cover stat.
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


class PosixStreamStore(StreamStore):
    """A directory reached with ordinary file calls (mounted or preloaded)."""

    def __init__(self, location: str, base: Optional[str] = None) -> None:
        self.location = location.rstrip("/") or "/"
        self.base = (base or "").rstrip("/")

    def _mkdirs(self, path: str) -> None:
        # Below the resource root create one component at a time and never
        # stat: interposers (DAGonFS preload) may not intercept stat or listing.
        if not self.base or not path.startswith(self.base + "/"):
            os.makedirs(path, exist_ok=True)
            return
        current = self.base
        for part in [p for p in path[len(self.base):].split("/") if p]:
            current += "/" + part
            try:
                os.mkdir(current)
            except FileExistsError:
                pass

    def prepare(self) -> None:
        self._mkdirs(self.location + "/" + MARKER_DIRECTORY)

    def write_item(self, name: str, data: bytes) -> None:
        _write_all(self.location + "/" + name, data)

    def read_item(self, name: str) -> bytes:
        return _read_all(self.location + "/" + name)

    def item_path(self, name: str) -> Optional[str]:
        return self.location + "/" + name

    def write_marker(self, sequence: int, payload: bytes) -> None:
        _write_all("%s/%s/%s" % (self.location, MARKER_DIRECTORY, _marker_name(sequence)), payload)

    def read_marker(self, sequence: int) -> Optional[bytes]:
        try:
            return _read_all("%s/%s/%s" % (self.location, MARKER_DIRECTORY, _marker_name(sequence)))
        except (FileNotFoundError, NotADirectoryError):
            return None


class DagonFSNativeStreamStore(StreamStore):
    """A stream inside a DAGonFS native-socket volume (``dagonfs.native.Client``)."""

    def __init__(self, socket_path: str, location: str, python_path: Optional[str] = None) -> None:
        if python_path and python_path not in sys.path:
            sys.path.insert(0, python_path)
        try:
            native = importlib.import_module("dagonfs.native")
        except ImportError as exc:
            raise StreamError("the DAGonFS native frontend needs DAGonFS's Python client "
                              "(set python_path, exported as DAGONFS_PYTHON)") from exc
        self.client = native.Client(socket_path)
        self.location = "/" + location.strip("/")

    def prepare(self) -> None:
        self.client.makedirs(self.location + "/" + MARKER_DIRECTORY)

    def write_item(self, name: str, data: bytes) -> None:
        self.client.write_bytes(self.location + "/" + name, data)

    def read_item(self, name: str) -> bytes:
        return self.client.read_bytes(self.location + "/" + name)

    def write_marker(self, sequence: int, payload: bytes) -> None:
        self.client.write_bytes("%s/%s/%s" % (self.location, MARKER_DIRECTORY, _marker_name(sequence)), payload)

    def read_marker(self, sequence: int) -> Optional[bytes]:
        try:
            return self.client.read_bytes("%s/%s/%s" % (self.location, MARKER_DIRECTORY, _marker_name(sequence)))
        except FileNotFoundError:
            return None


class ObjectStreamStore(StreamStore):
    """A stream of objects with deterministic keys (DynoStore and similar stores).

    *client* offers ``put_bytes(data, key)``, ``get_bytes(key)``, and
    ``exists(key)``; keys are UUIDs derived from the stream name, so producer
    and consumers agree on them without listing the catalog.
    """

    def __init__(self, client: Any, name: str) -> None:
        self.client = client
        self.name = name

    def key(self, kind: str, value: str) -> str:
        return str(uuid.uuid5(_STREAM_NAMESPACE, "%s/%s/%s" % (self.name, kind, value)))

    def write_item(self, name: str, data: bytes) -> None:
        self.client.put_bytes(data, self.key("item", name))

    def read_item(self, name: str) -> bytes:
        return self.client.get_bytes(self.key("item", name))

    def write_marker(self, sequence: int, payload: bytes) -> None:
        self.client.put_bytes(payload, self.key("marker", _marker_name(sequence)))

    def read_marker(self, sequence: int) -> Optional[bytes]:
        key = self.key("marker", _marker_name(sequence))
        if not self.client.exists(key):
            return None
        return self.client.get_bytes(key)


# -- writer and reader ------------------------------------------------------------

class _StateLock:
    """Exclusive, portable lock directory next to the producer's sequence file."""

    def __init__(self, path: str, timeout: float = 60.0) -> None:
        self.path = path + ".lock"
        self.timeout = timeout

    def __enter__(self) -> "_StateLock":
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                os.mkdir(self.path)
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise StreamError("stream state lock %s is held" % self.path) from None
                time.sleep(0.01)

    def __exit__(self, *exc: Any) -> None:
        os.rmdir(self.path)


class StreamWriter:
    """Producer side: publish items in order and end the stream once.

    The sequence number lives in a local state file (``state_dir``, by default
    ``$DAGON_STREAM_STATE_DIR``), never on the ad-hoc file system, so the
    protocol needs no rename, listing, or stat on the shared namespace.
    """

    def __init__(self, store: StreamStore, state_file: str) -> None:
        self.store = store
        self.state_file = state_file

    def _state(self) -> Dict[str, Any]:
        try:
            with open(self.state_file, encoding="utf-8") as stream:
                return json.load(stream)
        except FileNotFoundError:
            return {"next": 1, "closed": False}

    def _save(self, state: Dict[str, Any]) -> None:
        temporary = self.state_file + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(state, stream)
        os.replace(temporary, self.state_file)

    def _append(self, record: Dict[str, Any], data: Optional[bytes] = None, name: Optional[str] = None) -> int:
        os.makedirs(os.path.dirname(os.path.abspath(self.state_file)), exist_ok=True)
        with _StateLock(self.state_file):
            state = self._state()
            if state.get("closed"):
                if record.get("end"):
                    return int(state["next"]) - 1
                raise StreamError("the stream is already closed")
            if state["next"] == 1:
                self.store.prepare()
            if data is not None and name is not None:
                self.store.write_item(name, data)
            sequence = int(state["next"])
            record = dict(record, v=PROTOCOL_VERSION, seq=sequence)
            self.store.write_marker(sequence, (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
            state["next"] = sequence + 1
            state["closed"] = bool(record.get("end"))
            self._save(state)
            return sequence

    def publish_bytes(self, name: str, data: bytes) -> int:
        """Write item *name* and make it available; return its sequence number."""
        _check_item(name)
        data = bytes(data)
        return self._append({"item": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()},
                            data, name)

    def publish_file(self, local: str, name: Optional[str] = None) -> int:
        with open(local, "rb") as stream:
            return self.publish_bytes(name or os.path.basename(local), stream.read())

    def commit(self, name: str) -> int:
        """Make an item already written in place available (directory stores only)."""
        _check_item(name)
        if self.store.item_path(name) is None:
            raise StreamError("this stream has no shared directory: use publish instead of commit")
        data = self.store.read_item(name)
        return self._append({"item": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    def close(self, status: int = 0) -> int:
        """Write the end marker (idempotent); return its sequence number."""
        state = self._state()
        return self._append({"end": True, "status": int(status), "items": int(state["next"]) - 1})

    @property
    def closed(self) -> bool:
        return bool(self._state().get("closed"))


def _check_item(name: str) -> None:
    if not _ITEM.match(name or ""):
        raise StreamError("stream item names are 1-255 letters, digits, '.', '_' or '-' "
                          "and do not start with '.': %r" % name)


@dataclass(frozen=True)
class StreamItem:
    sequence: int
    name: str
    size: int
    sha256: str


class StreamReader:
    """Consumer side: iterate items as the producer publishes them.

    Iteration ends at the end marker; a non-zero producer status raises
    :class:`StreamProducerFailed`.  ``idle_timeout`` (seconds, ``None`` for
    no limit) bounds the wait for the next marker.
    """

    def __init__(self, store: StreamStore, poll: float = 0.02, max_poll: float = 0.2,
                 idle_timeout: Optional[float] = None, signal: Optional[str] = None,
                 grace: float = 30.0) -> None:
        self.store = store
        self.poll = poll
        self.max_poll = max_poll
        self.idle_timeout = idle_timeout
        # When the producer-ended signal exists, missing markers can only be
        # replication lag: wait *grace* seconds more, then fail.
        self.signal = signal
        self.grace = grace
        self.end: Optional[Dict[str, Any]] = None

    def _marker(self, sequence: int) -> Dict[str, Any]:
        delay = self.poll
        started = time.monotonic()
        ended_at = None
        while True:
            marker = _parse_marker(self.store.read_marker(sequence), sequence)
            if marker is not None:
                return marker
            now = time.monotonic()
            if self.idle_timeout is not None and now - started > self.idle_timeout:
                raise StreamError("no stream marker %d within %.1f seconds" % (sequence, self.idle_timeout))
            if ended_at is None and self.signal and os.path.exists(self.signal):
                ended_at = now
            if ended_at is not None and now - ended_at > self.grace:
                raise StreamError("the producer task ended without ending the stream (marker %d missing)"
                                  % sequence)
            time.sleep(delay)
            delay = min(self.max_poll, delay * 2)

    def __iter__(self) -> Iterator[StreamItem]:
        sequence = 1
        while True:
            marker = self._marker(sequence)
            if marker.get("end"):
                self.end = marker
                if marker.get("status"):
                    raise StreamProducerFailed("the stream producer ended with status %s" % marker["status"])
                if marker.get("items") != sequence - 1:
                    raise StreamError("the end marker counts %s items, %d were read"
                                      % (marker.get("items"), sequence - 1))
                return
            name = marker.get("item")
            _check_item(name)
            yield StreamItem(sequence, name, int(marker["size"]), str(marker["sha256"]))
            sequence += 1

    def read(self, item: StreamItem) -> bytes:
        """Item bytes, verified against the size and SHA-256 its marker records."""
        data = self.store.read_item(item.name)
        if len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
            raise StreamError("stream item %s does not match its marker" % item.name)
        return data

    def path(self, item: StreamItem) -> Optional[str]:
        return self.store.item_path(item.name)


# -- resolution from the task environment -----------------------------------------

def stream_specs(environment: Optional[Mapping[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    """Stream specifications exported to this task, by key."""
    environment = os.environ if environment is None else environment
    specs = {}
    for name, value in environment.items():
        if name.startswith("DAGON_STREAM_") and name.endswith("_SPEC"):
            try:
                specs[name[len("DAGON_STREAM_"):-len("_SPEC")]] = json.loads(value)
            except ValueError:
                continue
    return specs


def find_spec(stream: str, environment: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """The specification of *stream*: a location, a key, or a producer/path name."""
    environment = os.environ if environment is None else environment
    specs = stream_specs(environment)
    wanted = stream.rstrip("/")
    for key, spec in sorted(specs.items()):
        location = str(spec.get("location", ""))
        if location.startswith("$DAGON_BEEOND/") and environment.get("DAGON_BEEOND"):
            # BeeOND mounts exist only inside the allocation.
            spec = dict(spec, location=environment["DAGON_BEEOND"] + location[len("$DAGON_BEEOND"):])
            location = spec["location"]
        if wanted in (key, location.rstrip("/"), "%s/%s" % (spec.get("producer"), spec.get("path"))):
            return spec
    known = ", ".join(sorted(spec.get("location", key) for key, spec in specs.items())) or "none"
    raise StreamError("no stream %r is bound to this task (bound: %s)" % (stream, known))


def open_store(spec: Mapping[str, Any]) -> StreamStore:
    """Open the store of *spec* through its adapter, falling back to POSIX access."""
    adapter = None
    module_name, _, qualname = str(spec.get("adapter", "")).partition(":")
    if module_name and spec.get("access") not in ("posix", "preload"):
        try:
            adapter = importlib.import_module(module_name)
            for part in qualname.split("."):
                adapter = getattr(adapter, part)
        except (ImportError, AttributeError) as exc:
            raise StreamError("stream adapter %s is not importable in this task" % spec.get("adapter")) from exc
    if adapter is not None and hasattr(adapter, "open_stream_store"):
        return adapter.open_stream_store(spec)
    if spec.get("access") in ("posix", "preload"):
        return PosixStreamStore(str(spec["location"]), spec.get("parameters", {}).get("base"))
    raise StreamError("no stream store for access mode %r" % spec.get("access"))


def state_file(spec: Mapping[str, Any], state_dir: Optional[str] = None) -> str:
    directory = state_dir or os.environ.get("DAGON_STREAM_STATE_DIR") or os.path.join(".dagon", "streams")
    name = hashlib.sha256(str(spec["location"]).encode("utf-8")).hexdigest()[:24]
    return os.path.join(directory, name + ".json")


def writer(stream: str, state_dir: Optional[str] = None,
           environment: Optional[Mapping[str, str]] = None) -> StreamWriter:
    """Writer for a stream this task produces."""
    spec = find_spec(stream, environment)
    return StreamWriter(open_store(spec), state_file(spec, state_dir))


def reader(stream: str, idle_timeout: Optional[float] = None,
           environment: Optional[Mapping[str, str]] = None) -> StreamReader:
    """Reader for a stream this task consumes."""
    if idle_timeout is None and os.environ.get("DAGON_STREAM_IDLE_TIMEOUT"):
        idle_timeout = float(os.environ["DAGON_STREAM_IDLE_TIMEOUT"])
    spec = find_spec(stream, environment)
    grace = float(os.environ.get("DAGON_STREAM_END_GRACE", "30"))
    return StreamReader(open_store(spec), idle_timeout=idle_timeout, signal=spec.get("signal"), grace=grace)


def main(argv: List[str]) -> int:
    """``python -m dagon.adhoc stream publish|commit|close|items``."""
    import argparse
    parser = argparse.ArgumentParser(prog="python -m dagon.adhoc stream")
    operations = parser.add_subparsers(dest="operation", required=True)
    publish = operations.add_parser("publish", help="copy a local file into the stream and publish it")
    publish.add_argument("stream")
    publish.add_argument("local")
    publish.add_argument("--name")
    commit = operations.add_parser("commit", help="publish an item already written in the stream directory")
    commit.add_argument("stream")
    commit.add_argument("item")
    close = operations.add_parser("close", help="end the stream (idempotent)")
    close.add_argument("stream")
    close.add_argument("--status", type=int, default=0)
    items = operations.add_parser("items", help="print each item as it becomes available")
    items.add_argument("stream")
    items.add_argument("--into", help="copy each item (verified) into this local directory and print its path")
    items.add_argument("--verify", action="store_true", help="verify items read in place")
    items.add_argument("--idle-timeout", type=float)
    options = parser.parse_args(argv)
    try:
        if options.operation == "publish":
            print(writer(options.stream).publish_file(options.local, options.name))
        elif options.operation == "commit":
            print(writer(options.stream).commit(options.item))
        elif options.operation == "close":
            writer(options.stream).close(options.status)
        else:
            stream_reader = reader(options.stream, options.idle_timeout)
            if options.into:
                os.makedirs(options.into, exist_ok=True)
            for item in stream_reader:
                direct = stream_reader.path(item)
                if options.into or direct is None:
                    target = os.path.join(options.into or os.path.join(".dagon", "stream-items"), item.name)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as stream:
                        stream.write(stream_reader.read(item))
                    print(target, flush=True)
                else:
                    if options.verify:
                        stream_reader.read(item)
                    print(direct, flush=True)
    except StreamProducerFailed as exc:
        print("dagon.adhoc stream: %s" % exc, file=sys.stderr)
        return 3
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        # Adapter errors (for example AdHocFileSystemError) are RuntimeErrors.
        print("dagon.adhoc stream: %s" % exc, file=sys.stderr)
        return 2
    return 0


__all__ = ["StreamChannel", "StreamError", "StreamItem", "StreamProducerFailed", "StreamReader",
           "StreamStore", "StreamWriter", "PosixStreamStore", "DagonFSNativeStreamStore",
           "ObjectStreamStore", "WorkflowReference", "parse_reference", "stream_reference",
           "is_stream_reference", "reject_stream_reference", "reader", "writer", "open_store",
           "find_spec", "stream_specs", "stream_environment", "iter_command_references", "main"]
