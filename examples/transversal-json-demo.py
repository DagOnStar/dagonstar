
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

    # Create the orchestration workflow
    filename = "./jsons/MW-demo.json"
    with open(filename, 'r') as f:
        datastore = json.load(f)

    workflow = Workflow("NEW-DAGT_PS",jsonload=datastore)
    # Set the dry
    workflow.set_dry(False)
    #load json to a workflow
    
    workflow.make_dependencies()

    jsonWorkflow = workflow.as_json() 
    with open('./jsons/NEW-Meta-workflow.json', 'w') as outfile:
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
