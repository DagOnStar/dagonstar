import logging
import logging.config
import os
from logging.config import fileConfig
import threading
import copy 
from dagon.TPS_api import API as TPSapi
from requests.exceptions import ConnectionError
from dagon.config import read_config

from time import time, sleep


class DAG_TPS(object):

    def __init__(self, name,config=None, config_file='dagon.ini', max_threads=10):
        """
        Create a meta-workflow

        :param name: Workflow name
        :type name: str

        """
        if config is not None:
            self.cfg = config
        else:
            self.cfg = read_config(config_file)
            fileConfig(config_file)

        self.workflows = []
        self.name = name
        self.logger = logging.getLogger()
        self.workflow_id = 0
        self.tasks = []
        self.T_tasks_needed = []
        self.T_tasks_needy = []
        self.is_api_available = False
        self.running = False


        self.TPP=dict() #list of transversal processing points
        self.tpp_counter = 0
        self.is_tpsapi_available = False

        try:
            self.TPSapi = TPSapi(self.cfg['transversal_service']['route'],self.name)
            self.is_tpsapi_available = True
            self.logger.debug("TPS API is alive")

        except KeyError:
            self.logger.error("No transversal service URL in config file")
        except ConnectionError as e:
            self.logger.error(e)



    def set_dry(self, dry):
        for wf in self.workflows:
            wf.dry = dry

    def add_workflow(self, workflow):
        """
        Add a workflow to this meta-workflow

        :param workflow: :class:`dagon.workflow` instance
        :type workflow: :class:`dagon.workflow`
        """
        self.workflows.append(workflow)
        workflow.set_dag_tps(self)
        #if self.is_api_available:
        #    self.api.add_task(self.workflow_id, task)

    def find_task_by_name(self, workflow_name, task_name):
        """
        Search for a task of an specific workflow

        :param workflow_name: Name of the workflow
        :type workflow_name: str

        :param task_name: Name of the task
        :type task_name: str

        :return: task instance
        :rtype: :class:`dagon.task.Task` instance if it is found, None in other case
        """

        # Check if the workflow is the current one
        for wf in self.workflows:
            if workflow_name == wf.name:
                wf.find_task_by_name(wf.name,task_name)
        return None

    def find_workflow_task(self,task_name):
        """
        Search for workflow name of an specific task

        :param task_name: Name of the task
        :type task_name: str

        :return: workflow name
        :rtype: string
        """
        # Check if the workflow is the current one
        for wf in self.workflows:
            if wf.find_task_by_name(wf.name,task_name) is not None:
                return wf.name
        return None


    def make_dependencies(self):
        """
        Looks for all the dependencies between workflows
        """
        for wf in self.workflows:
            #check the dependencies for each workflow
            wf.make_dependencies()
            #add the workflow's tasks to the DAGtps
        #self.Validate_WF()
            

    # Return a json representation of the workflow
    def as_json(self,json_format="mw" ):
        """
        Return a json representation of the meta-workflow

        :param json_format: format of the json returned (mw o wf)
        :type json_format: str

        :return: JSON representation
        :rtype: dict(str, object) with data class
        """
        if json_format == "mw":
            jsonWorkflow = {"tasks": {}, "name": self.name, "id": self.workflow_id}
            for wf in self.workflows:
                for task in wf.tasks:
                    jsonWorkflow['tasks'][task.name] = task.as_json()
            return jsonWorkflow
        if json_format == "wf":
            jsonWorkflow = {"tasks": {}, "name": self.name, "id": self.workflow_id}
            for wf in self.workflows:
                for task in wf.tasks:
                    temp = task.remove_from_workflow()
                    jsonWorkflow['tasks'][task.name] = task.as_json()
                    jsonWorkflow['tasks'][task.name]['command'] = temp
            return jsonWorkflow


    def run(self):
        self.logger.debug("Running meta-workflow: %s", self.name)
        self.running=True
        start_time = time()
        #print self.tasks
        workflows= []
        for wf in self.workflows:
            workflows.append(threading.Thread(target=wf.run))
        for wf in workflows: wf.start()
        for wf in workflows: wf.join()

        completed_in = (time() - start_time)
        self.logger.info("Meta-Workflow '"+self.name+ "' completed in %s seconds ---" % completed_in)

    def Validate_WF(self):
        """
        Validate the transversality points to avoid any kind of cycle on the grap

        :param workflow: list of declared workflows
        :type workflow: list(class: dagon.workflow,...n)

        Raise an Exception when a cylce is founded

        self.tasks is fill with all the task of each workflow
        """
        for workflow in self.workflows:
            for task in workflow.tasks:
                for prev in task.prevs:
                    if workflow.find_task_by_name(workflow.name,prev) is None: #if is a task from another workflow -  'do you need someone?'
                        needed = False; needy = False
                        self.T_tasks_needed.append(prev) #dependency task is added to the transversal ones
                        #if the actual task is founded in the transversal, there exist a cycle.
                        if task in self.T_tasks_needed or task.nexts in self.T_tasks_needed: needed=True #are you or your decendents needed?
                        if prev in self.T_tasks_needy: needy=True #who you need is also needed?
                        if needy and needed:
                            logging.warning('A cycle have been found')
                            raise Exception("A cycle have been found from %s to %s" % (prev.name, task.name))
                        else:
                            self.T_tasks_needy.append(task) #add the task and decendets to the needys array
                            for t in task.nexts:
                                self.T_tasks_needy.append(t)
                temp = task.remove_from_workflow() #the command is changed, deleating the workflow reference
                self.tasks.append(temp)

    def Create_TPP_Double(self, DSA, DSB, keygroups, Apath= None, Bpath= None , name=None ):
        """
        Create 2 csv in base of 2 task working dir and a keygroup list

        :param DSA,DSB: name of a declared task
        :type DSA: string}

        :param keygroups: list of the keys (name of columns) of linking each task (datasources) in the form ('DSA_att1-DSB_att1,DSA_att2-DSB_att2' )
        :type keygroups: string

        :param DSApath,DSBpath: adittional path to add to heach task if is necesary. e.g. /output/
        :type DSA: string}

        Return the tpp_name

        Raise an Exception when the task doen't exist or the keygroups are not correct
        """
        if Apath is None: Apath = DSA
        else: Apath = DSA + ":/" + Apath
        if Bpath is None: Bpath = DSB
        else: Bpath = DSB + ":/" + Bpath

        if name is not None:
            tpp_name = name
        else:
            tppid= str(self.tpp_counter)
            tpp_name = "TP_"+tppid
            self.tpp_counter+=1

        tpp = { "NAME": tpp_name, "TYPE": "Double", "TPP_DS": { 
                DSA: {
                    "TYPE": "ID",
                    "ID": Apath,
                    "WF_name": self.find_workflow_task(DSA)
                },
                DSB: {
                    "TYPE": "ID",
                    "ID": Bpath,
                    "WF_name": self.find_workflow_task(DSB)

                }
            },"KEYGROUP": keygroups }

        self.TPP[tpp_name] = tpp
        return tpp_name

    def Create_TPP_Single(self, DS, path= None, name=None ):
        """
        Create a csv in base of a task working dir

        :param DS: name of a declared task
        :type DS: string

        :param path: adittional path to add to each task if is necesary. e.g. /output/
        :type DS: string

        Return the tpp_name
        """
        if path is None: path = DS
        else: path = DS + ":/" + path

        if name is not None:
            tpp_name = name
        else:
            tppid= str(self.tpp_counter)
            tpp_name = "TP_"+tppid
            self.tpp_counter+=1

        tpp = { "NAME": tpp_name, "TYPE": "Single", "TPP_DS": { 
                DS: {
                    "TYPE": "ID",
                    "ID": path,
                    "WF_name": self.find_workflow_task(DS)
                }
            },"KEYGROUP": "None" }

        self.TPP[tpp_name] = tpp
        return tpp_name



    def prepare_tps(self):
        """
        Initialize the TPS manager with the TPS created

        :raises Exception: when there is an error with the call
        """
        tppset_name= "DagonTPP_%s" % self.name
        TPPset =  {tppset_name: self.TPP } 
        if self.is_tpsapi_available == True:
            dag = self.as_json()
            if self.running ==False:
                self.TPSapi.LoadDAGtps("dagon",TPPset,tppset_name, mode="online") #load DAGtps and tpp points to service
            else:
                self.TPSapi.LoadDAGtps(dag,TPPset,tppset_name) #load DAGtps and tpp points to service
