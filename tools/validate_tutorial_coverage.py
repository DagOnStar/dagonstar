#!/usr/bin/env python3
"""Validate tutorial feature coverage: every TaskType and inventoried feature has lessons and evidence.

Usage (from the repository root)::

    python tools/validate_tutorial_coverage.py

The TaskType inventory is derived from :class:`dagon.task.TaskType` at run time,
so a newly registered type fails validation until it is mapped.  Dynamic type
checks alone do not establish complete feature coverage: ``REQUIRED_FEATURES``
below is the curated inventory of supported, public features, reviewed by hand
when the implementation changes.  Every required feature must appear in
``docs/tutorial/coverage.json`` with lessons, runnable examples, resolvable test
targets, existing source paths, and stated limitations, unless it is listed as
an exclusion with implementation evidence.
"""
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TUTORIAL = ROOT / "docs" / "tutorial"
MANIFEST = TUTORIAL / "coverage.json"
NOTEBOOK = TUTORIAL / "DAGonStar_tutorial.ipynb"
LESSON_COUNT = 33
EVIDENCE_LEVELS = ("local-executed", "mock-contract", "portable-emulation", "live-optional", "planned")
FIELDS = ("feature_id", "category", "task_types", "source_paths", "lessons", "example_paths",
          "test_targets", "evidence_level", "limitations")

# Curated inventory of supported, public features (in addition to one entry per TaskType).
REQUIRED_FEATURES = (
    "graph.explicit-dependencies", "graph.workflow-references", "graph.cycle-validation",
    "execution.scratch-and-launchers", "staging.copy-link", "execution.checkpoint-resume",
    "execution.async-lifecycle", "execution.dry-run", "execution.portable-emulation", "config.dagon-ini",
    "workflow.json-roundtrip",
    "agentic.profiles", "agentic.tools", "agentic.guardrails", "agentic.evaluation", "agentic.publication",
    "agentic.checkpoint-identity", "agentic.mixed-dataflow", "agentic.openai-compatible-adapter",
    "agentic.cwl-runner",
    "faas.http-provider", "faas.cloud-adapters", "iot.actuation-safety", "iot.compute-placement",
    "remote.ssh-ports-and-quoting", "slurm.beeond", "storage.adhoc-filesystems", "slurm.scheduler-prestaging",
    "movers.scp", "movers.gridftp-globus", "movers.skycds", "movers.dynostore", "movers.stager-modes",
    "fair.metadata-export", "fair.agentic-artifacts", "meta.dag-tps", "meta.external-engines",
    "meta.dagon-service-api", "cwl.export",
    "operations.runtime-environment", "operations.packaging-extras", "operations.continuous-integration",
)


def task_type_values() -> List[str]:
    from dagon.task import TaskType
    return sorted(item.value for item in TaskType)


def lesson_scripts() -> Dict[int, str]:
    scripts = {}
    for path in sorted((ROOT / "examples" / "tutorial").glob("lesson_*.py")):
        match = re.match(r"lesson_([0-9]{2})_", path.name)
        if match:
            scripts[int(match.group(1))] = path.relative_to(ROOT).as_posix()
    return scripts


def _test_target_problem(target: str) -> Optional[str]:
    parts = target.split(".")
    if len(parts) < 2 or parts[0] != "tests":
        return "test target must start with 'tests.': %s" % target
    path = ROOT / "tests" / (parts[1] + ".py")
    if not path.is_file():
        return "test module does not exist: %s" % target
    text = path.read_text(encoding="utf-8")
    if len(parts) >= 3 and not re.search(r"^class %s\b" % re.escape(parts[2]), text, re.M):
        return "test class does not exist: %s" % target
    if len(parts) >= 4 and not re.search(r"^\s+def %s\(" % re.escape(parts[3]), text, re.M):
        return "test method does not exist: %s" % target
    if len(parts) > 4:
        return "test target is too deep: %s" % target
    return None


def _notebook_problems(notebook: Dict[str, Any], scripts: Dict[int, str]) -> List[str]:
    errors = []
    cells = notebook.get("cells", [])
    starts = []
    for index, cell in enumerate(cells):
        text = "".join(cell.get("source", []))
        match = re.match(r"## Lesson ([0-9]{2}) ", text) if cell.get("cell_type") == "markdown" else None
        if match:
            starts.append((int(match.group(1)), index))
    numbers = [number for number, _ in starts]
    if numbers != list(range(LESSON_COUNT)):
        missing = sorted(set(range(LESSON_COUNT)) - set(numbers))
        errors.append("notebook lesson sections are not Lessons 00-%02d in order (missing: %s)"
                      % (LESSON_COUNT - 1, ", ".join("%02d" % n for n in missing) or "none"))
    for position, (number, start) in enumerate(starts):
        stop = starts[position + 1][1] if position + 1 < len(starts) else len(cells)
        code = "\n".join("".join(cell.get("source", [])) for cell in cells[start + 1:stop]
                         if cell.get("cell_type") == "code")
        script = scripts.get(number)
        if not code.strip():
            errors.append("notebook Lesson %02d has no code cell" % number)
        elif script and script not in code:
            errors.append("notebook Lesson %02d does not run %s" % (number, script))
    return errors


