"""Credential-free BATCH -> FAAS(mock) -> BATCH example."""
from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("FaaS-Mock", config={"batch": {"remove_dir": False, "scratch_dir_base": "/tmp"}})
workflow.add_task(DagonTask(TaskType.BATCH, "prepare",
    "mkdir -p outputs; printf '{\"value\": 4}' > outputs/input.json"))
workflow.add_task(DagonTask(TaskType.FAAS, "invoke", provider="mock", function="double-value",
    inputs={"request": {"document": "workflow:///prepare/outputs/input.json"}},
    outputs={"result": "result.json"},
    provider_options={"mock": {"response": {
        "status": "succeeded", "result": {"processed": 1},
        "outputs": {"result": {"value": 8}}}}}))
workflow.add_task(DagonTask(TaskType.BATCH, "consume",
    "cat workflow:///invoke/outputs/result.json > summary.json"))
workflow.run()
