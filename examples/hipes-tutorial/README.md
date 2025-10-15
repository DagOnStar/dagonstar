# DAGonCAPIO and GLOBO-GLOWPP developing a computational workflow for orchestrating a global weather forecasting model 
**HiPES Workshop (Euro-Par 2025)**

**Credits:** Developed by Gennaro Mellone, Dario Caramiello, Raffaele Montella (University of Naples "Parthenope")for the HiPES 2025 Tutorial Session (Euro-Par 2025)

---
## Introduction
This tutorial walks you through a reproducible **computational workflow** for orchestrating a **global weather forecasting model**.  
Using **DAGonStar** as the orchestrator in combination with **Globo GLOWPP**, you will:

1. **Simulation Preparation** — create a configuration task with PyGLOBO parameters.  
2. **PyGLOBO Run** — launch the PyGLOBO container to produce a NetCDF forecast.  
3. **Result Visualization** — convert the NetCDF output into a PNG image.

By the end, you’ll have an end-to-end pipeline: configure → forecast → visualize.

---

## Preliminary

Set up your Python environment, configure `dagon.ini`, and verify DAGonStar.

**Description**  
- Create and activate a virtual environment.  
- Install required Python packages from `requirements.txt`.  
- Create a scratch directory for runs and set the path in `dagon.ini`.  
- Sanity-check your setup with a preliminary script.  

**Commands**
```bash
# Create and activate a virtualenv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create runs folder (used by the workflow)
mkdir -p runs/
```

**Configure `dagon.ini`**  
Add (or edit) the following lines (use an editor of your choice):
```
[batch]
scratch_dir_base = <your-absolute-path>/runs
```

**Test DAGonStar**
```bash
cd 0-preliminary-step/
python preliminary-test.py
cd ..
```

---

## 1) Create a Configuration

**Description**  
Generate the **YAML configuration** that defines the PyGLOBO run (e.g., forecast length, resolution, output filename). This makes your workflow parameter-driven and reproducible.

**Commands**
```bash
cd 1-config/
python hipes-workflow.py
```

Check the output in `runs/` folder to see workflow results.

*Back to the main folder*
```bash
cd ..
```

---

## 2) Add the Core: PyGLOBO for Forecasting

**Description**  
Prepare the PyGLOBO environment, obtain input data (IC/BC), build the Docker image, and run the forecast. The containerized run will produce a **NetCDF** file in your `runs/` directory.

**Commands**
```bash
cd 2-pyglobo/

# Get the PyGLOBO base (build context)
git clone https://git.isac.cnr.it/montella/globone-glowpp
cd globone-glowpp

# Download initial/boundary conditions (IC/BC)
wget http://wilma.to.isac.cnr.it/diss/globo/globo-ic-bc-20241016.tar.gz
mkdir -p input_data
tar -xzf globo-ic-bc-20241016.tar.gz -C input_data
```

*Build the Docker image (become root only if needed):*
```bash
# (optional)
sudo su

docker build -t globo .

```

*Run (as root) the workflow (launch the containerized forecast):*
```bash
python hipes-workflow.py
```

Check the output in `runs/` folder to see workflow results.

*Back to the main folder*
```bash
cd ..
```
---

## 3) Let’s Visualize Our NetCDF Output!

**Description**  
Build a small container that reads a NetCDF file and produces a **PNG** image, stored in `runs/`. This provides a quick visual check of the forecast output.

**Commands**
```bash
cd 3-map2png/

# Build the image used for conversion (become root only if needed)
docker build -t map2png .

# Run the visualization workflow
python hipes-workflow.py
```

> ✅ Congratulations — your output image is in the `runs/` folder!

---

## Building Docker Containers (note)
If you encounter issues compiling or running containers, you may temporarily switch to **root** for this tutorial.  
Use responsibly and return to your normal user afterwards.

**Command**
```bash
sudo su
```

---

## Conclusion
**Congratulations! 🎉**  
You have successfully set up a complete, reproducible workflow using DAGonStar to:  
1. **Prepare** the forecast configuration,  
2. **Run** the PyGLOBO model to generate NetCDF output, and  
3. **Visualize** the results as a PNG image.  

You’re now ready to adapt, extend, or scale this pipeline for research and production use cases.  


## Useful links
- [DagonStar GitHub](https://github.com/DagOnStar/dagonstar)  
- [PyGLOBO Project](https://git.isac.cnr.it/montella/globone-glowpp)  
