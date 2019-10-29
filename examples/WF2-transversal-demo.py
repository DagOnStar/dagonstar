
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


#second workflow
    workflow2 = Workflow("wf2-transversal-demo")
    workflow2.set_dry(False)
    # The task E
    taskE = DagonTask(TaskType.BATCH, "E", "mkdir output;hostname > output/f1.txt")

    # The task f
    taskF = DagonTask(TaskType.BATCH, "F", "echo $RANDOM > f2.txt; cat workflow://wf1-transversal-demo/A/output/f1.txt >> f2.txt; cat workflow:///E/output/f1.txt >> f2.txt")

    # The task g
    taskG = DagonTask(TaskType.BATCH, "G", "cat workflow:///F/f2.txt >> f3.txt; cat workflow://wf1-transversal-demo/C/f2.txt >> f3.txt")

    # add tasks to the workflow 2
    workflow2.add_task(taskE)
    workflow2.add_task(taskF)
    workflow2.add_task(taskG)

    workflow2.make_dependencies()

    jsonWorkflow = workflow2.as_json() 
    with open('./jsons/wf2-transversal-demo.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)

    # run the workflow
    workflow2.run()

    

    # if workflow.get_dry() is False:
    #     # set the result filename
    #     result_filename = taskD.get_scratch_dir() + "/f3.txt"
    #     while not os.path.exists(result_filename):
    #         time.sleep(1)

    #     # get the results
    #     with open(result_filename, "r") as infile:
    #         result = infile.readlines()
    #         print result
