"""The supervised, bounded agent loop and accepted-output publication.

Phases: validate -> stage -> initialize -> propose -> validate action ->
execute tool -> observe -> evaluate candidate -> revise or accept -> publish.
The same engine runs inside :class:`dagon.agentic.task.AgenticTask` and the
``dagon-agent-runner`` command used by CWL.

Publication protocol (inside the task directory):

1. At start, remove any previous commit manifest, then previous declared
   outputs and attempt directories (crash cleanup).
2. Candidates live in ``.dagon/agentic/attempts/NN/`` (attempt-private).
3. On acceptance, the result, trace, and evaluation report are each written
   through a temporary file and ``os.replace``; the commit manifest
   ``.dagon/agentic/commit.json`` is written *last*.  Multi-file publication is
   not atomic as a whole: only the commit manifest plus task success signal
   readiness.  A crash before the manifest leaves no reusable checkpoint.
4. On failure, diagnostics (evaluation report with ``accepted: false`` and the
   bounded trace) are written; the result file and commit manifest are not.
"""
import json
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from dagon.agentic import guardrails as guards
from dagon.agentic.config import EffectiveProfile
from dagon.agentic.errors import (AgenticBudgetExhausted, AgenticCancelled, AgenticError,
                                  AgenticEvaluationError, AgenticGuardrailViolation, AgenticNotAccepted,
                                  AgenticTimeoutError, AgenticToolError, AgenticValidationError)
from dagon.agentic.evaluation import aggregate, evaluate
from dagon.agentic.models import contract_references
from dagon.agentic.registry import Registry
from dagon.agentic.sandbox import call_in_process, call_inline
from dagon.agentic.schema import validate as validate_schema
from dagon.agentic.security import (atomic_write_text, bounded_dumps, contained_path, json_copy, redact,
                                    sha256_file, sha256_json)

REPORT_SCHEMA_VERSION = 1
AGENTIC_DIR = ".dagon/agentic"
COMMIT_MANIFEST = AGENTIC_DIR + "/commit.json"
_SELF_ASSESSMENT = ("score", "accepted", "self_score", "result_fit", "confidence")


