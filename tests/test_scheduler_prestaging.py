"""Scheduler-aware pre-staging (``pre_stage``) for local Slurm tasks.

No Slurm installation is needed: ``sbatch`` is replaced by
``examples/dataflow/slurm/mock_scheduler.py`` (which runs the job script with
the local bash and records what existed at submission time) or by mocks of
``on_execute``.  The context discovery script is replaced by a canned one so
the tests need no network access.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from dagon import Workflow
from dagon.batch import Batch, Slurm
from dagon.platform_support import bash_executable
from dagon.prestage import (
    DESTINATION_IDENTITY_NAME, IDENTITY_NAME, INTEGRITY_CONTENT, INTEGRITY_EXISTENCE, LOCK_NAME, MARKER_NAME,
    PRE_STAGE_POLICY_VERSION, PreparedTask, PreStageConfigurationError, SchedulerSubmissionError,
    ScheduledExecutionError, StageInFailedError, StageInput, TaskPhase, estimated_core_hours_saved,
    identity_digest, identity_script, validate_pre_stage, validate_reference_path,
)
from dagon.stager.base import DataMover, Stager, StagerMover
from dagon.task import DagonTask, Task, TaskType, parsable_job_id

from tests.helpers import (
    CANNED_CONTEXT_INFO, canned_context_script, load_mock_scheduler, make_workflow, minimal_config,
    scratch_config,
)

ROOT = Path(__file__).resolve().parents[1]
CONTEXT_OUTPUT = "\n************************************\n" + json.dumps(CANNED_CONTEXT_INFO) + "\n"
mock_scheduler = load_mock_scheduler()


def no_network_context():
    return mock.patch.object(Task, "get_how_im_script", canned_context_script)


class ConfigurationTests(unittest.TestCase):
    def test_workflow_default_is_false(self):
        self.assertIs(False, make_workflow().pre_stage)

    def test_task_default_is_none_and_explicit_values_are_kept(self):
        self.assertIsNone(Slurm("t", "true").pre_stage)
        self.assertIs(True, Slurm("t", "true", pre_stage=True).pre_stage)
        self.assertIs(False, Slurm("t", "true", pre_stage=False).pre_stage)
        self.assertIs(True, DagonTask(TaskType.SLURM, "t", "true", pre_stage=True).pre_stage)

    def test_invalid_values_are_rejected(self):
        for value in ("true", "False", 1, 0, "", [], 1.0):
            with self.subTest(value=value):
                with self.assertRaises(PreStageConfigurationError):
                    Workflow("w", config=minimal_config(), pre_stage=value)
                with self.assertRaises(PreStageConfigurationError):
                    Slurm("t", "true", pre_stage=value)
        with self.assertRaises(PreStageConfigurationError):
            Workflow("w", config=minimal_config(), pre_stage=None)
        self.assertIsNone(validate_pre_stage(None))

    def test_configuration_error_is_a_value_error(self):
        self.assertTrue(issubclass(PreStageConfigurationError, ValueError))

    def test_positional_api_is_unchanged(self):
        task = Slurm("t", "true", "c", "p", 2, 100, "00:10:00", 1, 2, "/scratch/t")
        self.assertEqual(("c", "p", 2, 100, "00:10:00", 1, 2, "/scratch/t"),
                         (task.comment, task.partition, task.ntasks, task.memory, task.time, task.nodes,
                          task.ntasks_per_node, task.working_dir))
        self.assertIsNone(task.pre_stage)

    def test_resolution_matrix(self):
        cases = [
            (False, None, False), (False, False, False), (False, True, True),
            (True, None, True), (True, False, False), (True, True, True),
        ]
        for workflow_value, task_value, expected in cases:
            with self.subTest(workflow=workflow_value, task=task_value):
                workflow = Workflow("w", config=minimal_config(), pre_stage=workflow_value)
                task = Slurm("t", "true", pre_stage=task_value)
                workflow.add_task(task)
                self.assertIs(expected, task.resolve_pre_stage())
                self.assertIs(task_value, task.pre_stage)  # never mutated

    def test_inheritance_follows_later_workflow_changes(self):
        workflow = make_workflow()
        task = Slurm("t", "true")
        workflow.add_task(task)
        self.assertFalse(task.resolve_pre_stage())
        workflow.pre_stage = True
        self.assertTrue(task.resolve_pre_stage())

    def test_unsupported_backends_keep_legacy_semantics_when_inheriting(self):
        workflow = Workflow("w", config=minimal_config(), pre_stage=True)
        task = Batch("b", "true")
        workflow.add_task(task)
        self.assertFalse(task.resolve_pre_stage())
        self.assertFalse(task.pre_stage_capable)

    def test_explicit_request_on_unsupported_backend_is_rejected(self):
        task = Batch("b", "true")
        task.pre_stage = True
        with self.assertRaisesRegex(PreStageConfigurationError, "only Slurm and RemoteSlurm"):
            make_workflow().add_task(task)

    def test_beeond_explicit_request_is_rejected(self):
        for spec in ("task", "workflow", {"scope": "task"}):
            with self.subTest(spec=spec):
                task = Slurm("t", "true", beeond=spec, pre_stage=True)
                with self.assertRaisesRegex(PreStageConfigurationError, "BeeOND"):
                    make_workflow().add_task(task)

    def test_beeond_inherited_request_falls_back_with_warning(self):
        workflow = Workflow("w", config=minimal_config(), pre_stage=True)
        task = Slurm("t", "true", beeond="task")
        workflow.add_task(task)
        with self.assertLogs(level="WARNING") as logs:
            self.assertFalse(task.resolve_pre_stage())
        self.assertIn("BeeOND", "\n".join(logs.output))

    def test_scheduler_stager_mover_is_rejected(self):
        # StagerMover.SLURM submits copy jobs: that would request scheduler
        # resources before stage-in has succeeded.
        workflow = make_workflow()
        task = Slurm("t", "true", pre_stage=True)
        task.set_stager_mover(StagerMover.SLURM)
        with self.assertRaisesRegex(PreStageConfigurationError, "StagerMover.SLURM"):
            workflow.add_task(task)
        workflow = Workflow("w", config=minimal_config(), pre_stage=True)
        workflow.set_stager_mover(StagerMover.SLURM)
        inherited = Slurm("t", "true")
        workflow.add_task(inherited)
        with self.assertLogs(level="WARNING") as logs:
            self.assertFalse(inherited.resolve_pre_stage())
        self.assertIn("StagerMover.SLURM", "\n".join(logs.output))
        for mover in (StagerMover.NORMAL, StagerMover.PARALLEL, StagerMover.NORMAL.value):
            with self.subTest(mover=mover):
                eligible = Slurm("t", "true", pre_stage=True)
                eligible.set_stager_mover(mover)
                make_workflow().add_task(eligible)
                self.assertTrue(eligible.resolve_pre_stage())

    def test_shared_working_directory_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            shared = os.path.join(directory, "shared")
            workflow = make_workflow()
            workflow.add_task(Slurm("first", "true", working_dir=shared))
            with self.assertRaisesRegex(PreStageConfigurationError, "shared with task first"):
                workflow.add_task(Slurm("second", "true", working_dir=shared + "/", pre_stage=True))
            workflow = Workflow("w", config=minimal_config(), pre_stage=True)
            first = Slurm("first", "true", working_dir=shared)
            second = Slurm("second", "true", working_dir=os.path.join(shared, ".", ""))
            workflow.add_task(first)
            workflow.add_task(second)
            with self.assertLogs(level="WARNING") as logs:
                self.assertFalse(second.resolve_pre_stage())
                self.assertFalse(first.resolve_pre_stage())
            self.assertIn("shared with task", "\n".join(logs.output))
            # The same path on another host is a different directory.
            workflow = make_workflow()
            local = Slurm("local", "true", working_dir=shared)
            elsewhere = Slurm("elsewhere", "true", working_dir=shared, pre_stage=True)
            elsewhere.ip = "192.0.2.1"
            workflow.add_task(local)
            workflow.add_task(elsewhere)
            self.assertIsNone(elsewhere.shared_working_dir_task())
            self.assertIsNone(Slurm("solo", "true", working_dir=shared).shared_working_dir_task())

    def test_unsafe_references_are_rejected(self):
        for workflow_name, task_name, local_path in (("wf", "A", "/../outside"), ("wf", "A", "/x/../../y"),
                                                     ("..", "A", "/a.txt"), ("wf", "..", "/a.txt"),
                                                     ("wf", "", "/a.txt"), ("wf", "A", "/"),
                                                     ("wf", "A", "/x\\..\\y")):
            with self.subTest(reference=(workflow_name, task_name, local_path)):
                with self.assertRaises(PreStageConfigurationError):
                    validate_reference_path(workflow_name, task_name, local_path)
        for local_path in ("/a.txt", "/dir/a*.txt", "//a.txt", "/./a.txt", "/a..b.txt"):
            validate_reference_path("wf", "A", local_path)

    def test_parallel_mode_is_not_eligible(self):
        workflow = make_workflow()
        task = Slurm("t", "true", pre_stage=True)
        workflow.add_task(task)
        task.set_mode("parallel")
        with self.assertRaisesRegex(PreStageConfigurationError, "parallel"):
            task.resolve_pre_stage()

    def test_json_round_trip(self):
        workflow = Workflow("w", config=minimal_config(), pre_stage=True)
        workflow.add_task(Slurm("a", "true", pre_stage=False))
        workflow.add_task(Slurm("b", "true"))
        data = json.loads(json.dumps(workflow.as_json()))
        self.assertIs(True, data["pre_stage"])
        self.assertIs(False, data["tasks"]["a"]["pre_stage"])
        self.assertNotIn("pre_stage", data["tasks"]["b"])
        clone = Workflow("x", config=minimal_config(), jsonload=data)
        self.assertTrue(clone.pre_stage)
        self.assertEqual([False, None], [task.pre_stage for task in clone.tasks])

    def test_default_json_is_unchanged(self):
        workflow = make_workflow()
        workflow.add_task(Slurm("a", "true"))
        data = workflow.as_json()
        self.assertNotIn("pre_stage", data)
        self.assertNotIn("pre_stage", data["tasks"]["a"])

    def test_cwl_export_is_independent_of_pre_stage(self):
        documents = []
        for enabled in (False, True):
            workflow = Workflow("w", config=minimal_config(), pre_stage=enabled)
            workflow.add_task(Slurm("a", "echo a > a.txt"))
            workflow.add_task(Slurm("b", "cat workflow:///a/a.txt", pre_stage=enabled))
            with tempfile.TemporaryDirectory() as directory:
                target = os.path.join(directory, "w.cwl")
                workflow.saveAsCWL(target)
                with open(target, encoding="utf-8") as stream:
                    documents.append(stream.read())
        self.assertEqual(documents[0], documents[1])
        self.assertNotIn("pre_stage", documents[1])

    def test_core_hour_estimate(self):
        self.assertEqual(200.0, estimated_core_hours_saved(200, 3600))
        self.assertEqual(10.0, estimated_core_hours_saved(200, 180))
        self.assertIsNone(estimated_core_hours_saved(None, 10))
        self.assertIsNone(estimated_core_hours_saved(4, None))
        task = Slurm("t", "true", nodes=4, ntasks_per_node=50)
        self.assertEqual(200, task.requested_cores())
        self.assertEqual(8, Slurm("t", "true", ntasks=8).requested_cores())
        self.assertIsNone(Slurm("t", "true").requested_cores())


def three_task_workflow(scratch=None, workflow_pre_stage=False, consumer_pre_stage=None, command=None):
    config = scratch_config(scratch) if scratch else minimal_config()
    workflow = Workflow("wf", config=config, pre_stage=workflow_pre_stage)
    first = Slurm("A", "echo alpha > a.txt", working_dir=None if scratch else "/scratch/A")
    second = Slurm("B", "echo beta > b.txt", working_dir=None if scratch else "/scratch/B")
    consumer = Slurm("C", command or "cat workflow:///A/a.txt workflow:///B/b.txt > c.txt",
                     partition="p", working_dir=None if scratch else "/scratch/C", pre_stage=consumer_pre_stage)
    for task in (first, second, consumer):
        workflow.add_task(task)
    workflow.make_dependencies()
    return workflow, first, second, consumer


class LauncherGenerationTests(unittest.TestCase):
    """Command generation with mocked context discovery."""

    def prepare(self, consumer, strict):
        for producer in consumer.prevs:
            producer.info = dict(CANNED_CONTEXT_INFO)
        with mock.patch.object(Slurm, "on_execute", return_value={"code": 0, "output": CONTEXT_OUTPUT}):
            return consumer.prepare_task(consumer.command, strict_staging=strict)

    def test_legacy_launcher_is_byte_for_byte_unchanged(self):
        _workflow, _a, _b, consumer = three_task_workflow()
        for producer in consumer.prevs:
            producer.info = dict(CANNED_CONTEXT_INFO)
        with mock.patch.object(Slurm, "on_execute", return_value={"code": 0, "output": CONTEXT_OUTPUT}):
            launcher = consumer.post_process_command(consumer.pre_process_command(consumer.command))
        expected = (ROOT / "tests" / "fixtures" / "legacy_slurm_launcher.sh").read_text(encoding="utf-8")
        self.assertEqual(expected, launcher)

    def test_prepared_task_reproduces_the_legacy_launcher(self):
        _workflow, _a, _b, consumer = three_task_workflow()
        prepared = self.prepare(consumer, strict=False)
        self.assertIsInstance(prepared, PreparedTask)
        expected = (ROOT / "tests" / "fixtures" / "legacy_slurm_launcher.sh").read_text(encoding="utf-8")
        self.assertEqual(expected, consumer.post_process_command(prepared.legacy_launcher()))

    def test_manifest_and_substitutions_cover_multiple_producers(self):
        _workflow, _a, _b, consumer = three_task_workflow()
        prepared = self.prepare(consumer, strict=True)
        self.assertEqual(["workflow:///A/a.txt", "workflow:///B/b.txt"],
                         [item.reference for item in prepared.inputs])
        self.assertEqual("cat /scratch/C/.dagon/inputs/wf/A//a.txt /scratch/C/.dagon/inputs/wf/B//b.txt > c.txt",
                         prepared.resolved_command)
        self.assertEqual(["/scratch/C/.dagon/inputs/wf/A//a.txt", "/scratch/C/.dagon/inputs/wf/B//b.txt"],
                         [item.destination for item in prepared.inputs])

    def test_staging_appears_only_in_the_stage_in_script(self):
        _workflow, _a, _b, consumer = three_task_workflow()
        prepared = self.prepare(consumer, strict=True)
        compute = prepared.compute_launcher()
        stage = prepared.stage_in_script()
        self.assertNotIn("cp -r", compute)
        self.assertNotIn("# Start staging in", compute)
        self.assertIn(prepared.resolved_command, compute)
        self.assertEqual(2, stage.count("cmd='cp -r"))  # single-quoted template in strict mode
        self.assertNotIn(prepared.resolved_command, stage)  # never runs the user command
        self.assertIn("dagon_verify_staged /scratch/C/.dagon/inputs/wf/A//a.txt", stage)
        self.assertIn("rm -f /scratch/C/.dagon/" + MARKER_NAME, stage)

    def test_generated_scripts_are_valid_bash(self):
        _workflow, _a, _b, consumer = three_task_workflow()
        prepared = self.prepare(consumer, strict=True)
        for script in (prepared.stage_in_script(), consumer.post_process_command(prepared.compute_launcher())):
            completed = subprocess.run([bash_executable(), "-n"], input=script, text=True, capture_output=True)
            self.assertEqual(0, completed.returncode, completed.stderr)

    def test_beeond_prologue_stays_in_the_compute_launcher(self):
        prepared = PreparedTask(working_dir="/w", header="#! /bin/bash\ncode=0\n", prologue="PROLOGUE\n",
                                stage_blocks=["BLOCK\n"], invoke="RUN\n", resolved_command="run",
                                inputs=[StageInput("workflow:///a/x", "wf", "a", "/x", "/a//x", "/w/x")])
        self.assertIn("PROLOGUE", prepared.compute_launcher())
        self.assertNotIn("PROLOGUE", prepared.stage_in_script())
        self.assertIn("BLOCK", prepared.stage_in_script())
        self.assertNotIn("BLOCK", prepared.compute_launcher())

    def test_empty_inputs_produce_a_no_op_stage_script(self):
        prepared = PreparedTask(working_dir="/w", header="", prologue="", stage_blocks=[], invoke="",
                                resolved_command="true")
        script = prepared.stage_in_script()
        self.assertIn("no workflow:// inputs", script)
        self.assertNotIn("dagon_verify_staged /", script)
        self.assertIn("stage-in: no workflow:// inputs", prepared.planned_order())


class LifecycleOrderTests(unittest.TestCase):
    """Order of context discovery, stage-in, and submission with ``on_execute`` mocked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_consumer(self, workflow_pre_stage, consumer_pre_stage, stage_code=0, submit_result=None):
        workflow, first, second, consumer = three_task_workflow(
            self.tmp.name, workflow_pre_stage=workflow_pre_stage, consumer_pre_stage=consumer_pre_stage)
        for producer in (first, second):
            producer.info = dict(CANNED_CONTEXT_INFO)
            producer.working_dir = os.path.join(self.tmp.name, producer.name)
        calls = []

        def on_execute(task, script, script_name):
            calls.append(("on_execute", script_name, script))
            if script_name == "context.sh":
                return {"code": 0, "output": CONTEXT_OUTPUT, "message": ""}
            return submit_result or {"code": 0, "output": "7\n", "message": ""}

        def run_stage_in(task, script):
            calls.append(("stage_in", "stage_in.sh", script))
            return {"code": stage_code, "output": "", "message": "cp: missing" if stage_code else ""}

        def write_marker(task, content):
            calls.append(("marker", MARKER_NAME, content))

        def read_scratch_file(task, filepath):
            return "" if filepath.endswith((IDENTITY_NAME, DESTINATION_IDENTITY_NAME)) else None

        with mock.patch.object(Slurm, "on_execute", on_execute), \
                mock.patch.object(Slurm, "run_stage_in", run_stage_in), \
                mock.patch.object(Slurm, "write_stage_marker", write_marker), \
                mock.patch.object(Slurm, "read_scratch_file", read_scratch_file):
            try:
                consumer.execute()
                error = None
            except Exception as exc:  # inspected by the tests
                error = exc
        return consumer, calls, error

    def test_default_keeps_staging_inside_the_launcher(self):
        consumer, calls, error = self.run_consumer(False, None)
        self.assertIsNone(error)
        self.assertEqual(["context.sh", "launcher.sh"], [call[1] for call in calls])
        self.assertIn("# Start staging in", calls[-1][2])
        self.assertIn("cp -r", calls[-1][2])
        self.assertEqual({}, consumer.pre_stage_metrics)
        self.assertNotIn("pre_stage", consumer.get_execution_metadata())

    def test_task_opt_out_keeps_legacy_launcher(self):
        consumer, calls, error = self.run_consumer(True, False)
        self.assertIsNone(error)
        self.assertEqual(["context.sh", "launcher.sh"], [call[1] for call in calls])
        self.assertIn("cp -r", calls[-1][2])
        self.assertEqual({"pre_stage_effective": False, "policy_version": PRE_STAGE_POLICY_VERSION},
                         consumer.get_execution_metadata()["pre_stage"])

    def test_inherited_and_explicit_pre_stage_stage_before_submission(self):
        for workflow_value, task_value in ((True, None), (False, True)):
            with self.subTest(workflow=workflow_value, task=task_value):
                consumer, calls, error = self.run_consumer(workflow_value, task_value)
                self.assertIsNone(error)
                self.assertEqual(["context.sh", "stage_in.sh", MARKER_NAME, "launcher.sh"],
                                 [call[1] for call in calls])
                self.assertNotIn("cp -r", calls[-1][2])
                self.assertEqual(TaskPhase.COMPLETED, consumer.pre_stage_phase)
                checkpoint = consumer.workflow.checkpoints[consumer.checkpoint_key()]
                self.assertEqual(0, checkpoint["code"])
                self.assertTrue(checkpoint["pre_stage"]["staged"])

    def test_failed_staging_never_submits(self):
        consumer, calls, error = self.run_consumer(True, None, stage_code=1)
        self.assertIsInstance(error, StageInFailedError)
        self.assertEqual("staging", error.phase)
        self.assertEqual(["context.sh", "stage_in.sh"], [call[1] for call in calls])
        self.assertEqual("staging", consumer.failure_phase)
        self.assertEqual(TaskPhase.FAILED, consumer.pre_stage_phase)
        self.assertFalse(consumer.workflow.checkpoints[consumer.checkpoint_key()]["pre_stage"]["staged"])
        self.assertNotIn("code", consumer.workflow.checkpoints[consumer.checkpoint_key()])

    def test_submission_and_execution_failures_are_distinguished(self):
        _consumer, calls, error = self.run_consumer(
            True, None, submit_result={"code": 1, "output": "", "message": "sbatch: error: invalid partition"})
        self.assertIsInstance(error, SchedulerSubmissionError)
        self.assertEqual("submission", error.phase)
        self.assertIn(MARKER_NAME, [call[1] for call in calls])  # staged data is kept
        consumer, calls, error = self.run_consumer(
            True, None, submit_result={"code": 3, "output": "9\n", "message": ""})
        self.assertIsInstance(error, ScheduledExecutionError)
        self.assertEqual("execution", error.phase)
        self.assertEqual("9", consumer.get_execution_metadata()["pre_stage"]["scheduler_job_id"])

    def test_pre_staged_submission_uses_parsable_output(self):
        consumer, calls, error = self.run_consumer(True, None)
        self.assertIsNone(error)
        consumer.pre_stage_submission = True
        self.assertTrue(consumer.generate_command("launcher.sh").startswith("sbatch --parsable "))
        consumer.pre_stage_submission = False
        self.assertNotIn("--parsable", consumer.generate_command("launcher.sh"))  # legacy submission unchanged
        self.assertEqual("7", consumer.get_execution_metadata()["pre_stage"]["scheduler_job_id"])

    def test_failure_phase_does_not_depend_on_display_text(self):
        for output, expected in (("Submitted batch job 9\n", SchedulerSubmissionError),
                                 ("sbatch: error: Submitted batch job 9 is a lie\n", SchedulerSubmissionError),
                                 ("", SchedulerSubmissionError),
                                 ("12;cluster-a\n", ScheduledExecutionError),
                                 ("12_3\nslurmstepd: error\n", ScheduledExecutionError)):
            with self.subTest(output=output):
                _consumer, _calls, error = self.run_consumer(
                    True, None, submit_result={"code": 1, "output": output, "message": "failed"})
                self.assertIsInstance(error, expected)

    def test_success_without_a_job_identifier_is_never_completed(self):
        for output in ("", "Submitted batch job 7\n", "sbatch: warning: partition is draining\n", "7 jobs\n"):
            with self.subTest(output=output):
                consumer, calls, error = self.run_consumer(
                    True, None, submit_result={"code": 0, "output": output, "message": ""})
                self.assertIsInstance(error, SchedulerSubmissionError)
                self.assertIn("without a job identifier", str(error))
                self.assertEqual("submission", consumer.failure_phase)
                self.assertEqual(TaskPhase.FAILED, consumer.pre_stage_phase)
                self.assertIsNone(consumer.get_execution_metadata()["pre_stage"]["scheduler_job_id"])
                self.assertNotEqual(0, consumer.workflow.checkpoints[consumer.checkpoint_key()]["code"])

    def test_parsable_job_id(self):
        self.assertEqual("42", parsable_job_id("42\n"))
        self.assertEqual("42", parsable_job_id("\n42;cluster\n"))
        self.assertEqual("42_7", parsable_job_id("42_7"))
        self.assertIsNone(parsable_job_id("Submitted batch job 42"))
        self.assertIsNone(parsable_job_id("sbatch: error: 42"))
        self.assertIsNone(parsable_job_id(None))

    def test_context_failure_is_a_staging_failure_without_submission(self):
        workflow, _a, _b, consumer = three_task_workflow(self.tmp.name, workflow_pre_stage=True)
        submitted = []
        with mock.patch.object(Slurm, "on_execute",
                               side_effect=lambda script, name: submitted.append(name) or {
                                   "code": 1, "output": "", "message": "context failed"}):
            with self.assertRaises(StageInFailedError):
                consumer.execute()
        self.assertEqual(["context.sh"], submitted)

    def test_invalid_late_override_fails_before_creating_scratch(self):
        workflow = make_workflow()
        task = Slurm("t", "true", working_dir=os.path.join(self.tmp.name, "never"))
        workflow.add_task(task)
        task.pre_stage = "yes"
        with self.assertRaises(PreStageConfigurationError):
            task.execute()
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "never")))


