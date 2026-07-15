"""Invoke a credential-free local HTTP function fixture."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dagon import Workflow
from dagon.task import DagonTask, TaskType


class Function(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        value = request["data"]["inputs"]["value"]
        response = json.dumps({"status": "succeeded", "outputs": {"result": {"value": value * 2}}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("X-Request-ID", "local-http-1")
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Function)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    workflow = Workflow("FaaS-HTTP", config={"batch": {"remove_dir": False, "scratch_dir_base": "/tmp"}})
    workflow.add_task(DagonTask(TaskType.FAAS, "double", provider="http", function="local-double",
        inputs={"value": 4}, outputs={"result": "result.json"},
        provider_options={"http": {"endpoint": "http://127.0.0.1:%d/invoke" % server.server_port}}))
    workflow.run()
finally:
    server.shutdown()
    server.server_close()
