"""Provider-neutral IoT invocation records."""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class IoTInvocation:
    invocation_id: str
    status: str = "WAITING"
    progress: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IoTInvocationResult:
    invocation_id: str
    status: str
    started_at: str
    completed_at: Optional[str]
    operation: str
    provider: str
    requested_target: Any
    selected_target: Any
    payload: Any
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    acknowledgements: List[Dict[str, Any]] = field(default_factory=list)
    measurements: Dict[str, Any] = field(default_factory=dict)
    placement: Optional[Dict[str, Any]] = None
    migration_history: List[Dict[str, Any]] = field(default_factory=list)
    protocol_metadata: Dict[str, Any] = field(default_factory=dict)
    outcome_certainty: str = "known"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
