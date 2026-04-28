# DAGonStar (aka DAGon*)

DAGonStar (Direct acyclic graph On anything) is a lightweight Python library implementing a workflow engine able to execute parallel jobs represented by direct acyclic graphs on any combination of local machines, on-premise high-performance computing clusters, containers, and cloud-based virtual infrastructures.

![The DAGonStar Logo](/figures/DAGonStar_Logo01.png)

## TFG 2026: Container support in the Compute Continuum

This repository has been extended as part of a Final Degree Project (TFG) in Computer Engineering. The main goal is to provide DAGonStar with advanced orchestration capabilities for containerized environments optimized for Edge Computing and the Compute Continuum.

### Implemented Technologies

New executors have been designed and implemented to support:

* **Apptainer (Singularity)**: High-performance containers without root privileges (ideal for HPC and Edge environments).
* **HashiCorp Nomad**: Lightweight orchestrator for task burst management in the Edge.
* **Kubernetes (k3s)**: Lightweight Kubernetes distribution for pod-based orchestration and data streaming.
* **Docker**: Standard industrial container support.

### Roadmap and Navigation Guide

To evaluate the technical implementation, the following directories are highlighted:

* **dagon/**: Core framework extensions.
  * `apptainer_task.py`: SIF image management and writeable overlays logic.
  * `nomad_task.py`: Interaction with Nomad's REST API.
  * `kubernetes_task.py`: Pod orchestration and `kubectl`-based data streaming.
  * `docker_task.py`: Refactored Docker support.
* **examples/taskflow/**: Basic demonstration scripts for each new task type.
* **examples/dataflow/**: Examples showcasing data-driven staging between different executors.
* **examples/edge_fog/**: Real-world evaluation scenario involving sensor telemetry, Raspberry Pi 5, and power monitoring.
* **outputs/**: Raw metrics in CSV and JSON formats covering performance and energy consumption benchmarks (analyzed in Chapter 4 of the thesis).

### Monitoring and Observability

The extension includes native integration with:

* **Prometheus**: Metrics collection (CPU, RAM, Temperature, and Energy consumption).
* **Grafana**: Dynamic visualization of load profiles for different container technologies.
* **MongoDB Atlas**: Cloud-based persistence for functional and operational results.

---

# Original Features

* Workflows described as a Python script
* Fully supporting the workflow:// schema
* Supported task types:
  * Local
  * Bash
  * Remote
  * Slurm
  * REST
  * Cloud (AWS, Digital Ocean, Google Grid, Azure, OpenStack)
  * Container (Docker, Apptainer, Kubernetes, Nomad)
  * IoT (Compute Continuum)
* Task related data locality
* Transparent staging technologies (Link, Copy, Secure Copy, Globus)
* Parallel patterns
* Implicit and explicit checkpoint system
* Garbage collector for scratch directory footprint minimization

# Acknowledgments

The following initiatives support DAGonStar development:

* Research agreement "Modelling mytilus farming at scale" (MytilX)
* Research contract "Mytilus farming System with High-Performance Computing and Artificial Intelligence" (MytilEx)
* EuroHPC H2020 project "Adaptative Multi-tier Intelligent data manager for Exascale" (ADMIRE)

# Installation

```bash
git clone https://github.com/sebas80sebas/dagonstar-containers.git
cd dagonstar-containers
virtualenv venv  
. venv/bin/activate  
pip install -r requirements.txt  
export PYTHONPATH=$PWD:$PYTHONPATH  
```

# Demo

```bash
cp dagon.ini.sample examples/dagon.ini 
cd examples/taskflow
python taskflow-demo.py
```

# Cite DAGonStar

* Sánchez-Gallegos et al. "An efficient pattern-based approach for workflow supporting large-scale science: The DagOnStar experience." (2021)
* Barron-Lugo et al. "A novel transversal processing model to build environmental big data services in the cloud." (2021)
* Sánchez-Gallegos et al. "Internet of things orchestration using dagon workflow engine." (2019)
* Montella et al. "Dagon: Executing direct acyclic graphs as parallel jobs on anything." (2018)
