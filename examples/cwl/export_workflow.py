"""Export a portable DAGonStar command graph as CWL v1.2."""

import argparse
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


def local_config():
    """Return configuration that requires no file or external service."""
    return {
        "batch": {
            "scratch_dir_base": "/tmp",
            "run_base": "",
            "threads": "2",
        },
        "dagon_service": {"use": "False"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }


def build_workflow():
    """Build a command-only graph that is portable to a generic CWL runner."""
    workflow = Workflow("DAGonStar CWL interoperability", config=local_config())
    observations = DagonTask(
        TaskType.BATCH,
        "collect-observations",
        "printf 'observations ready\\n'",
    )
    parameters = DagonTask(
        TaskType.BATCH,
        "prepare-parameters",
        "printf 'parameters ready\\n'",
    )
    simulation = DagonTask(
        TaskType.BATCH,
        "run-simulation",
        "printf 'simulation complete\\n'",
    )
    workflow.add_task(observations)
    workflow.add_task(parameters)
    workflow.add_task(simulation)
    simulation.add_dependency_to(observations)
    simulation.add_dependency_to(parameters)
    return workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("interoperable-workflow.cwl"),
        help="destination CWL file",
    )
    args = parser.parse_args()
    build_workflow().saveAsCWL(args.output)
    print("Wrote %s" % args.output)


if __name__ == "__main__":
    main()