class StrictStagerTests(unittest.TestCase):
    def run_block(self, src, dst):
        stager = Stager(DataMover.COPY, StagerMover.NORMAL, minimal_config())
        block = stager.generate_command(src, dst, 'cp -r "$file" "$dst"', StagerMover.NORMAL.value, strict=True)
        completed = subprocess.run([bash_executable(), "-c", block + '\necho "rc=$?"\n'],
                                   capture_output=True, text=True)
        return completed.stdout.strip().splitlines()[-1]

    def test_legacy_text_is_unchanged_without_strict(self):
        stager = Stager(DataMover.COPY, StagerMover.NORMAL, minimal_config())
        legacy = stager.generate_command("/a", "/b", "cp", 0)
        self.assertNotIn("dagon_stage_status", legacy)
        self.assertIn("for file in $src\ndo", legacy)

    def test_strict_mode_reports_failures_and_handles_spaces(self):
        with tempfile.TemporaryDirectory(prefix="dagon strict ") as directory:
            source = os.path.join(directory, "source dir")
            target = os.path.join(directory, "target dir")
            os.makedirs(source)
            os.makedirs(target)
            for name in ("one file.txt", "two.txt"):
                Path(source, name).write_text(name, encoding="utf-8")
            self.assertEqual("rc=0", self.run_block(source.replace("\\", "/") + "/*.txt", target.replace("\\", "/")))
            self.assertEqual(["one file.txt", "two.txt"], sorted(os.listdir(target)))
            self.assertEqual("rc=1", self.run_block(source.replace("\\", "/") + "/missing.txt",
                                                    target.replace("\\", "/")))


