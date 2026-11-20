"""Tests for ``TaskType.META`` (dagon.meta): external workflows run through adapters.

The default tests need no workflow engine: the ``command`` adapter runs a
small Python "engine" written by the test, the ``mock`` adapter covers
portable emulation, and each engine adapter is checked through the command
and parameter files it generates.  ``MetaLiveEngineTests`` run the real
engines (Snakemake, Parsl, Nextflow, StreamFlow, cwltool) only when they are
installed; set ``DAGON_META_PARSL_PYTHON`` to an interpreter with Parsl.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dagon import Status, Workflow
from dagon.fair import Agent, FairProfile
from dagon.meta import (EngineCapabilities, EngineInvocation, MetaEngineAdapter, MetaRunContext, adapter_names,
                        get_adapter, register_adapter, unregister_adapter)
from dagon.meta.models import MetaInput
from dagon.task import DagonTask, TaskType
from tests.helpers import minimal_config, scratch_config

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "examples" / "meta" / "workflows"

ENGINE = """
import json, os, sys
params = json.load(open(os.environ["DAGON_META_PARAMETERS"], encoding="utf-8"))
if params.get("fail"):
    sys.stderr.write("engine failure requested\\n")
    raise SystemExit(3)
if params.get("sleep"):
    import time; time.sleep(params["sleep"])
os.makedirs("results", exist_ok=True)
text = open(params["text"], encoding="utf-8").read()
with open("results/upper.txt", "w", encoding="utf-8") as stream:
    stream.write(text.upper() * int(params.get("times", 1)))
if params.get("tree"):
    names = sorted(os.listdir(params["tree"]))
    os.makedirs("results/tree", exist_ok=True)
    with open("results/tree/listing.txt", "w", encoding="utf-8") as stream:
        stream.write("\\n".join(names) + "\\n")
