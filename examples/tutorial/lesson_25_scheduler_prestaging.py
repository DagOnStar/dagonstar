"""Lesson 25: stage inputs before submission, and never submit when stage-in fails (mock sbatch)."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "examples" / "dataflow" / "slurm"))
import logging
import tempfile
from pathlib import Path

from mock_scheduler import mock_sbatch, submission_for  # noqa: E402
from dagon.batch import Batch, Slurm  # noqa: E402
from dagon.prestage import PreStageConfigurationError  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402
from examples.tutorial.common.support import workflow  # noqa: E402

logging.disable(logging.CRITICAL)  # the induced failure logs an expected error
refused = []
plain = Batch("b", "true")
plain.pre_stage = True  # an explicit request on a backend without the capability
for label, task in (("batch", plain), ("beeond", Slurm("s", "true", beeond="task", pre_stage=True))):
    try:
        workflow("eligibility-" + label, tempfile.gettempdir()).add_task(task)
    except PreStageConfigurationError:
        refused.append(label)
assert refused == ["batch", "beeond"], refused


def run(scratch, reference):
    log = str(Path(scratch, "sbatch.jsonl"))
    wf = workflow("PreStage25", scratch, pre_stage=True)
    producer = DagonTask(TaskType.BATCH, "forcing", "mkdir -p data; echo 1.5 > data/wind.txt")
    simulate = DagonTask(TaskType.SLURM, "simulate", "cat " + reference + " > used.txt", ntasks=8)
    wf.add_task(producer)
    wf.add_task(simulate)
    with mock_sbatch(log):
        wf.run()
    return simulate, submission_for(log, "simulate")


with tempfile.TemporaryDirectory(prefix="dagon-tutorial-25-") as scratch:
    simulate, submission = run(scratch, "workflow:///forcing/data/wind.txt")
    assert simulate.status.name == "FINISHED"
    assert submission["marker_present"] and submission["inputs_populated"], submission
    metadata = simulate.get_execution_metadata()["pre_stage"]
    assert metadata["pre_stage_effective"] and metadata["inputs_content_verified"] == 1
    assert scratch not in str(metadata), "pre-staging metadata stays path-free"

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-25-") as scratch:
    simulate, submission = run(scratch, "workflow:///forcing/data/missing.txt")
    assert simulate.status.name == "FAILED" and simulate.failure_phase == "staging"
    assert submission is None, "sbatch must never run after a failed stage-in"
print("ineligible requests refused:", refused)
print("inputs staged and verified before sbatch; failed stage-in never submitted")
