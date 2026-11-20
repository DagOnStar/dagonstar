"""Meta-tasks: run workflows written for other engines inside a DAGonStar workflow.

See :class:`dagon.meta.task.MetaTask`, the adapter interface
:class:`dagon.meta.adapters.base.MetaEngineAdapter`, and ``docs/meta_tasks.md``.
Importing this package imports no workflow engine.
"""

from dagon.meta.adapters.base import (BUILTIN_ADAPTERS, ENTRY_POINT_GROUP, MetaEngineAdapter, adapter_exists,
                                      adapter_names, get_adapter, register_adapter, unregister_adapter)
from dagon.meta.models import (SCHEMA_VERSION, EngineCapabilities, EngineInvocation, EngineResult,
                               MetaEngineFailedError, MetaEngineUnavailableError, MetaInput, MetaOutputError,
                               MetaRunContext, MetaStagingError, MetaTaskError, MetaTimeoutError, MetaValidationError)


def __getattr__(name):
    # Imported lazily: dagon.meta.task imports dagon.task, which imports dagon.
    if name == "MetaTask":
        from dagon.meta.task import MetaTask
        return MetaTask
    raise AttributeError(name)


__all__ = ["BUILTIN_ADAPTERS", "ENTRY_POINT_GROUP", "SCHEMA_VERSION", "EngineCapabilities", "EngineInvocation",
           "EngineResult", "MetaEngineAdapter", "MetaEngineFailedError", "MetaEngineUnavailableError", "MetaInput",
           "MetaOutputError", "MetaRunContext", "MetaStagingError", "MetaTask", "MetaTaskError", "MetaTimeoutError",
           "MetaValidationError", "adapter_exists", "adapter_names", "get_adapter", "register_adapter",
           "unregister_adapter"]
