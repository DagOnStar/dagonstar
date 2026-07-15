# Native Python task example

Run locally from this directory with `python3 workflow.py` after configuring DAGonStar.
The workflow stages a producer file into a native scratch directory and exposes its declared output downstream.

For Slurm, set `executor="slurm"` and pass scheduler settings in `resources`; the compute node must import the function module and DAGonStar.

For a runnable example whose callable is in a separate file and imports NumPy
installed from `requirements.txt`, see [with_requirements](with_requirements/README.md).
