"""Snakemake adapter: ``snakemake --snakefile <Snakefile> --configfile <inputs>``.

Inputs become Snakemake ``config`` entries through a JSON configuration file
(YAML is a superset of JSON): a file input ``table`` is ``config["table"]``
holding an absolute path.  ``--directory`` points Snakemake at the engine
working directory, so relative rule outputs land where meta-task outputs are
collected from.

Engine options: ``cores`` (int or ``"all"``, default 1), ``targets`` (list of
rules or files), ``profile`` (str), ``executor`` (str, a Snakemake executor
plugin such as ``slurm``), plus the common ``executable`` and ``arguments``.
"""

from typing import Any, List, Mapping

from dagon.meta.adapters.base import MetaEngineAdapter
from dagon.meta.models import EngineInvocation, MetaRunContext, MetaValidationError


class SnakemakeAdapter(MetaEngineAdapter):
    name = "snakemake"
    executable = "snakemake"
    options = ("cores", "targets", "profile", "executor")

    def validate(self, workflow: str, engine_options: Mapping[str, Any]) -> None:
        super().validate(workflow, engine_options)
        cores = engine_options.get("cores", 1)
        if not (cores == "all" or (isinstance(cores, int) and not isinstance(cores, bool) and cores > 0)):
            raise MetaValidationError("snakemake engine option 'cores' must be a positive integer or 'all'")
        targets = engine_options.get("targets", [])
        if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
            raise MetaValidationError("snakemake engine option 'targets' must be a list of strings")
        for name in ("profile", "executor"):
            if name in engine_options and not isinstance(engine_options[name], str):
                raise MetaValidationError("snakemake engine option %r must be a string" % name)

    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        configfile = context.write_json("snakemake-config.json", context.parameters)
        argv: List[str] = [self.resolve_executable(context), "--snakefile", context.workflow,
                           "--directory", str(context.run_dir), "--configfile", str(configfile),
                           "--cores", str(context.option("cores", 1))]
        if context.option("profile"):
            argv += ["--profile", context.option("profile")]
        if context.option("executor"):
            argv += ["--executor", context.option("executor")]
        argv += context.arguments()
        argv += list(context.option("targets", []))
        return EngineInvocation(argv=argv, cwd=context.run_dir, generated_files=[".dagon/snakemake-config.json"])
