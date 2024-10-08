
import json
import time
import os
import threading


"""
Cycle detection
author: J.Armando Barron-lugo
date: 14/10/2023
description: 

    Build of a metaworkflow composed of 3 different workflows with a cycle in their dependencies. 

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
    workflow = Workflow("WF-1")

    # Set the dry
    workflow.set_dry(False)

    # The task a
    taskA = DagonTask(TaskType.BATCH, "A", "$SC:5 ;mkdir output;hostname > output/f1.txt; cat workflow://WF-3/H/output/f1.txt >> output/f1.txt")

    # The task b
    taskB = DagonTask(TaskType.BATCH, "B", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")

    # The task c
    taskC = DagonTask(TaskType.BATCH, "C", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")

    # The task d
    taskD = DagonTask(TaskType.BATCH, "D", "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt")

    #second workflow
    workflow2 = Workflow("WF-2")

    workflow2.set_dry(False)

    # The task E
    taskE = DagonTask(TaskType.BATCH, "E", "mkdir output;hostname > output/f1.txt")

    # The task f
    taskF = DagonTask(TaskType.BATCH, "F", "echo $RANDOM > f2.txt; cat workflow://WF-1/A/output/f1.txt >> f2.txt; cat workflow:///E/output/f1.txt >> f2.txt")

    # The task g
    taskG = DagonTask(TaskType.BATCH, "G", "cat workflow:///F/f2.txt >> f3.txt; cat workflow://WF-1/C/f2.txt >> f3.txt")

    #third workflow
    workflow3 = Workflow("WF-3")

    workflow3.set_dry(False)

    # The task h
    taskH = DagonTask(TaskType.BATCH, "H", "mkdir output;hostname > output/f1.txt; cat workflow://WF-2/G/f3.txt >> output/f1.txt")

    # The task i
    taskI = DagonTask(TaskType.BATCH, "I", "echo $RANDOM > f2.txt; cat workflow:///H/output/f1.txt >> f2.txt")

    # The task j
    taskJ = DagonTask(TaskType.BATCH, "J", "echo $RANDOM > f3.txt; cat workflow:///I/f2.txt >> f3.txt")

    # add tasks to the workflow 1
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)

    # add tasks to the workflow 2
    workflow2.add_task(taskE)
    workflow2.add_task(taskF)
    workflow2.add_task(taskG)

    # add tasks to the workflow 2
    workflow3.add_task(taskH)
    workflow3.add_task(taskI)
    workflow3.add_task(taskJ)


    #list of the workflows
    #WF =[workflow,workflow2,workflow3]

    metaworkflow=DAG_TPS("Transversal-Cycle-Demo")
    metaworkflow.add_workflow(workflow)
    metaworkflow.add_workflow(workflow2)
    metaworkflow.add_workflow(workflow3)

    metaworkflow.make_dependencies()

    jsonWorkflow = metaworkflow.as_json(json_format="wf") 
    with open('.metaworkflow-with-cycles.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)

    # run the workflow
    metaworkflow.run()

    