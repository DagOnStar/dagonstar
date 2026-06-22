# Web task example

Run `python3 download_and_process.py` after configuring DAGonStar. It starts a local HTTP service, stages a batch output into a `TaskType.WEB` multipart request, then uses `TaskType.NATIVE` to consume the response. No external service or credential is required. Responses are in `outputs/`; runner metadata is in `.dagon/`. For real services, use environment-variable authentication fields and never hardcode secrets.
