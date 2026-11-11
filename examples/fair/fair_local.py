"""A fully local two-task FAIR-by-design DAGonStar example.

Run from the repository root (no ``dagon.ini`` is required)::

    python3 examples/fair/fair_local.py                 # temporary scratch dir
    python3 examples/fair/fair_local.py --scratch DIR   # keep results in DIR

The workflow uses an inline configuration, local processes only, and writes the
FAIR metadata bundle under ``<scratch>/.dagon/fair/FAIR-Demo/<run-uuid>/``.
"""
import argparse
import tempfile
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType
from dagon.fair import AccessPolicy, Agent, Artifact, FairProfile

EXPECTED_FILES = ("run.json", "ro-crate-metadata.json", "prov.json", "datacite.json",
                  "codemeta.json", "checksums.sha256", "fairness-report.json", "report.md",
                  "report.html")


def local_config(scratch: str) -> dict:
    """Return a configuration that requires no file or external service."""
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "2"},
        "dagon_service": {"use": "False"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }


def build_workflow(scratch: str) -> Workflow:
    workflow = Workflow("FAIR-Demo", config=local_config(scratch))
    workflow.enable_fair(FairProfile(
        title="DAGonStar FAIR demo", description="A two-task local FAIR workflow.",
        creators=[Agent(name="DAGonStar Team")], license="Apache-2.0", keywords=["FAIR", "provenance"],
        access_policy=AccessPolicy(metadata="public", data="local")))
    first = DagonTask(TaskType.BATCH, "A", "mkdir -p output; echo hello > output/message.txt").declare_outputs(
        Artifact("output/message.txt", name="Message", media_type="text/plain", license="Apache-2.0"))
    second = DagonTask(TaskType.BATCH, "B",
                       "cat workflow:///A/output/message.txt > copied-message.txt").declare_outputs(
        Artifact("copied-message.txt", name="Copied message", media_type="text/plain", license="Apache-2.0"))
    workflow.add_task(first)
    workflow.add_task(second)
    return workflow


def run(scratch: str) -> Path:
    """Run the workflow and return the FAIR output directory after verification."""
    workflow = build_workflow(scratch)
    workflow.make_dependencies()
    workflow.run()
    bundles = sorted(Path(scratch, ".dagon", "fair", "FAIR-Demo").glob("*"))
    if len(bundles) != 1:
        raise SystemExit("expected exactly one FAIR bundle, found %d" % len(bundles))
    missing = [name for name in EXPECTED_FILES if not (bundles[0] / name).is_file()]
    if missing:
        raise SystemExit("FAIR bundle is missing: " + ", ".join(missing))
    return bundles[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", help="scratch directory to keep (default: temporary)")
    args = parser.parse_args()
    if args.scratch:
        Path(args.scratch).mkdir(parents=True, exist_ok=True)
        print("FAIR metadata written to", run(str(Path(args.scratch).resolve())))
        return
    with tempfile.TemporaryDirectory(prefix="dagon-fair-") as scratch:
        bundle = run(scratch)
        print("FAIR metadata verified:", ", ".join(sorted(p.name for p in bundle.iterdir())))


if __name__ == "__main__":
    main()
