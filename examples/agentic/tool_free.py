"""Tool-free agentic loop: the mock revises once after independent evaluation feedback."""
import tempfile

from agentic_common import producer, quality_control, read, workflow

with tempfile.TemporaryDirectory(prefix="dagon-agentic-") as scratch:
    wf = workflow("AgenticToolFree", scratch)
    wf.add_task(producer())
    agent = quality_control(tools=[])  # an explicit empty list disables the profile's tools
    wf.add_task(agent)
    wf.run()
    report = read(agent, "outputs/evaluation.json")
    assert report["accepted"] is True, report
    assert [item["result_fit"] for item in report["attempts"]] == [0.8, 1.0]
    assert report["usage"]["tool_calls"] == 0
    assert [row["id"] for row in read(agent, "outputs/result.json")["observations"]] == [1, 2, 3, 4]
    print("tool-free: attempts", [item["result_fit"] for item in report["attempts"]], "accepted")
