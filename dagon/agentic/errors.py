"""Typed errors raised by agentic workflow tasks.

Every error carries a short, stable ``code`` so reports, checkpoints, and tests
can classify a failure without parsing display text.
"""


class AgenticError(Exception):
    """Base class for every agentic-task failure."""

    code = "agentic_error"


class AgenticValidationError(AgenticError, ValueError):
    """The task declaration (contract) is invalid."""

    code = "invalid_contract"


class AgenticConfigurationError(AgenticError, ValueError):
    """The ``dagon.ini`` agent, agent-provider, or LLM-provider configuration is invalid."""

    code = "invalid_configuration"


class AgenticProviderError(AgenticError):
    """The agent provider (adapter) failed; the message is already redacted."""

    code = "provider_error"


class AgenticToolError(AgenticError):
    """A registered tool raised, returned invalid data, or exceeded its bounds."""

    code = "tool_error"


class AgenticTimeoutError(AgenticError):
    """An operation exceeded its deadline (clamped to the remaining task time)."""

    code = "timeout"


class AgenticCancelled(AgenticError):
    """The task was cancelled; nothing was published."""

    code = "cancelled"


class AgenticGuardrailViolation(AgenticError):
    """A non-repairable guardrail blocked an action or candidate."""

    code = "guardrail_blocked"

    def __init__(self, message, violation=None):
        AgenticError.__init__(self, message)
        self.violation = violation


class AgenticEvaluationError(AgenticError):
    """An evaluator failed to execute or returned an invalid result."""

    code = "evaluator_error"


class AgenticTransientEvaluationError(AgenticEvaluationError):
    """An evaluator failure explicitly classified as transient (retried once within budget)."""

    code = "evaluator_transient_error"


class AgenticBudgetExhausted(AgenticError):
    """A finite execution budget was exhausted before a candidate was accepted."""

    code = "budget_exhausted"


class AgenticNotAccepted(AgenticError):
    """The bounded loop ended without an accepted candidate.

    ``report`` is the (redacted) evaluation report written as a diagnostic.
    """

    code = "not_accepted"

    def __init__(self, message, report=None):
        AgenticError.__init__(self, message)
        self.report = report
