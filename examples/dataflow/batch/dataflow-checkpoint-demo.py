
import json
import time
import os

from dagon import Workflow
from dagon.task import DagonTask, TaskType


# Check if this is the main
if __name__ == '__main__':
    # Create the orchestration workflow
    workflow = Workflow("DataFlow-Checkpoint-Demo", checkpoint_file="last_run.json")

    # Set the dry
    workflow.set_dry(False)

    # The task a
    taskA = DagonTask(TaskType.BATCH, "A", "mkdir output;hostname > output/f1.txt")

    # The task b
    taskB = DagonTask(TaskType.BATCH, "B", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")

    # The task c
    taskC = DagonTask(TaskType.BATCH, "C", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")

    # The task d
    taskD = DagonTask(TaskType.BATCH, "D", "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt")

    # Explicit checkpoint
    taskCheckpoint = DagonTask(TaskType.CHECKPOINT, "Checkpoint_1", "workflow:///D/f3.txt")

    # The task e
    taskE = DagonTask(TaskType.BATCH, "E", "mkdir output;cp workflow:///Checkpoint_1/DataFlow-Checkpoint-Demo/D/f3.txt output/f4.txt")

    # The task f
    taskF = DagonTask(TaskType.BATCH, "F", "echo $RANDOM > f5.txt; cat workflow:///E/output/f4.txt >> f5.txt")

    # The task g
    taskG = DagonTask(TaskType.BATCH, "G", "echo $RANDOM > f6.txt; cat workflow:///E/output/f4.txt >> f6.txt")

    # The task h
    taskH = DagonTask(TaskType.BATCH, "H", "cat workflow:///F/f5.txt >> f7.txt; cat workflow:///G/f6.txt >> f7.txt")

    # add tasks to the workflow
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)
    workflow.add_task(taskCheckpoint)
    workflow.add_task(taskE)
    workflow.add_task(taskF)
    workflow.add_task(taskG)
    workflow.add_task(taskH)

    workflow.make_dependencies()

    # run the workflow
    workflow.run("last_run.json")

    if workflow.get_dry() is False:
        # set the result filename
        result_filename = taskH.get_scratch_dir() + "/f7.txt"
        while not os.path.exists(result_filename):
            time.sleep(1)

        # get the results
        with open(result_filename, "r") as infile:
            result = infile.readlines()
            print(result)
