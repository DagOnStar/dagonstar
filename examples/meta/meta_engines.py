"""Run the same word-count workflow, written for different engines, as DAGonStar meta-tasks.

    python examples/meta/meta_engines.py                     # every installed engine
    python examples/meta/meta_engines.py --engine snakemake  # one engine
    python examples/meta/meta_engines.py --engine parsl --parsl-python /path/to/venv/bin/python

Each run builds the graph ``producer -> <engine> meta-task -> report``: a
DAGonStar batch task writes a text, the external workflow (unmodified, under
``workflows/``) counts its words, and a DAGonStar batch task reads the counts
through ``workflow:///<meta task>/outputs/counts.tsv``.  Engines that are not
installed are reported as skipped; nothing is installed or modified.
Scratch data goes to a temporary directory unless ``--scratch`` is given.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dagon import Status, Workflow  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

HERE = Path(__file__).resolve().parent / "workflows"
TEXT = "the quick brown fox jumps over the lazy dog the fox sleeps"

ENGINES = {
    # engine: (workflow definition, engine options, output descriptor)
    "snakemake": (HERE / "Snakefile", {"cores": 1}, {"path": "counts.tsv", "source": "results/counts.tsv"}),
    "parsl": (HERE / "wordcount_parsl.py", {"entrypoint": "main", "config": "threads"},
              {"path": "counts.tsv", "source": "results/counts.tsv"}),
    "nextflow": (HERE / "main.nf", {}, {"path": "counts.tsv", "source": "results/counts.tsv"}),
    "streamflow": (HERE / "wordcount.cwl", {}, {"path": "counts.tsv", "engine_output": "counts"}),
    "cwl": (HERE / "wordcount.cwl", {"arguments": ["--no-container"]},
            {"path": "counts.tsv", "engine_output": "counts"}),
}


def available(engine: str, parsl_python: str) -> bool:
    if engine == "parsl":
        return subprocess.run([parsl_python, "-c", "import parsl"], capture_output=True).returncode == 0
    return shutil.which({"cwl": "cwltool"}.get(engine, engine)) is not None


def build(engine: str, scratch: str, parsl_python: str) -> Workflow:
    config = {"batch": {"scratch_dir_base": scratch, "threads": "1"}, "dagon_service": {"use": "False"},
              "ftp_pub": {"ip": "localhost"}, "slurm": {"partition": ""}}
    workflow = Workflow("meta-" + engine, config=config)
    workflow.add_task(DagonTask(TaskType.BATCH, "producer",
                                "mkdir -p data; printf '%s\\n' '" + TEXT + "' > data/text.txt"))
    definition, options, output = ENGINES[engine]
    options = dict(options)
    if engine == "parsl":
        options["python"] = parsl_python
    workflow.add_task(DagonTask(TaskType.META, "count", engine=engine, workflow=str(definition),
                                inputs={"text": "workflow:///producer/data/text.txt", "top": 3},
                                outputs={"counts": output}, engine_options=options, timeout=900))
    workflow.add_task(DagonTask(TaskType.BATCH, "report", "head -n 1 workflow:///count/outputs/counts.tsv > top.txt"))
    return workflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=["all"] + sorted(ENGINES), default="all")
    parser.add_argument("--parsl-python", default=sys.executable, help="interpreter that has Parsl installed")
    parser.add_argument("--scratch", help="scratch directory (default: a temporary directory)")
    arguments = parser.parse_args()
    engines = sorted(ENGINES) if arguments.engine == "all" else [arguments.engine]
    failures = 0
    with tempfile.TemporaryDirectory(prefix="dagon-meta-") as temporary:
        scratch = arguments.scratch or temporary
        for engine in engines:
            if not available(engine, arguments.parsl_python):
                print("%-10s skipped (engine not installed)" % engine)
                continue
            workflow = build(engine, str(Path(scratch, engine)), arguments.parsl_python)
            Path(scratch, engine).mkdir(parents=True, exist_ok=True)
            workflow.run()
            statuses = {task.name: task.status for task in workflow.tasks}
            if any(status is not Status.FINISHED for status in statuses.values()):
                failures += 1
                print("%-10s FAILED %s" % (engine, {name: status.name for name, status in statuses.items()}))
                continue
            report = workflow.find_task_by_name(workflow.name, "report")
            meta = workflow.find_task_by_name(workflow.name, "count")
            top = Path(report.working_dir, "top.txt").read_text(encoding="utf-8").strip()
            version = meta.meta_result.get("engine_version")
            print("%-10s ok   engine %-12s top word: %s" % (engine, version or "?", top.replace("\t", " = ")))
            assert top == "the\t3", top
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
