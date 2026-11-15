"""Command-line runner shared by CWL exports and local use.

Usage::

    dagon-agent-runner run --spec agent-task.json --config dagon.ini --workdir . \\
        --bind workflow:///prepare/outputs/observations.json=/path/to/observations.json

``--spec`` is the versioned contract (``AgenticTask.portable_spec()``).  The
named profile is resolved from ``--config`` at run time; every ``workflow://``
reference in the contract must be bound to a readable file.  Exit status: 0
accepted, 2 not accepted or blocked, 1 invalid contract or configuration.
The same :class:`~dagon.agentic.engine.AgentEngine` as in-workflow execution
is used.  ``python -m dagon.agentic.runner`` is equivalent.
"""
import argparse
import json
import os
import sys
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from dagon.agentic.config import resolve_profile
from dagon.agentic.engine import AgentEngine, compute_identity
from dagon.agentic.errors import AgenticConfigurationError, AgenticError, AgenticValidationError
from dagon.agentic.models import contract_references, normalize_contract
from dagon.agentic.providers import prepare_adapter
from dagon.agentic.registry import default_registry
from dagon.agentic.security import atomic_write_text, redact, sha256_file


def _bindings(values: List[str]) -> Dict[str, str]:
    result = {}
    for value in values:
        uri, separator, path = value.partition("=")
        if not separator or not uri.startswith("workflow://") or not path:
            raise AgenticValidationError("--bind expects workflow://<...>=<path>, got %r" % value)
        result[uri] = path
    return result


def run(spec: Dict[str, Any], config_path: str, workdir: str, bindings: Dict[str, str],
        portable_emulation: bool = False, workflow: str = "cwl", task: str = "agentic") -> Dict[str, Any]:
    registry = default_registry()
    declaration = dict(spec)
    declaration.pop("schema_version", None)
    contract = normalize_contract(registry=registry, **declaration)
    if not Path(config_path).is_file():
        raise AgenticConfigurationError("configuration file %s does not exist" % config_path)
    cfg = ConfigParser(interpolation=None)
    cfg.read(config_path, encoding="utf-8")
    profile = resolve_profile(cfg, contract["agent"], contract["tools"], contract["guardrails"],
                              contract["budgets"], registry)
    references, hashes = {}, {}
    for reference in contract_references(contract):
        if reference not in bindings:
            raise AgenticValidationError("no --bind given for %s" % reference)
        path = Path(bindings[reference])
        if not path.is_file():
            raise AgenticValidationError("bound input for %s is not a readable file" % reference)
        references[reference] = str(path.resolve())
        hashes[reference] = sha256_file(path)
    inputs = {name: dict(item, path=references[item["uri"]], sha256=hashes[item["uri"]],
                         size=os.path.getsize(references[item["uri"]]))
              for name, item in contract["inputs"].items()}
    identity = compute_identity(contract, profile, registry, hashes, workflow, task)
    adapter, secrets, emulation = prepare_adapter(profile, cfg, registry, portable_emulation)
    engine = AgentEngine(contract, profile, adapter, inputs, references, workdir, registry, identity,
                         secrets=secrets, emulation=emulation)
    return engine.run()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="dagon-agent-runner",
                                     description="Run one DAGonStar agentic task contract.")
    sub = parser.add_subparsers(dest="command")
    command = sub.add_parser("run")
    command.add_argument("--spec", required=True)
    command.add_argument("--config", required=True, help="dagon.ini that defines the named agent profile")
    command.add_argument("--workdir", default=".")
    command.add_argument("--bind", action="append", default=[], help="workflow://...=<file>")
    command.add_argument("--workflow", default="cwl")
    command.add_argument("--task", default="agentic")
    command.add_argument("--portable-emulation", action="store_true")
    args = parser.parse_args(argv)
    if args.command != "run":
        parser.print_help()
        return 1
    workdir = Path(args.workdir)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        report = run(spec, args.config, str(workdir), _bindings(args.bind), args.portable_emulation,
                     args.workflow, args.task)
        print(json.dumps({"accepted": report["accepted"], "result_fit": report["result_fit"],
                          "termination_reason": report["termination_reason"]}, sort_keys=True))
        return 0
    except (AgenticValidationError, AgenticConfigurationError) as exc:
        code, status = 1, {"error": exc.code, "message": str(exc)}
    except AgenticError as exc:
        code, status = 2, {"error": exc.code, "message": str(exc)}
    except (OSError, ValueError) as exc:
        code, status = 1, {"error": "invalid_input", "message": str(exc)}
    atomic_write_text(workdir / ".dagon" / "agentic" / "runner-error.json",
                      json.dumps(redact(status), indent=2, sort_keys=True) + "\n")
    print(json.dumps(redact(status), sort_keys=True), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
