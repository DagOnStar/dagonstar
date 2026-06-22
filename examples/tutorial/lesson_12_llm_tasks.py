"""Runnable source for Tutorial Lesson 12; run from the repository root."""

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


class MockChatHandler(BaseHTTPRequestHandler):
    """A deterministic, local subset of the Chat Completions protocol."""

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        content = request["messages"][-1]["content"]
        response = {"choices": [{"message": {"role": "assistant", "content": "Mock summary: " + content}}]}
        payload = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockChatHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="dagon-llm-lesson-") as scratch:
            config = {
                "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
                "dagon_service": {"use": "False", "route": "http://localhost:57000"},
                "ftp_pub": {"ip": "localhost"}, "slurm": {"partition": ""},
                "llm.local_mock": {"endpoint": "http://127.0.0.1:%s" % server.server_port,
                                   "api_key": "example-key-not-a-secret", "model": "mock-chat"},
            }
            workflow = Workflow("Lesson12", config=config)
            workflow.add_task(DagonTask(TaskType.BATCH, "prepare_report", "mkdir -p output; printf 'temperature increased by 1.2 C' > output/report.txt"))
            summarize = DagonTask(TaskType.LLM, "summarize_report", {"messages": [{"role": "user", "content": "Summarize this report: {report}"}]}, provider="local_mock", input_files={"report": "workflow:///prepare_report/output/report.txt"})
            workflow.add_task(summarize)
            workflow.run()
            print(Path(summarize.working_dir, "response.json").read_text(encoding="utf-8"))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