"""


def write_engine(directory):
    path = Path(directory, "engine.py")
    path.write_text(ENGINE, encoding="utf-8")
    return str(path)


def meta(name="meta", engine_path="engine.py", inputs=None, outputs=None, **options):
    return DagonTask(TaskType.META, name, engine="command", workflow=engine_path,
                     inputs=inputs if inputs is not None else {"text": "workflow:///producer/out/a.txt", "times": 2},
                     outputs=outputs if outputs is not None else {"upper": {"path": "upper.txt",
                                                                            "source": "results/upper.txt"}},
                     engine_options={"command": [sys.executable, "{workflow}"]}, **options)


def producer(text="hello"):
    return DagonTask(TaskType.BATCH, "producer", "mkdir -p out; printf '%s' '" + text + "' > out/a.txt")


def context(directory, engine, workflow="wf", inputs=None, options=None, outputs=None):
    workdir = Path(directory)
    (workdir / "run").mkdir(parents=True, exist_ok=True)
    return MetaRunContext(engine=engine, workflow=workflow, workdir=workdir, run_dir=workdir / "run",
                          metadata_dir=workdir / ".dagon", inputs=inputs or [], outputs=outputs or {},
                          engine_options=dict(options or {}), environment={}, timeout=None, python=sys.executable)


class MetaValidationTests(unittest.TestCase):
    def test_builtin_adapters_are_registered(self):
        self.assertTrue({"mock", "command", "nextflow", "snakemake", "parsl", "streamflow", "cwl"}
                        <= set(adapter_names()))

    def test_invalid_specifications_are_rejected_before_side_effects(self):
        cases = [
            dict(engine="unknown-engine", workflow="x"),
            dict(engine="snakemake", workflow=""),
            dict(engine="snakemake", workflow="Snakefile", inputs={"1bad": 1}),
            dict(engine="snakemake", workflow="Snakefile", inputs={"x": {"v": "workflow:///p/a.txt"}}),
            dict(engine="snakemake", workflow="Snakefile", inputs={"x": "workflow:///p"}),
            dict(engine="snakemake", workflow="Snakefile", inputs={"x": "workflow:///p/a.txt?stream"}),
            dict(engine="snakemake", workflow="Snakefile", outputs={"o": "../escape.txt"}),
            dict(engine="snakemake", workflow="Snakefile", outputs={"o": {"path": "o", "engine_output": "o"}}),
            dict(engine="snakemake", workflow="Snakefile", outputs={"o": {"path": "o", "type": "socket"}}),
            dict(engine="snakemake", workflow="Snakefile", outputs={"a": "same", "b": "same"}),
            dict(engine="snakemake", workflow="Snakefile", engine_options={"api_token": "x"}),
            dict(engine="snakemake", workflow="Snakefile", engine_options={"bogus": 1}),
            dict(engine="snakemake", workflow="Snakefile", engine_options={"cores": 0}),
            dict(engine="snakemake", workflow="Snakefile", environment={"AWS_SECRET_ACCESS_KEY": "x"}),
            dict(engine="snakemake", workflow="Snakefile", timeout=-1),
            dict(engine="snakemake", workflow="Snakefile", staging="hardlink"),
            dict(engine="snakemake", workflow="workflow:///p/Snakefile"),
            dict(engine="command", workflow="x.sh", engine_options={"command": "echo hi"}),
            dict(engine="parsl", workflow="flow.py", engine_options={"config": "unknown"}),
            dict(engine="parsl", workflow="flow.py", engine_options={"mode": "script", "entrypoint": "main"}),
            dict(engine="streamflow", workflow="flow.nf"),
            dict(engine="nextflow", workflow="main.nf", engine_options={"work_dir": "/abs"}),
            dict(engine="snakemake", workflow="Snakefile", unexpected=True),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                DagonTask(TaskType.META, "meta", **case)

    def test_inputs_and_outputs_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory, "table.csv")
            local.write_text("a,b\n", encoding="utf-8")
            task = DagonTask(TaskType.META, "meta", engine="snakemake", workflow=str(Path(directory, "Snakefile")),
                             inputs={"ref": "workflow:///producer/out/a.txt",
                                     "table": {"type": "file", "path": str(local)},
                                     "n": 3, "opts": {"a": [1, 2]}},
                             outputs={"counts": "results/counts.tsv",
                                      "plots": {"path": "plots", "source": "results/plots", "type": "directory"}})
        self.assertEqual(task.inputs["ref"], {"type": "auto", "path": "workflow:///producer/out/a.txt"})
        self.assertEqual(task.inputs["table"]["type"], "file")
        self.assertEqual(task.inputs["n"], {"type": "value", "value": 3})
        self.assertEqual(task.outputs["counts"], {"path": "results/counts.tsv", "source": "results/counts.tsv",
                                                  "type": "file", "required": True})
        self.assertEqual(task.outputs["plots"]["type"], "directory")
        self.assertTrue(Path(task.workflow_location).is_absolute())

    def test_remote_nextflow_pipeline_names_are_kept(self):
        task = DagonTask(TaskType.META, "meta", engine="nextflow", workflow="nextflow-io/hello",
                         engine_options={"revision": "master"})
        self.assertEqual(task.workflow_location, "nextflow-io/hello")

    def test_json_round_trip_and_spec_is_credential_free(self):
        workflow = Workflow("meta-json", config=minimal_config())
        workflow.add_task(producer())
        workflow.add_task(meta(engine_path="/opt/engine.py", environment={"OMP_NUM_THREADS": "2"}, timeout=30))
        document = workflow.as_json()
        restored = Workflow("restored", config=minimal_config())
        restored.load_json(document)
        original = workflow.find_task_by_name("meta-json", "meta")
        loaded = restored.find_task_by_name("meta-json", "meta")
        self.assertEqual(document["tasks"]["meta"]["type"], "meta")
        self.assertEqual(loaded.portable_spec(), original.portable_spec())
        self.assertEqual(loaded.task_type, TaskType.META)


class MetaDependencyTests(unittest.TestCase):
    def test_reference_is_discovered_once_per_producer(self):
        workflow = Workflow("meta-deps", config=minimal_config())
        source = producer()
        workflow.add_task(source)
        workflow.add_task(meta(inputs={"a": "workflow:///producer/out/a.txt", "b": "workflow:///producer/out"}))
        workflow.make_dependencies()
        task = workflow.find_task_by_name("meta-deps", "meta")
        self.assertEqual(task.prevs, [source])
        self.assertEqual(source.reference_count, 1)

    def test_missing_producer_is_reported(self):
        workflow = Workflow("meta-missing", config=minimal_config())
        workflow.add_task(meta())
        with self.assertRaises(ValueError):
            workflow.make_dependencies()


class MetaExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.engine = write_engine(self.directory)

    def _workflow(self, name="meta-run", **kwargs):
        config = scratch_config(self.directory)
        return Workflow(name, config=config, **kwargs)

    def test_meta_task_passes_data_both_ways_with_workflow_references(self):
        workflow = self._workflow()
        workflow.add_task(producer("hello"))
        workflow.add_task(DagonTask(TaskType.BATCH, "tree", "mkdir -p data; touch data/x data/y"))
        workflow.add_task(meta(engine_path=self.engine,
                               inputs={"text": "workflow:///producer/out/a.txt", "times": 2,
                                       "tree": {"type": "directory", "path": "workflow:///tree/data"}},
                               outputs={"upper": {"path": "upper.txt", "source": "results/upper.txt"},
                                        "tree": {"path": "tree", "source": "results/tree", "type": "directory"}}))
        workflow.add_task(DagonTask(TaskType.BATCH, "consumer",
                                    "cat workflow:///meta/outputs/upper.txt workflow:///meta/outputs/tree/listing.txt"
                                    " > final.txt"))
        workflow.run()
        self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks),
                        [(task.name, task.status) for task in workflow.tasks])
        task = workflow.find_task_by_name("meta-run", "meta")
        consumer = workflow.find_task_by_name("meta-run", "consumer")
        self.assertEqual(Path(consumer.working_dir, "final.txt").read_text(encoding="utf-8"), "HELLOHELLOx\ny\n")
        self.assertTrue(Path(task.working_dir, "inputs", "text", "a.txt").is_file())
        result = json.loads(Path(task.working_dir, ".dagon", "meta_result.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in result["outputs"]], ["tree", "upper"])
        self.assertEqual(result["workflow"]["kind"], "file")
        self.assertEqual({item["type"] for item in result["inputs"]}, {"file", "directory"})
        invocation = json.loads(Path(task.working_dir, ".dagon", "meta_invocation.json").read_text(encoding="utf-8"))
        self.assertEqual(invocation["argv"][0], sys.executable)
        metadata = task.get_execution_metadata()
        self.assertEqual(metadata["model"], "meta")
        self.assertEqual(metadata["adapter"], "command")

    def test_engine_failure_fails_the_task_and_its_dependants(self):
        workflow = self._workflow("meta-fail")
        workflow.add_task(producer())
        workflow.add_task(meta(engine_path=self.engine, inputs={"text": "workflow:///producer/out/a.txt",
                                                                "fail": True}))
        workflow.add_task(DagonTask(TaskType.BATCH, "consumer", "cat workflow:///meta/outputs/upper.txt"))
        workflow.run()
        task = workflow.find_task_by_name("meta-fail", "meta")
        self.assertIs(task.status, Status.FAILED)
        self.assertEqual(task.failure_phase, "execution")
        self.assertIs(workflow.find_task_by_name("meta-fail", "consumer").status, Status.FAILED)
        self.assertIn("engine failure requested",
                      Path(task.working_dir, ".dagon", "engine_stderr.txt").read_text(encoding="utf-8"))

    def test_missing_declared_output_is_an_output_failure(self):
        workflow = self._workflow("meta-missing-output")
        workflow.add_task(producer())
        workflow.add_task(meta(engine_path=self.engine, outputs={"x": {"path": "x.txt", "source": "nope.txt"}}))
        workflow.run()
        task = workflow.find_task_by_name("meta-missing-output", "meta")
        self.assertIs(task.status, Status.FAILED)
        self.assertEqual(task.failure_phase, "outputs")

    def test_optional_output_may_be_absent(self):
        workflow = self._workflow("meta-optional")
        workflow.add_task(producer())
        workflow.add_task(meta(engine_path=self.engine,
                               outputs={"x": {"path": "x.txt", "source": "nope.txt", "required": False}}))
        workflow.run()
        self.assertIs(workflow.find_task_by_name("meta-optional", "meta").status, Status.FINISHED)

    def test_timeout_terminates_the_engine(self):
        workflow = self._workflow("meta-timeout")
        workflow.add_task(producer())
        workflow.add_task(meta(engine_path=self.engine, inputs={"text": "workflow:///producer/out/a.txt", "sleep": 30},
                               timeout=1))
        workflow.run()
        task = workflow.find_task_by_name("meta-timeout", "meta")
        self.assertIs(task.status, Status.FAILED)
        self.assertEqual(task.failure_phase, "execution")

    def test_missing_engine_is_reported_without_running(self):
        workflow = self._workflow("meta-unavailable")
        workflow.add_task(DagonTask(TaskType.META, "meta", engine="snakemake", workflow=self.engine,
                                    engine_options={"executable": "dagon-no-such-snakemake"}))
        workflow.run()
        task = workflow.find_task_by_name("meta-unavailable", "meta")
        self.assertIs(task.status, Status.FAILED)
        self.assertEqual(task.failure_phase, "engine")

    @unittest.skipIf(os.name == "nt", "symbolic links need privileges on Windows")
    def test_outputs_outside_scratch_are_refused(self):
        outside = Path(self.directory, "outside.txt")
        outside.write_text("secret", encoding="utf-8")
        script = Path(self.directory, "escape.py")
        script.write_text("import os\nos.symlink(%r, 'leak.txt')\n" % str(outside), encoding="utf-8")
        workflow = self._workflow("meta-escape")
        workflow.add_task(DagonTask(TaskType.META, "meta", engine="command", workflow=str(script),
                                    outputs={"leak": "leak.txt"},
                                    engine_options={"command": [sys.executable, "{workflow}"]}))
        workflow.run()
        task = workflow.find_task_by_name("meta-escape", "meta")
        self.assertIs(task.status, Status.FAILED)
        self.assertEqual(task.failure_phase, "outputs")

    @unittest.skipIf(os.name == "nt", "symbolic links need privileges on Windows")
    def test_symlink_staging(self):
        workflow = self._workflow("meta-symlink")
        workflow.add_task(producer())
        workflow.add_task(meta(engine_path=self.engine, staging="symlink"))
        workflow.run()
        task = workflow.find_task_by_name("meta-symlink", "meta")
        self.assertIs(task.status, Status.FINISHED)
        self.assertTrue(Path(task.working_dir, "inputs", "text", "a.txt").is_symlink())

    def test_checkpoint_reuse_is_reverified(self):
        checkpoint = str(Path(self.directory, "checkpoint.json"))

        def run_once():
            workflow = self._workflow("meta-resume", checkpoint_file=checkpoint)
            workflow.add_task(producer())
            workflow.add_task(meta(engine_path=self.engine))
            workflow.run(checkpoint)
            task = workflow.find_task_by_name("meta-resume", "meta")
            self.assertIs(task.status, Status.FINISHED)
            return task

        first = run_once()
        self.assertFalse(first.fair_checkpoint_reused)
        second = run_once()
        self.assertTrue(second.fair_checkpoint_reused)
        self.assertEqual(second.working_dir, first.working_dir)
        # A changed workflow definition invalidates the checkpoint.
        Path(self.engine).write_text(ENGINE + "\n# changed\n", encoding="utf-8")
        third = run_once()
        self.assertFalse(third.fair_checkpoint_reused)
        # A tampered output invalidates the checkpoint.
        Path(third.working_dir, "outputs", "upper.txt").write_text("tampered", encoding="utf-8")
        self.assertFalse(run_once().fair_checkpoint_reused)

    def test_bare_successful_directory_is_not_reused(self):
        workflow = self._workflow("meta-bare")
        task = meta(engine_path=self.engine)
        workflow.add_task(task)
        workflow.checkpoints["meta-bare.meta"] = {"working_dir": self.directory, "code": 0}
        self.assertFalse(task.reuse_checkpoint())

    def test_portable_emulation_uses_the_mock_engine(self):
        workflow = self._workflow("meta-portable", portable_emulation=True)
        workflow.add_task(producer())
        workflow.add_task(DagonTask(TaskType.META, "meta", engine="nextflow", workflow="nextflow-io/hello",
                                    inputs={"text": "workflow:///producer/out/a.txt"},
                                    outputs={"counts": "results/counts.tsv",
                                             "plots": {"path": "plots", "type": "directory"}}))
        workflow.add_task(DagonTask(TaskType.BATCH, "consumer", "cat workflow:///meta/outputs/results/counts.tsv"))
        workflow.run()
        self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks))
        task = workflow.find_task_by_name("meta-portable", "meta")
        self.assertTrue(task.meta_result["emulated"])
        placeholder = json.loads(Path(task.working_dir, "outputs", "results", "counts.tsv").read_text(encoding="utf-8"))
        self.assertEqual(placeholder["engine"], "nextflow")
        self.assertTrue(placeholder["portable_emulation"])

    def test_fair_records_outputs_and_external_workflow(self):
        fair_dir = str(Path(self.directory, "fair"))
        workflow = self._workflow("meta-fair")
        workflow.enable_fair(FairProfile(title="Meta FAIR", description="External workflow provenance.",
                                         creators=[Agent(name="DAGonStar tests")], license="Apache-2.0",
                                         output_dir=fair_dir))
        workflow.add_task(producer())
        workflow.add_task(meta(engine_path=self.engine))
        workflow.run()
        run = json.loads(Path(fair_dir, "run.json").read_text(encoding="utf-8"))
        artifacts = [item for item in run["artifacts"] if item.get("task") == "meta"]
        self.assertEqual(artifacts[0]["path"], "outputs/upper.txt")
        self.assertTrue(artifacts[0]["checksum"].startswith("sha256:"))
        crate = json.loads(Path(fair_dir, "ro-crate-metadata.json").read_text(encoding="utf-8"))
        workflows = [item for item in crate["@graph"] if "ComputationalWorkflow" in item.get("@type", [])]
        self.assertEqual(workflows[0]["programmingLanguage"], "command")
        self.assertNotIn("DAGON_META_PARAMETERS", json.dumps(run))


class MetaAdapterCommandTests(unittest.TestCase):
    """Each engine adapter builds the engine's documented command and parameter files."""

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.text = Path(self.directory, "text.txt")
        self.text.write_text("a b", encoding="utf-8")
        self.inputs = [MetaInput("text", "file", str(self.text), "workflow:///p/text.txt", "0" * 64),
                       MetaInput("top", "value", 3)]

    def _prepare(self, engine, workflow, options=None):
        options = dict(options or {}, executable=sys.executable) if engine not in ("parsl",) else dict(options or {})
        ctx = context(self.directory, engine, workflow, self.inputs, options)
        get_adapter(engine).validate(workflow, ctx.engine_options)
        return ctx, get_adapter(engine).prepare(ctx)

    def test_nextflow(self):
        ctx, invocation = self._prepare("nextflow", "main.nf", {"profile": "test", "revision": "v1", "resume": True,
                                                               "config": ["site.config"]})
        argv = invocation.argv
        self.assertEqual(argv[1:3], ["-log", str(ctx.metadata_dir / "nextflow.log")])
        self.assertIn("-c", argv)
        self.assertLess(argv.index("-c"), argv.index("run"))
        for flag in ("-params-file", "-work-dir", "-profile", "-r", "-resume", "-with-trace"):
            self.assertIn(flag, argv)
        params = json.loads(Path(argv[argv.index("-params-file") + 1]).read_text(encoding="utf-8"))
        self.assertEqual(params, {"text": str(self.text), "top": 3})

    def test_snakemake(self):
        ctx, invocation = self._prepare("snakemake", "Snakefile", {"cores": 2, "targets": ["all"], "executor": "slurm"})
        argv = invocation.argv
        self.assertEqual(argv[argv.index("--cores") + 1], "2")
        self.assertEqual(argv[argv.index("--directory") + 1], str(ctx.run_dir))
        self.assertEqual(argv[argv.index("--executor") + 1], "slurm")
        self.assertEqual(argv[-1], "all")
        config = json.loads(Path(argv[argv.index("--configfile") + 1]).read_text(encoding="utf-8"))
        self.assertEqual(config["text"], str(self.text))

    def test_parsl_function_and_script_modes(self):
        ctx, invocation = self._prepare("parsl", "flow.py", {"entrypoint": "run", "config": "threads",
                                                            "max_threads": 2})
        self.assertTrue(invocation.argv[1].endswith("parsl_driver.py"))
        job = json.loads(Path(invocation.argv[3]).read_text(encoding="utf-8"))
        self.assertEqual((job["entrypoint"], job["config"], job["max_threads"]), ("run", "threads", 2))
        ctx, invocation = self._prepare("parsl", "flow.py", {"mode": "script", "arguments": ["{inputs[text]}"]})
        self.assertEqual(invocation.argv[1:], ["flow.py", str(self.text)])
        self.assertIn("DAGON_META_PARAMETERS", invocation.environment)

    def test_cwl_and_streamflow_job_documents(self):
        ctx, invocation = self._prepare("cwl", "wf.cwl", {"arguments": ["--no-container"]})
        job = json.loads(Path(invocation.argv[-1]).read_text(encoding="utf-8"))
        self.assertEqual(job, {"text": {"class": "File", "path": str(self.text)}, "top": 3})
        self.assertIn("--no-container", invocation.argv)
        ctx, invocation = self._prepare("streamflow", str(Path(self.directory, "wf.cwl")),
                                        {"deployments": {"local": {"type": "local", "config": {}}},
                                         "bindings": [{"step": "/count", "target": {"deployment": "local"}}]})
        self.assertEqual(invocation.argv[1], "run")
        document = json.loads(Path(invocation.argv[2]).read_text(encoding="utf-8"))
        workflow = document["workflows"]["dagon"]
        self.assertEqual(workflow["type"], "cwl")
        self.assertTrue(workflow["config"]["settings"].endswith("cwl-job.json"))
        self.assertIn("local", document["deployments"])
        self.assertTrue(document["database"]["config"]["connection"].endswith("streamflow.db"))

    def test_existing_streamflow_file_is_derived_not_modified(self):
        original = Path(self.directory, "streamflow.json")
        source = {"version": "v1.0", "workflows": {"main": {"type": "cwl", "config": {"file": "wf.cwl",
                                                                                     "settings": "old.yml"}}}}
        original.write_text(json.dumps(source), encoding="utf-8")
        ctx, invocation = self._prepare("streamflow", str(original))
        derived = json.loads(Path(invocation.argv[2]).read_text(encoding="utf-8"))
        self.assertEqual(derived["workflows"]["main"]["config"]["file"], str(Path(self.directory, "wf.cwl").resolve()))
        self.assertEqual(json.loads(original.read_text(encoding="utf-8")), source)

    def test_cwl_reported_outputs_are_parsed(self):
        from dagon.meta.adapters.cwl import reported_outputs
        stdout = 'INFO log line\n{\n  "counts": {"class": "File", "location": "file:///tmp/a%20b.tsv"},\n' \
                 '  "n": 3\n}\n'
        self.assertEqual(reported_outputs(stdout), {"counts": "/tmp/a b.tsv"})

    def test_version_parser_ignores_interpreter_paths(self):
        from dagon.meta.adapters.base import _first_version
        self.assertEqual(_first_version("/usr/lib/python3.12/bin/cwltool 3.1.2024"), "3.1.2024")