class ContentIdentityTests(unittest.TestCase):
    """The bash helpers that compare staged content and record source identity."""

    def run_bash(self, body):
        from dagon.prestage import _DIGEST_FUNCTIONS
        return subprocess.run([bash_executable(), "-c", _DIGEST_FUNCTIONS + body], capture_output=True, text=True)

    def test_copy_link_and_corruption(self):
        with tempfile.TemporaryDirectory(prefix="dagon digest ") as directory:
            root = directory.replace("\\", "/")
            os.makedirs(os.path.join(directory, "src dir", "sub"))
            Path(directory, "src dir", "a.txt").write_text("alpha", encoding="utf-8")
            Path(directory, "src dir", "sub", "b.txt").write_text("beta", encoding="utf-8")
            shutil.copytree(os.path.join(directory, "src dir"), os.path.join(directory, "copy", "src dir"))
            compare = 'dagon_compare_staged "%s/src dir" "%s/copy/src dir"; echo "rc=$?"' % (root, root)
            self.assertIn("rc=0", self.run_bash(compare).stdout)
            Path(directory, "copy", "src dir", "sub", "b.txt").write_text("BETA", encoding="utf-8")  # same size
            result = self.run_bash(compare)
            self.assertIn("rc=1", result.stdout)
            self.assertIn("differs from its source", result.stderr)
            Path(directory, "copy", "src dir", "sub", "b.txt").unlink()  # partial transfer
            self.assertIn("rc=1", self.run_bash(compare).stdout)
            if os.name != "nt":
                os.makedirs(os.path.join(directory, "link"))
                os.symlink(os.path.join(directory, "src dir"), os.path.join(directory, "link", "src dir"))
                linked = 'dagon_compare_staged "%s/src dir" "%s/link/src dir"; echo "rc=$?"' % (root, root)
                self.assertIn("rc=0", self.run_bash(linked).stdout)

    def test_identity_changes_with_content_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "a.txt")
            source.write_text("alpha", encoding="utf-8")
            item = StageInput("workflow:///A/a.txt", "wf", "A", "/a.txt", directory.replace("\\", "/") + "//a.txt",
                              "", integrity=INTEGRITY_CONTENT)
            remote = StageInput("workflow:///B/b.txt", "wf", "B", "/b.txt", "/elsewhere/b.txt", "",
                                integrity=INTEGRITY_EXISTENCE)
            script = identity_script([item, remote])
            self.assertNotIn("/elsewhere", script)  # existence-only inputs take no part

            def digest():
                completed = subprocess.run([bash_executable(), "-c", script], capture_output=True, text=True)
                self.assertEqual(0, completed.returncode, completed.stderr)
                return identity_digest(completed.stdout)

            first = digest()
            self.assertEqual(first, digest())
            os.utime(source, (0, 0))  # timestamps are not part of the identity
            self.assertEqual(first, digest())
            source.write_text("omega", encoding="utf-8")
            self.assertNotEqual(first, digest())


