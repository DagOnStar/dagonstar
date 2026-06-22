"""Minimal DAGonStar workflow designed for Google Colab and local notebooks."""

from pathlib import Path
import tempfile

from dagon import Workflow
from dagon.task import DagonTask, TaskType


def workflow_config(workdir: Path) -> dict:
    """Return the minimal local configuration required by this example."""
    return {
        "batch": {"scratch_dir_base": str(workdir), "run_base": "", "remove_dir": "False"},
        "dagon_service": {"use": "False"},
        "ftp_pub": {"ip": "localhost", "user": "anonymous", "password": ""},
    }


def build_workflow(workdir: Path) -> Workflow:
    """Build a three-task local DAG using a ``workflow://`` input."""
    workflow = Workflow("ColabHello", config=workflow_config(workdir))
    workflow.add_task(DagonTask(TaskType.BATCH, "write_hello", "printf 'hello from DAGonStar\\n' > hello.txt"))
    workflow.add_task(DagonTask(
        TaskType.BATCH, "decorate_hello",
        "sed 's/$/ from a dependent task/' workflow:///write_hello/hello.txt > result.txt",
    ))
    workflow.add_task(DagonTask(
        TaskType.BATCH, "validate", "grep -q 'dependent task' workflow:///decorate_hello/result.txt",
    ))
    workflow.make_dependencies()
    return workflow


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="dagonstar-colab-"))
    workflow = build_workflow(workdir)
    workflow.run()
    result = Path(workflow.tasks[1].get_scratch_dir()) / "result.txt"
    print(f"Working directory: {workdir}")
    print(result.read_text(encoding="utf-8").strip())
    print("DAGonStar Colab hello example completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
