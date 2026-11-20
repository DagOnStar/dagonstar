"""Nextflow adapter: ``nextflow run <pipeline> -params-file <inputs>``.

Inputs become Nextflow ``params`` through a JSON ``-params-file``: a file
input ``reads`` is visible to the pipeline as ``params.reads`` holding an
absolute path.  The pipeline runs with the engine working directory as its
launch directory, so ``publishDir`` paths relative to ``launchDir`` land where
meta-task outputs are collected from.  ``workflow`` is a local ``main.nf``, a
local project directory, or (``remote_workflows``) a pipeline name such as
``nextflow-io/hello`` that Nextflow resolves itself; pin it with ``revision``.

Engine options: ``profile`` (str), ``config`` (list of config files),
``revision`` (str), ``resume`` (bool), ``trace`` (bool, default True),
``work_dir`` (relative to the engine working directory, default ``work``),
plus the common ``executable`` and ``arguments``.
"""

import csv
from pathlib import Path
from typing import Any, List, Mapping

from dagon.meta.adapters.base import MetaEngineAdapter
from dagon.meta.models import (EngineCapabilities, EngineInvocation, EngineResult, MetaRunContext,
                               MetaValidationError, safe_relative)


class NextflowAdapter(MetaEngineAdapter):
    name = "nextflow"
    executable = "nextflow"
    options = ("profile", "config", "revision", "resume", "trace", "work_dir")
    version_arguments = ("-version",)

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(remote_workflows=True)

    def validate(self, workflow: str, engine_options: Mapping[str, Any]) -> None:
        super().validate(workflow, engine_options)
        config = engine_options.get("config", [])
        if isinstance(config, str):
            config = [config]
        if not isinstance(config, list) or not all(isinstance(item, str) for item in config):
            raise MetaValidationError("nextflow engine option 'config' must be a path or a list of paths")
        for name in ("profile", "revision"):
            if name in engine_options and not isinstance(engine_options[name], str):
                raise MetaValidationError("nextflow engine option %r must be a string" % name)
        safe_relative(engine_options.get("work_dir", "work"), "nextflow work_dir")

    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        parameters = context.write_json("nextflow-params.json", context.parameters)
        executable = self.resolve_executable(context)
        argv: List[str] = [executable, "-log", str(context.metadata_dir / "nextflow.log")]
        config = context.option("config", [])
        for item in [config] if isinstance(config, str) else config:
            argv += ["-c", str(Path(item).expanduser().resolve())]
        argv += ["run", context.workflow, "-params-file", str(parameters),
                 "-work-dir", str(context.run_dir / safe_relative(context.option("work_dir", "work"), "work_dir")),
                 "-ansi-log", "false"]
        if context.option("profile"):
            argv += ["-profile", context.option("profile")]
        if context.option("revision"):
            argv += ["-r", context.option("revision")]
        if context.option("resume"):
            argv.append("-resume")
        generated = [".dagon/nextflow-params.json", ".dagon/nextflow.log"]
        if context.option("trace", True):
            argv += ["-with-trace", str(context.metadata_dir / "nextflow-trace.txt")]
            generated.append(".dagon/nextflow-trace.txt")
        argv += context.arguments()
        # NXF_ANSI_LOG keeps logs plain; the engine configuration is otherwise untouched.
        return EngineInvocation(argv=argv, cwd=context.run_dir, environment={"NXF_ANSI_LOG": "false"},
                                generated_files=generated)

    def execute(self, context: MetaRunContext, invocation: EngineInvocation) -> EngineResult:
        result = super().execute(context, invocation)
        trace = context.metadata_dir / "nextflow-trace.txt"
        if trace.is_file():
            try:
                with open(str(trace), encoding="utf-8") as stream:
                    rows = list(csv.DictReader(stream, delimiter="\t"))
                result.metadata["processes"] = len(rows)
                result.metadata["process_status"] = sorted({row.get("status", "") for row in rows} - {""})
            except (OSError, csv.Error):
                pass
        return result
