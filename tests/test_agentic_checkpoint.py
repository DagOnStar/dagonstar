"""Content- and configuration-aware checkpoint reuse for agentic tasks."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dagon.agentic import AgenticNotAccepted, ToolSpec
from dagon.agentic.engine import COMMIT_MANIFEST, AgentEngine
from dagon.agentic.registry import snapshot
from tests.agentic_fixtures import DATA, agent_task, agent_workflow, prepared


class AgenticCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.scratch = self.directory.name
        self.workflow = agent_workflow("resume", self.scratch)
        self.task = prepared(self.workflow, self.scratch)
        self.task.execute()

    def tearDown(self):
        self.directory.cleanup()

    def rerun(self, task=None, cfg=None, data=None):
        """Return a fresh task in a fresh workflow sharing the recorded checkpoints."""
        workflow = agent_workflow("resume", self.scratch)
        if cfg:
            for section, values in cfg.items():
                workflow.cfg[section].update(values)
        task = prepared(workflow, self.scratch, task, data=data)
        workflow.checkpoints.update(json.loads(json.dumps(self.workflow.checkpoints)))
        return task

    def test_identical_identity_reuses_the_accepted_run(self):
        again = self.rerun()
        self.assertTrue(again.reuse_checkpoint())
        self.assertEqual(again.working_dir, self.task.working_dir)
        self.assertTrue(again.fair_checkpoint_reused)
        self.assertTrue(again.agentic_report["accepted"])
        with mock.patch.object(AgentEngine, "run") as engine:
            again.execute()
        engine.assert_not_called()

    def test_tampered_or_missing_artifacts_are_not_reused(self):
        for relative in ("outputs/result.json", "outputs/evaluation.json", "outputs/trace.json", COMMIT_MANIFEST):
            with self.subTest(relative):
                target = Path(self.task.working_dir, relative)
                original = target.read_bytes()
                target.write_bytes(original.replace(b"1", b"7", 1) + b" ")
                self.assertFalse(self.rerun().reuse_checkpoint())
                target.unlink()
                self.assertFalse(self.rerun().reuse_checkpoint())
                target.write_bytes(original)
                self.assertTrue(self.rerun().reuse_checkpoint())

    def test_changed_contract_input_profile_or_versions_invalidate_reuse(self):
        self.assertFalse(self.rerun(agent_task(evaluation={"threshold": 0.9})).reuse_checkpoint())
        self.assertFalse(self.rerun(cfg={"agent.quality-local": {"max_steps": "7"}}).reuse_checkpoint())
        self.assertFalse(self.rerun(data={"observations": DATA["observations"][:4]}).reuse_checkpoint())
        self.assertTrue(self.rerun(data=DATA).reuse_checkpoint())
        registry = snapshot()
        registry.register_tool(ToolSpec("inspect_records", "2.0.0", "new version",
                                        "dagon.agentic.builtins:inspect_records", side_effect="read"), replace=True)
        self.assertFalse(self.rerun(agent_task(registry=registry)).reuse_checkpoint())

    def test_failed_runs_are_never_reused(self):
        workflow = agent_workflow("failed", self.scratch)
        task = prepared(workflow, self.scratch, agent_task(agent="malformed"))
        with self.assertRaises(AgenticNotAccepted):
            task.execute()
        self.assertEqual(workflow.checkpoints[task.checkpoint_key()]["code"], 1)
        self.assertFalse(task.reuse_checkpoint())

    def test_crash_during_publication_leaves_no_reusable_state_and_is_cleaned(self):
        workflow = agent_workflow("crash", self.scratch)
        fixed = Path(self.scratch, "fixed-agent")
        task = prepared(workflow, self.scratch, agent_task(working_dir=str(fixed)))
        original = AgentEngine._write_json

        def crash(engine, target, value):
            if target.name == "commit.json":
                raise OSError("simulated crash before the commit manifest")
            return original(engine, target, value)

        with mock.patch.object(AgentEngine, "_write_json", crash):
            with self.assertRaises(OSError):
                task.execute()
        self.assertFalse(Path(fixed, COMMIT_MANIFEST).exists())
        self.assertFalse(task.reuse_checkpoint())
        # A stale result left by a crashed process is removed before the next attempt.
        Path(fixed, "outputs", "result.json").write_text("{\"stale\": true}", encoding="utf-8")
        workflow.checkpoints.clear()
        task.execute()
        self.assertNotIn("stale", Path(fixed, "outputs", "result.json").read_text(encoding="utf-8"))
        self.assertTrue(task.reuse_checkpoint())


if __name__ == "__main__":
    unittest.main()
