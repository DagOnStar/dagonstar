# DAGonStar (aka DAGon\*)
DAGonStar (Direct acyclic graph On anything) is a lightweight Python library implementing
a workflow engine able to execute parallel jobs represented by direct acyclic graphs on
any combination of local machines, on-premise high-performance computing clusters,
containers, and cloud-based virtual infrastructures.

 ![The DAGonStar Logo](/figures/DAGonStar_Logo01.png)

DAGonStar is used as the primary workflow engine to run real-world production-level
applications.

DAGonStar is in production at the [Center for Monitoring and Modeling Marine and Atmosphere](https:/meteo.uniparthenope.it)
applications hosted at the University of Naples "Parthenope".

# Motivation
Thanks to the advent of public, private, and hybrid clouds, the democratization of
Computational resources changed the rules in many science fields.
For decades, one of the efforts of computer scientists and computer engineers was the
development of tools able to simplify access to high-end computational resources by
computational scientists. However, nowadays, any science field can be considered
"computational" if the availability of powerful but easy-to-manage workflow
engines is crucial.

# Features

* Workflows described as a Python script
* Fully supporting the workflow:// schema
* Supported task types:
  * Local
  * Bash
  * Remote
  * Slurm
  * REST
  * Cloud (AWS, Digital Ocean, Google Grid, Azure, OpenStack)
  * Container (Docker)
  * IoT (Compute Continuum)
* Task related data locality
* Transparent staging technologies
  * Link
  * Copy
  * Secure Copy
  * Globus
* Parallel patterns
* Implicit and explicit checkpoint system
* Garbage collector for scratch directory footprint minimization

# Acknowledgments
The following initiatives support DAGonStar development:

* Research agreement "Modelling mytilus farming at scale"
  (MytilX, CUP D13C24000470002, funded by the Istituto Zooprofilattico Sperimentale dell’Umbria e delle Marche) -
  DAGonStar orchestrates the production workflow to deliver use case, study zones specific, weather, marine, pollutants,
  and farmed mussels contamination forecasts and predictions.


