"""Lesson 28: compose workflows with DAG_TPS and named workflow:// references across workflows."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import tempfile
from pathlib import Path

from dagon.dag_tps import DAG_TPS
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import config, workflow

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-28-") as scratch:
    meta = DAG_TPS("Campaign28", config=config(scratch))
    acquisition = workflow("Acquisition", scratch)
    analysis = workflow("Analysis", scratch)
    collect = DagonTask(TaskType.BATCH, "collect", "mkdir -p out; echo 3.2 > out/wind.txt")
    analyse = DagonTask(TaskType.BATCH, "analyse", "cat workflow://Acquisition/collect/out/wind.txt > wind.txt")
    acquisition.add_task(collect)
    analysis.add_task(analyse)
    meta.add_workflow(acquisition)
    meta.add_workflow(analysis)
    meta.make_dependencies()
    assert collect in analyse.prevs and collect.reference_count == 1
    meta.run()
    assert Path(analyse.working_dir, "wind.txt").read_text().strip() == "3.2"

    offline = workflow("Offline", scratch)
    offline.add_task(DagonTask(TaskType.BATCH, "orphan", "cat workflow://Missing/task/out.txt"))
    try:
        offline.make_dependencies()
    except ConnectionError as error:
        message = str(error)
    else:
        raise AssertionError("an unresolved cross-workflow reference must fail")
print("cross-workflow edge Acquisition.collect -> Analysis.analyse resolved and executed")
print("unresolvable reference without the optional service:", message)
