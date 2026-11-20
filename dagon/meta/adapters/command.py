"""Generic adapter for any engine with a command-line interface.

``engine_options["command"]`` is an argument vector (never a shell string)
whose items may contain these placeholders, expanded with ``str.format``:

``{workflow}``         absolute workflow location
``{parameters_file}``  JSON document with every input (absolute paths for files)
``{run_dir}``          engine working directory
``{workdir}``          task scratch directory
``{python}``           the Python interpreter running DAGonStar
``{inputs[name]}``     the value of one input (an absolute path for files)

The parameter document path is also exported as ``DAGON_META_PARAMETERS``.
"""

from typing import Any, Mapping

from dagon.meta.adapters.base import MetaEngineAdapter
from dagon.meta.models import EngineCapabilities, EngineInvocation, MetaRunContext, MetaValidationError


class CommandAdapter(MetaEngineAdapter):
    name = "command"
    executable = None
    options = ("command",)

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(remote_workflows=True)

    def validate(self, workflow: str, engine_options: Mapping[str, Any]) -> None:
        super().validate(workflow, engine_options)
        command = engine_options.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            raise MetaValidationError("the command adapter needs engine_options['command'] as a non-empty "
                                      "list of strings (an argument vector, not a shell string)")

    def unavailable_reason(self, context: MetaRunContext) -> Any:
        try:
            self._argv(context, "parameters.json")
        except MetaValidationError as exc:
            return str(exc)
        return None

    def _argv(self, context: MetaRunContext, parameters_file: str) -> list:
        values = {"workflow": context.workflow, "parameters_file": parameters_file, "run_dir": str(context.run_dir),
                  "workdir": str(context.workdir), "python": context.python, "inputs": context.parameters}
        try:
            return [item.format(**values) for item in context.option("command")] + context.arguments()
        except (KeyError, IndexError, ValueError) as exc:
            raise MetaValidationError("invalid placeholder in the command adapter argument vector: %s" % exc) from exc

    def prepare(self, context: MetaRunContext) -> EngineInvocation:
        parameters = context.write_json("meta-parameters.json", context.parameters)
        return EngineInvocation(argv=self._argv(context, str(parameters)), cwd=context.run_dir,
                                environment={"DAGON_META_PARAMETERS": str(parameters)},
                                generated_files=[".dagon/meta-parameters.json"])

    def version(self, context: MetaRunContext) -> Any:
        return None
