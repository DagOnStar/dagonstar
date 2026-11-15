"""Lesson 32 capstone: every registered TaskType in one portable, checkpointed, FAIR-recorded graph,
an accepted agentic step, a CWL export, and a feature checklist.  No live adapter is ever invoked."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "agentic"))
import json
import tempfile
from pathlib import Path
from unittest import mock

from agentic_common import write_ini  # noqa: E402
from dagon import Status, Workflow  # noqa: E402
from dagon.config import read_config  # noqa: E402
from dagon.fair import Agent, FairProfile  # noqa: E402
from dagon.remote import CloudTask  # noqa: E402
from dagon.task import DagonTask, TaskType  # noqa: E402

REF = "workflow:///producer/output/value.txt"
OBSERVATIONS = "workflow:///table/outputs/observations.json"


def live_call(*args, **kwargs):
    raise AssertionError("a live adapter or network call was attempted")


def all_tasks():
    with mock.patch("dagon.docker_task.docker.from_env", return_value=None), \
            mock.patch("dagon.kubernetes_task.config.load_kube_config"), \
            mock.patch("dagon.kubernetes_task.client.CoreV1Api"), \
            mock.patch.object(CloudTask, "connect", return_value=None, create=True):
        return {
            TaskType.CHECKPOINT: DagonTask(TaskType.CHECKPOINT, "checkpoint", REF),
            TaskType.BATCH: DagonTask(TaskType.BATCH, "batch", "cat " + REF),
            TaskType.SLURM: DagonTask(TaskType.SLURM, "slurm", "cat " + REF),
            TaskType.CLOUD: DagonTask(TaskType.CLOUD, "cloud", "cat " + REF, provider="mock",
                                      ssh_username="user", key_options={"key_path": "/tmp/key"},
                                      instance_id="instance"),
            TaskType.DOCKER: DagonTask(TaskType.DOCKER, "docker", "cat " + REF, image="busybox", pull=False),
            TaskType.KUBERNETES: DagonTask(TaskType.KUBERNETES, "kubernetes", "cat " + REF, image="busybox"),
            TaskType.APPTAINER: DagonTask(TaskType.APPTAINER, "apptainer", "cat " + REF, image="busybox.sif"),
            TaskType.NOMAD: DagonTask(TaskType.NOMAD, "nomad", "cat " + REF, image="busybox"),
            TaskType.LLM: DagonTask(TaskType.LLM, "llm", {"messages": [{"content": REF}]}, provider="mock"),
            TaskType.NATIVE: DagonTask(TaskType.NATIVE, "native",
                                       "examples.tutorial.common.native_functions:count_records",
                                       inputs={"input_file": "workflow:///agentic/outputs/result.json"},
                                       outputs={"output_file": "count.json"}),
            TaskType.WEB: DagonTask(TaskType.WEB, "web", {"method": "POST", "url": "http://example.invalid",
                                                          "body": {"text": REF}}),
            TaskType.FAAS: DagonTask(TaskType.FAAS, "faas", provider="mock", function="echo",
                                     inputs={"document": REF}),
            TaskType.IOT: DagonTask(TaskType.IOT, "iot", operation="observe", provider="mock",
                                    request={"events": [{"source": REF}]}, completion={"mode": "first_event"},
                                    outputs={"observations": "outputs/observations.json"}),
            TaskType.AGENTIC: DagonTask(TaskType.AGENTIC, "agentic", agent="quality-local",
                                        specification={"objective": "Deduplicate the observation table",
                                                       "output_schema": {"type": "object",
                                                                         "required": ["observations"]}},
                                        inputs={"source": OBSERVATIONS},
                                        requirements=[{"id": "complete", "evaluator": "record_coverage",
                                                       "expected": {"count": 4}, "mandatory": True}]),
        }


TABLE = json.dumps({"observations": [{"id": n, "station": "SYN001"} for n in (1, 2, 2, 3, 4)]})

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-32-") as scratch:
    checkpoint = str(Path(scratch, "checkpoint.json"))
    fair_dir = str(Path(scratch, "fair"))
    with mock.patch("dagon.agentic.providers.OpenAICompatibleAdapter.propose", side_effect=live_call), \
            mock.patch("urllib.request.urlopen", side_effect=live_call):
        wf = Workflow("Capstone32", config=read_config(str(write_ini(scratch))), portable_emulation=True,
                      checkpoint_file=checkpoint)
        wf.enable_fair(FairProfile(title="Capstone", description="All task types, portable emulation.",
                                   creators=[Agent(name="Course participant")], license="CC-BY-4.0",
                                   output_dir=fair_dir))
        wf.add_task(DagonTask(TaskType.BATCH, "producer", "mkdir -p output; printf '1\\n2\\n' > output/value.txt"))
        wf.add_task(DagonTask(TaskType.BATCH, "table",
                              "mkdir -p outputs; printf '%s' '" + TABLE + "' > outputs/observations.json"))
        tasks = all_tasks()
        assert set(tasks) == set(TaskType), "the capstone must include every registered TaskType"
        for task in tasks.values():
            wf.add_task(task)
        wf.run()
    failed = [task.name for task in wf.tasks if task.status is not Status.FINISHED]
    assert not failed, failed
    evaluation = json.loads(Path(tasks[TaskType.AGENTIC].working_dir, "outputs", "evaluation.json").read_text())
    assert evaluation["accepted"] and evaluation["execution"]["portable_emulation"] is True
    count = json.loads(Path(tasks[TaskType.NATIVE].working_dir, "outputs", "count.json").read_text())
    assert count == {"count": 4}
    run = json.loads(Path(fair_dir, "run.json").read_text(encoding="utf-8"))
    assert set(run["tasks"]) == {task.name for task in wf.tasks}
    assert Path(checkpoint).is_file()
    cwl = Path(scratch, "capstone.cwl")
    wf.saveAsCWL(str(cwl))
    document = json.loads(cwl.read_text(encoding="utf-8"))
    assert {task.name for task in wf.tasks} <= set(document["steps"]) and scratch not in cwl.read_text()

checklist = {"task types": len(TaskType), "agent accepted": True, "FAIR run recorded": True,
             "checkpoint written": True, "CWL exported": True, "live adapters invoked": 0}
print(json.dumps(checklist, sort_keys=True))
