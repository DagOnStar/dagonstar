"""Provider adapters for FaaS tasks. Optional SDKs are imported lazily."""
import json
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Type
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dagon.faas_models import FaaSInvocation, ProviderCapabilities, ProviderInvocationResult


class FaaSError(RuntimeError):
    code = "function_error"
    transient = False

    def __init__(self, message: str, code: str = "function_error", transient: bool = False) -> None:
        super().__init__(message)
        self.code, self.transient = code, transient


class FaaSProvider(ABC):
    name = "provider"

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError

    @abstractmethod
    def invoke(self, invocation: FaaSInvocation) -> ProviderInvocationResult:
        raise NotImplementedError

    def sanitize_metadata(self, metadata: Mapping[str, Any]) -> Mapping[str, Any]:
        denied = ("authorization", "token", "secret", "password", "key", "credential")
        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()
                        if not any(item in str(k).lower() for item in denied)}
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                parts = urlsplit(value)
                query = [(key, "REDACTED" if any(item in key.lower() for item in denied + ("signature",)) else val)
                         for key, val in parse_qsl(parts.query, keep_blank_values=True)]
                return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
            return value
        return clean(dict(metadata))


class MockProvider(FaaSProvider):
    name = "mock"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_sync=True, supports_async=True, supports_cloudevents=True)

    def invoke(self, invocation: FaaSInvocation) -> ProviderInvocationResult:
        options = dict(invocation.provider_options)
        failures = options.get("transient_failures", 0)
        if invocation.attempt <= failures:
            raise FaaSError("Mock transient failure", "provider_unavailable", True)
        if options.get("error"):
            raise FaaSError("Mock function error", "function_error", False)
        response = options.get("response", {"status": "succeeded", "result": dict(invocation.payload), "outputs": {}})
        return ProviderInvocationResult(True, invocation.invocation == "sync", "mock-%04d" % invocation.attempt,
                                        "succeeded" if invocation.invocation == "sync" else "accepted",
                                        response, {"service": "mock", "attempt": invocation.attempt})


class HTTPProvider(FaaSProvider):
    name = "http"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_sync=True, supports_async=True, supports_cloudevents=True)

    def _headers(self, options: Mapping[str, Any], endpoint: str) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        for name, env_name in dict(options.get("header_env", {})).items():
            value = os.environ.get(str(env_name))
            if value is None:
                raise FaaSError("Required HTTP header environment variable is unset: %s" % env_name, "authentication")
            headers[str(name)] = value
        return headers

    def invoke(self, invocation: FaaSInvocation) -> ProviderInvocationResult:
        options = dict(invocation.provider_options)
        endpoint = options.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
            raise FaaSError("HTTP FaaS provider requires an http(s) endpoint", "invalid_request")
        headers = self._headers(options, endpoint)
        if options.get("cloudevents"):
            headers.update({"ce-specversion": "1.0", "ce-type": "org.dagonstar.task.invoke",
                            "ce-source": "dagonstar", "ce-id": invocation.idempotency_key})
        request = Request(endpoint, json.dumps(invocation.payload).encode("utf-8"), headers, method="POST")
        try:
            with urlopen(request, timeout=invocation.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                request_id = response.headers.get("x-request-id") or response.headers.get("x-amzn-requestid")
                return ProviderInvocationResult(True, invocation.invocation == "sync", request_id,
                                                "succeeded", payload, {"service": "http", "status_code": response.status})
        except HTTPError as exc:
            transient = exc.code in (408, 429, 500, 502, 503, 504)
            raise FaaSError("HTTP function returned status %s" % exc.code,
                            "provider_unavailable" if transient else "function_error", transient) from exc
        except (URLError, TimeoutError) as exc:
            raise FaaSError("Unable to contact HTTP function: %s" % getattr(exc, "reason", exc),
                            "transport_error", True) from exc
        except (ValueError, UnicodeError) as exc:
            raise FaaSError("HTTP function returned invalid JSON", "invalid_response") from exc


class AWSLambdaProvider(FaaSProvider):
    name = "aws"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_sync=True, supports_async=True, max_inline_request_bytes=6 * 1024 * 1024)

    def invoke(self, invocation: FaaSInvocation) -> ProviderInvocationResult:
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError as exc:
            raise FaaSError('AWS Lambda support requires: python -m pip install ".[faas-aws]"', "unsupported_capability") from exc
        options = dict(invocation.provider_options)
        session = boto3.Session(profile_name=options.get("profile"), region_name=options.get("region"))
        try:
            response = session.client("lambda").invoke(FunctionName=invocation.function,
                InvocationType="RequestResponse" if invocation.invocation == "sync" else "Event",
                Payload=json.dumps(invocation.payload).encode("utf-8"), **({"Qualifier": options["qualifier"]} if options.get("qualifier") else {}))
        except (BotoCoreError, ClientError) as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            transient = code in ("TooManyRequestsException", "ServiceException", "ResourceNotReadyException")
            raise FaaSError("AWS Lambda invocation failed (%s)" % (code or type(exc).__name__),
                            "throttled" if code == "TooManyRequestsException" else "provider_unavailable", transient) from exc
        raw = response.get("Payload").read() if response.get("Payload") else b"{}"
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if response.get("FunctionError"):
            raise FaaSError("AWS Lambda reported a function error", "function_error")
        meta = response.get("ResponseMetadata", {})
        return ProviderInvocationResult(True, invocation.invocation == "sync", meta.get("RequestId"), "succeeded", payload,
            {"service": "lambda", "function_version": response.get("ExecutedVersion"), "status_code": response.get("StatusCode")})


