"""Lesson 15: declared tools, external guardrails, and a blocked undeclared action without side effects."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "agentic"))
import tempfile
from pathlib import Path

from agentic_common import producer, quality_control, read, workflow  # noqa: E402
from dagon import Status  # noqa: E402
from dagon.agentic.guardrails import check_action  # noqa: E402
from dagon.agentic.registry import default_registry  # noqa: E402

registry = default_registry()
allowed = ["inspect_records"]
codes = {}
for label, tool, arguments in (
        ("undeclared", "repair_records", {"input": "source"}),
        ("escape", "inspect_records", {"input": "../../etc/passwd"}),
        ("uri", "inspect_records", {"input": "workflow:///other/secret.json"})):
    violation = check_action(tool, arguments, allowed, registry)
    codes[label] = violation.code if violation else None
assert codes == {"undeclared": "undeclared_tool", "escape": "path_escape",
                 "uri": "workflow_uri_injection"}, codes

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-15-") as scratch:
    wf = workflow("Agentic15", scratch)
    wf.add_task(producer())
    agent = quality_control()
    wf.add_task(agent)
    wf.run()
    trace = read(agent, "outputs/trace.json")
    tools = [entry.get("tool") for entry in trace["entries"] if entry["event"] == "tool"]
    assert tools == ["inspect_records", "repair_records"], tools
    report = read(agent, "outputs/evaluation.json")
    assert report["accepted"] and report["guardrail_versions"]["preserve_record_ids"]

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-15-") as scratch:
    wf = workflow("Agentic15Blocked", scratch)
    wf.add_task(producer())
    agent = quality_control(agent="quality-adversarial")
    wf.add_task(agent)
    wf.run()
    assert agent.status is Status.FAILED
    report = read(agent, "outputs/evaluation.json")
    assert report["termination_reason"] == "guardrail_blocked"
    assert report["usage"]["tool_calls"] == 0
    assert not Path(agent.working_dir, "outputs/result.json").exists()
    assert Path(agent.working_dir, ".dagon", "inputs").is_dir(), "the proposed destructive action never ran"
print("action checks:", codes)
print("repair tools:", tools, "| adversarial run:", report["termination_reason"])
