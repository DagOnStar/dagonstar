"""A local, file-producing DAGonStar workflow for Colab or Jupyter."""

from pathlib import Path
import tempfile

from dagon import Workflow
from dagon.task import DagonTask, TaskType
from hello_colab import workflow_config


def build_workflow(workdir: Path) -> Workflow:
    """Build ``prepare_data -> transform_data -> summarize_data``."""
    workflow = Workflow("ColabWorkflowFiles", config=workflow_config(workdir))
    workflow.add_task(DagonTask(
        TaskType.BATCH, "prepare_data",
        "printf 'name,value\\nalpha,2\\nbeta,3\\n' > input.csv",
    ))
    workflow.add_task(DagonTask(
        TaskType.BATCH, "transform_data",
        "awk -F, 'NR == 1 { print \"name,double\"; next } { print $1 \",\" $2 * 2 }' "
        "workflow:///prepare_data/input.csv > transformed.csv",
    ))
    workflow.add_task(DagonTask(
        TaskType.BATCH, "summarize_data",
        "awk -F, 'NR > 1 { total += $2 } END { print \"total=\" total }' "
        "workflow:///transform_data/transformed.csv > summary.txt",
    ))
    workflow.make_dependencies()
    return workflow


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="dagonstar-colab-files-"))
    workflow = build_workflow(workdir)
    workflow.run()
    summary = Path(workflow.tasks[2].get_scratch_dir()) / "summary.txt"
    print(f"Working directory: {workdir}")
    print(f"Summary path: {summary}")
    print(summary.read_text(encoding="utf-8").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
