import json
import os.path
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from dagon.docker_task import DockerTask
from dagon import Status
from dagon.dag_tps import DAG_TPS
import sys
import time
from datetime import datetime,timedelta
import os 
# Check if this is the main

def cleanContainers():
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_todb:v1)')
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_interpolation:v1)')

if __name__ == '__main__':

    #command_dir = "/home/robot/Escritorio/Projects/Crawlers/Merra_Master/"
    # Create the orchestration workflow
    command_dir = sys.argv[1]
    init_date = sys.argv[2]
    end_date = sys.argv[3]
    no_workflows = int(sys.argv[4]) 
    iterations = 31




    if not os.path.exists("../logs/"):
        os.makedirs("../logs/")

    logfile= open("../logs/LOG_multi_test_No-"+str(no_workflows)+"_workflows.txt", "a+")
    logfile.write("building,validation,runtime\n")

    for i in range(0,iterations):
        init_date = sys.argv[2]
        end_date = sys.argv[3]
        
        idate = datetime.strptime(init_date, '%d-%m-%Y')
        edate = datetime.strptime(end_date, '%d-%m-%Y')
        daterange = (edate-idate)/no_workflows
        start_building = time.time()

        meta_workflow = DAG_TPS("DAGtp_"+str(no_workflows)+"_workflows")
        adquisition_list = "'"
        for i in range(1,no_workflows+1):
            init_date = idate.strftime('%d-%m-%Y')
            end_date = (idate + daterange).strftime('%d-%m-%Y')
            workflow_name = "Merra-Docker_%s" %(i)
            workflow = Workflow(workflow_name)
            adquisition_list += "workflow://%s/Adquisition%s/metadata/FilesNc '" %(workflow_name,i)

            taskA = DagonTask(TaskType.BATCH, "Adquisition"+str(i) , "cp -r "+command_dir+"/launcher/lib $PWD;java -jar "+command_dir+"launcher/launcher.jar 1 1 "+str(init_date)+" "+str(end_date)+" $PWD/ aqui"+str(i))
            # The task b
            taskB = DockerTask("Interpolation"+str(i), "python /home/Interpolacion.py -i "+adquisition_list+" -w 1 ", image="module_interpolation:v1")
            
            taskC = DockerTask("Uploader"+str(i), "python /home/upload.py -i workflow:///Interpolation"+str(i)+"/output -w 1 ", image="module_todb:v1")
            # add tasks to the workflow
            workflow.add_task(taskA)
            workflow.add_task(taskB)
            workflow.add_task(taskC)
            meta_workflow.add_workflow(workflow)
            adquisition_list = adquisition_list[:-1]
            adquisition_list+=","
            idate = datetime.strptime(end_date, '%d-%m-%Y') + timedelta(days=1) ##adding 1 day

        # The task a 
        meta_workflow.make_dependencies()
        end_building = time.time()

        start_validation= time.time()

        meta_workflow.Validate_WF()

        end_validation= time.time()

        # run the workflow
        start_exe = time.time()

        meta_workflow.run()
        end_exe = time.time()
        logfile.write("%s,%s,%s\n" %(end_building-start_building, end_validation-start_validation, end_exe-start_exe))
    logfile.close()
    #docker rm -f $(docker ps -aq --filter ancestor=module_todb:v1)
    #docker rm -f $(docker ps -aq --filter ancestor=module_interpolation:v1)



