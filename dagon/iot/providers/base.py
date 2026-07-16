"""IoT provider contract."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Set

from dagon.iot.model import IoTInvocation, IoTInvocationResult


class IoTProvider(ABC):
    name = ""
    supports_reattach = False

    @abstractmethod
    def capabilities(self) -> Set[str]:
        raise NotImplementedError

    def prepare(self, request: Dict[str, Any], context: Dict[str, Any]) -> None:
        return None

    @abstractmethod
    def invoke(self, request: Dict[str, Any], context: Dict[str, Any]) -> IoTInvocation:
        raise NotImplementedError

    @abstractmethod
    def poll(self, invocation: IoTInvocation, context: Dict[str, Any]) -> IoTInvocationResult:
        raise NotImplementedError

    def reattach(self, checkpoint: Dict[str, Any], context: Dict[str, Any]) -> IoTInvocation:
        raise NotImplementedError("Provider does not support reattachment")

    def cancel(self, invocation: IoTInvocation, context: Dict[str, Any]) -> None:
        return None
