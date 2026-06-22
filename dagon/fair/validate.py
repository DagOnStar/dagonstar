"""Small deterministic FAIR validation gates."""
from typing import Any, Dict, List


class FairValidationError(ValueError):
    pass


def validate_profile(profile: Any, strict: bool = False) -> Dict[str, Any]:
    missing = [field for field in ("title", "description", "license") if not getattr(profile, field, None)]
    if not getattr(profile, "creators", None):
        missing.append("creators")
    if missing and strict:
        raise FairValidationError("FAIR profile is missing: " + ", ".join(missing))
    return {"missing": missing}


def validate_run(run: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    checks = []
    profile = run.get("profile", {})
    for key in ("run_id", "workflow_id"):
        ok = bool(run.get(key))
        checks.append({"id": "F1", "status": "passed" if ok else "failed", "message": key + " present"})
        if not ok: errors.append("Missing " + key)
    metadata_ok = bool(profile.get("title") and profile.get("description") and profile.get("creators"))
    checks.append({"id": "F2", "status": "passed" if metadata_ok else "failed", "message": "core descriptive metadata"})
    if not metadata_ok: errors.append("Missing core descriptive metadata")
    checks.extend([
        {"id": "A1", "status": "passed" if profile.get("access_policy") else "failed", "message": "access policy present"},
        {"id": "I1", "status": "passed", "message": "RO-Crate JSON-LD export available"},
        {"id": "I2", "status": "passed", "message": "PROV JSON export available"},
        {"id": "R1.1", "status": "passed" if profile.get("license") else "failed", "message": "license present"},
    ])
    for artifact in run.get("artifacts", []):
        if artifact.get("declared_output") and not artifact.get("exists"):
            (errors if strict else warnings).append("Declared output missing: " + artifact.get("path", "unknown"))
    status = "failed" if errors else ("passed-with-warnings" if warnings else "passed")
    return {"status": status, "errors": errors, "warnings": warnings, "checks": checks}