* Research contract "Mytilus farming System with High-Performance Computing and Artificial Intelligence"
  (MytilEx, CUP I63C23000180002, funded by the Campania Region, Veterinary sector) -
  DAGonStar orchestrates the production workflow to deliver daily 168 weather, marine, pollutants,
  and farmed mussels contamination forecasts and predictions. [PWA](http://meteo.uniparthenope.it/mytilex/)


* EuroHPC H2020 project "Adaptative Multi-tier Intelligent data manager for Exascale"
  (ADMIRE, 956748-ADMIRE-H2020-JTI-EuroHPC-2019-1, funded by the European Commission) - 
  WP7: DAGonStar orchestrates the Environmental Application delivering on-demand weather, marine,
  and pollutants simulations and forecasts on the Campania Region (Italy).
  [link](https://www.admire-eurohpc.eu)

# Cite DAGonStar

## Workflow engine

* Sánchez-Gallegos, Dante Domizzi, Diana Di Luccio, Sokol Kosta, J. L. Gonzalez-Compean, and Raffaele Montella.
  "An efficient pattern-based approach for workflow supporting large-scale science: The DagOnStar experience."
  Future Generation Computer Systems 122 (2021): 187-203.
  [link](https://www.sciencedirect.com/science/article/pii/S0167739X21000984)


* Barron-Lugo, J.A., Gonzalez-Compean, J. L., Carretero, J., Lopez-Arevalo, I., & Montella, R. (2021).
  A novel transversal processing model to build environmental big data services in the cloud. 
  Environmental Modelling & Software, 144, 105173.
  [link](https://www.sciencedirect.com/science/article/abs/pii/S1364815221002152)


* Sánchez-Gallegos, Dante D., Diana Di Luccio, José Luis Gonzalez-Compean, and Raffaele Montella.
  "Internet of things orchestration using dagon workflow engine."
  In 2019 IEEE 5th world forum on internet of things (WF-IoT), pp. 95-100. IEEE, 2019.
  [link](https://ieeexplore.ieee.org/abstract/document/8767199)


* Sánchez-Gallegos, Dante D., Diana Di Luccio, J. L. Gonzalez-Compean, and Raffaele Montella.
  "A microservice-based building block approach for scientific workflow engines: Processing large data volumes with dagonstar."
  In 2019 15th International Conference on Signal-Image Technology & Internet-Based Systems (SITIS), pp. 368-375. IEEE, 2019.
  [link](https://ieeexplore.ieee.org/abstract/document/9067951)


* Montella, Raffaele, Diana Di Luccio, and Sokol Kosta.
  "Dagon: Executing direct acyclic graphs as parallel jobs on anything."
  In 2018 IEEE/ACM Workflows in Support of Large-Scale Science (WORKS), pp. 64-73. IEEE, 2018.
  [link](https://ieeexplore.ieee.org/abstract/document/8638376)

## Applications
* Mellone, Gennaro, Ciro Giuseppe De Vita, Enrico Zambianchi, David Expósito Singh,
  Diana Di Luccio, and Raffaele Montella.
  "Democratizing the computational environmental marine data science: using the high-performance cloud-native computing for inert transport and diffusion lagrangian modelling."
  In 2022 IEEE International Workshop on Metrology for the Sea; Learning to Measure Sea Health Parameters (MetroSea), pp. 267-272. IEEE, 2022.
  [link](https://ieeexplore.ieee.org/abstract/document/9950862)


* De Vita, Ciro Giuseppe, Gennaro Mellone, Aniello Florio,
  Catherine Alessandra Torres Charles, Diana Di Luccio,
  Marco Lapegna, Guido Benassai, Giorgio Budillon, and Raffaele Montella.
  "Parallel and hierarchically-distributed Shoreline Alert Model (SAM)." 
  In 2023 31st Euromicro International Conference on Parallel, Distributed and Network-Based Processing (PDP), pp. 109-113. IEEE, 2023.
  [link](https://ieeexplore.ieee.org/abstract/document/10136945)


* Montella, Raffaele, Diana Di Luccio, Ciro Giuseppe De Vita, Gennaro Mellone,
  Marco Lapegna, Gloria Ortega, Livia Marcellino, Enrico Zambianchi, and Giulio Giunta.
  "A highly scalable high-performance Lagrangian transport and diffusion model for marine pollutants assessment."
  In 2023 31st Euromicro International Conference on Parallel, Distributed and Network-Based Processing (PDP), pp. 17-26. IEEE, 2023.
  [link](https://ieeexplore.ieee.org/abstract/document/10137219)


## Surveys

* Aldinucci, Marco, Giovanni Agosta, Antonio Andreini, Claudio A. Ardagna,
  Andrea Bartolini, Alessandro Cilardo, Biagio Cosenza et al.
  "The Italian research on HPC key technologies across EuroHPC."
  In Proceedings of the 18th ACM international conference on computing frontiers, pp. 178-184. 2021.
  [link](https://dl.acm.org/doi/abs/10.1145/3457388.3458508)

# Installation 

```bash
git clone https://github.com/DagOnStar/dagonstar.git  
cd dagonstar  
python3 -m venv venv  
. venv/bin/activate  
pip install -r requirements.txt  
export PYTHONPATH=$PWD:$PYTHONPATH  
```

## Troubleshooting 

* On some MacOS installations, pycrypto fails to automatically install. 
  Usually this is due to *gmp* library missing in the default include and library path.
  Before launching the requirements install, find the location of the missing library.
  Then export the CFLAGS as in the example below (The actual path could be different):

```bash
export "CFLAGS=-I/usr/local/Cellar/gmp/6.2.1_1/include -L/usr/local/Cellar/gmp/6.2.1_1/lib"
```


# Demo

Copy the configuration file in the examples directory.

```bash
cp dagon.ini.sample examples/dagon.ini 
cd examples
```

Edit the ini file matching your system configuration.

## Task oriented workflow.

The workflow is defined as tasks and their explicit dependencies.

```bash
python taskflow-demo.py
```

## Data oriented workflow.

The workflow is defined by data dependencies (task dependencies are automatically resolved)

```bash 
python dataflow-demo.py
```


## Batch Task Flow
```python
    from dagon import Workflow
    from dagon.task import TaskType, DagonTask

    # Create the orchestration workflow
    workflow = Workflow("Taskflow-Demo")
  
    taskA = DagonTask(TaskType.BATCH, "Tokio", "/bin/hostname >tokio.out")
    taskB = DagonTask(TaskType.BATCH, "Berlin", "/bin/date")
    taskC = DagonTask(TaskType.BATCH, "Nairobi", "/usr/bin/uptime")
    taskD = DagonTask(TaskType.BATCH, "Mosco", "cat workflow://Tokio/tokio.out")

    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)
  
    taskB.add_dependency_to(taskA)
    taskC.add_dependency_to(taskA)
    taskD.add_dependency_to(taskB)
    taskD.add_dependency_to(taskC)
    
    workflow.run()
```

## Batch Data Flow
```python
    from dagon import Workflow
    from dagon.task import DagonTask, TaskType
    
    # Check if this is the main
    if __name__ == '__main__':    
      # Create the orchestration workflow
      workflow=Workflow("DataFlow-Demo")
      
      # The task a
      taskA = DagonTask(TaskType.BATCH, "A", "mkdir output; hostname > output/f1.txt")

      # The task b
      taskB = DagonTask(TaskType.BATCH, "B", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")

      # The task c
      taskC = DagonTask(TaskType.BATCH, "C", "echo $RANDOM > f2.txt; cat workflow:///A/output/f1.txt >> f2.txt")

      # The task d
      taskD = DagonTask(TaskType.BATCH, "D", "cat workflow:///B/f2.txt >> f3.txt; cat workflow:///C/f2.txt >> f3.txt")
      
      # add tasks to the workflow
      workflow.add_task(taskA)
      workflow.add_task(taskB)
      workflow.add_task(taskC)
      workflow.add_task(taskD)
    
      workflow.make_dependencies()

      # run the workflow
      workflow.run()
```
## Meta workflow
```python
    from dagon import Workflow
    from dagon.dag_tps import DAG_TPS
    from dagon.task import DagonTask, TaskType
    
    workflow = Workflow("DataFlow-Demo-Server")
    workflow.set_dry(False)    # Set the dry
    # The task a
    taskA = DagonTask(TaskType.BATCH, "A", "mkdir output;echo 'A1,A2,A3' > output/f1.csv")
    # The task b
    taskB = DagonTask(TaskType.BATCH, "B", "echo 'B1,B2,B3' > f2.csv; cat workflow:///A/output/f1.csv >> f2.csv")
    # The task c
    taskC = DagonTask(TaskType.BATCH, "C", "echo 'C1,C2,C3' > f2.txt; cat workflow:///A/output/f1.csv >> f2.csv")
    # The task d
    taskD = DagonTask(TaskType.BATCH, "D", "cat workflow:///B/f2.csv >> f3.csv; cat workflow:///C/f2.csv >> f3.csv")

    #second workflow
    workflow2 = Workflow("DataFlow-transversal")
    workflow2.set_dry(False)    # Set the dry
    # The task E
    taskE = DagonTask(TaskType.BATCH, "E", "mkdir output;echo 'E1,E2,E3' > output/f1.csv")
    # The task f
    taskF = DagonTask(TaskType.BATCH, "F", "echo 'F1,F2,F3' > f2.csv; cat workflow://DataFlow-Demo-Server/A/output/f1.csv >> f2.csv; cat workflow:///E/output/f1.csv >> f2.csv")
    # The task g
    taskG = DagonTask(TaskType.BATCH, "G", "cat workflow:///F/f2.csv >> f3.csv; cat workflow://DataFlow-Demo-Server/C/f2.csv >> f3.csv")

    # add tasks to the workflow 1
    workflow.add_task(taskA)
    workflow.add_task(taskB)
    workflow.add_task(taskC)
    workflow.add_task(taskD)

    # add tasks to the workflow 2
    workflow2.add_task(taskE)
    workflow2.add_task(taskF)
    workflow2.add_task(taskG)

    #list of the workflows
    metaworkflow=DAG_TPS("NewDAG")
    metaworkflow.add_workflow(workflow)
    metaworkflow.add_workflow(workflow2)
    metaworkflow.make_dependencies()

    metaworkflow.run()
```
