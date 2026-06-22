# Native Python Task Example

[`examples/native`](../../examples/native) maps a producer's `workflow:///produce/data/input.txt` to an importable function's staged `input_file`, passes `scale` as a scalar, and declares `outputs/scaled.txt`.

Run from the example directory with `python3 workflow.py`. Inputs are copied below `inputs/`, results go to `.dagon/native_result.json`, and Slurm sites can use `executor="slurm"` with `resources` when the module is available on compute nodes.
