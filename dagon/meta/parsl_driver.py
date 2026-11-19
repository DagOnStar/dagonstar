"""Driver that runs a Parsl program for a meta-task: ``python parsl_driver.py --job FILE``.

It runs in the interpreter that has Parsl installed, never in the DAGonStar
process, imports nothing from DAGonStar, and uses only public Parsl APIs (``parsl.load``, ``parsl.dfk``,
``parsl.clear``), so Parsl is not modified.
"""

import argparse
import concurrent.futures
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def _load_module(path: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot import Parsl program %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(path).resolve().parent))
    spec.loader.exec_module(module)
    return module


def _config(job: Dict[str, Any]) -> Any:
    from parsl.config import Config
    choice = job.get("config", "threads")
    if choice == "threads":
        from parsl.executors.threads import ThreadPoolExecutor
        return Config(executors=[ThreadPoolExecutor(label="dagon_threads", max_threads=int(job.get("max_threads", 4)))],
                      run_dir=job["run_dir"])
    if choice == "htex_local":
        from parsl.executors import HighThroughputExecutor
        from parsl.providers import LocalProvider
        return Config(executors=[HighThroughputExecutor(label="dagon_htex", provider=LocalProvider(init_blocks=1,
                                                                                                    max_blocks=1))],
                      run_dir=job["run_dir"])
    location, _, attribute = choice.rpartition(":")
    config = getattr(_load_module(str(Path(location).resolve()), "dagon_meta_parsl_config"), attribute)
    if getattr(config, "run_dir", None) in (None, "runinfo"):
        config.run_dir = job["run_dir"]
    return config


def _resolve(value: Any, counter: Dict[str, int]) -> Any:
    """Wait for every future in *value* and return a JSON-friendly result."""
    if isinstance(value, concurrent.futures.Future):
        counter["apps"] += 1
        return _resolve(value.result(), counter)
    if isinstance(value, dict):
        return {str(key): _resolve(item, counter) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_resolve(item, counter) for item in value]
    if hasattr(value, "filepath"):  # parsl.data_provider.files.File
        return str(value.filepath)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    arguments, extra = parser.parse_known_args()
    job = json.loads(Path(arguments.job).read_text(encoding="utf-8"))
    parameters = json.loads(Path(job["parameters_file"]).read_text(encoding="utf-8"))
    sys.argv = [job["workflow"]] + extra
    import parsl
    module = _load_module(job["workflow"], "dagon_meta_parsl_program")
    entrypoint = getattr(module, job["entrypoint"], None)
    if not callable(entrypoint):
        raise SystemExit("Parsl program %s defines no callable %r" % (job["workflow"], job["entrypoint"]))
    parsl.load(_config(job))
    counter = {"apps": 0}
    try:
        result = _resolve(entrypoint(**parameters), counter)
    finally:
        try:
            parsl.dfk().cleanup()
        finally:
            parsl.clear()
    document = {"result": result, "apps": counter["apps"], "parsl_version": getattr(parsl, "__version__", None)}
    target = Path(job["result_path"])
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
