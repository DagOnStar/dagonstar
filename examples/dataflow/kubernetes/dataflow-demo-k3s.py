import json
import os.path
import sys
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType

if __name__ == '__main__':
    # Create the orchestration workflow
    workflow = Workflow("DataFlow-Demo-K8s")
    
    # Task A: creates a directory and saves the hostname to a file
    taskA = DagonTask(TaskType.KUBERNETES, "A",
                      "mkdir output; hostname > output/f1.txt",
                      image="ubuntu:20.04")
    
    # Task B: generates random number and concatenates the result from A
    taskB = DagonTask(TaskType.KUBERNETES, "B",
                      "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt",
                      image="ubuntu:20.04")
    
    # Task C: does the same as B (simulating another branch)
    taskC = DagonTask(TaskType.KUBERNETES, "C",
                      "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt",
                      image="ubuntu:20.04")
    
    # Task D: combines the outputs from B and C and displays the result
    taskD = DagonTask(TaskType.KUBERNETES, "D",
                  "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt; echo '=== Final contents of f3.txt ==='; cat f3.txt",
                  image="ubuntu:20.04")
    
    # Add tasks to the workflow
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)
    
    # Build dependencies automatically
    workflow.make_dependencies()
    
    # Save the workflow as JSON
    jsonWorkflow = workflow.as_json()
    with open('dataflow-demo-k8s.json', 'w') as outfile:
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
        outfile.write(stringWorkflow)
    
    # Run the workflow
    workflow.run()
    print("Workflow completed successfully")
        
    # Allow time for cleanup operations to complete
    time.sleep(2)
    
    # Explicitly terminate
    sys.exit(0)
