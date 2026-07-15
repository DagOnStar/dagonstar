"""Standalone entry point used by CWL and provider-boundary tooling."""
import argparse
import json
import sys

from dagon.faas_models import FaaSInvocation
from dagon.faas_providers import get_provider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    arguments = parser.parse_args()
    with open(arguments.spec, encoding="utf-8") as stream:
        spec = json.load(stream)
    provider = get_provider(spec["provider"])
    result = provider.invoke(FaaSInvocation(spec["provider"], spec["function"], spec.get("invocation", "sync"),
        spec.get("payload", spec.get("inputs", {})), spec.get("timeout"), spec.get("idempotency_key", "cwl"), 1,
        spec.get("provider_options", {}).get(spec["provider"], spec.get("provider_options", {}))))
    json.dump(result.payload or {}, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