class MetaRegistryTests(unittest.TestCase):
    def tearDown(self):
        unregister_adapter("echo-engine")

    def test_a_new_engine_needs_only_an_adapter(self):
        class EchoAdapter(MetaEngineAdapter):
            name = "echo-engine"

            def capabilities(self):
                # "anything" is resolved by the engine, not a local file.
                return EngineCapabilities(remote_workflows=True)

            def prepare(self, ctx):
                parameters = ctx.write_json("echo.json", ctx.parameters)
                code = "import shutil,sys; shutil.copy(sys.argv[1], 'echo.json')"
                return EngineInvocation(argv=[sys.executable, "-c", code, str(parameters)], cwd=ctx.run_dir)

        register_adapter("echo-engine", EchoAdapter)
        self.assertIn("echo-engine", adapter_names())
        with self.assertRaises(ValueError):
            register_adapter("nextflow", EchoAdapter)
        with self.assertRaises(TypeError):
            register_adapter("not-an-adapter", object)
        with tempfile.TemporaryDirectory() as directory:
            workflow = Workflow("meta-plugin", config=scratch_config(directory))
            workflow.add_task(DagonTask(TaskType.META, "meta", engine="echo-engine", workflow="anything",
                                        inputs={"n": 7}, outputs={"echo": "echo.json"}))
            workflow.run()
            task = workflow.find_task_by_name("meta-plugin", "meta")
            self.assertIs(task.status, Status.FINISHED)
            self.assertEqual(json.loads(Path(task.working_dir, "outputs", "echo.json").read_text()), {"n": 7})


