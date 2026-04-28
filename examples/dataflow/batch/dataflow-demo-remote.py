from dagon import Workflow
from dagon import batch
import json
import configparser
import time
import os

# Check if this is the main
from dagon.task import DagonTask, TaskType

if __name__ == '__main__':
    # Read SSH configuration from dagon.ini
    config = configparser.ConfigParser()
    config.read('dagon.ini')
    REMOTE_IP = config.get('ssh', 'remote_ip')
    SSH_USER = config.get('ssh', 'ssh_user')
    SSH_PORT = config.getint('ssh', 'ssh_port')

    # Create the orchestration workflow
    workflow = Workflow("DataFlow-Demo-Remote")

    # Set the dry
    workflow.set_dry(False)

    # The task a
    taskA = DagonTask(TaskType.BATCH, "A", "mkdir output;hostname > output/f1.txt", ip=REMOTE_IP, ssh_username=SSH_USER, keypath="")

    # The task b
    taskB = DagonTask(TaskType.BATCH, "B", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt", ip=REMOTE_IP, ssh_username=SSH_USER, keypath="")

    # The task c
    taskC = DagonTask(TaskType.BATCH, "C", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt", ip=REMOTE_IP, ssh_username=SSH_USER, keypath="")

    # The task d
    taskD = DagonTask(TaskType.BATCH, "D", "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt", ip=REMOTE_IP, ssh_username=SSH_USER, keypath="")

    # add tasks to the workflow
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)

    workflow.make_dependencies()

    jsonWorkflow = workflow.as_json()
    with open('dataflow-demo-remote.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)

    # run the workflow
    workflow.run()
