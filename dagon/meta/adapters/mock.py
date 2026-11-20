"""Deterministic, engine-free adapter used by portable emulation and tests.

The mock adapter never starts a process.  It writes one JSON placeholder per
declared output (an empty directory with a placeholder for directory
outputs) that records the engine that *would* have run and the identity of
every input it received.  Results are marked ``emulated`` everywhere.
"""

import json
from typing import Any, Dict

from dagon.meta.adapters.base import MetaEngineAdapter
from dagon.meta.models import EngineCapabilities, EngineInvocation, EngineResult, MetaRunContext


class MockAdapter(MetaEngineAdapter):
    name = "mock"
    executable = None
    options = ("emulated_engine",)

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(remote_workflows=True, named_outputs=True)

    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        context.write_json("mock-parameters.json", context.parameters)
        return EngineInvocation(argv=[], cwd=context.run_dir, generated_files=[".dagon/mock-parameters.json"])

    def execute(self, context: MetaRunContext, invocation: EngineInvocation) -> EngineResult:
        document: Dict[str, Any] = {
            "portable_emulation": True,
            "engine": context.option("emulated_engine", context.engine),
            "inputs": {item.name: ({"sha256": item.sha256} if item.sha256 else {"value": item.value})
                       for item in context.inputs},
        }
        reported: Dict[str, str] = {}
        for name, output in sorted(context.outputs.items()):
            source = context.run_dir / (output.get("source") or output["path"])
            payload = json.dumps(dict(document, output=name), indent=2, sort_keys=True) + "\n"
            if output["type"] == "directory":
                source.mkdir(parents=True, exist_ok=True)
                (source / "placeholder.json").write_text(payload, encoding="utf-8")
            else:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(payload, encoding="utf-8")
            reported[name] = str(source)
        self._write_logs(context, json.dumps(document, sort_keys=True) + "\n", "")
        return EngineResult(0, reported_outputs=reported, metadata={"emulated": True})

    def collect_outputs(self, context: MetaRunContext, result: EngineResult) -> Dict[str, str]:
        return dict(result.reported_outputs)

    def version(self, context: MetaRunContext) -> str:
        return "mock"
