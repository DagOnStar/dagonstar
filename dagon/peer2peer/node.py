import hashlib
from flask import Flask
from flask import request
import json
import sys
import requests
import os
import socket
from time import sleep



app = Flask(__name__)

# nodes
ip = "localhost"

m = 10
ID = int(sys.argv[1]) #workflow
PortBase=int(sys.argv[2])
SuscribedNodes=[]
Records = []
Transversal_Records = dict()

@app.route('/updateTask', methods=['POST'])
def update():
    params = request.get_json()
    if 'task' in params and 'status' in params and 'working_dir' in params:
        task_name = params['task']
        task_status = params['status']
        task_working_dir = params['working_dir']
        update_task(task_name,task_status,task_working_dir)
        return "OK"
    return "BAD"

@app.route('/getTask', methods=['POST'])
def get_Task():
    params = request.get_json()
    if 'workflow' in params and 'task' in params:
        task_name = params['task']
        task_workflow = params['workflow']

        for x in Transversal_Records[task_workflow]:
            while True:
                if x['name'] == task_name and x['status'] == "FINISHED":
                    return json.dumps(x)
                else:
                    sleep(1)

@app.route('/subscribe', methods=['POST'])
def subscribe():
    params = request.get_json()
    if 'id' in params and 'port' in params and 'ip' in params:
        sus_id = params['id']
        sus_port = params['port']
        sus_ip = params['ip']
        if (in_suscribed_nodes(sus_id)):
            return "None"
        info = {'id':sus_id,'port':sus_port,'ip':sus_ip}
        SuscribedNodes.append(info)
        return json.dumps(Records)        #need to return the actual info


@app.route('/notify/<workflow>', methods=['POST'])
def getNotification(workflow):
    global Transversal_Records
    params = request.get_json()
    if 'name' in params and 'status' in params and 'working_dir' in params:
        name = params['name']
        status = params['status']
        working_dir = params['working_dir']
        info = {'name':name,'status':status,'working_dir':working_dir}

        # workflow exist in records
        if not workflow in Transversal_Records:
            Transversal_Records[workflow]=[]
        #look for the task

        for task in Transversal_Records[workflow]:
            if task['name']==name:
                task['status'] = status
                return "OK"
        Transversal_Records[workflow].append(info)
        return "OK"
    return "BAD"


@app.route('/list_subs', methods=['GET'])
def get_subscribers():
    return json.dumps(SuscribedNodes)
@app.route('/list_tasks', methods=['GET'])
def get_task_list():
    return json.dumps(Records)
@app.route('/list_trans', methods=['GET'])
def get_transversal_list():
    return json.dumps(Transversal_Records)

def subscribe2workflow(id,host):
    global Transversal_Records
    service = "/subscribe"
    url = "http://%s/%s" % (host,service)
    ip,port = host.split(":")
    data = {'id':id,'port':port,'ip':ip}
    res = requests.post(url, json=data)
    if res.status_code != 201 and res.status_code != 200:  # error
        raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))
    if res.text == "OK":
        return 0
    else:
        data = json.loads(res.text)
        for item in data:
            Transversal_Records[host].append(item)

def CheckStatus():
    pass

def in_suscribed_nodes(id_node):
    for item in SuscribedNodes:
        if item['id']==id_node:
            return True
    return False

def update_task(task_name,task_status,task_working_dir):
    global Records
    for item in Records:
        if item['name'] == task_name:
            item['status'] = task_status
            item['working_dir'] = task_working_dir
            notify_suscribers(item) #notify suscribers
            return True
    info = {'name':task_name,'status':task_status,'working_dir':task_working_dir}
    Records.append(info)
    notify_suscribers(info) #notify suscribers
    return False

def if_task_exist(task_name):
    for item in Records:
        if item['name'] == task_name:
            return True
    return False

def notify_suscribers(data):
    for subscriber in SuscribedNodes:
        service = "notify/%s" % ID
        url = "http://%s:%s/%s" % (subscriber['ip'],subscriber['port'],service)  
        print(url)
        res = requests.post(url, json=data)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))

def Check():
	for node in SuscribedNodes:
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		result = sock.connect_ex((ip,int(node[1])))
		if result == 0:
			pass
		else:
			requests.get('http://'+ip+':'+str(PortBase)+'/DeleteNode?id='+str(node[0]),verify=False)
			print ("hubo un nodo caido")
		sock.close()


if __name__ == '__main__':
	app.run(host='0.0.0.0', port=(PortBase),debug = True)