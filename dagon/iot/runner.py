"""Stable command-line adapter used by CWL IoT tools."""
import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

from dagon.iot.registry import get_provider
from dagon.iot.security import redact


def run(spec: Dict[str, Any], workdir: str, result_path: str) -> Dict[str, Any]:
    provider = get_provider(spec.get("provider", "mock"))
    context = {"spec": spec, "workdir": workdir}
    provider.prepare(spec, context)
    result = provider.poll(provider.invoke(spec, context), context).as_dict()
    destination = Path(workdir, result_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(redact(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, relative in spec.get("outputs", {}).items():
        output = Path(workdir, relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = result["payload"]
        if isinstance(payload, dict) and name in payload:
            payload = payload[name]
        output.write_text(json.dumps(redact(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(prog="dagon-iot-runner")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("run")
    command.add_argument("--spec", required=True)
    command.add_argument("--workdir", default=".")
    command.add_argument("--result", default="outputs/result.json")
    args = parser.parse_args(argv)
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        run(spec, args.workdir, args.result)
        return 0
    except Exception as exc:
        Path("iot-error.json").write_text(json.dumps(redact({"error": str(exc)})) + "\n", encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
