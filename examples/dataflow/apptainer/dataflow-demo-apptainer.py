#!/usr/bin/env python3
"""
DataFlow demo using Apptainer
"""
import json
import os.path
import sys
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType

if __name__ == '__main__':
    print("Starting demo with Apptainer...")
    
    # Create the orchestration workflow
    workflow = Workflow("DataFlow-Demo-Apptainer")
    
    # Task A: creates a directory and saves the hostname to a file
    taskA = DagonTask(TaskType.APPTAINER, "A",
                      "mkdir -p output && hostname > output/f1.txt && echo 'Task A completed' >> output/f1.txt",
                      image="docker://ubuntu:20.04",
                      overlay_size="256")
    
    # Task B: generates random number and concatenates result from A  
    taskB = DagonTask(TaskType.APPTAINER, "B",
                      "echo $RANDOM > f2.txt && cat workflow:///A/output/f1.txt >> f2.txt",
                      image="docker://ubuntu:20.04",
                      overlay_size="256")
    
    # Task C: does the same as B (simulating another branch)
    taskC = DagonTask(TaskType.APPTAINER, "C", 
                      "echo $RANDOM > f2.txt && cat workflow:///A/output/f1.txt >> f2.txt",
                      image="docker://ubuntu:20.04",
                      overlay_size="256")
    
    # Task D: combines outputs from B and C and displays the result
    taskD = DagonTask(TaskType.APPTAINER, "D",
                      "cat workflow:///B/f2.txt >> f3.txt && cat workflow:///C/f2.txt >> f3.txt && echo '=== Final contents of f3.txt ===' && cat f3.txt",
                      image="docker://ubuntu:20.04",
                      overlay_size="256")
    
    # Add tasks to workflow
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)
    
    # Build dependencies automatically
    workflow.make_dependencies()
    
    # Save the workflow as JSON
    jsonWorkflow = workflow.as_json()
    with open('dataflow-demo-apptainer.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)
    
    print("Running workflow with Ubuntu...")
    
    # Execute the workflow
    start_time = time.time()
    workflow.run()
    end_time = time.time()
    
    print(f"Workflow completed successfully in {end_time - start_time:.1f} seconds")
    
    # Allow time for cleanup operations to complete
    time.sleep(3)
    
    # Exit explicitly
    sys.exit(0)
