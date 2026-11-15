"""Shared, credential-free fixtures for agentic-task tests."""
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dagon import Workflow
from dagon.agentic.config import MOCK_SCENARIOS
from dagon.task import DagonTask, TaskType
from tests.helpers import minimal_config

DATA = {"observations": [{"id": 1, "value": 1.5}, {"id": 2, "value": 2.5}, {"id": 2, "value": 2.5},
                         {"id": 3, "value": 3.5}, {"id": 4, "value": 4.5}]}
SOURCE = "workflow:///prepare/outputs/observations.json"
REQUIREMENT = {"id": "completeness", "description": "All expected records are present",
               "evaluator": "record_coverage", "expected": {"count": 4}, "weight": 1.0,
               "mandatory": True, "minimum_score": 1.0}
SPECIFICATION = {"schema_version": 1, "objective": "Produce a complete, validated observation table",
                 "context": "Deterministic teaching fixture",
                 "output_schema": {"type": "object", "required": ["observations"]}}
SECRET = "sk-test-SENTINEL-0123456789"

FIXTURE_INI = """[agent_provider.fixture]
implementation = mock

[agent.quality-local]
provider = fixture
strategy = bounded_iterative
tools = inspect_records, repair_records
guardrails = preserve_record_ids
max_steps = 8
max_tool_calls = 8
timeout_seconds = 60
max_tokens = 4096
max_tool_output_bytes = 65536
max_trace_bytes = 262144
"""


def agent_sections(endpoint=None):
    sections = {
        "agent_provider.fixture": {"implementation": "mock"},
        "agent.quality-local": {"provider": "fixture", "strategy": "bounded_iterative",
                                "tools": "inspect_records, repair_records", "guardrails": "preserve_record_ids",
                                "max_steps": "8", "max_tool_calls": "8", "timeout_seconds": "60",
                                "max_tokens": "4096", "max_tool_output_bytes": "65536",
                                "max_trace_bytes": "262144"},
        "agent.reason-only": {"provider": "fixture", "max_steps": "4", "timeout_seconds": "60"},
    }
    for scenario in sorted(MOCK_SCENARIOS):
        sections["agent_provider.mock-" + scenario] = {"implementation": "mock", "scenario": scenario}
        sections["agent." + scenario] = {"provider": "mock-" + scenario, "tools": "inspect_records, repair_records",
                                         "guardrails": "preserve_record_ids", "max_steps": "4",
                                         "timeout_seconds": "1" if scenario == "slow" else "60"}
    if endpoint is not None:
        sections["llm.loopback"] = {"endpoint": endpoint, "model": "fixture-model",
                                    "api_key_env": "DAGON_TEST_AGENT_KEY"}
        sections["agent_provider.builtin"] = {"implementation": "builtin"}
        sections["agent.quality-live"] = {"provider": "builtin", "llm_provider": "loopback",
                                          "tools": "inspect_records, repair_records",
                                          "guardrails": "preserve_record_ids", "max_steps": "6",
                                          "timeout_seconds": "30", "max_tokens": "4096"}
    return sections


def agent_config(scratch, endpoint=None):
    config = minimal_config()
    config["batch"]["scratch_dir_base"] = str(scratch)
    config.update(agent_sections(endpoint))
    return config


def agent_workflow(name, scratch, portable=False, endpoint=None, **options):
    return Workflow(name, config=agent_config(scratch, endpoint), portable_emulation=portable, **options)


def add_producer(workflow, scratch, name="prepare", data=None, relative="outputs/observations.json", raw=None):
    """Add a completed producer whose output already exists (checkpoint-reused when run)."""
    directory = Path(scratch, "producer-" + name)
    target = directory / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        target.write_bytes(raw)
    else:
        target.write_text(json.dumps(DATA if data is None else data), encoding="utf-8")
    task = DagonTask(TaskType.BATCH, name, "exit 1", working_dir=str(directory))
    workflow.add_task(task)
    workflow.checkpoints[workflow.name + "." + name] = {"working_dir": str(directory), "code": 0}
    return task


def agent_task(name="quality_control", **overrides):
    options = dict(agent="quality-local", specification=SPECIFICATION, inputs={"source": SOURCE},
                   requirements=[REQUIREMENT], evaluation={"aggregation": "weighted_mean", "threshold": 1.0})
    options.update(overrides)
    return DagonTask(TaskType.AGENTIC, name=name, **options)


def prepared(workflow, scratch, task=None, **producer):
    add_producer(workflow, scratch, **producer)
    task = task or agent_task()
    workflow.add_task(task)
    workflow.make_dependencies()
    return task


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# -- trusted test tools, evaluators, and guards ----------------------------------

