"""Importable NumPy-backed functions used by the requirements example."""

import json

import numpy as np


def summarize_measurements(input_file: str, output_file: str) -> dict:
    """Write summary statistics for one number per input line."""
    values = np.loadtxt(input_file, dtype=float, ndmin=1)
    summary = {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
    }
    with open(output_file, "w", encoding="utf-8") as destination:
        json.dump(summary, destination, indent=2, sort_keys=True)
        destination.write("\n")
    return summary
