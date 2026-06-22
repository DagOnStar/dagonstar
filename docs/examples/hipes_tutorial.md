# HiPES Tutorial Examples

Source directory: [`examples/hipes-tutorial`](../../examples/hipes-tutorial)

## Files and stages

- `0-preliminary-step/preliminary-test.py`
- `1-config/hipes-workflow.py`
- `2-pyglobo/hipes-workflow.py`
- `3-map2png/hipes-workflow.py`
- `3-map2png/map2png.py`
- `3-map2png/Dockerfile`
- `hipes-workflow-final.py`
- `HiPES-Dagon_Globo_Tutorial.pdf`
- `requirements.txt`

## Purpose

The HiPES tutorial is a staged learning path showing how a scientific workflow
can evolve from a preliminary script to a containerized/data-rendering workflow.

## Concepts exercised

- incremental workflow construction;
- external Python dependencies;
- map rendering;
- Docker image definition;
- shape files and geospatial assets;
- file-based exchange between tasks.

## Stage interpretation

### Preliminary step

Validates the local environment and introduces the computational activity.

### Configuration step

Introduces DAGonStar workflow configuration and task construction.

### PyGlobo step

Adds domain-specific scientific processing.

### Map-to-PNG step

Wraps map rendering into workflow tasks and includes a Dockerfile for
environment reproducibility.

## Verification

Install the tutorial-specific requirements in an isolated environment:

```bash
cd examples/hipes-tutorial
python -m pip install -r requirements.txt
```

Then follow the stage directories in order. The `3-map2png` stage has its own
requirements and Dockerfile.

## Scientific interpretation

This example family is useful for teaching because it connects:

- workflow orchestration;
- domain processing;
- geospatial visualization;
- containerization;
- progressive reproducibility.
