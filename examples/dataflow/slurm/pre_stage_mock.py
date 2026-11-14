"""Scheduler-aware pre-staging, legacy vs enabled, with a mock scheduler (no Slurm required).

Run from any directory (no ``dagon.ini`` is required)::

    python3 examples/dataflow/slurm/pre_stage_mock.py                 # temporary scratch
    python3 examples/dataflow/slurm/pre_stage_mock.py --scratch DIR   # keep results in DIR

The workflow has the shape of a small coastal-ocean forecast:

* ``forcing`` writes 24 hourly atmospheric forcing files;
* ``bathymetry`` writes a synthetic depth profile;
* ``simulate`` is the expensive step (it requests 200 cores) and reads every
  forcing file through a glob, ``workflow:///forcing/forcing/hour_*.txt``, plus
  the bathymetry;
* ``analyse`` extracts the five highest sea levels and explicitly opts out
  (``pre_stage=False``) to show a task-level override.

The workflow runs twice: with the default lifecycle, where ``simulate``
stages its inputs inside the job, and with ``Workflow(pre_stage=True)``, where
it stages them before ``sbatch`` is called.  ``sbatch`` is replaced by
``mock_scheduler.py``, which runs the job script immediately with the local
bash and records, at submission time, whether the stage-in marker existed
and whether the inputs were already on scratch.  There is no queue and no
allocation here, so the core-hour figure printed at the end is the estimate
``cores x staging_seconds / 3600`` of allocated resources that the legacy
lifecycle would have held while staging, not a measurement.
"""
import argparse
import os
import sys
import tempfile
from typing import Any, Dict, Optional

from dagon import Workflow
from dagon.task import DagonTask, TaskType

from mock_scheduler import mock_sbatch, submission_for

CORES = 200


def local_config(scratch: str) -> dict:
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
        "dagon_service": {"use": "False"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }


def build_workflow(scratch: str, pre_stage: bool, cores: int = CORES, partition: Optional[str] = None,
                   remote: Optional[Dict[str, Any]] = None, name: str = "Coastal-Forecast") -> Workflow:
    """Build the coastal-forecast workflow.

    *remote* holds ``ip``, ``ssh_username``, ``keypath`` and ``ssh_port`` for
    RemoteSlurm tasks; *scratch* is then a path on the remote login host.
    """
    workflow = Workflow(name, config=local_config(scratch), pre_stage=pre_stage)
    site: Dict[str, Any] = dict(remote or {})
    if partition:
        site["partition"] = partition
    forcing = DagonTask(
        TaskType.SLURM, "forcing",
        "mkdir -p forcing; for h in $(seq 0 23); do "
        "seq 1 500 | awk -v h=$h '{printf \"%d %d %.4f\\n\", h, $1, 0.3*sin(($1+h)/40.0)}' "
        "> forcing/hour_$h.txt; done",
        ntasks=1, **site)
    bathymetry = DagonTask(TaskType.SLURM, "bathymetry",
                           "seq 1 500 | awk '{printf \"%d %.1f\\n\", $1, -5-($1 % 37)}' > bathymetry.txt",
                           ntasks=1, **site)
    simulate = DagonTask(
        TaskType.SLURM, "simulate",
        "cat workflow:///forcing/forcing/hour_*.txt | "
        "awk 'NR==FNR {depth[$1]=$2; next} {level[$2]+=$3} END {for (c in level) "
        "printf \"%d %.4f\\n\", c, level[c]/24.0*(1-depth[c]/100.0)}' "
        "workflow:///bathymetry/bathymetry.txt - | sort -n > sea_level.txt",
        ntasks=cores, **site)
    analyse = DagonTask(TaskType.SLURM, "analyse",
                        "sort -k2 -g workflow:///simulate/sea_level.txt | tail -n 5 > extremes.txt",
                        ntasks=1, pre_stage=False, **site)
    for task in (forcing, bathymetry, simulate, analyse):
        workflow.add_task(task)
    workflow.make_dependencies()
    return workflow


def run_mode(scratch: str, pre_stage: bool) -> dict:
    label = "pre-staged" if pre_stage else "legacy"
    directory = os.path.join(scratch, label)
    os.makedirs(directory, exist_ok=True)
    log = os.path.join(directory, "sbatch-log.jsonl")
    workflow = build_workflow(directory, pre_stage)
    with mock_sbatch(log):
        workflow.run()
    tasks = {task.name: task for task in workflow.tasks}
    failed = [name for name, task in tasks.items() if task.status.name != "FINISHED"]
    with open(os.path.join(tasks["analyse"].working_dir, "extremes.txt")) as stream:
        extremes = stream.read()
    metadata = tasks["simulate"].get_execution_metadata().get("pre_stage", {})
    return {"label": label, "failed": failed, "extremes": extremes,
            "simulate": submission_for(log, "simulate"), "analyse": submission_for(log, "analyse"),
            "metadata": metadata}


def describe(result: dict) -> None:
    print("== %s lifecycle" % result["label"])
    for name in ("simulate", "analyse"):
        record = result[name]
        print("   %-8s at sbatch: stage-in marker present=%s, inputs on scratch=%s"
              % (name, record["marker_present"], record["inputs_populated"]))
    if result["metadata"].get("pre_stage_effective"):
        print("   simulate staged %d inputs in %.3f s before submission"
              % (result["metadata"]["inputs"], result["metadata"]["staging_seconds"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", help="scratch directory to keep (default: temporary)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="dagon-prestage-") as temporary:
        scratch = os.path.abspath(args.scratch or temporary)
        legacy = run_mode(scratch, pre_stage=False)
        staged = run_mode(scratch, pre_stage=True)
        for result in (legacy, staged):
            describe(result)
        metadata = staged["metadata"]
        saved = metadata.get("estimated_allocated_core_hours_saved")
        print("Estimated allocated core-hours not held during stage-in (%d cores): %s"
              % (CORES, "%.6f" % saved if saved is not None else "n/a"))
        print("Highest sea levels (identical in both modes):")
        print(staged["extremes"], end="")
        ok = (not legacy["failed"] and not staged["failed"]
              and legacy["extremes"] == staged["extremes"] and len(staged["extremes"].splitlines()) == 5
              # legacy: simulate staged inside the job
              and not legacy["simulate"]["marker_present"] and not legacy["simulate"]["inputs_populated"]
              # enabled: simulate staged and verified before sbatch
              and staged["simulate"]["marker_present"] and staged["simulate"]["inputs_populated"]
              # task-level opt-out keeps the legacy lifecycle
              and not staged["analyse"]["marker_present"] and not staged["analyse"]["inputs_populated"]
              and metadata.get("inputs") == 2 and metadata.get("requested_cores") == CORES)
        print("Verification:", "ok" if ok else "FAILED")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
