import sys
import time
from datetime import datetime,timedelta
import threading
import os


def launch(command_dir,init_date,end_date,id_w,no_workflows):
    #launch workflow
    cmd = "python3 transversal-merra-different-scripts.py %s %s %s %s %s" %(command_dir,init_date,end_date,id_w,no_workflows)
    os.system(cmd)


def cleanContainers():
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_todb:v1)')
    os.system('docker rm -f $(docker ps -aq --filter ancestor=module_interpolation:v1)')


if not os.path.exists("../logs/"):
    os.makedirs("../logs/")

command_dir = sys.argv[1]
init_date = sys.argv[2]
end_date = sys.argv[3]
no_workflows = int(sys.argv[4]) 
iterations = 31


if not os.path.exists("../logs/test_with_"+str(no_workflows)):
    os.makedirs("../logs/test_with_"+str(no_workflows))

idate = datetime.strptime(init_date, '%d-%m-%Y')
edate = datetime.strptime(end_date, '%d-%m-%Y')
daterange = (edate-idate)/no_workflows

logfile= open("../logs/test_with_"+str(no_workflows)+"/workflows", "a+")
logfilemw= open("../logs/test_with_"+str(no_workflows)+"/mw_workflows", "a+")

logfile.write("workflow,building,validation,runtime\n")
logfile.close()

logfilemw.write("runtime\n")


for i in range(0,iterations):
    init_date = sys.argv[2]
    end_date = sys.argv[3]
    idate = datetime.strptime(init_date, '%d-%m-%Y')
    edate = datetime.strptime(end_date, '%d-%m-%Y')
    daterange = (edate-idate)/no_workflows
    #save the number of workflows
    wf = []
    for w in range(1,no_workflows+1):
        init_date = idate.strftime('%d-%m-%Y')
        end_date = (idate + daterange).strftime('%d-%m-%Y')
        wf.append(threading.Thread(target=launch, args=(command_dir,init_date,end_date,w,no_workflows)))
        idate = datetime.strptime(end_date, '%d-%m-%Y') + timedelta(days=1) ##adding 1 day
    
    start_exe = time.time()
    for w in wf:
        w.start()
        time.sleep(1) #wait for a second
    
    for w in wf:
        w.join()
    end_exe = time.time()
    logfilemw.write("%s\n" %(end_exe-start_exe))
    cleanContainers()

logfilemw.close()

