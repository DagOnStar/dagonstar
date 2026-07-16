"""Lazy provider registry."""
from importlib import import_module
from typing import Any, Dict, Tuple


_PROVIDERS: Dict[str, Tuple[str, str]] = {"mock": ("dagon.iot.providers.mock", "MockIoTProvider")}


def register_provider(name: str, module: str, class_name: str) -> None:
    _PROVIDERS[name.lower()] = (module, class_name)


def get_provider(name: str) -> Any:
    try:
        module, class_name = _PROVIDERS[name.lower()]
    except KeyError as exc:
        raise ValueError("Unknown IoT provider: %s" % name) from exc
    return getattr(import_module(module), class_name)()


def provider_exists(name: str) -> bool:
    return name.lower() in _PROVIDERS
