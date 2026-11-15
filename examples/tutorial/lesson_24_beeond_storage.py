"""Lesson 24: BeeOND configuration, scheduler fragments, and persistence under portable emulation."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from pathlib import Path

from dagon import Workflow
from dagon.batch import Slurm
from dagon.beeond import BeeONDConfig
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import config

defaults = BeeONDConfig()
assert defaults.scope == "task" and defaults.persist and defaults.comment == "beeond-fs"
rejected = []
for options in ({"scope": "cluster"}, {"mount_template": "/mnt/$(id)"}, {"volume": "a b"}):
    try:
        BeeONDConfig(**options)
    except ValueError:
        rejected.append(sorted(options)[0])
assert rejected == ["scope", "mount_template", "volume"], rejected

command = Slurm("Sim", "run", comment="beeond-fs", nodes=2, nodelist="wn[01-02]", beeond="task",
                working_dir="/scratch/w").generate_command("launcher.sh")
assert command.count("--comment=beeond-fs") == 1, command

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-24-") as scratch:
    wf = Workflow("BeeOND24", config=config(scratch), portable_emulation=True)
    wf.create_beeond_volume("shared", time="00:10:00")
    write = DagonTask(TaskType.SLURM, "write", 'echo persisted > "$DAGON_BEEOND/result.txt"', beeond="task")
    read = DagonTask(TaskType.BATCH, "read", "cp workflow:///write/beeond/result.txt copy.txt")
    stage = DagonTask(TaskType.SLURM, "stage", 'echo shared > "$DAGON_BEEOND/input.txt"',
                      beeond="workflow:shared")
    use = DagonTask(TaskType.SLURM, "use", 'cat "$DAGON_BEEOND/input.txt" > used.txt',
                    beeond="workflow:shared")
    for task in (write, read, stage, use):
        wf.add_task(task)
    use.add_dependency_to(stage)
    wf.run()
    assert Path(read.working_dir, "copy.txt").read_text().strip() == "persisted"
    assert Path(use.working_dir, "used.txt").read_text().strip() == "shared"
print("invalid options rejected:", rejected)
print("task volume persisted and consumed; workflow volume shared (portable emulation, no scheduler)")
