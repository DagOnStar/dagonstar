"""Self-contained meta-task example: no external workflow engine is required.

    python examples/meta/meta_workflow_local.py

``workflows/tiny_engine.py`` stands in for an external engine: an independent
program that knows nothing about DAGonStar except the documented parameter
document of the generic ``command`` adapter.  The graph is

    producer (batch) -> wordcount (meta, command adapter) -> report (batch)

and data moves only through ``workflow://`` references.  A second run with the
same checkpoint file reuses the meta-task after re-verifying its specification,
workflow definition, input, and output digests.  The example finishes with a
portable-emulation run of a Nextflow meta-task that uses the deterministic mock
engine, so it runs without Nextflow.  Scratch data lives in a temporary directory.
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dagon import Status, Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

ENGINE = Path(__file__).resolve().parent / "workflows" / "tiny_engine.py"


def configuration(scratch: str) -> dict:
    return {"batch": {"scratch_dir_base": scratch, "threads": "1"}, "dagon_service": {"use": "False"},
            "ftp_pub": {"ip": "localhost"}, "slurm": {"partition": ""}}


def build(scratch: str, checkpoint: str) -> Workflow:
    workflow = Workflow("MetaLocal", config=configuration(scratch), checkpoint_file=checkpoint)
    workflow.add_task(DagonTask(TaskType.BATCH, "producer",
                                "mkdir -p data; printf 'sea wind sea wave sea wind\\n' > data/text.txt"))
    workflow.add_task(DagonTask(
        TaskType.META, "wordcount", engine="command", workflow=str(ENGINE),
        inputs={"text": "workflow:///producer/data/text.txt", "top": 2},
        outputs={"counts": {"path": "counts.tsv", "source": "results/counts.tsv"}},
        engine_options={"command": [sys.executable, "{workflow}", "{parameters_file}"]}))
    workflow.add_task(DagonTask(TaskType.BATCH, "report",
                                "head -n 1 workflow:///wordcount/outputs/counts.tsv > top.txt"))
    return workflow


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dagon-meta-local-") as scratch:
        checkpoint = str(Path(scratch, "checkpoint.json"))
        first = build(scratch, checkpoint)
        first.run(checkpoint)
        assert all(task.status is Status.FINISHED for task in first.tasks), [(t.name, t.status) for t in first.tasks]
        report = first.find_task_by_name("MetaLocal", "report")
        top = Path(report.working_dir, "top.txt").read_text(encoding="utf-8").strip()
        assert top == "sea\t3", top
        meta = first.find_task_by_name("MetaLocal", "wordcount")
        result = meta.meta_result
        print("external workflow ran:", result["engine"], "workflow sha256", result["workflow"]["sha256"][:12])
        print("collected outputs:", [item["path"] for item in result["outputs"]], "top word:", top.replace("\t", " = "))

        second = build(scratch, checkpoint)
        second.run(checkpoint)
        reused = second.find_task_by_name("MetaLocal", "wordcount")
        assert reused.fair_checkpoint_reused and reused.working_dir == meta.working_dir
        print("second run reused the verified meta-task checkpoint")

        emulated = Workflow("MetaEmulated", config=configuration(scratch), portable_emulation=True)
        emulated.add_task(DagonTask(TaskType.BATCH, "producer", "mkdir -p data; echo 1 > data/x.txt"))
        emulated.add_task(DagonTask(TaskType.META, "pipeline", engine="nextflow", workflow="nextflow-io/hello",
                                    inputs={"x": "workflow:///producer/data/x.txt"},
                                    outputs={"summary": "results/summary.json"}))
        emulated.run()
        pipeline = emulated.find_task_by_name("MetaEmulated", "pipeline")
        assert pipeline.status is Status.FINISHED and pipeline.meta_result["emulated"]
        placeholder = json.loads(Path(pipeline.working_dir, "outputs", "results", "summary.json").read_text())
        print("portable emulation: mock engine stood in for", placeholder["engine"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
