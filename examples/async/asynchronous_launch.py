"""Run a local workflow without blocking the calling thread."""

from dagon import Workflow
from dagon.task import DagonTask, TaskType


def show_task_event(task):
    print("%s: %s" % (task.name, task.status.name))


if __name__ == "__main__":
    workflow = Workflow("AsynchronousLaunch")
    workflow.add_task(DagonTask(TaskType.BATCH, "prepare", "echo prepared"))

    workflow.on_workflow_start += lambda wf: print("Workflow started:", wf.name)
    workflow.on_task_start += show_task_event
    workflow.on_task_end += show_task_event
    workflow.on_workflow_end += lambda wf: print("Workflow finished:", wf.name)

    workflow.launch()
    print("The workflow is running while this line is printed.")
    workflow.wait()
