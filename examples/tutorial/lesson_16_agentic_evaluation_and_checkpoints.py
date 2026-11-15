"""Lesson 16: independent result fit, mandatory gates, accepted publication, and checkpoint identity."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "agentic"))
import json
import tempfile
from pathlib import Path

from agentic_common import OBSERVATIONS, producer, quality_control, read, workflow  # noqa: E402
from dagon import Status  # noqa: E402
from dagon.agentic.evaluation import aggregate  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

# Golden aggregate: F = (2 * 1.0 + 1 * 0.0) / 3; the mandatory gate fails independently of F.
golden = aggregate([
    {"id": "completeness", "status": "pass", "score": 1.0, "weight": 2.0, "mandatory": False,
     "minimum_score": None, "hard": False},
    {"id": "stations", "status": "fail", "score": 0.0, "weight": 1.0, "mandatory": True,
     "minimum_score": 1.0, "hard": False}], threshold=0.6)
assert abs(golden["result_fit"] - 2.0 / 3.0) < 1e-12 and golden["accepted"] is False, golden
assert golden["mandatory_failures"] == ["stations"], golden

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-16-") as scratch:
    wf = workflow("Agentic16Gate", scratch)
    wf.add_task(producer())
    agent = quality_control(tools=[], budgets={"max_attempts": 2}, requirements=[
        {"id": "completeness", "evaluator": "record_coverage", "expected": {"count": 4}, "weight": 2.0},
        {"id": "stations", "evaluator": "exact_match", "expected": 5, "weight": 1.0, "mandatory": True,
         "options": {"path": "station_count"}}], evaluation={"threshold": 0.6})
    consumer = DagonTask(TaskType.BATCH, "publish_table",
                         "cp workflow:///quality_control/outputs/result.json table.json")
    wf.add_task(agent)
    wf.add_task(consumer)
    wf.run()
    assert agent.status is Status.FAILED and consumer.working_dir is None
    report = read(agent, "outputs/evaluation.json")
    assert report["mandatory_failures"] == ["stations"] and not report["accepted"]
    assert not Path(agent.working_dir, "outputs/result.json").exists(), "rejected output must not be published"

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-16-") as scratch:
    checkpoint = str(Path(scratch, "checkpoint.json"))

    def run(threshold=1.0):
        wf = workflow("Agentic16Resume", scratch, checkpoint_file=checkpoint)
        wf.add_task(producer())
        task = quality_control(evaluation={"threshold": threshold})
        wf.add_task(task)
        wf.run(checkpoint)
        return task

    first = run()
    assert Path(first.working_dir, ".dagon", "agentic", "commit.json").is_file()
    assert run().fair_checkpoint_reused
    assert not run(threshold=0.95).fair_checkpoint_reused, "a contract change must re-run"
    upstream = Path(first.prevs[0].working_dir, "outputs", "observations.json")
    unique = [row for index, row in enumerate(OBSERVATIONS["observations"]) if index != 2]
    upstream.write_text(json.dumps({"observations": unique}), encoding="utf-8")
    assert not run(threshold=0.95).fair_checkpoint_reused, "an input content change must re-run"
print("golden fit:", round(golden["result_fit"], 6), "| gate failures:", golden["mandatory_failures"])
print("checkpoint: reused when identical; re-ran after contract and input changes")
