"""A self-contained local HTTP workflow; run with python3 download_and_process.py."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dagon import Workflow
from dagon.task import DagonTask, TaskType


class EchoHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"body": body.decode("utf-8")}).encode("utf-8"))

    def log_message(self, *_):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), EchoHandler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    workflow = Workflow("web-example")
    workflow.add_task(DagonTask(TaskType.BATCH, "prepare", "mkdir -p output; echo sample > output/data.txt"))
    workflow.add_task(DagonTask(TaskType.WEB, "upload", {"method": "POST", "url": "http://127.0.0.1:%s/upload" % server.server_port, "multipart": {"dataset": {"file": "workflow:///prepare/output/data.txt", "content_type": "text/plain"}}, "outputs": {"body": "reply.json", "metadata": "request.json"}}))
    workflow.add_task(DagonTask(TaskType.NATIVE, "summarize", "tasks:summarize_response", inputs={"response_file": "workflow:///upload/outputs/reply.json"}, outputs={"summary_file": "summary.json"}))
    workflow.run()
finally:
    server.shutdown()