class LocalMockSchedulerTests(unittest.TestCase):
    """Real launchers and stage-in scripts with a mock ``sbatch -W``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.scratch = os.path.join(self.tmp.name, "scratch")
        self.log = os.path.join(self.tmp.name, "sbatch.jsonl")

    def run_workflow(self, workflow, reject=False, fails=False):
        with no_network_context(), mock_scheduler.mock_sbatch(self.log, reject=reject):
            if fails:
                with self.assertLogs(level="ERROR"):
                    workflow.run()
            else:
                workflow.run()
        return mock_scheduler.read_log(self.log)

    def test_inputs_are_staged_before_submission(self):
        workflow, first, second, consumer = three_task_workflow(self.scratch, workflow_pre_stage=True)
        staged_at = {}
        workflow.add_listener("on_task_staging_in_end", lambda task: staged_at.setdefault(task.name, time.time()))
        log = self.run_workflow(workflow)
        self.assertEqual(["FINISHED"] * 3, [task.status.name for task in (first, second, consumer)])
        self.assertEqual("alpha\nbeta\n", Path(consumer.working_dir, "c.txt").read_text(encoding="utf-8"))
        submission = mock_scheduler.submission_for(self.log, "C")
        self.assertTrue(submission["marker_present"])
        self.assertTrue(submission["inputs_populated"])
        self.assertLess(staged_at["C"], submission["time"])
        self.assertEqual(3, len(log))
        marker = json.loads(Path(consumer.working_dir, ".dagon", MARKER_NAME).read_text(encoding="utf-8"))
        self.assertEqual("C", marker["task"])
        self.assertEqual(["workflow:///A/a.txt", "workflow:///B/b.txt"],
                         [item["reference"] for item in marker["inputs"]])
        self.assertEqual([INTEGRITY_CONTENT] * 2, [item["integrity"] for item in marker["inputs"]])
        self.assertEqual(64, len(marker["source_identity_sha256"]))
        metadata = consumer.get_execution_metadata()["pre_stage"]
        self.assertEqual(2, metadata["inputs_content_verified"])
        self.assertEqual("4242", metadata["scheduler_job_id"])
        self.assertTrue(submission["parsable"])
        self.assertTrue(metadata["pre_stage_effective"])
        self.assertEqual("COMPLETED", metadata["phase"])
        self.assertEqual(2, metadata["inputs"])
        self.assertIsNotNone(metadata["execution_seconds"])
        self.assertNotIn(self.scratch, json.dumps(metadata))  # no paths in provenance

    def test_legacy_run_stages_inside_the_job(self):
        workflow, _first, _second, consumer = three_task_workflow(self.scratch)
        self.run_workflow(workflow)
        submission = mock_scheduler.submission_for(self.log, "C")
        self.assertFalse(submission["marker_present"])
        self.assertFalse(submission["inputs_populated"])
        self.assertEqual("FINISHED", consumer.status.name)
        self.assertFalse(Path(consumer.working_dir, ".dagon", "stage_in.sh").exists())

    def test_missing_input_fails_staging_without_submission(self):
        workflow, first, second, consumer = three_task_workflow(
            self.scratch, workflow_pre_stage=True, command="cat workflow:///A/missing.txt workflow:///B/b.txt")
        self.run_workflow(workflow, fails=True)
        self.assertEqual("FAILED", consumer.status.name)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertIsNone(mock_scheduler.submission_for(self.log, "C"))
        self.assertFalse(Path(consumer.working_dir, ".dagon", MARKER_NAME).exists())
        self.assertEqual(["FINISHED", "FINISHED"], [first.status.name, second.status.name])

    def test_task_without_inputs_submits_directly(self):
        workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True)
        task = Slurm("solo", "echo ok > ok.txt", ntasks=4)
        workflow.add_task(task)
        self.run_workflow(workflow)
        self.assertEqual("FINISHED", task.status.name)
        self.assertTrue(mock_scheduler.submission_for(self.log, "solo")["marker_present"])
        self.assertEqual(0, task.get_execution_metadata()["pre_stage"]["inputs"])

    def test_rejected_submission_keeps_staged_inputs(self):
        workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True)
        task = Slurm("solo", "true")
        workflow.add_task(task)
        self.run_workflow(workflow, reject=True, fails=True)
        self.assertEqual("FAILED", task.status.name)
        self.assertEqual("submission", task.failure_phase)
        self.assertTrue(Path(task.working_dir, ".dagon", MARKER_NAME).exists())

    def test_job_failure_is_an_execution_failure(self):
        workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True)
        task = Slurm("solo", "sh -c 'exit 3'")
        workflow.add_task(task)
        self.run_workflow(workflow, fails=True)
        self.assertEqual("FAILED", task.status.name)
        self.assertEqual("execution", task.failure_phase)

    def test_retry_after_partial_staging_restages_and_never_trusts_a_stale_marker(self):
        producer_dir = os.path.join(self.scratch, "producer")
        consumer_dir = os.path.join(self.scratch, "consumer")
        os.makedirs(os.path.join(consumer_dir, ".dagon", "inputs", "wf", "A"))
        stale = Path(consumer_dir, ".dagon", MARKER_NAME)
        stale.write_text('{"stale": true}', encoding="utf-8")
        Path(consumer_dir, ".dagon", "inputs", "wf", "A", "partial.txt").write_text("x", encoding="utf-8")

        def build(command):
            workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True)
            producer = Slurm("A", command, working_dir=producer_dir)
            consumer = Slurm("C", "cat workflow:///A/a.txt > c.txt", working_dir=consumer_dir)
            workflow.add_task(producer)
            workflow.add_task(consumer)
            return workflow, consumer

        workflow, consumer = build("true")  # the producer does not create a.txt
        self.run_workflow(workflow, fails=True)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertFalse(stale.exists())  # removed before the transfer started
        # Data staged by an earlier attempt is discarded, never trusted.
        self.assertFalse(Path(consumer_dir, ".dagon", "inputs", "wf", "A", "partial.txt").exists())

        workflow, consumer = build("echo fixed > a.txt")
        self.run_workflow(workflow)
        self.assertEqual("FINISHED", consumer.status.name)
        self.assertEqual("fixed\n", Path(consumer_dir, "c.txt").read_text(encoding="utf-8"))
        self.assertEqual("C", json.loads(stale.read_text(encoding="utf-8"))["task"])

    def test_checkpoint_resume_neither_restages_nor_resubmits(self):
        checkpoint = os.path.join(self.tmp.name, "checkpoint.json")

        def build():
            workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True,
                                checkpoint_file=checkpoint)
            producer = Slurm("A", "echo alpha > a.txt")
            consumer = Slurm("C", "cat workflow:///A/a.txt > c.txt")
            workflow.add_task(producer)
            workflow.add_task(consumer)
            return workflow, consumer

        workflow, consumer = build()
        self.run_workflow(workflow)
        self.assertEqual(2, len(mock_scheduler.read_log(self.log)))
        saved = json.loads(Path(checkpoint).read_text(encoding="utf-8"))
        self.assertTrue(saved["wf.C"]["pre_stage"]["staged"])
        workflow, consumer = build()
        with no_network_context(), mock_scheduler.mock_sbatch(self.log):
            workflow.run(resume_checkpoint_file=checkpoint)
        self.assertEqual("FINISHED", consumer.status.name)
        self.assertEqual(2, len(mock_scheduler.read_log(self.log)))  # nothing resubmitted
        self.assertTrue(consumer.fair_checkpoint_reused)

    def resumable_run(self, checkpoint):
        def build():
            workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True,
                                checkpoint_file=checkpoint)
            producer = Slurm("A", "echo alpha > a.txt")
            consumer = Slurm("C", "cat workflow:///A/a.txt > c.txt")
            workflow.add_task(producer)
            workflow.add_task(consumer)
            return workflow, producer, consumer

        workflow, producer, consumer = build()
        self.run_workflow(workflow)
        self.assertEqual(2, len(mock_scheduler.read_log(self.log)))
        return build, producer, consumer

    def resume(self, workflow, checkpoint):
        with no_network_context(), mock_scheduler.mock_sbatch(self.log), self.assertLogs(level="WARNING") as logs:
            workflow.run(resume_checkpoint_file=checkpoint)
        return "\n".join(logs.output)

    def test_changed_input_invalidates_a_successful_checkpoint(self):
        checkpoint = os.path.join(self.tmp.name, "checkpoint.json")
        build, producer, first_consumer = self.resumable_run(checkpoint)
        # Change the producer's output after the consumer completed (same size).
        Path(producer.working_dir, "a.txt").write_text("omega\n", encoding="utf-8")
        workflow, _producer, consumer = build()
        logs = self.resume(workflow, checkpoint)
        self.assertIn("content of at least one input changed", logs)
        self.assertEqual("FINISHED", consumer.status.name)
        self.assertFalse(consumer.fair_checkpoint_reused)
        self.assertEqual(["A", "C", "C"], [item["job_name"] for item in mock_scheduler.read_log(self.log)])
        self.assertNotEqual(first_consumer.working_dir, consumer.working_dir)
        self.assertEqual("omega\n", Path(consumer.working_dir, "c.txt").read_text(encoding="utf-8"))

    def test_checkpoint_that_cannot_be_reverified_is_not_reused(self):
        checkpoint = os.path.join(self.tmp.name, "checkpoint.json")
        build, _producer, _consumer = self.resumable_run(checkpoint)
        saved = json.loads(Path(checkpoint).read_text(encoding="utf-8"))
        saved["wf.C"]["pre_stage"]["inputs"][0]["integrity"] = INTEGRITY_EXISTENCE  # e.g. an SCP transfer
        Path(checkpoint).write_text(json.dumps(saved), encoding="utf-8")
        workflow, _producer, consumer = build()
        logs = self.resume(workflow, checkpoint)
        self.assertIn("cannot be re-verified", logs)
        self.assertEqual(3, len(mock_scheduler.read_log(self.log)))
        self.assertEqual("FINISHED", consumer.status.name)

    def test_checkpoint_without_identity_is_not_reused(self):
        checkpoint = os.path.join(self.tmp.name, "checkpoint.json")
        build, _producer, _consumer = self.resumable_run(checkpoint)
        saved = json.loads(Path(checkpoint).read_text(encoding="utf-8"))
        del saved["wf.C"]["pre_stage"]["source_identity_sha256"]  # e.g. written by an older policy
        Path(checkpoint).write_text(json.dumps(saved), encoding="utf-8")
        workflow, _producer, consumer = build()
        self.assertIn("no input identity", self.resume(workflow, checkpoint))
        self.assertEqual(3, len(mock_scheduler.read_log(self.log)))

    def test_dry_run_neither_stages_nor_submits(self):
        workflow, _first, _second, consumer = three_task_workflow(self.scratch, workflow_pre_stage=True)
        workflow.set_dry(True)
        with mock.patch.object(Slurm, "on_execute", side_effect=AssertionError("dry run executed a script")), \
                mock.patch.object(Batch, "execute_command", side_effect=AssertionError("dry run ran a command")), \
                self.assertLogs(level="INFO") as logs:
            self.run_workflow(workflow)
        self.assertEqual([], mock_scheduler.read_log(self.log))
        self.assertIsNone(consumer.working_dir)  # no scratch directory was assigned or created
        self.assertFalse(os.path.exists(self.scratch))
        self.assertNotIn(consumer.checkpoint_key(), workflow.checkpoints)
        self.assertIn("planned pre-staged order", "\n".join(logs.output))
        self.assertEqual(5, len(consumer.prepared_task.planned_order()))  # scratch, 2 inputs, verify, submit
        self.assertTrue(consumer.get_execution_metadata()["pre_stage"]["dry_run"])
        self.assertEqual(["FINISHED"] * 3, [task.status.name for task in workflow.tasks])

    def test_dry_run_rejects_unsafe_references(self):
        workflow, _first, _second, consumer = three_task_workflow(
            self.scratch, workflow_pre_stage=True, command="cat workflow:///A/../../etc/passwd")
        workflow.set_dry(True)
        self.run_workflow(workflow, fails=True)
        self.assertEqual("FAILED", consumer.status.name)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertFalse(os.path.exists(self.scratch))

    def test_traversal_reference_is_refused_before_any_transfer(self):
        outside = os.path.join(self.tmp.name, "outside.txt")
        Path(outside).write_text("secret", encoding="utf-8")
        workflow, _first, _second, consumer = three_task_workflow(
            self.scratch, workflow_pre_stage=True, command="cat workflow:///A/../../outside.txt > c.txt")
        self.run_workflow(workflow, fails=True)
        self.assertEqual("FAILED", consumer.status.name)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertIsNone(mock_scheduler.submission_for(self.log, "C"))
        self.assertFalse(Path(consumer.working_dir, ".dagon", "stage_in.sh").exists())
        self.assertFalse(Path(consumer.working_dir, ".dagon", "inputs").exists())

    def test_corrupted_transfer_is_not_marked_complete(self):
        original = Stager.generate_command

        def corrupting(stager, src, dst, cmd, mode, strict=False):
            # A mover that "succeeds" while writing the wrong bytes.
            return original(stager, src, dst, 'printf corrupted > "$dst/$(basename "$file")"', mode, strict=strict)

        workflow, _first, _second, consumer = three_task_workflow(self.scratch, workflow_pre_stage=True)
        with mock.patch.object(Stager, "generate_command", corrupting):
            self.run_workflow(workflow, fails=True)
        self.assertEqual("FAILED", consumer.status.name)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertIsNone(mock_scheduler.submission_for(self.log, "C"))
        self.assertFalse(Path(consumer.working_dir, ".dagon", MARKER_NAME).exists())
        self.assertFalse(Path(consumer.working_dir, ".dagon", IDENTITY_NAME).exists())

    def test_staged_input_changed_while_queued_never_reaches_the_command(self):
        original = Slurm.on_execute
        for label, change in (("same-size rewrite", lambda staged: staged.write_text("ALPHA\n", encoding="utf-8")),
                              ("truncation", lambda staged: staged.write_text("", encoding="utf-8")),
                              ("removed", lambda staged: staged.unlink())):
            with self.subTest(change=label):
                scratch = os.path.join(self.tmp.name, label.replace(" ", "-"))
                workflow, _first, _second, consumer = three_task_workflow(scratch, workflow_pre_stage=True)

                def queued_change(task, script, script_name, change=change):
                    if task.name == "C" and script_name == "launcher.sh":
                        # Stage-in has verified and recorded the inputs; the job is queued.
                        change(Path(task.working_dir, ".dagon", "inputs", "wf", "A", "a.txt"))
                    return original(task, script, script_name)

                with mock.patch.object(Slurm, "on_execute", queued_change):
                    self.run_workflow(workflow, fails=True)
                self.assertEqual("FAILED", consumer.status.name)
                self.assertEqual("execution", consumer.failure_phase)
                self.assertFalse(Path(consumer.working_dir, "c.txt").exists())  # the command never ran
                self.assertTrue(Path(consumer.working_dir, ".dagon", DESTINATION_IDENTITY_NAME).exists())

    def test_stage_in_lock_is_released_after_the_job(self):
        workflow, _first, _second, consumer = three_task_workflow(self.scratch, workflow_pre_stage=True)
        self.run_workflow(workflow)
        self.assertEqual("FINISHED", consumer.status.name)
        self.assertFalse(Path(consumer.working_dir, ".dagon", LOCK_NAME).exists())
        marker = json.loads(Path(consumer.working_dir, ".dagon", MARKER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(64, len(marker["destination_identity_sha256"]))

    def test_lock_is_released_when_staging_fails(self):
        workflow, _first, _second, consumer = three_task_workflow(
            self.scratch, workflow_pre_stage=True, command="cat workflow:///A/missing.txt")
        self.run_workflow(workflow, fails=True)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertFalse(Path(consumer.working_dir, ".dagon", LOCK_NAME).exists())

    def test_another_runs_lock_blocks_stage_in_without_touching_its_data(self):
        consumer_dir = os.path.join(self.scratch, "consumer")
        lock = Path(consumer_dir, ".dagon", LOCK_NAME)
        lock.mkdir(parents=True)
        Path(lock, "owner").write_text("another-run\n", encoding="utf-8")
        foreign = Path(consumer_dir, ".dagon", "inputs", "wf", "A", "a.txt")
        foreign.parent.mkdir(parents=True)
        foreign.write_text("theirs\n", encoding="utf-8")
        Path(consumer_dir, ".dagon", MARKER_NAME).write_text("{}", encoding="utf-8")
        workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True)
        producer = Slurm("A", "echo alpha > a.txt")
        consumer = Slurm("C", "cat workflow:///A/a.txt > c.txt", working_dir=consumer_dir)
        workflow.add_task(producer)
        workflow.add_task(consumer)
        self.run_workflow(workflow, fails=True)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertTrue(consumer.get_execution_metadata()["pre_stage"]["stage_in_lock_busy"])
        self.assertIsNone(mock_scheduler.submission_for(self.log, "C"))
        self.assertEqual("another-run\n", Path(lock, "owner").read_text(encoding="utf-8"))  # not released
        self.assertEqual("theirs\n", foreign.read_text(encoding="utf-8"))  # nothing replaced
        self.assertTrue(Path(consumer_dir, ".dagon", MARKER_NAME).exists())

    def test_stage_in_handles_spaces_in_scratch_paths(self):
        scratch = os.path.join(self.tmp.name, "scratch with spaces")
        workflow = Workflow("wf", config=scratch_config(scratch), pre_stage=True)
        producer = Slurm("A", "true", working_dir=os.path.join(scratch, "producer dir"))
        consumer = Slurm("C", "cat workflow:///A/a*.txt", working_dir=os.path.join(scratch, "consumer dir"))
        workflow.add_task(producer)
        workflow.add_task(consumer)
        workflow.make_dependencies()
        os.makedirs(os.path.join(producer.working_dir, ".dagon"))
        for name in ("a 1.txt", "a2.txt"):
            Path(producer.working_dir, name).write_text(name, encoding="utf-8")
        producer.info = dict(CANNED_CONTEXT_INFO)
        consumer.create_working_dir()
        with no_network_context():
            prepared = consumer.prepare_task(consumer.command, strict_staging=True)
        result = consumer.run_stage_in(prepared.stage_in_script())
        self.assertEqual(0, result["code"], result)
        staged = Path(consumer.working_dir, ".dagon", "inputs", "wf", "A")
        self.assertEqual(["a 1.txt", "a2.txt"], sorted(os.listdir(str(staged))))

    def test_failure_of_a_later_input_stops_staging_and_submission(self):
        workflow, first, second, consumer = three_task_workflow(
            self.scratch, workflow_pre_stage=True, command="cat workflow:///A/a.txt workflow:///B/missing.txt")
        self.run_workflow(workflow, fails=True)
        self.assertEqual("staging", consumer.failure_phase)
        self.assertIsNone(mock_scheduler.submission_for(self.log, "C"))
        self.assertTrue(Path(consumer.working_dir, ".dagon", "inputs", "wf", "A", "a.txt").exists())
        self.assertFalse(Path(consumer.working_dir, ".dagon", MARKER_NAME).exists())

    def test_repeated_references_and_concurrent_consumers(self):
        workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True)
        producer = Slurm("A", "seq 1 3 > a.txt")
        twice = Slurm("twice", "cat workflow:///A/a.txt workflow:///A/a.txt > out.txt")
        other = Slurm("other", "wc -l < workflow:///A/a.txt > out.txt")
        for task in (producer, twice, other):
            workflow.add_task(task)
        self.run_workflow(workflow)
        self.assertEqual("1\n2\n3\n1\n2\n3\n", Path(twice.working_dir, "out.txt").read_text(encoding="utf-8"))
        self.assertEqual("3", Path(other.working_dir, "out.txt").read_text(encoding="utf-8").strip())
        self.assertNotEqual(twice.working_dir, other.working_dir)  # each consumer stages privately
        for name in ("twice", "other"):
            self.assertTrue(mock_scheduler.submission_for(self.log, name)["inputs_populated"])
        self.assertEqual(1, len([item for item in mock_scheduler.read_log(self.log) if item["job_name"] == "twice"]))

    def test_job_fails_clearly_when_staged_data_is_not_visible_in_the_allocation(self):
        # Emulate a non-shared scratch: the marker and inputs exist on the
        # submission host but are gone when the job starts.
        workflow, _first, _second, consumer = three_task_workflow(self.scratch, workflow_pre_stage=True)
        original = Slurm.on_execute

        def hide_staged_data(task, script, script_name):
            if script_name == "launcher.sh" and task.name == "C":
                os.remove(os.path.join(task.working_dir, ".dagon", MARKER_NAME))
            return original(task, script, script_name)

        with mock.patch.object(Slurm, "on_execute", hide_staged_data):
            self.run_workflow(workflow, fails=True)
        self.assertEqual("execution", consumer.failure_phase)
        self.assertFalse(Path(consumer.working_dir, "c.txt").exists())  # the command never ran
        self.assertIn("must be shared", str(consumer.result.get("message")))

    @unittest.skipIf(os.name == "nt", "shell metacharacters are not valid in Windows paths")
    def test_shell_metacharacters_in_scratch_paths_are_never_executed(self):
        scratch = os.path.join(self.tmp.name, "evil $(touch INJECTED) `touch TICK` ;dir")
        workflow = Workflow("wf", config=scratch_config(scratch), pre_stage=True)
        producer = Slurm("A", "true", working_dir=os.path.join(scratch, "producer"))
        consumer = Slurm("C", "cat workflow:///A/a.txt", working_dir=os.path.join(scratch, "consumer"))
        workflow.add_task(producer)
        workflow.add_task(consumer)
        workflow.make_dependencies()
        os.makedirs(os.path.join(producer.working_dir, ".dagon"))
        Path(producer.working_dir, "a.txt").write_text("payload", encoding="utf-8")
        producer.info = dict(CANNED_CONTEXT_INFO)
        consumer.create_working_dir()
        cwd = os.getcwd()
        os.chdir(self.tmp.name)  # an executed payload would land here
        try:
            with no_network_context():
                prepared = consumer.prepare_task(consumer.command, strict_staging=True)  # runs context.sh
            result = consumer.run_stage_in(prepared.stage_in_script())
        finally:
            os.chdir(cwd)
        self.assertEqual(0, result["code"], result)
        self.assertEqual("payload", Path(consumer.working_dir, ".dagon", "inputs", "wf", "A", "a.txt")
                         .read_text(encoding="utf-8"))
        for directory in (self.tmp.name, consumer.working_dir, os.path.join(consumer.working_dir, ".dagon")):
            self.assertFalse(os.path.exists(os.path.join(directory, "INJECTED")), directory)
            self.assertFalse(os.path.exists(os.path.join(directory, "TICK")), directory)

    def test_other_task_types_are_unchanged_under_workflow_default(self):
        workflow = Workflow("wf", config=scratch_config(self.scratch), pre_stage=True)
        producer = Batch("A", "echo alpha > a.txt")
        consumer = Batch("C", "cat workflow:///A/a.txt > c.txt")
        workflow.add_task(producer)
        workflow.add_task(consumer)
        with no_network_context():
            workflow.run()
        self.assertEqual("FINISHED", consumer.status.name)
        self.assertFalse(Path(consumer.working_dir, ".dagon", "stage_in.sh").exists())
        self.assertEqual({}, consumer.pre_stage_metrics)

    def test_fair_records_pre_stage_metadata_without_paths(self):
        from dagon.fair import Agent, FairProfile
        workflow, _first, _second, consumer = three_task_workflow(self.scratch, workflow_pre_stage=True)
        recorder = workflow.enable_fair(FairProfile(
            title="pre-stage", description="pre-staging provenance", creators=[Agent(name="Test Lab")],
            license="Apache-2.0", output_dir=os.path.join(self.tmp.name, "fair")))
        self.run_workflow(workflow)
        record = recorder.run["tasks"]["C"]
        self.assertTrue(record["execution"]["pre_stage"]["pre_stage_effective"])
        staging = [item for item in recorder.run["staging"] if item["task"] == "C" and item["phase"] == "in"]
        self.assertEqual(1, len(staging))
        exported = Path(self.tmp.name, "fair", "run.json").read_text(encoding="utf-8")
        self.assertIn("pre_stage_effective", exported)
        self.assertNotIn(os.path.join(consumer.working_dir, ".dagon", "inputs"), exported)


def load_slurm_example(name):
    import importlib
    import sys
    directory = str(ROOT / "examples" / "dataflow" / "slurm")
    if directory not in sys.path:
        sys.path.insert(0, directory)
    return importlib.import_module(name)


class ExampleTests(unittest.TestCase):
    """The pre-staging examples, with ``sbatch`` replaced by the mock scheduler."""

    def test_mock_example_verifies(self):
        completed = subprocess.run(
            [__import__("sys").executable, str(ROOT / "examples" / "dataflow" / "slurm" / "pre_stage_mock.py")],
            capture_output=True, text=True, timeout=300,
            env=dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])))
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("Verification: ok", completed.stdout)

    def test_local_slurm_example_with_mock_scheduler(self):
        example = load_slurm_example("pre_stage_local")
        with tempfile.TemporaryDirectory() as directory:
            log = os.path.join(directory, "sbatch.jsonl")
            argv = ["pre_stage_local.py", "--scratch", os.path.join(directory, "scratch"), "--cores", "8"]
            with no_network_context(), mock_scheduler.mock_sbatch(log), mock.patch("sys.argv", argv):
                self.assertEqual(0, example.main())
            self.assertTrue(mock_scheduler.submission_for(log, "simulate")["marker_present"])


if __name__ == "__main__":
    unittest.main()
