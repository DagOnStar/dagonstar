"""StreamFlow adapter: ``streamflow run <streamflow file> --outdir <dir>``.

StreamFlow executes CWL workflows on hybrid infrastructures described in a
*StreamFlow file*.  Two forms of ``workflow`` are accepted; StreamFlow is
never modified:

* a CWL workflow (``.cwl``): the adapter generates the StreamFlow file, with
  optional ``deployments`` and ``bindings`` engine options copied verbatim
  into it (for example a Slurm or Docker deployment bound to one step);
* an existing StreamFlow file (``.yml``/``.yaml``/``.json``): the adapter
  writes a derived copy whose workflow ``settings`` point at the meta-task
  inputs and whose CWL ``file`` is absolute.  Reading YAML needs PyYAML,
  which StreamFlow itself depends on; ``workflow_name`` selects the workflow
  when the file declares several.

Inputs become the CWL job document (``File``/``Directory`` objects).  The
StreamFlow metadata database is kept inside the task scratch directory.  The
CWL output object that StreamFlow prints is used for ``engine_output`` outputs.

Engine options: ``deployments``, ``bindings``, ``workflow_name``, plus the
common ``executable`` and ``arguments``.  StreamFlow resolves relative paths
against the StreamFlow file's directory; because the derived file lives in
``.dagon``, paths inside ``deployments`` should be absolute.
"""

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from dagon.meta.adapters.base import MetaEngineAdapter
from dagon.meta.adapters.cwl import cwl_job, reported_outputs
from dagon.meta.models import (EngineCapabilities, EngineInvocation, EngineResult, MetaRunContext,
                               MetaValidationError)

_STREAMFLOW_SUFFIXES = (".yml", ".yaml", ".json")


class StreamFlowAdapter(MetaEngineAdapter):
    name = "streamflow"
    executable = "streamflow"
    options = ("deployments", "bindings", "workflow_name")
    version_arguments = ("version",)

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(named_outputs=True)

    def validate(self, workflow: str, engine_options: Mapping[str, Any]) -> None:
        super().validate(workflow, engine_options)
        if not str(workflow).lower().endswith((".cwl",) + _STREAMFLOW_SUFFIXES):
            raise MetaValidationError("the streamflow adapter runs a CWL workflow (.cwl) or a StreamFlow file "
                                      "(.yml, .yaml, .json): %s" % workflow)
        if not isinstance(engine_options.get("deployments", {}), dict):
            raise MetaValidationError("streamflow engine option 'deployments' must be a mapping")
        if not isinstance(engine_options.get("bindings", []), list):
            raise MetaValidationError("streamflow engine option 'bindings' must be a list")
        if str(workflow).lower().endswith(_STREAMFLOW_SUFFIXES) and (
                engine_options.get("deployments") or engine_options.get("bindings")):
            raise MetaValidationError("'deployments' and 'bindings' apply to a generated StreamFlow file; "
                                      "declare them in the StreamFlow file you supplied instead")

    def _document(self, context: MetaRunContext, job: Path) -> Dict[str, Any]:
        source = Path(context.workflow)
        if source.suffix.lower() == ".cwl":
            workflow = {"type": "cwl", "config": {"file": str(source), "settings": str(job)}}
            if context.option("bindings"):
                workflow["bindings"] = context.option("bindings")
            document: Dict[str, Any] = {"version": "v1.0", "workflows": {"dagon": workflow}}
            if context.option("deployments"):
                document["deployments"] = context.option("deployments")
        else:
            text = source.read_text(encoding="utf-8")
            if source.suffix.lower() == ".json":
                document = json.loads(text)
            else:
                try:
                    import yaml
                except ImportError as exc:
                    raise MetaValidationError("reading a YAML StreamFlow file needs PyYAML (installed with "
                                              "StreamFlow); or pass the CWL workflow instead") from exc
                document = yaml.safe_load(text)
            workflows = document.get("workflows") if isinstance(document, dict) else None
            if not isinstance(workflows, dict) or not workflows:
                raise MetaValidationError("the StreamFlow file %s declares no workflows" % source)
            name = context.option("workflow_name") or (next(iter(workflows)) if len(workflows) == 1 else None)
            if name not in workflows:
                raise MetaValidationError("set engine_options['workflow_name'] to one of: %s"
                                          % ", ".join(sorted(workflows)))
            config = workflows[name].setdefault("config", {})
            config["file"] = str((source.parent / config.get("file", "")).resolve())
            config["settings"] = str(job)
        document.setdefault("database", {"type": "default",
                                         "config": {"connection": str(context.metadata_dir / "streamflow.db")}})
        return document

    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        job = context.write_json("cwl-job.json", cwl_job(context))
        # JSON is valid YAML, and StreamFlow reads its file with a YAML loader.
        streamflow_file = context.write_json("streamflow.yml", self._document(context, job))
        outdir = context.run_dir / "streamflow-output"
        argv = [self.resolve_executable(context), "run", str(streamflow_file), "--outdir", str(outdir)]
        argv += context.arguments()
        return EngineInvocation(argv=argv, cwd=context.run_dir,
                                generated_files=[".dagon/cwl-job.json", ".dagon/streamflow.yml",
                                                 ".dagon/streamflow.db"])

    def collect_outputs(self, context: MetaRunContext, result: EngineResult) -> Dict[str, str]:
        return reported_outputs(result.stdout)
