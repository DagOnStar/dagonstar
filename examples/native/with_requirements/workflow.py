"""Run a native task whose function imports NumPy from requirements.txt."""

from dagon import Workflow
from dagon.task import DagonTask, TaskType


workflow = Workflow("native-numpy")
workflow.add_task(DagonTask(
    TaskType.BATCH,
    "produce",
    "mkdir -p data; printf '1.0\\n2.5\\n4.0\\n' > data/measurements.txt",
))
workflow.add_task(DagonTask(
    TaskType.NATIVE,
    "summarize",
    "statistics_functions:summarize_measurements",
    inputs={"input_file": "workflow:///produce/data/measurements.txt"},
    outputs={"output_file": "summary.json"},
))
workflow.run()
