
import json
import time
import os
import threading


from dagon import Workflow
from dagon.dag_tps import DAG_TPS
from dagon.task import DagonTask, TaskType

import logging

logging.debug('This message should go to the log file')
logging.info('So should this')
logging.warning('And this, too')

# Check if this is the main
if __name__ == '__main__':

    config = {
        "scratch_dir_base": "/tmp/test6",
        "remove_dir": False
    }

    # Create the orchestration workflow
    workflow = Workflow("DataFlow-Demo-Server")

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

#second workflow
    workflow2 = Workflow("DataFlow-transversal")
    workflow2.set_dry(False)
    # The task E
    taskE = DagonTask(TaskType.BATCH, "E", "mkdir output;hostname > output/f1.txt")

    # The task f
    taskF = DagonTask(TaskType.BATCH, "F", "echo $RANDOM > f2.txt; cat workflow://DataFlow-Demo-Server/A/output/f1.txt >> f2.txt; cat workflow:///E/output/f1.txt >> f2.txt")

    # The task g
    taskG = DagonTask(TaskType.BATCH, "G", "cat workflow:///F/f2.txt >> f3.txt; cat workflow://DataFlow-Demo-Server/C/f2.txt >> f3.txt")

    # add tasks to the workflow 1
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)

    # add tasks to the workflow 2
    workflow2.add_task(taskE)
    workflow2.add_task(taskF)
    workflow2.add_task(taskG)

#list of the workflows
    #WF =[workflow,workflow2]
    metaworkflow=DAG_TPS("NewDAG")
    metaworkflow.add_workflow(workflow)
    metaworkflow.add_workflow(workflow2)
    metaworkflow.make_dependencies()

    jsonWorkflow = metaworkflow.as_json(json_format="mw") 
    with open('./jsons/MW-demo2.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)

    # run the workflow
    metaworkflow.run()

    

    # if workflow.get_dry() is False:
    #     # set the result filename
    #     result_filename = taskD.get_scratch_dir() + "/f3.txt"
    #     while not os.path.exists(result_filename):
    #         time.sleep(1)

    #     # get the results
    #     with open(result_filename, "r") as infile:
    #         result = infile.readlines()
    #         print result
