"""Lesson 27: opt-in FAIR metadata with declared artifacts, licences, and a credential-free bundle."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
import json
import tempfile
from pathlib import Path

from dagon.fair import AccessPolicy, Agent, Artifact, FairProfile
from dagon.task import DagonTask, TaskType
from examples.tutorial.common.support import workflow

EXPECTED = {"run.json", "ro-crate-metadata.json", "prov.json", "datacite.json", "codemeta.json",
            "checksums.sha256", "fairness-report.json", "report.md", "report.html"}
SECRET = "sk-teaching-sentinel-0000"

with tempfile.TemporaryDirectory(prefix="dagon-tutorial-27-") as scratch:
    plain = workflow("NoFAIR27", scratch)
    plain.add_task(DagonTask(TaskType.BATCH, "A", "echo plain > plain.txt"))
    plain.run()
    assert not Path(scratch, ".dagon", "fair").exists(), "FAIR recording is opt-in"

    wf = workflow("FAIR27", scratch, extra={"llm": {"api_key": SECRET}})
    wf.enable_fair(FairProfile(title="Synthetic station summary", description="Two-step FAIR lesson.",
                               creators=[Agent(name="Course participant")], license="CC-BY-4.0",
                               keywords=["tutorial"], access_policy=AccessPolicy(metadata="public", data="local")))
    first = DagonTask(TaskType.BATCH, "measure", "mkdir -p out; echo 12.5 > out/t.txt").declare_outputs(
        Artifact("out/t.txt", name="Temperature", media_type="text/plain", license="CC-BY-4.0"))
    second = DagonTask(TaskType.BATCH, "summarise", "cat workflow:///measure/out/t.txt > summary.txt")
    second.declare_outputs(Artifact("summary.txt", name="Summary", media_type="text/plain", license="CC-BY-4.0"))
    wf.add_task(first)
    wf.add_task(second)
    wf.run()
    bundles = sorted(Path(scratch, ".dagon", "fair", "FAIR27").glob("*"))
    assert len(bundles) == 1, bundles
    names = {path.name for path in bundles[0].iterdir()}
    assert EXPECTED <= names, EXPECTED - names
    text = "".join(path.read_text(encoding="utf-8") for path in bundles[0].iterdir() if path.is_file())
    assert SECRET not in text, "configuration secrets must never reach FAIR metadata"
    crate = json.loads((bundles[0] / "ro-crate-metadata.json").read_text(encoding="utf-8"))
    licences = {item.get("license") for item in crate["@graph"] if isinstance(item, dict)}
    assert any("CC-BY-4.0" in str(value) for value in licences), licences
print("bundle files:", ", ".join(sorted(EXPECTED)))
print("FAIR stays off by default; the sentinel secret is absent from every exported file")
