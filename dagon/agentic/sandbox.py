"""Deadline-bounded execution of trusted tools, evaluators, guardrails, and adapters.

* ``process`` isolation runs ``module:function`` in a supervised child Python
  process (its own process group/session).  On timeout or cancellation the
  whole group is killed and reaped, so side effects and grandchildren stop.
  :class:`ProcessAdapter` keeps one such process for an adapter's whole run.
* ``inline`` isolation runs in a daemon thread.  A thread cannot be stopped,
  so the registry permits inline execution only for components registered
  with ``side_effect="none"``; on timeout the result is discarded.  That
  declaration is a statement by trusted registration code, not containment.

Neither mode is an operating-system security sandbox.
"""
import importlib
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union

from dagon.agentic.errors import (AgenticCancelled, AgenticProviderError, AgenticTimeoutError,
                                  AgenticToolError)

_POLL_SECONDS = 0.05


def _resolve(function: Union[str, Callable[..., Any]]) -> Callable[..., Any]:
    if callable(function):
        return function
    module_name, _, attribute = function.partition(":")
    return getattr(importlib.import_module(module_name), attribute)


def _worker_environment() -> dict:
    environment = dict(os.environ)
    package_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    entries = [package_root]
    for entry in sys.path:
        entry = entry or os.getcwd()
        if os.path.isdir(entry) and entry not in entries:
            entries.append(entry)
    environment["PYTHONPATH"] = os.pathsep.join(entries)
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _kill_group(process: "subprocess.Popen[bytes]") -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            # Terminate the worker and its descendants on Windows.
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            process.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _spawn(module: str) -> "subprocess.Popen[bytes]":
    options: dict = {}
    if os.name == "posix":
        options["start_new_session"] = True
    else:
        options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen([sys.executable, "-m", module], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=_worker_environment(), **options)


def call_in_process(function: str, args: List[Any], timeout: float, max_output_bytes: int,
                    cancel_event: Optional[threading.Event] = None) -> Any:
    """Run ``function(*args)`` in a supervised child process within ``timeout`` seconds."""
    if timeout <= 0:
        raise AgenticTimeoutError("no time remains for %s" % function)
    process = _spawn("dagon.agentic.worker")
    request = json.dumps({"function": function, "args": args}, allow_nan=False).encode("utf-8")
    deadline = time.monotonic() + timeout
    pending: Optional[bytes] = request
    stdout = b""
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _kill_group(process)
                process.communicate()
                raise AgenticCancelled("cancelled while running %s" % function)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_group(process)
                process.communicate()
                raise AgenticTimeoutError("%s exceeded its %.3g s deadline and was terminated" % (function, timeout))
            try:
                stdout, _ = process.communicate(pending, timeout=min(_POLL_SECONDS, remaining))
                break
            except subprocess.TimeoutExpired:
                pending = None
    finally:
        if process.poll() is None:
            _kill_group(process)
            process.communicate()
        elif os.name == "posix":
            # Reap any grandchildren the worker left in its process group.
            _kill_group(process)
    if len(stdout) > max_output_bytes + 1024:
        raise AgenticToolError("%s produced %d bytes, above the %d-byte bound"
                               % (function, len(stdout), max_output_bytes))
    try:
        reply = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AgenticToolError("%s returned no valid worker reply (exit %s)" % (function, process.returncode))
    if not reply.get("ok"):
        raise AgenticToolError(str(reply.get("error"))[:2000])
    return reply.get("result")