def sleepy_tool(arguments, context):
    time.sleep(float(arguments.get("seconds", 30)))
    return {"slept": True}


def spawning_tool(arguments, context):
    """Start a long-lived grandchild that records its PID, then hang."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    Path(arguments["pid_file"]).write_text(str(child.pid), encoding="utf-8")
    time.sleep(60)
    return {}


def failing_tool(arguments, context):
    raise RuntimeError("tool failure sentinel")


def huge_tool(arguments, context):
    return {"blob": "x" * 200000}


def nan_evaluator(candidate, expected, options, context):
    return {"status": "pass", "score": float("nan")}


def high_evaluator(candidate, expected, options, context):
    return {"status": "pass", "score": 1.2}


def raising_evaluator(candidate, expected, options, context):
    raise RuntimeError("evaluator failure sentinel")


def fixed_evaluator(candidate, expected, options, context):
    return {"status": "pass" if expected >= 1 else "fail", "score": expected}


def raising_guard(subject, context):
    raise RuntimeError("guard failure sentinel")


# -- late-effect fixtures: each records that it started, outlives its deadline, then writes a marker --

def _late_marker(marker, delay, started=None, spawn=False):
    if started:
        # Wall-clock start on this host (file mtimes may come from an NFS server's clock).
        Path(started).write_text(repr(time.time()), encoding="utf-8")
    if spawn:
        # A descendant that would write the marker after the component has been stopped.
        code = "import time, pathlib; time.sleep(%r); pathlib.Path(%r).write_text('late')" % (delay, marker)
        subprocess.Popen([sys.executable, "-c", code])
        time.sleep(delay + 30)
    time.sleep(delay)
    Path(marker).write_text("late", encoding="utf-8")


def late_evaluator(candidate, expected, options, context):
    _late_marker(options["marker"], options["delay"], options.get("started"), options.get("spawn", False))
    return {"status": "pass", "score": 1.0}


def late_guard(subject, context):
    _late_marker(os.environ["DAGON_TEST_LATE_MARKER"], float(os.environ["DAGON_TEST_LATE_DELAY"]),
                 os.environ.get("DAGON_TEST_LATE_STARTED"))
    return None


class LateAdapter(object):
    """A custom adapter whose first proposal outlives the time it was given, then writes a marker."""

    id = "late"
    deterministic = True

    def __init__(self, marker="", started="", spawn=False):
        self.marker = marker
        self.started = started
        self.spawn = spawn

    def propose(self, state, max_tokens, timeout):
        _late_marker(self.marker, float(timeout) + 0.5, self.started, self.spawn)
        return {"action": "submit", "candidate": {"observations": []}}, {"total_tokens": 0}


def late_adapter_factory(**options):
    return LateAdapter(marker=os.environ.get("DAGON_TEST_LATE_MARKER", ""),
                       started=os.environ.get("DAGON_TEST_LATE_STARTED", ""),
                       spawn=os.environ.get("DAGON_TEST_LATE_SPAWN") == "1")


def pid_alive(pid):
    """True if ``pid`` is running; a killed but unreaped (zombie) process counts as stopped.

    Inside containers whose init does not reap orphans, a killed grandchild stays
    a zombie, and minimal images have no ``ps``, so Linux reads ``/proc`` directly.
    """
    if os.name != "posix":
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    stat = Path("/proc", str(pid), "stat")
    if Path("/proc/self/stat").exists():
        try:
            state = stat.read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            return False
        return state not in ("Z", "X")
    try:
        out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
        return bool(out.strip()) and not out.strip().startswith("Z")
    except OSError:
        return True


# -- loopback OpenAI-compatible fixture --------------------------------------------

class LoopbackLLM(object):
    """Scripted Chat Completions server on 127.0.0.1 with an ephemeral port."""

    def __init__(self, replies, status=200, usage=True):
        self.replies = list(replies)
        self.requests = []
        self.status = status
        self.usage = usage
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                fixture.requests.append({"path": self.path, "authorization": self.headers.get("Authorization"),
                                         "body": body})
                if fixture.status != 200:
                    payload = json.dumps({"error": "denied for key " + SECRET}).encode("utf-8")
                    self.send_response(fixture.status)
                else:
                    reply = fixture.replies.pop(0) if fixture.replies else {"action": "submit", "candidate": {}}
                    content = reply if isinstance(reply, str) else json.dumps(reply)
                    response = {"choices": [{"message": {"role": "assistant", "content": content}}]}
                    if fixture.usage:
                        response["usage"] = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
                    payload = json.dumps(response).encode("utf-8")
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.endpoint = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
