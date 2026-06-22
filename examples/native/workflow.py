"""Run with: python3 workflow.py (from this directory)."""

from dagon import Workflow
from dagon.task import DagonTask, TaskType

workflow = Workflow("native-example")
workflow.add_task(DagonTask(TaskType.BATCH, "produce", "mkdir -p data; printf '2\\n4\\n' > data/input.txt"))
workflow.add_task(DagonTask(TaskType.NATIVE, "transform", "native_functions:transform", inputs={"input_file": "workflow:///produce/data/input.txt", "scale": 1.5}, outputs={"output_file": "scaled.txt"}))
workflow.add_task(DagonTask(TaskType.BATCH, "consume", "cat workflow:///transform/outputs/scaled.txt"))
workflow.run()
