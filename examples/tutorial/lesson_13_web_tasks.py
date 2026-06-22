"""Runnable source for Tutorial Lesson 13; run from the repository root."""

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


class EchoHandler(BaseHTTPRequestHandler):
    """Local endpoint used to demonstrate a multipart web task."""

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


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), EchoHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="dagon-web-lesson-") as scratch:
            config = {"batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
                      "dagon_service": {"use": "False", "route": "http://localhost:57000"},
                      "ftp_pub": {"ip": "localhost"}, "slurm": {"partition": ""}}
            workflow = Workflow("Lesson13", config=config)
            workflow.add_task(DagonTask(TaskType.BATCH, "prepare", "mkdir -p output; printf sample > output/data.txt"))
            upload = DagonTask(TaskType.WEB, "upload", {"method": "POST", "url": "http://127.0.0.1:%s/upload" % server.server_port, "multipart": {"dataset": {"file": "workflow:///prepare/output/data.txt", "content_type": "text/plain"}}, "expected_status": 200, "outputs": {"body": "reply.json", "metadata": "request.json"}})
            workflow.add_task(upload)
            workflow.add_task(DagonTask(TaskType.BATCH, "consume", "cat workflow:///upload/outputs/reply.json"))
            workflow.run()
            print(Path(upload.working_dir, "outputs", "reply.json").read_text())
            print(Path(upload.working_dir, ".dagon", "web_result.json").read_text())
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
