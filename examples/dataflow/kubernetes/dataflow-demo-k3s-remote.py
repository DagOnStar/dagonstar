#!/usr/bin/env python3
"""
Simple test for RemoteKubernetesTask - Kubernetes tasks on remote cluster via SSH
"""

import json
import configparser
import sys
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType

if __name__ == '__main__':
    # Read SSH configuration from dagon.ini
    config = configparser.ConfigParser()
    config.read('dagon.ini')
    REMOTE_IP = config.get('ssh', 'remote_ip')
    SSH_USER = config.get('ssh', 'ssh_user')
    SSH_PORT = config.getint('ssh', 'ssh_port')

    # Create workflow
    workflow = Workflow("DataFlow-Demo-K3S-Remote")

    # Task A: Create directory and write hostname
    taskA = DagonTask(
        TaskType.KUBERNETES,
        "A",
        "mkdir output; hostname > output/f1.txt",
        image="ubuntu:20.04",
        ip=REMOTE_IP,
        ssh_username=SSH_USER,
        ssh_port=SSH_PORT
    )

    # Task B: Generate random number and read from A
    taskB = DagonTask(
        TaskType.KUBERNETES,
        "B",
        "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt",
        image="ubuntu:20.04",
        ip=REMOTE_IP,
        ssh_username=SSH_USER,
        ssh_port=SSH_PORT
    )

    # Task C: Generate random number and read from A
    taskC = DagonTask(
        TaskType.KUBERNETES,
        "C",
        "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt",
        image="ubuntu:20.04",
        ip=REMOTE_IP,
        ssh_username=SSH_USER,
        ssh_port=SSH_PORT
    )

    # Task D: Combine outputs from B and C and display the result
    taskD = DagonTask(
        TaskType.KUBERNETES,
        "D",
        "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt; echo '=== Final contents of f3.txt ==='; cat f3.txt",
        image="ubuntu:20.04",
        ip=REMOTE_IP,
        ssh_username=SSH_USER,
        ssh_port=SSH_PORT
    )

    # Add tasks to workflow
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)

    # Set dependencies
    workflow.make_dependencies()

    # Save workflow as JSON
    jsonWorkflow = workflow.as_json()
    with open('dataflow-demo-k3s-remote.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)
    print("✓ Workflow saved to: dataflow-demo-k3s-remote.json")

    # Run workflow
    print("\n" + "="*60)
    print("Starting Remote Kubernetes Workflow")
    print("="*60 + "\n")
    workflow.run()
    print("\n" + "="*60)
    print("Workflow Completed Successfully!")
    print("="*60 + "\n")

    # Allow time for cleanup operations to complete
    time.sleep(2)

    # Explicitly terminate
    sys.exit(0)
