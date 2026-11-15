"""Resolve named agent profiles from ``dagon.ini``.

Resolution: ``[agent.<profile>]`` -> ``[agent_provider.<provider>]`` -> (for
adapters that need one) ``[llm.<llm_provider>]``.  The profile is the maximum
authority: a task may only narrow its tools and budgets and add guardrails.
Secrets are never read here; ``api_key_env`` is resolved at invocation time.
"""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from dagon.agentic.errors import AgenticConfigurationError
from dagon.agentic.registry import Registry, default_registry
from dagon.agentic.security import sha256_json

PROFILE_KEYS = {"provider", "llm_provider", "strategy", "tools", "guardrails", "max_steps", "max_tool_calls",
                "max_attempts", "timeout_seconds", "max_tokens", "max_tool_output_bytes", "max_trace_bytes",
                "temperature", "description"}
PROVIDER_KEYS = {"implementation", "scenario", "description"}
STRATEGIES = {"bounded_iterative"}
MOCK_SCENARIOS = {"cooperative", "undeclared_tool", "path_escape", "workflow_uri", "malformed",
                  "self_reported_score", "drop_records", "slow"}
#: Documented finite defaults for budgets a profile may omit.
DEFAULT_BUDGETS = {"max_tool_calls": 8, "max_tokens": 4096, "max_tool_output_bytes": 65536,
                   "max_trace_bytes": 262144}
_INTEGER_BUDGETS = ("max_steps", "max_tool_calls", "max_attempts", "max_tokens", "max_tool_output_bytes",
                    "max_trace_bytes")


@dataclass(frozen=True)
class EffectiveProfile:
    """Normalized, non-secret effective configuration of one agentic task."""

    name: str
    provider: str
    implementation: str
    strategy: str
    tools: Tuple[str, ...]
    guardrails: Tuple[str, ...]
    budgets: Dict[str, Any]
    scenario: Optional[str] = None
    llm_provider: Optional[str] = None
    llm: Dict[str, Any] = field(default_factory=dict)
    temperature: Optional[float] = None

    def normalized(self) -> Dict[str, Any]:
        """Return the non-secret configuration used for identity hashing.

        Endpoints and credential *references* are included in the digest but
        are never exported; ``public()`` is the exportable view.
        """
        return {"name": self.name, "provider": self.provider, "implementation": self.implementation,
                "strategy": self.strategy, "tools": list(self.tools), "guardrails": list(self.guardrails),
                "budgets": dict(sorted(self.budgets.items())), "scenario": self.scenario,
                "llm_provider": self.llm_provider, "llm": dict(sorted(self.llm.items())),
                "temperature": self.temperature}

    @property
    def digest(self) -> str:
        return sha256_json(self.normalized())

    def public(self) -> Dict[str, Any]:
        return {"profile": self.name, "provider": self.provider, "implementation": self.implementation,
                "strategy": self.strategy, "tools": list(self.tools), "guardrails": list(self.guardrails),
                "budgets": dict(sorted(self.budgets.items())), "llm_provider": self.llm_provider,
                "profile_digest": self.digest}


def _section(cfg: Any, name: str) -> Optional[Dict[str, str]]:
    """Read a section from a ConfigParser or the dict form produced by ``read_config``."""
    if cfg is None:
        return None
    has_section = getattr(cfg, "has_section", None)
    if callable(has_section):
        if not has_section(name):
            return None
        return {key: value for key, value in cfg.items(name, raw=True)}
    if name not in cfg:  # never index a defaultdict: that would create the section
        return None
    return dict(cfg[name])


def _list(value: Optional[str]) -> List[str]:
    if value is None:
        return []
    return [item.strip() for item in str(value).replace("\n", ",").split(",") if item.strip()]


def _number(section: str, key: str, value: str, integer: bool) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AgenticConfigurationError("[%s] %s must be a number, got %r" % (section, key, value))
    if not math.isfinite(number) or number <= 0:
        raise AgenticConfigurationError("[%s] %s must be finite and positive" % (section, key))
    if integer:
        if int(number) != number:
            raise AgenticConfigurationError("[%s] %s must be an integer" % (section, key))
        return int(number)
    return number


