"""Lesson 14: an agentic contract, its dagon.ini profile, and a bounded tool-free revision loop."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "agentic"))
import tempfile

from agentic_common import producer, quality_control, read, workflow  # noqa: E402
from dagon.agentic import AgenticConfigurationError, AgenticValidationError  # noqa: E402

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-14-") as scratch:
    wf = workflow("Agentic14", scratch)
    wf.add_task(producer())
    agent = quality_control(tools=[])  # explicit empty list: no tools, even though the profile allows two
    wf.add_task(agent)
    profile = agent.resolve_profile()
    assert profile.name == "quality-local" and profile.tools == (), profile.public()
    wf.run()
    report = read(agent, "outputs/evaluation.json")
    assert report["accepted"] is True
    assert [item["result_fit"] for item in report["attempts"]] == [0.8, 1.0]
    assert report["usage"]["tool_calls"] == 0
    assert report["execution"]["determinism"] == "deterministic_fixture"

    failures = {}
    for name, options in (("missing_profile", {"agent": "missing"}),
                          ("budget_above_profile", {"budgets": {"max_steps": 99}}),
                          ("unknown_tool", {"tools": ["shell"]}),
                          ("no_requirements", {"requirements": []})):
        try:
            task = quality_control(name=name, **options)
            wf.add_task(task)
            task.resolve_profile()
        except (AgenticConfigurationError, AgenticValidationError) as error:
            failures[name] = error.code
    assert failures == {"missing_profile": "invalid_configuration",
                        "budget_above_profile": "invalid_configuration",
                        "unknown_tool": "invalid_contract",
                        "no_requirements": "invalid_contract"}, failures
print("fits per attempt:", [item["result_fit"] for item in report["attempts"]])
print("rejected before execution:", failures)