def call_inline(function: Union[str, Callable[..., Any]], args: List[Any], timeout: float,
                cancel_event: Optional[threading.Event] = None) -> Any:
    """Run side-effect-free ``function(*args)`` in a daemon thread with a deadline."""
    if timeout <= 0:
        raise AgenticTimeoutError("no time remains for the operation")
    target = _resolve(function)
    outcome: dict = {}

    def runner() -> None:
        try:
            outcome["result"] = target(*args)
        except BaseException as exc:  # propagated to the caller below
            outcome["error"] = exc

    thread = threading.Thread(target=runner, name="dagon-agentic-inline", daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while thread.is_alive():
        if cancel_event is not None and cancel_event.is_set():
            raise AgenticCancelled("cancelled during an inline operation")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgenticTimeoutError("operation exceeded its %.3g s deadline" % timeout)
        thread.join(min(_POLL_SECONDS, remaining))
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")


class ProcessAdapter(object):
    """An agent adapter hosted in a supervised worker process for one run.

    ``factory`` is an importable ``module:function`` that builds the adapter
    from JSON ``options`` inside the worker.  Every call has a deadline; on
    timeout, cancellation, or a protocol error the worker's process group is
    killed, so a slow adapter cannot act after the supervisor stops waiting.
    Credentials are never sent over the pipe: the worker inherits the
    environment and resolves ``api_key_env`` itself.
    """

    supervised = True

    def __init__(self, factory: str, options: Dict[str, Any], timeout: float,
                 cancel_event: Optional[threading.Event] = None, max_reply_bytes: int = 8 * 1024 * 1024) -> None:
        self.factory = factory
        self.max_reply_bytes = max_reply_bytes
        self.id = "custom"
        self.deterministic = False
        self._lines: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._stderr = b""
        self._process: Optional["subprocess.Popen[bytes]"] = _spawn("dagon.agentic.adapter_worker")
        threading.Thread(target=self._read_stdout, name="dagon-agentic-adapter-out", daemon=True).start()
        threading.Thread(target=self._read_stderr, name="dagon-agentic-adapter-err", daemon=True).start()
        reply = self._call({"factory": factory, "options": options}, timeout, cancel_event)
        self.id = str(reply.get("id", "custom"))
        self.deterministic = bool(reply.get("deterministic"))

    def _read_stdout(self) -> None:
        process = self._process
        assert process is not None and process.stdout is not None
        while True:
            line = process.stdout.readline(self.max_reply_bytes + 1)
            if not line:
                self._lines.put(None)
                return
            self._lines.put(line)

    def _read_stderr(self) -> None:
        process = self._process
        assert process is not None and process.stderr is not None
        for chunk in iter(lambda: process.stderr.read(4096), b""):  # type: ignore[union-attr]
            self._stderr = (self._stderr + chunk)[-4096:]

    def _call(self, request: Dict[str, Any], timeout: float, cancel_event: Optional[threading.Event]) -> Dict[str, Any]:
        process = self._process
        if process is None or process.poll() is not None:
            raise AgenticProviderError("the adapter worker is not running")
        if timeout <= 0:
            self.close(kill=True)
            raise AgenticTimeoutError("no time remains for the adapter")
        try:
            assert process.stdin is not None
            process.stdin.write((json.dumps(request, allow_nan=False) + "\n").encode("utf-8"))
            process.stdin.flush()
        except (OSError, ValueError) as exc:
            self.close(kill=True)
            raise AgenticProviderError("could not send a request to the adapter worker: %s" % exc)
        deadline = time.monotonic() + timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                self.close(kill=True)
                raise AgenticCancelled("cancelled while the adapter was running")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close(kill=True)
                raise AgenticTimeoutError("the adapter exceeded its %.3g s deadline and was terminated" % timeout)
            try:
                line = self._lines.get(timeout=min(_POLL_SECONDS, remaining))
                break
            except queue.Empty:
                continue
        if line is None or not line.endswith(b"\n"):
            detail = self._stderr.decode("utf-8", errors="replace")[-500:]
            self.close(kill=True)
            raise AgenticProviderError("the adapter worker returned no complete reply%s"
                                       % ((": " + detail) if detail else ""))
        try:
            reply = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self.close(kill=True)
            raise AgenticProviderError("the adapter worker returned an invalid reply")
        if not isinstance(reply, dict) or not reply.get("ok"):
            message = str(reply.get("error") if isinstance(reply, dict) else reply)[:2000]
            raise AgenticProviderError("agent adapter failed: %s" % message)
        return reply

    def propose(self, state: Dict[str, Any], max_tokens: int, timeout: float,
                cancel_event: Optional[threading.Event] = None) -> Any:
        reply = self._call({"state": state, "max_tokens": max_tokens, "timeout": timeout}, timeout, cancel_event)
        return reply.get("response"), reply.get("usage")

    def close(self, kill: bool = False) -> None:
        """End the worker; ``kill`` stops its whole process group immediately."""
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if not kill and process.poll() is None and process.stdin is not None:
                process.stdin.close()
                process.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None or os.name == "posix":
            _kill_group(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
