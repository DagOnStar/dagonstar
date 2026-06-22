"""Run an end-to-end LLM workflow against a local OpenAI-compatible mock."""

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType


class MockChatCompletionsHandler(BaseHTTPRequestHandler):
    """A tiny deterministic Chat Completions server used only by this example."""

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        size = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(size).decode("utf-8"))
        content = request["messages"][-1]["content"]
        response = {
            "id": "mock-completion",
            "choices": [{"message": {"role": "assistant", "content": "Mock summary: " + content}}],
        }
        payload = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockChatCompletionsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="dagon-llm-example-") as scratch:
            workflow = Workflow("LocalMockLLM", config={
                "batch": {"scratch_dir_base": scratch, "run_base": "", "threads": "1"},
                "dagon_service": {"use": "False", "route": "http://localhost:57000"},
                "ftp_pub": {"ip": "localhost"},
                "slurm": {"partition": ""},
                "llm.local_mock": {
                    "endpoint": "http://127.0.0.1:%s" % server.server_port,
                    "api_key": "example-key-not-a-secret",
                    "model": "mock-chat",
                },
            })
            produce = DagonTask(
                TaskType.BATCH, "prepare_report",
                "mkdir -p output; printf 'temperature increased by 1.2 C' > output/report.txt",
            )
            summarize = DagonTask(
                TaskType.LLM, "summarize_report",
                {"messages": [{"role": "user", "content": "Summarize this report: {report}"}]},
                provider="local_mock",
                input_files={"report": "workflow:///prepare_report/output/report.txt"},
            )
            workflow.add_task(produce)
            workflow.add_task(summarize)
            workflow.run()
            response_path = Path(summarize.working_dir, "response.json")
            print(response_path.read_text(encoding="utf-8"))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
