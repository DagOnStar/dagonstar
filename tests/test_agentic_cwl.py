"""Executable CWL v1.2 export and the packaged agent runner."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dagon import Workflow
from dagon.task import DagonTask, TaskType
from tests.agentic_fixtures import DATA, FIXTURE_INI, SECRET, agent_task
from tests.helpers import minimal_config

ROOT = Path(__file__).resolve().parents[1]


def environment():
    env = dict(os.environ)
    extra = [item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item]
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT)] + extra)
    return env


def graph(portable=False, name="agentic-cwl"):
    config = minimal_config()
    config["llm.private"] = {"endpoint": "https://private.invalid", "api_key": SECRET}
    workflow = Workflow(name, config=config, portable_emulation=portable)
    workflow.add_task(DagonTask(TaskType.BATCH, "prepare", "mkdir -p outputs; printf '%s' '"
                                + json.dumps(DATA) + "' > outputs/observations.json"))
    workflow.add_task(agent_task())
    copy = "mkdir -p outputs; cp workflow:///quality_control/outputs/result.json outputs/copy.json"
    workflow.add_task(DagonTask(TaskType.BATCH, "consume", copy))
    return workflow


class AgenticCWLExportTests(unittest.TestCase):
    def export(self, workflow, directory, name="workflow.cwl"):
        target = Path(directory, name)
        workflow.saveAsCWL(target)
        return target, json.loads(target.read_text(encoding="utf-8"))

    def test_export_is_deterministic_executable_and_credential_free(self):
        with tempfile.TemporaryDirectory() as directory:
            first, document = self.export(graph(), directory, "first.cwl")
            second, _ = self.export(graph(), directory, "second.cwl")
            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))
        text = json.dumps(document)
        for forbidden in (SECRET, "private.invalid", directory, "/tmp/"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(document["inputs"], {"dagon_config": "File"})
        agent = document["steps"]["quality_control"]
        tool = agent["run"]
        self.assertEqual(tool["baseCommand"], ["dagon-agent-runner", "run"])
        self.assertIn("$(inputs.dagon_config.path)", tool["arguments"])
        self.assertEqual(agent["in"]["in_0"], "prepare/file_outputs_observations_json")
        self.assertEqual(agent["in"]["dagon_config"], "dagon_config")
        self.assertEqual(tool["outputs"]["result"]["outputBinding"]["glob"], "outputs/result.json")
        self.assertEqual(tool["hints"]["dagon:AgenticTask"]["agent_profile"], "quality-local")
        producer = document["steps"]["prepare"]
        self.assertIn("file_outputs_observations_json", producer["out"])
        consumer = document["steps"]["consume"]
        self.assertEqual(consumer["in"]["quality_control_result"], "quality_control/result")
        self.assertIn("$(inputs.quality_control_result.path)", consumer["run"]["arguments"][0])
        self.assertIn("quality_control_evaluation", document["outputs"])
        self.assertEqual(document["$namespaces"]["dagon"], "https://dagonstar.org/cwl#")

    def test_workflows_without_agentic_tasks_are_unchanged(self):
        workflow = Workflow("plain", config=minimal_config())
        workflow.add_task(DagonTask(TaskType.BATCH, "a", "echo a > a.txt"))
        workflow.add_task(DagonTask(TaskType.BATCH, "b", "cat workflow:///a/a.txt"))
        with tempfile.TemporaryDirectory() as directory:
            _, document = self.export(workflow, directory)
        self.assertEqual(document["inputs"], {})
        self.assertEqual(document["steps"]["b"]["run"]["baseCommand"], ["/bin/sh", "-c", "cat workflow:///a/a.txt"])
        self.assertNotIn("$namespaces", document)

    @unittest.skipUnless(shutil.which("cwltool") and shutil.which("dagon-agent-runner"),
                         "cwltool and an installed dagon-agent-runner are required")
    def test_cwltool_validates_and_executes_producer_agent_consumer(self):
        for portable in (False, True):
            with self.subTest(portable=portable), tempfile.TemporaryDirectory() as directory:
                target, _ = self.export(graph(portable), directory)
                ini = Path(directory, "dagon.ini")
                ini.write_text(FIXTURE_INI, encoding="utf-8")
                job = Path(directory, "job.json")
                job.write_text(json.dumps({"dagon_config": {"class": "File", "path": str(ini)}}), encoding="utf-8")
                subprocess.run(["cwltool", "--validate", str(target)], check=True, capture_output=True, text=True)
                completed = subprocess.run(["cwltool", "--no-container", "--outdir", str(Path(directory, "out")),
                                            str(target), str(job)], capture_output=True, text=True, cwd=directory)
                self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
                outputs = json.loads(completed.stdout)
                result = json.loads(Path(outputs["quality_control_result"]["path"]).read_text(encoding="utf-8"))
                evaluation = json.loads(Path(outputs["quality_control_evaluation"]["path"]).read_text(encoding="utf-8"))
                self.assertEqual([item["id"] for item in result["observations"]], [1, 2, 3, 4])
                self.assertTrue(evaluation["accepted"])
                self.assertEqual(evaluation["execution"]["portable_emulation"], portable)
                self.assertTrue(outputs["consume_completed"])


class AgentRunnerTests(unittest.TestCase):
    def run_runner(self, directory, profile_ini=FIXTURE_INI, bind=True, spec=None):
        Path(directory, "dagon.ini").write_text(profile_ini, encoding="utf-8")
        source = Path(directory, "observations.json")
        source.write_text(json.dumps(DATA), encoding="utf-8")
        Path(directory, "task.json").write_text(json.dumps(spec or agent_task().portable_spec()), encoding="utf-8")
        command = [sys.executable, "-m", "dagon.agentic.runner", "run", "--spec", "task.json", "--config", "dagon.ini",
                   "--workdir", "work"]
        if bind:
            command += ["--bind", "workflow:///prepare/outputs/observations.json=" + str(source)]
        return subprocess.run(command, cwd=directory, env=environment(), capture_output=True, text=True)

    def test_runner_accepts_and_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = self.run_runner(directory)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["accepted"])
            self.assertTrue(Path(directory, "work", ".dagon/agentic/commit.json").is_file())

    def test_runner_exit_codes_for_configuration_and_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.run_runner(directory, bind=False).returncode, 1)
            self.assertEqual(self.run_runner(directory, profile_ini="[other]\nx=1\n").returncode, 1)
            malformed = FIXTURE_INI + "\n[agent_provider.bad]\nimplementation = mock\nscenario = malformed\n" \
                                      "[agent.bad]\nprovider = bad\nmax_steps = 2\ntimeout_seconds = 10\n"
            completed = self.run_runner(directory, profile_ini=malformed,
                                        spec=agent_task(agent="bad").portable_spec())
            self.assertEqual(completed.returncode, 2, completed.stderr)
            self.assertFalse(Path(directory, "work", "outputs/result.json").exists())
            error = json.loads(Path(directory, "work", ".dagon/agentic/runner-error.json").read_text(encoding="utf-8"))
            self.assertEqual(error["error"], "not_accepted")


if __name__ == "__main__":
    unittest.main()
