"""Lesson 28: compose workflows with DAG_TPS and named workflow:// references across workflows,
then call a workflow written for another engine as one TaskType.META task."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json
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

# Part 2: a meta-task runs an external workflow (here an engine-free stand-in driven by
# the generic command adapter) and exchanges data only through workflow:// references.
ENGINE = _Path(__file__).resolve().parents[1] / "meta" / "workflows" / "tiny_engine.py"
with tempfile.TemporaryDirectory(prefix="dagon-tutorial-28-meta-") as scratch:
    composite = workflow("Composite", scratch)
    composite.add_task(DagonTask(TaskType.BATCH, "observe", "mkdir -p out; printf 'gust calm gust\\n' > out/log.txt"))
    composite.add_task(DagonTask(TaskType.META, "external", engine="command", workflow=str(ENGINE),
                                 inputs={"text": "workflow:///observe/out/log.txt", "top": 1},
                                 outputs={"counts": {"path": "counts.tsv", "source": "results/counts.tsv"}},
                                 engine_options={"command": [sys.executable, "{workflow}", "{parameters_file}"]}))
    composite.add_task(DagonTask(TaskType.BATCH, "publish", "cp workflow:///external/outputs/counts.tsv top.tsv"))
    composite.run()
    external = composite.find_task_by_name("Composite", "external")
    publish = composite.find_task_by_name("Composite", "publish")
    assert [task.name for task in external.prevs] == ["observe"] and publish.prevs == [external]
    assert Path(publish.working_dir, "top.tsv").read_text().strip() == "gust\t2"
    result = json.loads(Path(external.working_dir, ".dagon", "meta_result.json").read_text())
    assert result["outputs"][0]["path"] == "outputs/counts.tsv" and len(result["workflow"]["sha256"]) == 64
print("meta-task observe -> external (command adapter) -> publish exchanged data through workflow://")
