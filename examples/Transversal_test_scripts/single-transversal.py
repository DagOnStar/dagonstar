import json
import os.path
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from dagon.docker_task import DockerTask
from dagon import Status
import sys
import time
if __name__ == '__main__':

    #command_dir = "/home/robot/Escritorio/Projects/Crawlers/Merra_Master/"
    command_dir = sys.argv[1]
    init_date = sys.argv[2]
    end_date = sys.argv[3]
    id_test = str(sys.argv[4]) #also iterations
    # Create the orchestration workflow
    if not os.path.exists("../logs/"):
        os.makedirs("../logs/")

    logfile= open("../logs/LOG_single_test_No-<"+id_test+".txt", "a+")
    logfile.write("building,validation,runtime\n")

    for i in range(0,int(id_test)):
        workflow = Workflow("Merra-Docker")

        # The task a
        start_building = time.time()
        taskA = DagonTask(TaskType.BATCH, "Adquisition", "cp -r "+command_dir+"/launcher/lib $PWD;\
            java -jar "+command_dir+"launcher/launcher.jar 1 1 "+init_date+" "+end_date+" $PWD/ aq_"+id_test)
        # The task b
        taskB = DockerTask("Interpolation", "python /home/Interpolacion.py -i workflow:///Adquisition/metadata/FilesNc -w 1 ", image="module_interpolation:v1")
        
        taskC = DockerTask("Uploader", "python /home/upload.py -i workflow:///Interpolation/output -w 1 ", image="module_todb:v1")

        # add tasks to the workflow
        workflow.add_task(taskA)
        workflow.add_task(taskB)
        workflow.add_task(taskC)

        workflow.make_dependencies()
        end_building = time.time()
        start_validation= time.time()
        workflow.Validate_WF()
        end_validation = time.time()

        jsonWorkflow = workflow.as_json()
        with open('Single-demo-docker.json', 'w') as outfile:
            stringWorkflow = json.dumps(jsonWorkflow, sort_keys=True, indent=2)
            outfile.write(stringWorkflow)

        # run the workflow
        start_exe = time.time()
        workflow.run()
        end_exe = time.time()
        logfile.write("%s,%s,%s\n" %(end_building-start_building, end_validation-start_validation, end_exe-start_exe))
        print("------------------")
    logfile.close()
