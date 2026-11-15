"""``TaskType.AGENTIC``: a bounded, evaluated agent as an ordinary workflow task."""
import json
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dagon.agentic.config import EffectiveProfile, resolve_profile
from dagon.agentic.engine import COMMIT_MANIFEST, AgentEngine, compute_identity
from dagon.agentic.errors import AgenticError, AgenticValidationError
from dagon.agentic.models import contract_references, normalize_contract, parse_reference
from dagon.agentic.providers import prepare_adapter
from dagon.agentic.registry import Registry, default_registry
from dagon.agentic.security import contained_path, sha256_file
from dagon.task import Task, TaskType

RUNNER_COMMAND = "dagon-agent-runner run --spec .dagon/agentic/task.json --config dagon.ini --workdir ."


class AgenticTask(Task):
    """Run a named agent profile against a declared contract and publish only an accepted result.

    The declaration selects a profile (``agent``) from ``dagon.ini``; it never
    contains endpoints, models, keys, adapter configuration, or code.  ``tools``
    may only narrow the profile's tools (``None`` inherits them, ``[]`` disables
    them), ``budgets`` may only lower the profile's budgets, and ``guardrails``
    are added to the profile's guardrails.  See ``docs/agentic_tasks.md``.
    """

    task_type = TaskType.AGENTIC

    def __init__(self, name: str, agent: Optional[str] = None, specification: Any = None,
                 requirements: Any = None, evaluation: Any = None, inputs: Any = None, outputs: Any = None,
                 tools: Optional[List[str]] = None, guardrails: Optional[List[str]] = None,
                 budgets: Optional[Dict[str, Any]] = None, working_dir: Optional[str] = None,
                 transversal_workflow: Optional[str] = None, globusendpoint: Optional[str] = None,
                 pre_stage: Optional[bool] = None, registry: Optional[Registry] = None) -> None:
        self.registry = registry or default_registry()
        self.contract = normalize_contract(agent, specification, requirements, evaluation, inputs, outputs,
                                           tools, guardrails, budgets, self.registry)
        super().__init__(name, RUNNER_COMMAND, working_dir=working_dir, transversal_workflow=transversal_workflow,
                         globusendpoint=globusendpoint)
        self.pre_stage = pre_stage
        self.cancel_event = threading.Event()
        self.agentic_report: Optional[Dict[str, Any]] = None
        self.effective_profile: Optional[EffectiveProfile] = None
        self.engine: Optional[AgentEngine] = None

    # -- declaration ---------------------------------------------------------------

    @property
    def agent(self) -> str:
        return self.contract["agent"]

    @property
    def outputs(self) -> Dict[str, str]:
        return dict(self.contract["outputs"])

    def portable_spec(self) -> Dict[str, Any]:
        """Return the versioned, logical contract (no paths, endpoints, or secrets)."""
        return json.loads(json.dumps(self.contract))

    def as_json(self) -> Dict[str, Any]:
        task = super().as_json()
        task.update({"type": "agentic", "command": None, "agentic": self.portable_spec()})
        task.pop("working_dir", None)
        return task

    def cancel(self) -> None:
        """Request cancellation: managed processes are terminated and nothing is published."""
        self.cancel_event.set()

    # -- graph ----------------------------------------------------------------------

    def _find_producer(self, workflow_name: str, task_name: str) -> Any:
        if self.workflows:
            for workflow in self.workflows:
                task = workflow.find_task_by_name(workflow_name, task_name)
                if task is not None:
                    return task
            return None
        return self.workflow.find_task_by_name(workflow_name, task_name)

    def _producers(self) -> List[Tuple[str, str, str, Any]]:
        found = []
        for reference in contract_references(self.contract):
            workflow_name, task_name, relative = parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            found.append((reference, workflow_name, relative, self._find_producer(workflow_name, task_name)))
        return found

    def pre_run(self) -> None:
        """Infer one dependency (and one reference count) per producer from every contract field."""
        if self.dag_tps is not None:
            self.workflows = self.dag_tps.workflows
        seen = set()
        for reference, workflow_name, _, producer in self._producers():
            if producer is None:
                raise AgenticValidationError("agentic input producer was not found: %s" % reference)
            if producer is self:
                raise AgenticValidationError("an agentic task cannot consume its own outputs: %s" % reference)
            if id(producer) in seen:
                continue
            seen.add(id(producer))
            if workflow_name == self.workflow.name:
                if producer not in self.prevs:
                    self.add_dependency_to(producer)
            elif producer not in self.prevs:
                self.add_transversal_point(producer)
            producer.increment_reference_count()

    def _release_references(self) -> None:
        seen = set()
        for _, _, _, producer in self._producers():
            if producer is not None and id(producer) not in seen:
                seen.add(id(producer))
                producer.decrement_reference_count()

    # -- configuration, staging, identity ---------------------------------------------

    def resolve_profile(self) -> EffectiveProfile:
        """Preflight: resolve the named profile before any provider, tool, or transfer."""
        profile = resolve_profile(self.workflow.cfg, self.contract["agent"], self.contract["tools"],
                                  self.contract["guardrails"], self.contract["budgets"], self.registry)
        self.effective_profile = profile
        return profile

    def _source(self, workflow_name: str, relative: str, producer: Any, reference: str) -> Path:
        if producer is None or not producer.working_dir:
            raise AgenticValidationError("agentic input producer is unavailable: %s" % reference)
        if not Path(producer.working_dir).is_dir():
            raise AgenticValidationError(
                "agentic tasks stage inputs only from producer directories readable on the submission host; "
                "%s is not (remote-only producers are not supported in v1): %s" % (producer.name, reference))
        return contained_path(producer.working_dir, relative, "input " + reference, must_exist=True)

    def reference_hashes(self) -> Dict[str, str]:
        """Hash every referenced producer artifact in place (no copy, no mutation)."""
        return {reference: sha256_file(self._source(workflow_name, relative, producer, reference))
                for reference, workflow_name, relative, producer in self._producers()}

    def _stage(self) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, str]]:
        staged: Dict[str, str] = {}
        hashes: Dict[str, str] = {}
        for reference, workflow_name, relative, producer in self._producers():
            if reference in staged:
                continue
            source = self._source(workflow_name, relative, producer, reference)
            digest = sha256_file(source)
            destination = Path(self.working_dir, ".dagon", "inputs", workflow_name, producer.name, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(source), str(destination))
            if sha256_file(destination) != digest:
                raise AgenticValidationError("staged content of %s does not match its source" % reference)
            staged[reference], hashes[reference] = str(destination), digest
        inputs = {}
        for name, descriptor in self.contract["inputs"].items():
            path = staged[descriptor["uri"]]
            inputs[name] = dict(descriptor, path=path, sha256=hashes[descriptor["uri"]], size=Path(path).stat().st_size)
        return inputs, staged, hashes

    # -- checkpoint -------------------------------------------------------------------

    def _checkpoint_problem(self, checkpoint: Dict[str, Any]) -> Optional[str]:
        if checkpoint.get("task_type") != "agentic" or checkpoint.get("schema_version") != 1:
            return "no agentic checkpoint record"
        if checkpoint.get("code") != 0 or checkpoint.get("accepted") is not True:
            return "the previous run was not accepted"
        working_dir = checkpoint.get("working_dir")
        if not isinstance(working_dir, str) or not Path(working_dir).is_dir():
            return "the previous working directory is not accessible"
        manifest = Path(working_dir, COMMIT_MANIFEST)
        if not manifest.is_file() or sha256_file(manifest) != checkpoint.get("commit_sha256"):
            return "the commit manifest is missing or changed"
        commit = json.loads(manifest.read_text(encoding="utf-8"))
        if commit.get("accepted") is not True or commit.get("identity_digest") != checkpoint.get("identity_digest"):
            return "the commit manifest does not match the checkpoint"
        evaluation = None
        for output in commit.get("outputs", []):
            target = contained_path(working_dir, output["path"], "checkpoint output")
            if not target.is_file() or sha256_file(target) != output.get("sha256"):
                return "output %s is missing or was modified" % output.get("path")
            if output.get("name") == "evaluation":
                evaluation = json.loads(target.read_text(encoding="utf-8"))
        if not evaluation or evaluation.get("accepted") is not True or \
                evaluation.get("digests", {}).get("identity") != checkpoint.get("identity_digest"):
            return "the evaluation report does not confirm acceptance for this identity"
        profile = self.resolve_profile()
        identity = compute_identity(self.contract, profile, self.registry, self.reference_hashes(),
                                    self.workflow.name, self.name)
        if identity["identity_digest"] != checkpoint.get("identity_digest"):
            return "the contract, effective profile, versions, or input content changed"
        self.agentic_report = evaluation
        return None

    def reuse_checkpoint(self) -> bool:
        """Reuse only an accepted run whose identity, manifest, and output hashes all re-verify."""
        checkpoint = self.workflow.checkpoints.get(self.checkpoint_key(), {})
        try:
            problem = self._checkpoint_problem(checkpoint)
        except (AgenticError, OSError, ValueError, KeyError) as exc:
            problem = "verification failed: %s" % exc
        if problem is not None:
            if checkpoint:
                self.workflow.logger.info("%s: agentic checkpoint not reused: %s", self.name, problem)
            return False
        self.working_dir = checkpoint["working_dir"]
        self.fair_checkpoint_reused = True
        return True

    # -- execution ----------------------------------------------------------------------

    def execute(self) -> None:
        profile = self.resolve_profile()
        if self.workflow.dry:
            # Dry run: validation only -- no scratch, transfer, provider, or tool call.
            for reference, _, _, producer in self._producers():
                if producer is None:
                    raise AgenticValidationError("agentic input producer was not found: %s" % reference)
            return
        if self.reuse_checkpoint():
            self._release_references()
            return
        self.create_working_dir()
        checkpoint = self.initialize_checkpoint()
        checkpoint.update({"task_type": "agentic", "schema_version": 1, "status": "RUNNING", "accepted": False})
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            inputs, staged, hashes = self._stage()
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        identity = compute_identity(self.contract, profile, self.registry, hashes, self.workflow.name, self.name)
        checkpoint["identity_digest"] = identity["identity_digest"]
        spec_path = Path(self.working_dir, ".dagon", "agentic", "task.json")
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(self.portable_spec(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # The adapter starts inside the engine, so worker start-up counts against the run's deadline.
        adapter, secrets, emulation = prepare_adapter(profile, self.workflow.cfg, self.registry,
                                                      self.workflow.is_portable_emulation() is True)
        self.workflow._fire_event("on_task_execute_start", self)
        self.engine = AgentEngine(self.contract, profile, adapter, inputs, staged, self.working_dir, self.registry,
                                  identity, self.cancel_event, secrets, emulation)
        try:
            report = self.engine.run()
        except AgenticError as exc:
            self.agentic_report = getattr(exc, "report", None)
            checkpoint.update({"code": 1, "status": "FAILED", "termination_reason": self.engine.termination_reason})
            raise
        manifest = Path(self.working_dir, COMMIT_MANIFEST)
        commit = self.engine.commit or {}
        checkpoint.update({"code": 0, "status": "SUCCEEDED", "accepted": True, "result_fit": report["result_fit"],
                           "commit_sha256": sha256_file(manifest), "outputs": commit.get("outputs", [])})
        self.agentic_report = report
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            self._release_references()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)

    def get_execution_metadata(self) -> Dict[str, Any]:
        """Return safe provenance: profile name/digest, outcome, and versions; never endpoints or keys."""
        report = self.agentic_report or {}
        metadata = {"model": "agentic", "agent_profile": self.contract["agent"],
                    "accepted": report.get("accepted", False), "result_fit": report.get("result_fit"),
                    "termination_reason": report.get("termination_reason"),
                    "contract_digest": report.get("digests", {}).get("contract"),
                    "profile_digest": report.get("digests", {}).get("configuration")}
        if report:
            metadata.update({"usage": {key: report["usage"][key] for key in ("steps", "tool_calls", "attempts")},
                             "evaluator_versions": report.get("evaluator_versions"),
                             "tool_versions": report.get("tool_versions"),
                             "guardrail_versions": report.get("guardrail_versions"),
                             "execution": report.get("execution")})
        return metadata