def resolve_profile(cfg: Any, name: str, task_tools: Optional[List[str]] = None,
                    task_guardrails: Optional[List[str]] = None, task_budgets: Optional[Dict[str, Any]] = None,
                    registry: Optional[Registry] = None) -> EffectiveProfile:
    """Resolve and validate a profile before any provider or tool call.

    :raises AgenticConfigurationError: for missing sections, unknown keys or
        names, invalid numbers, or a task that tries to widen its authority
    """
    registry = registry or default_registry()
    section_name = "agent." + name
    profile = _section(cfg, section_name)
    if profile is None:
        raise AgenticConfigurationError("agent profile %r is not configured (expected [%s] in dagon.ini)"
                                        % (name, section_name))
    unknown = sorted(set(profile) - PROFILE_KEYS)
    if unknown:
        raise AgenticConfigurationError("[%s] has unknown key(s): %s" % (section_name, ", ".join(unknown)))
    provider = profile.get("provider", "").strip()
    if not provider:
        raise AgenticConfigurationError("[%s] needs provider = <agent_provider name>" % section_name)
    provider_section_name = "agent_provider." + provider
    provider_section = _section(cfg, provider_section_name)
    if provider_section is None:
        raise AgenticConfigurationError("agent provider %r is not configured (expected [%s])"
                                        % (provider, provider_section_name))
    unknown = sorted(set(provider_section) - PROVIDER_KEYS)
    if unknown:
        raise AgenticConfigurationError("[%s] has unknown key(s): %s" % (provider_section_name, ", ".join(unknown)))
    implementation = provider_section.get("implementation", "").strip()
    if implementation not in registry.adapters:
        raise AgenticConfigurationError("[%s] implementation %r is not a registered adapter (registered: %s)"
                                        % (provider_section_name, implementation, ", ".join(sorted(registry.adapters))))
    scenario = provider_section.get("scenario")
    if scenario is not None:
        scenario = scenario.strip()
        if implementation != "mock" or scenario not in MOCK_SCENARIOS:
            raise AgenticConfigurationError("[%s] scenario is only valid for the mock adapter and must be one of: %s"
                                            % (provider_section_name, ", ".join(sorted(MOCK_SCENARIOS))))
    strategy = profile.get("strategy", "bounded_iterative").strip()
    if strategy not in STRATEGIES:
        raise AgenticConfigurationError("[%s] strategy must be one of: %s"
                                        % (section_name, ", ".join(sorted(STRATEGIES))))

    budgets: Dict[str, Any] = {}
    for key in ("max_steps", "timeout_seconds"):
        if not profile.get(key):
            raise AgenticConfigurationError("[%s] must set a finite positive %s" % (section_name, key))
    for key in _INTEGER_BUDGETS + ("timeout_seconds",):
        if profile.get(key):
            budgets[key] = _number(section_name, key, profile[key], key in _INTEGER_BUDGETS)
    for key, value in DEFAULT_BUDGETS.items():
        budgets.setdefault(key, value)
    budgets.setdefault("max_attempts", budgets["max_steps"])

    temperature = None
    if profile.get("temperature"):
        try:
            temperature = float(profile["temperature"])
        except ValueError:
            raise AgenticConfigurationError("[%s] temperature must be a number" % section_name)
        if not math.isfinite(temperature) or temperature < 0:
            raise AgenticConfigurationError("[%s] temperature must be finite and non-negative" % section_name)

    profile_tools = _list(profile.get("tools"))
    for tool in profile_tools:
        if tool not in registry.tools:
            raise AgenticConfigurationError("[%s] lists unknown tool %r" % (section_name, tool))
    if task_tools is None:
        tools = profile_tools
    else:
        widened = sorted(set(task_tools) - set(profile_tools))
        if widened:
            raise AgenticConfigurationError("task requests tool(s) %s not permitted by profile %s"
                                            % (", ".join(widened), name))
        tools = list(task_tools)
    profile_guards = _list(profile.get("guardrails"))
    for guard in profile_guards + list(task_guardrails or []):
        if guard not in registry.guardrails:
            raise AgenticConfigurationError("unknown guardrail %r" % guard)
    for key, value in (task_budgets or {}).items():
        if key not in budgets:
            raise AgenticConfigurationError("task budget %s has no profile maximum" % key)
        if value > budgets[key]:
            raise AgenticConfigurationError("task budget %s=%s exceeds the profile %s maximum %s"
                                            % (key, value, name, budgets[key]))
        budgets[key] = value

    llm_provider = (profile.get("llm_provider") or "").strip() or None
    llm: Dict[str, Any] = {}
    if registry.adapters[implementation].requires_llm and llm_provider is None:
        raise AgenticConfigurationError("[%s] uses adapter %r, which requires llm_provider = <[llm.*] name>"
                                        % (section_name, implementation))
    if llm_provider is not None:
        llm_section_name = "llm." + llm_provider
        llm_section = _section(cfg, llm_section_name)
        if llm_section is None:
            raise AgenticConfigurationError("LLM provider %r is not configured (expected [%s])"
                                            % (llm_provider, llm_section_name))
        endpoint = (llm_section.get("endpoint") or "").rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            raise AgenticConfigurationError("[%s] needs an http(s) endpoint" % llm_section_name)
        if llm_section.get("api_key"):
            # LLMTask still reads an inline api_key for compatibility; agentic profiles never do.
            raise AgenticConfigurationError("[%s] contains an inline api_key, which agentic profiles refuse: "
                                            "remove it and name an environment variable with api_key_env"
                                            % llm_section_name)
        variable = (llm_section.get("api_key_env") or "").strip()
        if not variable:
            raise AgenticConfigurationError("[%s] requires api_key_env (the name of the environment variable "
                                            "that holds the key)" % llm_section_name)
        llm = {"endpoint": endpoint, "model": llm_section.get("model", ""), "api_key_env": variable}
    return EffectiveProfile(
        name=name, provider=provider, implementation=implementation, strategy=strategy,
        tools=tuple(tools), guardrails=tuple(sorted(set(profile_guards) | set(task_guardrails or []))),
        budgets=budgets, scenario=scenario, llm_provider=llm_provider, llm=llm, temperature=temperature)


def resolve_api_key(cfg: Any, llm_provider: str) -> Tuple[str, List[str]]:
    """Resolve the LLM credential from ``api_key_env`` at invocation; return ``(key, secrets_to_redact)``.

    An inline ``api_key`` is refused: agentic credentials come only from the environment.
    """
    import os
    section = _section(cfg, "llm." + llm_provider) or {}
    if section.get("api_key"):
        raise AgenticConfigurationError("[llm.%s] contains an inline api_key, which agentic profiles refuse; "
                                        "use api_key_env" % llm_provider)
    variable = (section.get("api_key_env") or "").strip()
    key = os.environ.get(variable, "") if variable else ""
    if not key:
        raise AgenticConfigurationError("LLM provider %r has no credential: set the environment variable named "
                                        "by api_key_env" % llm_provider)
    return key, [key]
