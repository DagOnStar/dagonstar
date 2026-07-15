"""Dependency-free public models for Function-as-a-Service invocation."""
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff: str = "none"
    initial_delay_seconds: float = 0.0
    max_delay_seconds: Optional[float] = None
    retry_on: Tuple[str, ...] = ("throttled", "provider_unavailable", "transport_error")


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_sync: bool = True
    supports_async: bool = False
    supports_cloudevents: bool = False
    max_inline_request_bytes: Optional[int] = None
    max_inline_response_bytes: Optional[int] = None
    max_runtime_seconds: Optional[int] = None


@dataclass(frozen=True)
class FaaSInvocation:
    provider: str
    function: Any
    invocation: str
    payload: Mapping[str, Any]
    timeout: Optional[int]
    idempotency_key: str
    attempt: int
    provider_options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderInvocationResult:
    accepted: bool
    completed: bool
    request_id: Optional[str]
    status: str
    payload: Optional[Mapping[str, Any]]
    metadata: Mapping[str, Any] = field(default_factory=dict)
