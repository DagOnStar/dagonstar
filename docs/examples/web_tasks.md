# Web Task Example

[`examples/web`](../../examples/web) starts a local HTTP echo service. A batch task creates a file, `TaskType.WEB` stages `workflow:///prepare/output/data.txt`, and a native task consumes the response. Run `python3 download_and_process.py` in that directory. Responses and declared metadata are under `outputs/`; resolved runner data is below `.dagon/`. Authentication uses environment variables, never literals in workflows or metadata.
