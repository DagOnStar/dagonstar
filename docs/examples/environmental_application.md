# Environmental Application Examples

Source directory: [`examples/envapp`](../../examples/envapp)

## Files and directories

- `app.py`
- `README.md`
- `models/`
- `models/wrf/`
- `models/wrf/scripts/`
- `models/wrf/utils/`
- `archive2plot/`
- `publishWrf/`

## Purpose

The environmental application examples are research-oriented demonstration
material inspired by real forecasting workflows involving:

- WRF: Weather Research and Forecasting model;
- ROMS: Regional Ocean Modeling System;
- WaComM++: marine pollution modeling.

The repository describes this material as a mockup/sanitized demonstration of a
larger environmental forecasting system.

## Concepts exercised

- wrapping external scientific model executables;
- preparing model input files;
- executing model stages;
- post-processing outputs;
- rendering archived products to plots;
- publishing products.

## WRF scripts

The `models/wrf/scripts/` directory includes shell-oriented wrappers such as:

- `geogrid`
- `ungrib`
- `metgrid`
- `real`
- `wrf`
- `publishWrfOutput`
- namelist generators

These represent the common structure of a numerical weather workflow:

1. configure domain and static geographical data;
2. prepare meteorological input;
3. generate model-ready files;
4. run initialization;
5. run simulation;
6. post-process and publish outputs.

## archive2plot

`archive2plot` contains a utility for rendering post-processed model output as
image plots. It includes:

- `archive2plot.py`
- `Render.py`
- `maps.json`
- `archive2plot.conf`
- `requirements.txt`
- shapefile documentation

## Prerequisites

These examples may require substantial external software:

- compiled WRF and related preprocessing tools;
- geospatial Python libraries;
- NetCDF/HDF libraries;
- model input datasets;
- shapefiles or map assets;
- HPC or containerized execution environments.

They are not generic unit tests. Treat them as scientific application templates.

## Scientific interpretation

The environmental application is the richest example of DAGonStar's intended
domain: orchestrating heterogeneous model components and data products across
scientific software stacks.

To adapt it:

1. identify each model executable as a task;
2. define all file products exchanged between tasks;
3. wrap each executable in a reproducible launcher script;
4. encode cross-task data products with `workflow://`;
5. verify each model stage independently before running the full workflow.
