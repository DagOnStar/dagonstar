"""Tool-assisted repair under guardrails, then a blocked undeclared action with no side effect."""
import tempfile
from pathlib import Path

from agentic_common import producer, quality_control, read, workflow
from dagon import Status

with tempfile.TemporaryDirectory(prefix="dagon-agentic-") as scratch:
    wf = workflow("AgenticRepair", scratch)
    wf.add_task(producer())
    agent = quality_control()
    wf.add_task(agent)
    wf.run()
    report = read(agent, "outputs/evaluation.json")
    assert report["accepted"] and report["usage"]["tool_calls"] == 2, report["usage"]
    trace = read(agent, "outputs/trace.json")
    assert [entry["event"] for entry in trace["entries"]] == ["tool", "tool", "candidate"]
    print("repair: tools", [entry.get("tool") for entry in trace["entries"] if entry["event"] == "tool"])

with tempfile.TemporaryDirectory(prefix="dagon-agentic-") as scratch:
    wf = workflow("AgenticBlocked", scratch)
    wf.add_task(producer())
    agent = quality_control(agent="quality-adversarial")
    wf.add_task(agent)
    wf.run()
    assert agent.status is Status.FAILED
    report = read(agent, "outputs/evaluation.json")
    assert report["termination_reason"] == "guardrail_blocked", report["termination_reason"]
    assert report["usage"]["tool_calls"] == 0
    assert not Path(agent.working_dir, "outputs/result.json").exists()
    assert Path(agent.working_dir, ".dagon", "inputs").is_dir()  # the proposed `rm -rf .` never ran
    print("blocked:", report["error"]["message"])
