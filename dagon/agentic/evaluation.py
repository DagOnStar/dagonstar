"""Independent evaluation and the result-fit metric.

For valid evaluator results ``F = sum(w_i * s_i) / sum(w_i)`` over every
requirement with positive weight.  A candidate is accepted iff every hard
check passes, ``F >= threshold``, and every mandatory requirement reaches its
own ``minimum_score``.  Any evaluator execution error prevents acceptance and
yields ``result_fit = None``.  Scores are never clamped, renormalized, or
taken from the acting model.
"""
import math
import threading
from typing import Any, Callable, Dict, List, Optional

from dagon.agentic.errors import (AgenticCancelled, AgenticEvaluationError,
                                  AgenticTransientEvaluationError)
from dagon.agentic.registry import Registry
from dagon.agentic.sandbox import call_in_process, call_inline


def validate_evaluator_result(raw: Any, weight: float) -> Dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("status") not in ("pass", "fail"):
        raise AgenticEvaluationError("evaluator must return {'status': 'pass'|'fail', 'score': ...}")
    score = raw.get("score")
    if score is None:
        if weight > 0:
            raise AgenticEvaluationError("evaluator returned a null score for a weighted requirement")
    elif isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) \
            or score < 0 or score > 1:
        raise AgenticEvaluationError("evaluator returned invalid score %r (scores are never clamped)" % (score,))
    return {"status": raw["status"], "score": None if score is None else float(score),
            "observation": raw.get("observation"), "evidence": raw.get("evidence") or []}


def evaluate(contract: Dict[str, Any], candidate: Any, context: Dict[str, Any], registry: Registry,
             remaining: Callable[[], float], cancel_event: Optional[threading.Event] = None) -> List[Dict[str, Any]]:
    """Run every configured requirement (including zero-weight gates)."""
    results = []
    for requirement in contract["requirements"]:
        spec = registry.evaluators[requirement["evaluator"]]
        entry = {"id": requirement["id"], "evaluator": spec.id, "evaluator_version": spec.version,
                 "evaluator_kind": spec.kind, "weight": requirement["weight"], "mandatory": requirement["mandatory"],
                 "minimum_score": requirement["minimum_score"], "hard": requirement["hard"],
                 "expectation": {"expected": requirement["expected"], "options": requirement["options"],
                                 "reference": requirement["reference"]}}
        evaluator_context = dict(context)
        evaluator_context["requirement"] = {key: requirement[key] for key in ("id", "description", "options")}
        if requirement["reference"]:
            evaluator_context["reference_uri"] = requirement["reference"]
            evaluator_context["reference_path"] = context.get("references", {}).get(requirement["reference"])
        args = [candidate, requirement["expected"], requirement["options"], evaluator_context]
        retried = False
        while True:
            timeout = min(spec.timeout_seconds, remaining())
            try:
                if spec.isolation == "process":
                    raw = call_in_process(str(spec.function), args, timeout, 1024 * 1024, cancel_event)
                else:
                    raw = call_inline(spec.function, args, timeout, cancel_event)
                entry.update(validate_evaluator_result(raw, requirement["weight"]))
                entry["error"] = None
            except AgenticCancelled:
                raise
            except AgenticTransientEvaluationError as exc:
                if not retried and remaining() > 0:
                    retried = True
                    continue
                entry.update({"status": "error", "score": None, "observation": None, "evidence": [],
                              "error": "transient evaluator error (retry exhausted): %s" % str(exc)[:500]})
            except Exception as exc:
                entry.update({"status": "error", "score": None, "observation": None, "evidence": [],
                              "error": "%s: %s" % (type(exc).__name__, str(exc)[:500])})
            break
        entry["retried"] = retried
        results.append(entry)
    return results


def aggregate(results: List[Dict[str, Any]], threshold: float) -> Dict[str, Any]:
    errors = [item["id"] for item in results if item["status"] == "error"]
    hard = [{"id": item["id"], "status": item["status"]} for item in results if item["hard"]]
    mandatory_failures = [item["id"] for item in results if item["mandatory"] and (
        item["status"] == "error" or item["score"] is None or item["score"] < item["minimum_score"])]
    if errors:
        fit = None
    else:
        weighted = [item for item in results if item["weight"] > 0]
        fit = math.fsum(item["weight"] * item["score"] for item in weighted) / \
            math.fsum(item["weight"] for item in weighted)
    accepted = (not errors and all(item["status"] == "pass" for item in hard) and fit is not None
                and fit >= threshold and not mandatory_failures)
    return {"result_fit": fit, "accepted": accepted, "threshold": threshold, "hard_checks": hard,
            "mandatory_failures": mandatory_failures, "evaluator_errors": errors}
