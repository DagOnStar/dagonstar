
import requests
from requests.exceptions import ConnectionError
from requests.exceptions import MissingSchema
import logging

# Perform the communication with the TPS manager
class API:
    def __init__(self, url, workspace):
        self.base_url = url
        self.checkConnection()
        self.workspace = workspace

    # check if the service URL is valid or a service is available
    def checkConnection(self):
        """
        check if the service URL is valid or a service is available

        :raises ConnectionError: when it's not possible to connect to the URL provided
        """
        try:
            requests.head(self.base_url)
        except ConnectionError as e:
            raise ConnectionError("It is not possible connect to the URL %s" % self.base_url)
        except MissingSchema:
            raise ConnectionError("Bad URL %s" % self.base_url)

    # load DAGtps and TPPs
    def LoadDAGtps(self, dagtps, tpp, tpp_selected=None ,mode = "static"):
        """
        Load DAGtps to TPS manager

        :param dagtps: :class: json object to save
        :type dagtps: :class: json

        :param tpp: :class: json object with transversal points
        :type tpp: :class: json

        :raises Exception: when dagtps or tpp are in a diferent format
        """
        if tpp_selected is None: tpp_selected=tpp.keys()[0]
        service = "/init"
        url = self.base_url + service
        if mode == "static":
            data = {'dagtps':dagtps,
                    'client': self.workspace,
                    'TPP': tpp,
                    'TPTaken': tpp_selected }
        elif mode == "online":
            data = {'watcher':dagtps,
                    'client': self.workspace,
                    'TPP': tpp,
                    'TPTaken': tpp_selected }
        else:
            raise Exception("Mode not found")
        res = requests.put(url, json=data)
        if res.status_code == 201:  # created
            json_reponse = res.json()
            return "OK"
        else:
            raise Exception("Load error, key error (keygroup) %d %s" % (res.status_code, res.reason))

    # get Data from a TPP or a TPP/DS
    def GetData(self, TPP, DS = "",workspace=None):
        """
        aReturn the data inside a TPP in json format

        :param TPP: name of the TPP for data extract 
        :type workflow_id: string

        :param DS: optional DS inside the TPP
        :type DS: string

        :raises Exception: when there is an error with the call
        """
        if workspace is None: workspace = self.workspace
        service = "/%s/%s/%s" % (workspace, TPP, DS)
        url = self.base_url + service
        res = requests.get(url)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))
        else:
            return res.json()

    ########################################################################################
    ###############################     SERVICES     #######################################
    ########################################################################################

    def Describe(self, TPP, DS = "",workspace=None):
        """
        Get a stadistical description from all the numeric data columns in a TPP

        :param TPP: name of the TPP for data extract 
        :type workflow_id: string

        :param DS: optional DS inside the TPP
        :type DS: string

        :raises Exception: when there is an error with the call
        """
        self.checkConnection()
        if workspace is None: workspace = self.workspace
        service = "/%s/describe/%s/%s" % (workspace ,TPP, DS)
        url = self.base_url + service
        res = requests.get(url)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))
        else:
            return res.json()

    def ANOVA(self, TPP, variables, DS = "" , method = "pearson",workspace = None):
        """
        Get a descripcion of the variance, covaraince and correlation between diferent columns in a TPP

        :param TPP: name of the TPP for data extract 
        :type workflow_id: string

        :param variables: name of the columns to be calculated (separated by comma)
        :type workflow_id: string

        :param method: optional correlational method 
        :type DS: string

        :param DS: optional DS inside the TPP
        :type DS: string

        :return: data
        :rtype: : json

        :raises Exception: when there is an error with the call
        """
        self.checkConnection()
        if workspace is None: workspace = self.workspace
        service = "/%s/ANOVA/%s/%s" % (workspace,TPP, DS)
        url = self.base_url + service
        data = {"variables":variables ,"method": method }
        res = requests.get(url, json = data)
        if res.status_code != 201 and res.status_code != 200:  # error
            raise Exception("Something went wrong %d %s" % (res.status_code, res.reason))
        else:
            data = res.json()
            return data
