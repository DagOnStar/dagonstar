
from requests.exceptions import ConnectionError
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests
from requests.exceptions import MissingSchema


# Perform the communication with the dagon service
class API:
    """Client of DAGonService (https://github.com/DagOnStar/DagOnService).

    :param url: base URL of the service, e.g. ``http://localhost:57000``
    :param token: optional access token, sent as ``Authorization: Bearer``;
        required when the service sets ``DAGONSERVICE_API_TOKEN``
    :param timeout: seconds before a request is abandoned
    """

    def __init__(self, url: str, token: Optional[str] = None, timeout: float = 10.0) -> None:
        self.base_url = url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = "Bearer " + token
        self.checkConnection()

    def _url(self, *parts: Any) -> str:
        """Join path segments, percent-encoding each one (task names are free text)."""
        return self.base_url + "".join("/" + quote(str(part), safe="") for part in parts)

    # check if the service URL is valid or a service is available
    def checkConnection(self) -> None:
        """
        check if the service URL is valid or a service is available

        :raises ConnectionError: when it's not possible to connect to the URL provided
        """
        try:
            self.session.head(self.base_url + "/check", timeout=self.timeout)
        except ConnectionError as e:
            raise ConnectionError("It is not possible connect to the URL %s" % self.base_url)
        except MissingSchema:
            raise ConnectionError("Bad URL %s" % self.base_url)

    # create workflow on dagon service
    def create_workflow(self, workflow: Any) -> int:
        """
        create workflow on dagon service

        :param workflow: :class:`dagon.Workflow` object to save
        :type workflow: :class:`dagon.Workflow`

        :return: workflow id
        :rtype: int

        :raises Exception: when there is an error with the registration or the workflow name already exists
        """
        res = self.session.post(self._url("create"), json=workflow.as_json(), timeout=self.timeout)
        if res.status_code == 201:  # created
            json_reponse = res.json()
            return json_reponse['id']
        else:
            if res.status_code == 409:
                raise Exception("Workflow name already exists %d %s" % (res.status_code, res.reason))
            else:
                raise Exception("Workflow error registration %d %s" % (res.status_code, res.reason))

    # add task to workflow
    def add_task(self, workflow_id: int, task: Any) -> None:
        """
        add task to workflow

        :param workflow_id: workflow id of the tasks
        :type workflow_id: int

        :param task: task to add to the workflow
        :type task: :class:`dagon.task.Task`

        :raises Exception: when there is an error with the call
        """
        res = self.session.post(self._url("add_task", workflow_id), json=task.as_json(), timeout=self.timeout)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))

    # update a task status in the server
    def update_task_status(self, workflow_id: int, task: str, status: str) -> None:
        """
        update a task status in the server

        :param workflow_id: workflow id of the tasks
        :type workflow_id: int

        :param task: name of the task
        :type task: str

        :param status: task status
        :type status: str

        :raises Exception: when there is an error with the call
        """
        res = self.session.put(self._url("changestatus", workflow_id, task, status), timeout=self.timeout)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))

    # get a task from the server
    def get_task(self, workflow_id: int, task: str) -> Dict[str, Any]:
        """
        get a task from the server

        :param workflow_id: workflow id of the tasks
        :type workflow_id: int

        :param task: name of the task
        :type task: str

        :return: task
        :rtype: :class:`dagon.task.Task`

        :raises Exception: when there is an error with the call
        """

        res = self.session.get(self._url(workflow_id, task), timeout=self.timeout)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))
        else:
            task = res.json()
            return task

    # get a task from the server
    def get_workflow_by_name(self, workflow_name: str) -> str:
        """
        get a workflow id from the server

        :param workflow_name: workflow name
        :type workflow_name: str

        :return: id
        :rtype: :str

        :raises Exception: when there is an error with the call
        """

        res = self.session.get(self._url("getworkflow", workflow_name), timeout=self.timeout)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong, no Transversal workflow %s founded, %d %s" % (workflow_name,res.status_code, res.reason))
        else:
            workflow_id = res.text
            return workflow_id

    # update atribute of the task
    def update_task(self, workflow_id: int, task: str, attribute: str, value: str) -> None:
        """
        update attribute of the task

        :param workflow_id: workflow id of the tasks
        :type workflow_id: int

        :param task: name of the task
        :type task: str

        :param attribute: attribute of the task to update
        :type task: str

        :param value: value of the attribute
        :type task: str

        :raises Exception: when there is an error with the call
        """

        # ``params`` URL-encodes the value: paths with '&', '#' or '+' arrive intact.
        res = self.session.put(self._url("update", workflow_id, task, attribute),
                               params={"value": value}, timeout=self.timeout)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))

    # add dependency on task
    def add_dependency(self, workflow_id: int, task: str, dependency: str) -> None:
        """
        add a dependency to an existing task in a workflow

        :param workflow_id: workflow id of the tasks
        :type workflow_id: int

        :param task: name of the task
        :type task: str

        :param dependency: name of the dependency
        :type task: str

        :raises Exception: when there is an error with the call
        """
        res = self.session.put(self._url(workflow_id, task, "dependency", dependency), timeout=self.timeout)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))
