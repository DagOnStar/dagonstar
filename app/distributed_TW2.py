import json
import os.path
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from dagon.docker_task import DockerTask
from dagon import Status
import sys
import time

def cleanContainers():
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_todb:v1)')
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_interpolation:v1)')


if __name__ == '__main__':

    # -------------- DISTRIBUTED TRANSVERSAL WORKER 1 ------------------ #
    #command_dir = "/home/robot/Escritorio/Projects/Crawlers/Merra_Master/"
    iterations = str(sys.argv[1]) #also iterations
    # Create the orchestration workflow
    if not os.path.exists("../logs/"):
        os.makedirs("../logs/")

    logfile= open("../logs/TDW1-"+iterations+".txt", "a+")
    logfile.write("building,validation,runtime,idle_time\n")

    for i in range(1,int(iterations)+1):
        start_idle = time.time()
        while(True):
            try:
                workflow = Workflow("TDW2-"+str(i))

                # The tasks
                start_building = time.time()
                taskB = DockerTask("Interpolation", "python /home/Interpolacion.py -i workflow://TDW1-"+str(i)+"/Adquisition/metadata/FilesNc -w 1 ", image="module_interpolation:v1")
                taskC = DockerTask("Uploader", "python /home/upload.py -i workflow:///Interpolation/output -w 1 ", image="module_todb:v1")
                # add tasks to the workflow
                workflow.add_task(taskB)
                workflow.add_task(taskC)
                workflow.make_dependencies()
                end_building = time.time()

                start_validation= time.time()
                workflow.Validate_WF()
                end_validation = time.time()
                break
            except Exception as exe:
                time.sleep(1)#if the transversal workflow does not exist
        
        end_idle = time.time()
        # run the workflow
        start_exe = time.time()
        workflow.run()
        end_exe = time.time()

        logfile.write("%s,%s,%s,%s\n" %(end_building-start_building, end_validation-start_validation, end_exe-start_exe, end_idle-start_idle))
        #cleanContainers()
    logfile.close()
