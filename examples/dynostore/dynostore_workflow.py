"""Producer/consumer DAGonStar workflow backed explicitly by DynoStore."""

import argparse
import os
import tempfile
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType

from dynostore_commands import download_catalog, upload_catalog


def local_config(scratch: str) -> dict:
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "2"},
        "dagon_service": {"use": "False", "route": "http://localhost:57000"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }


def build_workflow(scratch: str, catalog: str) -> Workflow:
    workflow = Workflow("DynoStoreExample", config=local_config(scratch))
    producer = DagonTask(
        TaskType.BATCH,
        "producer",
        "printf 'station,value\\nedge-01,21.5\\n' > readings.csv; "
        + upload_catalog("readings.csv", catalog),
    )
    consumer = DagonTask(
        TaskType.BATCH,
        "consumer",
        "mkdir -p input; "
        + download_catalog(catalog, "input")
        + "; cp input/readings.csv result.csv",
    )
    workflow.add_task(producer)
    workflow.add_task(consumer)
    # Freeze automatically discovered references before adding the ordering-only
    # edge. No producer scratch file is staged into the consumer.
    workflow.make_dependencies()
    consumer.add_dependency_to(producer)
    return workflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="dagonstar-dynostore-example")
    parser.add_argument("--scratch", help="Persistent DAGonStar scratch directory")
    args = parser.parse_args()
    if not os.environ.get("DYNOSTORE_SERVER"):
        parser.error("set DYNOSTORE_SERVER to the DynoStore data access manager URL")

    if args.scratch:
        workflow = build_workflow(args.scratch, args.catalog)
        workflow.run()
        consumer = workflow.find_task_by_name(workflow.name, "consumer")
        print(Path(consumer.working_dir, "result.csv").read_text(encoding="utf-8"))
    else:
        with tempfile.TemporaryDirectory(prefix="dagon-dynostore-") as scratch:
            workflow = build_workflow(scratch, args.catalog)
            workflow.run()
            consumer = workflow.find_task_by_name(workflow.name, "consumer")
            print(Path(consumer.working_dir, "result.csv").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
