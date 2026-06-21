# Lesson 13: Execute a Web Task Locally

## Objective

Construct a reproducible workflow in which a local HTTP service receives a file
produced by an upstream task. The lesson demonstrates that a web request is a
first-class DAGonStar task: its dependency is inferred from `workflow://`, its
input is staged into a private scratch directory, and its response is a declared
workflow output.

## Concept

`TaskType.WEB` accepts a JSON-serializable request specification rather than a
shell command. The workflow driver writes that specification under `.dagon/`,
stages referenced files below `inputs/`, and invokes the web runner inside the
task directory. Consequently, the HTTP request occurs where the task executes;
`executor="slurm"` may be used at a configured cluster site without changing
the dataflow model.

## Complete local example

Save the following program as `lesson_13_web_tasks.py` and run
`python3 lesson_13_web_tasks.py` from the repository root. It starts a local
server bound only to `127.0.0.1`; no network service, account, or credential is
required.

```python
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


class EchoHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        reply = json.dumps({"received": "sample" in body.decode("utf-8")}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, _format, *_args):
        pass


def config(scratch):
    return {
        "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
        "dagon_service": {"use": "False", "route": "http://localhost:57000"},
        "ftp_pub": {"ip": "localhost"},
        "slurm": {"partition": ""},
    }


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), EchoHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="dagon-web-lesson-") as scratch:
            workflow = Workflow("Lesson13", config=config(scratch))
            prepare = DagonTask(
                TaskType.BATCH, "prepare", "mkdir -p output; printf sample > output/data.txt"
            )
            upload = DagonTask(
                TaskType.WEB,
                "upload",
                {
                    "method": "POST",
                    "url": "http://127.0.0.1:%s/upload" % server.server_port,
                    "multipart": {
                        "dataset": {
                            "file": "workflow:///prepare/output/data.txt",
                            "content_type": "text/plain",
                        }
                    },
                    "expected_status": 200,
                    "outputs": {"body": "reply.json", "metadata": "request.json"},
                },
            )
            consume = DagonTask(
                TaskType.BATCH, "consume", "cat workflow:///upload/outputs/reply.json"
            )
            for task in (prepare, upload, consume):
                workflow.add_task(task)
            workflow.run()
            print(Path(upload.working_dir, "outputs", "reply.json").read_text())
            print(Path(upload.working_dir, ".dagon", "web_result.json").read_text())
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
```

## Interpretation and inspection

The multipart wrapper explicitly distinguishes a file upload from an ordinary
string. DAGonStar creates `prepare -> upload` from the reference and copies the
file into `upload/inputs/Lesson13/prepare/output/data.txt`. The body is written
to `upload/outputs/reply.json`; the response metadata, including status code,
elapsed time, content hash, and non-secret authentication description, is
written to `.dagon/web_result.json` and the declared `outputs/request.json`.

For authentication, use environment-variable names such as
`{"type": "bearer", "token_env": "SERVICE_TOKEN"}`. Basic and API-key modes
follow the same principle. Never place secret values in a workflow, generated
request file, output, or tutorial. See the [web example](../../examples/web/README.md)
for the repository version and use `python3 -m unittest tests.test_web -v` for
a deterministic regression check.
