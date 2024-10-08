
import json
import time
import os
import threading

"""
Asynchronous dependency
author: J.Armando Barron-lugo
date: 14/10/2023
description: 

    Example of an asynchronous traversal dependency. This script describes a generic workflow in Dagon. The asynchronous dependency is located in WF2-traversal-async.py
"""



from dagon import Workflow
from dagon.dag_tps import DAG_TPS
from dagon.task import DagonTask, TaskType

# Check if this is the main
if __name__ == '__main__':

    config = {
        "scratch_dir_base": "/tmp/test6",
        "remove_dir": False
    }

    # Create the orchestration workflow
    workflow = Workflow("wf1-transversal-demo")

    # Set the dry
    workflow.set_dry(False)

    # The task a
    taskA = DagonTask(TaskType.BATCH, "A", "mkdir output;hostname > output/f1.txt")

    # The task b
    taskB = DagonTask(TaskType.BATCH, "B", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt;sleep 30")

    # The task c
    taskC = DagonTask(TaskType.BATCH, "C", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt;sleep 30")

    # The task d
    taskD = DagonTask(TaskType.BATCH, "D", "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt;sleep 30")

    # add tasks to the workflow 1
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)

    #list of the workflows
    workflow.make_dependencies()

    jsonWorkflow = workflow.as_json() 
    with open('wf1-transversal-demo.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)

    # run the workflow
    workflow.run()

    

    # if workflow.get_dry() is False:
    #     # set the result filename
    #     result_filename = taskD.get_scratch_dir() + "/f3.txt"
    #     while not os.path.exists(result_filename):
    #         time.sleep(1)

    #     # get the results
    #     with open(result_filename, "r") as infile:
    #         result = infile.readlines()
    #         print result
