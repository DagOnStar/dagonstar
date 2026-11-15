"""Lesson 12: invoke an already-deployed function through the mock FaaS provider."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json
import tempfile
from pathlib import Path
from unittest import mock

from dagon.faas_providers import FaaSError, get_provider
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow

SDK_MODULES = ("boto3", "botocore", "azure", "google")
assert not any(name in sys.modules for name in SDK_MODULES), "base import loaded a cloud SDK"

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-12-") as scratch:
    wf = workflow("FaaS12", scratch)
    prepare = DagonTask(TaskType.BATCH, "prepare",
                        "mkdir -p outputs; printf '{\"value\": 4}' > outputs/input.json")
    invoke = DagonTask(TaskType.FAAS, "invoke", provider="mock", function="double-value",
                       inputs={"request": {"document": "workflow:///prepare/outputs/input.json"}},
                       outputs={"result": "result.json"},
                       provider_options={"mock": {"response": {
                           "status": "succeeded", "outputs": {"result": {"value": 8}}}}})
    wf.add_task(prepare)
    wf.add_task(invoke)
    wf.make_dependencies()
    assert invoke.prevs == [prepare], "the nested workflow:// reference must create one edge"
    wf.run()
    result = json.loads(Path(invoke.working_dir, "outputs", "result.json").read_text(encoding="utf-8"))
    assert result == {"value": 8}, result

    # Controlled experiment: a checkpointed invocation is not repeated.
    provider = get_provider("mock")
    with mock.patch("dagon.faas.get_provider", return_value=provider) as factory:
        invoke.execute()
    assert factory.call_count == 0, "a completed FaaS checkpoint must not reinvoke the provider"

try:
    get_provider("does-not-exist")
except ValueError as error:
    print("unknown provider rejected:", error)
else:
    raise AssertionError("an unknown provider must be rejected")
assert issubclass(FaaSError, RuntimeError)
assert not any(name in sys.modules for name in SDK_MODULES), "the mock path loaded a cloud SDK"
print("FaaS result:", result, "| cloud SDKs imported: none")
