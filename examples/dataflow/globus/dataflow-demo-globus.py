import json

from dagon import Workflow, DataMover
from dagon.task import DagonTask, TaskType

# Check if this is the main
if __name__ == '__main__':

    # Create the orchestration workflow
    workflow = Workflow("DataFlow-Demo-Globus")

    # Set the data mover as grid ftp
    workflow.set_data_mover(DataMover.GRIDFTP)

    # Set the dry
    workflow.set_dry(False)

    # The task A
    taskA = DagonTask(TaskType.BATCH, "A", "mkdir output;hostname > output/f1.txt",
                      globusendpoint="b706f62a-6c56-11ee-b15f-7d6eafac2be9")

    # The task A
    taskB = DagonTask(TaskType.BATCH, "B", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt",
                      globusendpoint="b706f62a-6c56-11ee-b15f-7d6eafac2be9")

    # Add task A to the workflow
    workflow.add_task(taskA)

    # Add task B to the workflow
    workflow.add_task(taskB)

    # Create a json dump of the workflow
    jsonWorkflow = workflow.as_json()

    # Create a text file to save the json
    with open('dataflow-demo-globus.json', 'w') as outfile:
        # Get a string representation of the json object
        stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)

        # Write the json workflow
        outfile.write(stringWorkflow)

    # Run the workflow
    workflow.run()