class MetaCWLExportTests(unittest.TestCase):
    def test_meta_step_binds_references_and_runs_the_meta_runner(self):
        workflow = Workflow("meta-cwl", config=minimal_config())
        workflow.add_task(producer())
        workflow.add_task(DagonTask(TaskType.META, "meta", engine="snakemake", workflow=str(WORKFLOWS / "Snakefile"),
                                    inputs={"text": "workflow:///producer/out/a.txt", "top": 3},
                                    outputs={"counts": {"path": "counts.tsv", "source": "results/counts.tsv"}}))
        workflow.add_task(DagonTask(TaskType.META, "again", engine="snakemake", workflow=str(WORKFLOWS / "Snakefile"),
                                    inputs={"text": "workflow:///meta/outputs/counts.tsv"},
                                    outputs={"counts": "results/counts.tsv"}))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "meta.cwl")
            workflow.saveAsCWL(target)
            first = target.read_text(encoding="utf-8")
            workflow.saveAsCWL(target)
            self.assertEqual(first, target.read_text(encoding="utf-8"))
            document = json.loads(first)
            if shutil.which("cwltool"):
                subprocess.run(["cwltool", "--validate", str(target)], check=True, capture_output=True, text=True)
        step = document["steps"]["meta"]
        self.assertEqual(step["run"]["baseCommand"], ["dagon-meta-runner", "run"])
        self.assertEqual(step["in"]["in_0"], "producer/file_out_a_txt")
        self.assertIn("--bind", step["run"]["arguments"])
        self.assertEqual(step["run"]["hints"]["dagon:MetaTask"]["engine"], "snakemake")
        self.assertEqual(len(step["run"]["hints"]["dagon:MetaTask"]["workflow_sha256"]), 64)
        self.assertIn("counts", step["out"])
        self.assertEqual(document["steps"]["again"]["in"]["in_0"], "meta/file_outputs_counts_tsv")
        self.assertIn("dagon", document["$namespaces"])

    def test_meta_runner_cli_runs_a_specification(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = write_engine(directory)
            text = Path(directory, "text.txt")
            text.write_text("abc", encoding="utf-8")
            task = meta(engine_path=engine, inputs={"text": "workflow:///producer/out/a.txt"})
            spec = Path(directory, "spec.json")
            spec.write_text(json.dumps(task.portable_spec()), encoding="utf-8")
            workdir = Path(directory, "work")
            workdir.mkdir()
            environment = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]))
            completed = subprocess.run([sys.executable, "-m", "dagon.meta.runner", "run", "--spec", str(spec),
                                        "--workdir", str(workdir), "--bind",
                                        "workflow:///producer/out/a.txt=%s" % text],
                                       capture_output=True, text=True, env=environment)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(Path(workdir, "outputs", "upper.txt").read_text(encoding="utf-8"), "ABC")


