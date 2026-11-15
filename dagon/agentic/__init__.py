"""Agentic workflow tasks: bounded agents with independent evaluation.

``DagonTask(TaskType.AGENTIC, ...)`` creates :class:`AgenticTask`.  Agent and
LLM providers are configured only in ``dagon.ini``; see
``docs/agentic_tasks.md`` and ``docs/agentic_configuration.md``.
"""
from dagon.agentic.errors import (AgenticBudgetExhausted, AgenticCancelled, AgenticConfigurationError,
                                  AgenticError, AgenticEvaluationError, AgenticGuardrailViolation,
                                  AgenticNotAccepted, AgenticProviderError, AgenticTimeoutError,
                                  AgenticToolError, AgenticTransientEvaluationError, AgenticValidationError)
from dagon.agentic.registry import (AdapterSpec, EvaluatorSpec, GuardrailSpec, Registry, ToolSpec,
                                    default_registry, register_adapter, register_evaluator,
                                    register_guardrail, register_tool)


def __getattr__(name):
    # Import the task lazily so ``dagon.agentic`` helpers do not require ``dagon.task``.
    if name == "AgenticTask":
        from dagon.agentic.task import AgenticTask
        return AgenticTask
    raise AttributeError("module 'dagon.agentic' has no attribute %r" % name)


__all__ = [
    "AgenticTask", "AdapterSpec", "EvaluatorSpec", "GuardrailSpec", "Registry", "ToolSpec",
    "default_registry", "register_adapter", "register_evaluator", "register_guardrail", "register_tool",
    "AgenticError", "AgenticValidationError", "AgenticConfigurationError", "AgenticProviderError",
    "AgenticToolError", "AgenticTimeoutError", "AgenticCancelled", "AgenticGuardrailViolation",
    "AgenticEvaluationError", "AgenticTransientEvaluationError", "AgenticBudgetExhausted", "AgenticNotAccepted",
]
