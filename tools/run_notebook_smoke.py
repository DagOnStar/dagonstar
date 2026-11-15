#!/usr/bin/env python3
"""Execute the tutorial notebook's code cells in order, without Jupyter.

The notebook's code cells are plain Python (no shell or line magics); this
runner executes them in one namespace, as a kernel would, and fails on the
first exception. Lesson scripts that need unavailable infrastructure or tools
(Docker, cwltool, Slurm) report their own explicit skips. The setup cell runs
``pip install -e .[docker,kubernetes]`` exactly as in Jupyter, so run this in
a disposable or development environment.

Usage: python tools/run_notebook_smoke.py [--list]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "docs" / "tutorial" / "DAGonStar_tutorial.ipynb"
MAGIC = re.compile(r"^\s*[!%]", re.MULTILINE)


def code_cells(notebook=NOTEBOOK):
    """Return ``(index, heading, source)`` for each code cell, with the nearest preceding heading."""
    data = json.loads(Path(notebook).read_text(encoding="utf-8"))
    heading = "setup"
    cells = []
    for index, cell in enumerate(data["cells"]):
        source = "".join(cell.get("source", []))
        if cell["cell_type"] == "markdown":
            for line in source.splitlines():
                if line.startswith("## "):
                    heading = line[3:].strip()
                    break
        elif cell["cell_type"] == "code":
            if MAGIC.search(source):
                raise SystemExit("cell %d uses shell or line magics, which this runner does not execute" % index)
            cells.append((index, heading, source))
    return cells


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="list the code cells without executing them")
    args = parser.parse_args(argv)
    cells = code_cells()
    if args.list:
        for index, heading, _ in cells:
            print("%3d  %s" % (index, heading))
        return 0
    namespace = {"__name__": "__main__"}
    started = time.monotonic()
    for index, heading, source in cells:
        print("== cell %d (%s)" % (index, heading), flush=True)
        exec(compile(source, "%s[cell %d]" % (NOTEBOOK.name, index), "exec"), namespace)
    print("Executed %d notebook code cells in %.1f s" % (len(cells), time.monotonic() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
