import logging
import logging.config
import os
from logging.config import fileConfig
from types import NoneType
import threading
import copy 


from time import time, sleep


class DAG_TPS(object):

    def __init__(self, name,config=None, config_file='dagon.ini', max_threads=10):
        """
        Create a meta-workflow

        :param name: Workflow name
        :type name: str

        """
        self.workflows = []
        self.name = name
        self.logger = logging.getLogger()
        self.workflow_id = 0
        self.tasks = []
        self.T_tasks_needed = []
        self.T_tasks_needy = []

        self.is_api_available = False

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



    def make_dependencies(self):
        """
        Looks for all the dependencies between workflows
        """
        for wf in self.workflows:
            #check the dependencies for each workflow
            wf.make_dependencies()
            #add the workflow's tasks to the DAGtps
            self.Validate_WF(wf)
            

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
            wfJson = []
            for wf in self.workflows:
                jsonWorkflow = {"tasks": {}, "name": wf.name, "id": wf.workflow_id}
                for task in wf.tasks:
                    jsonWorkflow['tasks'][task.name] = task.as_json()
                wfJson.append(jsonWorkflow)
            return wfJson
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
        start_time = time()
        #print self.tasks
        workflows= []
        for wf in self.workflows:
            workflows.append(threading.Thread(target=wf.run))
        for wf in workflows: wf.start()
        for wf in workflows: wf.join()

        completed_in = (time() - start_time)
        self.logger.info("meta-Workflow '"+self.name+ "' completed in %s seconds ---" % completed_in)

    def Validate_WF(self,workflow):
        """
        Validate the transversality points to avoid any kind of cycle on the grap

        :param workflow: list of declared workflows
        :type workflow: list(class: dagon.workflow,...n)

        Raise an Exception when a cylce is founded

        self.tasks is fill with all the task of each workflow
        """
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