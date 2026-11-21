"""DAGonService client: token, URL encoding, and shell-safe scratch names."""

import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import dagon
from dagon.api import API
from dagon.task import DagonTask, TaskType


class _Recorder(BaseHTTPRequestHandler):
    requests = []

    def _reply(self, code, body):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length) if length else b""
        _Recorder.requests.append((self.command, self.path, self.headers.get("Authorization"), payload))

    def do_HEAD(self):
        self._record()
        self._reply(200, "")

    def do_POST(self):
        self._record()
        self._reply(201, {"id": "0123456789abcdef01234567"})

    def do_PUT(self):
        self._record()
        self._reply(200, {"status": "ok"})

    def do_GET(self):
        self._record()
        self._reply(200, {"status": "ok", "task": {}, "host": "localhost"})

    def log_message(self, *args):
        pass


class ServiceClientTest(unittest.TestCase):
    def setUp(self):
        _Recorder.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%d" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_token_is_sent_as_bearer(self):
        api = API(self.url + "/", token="s3cret")
        api.update_task_status("wid", "A", "RUNNING")
        method, path, auth, _ = _Recorder.requests[-1]
        self.assertEqual((method, path, auth), ("PUT", "/changestatus/wid/A/RUNNING", "Bearer s3cret"))

    def test_no_token_sends_no_header(self):
        API(self.url).update_task_status("wid", "A", "RUNNING")
        self.assertIsNone(_Recorder.requests[-1][2])

    def test_values_and_names_are_url_encoded(self):
        api = API(self.url)
        api.update_task("wid", "C$x", "working_dir", "/scratch/a&b #1+2")
        _, path, _, _ = _Recorder.requests[-1]
        self.assertEqual(path, "/update/wid/C%24x/working_dir?value=%2Fscratch%2Fa%26b+%231%2B2")
        api.add_dependency("wid", "step.1", "a b")
        self.assertEqual(_Recorder.requests[-1][1], "/wid/step.1/dependency/a%20b")

    def test_workflow_reads_token_from_config(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        workflow = dagon.Workflow("Tokened", config={
            "dagon_service": {"route": self.url, "use": "True", "token": "t0k"},
            "batch": {"scratch_dir_base": scratch + os.sep}})
        self.assertTrue(workflow.is_api_available)
        create = [r for r in _Recorder.requests if r[0] == "POST"][0]
        self.assertEqual((create[1], create[2]), ("/create", "Bearer t0k"))


class ScratchNameTest(unittest.TestCase):
    def test_scratch_name_is_shell_safe(self):
        task = DagonTask(TaskType.BATCH, "C$x y'z", "true")
        name = task.get_scratch_name()
        self.assertRegex(name, r"^\d+-C_x_y_z$")
        self.assertEqual(DagonTask(TaskType.BATCH, "step.1-a_b", "true").get_scratch_name().split("-", 1)[1],
                         "step.1-a_b")

    def test_task_with_dollar_in_name_runs(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, True)
        workflow = dagon.Workflow("Dollar", config={
            "dagon_service": {"use": "False"},
            "batch": {"scratch_dir_base": scratch + os.sep, "remove_dir": "False"}})
        producer = DagonTask(TaskType.BATCH, "A", "echo hi > f.txt")
        consumer = DagonTask(TaskType.BATCH, "C$x", "cat workflow:///A/f.txt > g.txt")
        workflow.add_task(producer)
        workflow.add_task(consumer)
        workflow.make_dependencies()
        workflow.run()
        self.assertEqual(consumer.status, dagon.Status.FINISHED)
        with open(os.path.join(consumer.working_dir, "g.txt")) as handle:
            self.assertEqual(handle.read().strip(), "hi")


if __name__ == "__main__":
    unittest.main()
