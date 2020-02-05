import json
import os.path
import time
from dagon import Workflow
from dagon.task import DagonTask, TaskType
from dagon.docker_task import DockerTask
from dagon import Status
from dagon.dag_tps import DAG_TPS
import sys
# Check if this is the main
if __name__ == '__main__':


    command_dir = sys.argv[1]
    init_date = sys.argv[2]
    end_date = sys.argv[3]
    workflow_id = int(sys.argv[4])
    no_workflows = sys.argv[5]

    # Create the orchestration workflow


    workflow = Workflow("DAGtp_wf_"+str(workflow_id))

    #create list of dependencies to interpolation
    adquisition_list = "'"
    for i in range(1,workflow_id+1):
        workflow_name = "DAGtp_wf_"+str(i)
        adquisition_list += "workflow://%s/Adquisition%s/metadata/FilesNc '" %(workflow_name,i)

        adquisition_list = adquisition_list[:-1]
        adquisition_list+=","

    adquisition_list = adquisition_list[:-1]
    adquisition_list +="'"


    start_building = time.time()
    print(adquisition_list)
    taskA = DagonTask(TaskType.BATCH, "Adquisition"+str(workflow_id) , "cp -r "+command_dir+"/launcher/lib $PWD;java -jar "+command_dir+"launcher/launcher.jar 1 1 "+str(init_date)+" "+str(end_date)+" $PWD/ aq_ds_"+str(workflow_id))
    taskB = DockerTask("Interpolation"+str(workflow_id), "python /home/Interpolacion.py -i "+adquisition_list+" -w 1 ", image="module_interpolation:v1")
    taskC = DockerTask("Uploader"+str(workflow_id), "python /home/upload.py -i workflow:///Interpolation"+str(workflow_id)+"/output -w 1 ", image="module_todb:v1")
    
    # add tasks to the workflow
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.make_dependencies()
    end_building = time.time()

    start_validation= time.time()
    workflow.Validate_WF()
    end_validation= time.time()


    # run the workflow
    start_exe = time.time()
    workflow.run()
    end_exe = time.time()

    logfile= open("../logs/test_with_"+str(no_workflows)+"/workflows", "a+")
    logfile.write("%s,%s,%s,%s\n" %(workflow_id,end_building-start_building, end_validation-start_validation, end_exe-start_exe))
    logfile.close()
