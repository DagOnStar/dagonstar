"""Scheduler-aware pre-staging (``pre_stage``) support.

Legacy scheduler tasks transfer their ``workflow://`` inputs inside the batch
job, after the scheduler has allocated the requested resources::

    create scratch -> build launcher (staging + command) -> sbatch -> allocation -> stage-in -> compute

With ``pre_stage`` enabled, an eligible scheduler task stages its inputs on
the submission host first and submits a compute-only launcher afterwards::

    create scratch -> context -> stage plan -> stage_in.sh (submission host)
        -> verify -> stage-in marker -> sbatch (compute-only launcher) -> allocation -> compute

This module holds the backend-neutral parts of that lifecycle: value
validation, the structured :class:`PreparedTask` produced by
:meth:`dagon.task.Task.prepare_task`, the stage-in script renderer, the
completion marker, the internal phase model, and the error types that
distinguish staging, submission, and execution failures.  Backends opt in by
setting :attr:`dagon.task.Task.pre_stage_capable` and implementing the
submission-host helpers (see :class:`dagon.batch.Slurm`).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from dagon.shell import quote

#: Version of the pre-staging policy recorded in markers and metadata.
PRE_STAGE_POLICY_VERSION = 1

#: Name of the generated stage-in script inside ``<working_dir>/.dagon``.
STAGE_SCRIPT_NAME = "stage_in.sh"

#: Name of the stage-in completion marker inside ``<working_dir>/.dagon``.
MARKER_NAME = "stage-in-complete.json"

#: File written by the compute launcher when the allocation starts running it.
ALLOCATION_STARTED_NAME = "allocation_started_at"

#: Schema identifier of the completion marker.
MARKER_SCHEMA = "dagonstar.stage-in-marker/1"


class TaskPhase(Enum):
    """Internal pre-staging phase of a task.

    These phases are deliberately separate from :class:`dagon.Status`, whose
    externally visible values are unchanged: a pre-staged task is ``RUNNING``
    while it stages, waits in the queue, and computes, exactly as a legacy
    scheduler task is ``RUNNING`` while its job is queued.

    ``SUBMITTED`` covers queueing *and* execution, because ``sbatch -W`` only
    returns when the job ends.
    """

    PREPARING = "PREPARING"
    STAGING = "STAGING"
    STAGED = "STAGED"
    SUBMITTED = "SUBMITTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PreStageError(Exception):
    """Base class of pre-staging failures; :attr:`phase` names the failed phase."""

    phase = "pre_stage"


class PreStageConfigurationError(PreStageError, ValueError):
    """Pre-staging was requested where it is invalid or unsupported."""

    phase = "configuration"


class StageInFailedError(PreStageError):
    """The stage-in script failed or its success could not be confirmed.

    No scheduler job is submitted when this error is raised.
    """

    phase = "staging"


class SchedulerSubmissionError(PreStageError):
    """The scheduler rejected the compute job (no job identifier was returned)."""

    phase = "submission"


class ScheduledExecutionError(PreStageError):
    """The scheduler accepted the compute job, but the job failed."""

    phase = "execution"


def validate_pre_stage(value: Any, allow_none: bool = True) -> Optional[bool]:
    """Return *value* if it is a valid ``pre_stage`` setting.

    Only the real booleans ``True`` and ``False`` (and ``None`` where
    *allow_none* is set) are accepted.  Strings such as ``"true"`` and integers
    such as ``1`` are rejected so that a typo can never silently change where
    data is staged.

    :raises PreStageConfigurationError: for any other value
    """
    if value is None and allow_none:
        return None
    if type(value) is bool:
        return value
    expected = "True, False, or None" if allow_none else "True or False"
    raise PreStageConfigurationError(
        "pre_stage must be %s, not %r (%s)" % (expected, value, type(value).__name__))


def utc_now() -> str:
    """Return the current UTC time in ISO 8601 form with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def estimated_core_hours_saved(cores: Optional[int], staging_seconds: Optional[float]) -> Optional[float]:
    """Return ``cores * staging_seconds / 3600``.

    This is the number of allocated core-hours that the legacy lifecycle would
    have held while the same stage-in ran inside the allocation.  It is an
    estimate of avoided *allocated* resources, not a measured queue-time saving.
    """
    if cores is None or staging_seconds is None:
        return None
    if cores <= 0 or staging_seconds < 0:
        return None
    return round(cores * staging_seconds / 3600.0, 6)


@dataclass
class StageInput:
    """One resolved ``workflow://`` input of a task."""

    reference: str
    workflow: str
    task: str
    local_path: str
    source: str
    destination: str

    def as_dict(self) -> Dict[str, str]:
        return {"reference": self.reference, "workflow": self.workflow, "task": self.task,
                "local_path": self.local_path, "source": self.source, "destination": self.destination}


