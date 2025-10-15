"""
HiPES 2025 Tutorial - Workflow Demo
-----------------------------------

Credits:
- Developed for the HiPES 2025 Tutorial Session (Euro-Par 2025)
- Example workflow orchestrated with DagonStar
- Developed by Gennaro Mellone, Dario Caramiello, Raffaele Montella - High Performance Scientific Computing Lab (HPSC)
    University of Napoli "Parthenope".

This script demonstrates how to orchestrate a simple workflow:
1) Task A: Generates input parameters (toy example).
2) Task B: Runs a PyGLOBO forecasting job inside a Docker container.
3) Task C: Converts the NetCDF output into a PNG image.

The workflow is configured using `dagon.ini`.
"""

from dagon import Workflow
from dagon.task import DagonTask, TaskType

# Main entry point
if __name__ == '__main__':    
    # Create the orchestration workflow object
    # - "HiPES2025-Workflow-Demo" is the workflow name
    # - configuration options are loaded from dagon.ini
    workflow = Workflow("HiPES2025-Workflow-Demo", config_file="../dagon.ini")

    # --- Task A: Generate configuration data ---
    # In this task we are going to generate configuration data useful for the next task.
    # We will set "procx" and "procx" for setting the right number of cores required by PyGlobo, and "date"
    # a date to forecast.
    taskA = DagonTask(TaskType.BATCH, "A", 
                      " echo 2 > procx.txt; \
                        echo 3 > procy.txt; \
                        echo 2021-11-17 > date.txt; \
                        echo Data created!" 
                      )

    # Add tasks to the workflow definition
    workflow.add_task(taskA)

    # Let DAGonStar automatically resolve dependencies between tasks
    workflow.make_dependencies()

    # Run the workflow: tasks are executed respecting their dependencies
    workflow.run()