def validate(manifest: Optional[Dict[str, Any]] = None, notebook: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return a list of coverage problems; an empty list means the coverage is complete."""
    if manifest is None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if notebook is None:
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    errors: List[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("coverage.json schema_version must be 1")
    scripts = lesson_scripts()
    for number in range(LESSON_COUNT):
        if number not in scripts:
            errors.append("no example script for Lesson %02d (examples/tutorial/lesson_%02d_*.py)" % (number, number))
    features = manifest.get("features", [])
    exclusions = manifest.get("exclusions", [])
    seen = set()
    supported_types = set()
    supported_ids = set()
    lessons_used = set()
    for entry in features:
        fid = entry.get("feature_id", "<missing id>")
        for field in FIELDS:
            if field not in entry:
                errors.append("%s is missing field %s" % (fid, field))
        if fid in seen:
            errors.append("duplicate feature_id: %s" % fid)
        seen.add(fid)
        level = entry.get("evidence_level")
        if level not in EVIDENCE_LEVELS:
            errors.append("%s has unknown evidence_level %r" % (fid, level))
        if not str(entry.get("limitations", "")).strip():
            errors.append("%s states no limitations" % fid)
        for path in entry.get("source_paths", []):
            if not (ROOT / path).exists():
                errors.append("%s source path does not exist: %s" % (fid, path))
        for number in entry.get("lessons", []):
            if not isinstance(number, int) or not 0 <= number < LESSON_COUNT:
                errors.append("%s names an unknown lesson: %r" % (fid, number))
            else:
                lessons_used.add(number)
        for path in entry.get("example_paths", []):
            if not (ROOT / path).is_file():
                errors.append("%s example does not exist: %s" % (fid, path))
        for target in entry.get("test_targets", []):
            problem = _test_target_problem(target)
            if problem:
                errors.append("%s: %s" % (fid, problem))
        if level == "planned":
            continue  # planned features never count toward supported coverage
        if not entry.get("lessons") or not entry.get("example_paths") or not entry.get("test_targets"):
            errors.append("%s needs at least one lesson, one example, and one test target" % fid)
            continue
        supported_ids.add(fid)
        if entry.get("category") == "task-type":
            supported_types.update(entry.get("task_types", []))
    known_types = set(task_type_values())
    for value in sorted(known_types - supported_types):
        errors.append("registered TaskType %r has no supported task-type coverage entry" % value)
    for entry in features:
        for value in entry.get("task_types", []):
            if value not in known_types:
                errors.append("%s names an unregistered task type %r" % (entry.get("feature_id"), value))
    excluded = set()
    for item in exclusions:
        fid = item.get("feature_id", "<missing id>")
        excluded.add(fid)
        if not str(item.get("reason", "")).strip():
            errors.append("exclusion %s gives no reason" % fid)
        evidence = item.get("evidence", [])
        if not evidence:
            errors.append("exclusion %s gives no implementation evidence" % fid)
        for path in list(evidence) + list(item.get("source_paths", [])):
            if not (ROOT / path).exists():
                errors.append("exclusion %s cites a missing path: %s" % (fid, path))
        if fid in seen:
            errors.append("%s is both covered and excluded" % fid)
    for fid in REQUIRED_FEATURES:
        if fid not in supported_ids and fid not in excluded:
            errors.append("required feature has no supported coverage: %s" % fid)
    for number in sorted(set(range(LESSON_COUNT)) - lessons_used):
        errors.append("Lesson %02d is not mapped to any feature" % number)
    errors.extend(_notebook_problems(notebook, scripts))
    return errors


def summary(manifest: Optional[Dict[str, Any]] = None) -> str:
    if manifest is None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    features = manifest["features"]
    counted = [entry for entry in features if entry["evidence_level"] != "planned"]
    levels: Dict[str, int] = {}
    for entry in counted:
        levels[entry["evidence_level"]] = levels.get(entry["evidence_level"], 0) + 1
    return ("%d task types, %d required features, %d coverage entries (%s), %d documented exclusions, "
            "%d lessons; unmatched features: 0"
            % (len(task_type_values()), len(REQUIRED_FEATURES), len(counted),
               ", ".join("%s %d" % item for item in sorted(levels.items())), len(manifest.get("exclusions", [])),
               LESSON_COUNT))


if __name__ == "__main__":
    failures = validate()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(1)
    print("Coverage validated: " + summary())
