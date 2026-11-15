"""Shared fixture for the agentic examples: a temporary dagon.ini read by the normal reader.

Nothing here contacts a network service or needs a credential.  The
``quality-local`` profile uses the deterministic ``mock`` adapter.
"""
import json
import sys
from pathlib import Path

# Prefer the checkout when run from it; otherwise use the installed package.
_ROOT = Path(__file__).resolve().parent.parent.parent
if (_ROOT / "dagon").is_dir():
    sys.path.insert(0, str(_ROOT))

from dagon import Workflow  # noqa: E402
from dagon.config import read_config  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

OBSERVATIONS = {"observations": [
    {"id": 1, "station": "SYN001", "temperature_c": 12.0},
    {"id": 2, "station": "SYN001", "temperature_c": 14.0},
    {"id": 2, "station": "SYN001", "temperature_c": 14.0},
    {"id": 3, "station": "SYN002", "temperature_c": 11.5},
    {"id": 4, "station": "SYN002", "temperature_c": 13.5},
]}
SOURCE = "workflow:///prepare/outputs/observations.json"

DAGON_INI = """[batch]
scratch_dir_base = {scratch}
run_base =
remove_dir = False

[dagon_service]
use = False

[ftp_pub]
ip = localhost

[agent_provider.fixture]
implementation = mock

[agent_provider.adversarial]
implementation = mock
scenario = undeclared_tool

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

[agent.quality-adversarial]
provider = adversarial
tools = inspect_records
max_steps = 4
timeout_seconds = 30
"""


def write_ini(scratch):
    path = Path(scratch, "dagon.ini")
    path.write_text(DAGON_INI.format(scratch=Path(scratch).as_posix()), encoding="utf-8")
    return path


def workflow(name, scratch, **options):
    """Create a workflow from a temporary dagon.ini loaded with ``dagon.config.read_config``."""
    return Workflow(name, config=read_config(str(write_ini(scratch))), **options)


def producer(data=None):
    text = json.dumps(OBSERVATIONS if data is None else data).replace("'", "'\\''")
    command = "mkdir -p outputs; printf '%s' '" + text + "' > outputs/observations.json"
    return DagonTask(TaskType.BATCH, "prepare", command)


def quality_control(name="quality_control", **overrides):
    options = dict(
        agent="quality-local",
        specification={"schema_version": 1, "objective": "Produce a complete, validated observation table",
                       "context": "Deterministic teaching fixture",
                       "output_schema": {"type": "object", "required": ["observations"]}},
        inputs={"source": SOURCE},
        requirements=[{"id": "completeness", "description": "All expected records are present",
                       "evaluator": "record_coverage", "expected": {"count": 4}, "weight": 1.0,
                       "mandatory": True, "minimum_score": 1.0}],
        evaluation={"aggregation": "weighted_mean", "threshold": 1.0},
        outputs={"result": "outputs/result.json", "evaluation": "outputs/evaluation.json"},
    )
    options.update(overrides)
    return DagonTask(TaskType.AGENTIC, name=name, **options)


def read(task, relative):
    return json.loads(Path(task.working_dir, relative).read_text(encoding="utf-8"))