# Bash helper used by stage-in scripts to confirm that every staged input
# exists.  The pattern is expanded with IFS set to a newline, so paths with
# spaces survive while globs still expand; an unmatched glob stays literal and
# fails the ``-e`` test, as does a dangling symbolic link.
_VERIFY_FUNCTION = r"""dagon_verify_staged() {
  local dagon_pattern="$1" dagon_item dagon_found=0 dagon_saved_ifs="$IFS"
  IFS='
'
  for dagon_item in $dagon_pattern; do
    IFS="$dagon_saved_ifs"
    if [ ! -e "$dagon_item" ]; then
      echo "DAGonStar: staged input is missing: $dagon_item" >&2
      return 1
    fi
    dagon_found=1
  done
  IFS="$dagon_saved_ifs"
  if [ "$dagon_found" -eq 0 ]; then
    echo "DAGonStar: staged input is missing: $dagon_pattern" >&2
    return 1
  fi
  return 0
}
"""


@dataclass
class PreparedTask:
    """Structured result of preparing a command task for execution.

    The fields are the pieces the legacy launcher has always been made of, so
    :meth:`legacy_launcher` reproduces it exactly, while
    :meth:`stage_in_script` and :meth:`compute_launcher` split the same plan
    into a submission-host stage-in script and an allocation-only launcher
    without parsing generated shell text.
    """

    working_dir: str
    header: str
    prologue: str
    stage_blocks: List[str]
    invoke: str
    resolved_command: str
    inputs: List[StageInput] = field(default_factory=list)

    def _cd(self, quoted: bool) -> str:
        target = quote(self.working_dir) if quoted else self.working_dir
        return ("# Change the current directory to the working directory\n"
                "cd " + target + "\n"
                "if [ $? -ne 0 ]; then code=1; fi \n\n")

    def legacy_launcher(self) -> str:
        """Return the launcher that stages inputs inside the allocation."""
        return (self.header + self._cd(False) + self.prologue + "# Start staging in\n\n"
                + "".join(self.stage_blocks) + self.invoke)

    def compute_launcher(self) -> str:
        """Return the allocation-only launcher used when inputs are pre-staged."""
        marker = self.working_dir + "/.dagon/" + ALLOCATION_STARTED_NAME
        return (self.header + self._cd(True)
                + "# Record when the allocation started running this launcher\n"
                + "date +%s > " + quote(marker) + " 2>/dev/null || true\n\n"
                + self.prologue
                + "# Inputs were staged before scheduler submission (pre_stage=True),\n"
                + "# see .dagon/" + STAGE_SCRIPT_NAME + " and .dagon/" + MARKER_NAME + "\n\n"
                + self.invoke)

    def stage_in_script(self) -> str:
        """Return the stage-in script that runs on the submission host.

        The script removes a stale completion marker first, stops at the first
        failed transfer, verifies every staged input, and exits non-zero on any
        failure.  It never runs the task command or the allocation prologue.
        """
        marker = self.working_dir + "/.dagon/" + MARKER_NAME
        script = ("#! /bin/bash\n"
                  "export PATH=\"$HOME/.local/bin:$PATH\"\n"
                  "# This is the DagOn stage-in script (scheduler-aware pre-staging).\n"
                  "# It runs on the submission host before the scheduler job is requested.\n\n"
                  "code=0\n"
                  "rm -f " + quote(marker) + "\n"
                  "cd " + quote(self.working_dir) + " || exit 1\n\n"
                  + _VERIFY_FUNCTION + "\n")
        if not self.stage_blocks:
            script += "# This task has no workflow:// inputs to stage\n"
        for number, block in enumerate(self.stage_blocks, 1):
            script += block
            script += ("\nif [ \"$code\" -ne 0 ]; then\n"
                       "  echo \"DAGonStar: stage-in transfer %d of %d failed\" >&2\n"
                       "  exit 1\n"
                       "fi\n" % (number, len(self.stage_blocks)))
        if self.inputs:
            script += "\n# Verify every staged input before the scheduler job is requested\n"
            for item in self.inputs:
                script += "dagon_verify_staged " + quote(item.destination) + " || code=1\n"
        script += "\nexit $code\n"
        return script

    def planned_order(self) -> List[str]:
        """Return a human-readable description of the pre-staged lifecycle."""
        steps = ["create scratch " + self.working_dir]
        if self.inputs:
            steps += ["stage-in " + item.reference + " -> " + item.destination for item in self.inputs]
        else:
            steps.append("stage-in: no workflow:// inputs")
        steps += ["verify staged inputs and write .dagon/" + MARKER_NAME,
                  "submit compute-only launcher to the scheduler"]
        return steps


def marker_document(task: Any, prepared: PreparedTask, started_at: str, finished_at: str,
                    staging_seconds: float) -> str:
    """Return the JSON content of the stage-in completion marker.

    The marker is local provenance written only after a verified successful
    stage-in.  It records task identity, the input manifest, the mover, the
    policy version, and timestamps; it never contains credentials.  It is not a
    skip token: a rerun always stages again.
    """
    document = {
        "schema": MARKER_SCHEMA,
        "policy_version": PRE_STAGE_POLICY_VERSION,
        "workflow": task.workflow.name,
        "task": task.name,
        "task_type": type(task).__name__,
        "data_mover": getattr(task.data_mover, "name", str(task.data_mover)),
        "stager_mover": getattr(task.stager_mover, "name", str(task.stager_mover)),
        "inputs": [item.as_dict() for item in prepared.inputs],
        "staging_started_at": started_at,
        "staging_finished_at": finished_at,
        "staging_seconds": round(staging_seconds, 3),
    }
    return json.dumps(document, indent=2, sort_keys=True) + "\n"