def _parsl_python():
    candidate = os.environ.get("DAGON_META_PARSL_PYTHON", sys.executable)
    try:
        return candidate if subprocess.run([candidate, "-c", "import parsl"], capture_output=True).returncode == 0 \
            else None
    except OSError:
        return None


class MetaLiveEngineTests(unittest.TestCase):
    """Word count through each installed engine; skipped when an engine is absent."""

    def _run(self, engine, workflow_file, options, output):
        with tempfile.TemporaryDirectory() as directory:
            workflow = Workflow("live-" + engine, config=scratch_config(directory))
            workflow.add_task(DagonTask(TaskType.BATCH, "producer",
                                        "mkdir -p data; printf 'b a b c b a\\n' > data/text.txt"))
            workflow.add_task(DagonTask(TaskType.META, "count", engine=engine, workflow=str(WORKFLOWS / workflow_file),
                                        inputs={"text": "workflow:///producer/data/text.txt", "top": 2},
                                        outputs={"counts": output}, engine_options=options, timeout=900))
            workflow.add_task(DagonTask(TaskType.BATCH, "report", "cp workflow:///count/outputs/counts.tsv top.tsv"))
            workflow.run()
            count = workflow.find_task_by_name(workflow.name, "count")
            self.assertTrue(all(task.status is Status.FINISHED for task in workflow.tasks),
                            Path(count.working_dir or ".", ".dagon", "engine_stderr.txt").read_text(encoding="utf-8")
                            if count.working_dir and Path(count.working_dir, ".dagon", "engine_stderr.txt").is_file()
                            else count.status)
            report = workflow.find_task_by_name(workflow.name, "report")
            self.assertEqual(Path(report.working_dir, "top.tsv").read_text(encoding="utf-8"), "b\t3\na\t2\n")

    @unittest.skipUnless(shutil.which("snakemake"), "Snakemake is not installed")
    def test_snakemake(self):
        self._run("snakemake", "Snakefile", {"cores": 1}, {"path": "counts.tsv", "source": "results/counts.tsv"})

    @unittest.skipUnless(_parsl_python(), "Parsl is not installed (set DAGON_META_PARSL_PYTHON)")
    def test_parsl(self):
        self._run("parsl", "wordcount_parsl.py", {"python": _parsl_python()},
                  {"path": "counts.tsv", "source": "results/counts.tsv"})

    @unittest.skipUnless(shutil.which("nextflow"), "Nextflow is not installed")
    def test_nextflow(self):
        self._run("nextflow", "main.nf", {}, {"path": "counts.tsv", "source": "results/counts.tsv"})

    @unittest.skipUnless(shutil.which("streamflow"), "StreamFlow is not installed")
    def test_streamflow(self):
        self._run("streamflow", "wordcount.cwl", {}, {"path": "counts.tsv", "engine_output": "counts"})

    @unittest.skipUnless(shutil.which("cwltool") and os.name != "nt", "cwltool is not installed")
    def test_cwltool(self):
        self._run("cwl", "wordcount.cwl", {"arguments": ["--no-container"]},
                  {"path": "counts.tsv", "engine_output": "counts"})


if __name__ == "__main__":
    unittest.main()
