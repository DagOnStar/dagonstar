"""Lesson 23: Slurm submission commands, quoting, and job outcomes through a local mock sbatch."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "examples" / "dataflow" / "slurm"))
import tempfile
from pathlib import Path

from mock_scheduler import mock_sbatch, submission_for  # noqa: E402
from dagon.batch import Slurm  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402
from examples.tutorial.common.support import workflow  # noqa: E402

command = Slurm("job name; touch pwned", "echo ok", partition="debug queue", ntasks=4, memory=2048,
                time="01:00:00", working_dir="/scratch/work dir").generate_command("launcher.sh")
assert "'job name; touch pwned'" in command and "'--partition=debug queue'" in command, command
assert "--ntasks=4" in command and "--mem=2048" in command and "--time=01:00:00" in command

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-23-") as scratch:
    log = str(Path(scratch, "sbatch.jsonl"))
    wf = workflow("Slurm23", scratch)
    good = DagonTask(TaskType.SLURM, "simulate", "mkdir -p outputs; echo 42 > outputs/value.txt", ntasks=2)
    bad = DagonTask(TaskType.SLURM, "broken", "sh -c 'exit 3'")
    wf.add_task(good)
    wf.add_task(bad)
    with mock_sbatch(log):
        wf.run()
    assert good.status.name == "FINISHED", good.status
    assert Path(good.working_dir, "outputs", "value.txt").read_text().strip() == "42"
    assert bad.status.name == "FAILED", bad.status
    assert submission_for(log, "simulate") is not None and submission_for(log, "broken") is not None
print("quoted sbatch:", command.split(" -W ")[0][:100])
print("mock scheduler: simulate FINISHED, broken FAILED (exit 3); no real Slurm contacted")