class AzureProvider(HTTPProvider):
    name = "azure"

    def _headers(self, options: Mapping[str, Any], endpoint: str) -> Dict[str, str]:
        headers = super()._headers(options, endpoint)
        token_env = options.get("token_env")
        if token_env:
            token = os.environ.get(str(token_env))
        else:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise FaaSError('Azure Functions support requires: python -m pip install ".[faas-azure]"', "unsupported_capability") from exc
            token = DefaultAzureCredential().get_token(options.get("scope", "https://management.azure.com/.default")).token
        if not token:
            raise FaaSError("Azure identity token is unavailable", "authentication")
        headers["Authorization"] = "Bearer " + token
        return headers


class GoogleProvider(HTTPProvider):
    name = "gcp"

    def _headers(self, options: Mapping[str, Any], endpoint: str) -> Dict[str, str]:
        headers = super()._headers(options, endpoint)
        token_env = options.get("token_env")
        if token_env:
            token = os.environ.get(str(token_env))
        else:
            try:
                from google.auth.transport.requests import Request as GoogleRequest
                from google.oauth2.id_token import fetch_id_token
            except ImportError as exc:
                raise FaaSError('Google Functions support requires: python -m pip install ".[faas-gcp]"', "unsupported_capability") from exc
            token = fetch_id_token(GoogleRequest(), options.get("audience", endpoint))
        if not token:
            raise FaaSError("Google identity token is unavailable", "authentication")
        headers["Authorization"] = "Bearer " + token
        return headers


_PROVIDERS: Dict[str, Type[FaaSProvider]] = {item.name: item for item in
    (MockProvider, HTTPProvider, AWSLambdaProvider, AzureProvider, GoogleProvider)}
_PROVIDERS["knative"] = HTTPProvider


def register_provider(name: str, provider: Type[FaaSProvider]) -> None:
    if not name or not issubclass(provider, FaaSProvider):
        raise ValueError("A FaaS provider must extend FaaSProvider")
    _PROVIDERS[name.lower()] = provider


def get_provider(name: str) -> FaaSProvider:
    try:
        return _PROVIDERS[name.lower()]()
    except KeyError as exc:
        raise ValueError("Unknown FaaS provider: %s" % name) from exc
