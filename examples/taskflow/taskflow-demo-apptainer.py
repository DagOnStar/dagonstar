#!/usr/bin/env python3
"""
Taskflow demo using ApptainerTask
"""
import json
import os.path
import sys
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType

if __name__ == '__main__':
    print("Starting Taskflow demo with Apptainer...")
    
    # Create the orchestration workflow
    workflow = Workflow("Taskflow-Demo-Apptainer")
    
    # Create tasks equivalent to the Kubernetes demo using Ubuntu
    taskA = DagonTask(TaskType.APPTAINER, "Tokyo", 
                     "/bin/hostname && echo 'Task Tokyo completed'",
                     image="docker://ubuntu:20.04",
                     overlay_size="256")
    
    taskB = DagonTask(TaskType.APPTAINER, "Berlin", 
                     "/bin/date && echo 'Task Berlin completed'",
                     image="docker://ubuntu:20.04",
                     overlay_size="256")
    
    taskC = DagonTask(TaskType.APPTAINER, "Nairobi", 
                     "/usr/bin/uptime && echo 'Task Nairobi completed'",
                     image="docker://ubuntu:20.04",
                     overlay_size="256")
    
    taskD = DagonTask(TaskType.APPTAINER, "Moscow", 
                     "/bin/uname -a && echo 'Task Moscow completed'",
                     image="docker://ubuntu:20.04",
                     overlay_size="256")
    
    # Add tasks to workflow
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)
    
    # Set dependencies
    taskB.add_dependency_to(taskA)
    taskC.add_dependency_to(taskA)
    taskD.add_dependency_to(taskB)
    taskD.add_dependency_to(taskC)
    
    # Save the workflow as JSON
    jsonWorkflow = workflow.as_json()
    with open('taskflow-demo-apptainer.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)
    
    print("Executing workflow with Apptainer...")
    
    # Execute the workflow
    start_time = time.time()
    workflow.run()
    end_time = time.time()
    
    print(f"Workflow completed successfully in {end_time - start_time:.1f} seconds")
    
    # Allow time for cleanup operations to complete
    time.sleep(3)
    
    # Exit explicitly
    sys.exit(0)
