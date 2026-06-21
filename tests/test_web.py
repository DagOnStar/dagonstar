import base64
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dagon.task import DagonTask, TaskType
from dagon.web.runner import run
from tests.helpers import minimal_config
from dagon import Workflow


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/status"):
            self.send_response(418)
        elif self.path.startswith("/basic"):
            self.send_response(200 if self.headers.get("Authorization") == "Basic dTpw" else 401)
        elif self.path.startswith("/auth"):
            expected = "Bearer token-value"
            self.send_response(200 if self.headers.get("Authorization") == expected else 401)
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"path": self.path}).encode())

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"body": body.decode("utf-8")}).encode())

    def log_message(self, *args):
        pass


class WebTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:%s" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _run(self, spec):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".dagon").mkdir()
            request = root / ".dagon/web_request.json"
            request.write_text(json.dumps(spec))
            result = run(str(request))
            body_file = root / "outputs/body.json"
            return result, (root / ".dagon/web_result.json").read_text(), body_file.read_text() if body_file.is_file() else ""

    def test_runner_get_query_metadata_and_environment_auth(self):
        old = os.environ.get("WEB_TEST_TOKEN")
        os.environ["WEB_TEST_TOKEN"] = "token-value"
        try:
            result, metadata, body = self._run({"method": "GET", "url": self.url + "/auth", "query": {"station": "napoli"},
                                      "auth": {"type": "bearer", "token_env": "WEB_TEST_TOKEN"},
                                      "outputs": {"body": "body.json", "headers": "headers.json", "metadata": "meta.json"}})
        finally:
            if old is None:
                os.environ.pop("WEB_TEST_TOKEN", None)
            else:
                os.environ["WEB_TEST_TOKEN"] = old
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["auth"], {"type": "bearer", "source": "env:WEB_TEST_TOKEN"})
        self.assertNotIn("token-value", metadata)
        self.assertIn("station=napoli", body)

    def test_json_multipart_and_unexpected_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".dagon").mkdir()
            (root / "inputs").mkdir()
            (root / "inputs/data.txt").write_text("sample")
            request = root / ".dagon/web_request.json"
            request.write_text(json.dumps({"method": "POST", "url": self.url + "/post", "multipart": {"file": {"file": "inputs/data.txt", "content_type": "text/plain"}, "config": {"value": {"fast": True}, "content_type": "application/json"}}, "outputs": {"body": "response.json"}}))
            result = run(str(request))
            self.assertEqual(result["status_code"], 200)
            self.assertIn("sample", (root / "outputs/response.json").read_text())
            request.write_text(json.dumps({"method": "GET", "url": self.url + "/status", "expected_status": 200}))
            with self.assertRaisesRegex(RuntimeError, "Unexpected HTTP status 418"):
                run(str(request))

    def test_workflow_reference_is_staged_and_creates_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            config = minimal_config()
            config["batch"]["scratch_dir_base"] = directory
            workflow = Workflow("Web", config=config)
            producer = DagonTask(TaskType.BATCH, "produce", "mkdir -p output; echo payload > output/input.txt")
            web = DagonTask(TaskType.WEB, "upload", {"method": "POST", "url": self.url + "/post", "multipart": {"dataset": {"file": "workflow:///produce/output/input.txt", "content_type": "text/plain"}}, "outputs": {"body": "reply.json"}})
            workflow.add_task(producer)
            workflow.add_task(web)
            workflow.run()
            self.assertIn(web, producer.nexts)
            self.assertTrue(Path(web.working_dir, "inputs/Web/produce/output/input.txt").is_file())
            self.assertIn("payload", Path(web.working_dir, "outputs/reply.json").read_text())

    def test_basic_and_slurm_command_validation(self):
        task = DagonTask(TaskType.WEB, "web", {"url": self.url, "auth": {"type": "basic", "username_env": "U", "password_env": "P"}}, executor="slurm", resources={"partition": "debug"})
        task.working_dir = "/tmp/web"
        self.assertIn("--partition=debug", task.generate_slurm_command("web_launcher.sh"))
        os.environ["WEB_TEST_USER"] = "u"
        os.environ["WEB_TEST_PASSWORD"] = "p"
        try:
            result, _, _ = self._run({"url": self.url + "/basic", "auth": {"type": "basic", "username_env": "WEB_TEST_USER", "password_env": "WEB_TEST_PASSWORD"}})
        finally:
            os.environ.pop("WEB_TEST_USER", None)
            os.environ.pop("WEB_TEST_PASSWORD", None)
        self.assertEqual(result["status_code"], 200)
        with self.assertRaisesRegex(ValueError, "environment"):
            DagonTask(TaskType.WEB, "unsafe", {"url": self.url, "auth": {"type": "bearer", "token": "nope"}})


if __name__ == "__main__":
    unittest.main()