class AgentEngine(object):
    """Run one agentic task contract to an accepted publication or a typed failure."""

    def __init__(self, contract: Dict[str, Any], profile: EffectiveProfile, adapter: Any,
                 inputs: Dict[str, Dict[str, Any]], references: Dict[str, str], workdir: Any,
                 registry: Registry, identity: Dict[str, Any], cancel_event: Optional[threading.Event] = None,
                 secrets: Optional[List[str]] = None, emulation: Optional[Dict[str, Any]] = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.contract = contract
        self.profile = profile
        self.adapter = adapter
        self.inputs = inputs
        self.references = references
        self.workdir = Path(workdir)
        self.registry = registry
        self.identity = identity
        self.cancel_event = cancel_event or threading.Event()
        self.secrets = list(secrets or [])
        self.emulation = emulation or {"portable_emulation": False}
        self.clock = clock
        self.budgets = dict(profile.budgets)
        self.steps = self.tool_calls = self.attempt = 0
        self.tokens: Dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "sources": []}
        self.history: List[Dict[str, Any]] = []
        self.trace: List[Dict[str, Any]] = []
        self.attempts: List[Dict[str, Any]] = []
        self.feedback: List[Dict[str, Any]] = []
        self.input_documents: Dict[str, Any] = {}
        self.last_results: List[Dict[str, Any]] = []
        self.last_aggregate: Dict[str, Any] = {"result_fit": None, "accepted": False, "hard_checks": [],
                                               "mandatory_failures": [], "evaluator_errors": []}
        self.selected_attempt: Optional[int] = None
        self.candidate: Any = None
        self.termination_reason = "not_started"
        self.started = 0.0
        self.report: Optional[Dict[str, Any]] = None
        self.commit: Optional[Dict[str, Any]] = None

    # -- bookkeeping ------------------------------------------------------------

    def remaining(self) -> float:
        return float(self.budgets["timeout_seconds"]) - (self.clock() - self.started)

    def _check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise AgenticCancelled("the agentic task was cancelled")

    def _event(self, event: str, **fields: Any) -> None:
        entry = {"step": self.steps, "event": event}
        entry.update(fields)
        self.trace.append(redact(entry, self.secrets))

    def _budget(self, name: str) -> AgenticBudgetExhausted:
        self.termination_reason = name + "_exhausted"
        return AgenticBudgetExhausted("budget %s=%s exhausted before an accepted result"
                                      % (name, self.budgets.get(name)))

    def _output(self, name: str) -> Path:
        return contained_path(self.workdir, self.contract["outputs"][name], "output " + name)

    def _prepare(self) -> None:
        agentic = self.workdir / ".dagon" / "agentic"
        agentic.mkdir(parents=True, exist_ok=True)
        manifest = self.workdir / COMMIT_MANIFEST
        if manifest.exists() or manifest.is_symlink():
            manifest.unlink()
        for name in self.contract["outputs"]:
            target = self._output(name)
            if target.is_symlink() or target.is_file():
                target.unlink()
        shutil.rmtree(str(agentic / "attempts"), ignore_errors=True)

    # -- phases -------------------------------------------------------------------

    def _input_guards(self) -> None:
        for name, descriptor in self.inputs.items():
            path = Path(descriptor["path"])
            if not path.is_file():
                raise AgenticValidationError("staged input %s is missing" % name)
            if not descriptor.get("binary") and descriptor.get("media_type", "").endswith("json"):
                try:
                    with open(str(path), encoding="utf-8") as stream:
                        self.input_documents[name] = json_copy(json.load(stream), "input " + name)
                except (ValueError, UnicodeDecodeError) as exc:
                    violation = guards.Violation("runtime", "input", "invalid_input",
                                                 "input %s is not valid finite JSON: %s" % (name, str(exc)[:200]))
                    self._violation(violation)
        for violation in guards.run_guards("input", self.profile.guardrails, self.input_documents,
                                           self._guard_context(), self.registry, self._guard_timeout(),
                                           self.cancel_event):
            self._violation(violation)

    def _guard_timeout(self) -> float:
        return max(0.001, min(10.0, self.remaining()))

    def _guard_context(self) -> Dict[str, Any]:
        return {"input_documents": self.input_documents, "specification": self.contract["specification"],
                "inputs": {name: {key: value for key, value in item.items() if key != "path"}
                           for name, item in self.inputs.items()}}

    def _violation(self, violation: guards.Violation) -> None:
        self._event("guardrail", **violation.as_dict())
        if not violation.retryable:
            self.termination_reason = "guardrail_blocked"
            raise AgenticGuardrailViolation("%s blocked by %s: %s" % (violation.stage, violation.guard,
                                                                      violation.reason), violation.as_dict())
        self.feedback = [{"kind": "guardrail", "code": violation.code, "reason": violation.reason,
                          "evidence": violation.evidence}]

    def _state(self) -> Dict[str, Any]:
        public_requirements = [{key: item[key] for key in ("id", "description", "evaluator", "expected", "weight",
                                                            "mandatory", "minimum_score", "hard", "options")}
                               for item in self.contract["requirements"]]
        return {
            "specification": self.contract["specification"], "requirements": public_requirements,
            "threshold": self.contract["evaluation"]["threshold"],
            "inputs": {name: dict(item) for name, item in self.inputs.items()},
            "tools": [self.registry.tools[item].public() for item in self.profile.tools],
            "history": list(self.history[-20:]), "feedback": list(self.feedback), "attempt": self.attempt,
            "step": self.steps,
            "remaining": {"steps": self.budgets["max_steps"] - self.steps,
                          "tool_calls": self.budgets["max_tool_calls"] - self.tool_calls,
                          "attempts": self.budgets["max_attempts"] - self.attempt,
                          "tokens": self.budgets["max_tokens"] - self.tokens["total_tokens"],
                          "seconds": round(self.remaining(), 3)},
        }

    def _start_adapter(self) -> None:
        """Start a deferred adapter within the run's deadline (worker start-up counts against it)."""
        from dagon.agentic.providers import AdapterStarter
        if isinstance(self.adapter, AdapterStarter):
            try:
                self.adapter = self.adapter(self.remaining(), self.cancel_event)
            except AgenticTimeoutError:
                raise self._budget("timeout_seconds")

    def _loop(self) -> None:
        while True:
            self._check_cancel()
            if self.steps >= self.budgets["max_steps"]:
                raise self._budget("max_steps")
            if self.remaining() <= 0:
                raise self._budget("timeout_seconds")
            tokens_left = self.budgets["max_tokens"] - self.tokens["total_tokens"]
            if tokens_left <= 0:
                raise self._budget("max_tokens")
            self.steps += 1
            try:
                if getattr(self.adapter, "supervised", False):
                    # Process-isolated adapter: killed with its process group at the deadline.
                    response, usage = self.adapter.propose(self._state(), tokens_left, self.remaining(),
                                                           self.cancel_event)
                else:
                    response, usage = call_inline(self.adapter.propose,
                                                  [self._state(), tokens_left, self.remaining()],
                                                  self.remaining(), self.cancel_event)
            except AgenticTimeoutError:
                raise self._budget("timeout_seconds")
            self._account(usage)
            if self.tokens["total_tokens"] > self.budgets["max_tokens"]:
                self._event("proposal_discarded", reason="token budget exceeded by this response")
                raise self._budget("max_tokens")
            if not isinstance(response, dict) or response.get("action") not in ("tool", "submit"):
                self._event("malformed_response", summary=str(response)[:200])
                self.feedback = [{"kind": "protocol", "code": "malformed_response",
                                  "reason": "reply with one JSON object whose action is 'tool' or 'submit'"}]
                self.history.append({"step": self.steps, "type": "malformed"})
                continue
            ignored = sorted(key for key in _SELF_ASSESSMENT if key in response)
            if ignored:
                self._event("self_assessment_ignored", fields=ignored)
            if response["action"] == "tool":
                self._tool(response.get("tool"), response.get("arguments", {}))
            elif self._submit(response.get("candidate")):
                self.termination_reason = "accepted"
                return

    def _account(self, usage: Any) -> None:
        usage = usage if isinstance(usage, dict) else {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key, 0)
            self.tokens[key] += int(value) if isinstance(value, int) and value > 0 else 0
        source = usage.get("source", "none")
        if source not in self.tokens["sources"]:
            self.tokens["sources"].append(source)

    def _tool(self, tool: Any, arguments: Any) -> None:
        violation = guards.check_action(tool, arguments, self.profile.tools, self.registry)
        if violation is not None:
            self.history.append({"step": self.steps, "type": "tool", "tool": str(tool)[:128],
                                 "rejected": violation.code})
            self._violation(violation)
            return
        if self.tool_calls >= self.budgets["max_tool_calls"]:
            raise self._budget("max_tool_calls")
        spec = self.registry.tools[tool]
        subject = {"tool": tool, "arguments": arguments, "side_effect": spec.side_effect}
        for violation in guards.run_guards("pre_action", self.profile.guardrails, subject, self._guard_context(),
                                           self.registry, self._guard_timeout(), self.cancel_event):
            self.history.append({"step": self.steps, "type": "tool", "tool": tool, "rejected": violation.code})
            self._violation(violation)
            return
        self.tool_calls += 1
        attempt_dir = self.workdir / AGENTIC_DIR / "attempts" / ("tool-%02d" % self.tool_calls)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        context = {"inputs": {name: {"path": item["path"], "binary": item["binary"],
                                     "media_type": item["media_type"]} for name, item in self.inputs.items()},
                   "attempt_dir": str(attempt_dir)}
        bound = min(spec.max_output_bytes, self.budgets["max_tool_output_bytes"])
        timeout = min(spec.timeout_seconds, self.remaining())
        started = self.clock()
        try:
            if spec.isolation == "process":
                result = call_in_process(str(spec.function), [arguments, context], timeout, bound, self.cancel_event)
            else:
                result = call_inline(spec.function, [arguments, context], timeout, self.cancel_event)
            bounded_dumps(result, bound)
        except AgenticCancelled:
            raise
        except (AgenticTimeoutError, AgenticToolError, ValueError, TypeError) as exc:
            if self.remaining() <= 0:
                raise self._budget("timeout_seconds")
            message = "%s: %s" % (type(exc).__name__, str(exc)[:300])
            self._event("tool", tool=tool, version=spec.version, status="error", error=message)
            self.history.append({"step": self.steps, "type": "tool", "tool": tool, "error": message})
            self.feedback = [{"kind": "tool", "code": "tool_failed", "tool": tool, "reason": message}]
            return
        errors = validate_schema(result, spec.result_schema)
        if errors:
            self._violation(guards.Violation("runtime", "post_action", "invalid_tool_result",
                                             "tool result does not match its schema", {"errors": errors[:10]},
                                             retryable=True))
            return
        subject = {"tool": tool, "arguments": arguments, "result": result}
        for violation in guards.run_guards("post_action", self.profile.guardrails, subject, self._guard_context(),
                                           self.registry, self._guard_timeout(), self.cancel_event):
            self._violation(violation)
            return
        self._event("tool", tool=tool, version=spec.version, status="ok", arguments=arguments,
                    observation_sha256=sha256_json(result), observation_bytes=len(json.dumps(result)),
                    seconds=round(self.clock() - started, 3))
        self.history.append({"step": self.steps, "type": "tool", "tool": tool, "arguments": arguments,
                             "observation": result})
        self.feedback = []

    def _submit(self, candidate: Any) -> bool:
        self.attempt += 1
        if self.attempt > self.budgets["max_attempts"]:
            raise self._budget("max_attempts")
        attempt_dir = self.workdir / AGENTIC_DIR / "attempts" / ("%02d" % self.attempt)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        summary: Dict[str, Any] = {"attempt": self.attempt, "step": self.steps, "result_fit": None,
                                   "accepted": False, "failed_requirements": [], "guard_violations": []}
        self.attempts.append(summary)
        violation = guards.check_candidate(candidate, self.contract["specification"].get("output_schema"),
                                           contract_references(self.contract))
        violations = [violation] if violation is not None else []
        if not violations:
            candidate = json_copy(candidate, "candidate")
            (attempt_dir / "candidate.json").write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                                                        encoding="utf-8")
            violations = guards.run_guards("result", self.profile.guardrails, candidate, self._guard_context(),
                                           self.registry, self._guard_timeout(), self.cancel_event)
        if violations:
            summary["guard_violations"] = [item.code for item in violations]
            self.history.append({"step": self.steps, "type": "candidate", "attempt": self.attempt,
                                 "rejected": summary["guard_violations"]})
            for item in violations:
                self._violation(item)
            return False
        context = {"specification": self.contract["specification"], "references": dict(self.references),
                   "inputs": {name: {key: value for key, value in item.items()} for name, item in self.inputs.items()}}
        results = evaluate(self.contract, candidate, context, self.registry, self.remaining, self.cancel_event)
        outcome = aggregate(results, self.contract["evaluation"]["threshold"])
        self.last_results, self.last_aggregate = results, outcome
        summary.update({"result_fit": outcome["result_fit"], "accepted": outcome["accepted"],
                        "failed_requirements": [item["id"] for item in results if item["status"] != "pass"]})
        self._event("candidate", attempt=self.attempt, result_fit=outcome["result_fit"],
                    accepted=outcome["accepted"], failed_requirements=summary["failed_requirements"],
                    candidate_sha256=sha256_json(candidate))
        if outcome["evaluator_errors"]:
            self.termination_reason = "evaluator_error"
            raise AgenticEvaluationError("evaluator error(s) for requirement(s): %s"
                                         % ", ".join(outcome["evaluator_errors"]))
        if outcome["accepted"]:
            self.selected_attempt = self.attempt
            self.candidate = candidate
            return True
        self.feedback = [{"kind": "evaluation", "requirement": item["id"], "status": item["status"],
                          "score": item["score"], "observation": item["observation"]}
                         for item in results if item["status"] != "pass"] or \
            [{"kind": "evaluation", "reason": "result fit %.6g is below threshold %.6g"
              % (outcome["result_fit"], outcome["threshold"])}]
        self.history.append({"step": self.steps, "type": "candidate", "attempt": self.attempt,
                             "result_fit": outcome["result_fit"], "accepted": False})
        return False

    # -- reporting and publication ----------------------------------------------

    def _bounded_trace(self) -> Dict[str, Any]:
        entries = list(self.trace)
        document: Dict[str, Any] = {"schema_version": REPORT_SCHEMA_VERSION, "truncated": False, "entries": entries,
                    "note": "structured action summaries only; no model reasoning text is stored"}
        limit = int(self.budgets["max_trace_bytes"])
        while len(json.dumps(document).encode("utf-8")) > limit and document["entries"]:
            document["entries"] = document["entries"][1:]
            document["truncated"] = True
        return document

    def build_report(self, accepted: bool, error: Optional[AgenticError] = None,
                     artifacts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        used_evaluators = [item["evaluator"] for item in self.contract["requirements"]]
        sources = self.tokens["sources"] or ["none"]
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "task": dict(self.identity.get("task", {})),
            "accepted": accepted,
            "result_fit": self.last_aggregate["result_fit"],
            "threshold": self.contract["evaluation"]["threshold"],
            "aggregation": self.contract["evaluation"]["aggregation"],
            "hard_checks": self.last_aggregate["hard_checks"],
            "mandatory_failures": self.last_aggregate["mandatory_failures"],
            "requirements": self.last_results,
            "attempts": self.attempts,
            "selected_attempt": self.selected_attempt,
            "termination_reason": self.termination_reason,
            "error": None if error is None else {"code": error.code, "message": str(error)[:1000]},
            "usage": {"steps": self.steps, "tool_calls": self.tool_calls, "attempts": self.attempt,
                      "tokens": {"prompt": self.tokens["prompt_tokens"], "completion": self.tokens["completion_tokens"],
                                 "total": self.tokens["total_tokens"],
                                 "accounting": sources[0] if len(sources) == 1 else "mixed"},
                      "elapsed_seconds": round(self.clock() - self.started, 3), "budgets": self.budgets},
            "evaluator_versions": self.registry.versions("evaluators", used_evaluators),
            "tool_versions": self.registry.versions("tools", self.profile.tools),
            "guardrail_versions": self.registry.versions("guardrails", self.profile.guardrails),
            "agent": self.profile.public(),
            "digests": {"contract": self.identity.get("contract_digest"),
                        "configuration": self.profile.digest,
                        "inputs": dict(self.identity.get("inputs", {})),
                        "identity": self.identity.get("identity_digest")},
            "artifacts": artifacts or {},
            "execution": dict(self.emulation, adapter=getattr(self.adapter, "id", self.profile.implementation),
                              determinism=self._determinism()),
        }
        return redact(report, self.secrets)

    def _determinism(self) -> str:
        from dagon.agentic.providers import AdapterStarter
        if isinstance(self.adapter, AdapterStarter):
            return "adapter_not_started"
        if getattr(self.adapter, "deterministic", False):
            return "deterministic_fixture"
        return "nondeterministic_live_model"

    def _write_json(self, target: Path, value: Any) -> str:
        atomic_write_text(target, json.dumps(value, indent=2, sort_keys=True) + "\n")
        return sha256_file(target)

    def _publish(self) -> Dict[str, Any]:
        self._check_cancel()
        outputs = self.contract["outputs"]
        artifacts = {"result": {"path": outputs["result"],
                                "sha256": self._write_json(self._output("result"), self.candidate)},
                     "trace": {"path": outputs["trace"],
                               "sha256": self._write_json(self._output("trace"), self._bounded_trace())}}
        report = self.build_report(True, artifacts=artifacts)
        evaluation_sha = self._write_json(self._output("evaluation"), report)
        self._check_cancel()
        commit = {"schema_version": REPORT_SCHEMA_VERSION, "accepted": True,
                  "identity_digest": self.identity.get("identity_digest"),
                  "selected_attempt": self.selected_attempt,
                  "outputs": [{"name": "result", "path": outputs["result"], "sha256": artifacts["result"]["sha256"]},
                              {"name": "trace", "path": outputs["trace"], "sha256": artifacts["trace"]["sha256"]},
                              {"name": "evaluation", "path": outputs["evaluation"], "sha256": evaluation_sha}]}
        self._write_json(self.workdir / COMMIT_MANIFEST, commit)
        self.report, self.commit = report, commit
        return report

    def _diagnostics(self, error: AgenticError) -> Dict[str, Any]:
        report = self.build_report(False, error=error)
        try:
            self._write_json(self._output("trace"), self._bounded_trace())
            self._write_json(self._output("evaluation"), report)
        except Exception:  # diagnostics are best effort and must not mask the failure
            pass
        self.report = report
        return report

    def run(self) -> Dict[str, Any]:
        """Execute the bounded loop; return the accepted report or raise a typed error."""
        self.started = self.clock()
        try:
            self._prepare()
            self._input_guards()
            self._start_adapter()
            self._loop()
            return self._publish()
        except AgenticError as exc:
            if self.termination_reason in ("not_started", "accepted"):
                self.termination_reason = exc.code
            if self.commit is None:
                # Nothing is published without a commit manifest.
                try:
                    result = self._output("result")
                    if result.is_file() or result.is_symlink():
                        result.unlink()
                except Exception:
                    pass
            exc.report = self._diagnostics(exc)  # type: ignore[attr-defined]
            if isinstance(exc, AgenticBudgetExhausted):
                raise AgenticNotAccepted(str(exc), exc.report) from exc  # type: ignore[attr-defined]
            raise
        finally:
            close = getattr(self.adapter, "close", None)
            if callable(close):
                close()


def compute_identity(contract: Dict[str, Any], profile: EffectiveProfile, registry: Registry,
                     reference_hashes: Dict[str, str], workflow: str, task: str) -> Dict[str, Any]:
    """Return the checkpoint identity: contract, effective profile, versions, and input content."""
    from dagon.agentic.models import contract_digest
    versions = {
        "tools": registry.versions("tools", profile.tools),
        "guardrails": registry.versions("guardrails", profile.guardrails),
        "evaluators": registry.versions("evaluators", [item["evaluator"] for item in contract["requirements"]]),
        "adapter": registry.adapters[profile.implementation].version,
    }
    identity = {"task": {"workflow": workflow, "name": task, "agent_profile": profile.name},
                "contract_digest": contract_digest(contract), "profile_digest": profile.digest,
                "versions": versions, "inputs": dict(sorted(reference_hashes.items())),
                "input_schemas": {name: {"media_type": item["media_type"], "binary": item["binary"]}
                                  for name, item in sorted(contract["inputs"].items())}}
    identity["identity_digest"] = sha256_json(identity)
    return identity
