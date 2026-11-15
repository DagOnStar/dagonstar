"""Accepted agentic results are reused only when contract, profile, versions, and inputs match."""
import json
import tempfile
from pathlib import Path

from agentic_common import OBSERVATIONS, producer, quality_control, workflow

with tempfile.TemporaryDirectory(prefix="dagon-agentic-") as scratch:
    checkpoint = str(Path(scratch, "checkpoint.json"))

    def run(threshold=1.0):
        wf = workflow("AgenticResume", scratch, checkpoint_file=checkpoint)
        wf.add_task(producer())
        agent = quality_control(evaluation={"threshold": threshold})
        wf.add_task(agent)
        wf.run(checkpoint)
        return agent

    first = run()
    second = run()
    assert second.fair_checkpoint_reused and second.working_dir == first.working_dir
    changed_contract = run(threshold=0.95)
    assert not changed_contract.fair_checkpoint_reused
    # The producer's checkpoint is reused, but its artifact content changed upstream:
    # the agentic identity hashes content, so the agent runs again.
    upstream = Path(first.prevs[0].working_dir, "outputs", "observations.json")
    unique = [row for index, row in enumerate(OBSERVATIONS["observations"]) if index != 2]
    upstream.write_text(json.dumps({"observations": unique}), encoding="utf-8")
    changed_input = run(threshold=0.95)
    assert not changed_input.fair_checkpoint_reused
    recorded = json.loads(Path(checkpoint).read_text(encoding="utf-8"))["AgenticResume.quality_control"]
    assert recorded["accepted"] is True and len(recorded["identity_digest"]) == 64
    print("reused once; contract change and input change both re-ran")
