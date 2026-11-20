"""CWL-runner adapter (``cwltool`` by default) and shared CWL job helpers.

Inputs become a CWL job document: file inputs are ``{"class": "File"}``
objects, directory inputs ``{"class": "Directory"}`` objects, other values
pass through.  The runner prints the CWL output object on standard output;
outputs declared with ``engine_output`` are taken from it by name.

Engine options: ``runner`` (executable, default ``cwltool``; any runner that
accepts ``--outdir`` and prints the output object, such as
``toil-cwl-runner``), plus the common ``executable`` (alias of ``runner``)
and ``arguments`` (for example ``["--no-container"]``).
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlsplit

from dagon.meta.adapters.base import MetaEngineAdapter
from dagon.meta.models import EngineCapabilities, EngineInvocation, EngineResult, MetaRunContext


def cwl_job(context: MetaRunContext) -> Dict[str, Any]:
    """Return the CWL job object for the meta-task inputs."""
    job: Dict[str, Any] = {}
    for item in context.inputs:
        if item.kind == "file":
            job[item.name] = {"class": "File", "path": item.value}
        elif item.kind == "directory":
            job[item.name] = {"class": "Directory", "path": item.value}
        else:
            job[item.name] = item.value
    return job


def _location(value: Any) -> Optional[str]:
    if not isinstance(value, dict) or value.get("class") not in ("File", "Directory"):
        return None
    if value.get("path"):
        return str(value["path"])
    location = str(value.get("location", ""))
    if location.startswith("file://"):
        return unquote(urlsplit(location).path)
    return None


def reported_outputs(stdout: str) -> Dict[str, str]:
    """Parse the last JSON object printed by a CWL runner into name -> local path."""
    text = stdout.strip()
    start = text.rfind("\n{")
    candidates = [text[start + 1:]] if start >= 0 else []
    candidates.append(text[text.find("{"):] if "{" in text else "")
    for candidate in candidates:
        try:
            document = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(document, dict):
            found = {}
            for name, value in document.items():
                location = _location(value)
                if location:
                    found[str(name)] = location
            return found
    return {}


class CWLAdapter(MetaEngineAdapter):
    name = "cwl"
    executable = "cwltool"
    options = ("runner",)

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(named_outputs=True)

    def resolve_executable(self, context: MetaRunContext) -> str:
        if "runner" in context.engine_options and "executable" not in context.engine_options:
            context.engine_options["executable"] = context.engine_options["runner"]
        return super().resolve_executable(context)

    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        job = context.write_json("cwl-job.json", cwl_job(context))
        outdir = context.run_dir / "cwl-output"
        argv = [self.resolve_executable(context)] + context.arguments() + ["--outdir", str(outdir),
                                                                           context.workflow, str(job)]
        return EngineInvocation(argv=argv, cwd=context.run_dir, generated_files=[".dagon/cwl-job.json"])

    def collect_outputs(self, context: MetaRunContext, result: EngineResult) -> Dict[str, str]:
        return reported_outputs(result.stdout)

    def unavailable_reason(self, context: MetaRunContext) -> Optional[str]:
        if not Path(context.workflow).is_file():
            return "the CWL workflow %s does not exist" % context.workflow
        return super().unavailable_reason(context)
