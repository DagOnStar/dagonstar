"""Lesson 31: run workflows written for other engines with TaskType.META.  A new engine needs
only an adapter; checkpoints are reused only after their identity is re-verified; failures name
their lifecycle phase; portable emulation replaces any engine by the deterministic mock."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json
import tempfile
from pathlib import Path

from dagon import Status
from dagon.meta import EngineInvocation, MetaEngineAdapter, register_adapter
from dagon.meta.adapters.base import adapter_names, unregister_adapter
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow

ENGINE_SCRIPT = """import json, sys
parameters = json.load(open(sys.argv[1]))
words = open(parameters["text"]).read().split()
open("tally.json", "w").write(json.dumps({"words": len(words), "unique": len(set(words))}))
"""


class TallyAdapter(MetaEngineAdapter):
    """A toy 'engine': runs a Python workflow file with a JSON parameter file, no shell."""

    name = "lesson31-tally"

    def prepare(self, context):
        parameters = context.write_json("tally-parameters.json", context.parameters)
        return EngineInvocation(argv=[sys.executable, context.workflow, str(parameters)], cwd=context.run_dir)


# 1. A new engine is one adapter class and one registration; built-in names are protected.
register_adapter("lesson31-tally", TallyAdapter, replace=True)
assert "lesson31-tally" in adapter_names()
try:
    register_adapter("nextflow", TallyAdapter)
except ValueError as error:
    protected = str(error)
else:
    raise AssertionError("a built-in adapter must not be replaced")


def build(scratch, definition, checkpoint=None):
    wf = workflow("Meta31", scratch, checkpoint_file=checkpoint)
    wf.add_task(DagonTask(TaskType.BATCH, "observe", "mkdir -p out; echo 'gust calm gust' > out/log.txt"))
    wf.add_task(DagonTask(TaskType.META, "tally", engine="lesson31-tally", workflow=str(definition),
                          inputs={"text": "workflow:///observe/out/log.txt"},
                          outputs={"tally": "tally.json"}))
    wf.add_task(DagonTask(TaskType.BATCH, "report", "cp workflow:///tally/outputs/tally.json report.json"))
    return wf


with tempfile.TemporaryDirectory(prefix="dagon-tutorial-31-") as scratch:
    definition = Path(scratch, "tally_workflow.py")
    definition.write_text(ENGINE_SCRIPT, encoding="utf-8")
    checkpoint = str(Path(scratch, "checkpoint.json"))

    # 2. Data moves only through workflow:// references, in and out of the engine.
    first = build(scratch, definition, checkpoint)
    first.run(checkpoint)
    tally = first.find_task_by_name("Meta31", "tally")
    report = first.find_task_by_name("Meta31", "report")
    assert json.loads(Path(report.working_dir, "report.json").read_text()) == {"words": 3, "unique": 2}
    metadata = tally.get_execution_metadata()
    assert metadata["model"] == "meta" and metadata["adapter"] == "lesson31-tally"
    print("observe -> tally (lesson31-tally adapter) -> report: 3 words, 2 unique")

    # 3. Checkpoint reuse re-verifies the specification, workflow definition, inputs, and outputs.
    second = build(scratch, definition, checkpoint)
    second.run(checkpoint)
    assert second.find_task_by_name("Meta31", "tally").fair_checkpoint_reused
    definition.write_text(ENGINE_SCRIPT + "# revised\n", encoding="utf-8")
    third = build(scratch, definition, checkpoint)
    third.run(checkpoint)
    assert not third.find_task_by_name("Meta31", "tally").fair_checkpoint_reused
    print("checkpoint reused when unchanged; rerun after the workflow definition changed")

    # 4. Failures name their phase: a missing engine fails before anything runs.
    missing = workflow("Missing31", scratch)
    missing.add_task(DagonTask(TaskType.META, "external", engine="snakemake", workflow=str(definition),
                               engine_options={"executable": "dagon-no-such-snakemake"}))
    missing.run()
    external = missing.find_task_by_name("Missing31", "external")
    assert external.status is Status.FAILED and external.failure_phase == "engine"
    try:
        DagonTask(TaskType.META, "leaky", engine="mock", workflow="x", engine_options={"api_token": "x"})
    except ValueError as error:
        rejected = str(error)
    else:
        raise AssertionError("credential-like engine options must be rejected")

    # 5. Portable emulation never starts the engine: the mock adapter writes placeholders.
    emulated = workflow("Emulated31", scratch, portable_emulation=True)
    emulated.add_task(DagonTask(TaskType.BATCH, "observe", "mkdir -p out; echo calm > out/log.txt"))
    emulated.add_task(DagonTask(TaskType.META, "pipeline", engine="nextflow", workflow="nextflow-io/hello",
                                inputs={"text": "workflow:///observe/out/log.txt"},
                                outputs={"counts": "results/counts.tsv"}))
    emulated.run()
    pipeline = emulated.find_task_by_name("Emulated31", "pipeline")
    placeholder = json.loads(Path(pipeline.working_dir, "outputs", "results", "counts.tsv").read_text())
    assert placeholder["portable_emulation"] is True and placeholder["engine"] == "nextflow"
unregister_adapter("lesson31-tally")
print("missing engine: failure_phase=engine; credential-like option rejected:", rejected)
print("built-in adapter protected:", protected)
print("nextflow emulated by the mock adapter: placeholder output, no engine started")
