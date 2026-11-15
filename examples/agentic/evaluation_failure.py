"""A candidate that misses a mandatory gate is not published and downstream tasks never run."""
import tempfile
from pathlib import Path

from agentic_common import producer, quality_control, read, workflow
from dagon import Status
from dagon.task import DagonTask, TaskType

with tempfile.TemporaryDirectory(prefix="dagon-agentic-") as scratch:
    wf = workflow("AgenticFailure", scratch)
    wf.add_task(producer())
    # Five unique stations are required, but the fixture only has two: no revision can succeed.
    agent = quality_control(tools=[], budgets={"max_attempts": 2}, requirements=[
        {"id": "completeness", "evaluator": "record_coverage", "expected": {"count": 4}, "weight": 2.0},
        {"id": "stations", "evaluator": "exact_match", "expected": 5, "weight": 1.0, "mandatory": True,
         "options": {"path": "station_count"}}],
        evaluation={"threshold": 0.6})
    consumer = DagonTask(TaskType.BATCH, "publish_table",
                         "cp workflow:///quality_control/outputs/result.json table.json")
    wf.add_task(agent)
    wf.add_task(consumer)
    wf.run()
    assert agent.status is Status.FAILED and consumer.status is Status.FAILED
    assert consumer.working_dir is None, "the downstream task must not execute"
    report = read(agent, "outputs/evaluation.json")
    assert report["accepted"] is False
    assert report["termination_reason"] == "max_attempts_exhausted"
    assert abs(report["attempts"][-1]["result_fit"] - 2.0 / 3.0) < 1e-12  # F = (2*1 + 1*0) / 3
    assert report["mandatory_failures"] == ["stations"]
    assert not Path(agent.working_dir, "outputs/result.json").exists()
    print("not accepted: fit", report["attempts"][-1]["result_fit"], "mandatory failures", report["mandatory_failures"])
