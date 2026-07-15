"""Export a credential-free FaaS workflow as JSON and CWL."""
import json
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("FaaS-Export", config={"batch": {"remove_dir": False, "scratch_dir_base": "/tmp"}})
workflow.add_task(DagonTask(TaskType.FAAS, "invoke", provider="mock", function="echo",
                            inputs={"value": 4}))
Path("faas-workflow.json").write_text(json.dumps(workflow.as_json(), indent=2), encoding="utf-8")
workflow.saveAsCWL("faas-workflow.cwl")
