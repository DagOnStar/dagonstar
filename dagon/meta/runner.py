"""Engine-neutral execution of one meta-task specification.

:func:`run` is shared by :class:`dagon.meta.task.MetaTask` and by the
``dagon-meta-runner`` command used in CWL exports, so both follow one
lifecycle:

1. resolve every input to a staged local path or a JSON value;
2. ask the adapter for the engine command (it writes the engine-native
   parameter files below ``.dagon``);
3. run the unmodified engine in ``run/`` (no shell, bounded by the timeout);
4. collect each declared output from the engine-reported location or its
   ``source`` path, refuse anything outside the scratch directory, and copy it
   to ``outputs/<path>``;
5. write ``.dagon/meta_result.json`` (credential-free, with SHA-256 digests).
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from dagon.meta.adapters.base import get_adapter
from dagon.meta.models import (SCHEMA_VERSION, MetaInput, MetaOutputError, MetaRunContext, MetaStagingError,
                               MetaValidationError, inside, sha256_path)

REFERENCE_PREFIX = "workflow://"


def input_kind(descriptor: Mapping[str, Any]) -> str:
    return str(descriptor.get("type", "value"))


def resolve_inputs(spec: Mapping[str, Any], workdir: Path, bindings: Mapping[str, str]) -> List[MetaInput]:
    """Turn the specification inputs into adapter inputs.

    *bindings* maps each ``workflow://`` reference (and local input path) to
    the staged location, relative to *workdir* or absolute.
    """
    resolved = []
    for name, descriptor in sorted(spec["inputs"].items()):
        kind = input_kind(descriptor)
        if kind == "value":
            resolved.append(MetaInput(name, "value", descriptor.get("value")))
            continue
        location = descriptor["path"]
        staged = bindings.get(location)
        if staged is None:
            if location.startswith(REFERENCE_PREFIX):
                raise MetaStagingError("meta-task input %s (%s) has no staged binding" % (name, location))
            staged = location
        path = Path(staged) if Path(staged).is_absolute() else workdir / staged
        if kind == "auto":
            kind = "directory" if path.is_dir() else "file"
        exists = path.is_dir() if kind == "directory" else path.is_file()
        if not exists:
            raise MetaStagingError("meta-task %s input %s does not exist: %s" % (kind, name, path))
        # ``reference`` keeps the logical location (workflow:// or local path) for identity checks.
        resolved.append(MetaInput(name, kind, str(path.resolve()), descriptor["path"], sha256_path(path)))
    return resolved


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    if temporary.is_dir():
        shutil.rmtree(str(temporary))
    if source.is_dir():
        shutil.copytree(str(source), str(temporary), symlinks=False)
        if destination.is_dir():
            shutil.rmtree(str(destination))
    else:
        shutil.copy2(str(source), str(temporary))
    os.replace(str(temporary), str(destination))


def collect_outputs(context: MetaRunContext, reported: Mapping[str, str]) -> List[Dict[str, Any]]:
    """Copy declared outputs into ``outputs/`` and return their evidence records."""
    evidence = []
    outputs_dir = context.workdir / "outputs"
    for name, declared in sorted(context.outputs.items()):
        if declared.get("engine_output"):
            location = reported.get(declared["engine_output"])
            source = Path(location) if location else None
        else:
            source = context.run_dir / declared["source"]
        if source is None or not (source.is_dir() if declared["type"] == "directory" else source.is_file()):
            if declared.get("required", True):
                raise MetaOutputError("the engine did not produce the declared %s output %s (%s)"
                                      % (declared["type"], name, declared.get("engine_output") or declared["source"]))
            continue
        if not inside(context.workdir, source):
            raise MetaOutputError("meta-task output %s resolves outside the task scratch directory: %s"
                                  % (name, source))
        destination = outputs_dir / declared["path"]
        _copy(source, destination)
        evidence.append({"name": name, "type": declared["type"],
                         "path": destination.relative_to(context.workdir).as_posix(),
                         "sha256": sha256_path(destination)})
    return evidence


def workflow_identity(workflow: str) -> Dict[str, Any]:
    """Return what can be substantiated locally about the external workflow definition."""
    location = Path(workflow)
    if location.exists():
        return {"location": workflow, "kind": "directory" if location.is_dir() else "file",
                "sha256": sha256_path(location)}
    return {"location": workflow, "kind": "remote", "sha256": None}


def run(spec: Mapping[str, Any], workdir: Any, bindings: Optional[Mapping[str, str]] = None,
        emulate: bool = False, environment: Optional[Mapping[str, str]] = None,
        python: Optional[str] = None) -> Dict[str, Any]:
    """Run one meta-task specification in *workdir* and return the result document."""
    if spec.get("schema_version") != SCHEMA_VERSION:
        raise MetaValidationError("unsupported meta-task schema version: %r" % spec.get("schema_version"))
    workdir = Path(workdir).resolve()
    metadata_dir, run_dir = workdir / ".dagon", workdir / "run"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    adapter = get_adapter("mock" if emulate else spec["engine"])
    engine_options = dict(spec.get("engine_options", {}))
    if emulate:
        engine_options = {"emulated_engine": spec["engine"]}
    adapter.validate(spec["workflow"], engine_options)
    context = MetaRunContext(
        engine=spec["engine"], workflow=spec["workflow"], workdir=workdir, run_dir=run_dir,
        metadata_dir=metadata_dir, inputs=resolve_inputs(spec, workdir, bindings or {}),
        outputs={name: dict(value) for name, value in spec.get("outputs", {}).items()},
        engine_options=engine_options, environment=dict(spec.get("environment", {}), **dict(environment or {})),
        timeout=spec.get("timeout"), python=python or sys.executable, emulated=emulate)
    identity = workflow_identity(spec["workflow"])
    if not emulate:
        if identity["kind"] == "remote" and not adapter.capabilities().remote_workflows:
            raise MetaStagingError("the %s workflow does not exist: %s" % (spec["engine"], spec["workflow"]))
        reason = adapter.unavailable_reason(context)
        if reason:
            from dagon.meta.models import MetaEngineUnavailableError
            raise MetaEngineUnavailableError(reason)
    started = time.time()
    invocation = adapter.prepare(context)
    context.write_json("meta_invocation.json", {
        "engine": spec["engine"], "adapter": adapter.name, "argv": [str(item) for item in invocation.argv],
        "cwd": str(invocation.cwd), "environment_names": sorted(set(context.environment) | set(invocation.environment)),
        "generated_files": invocation.generated_files, "emulated": emulate})
    result = adapter.execute(context, invocation)
    outputs = collect_outputs(context, adapter.collect_outputs(context, result))
    document = {
        "schema_version": SCHEMA_VERSION, "engine": spec["engine"], "adapter": adapter.name,
        "engine_version": adapter.version(context), "emulated": emulate, "workflow": identity,
        "returncode": result.returncode, "duration_seconds": round(time.time() - started, 6),
        "inputs": [{"name": item.name, "type": item.kind, "location": item.reference, "sha256": item.sha256}
                   for item in context.inputs if item.kind != "value"],
        "outputs": outputs, "engine_metadata": result.metadata,
    }
    context.write_json("meta_result.json", document)
    return document


def main(argv: Optional[List[str]] = None) -> int:
    """``dagon-meta-runner run --spec FILE [--workdir DIR] [--bind REF=PATH ...]``."""
    parser = argparse.ArgumentParser(prog="dagon-meta-runner", description="Run a DAGonStar meta-task specification.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("run", help="run the external workflow described by a specification")
    command.add_argument("--spec", required=True, help="meta-task specification (JSON)")
    command.add_argument("--workdir", default=".", help="task scratch directory (default: current directory)")
    command.add_argument("--bind", action="append", default=[], metavar="REFERENCE=PATH",
                         help="local path of a workflow:// input reference")
    command.add_argument("--portable-emulation", action="store_true", help="use the deterministic mock engine")
    arguments = parser.parse_args(argv)
    spec = json.loads(Path(arguments.spec).read_text(encoding="utf-8"))
    bindings = {}
    for item in arguments.bind:
        reference, separator, location = item.partition("=")
        if not separator:
            parser.error("--bind expects REFERENCE=PATH")
        bindings[reference] = str(Path(location).resolve())
    workdir = Path(arguments.workdir)
    try:
        document = run(spec, workdir, bindings, emulate=arguments.portable_emulation)
    except (MetaValidationError, MetaStagingError, MetaOutputError) as exc:
        print("dagon-meta-runner: %s" % exc, file=sys.stderr)
        return 2
    except Exception as exc:
        print("dagon-meta-runner: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps({"outputs": document["outputs"], "engine": document["engine"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
