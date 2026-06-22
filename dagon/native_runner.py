"""Runtime for :class:`dagon.native.NativeTask` specifications."""

import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict


def _inside(root: Path, candidate: str) -> Path:
    value = (root / candidate).resolve()
    if root.resolve() not in value.parents and value != root.resolve():
        raise ValueError("Native task path escapes its scratch directory: %s" % candidate)
    return value


def run(spec_path: str) -> Dict[str, Any]:
    """Run the importable function described by *spec_path* and write metadata."""
    spec_file = Path(spec_path).resolve()
    root = spec_file.parent.parent
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    module_path = spec.get("module_search_path")
    if module_path and module_path not in sys.path:
        sys.path.insert(0, module_path)
    function = getattr(importlib.import_module(spec["module"]), spec["function"])
    if not callable(function):
        raise ValueError("Native function is not callable")

    kwargs: Dict[str, Any] = {}
    for name, binding in spec["inputs"].items():
        kwargs[name] = str(_inside(root, binding["path"])) if binding["kind"] == "file" else binding["value"]
    for name, binding in spec["outputs"].items():
        output = _inside(root, binding["path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        kwargs[name] = str(output)

    inspect.signature(function).bind(**kwargs)
    result = function(**kwargs)
    for binding in spec["outputs"].values():
        output = _inside(root, binding["path"])
        if not output.is_file():
            raise FileNotFoundError("Native function did not produce declared output: %s" % output)
    try:
        encoded = json.dumps(result, indent=2, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("Native function result must be JSON-serializable") from exc
    result_path = _inside(root, spec["result_path"])
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(encoded + "\n", encoding="utf-8")
    return result


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m dagon.native_runner .dagon/native_spec.json")
    run(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
