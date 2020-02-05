import json
import os.path
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from dagon.docker_task import DockerTask
from dagon import Status
from dagon.dag_tps import DAG_TPS
import sys
import logging
import time

def cleanContainers():
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_todb:v1)')
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_interpolation:v1)')


# 2 workflows in a DAGTP adding TPS
if __name__ == '__main__':

    command_dir = sys.argv[1]
    no_TPS = int(sys.argv[2]) 
    iterations = 1

    logfile= open("../logs/"+str(no_TPS)+"_TPS_test.txt", "a+")
    logfile.write("building,validation,runtime,extraction,processing,\n")

    # Create the orchestration workflow
    for i in range(0,iterations):

        meta_workflow = DAG_TPS("DAGtp_2WF_"+str(no_TPS)+"TPS")
        start_building = time.time()

        wf_a = Workflow("TestTPS_WFa")
        taskA = DagonTask(TaskType.BATCH, "AdquisitionA", "cp -r "+command_dir+"/launcher/lib $PWD;java -jar "+command_dir+"launcher/launcher.jar 1 1 01-01-2019 02-01-2019 $PWD/ adq_tps_a")
        taskB = DockerTask("InterpolationA", "python /home/Interpolacion.py -i workflow:///AdquisitionA/metadata/FilesNc -w 1 ", image="module_interpolation:v1")
        taskC = DockerTask("UploaderA", "python /home/upload.py -i workflow:///InterpolationA/output -w 1 ", image="module_todb:v1")
        
        wf_b = Workflow("TestTPS_WFb")
        taskD = DagonTask(TaskType.BATCH, "AdquisitionB", "cp -r "+command_dir+"/launcher/lib $PWD;java -jar "+command_dir+"launcher/launcher.jar 1 1 01-03-2019 02-03-2019 $PWD/ adq_tps_b")
        taskE = DockerTask("InterpolationB", "python /home/Interpolacion.py -i workflow:///AdquisitionB/metadata/FilesNc -w 1 ", image="module_interpolation:v1")
        taskF = DockerTask("UploaderB", "python /home/upload.py -i workflow:///InterpolationB/output -w 1 ", image="module_todb:v1")

        wf_a.add_task(taskA)
        wf_a.add_task(taskB)
        wf_a.add_task(taskC)

        wf_b.add_task(taskD)
        wf_b.add_task(taskE)
        wf_b.add_task(taskF)

        meta_workflow.add_workflow(wf_a)
        meta_workflow.add_workflow(wf_b)

        meta_workflow.make_dependencies()

        end_building = time.time() #end building
        start_validation = time.time() #start validate
        meta_workflow.Validate_WF()
        end_validation = time.time() #end validation


        # run the workflow
        start_exe = time.time() #start execution
        meta_workflow.run()
        end_exe = time.time() #end execution

        start_extraction = time.time() #start data extraction 

        TPS = dict()
        for TPP in range(1,no_TPS+1):
            TPS[str(TPP)] = meta_workflow.Create_TPP_Double("InterpolationA", "InterpolationB" , "Station_code-Station_code", Bpath="output/", Apath="output/")
        meta_workflow.prepare_tps() #extract data
        end_extraction = time.time() #end data extraction 

        start_proc= time.time() #start TPS 

        for TPP in range(1,no_TPS+1):
            a = meta_workflow.TPSapi.Describe(TPS[str(TPP)])
        end_proc= time.time() #end TPS 
        
        logfile.write("%s,%s,%s,%s,%s\n" %(end_building-start_building, end_validation-start_validation, end_exe-start_exe,end_extraction-start_extraction,end_proc-start_proc))

        cleanContainers()

    logfile.close()