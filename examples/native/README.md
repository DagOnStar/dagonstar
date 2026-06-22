# Native Python task example

Run locally from this directory with `python3 workflow.py` after configuring DAGonStar.
The workflow stages a producer file into a native scratch directory and exposes its declared output downstream.

For Slurm, set `executor="slurm"` and pass scheduler settings in `resources`; the compute node must import the function module and DAGonStar.
