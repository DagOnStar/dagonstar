"""Lifecycle recorder and local standard-format FAIR exporters."""
import hashlib
import json
import mimetypes
import os
import platform
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Artifact
from .validate import validate_run


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "workflow"


def _checksum(path: Path) -> Optional[str]:
    if not path.is_file(): return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""): digest.update(block)
    return "sha256:" + digest.hexdigest()


class FairRecorder:
    """Captures workflow lifecycle events without changing task execution."""
    def __init__(self, workflow: Any, profile: Any) -> None:
        self.workflow, self.profile = workflow, profile
        self.run: Dict[str, Any] = {"workflow_id": "urn:dagonstar:workflow:" + _safe(workflow.name),
            "workflow_name": workflow.name, "profile": profile.as_dict(), "tasks": {}, "artifacts": [], "dependencies": [], "staging": []}
        self.output_dir: Optional[Path] = None
        for name in ("on_workflow_start", "on_workflow_end", "on_task_start", "on_task_end",
                     "on_task_wait", "on_task_staging_in_start", "on_task_staging_in_end",
                     "on_task_execute_start", "on_task_staging_out_start", "on_task_staging_out_end",
                     "on_dependencies_made"):
            workflow.add_listener(name, getattr(self, name))

    def on_dependencies_made(self, workflow: Any) -> None:
        edges = []
        for task in workflow.tasks:
            for previous in task.prevs:
                path = None
                marker = "workflow:///" + previous.name + "/"
                if marker in task.command:
                    path = task.command.split(marker, 1)[1].split(" ", 1)[0]
                edges.append({"producer": previous.name, "consumer": task.name,
                              "path": path, "type": "workflow-edge"})
        self.run["dependencies"] = edges

    def on_workflow_start(self, workflow: Any) -> None:
        self.run["run_id"] = "urn:dagonstar:run:" + str(uuid.uuid4())
        base = self.profile.output_dir or os.path.join(workflow.get_scratch_dir_base(), ".dagon", "fair", _safe(workflow.name), self.run["run_id"].rsplit(":", 1)[-1])
        self.output_dir = Path(base); self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run.update({"start_time": _utc(), "dagonstar_version": self._version(),
            "environment": {"python": sys.version.split()[0], "platform": platform.platform(), "variables": self._environment()},
            "data_mover": getattr(workflow.data_mover, "value", str(workflow.data_mover)),
            "stager_mover": getattr(workflow.stager_mover, "value", str(workflow.stager_mover))})
        self.on_dependencies_made(workflow)

    def on_task_start(self, task: Any) -> None:
        self.run["tasks"][task.name] = {"id": self._task_id(task), "name": task.name, "type": type(task).__name__,
            "command": task.command, "command_sha256": "sha256:" + hashlib.sha256(task.command.encode()).hexdigest(),
            "predecessors": [item.name for item in task.prevs], "successors": [item.name for item in task.nexts],
            "annotations": dict(task.fair_annotations), "declared_inputs": [self._artifact(a) for a in task.fair_inputs],
            "declared_outputs": [self._artifact(a) for a in task.fair_outputs], "start_time": _utc()}

    def on_task_wait(self, task: Any) -> None: self._record(task)["waited_for"] = [item.name for item in task.prevs]
    def on_task_staging_in_start(self, task: Any) -> None: self.run["staging"].append({"task": task.name, "phase": "in", "start_time": _utc()})
    def on_task_staging_in_end(self, task: Any) -> None: self.run["staging"][-1]["end_time"] = _utc()
    def on_task_staging_out_start(self, task: Any) -> None: self.run["staging"].append({"task": task.name, "phase": "out", "start_time": _utc()})
    def on_task_staging_out_end(self, task: Any) -> None: self.run["staging"][-1]["end_time"] = _utc()

    def on_task_execute_start(self, task: Any) -> None:
        record = self._record(task); record["working_dir"] = task.working_dir; record["backend"] = task.get_info() or {}

    def on_task_end(self, task: Any) -> None:
        record = self._record(task); record.update({"end_time": _utc(), "status": task.status.value,
            "checkpoint_reused": bool(task.fair_checkpoint_reused)})
        execution = task.get_execution_metadata()
        if execution:
            record["execution"] = execution
        for declared in task.fair_outputs:
            artifact = self._artifact(declared); artifact.update({"task": task.name, "declared_output": True, "id": self._artifact_id(task.name, declared.path)})
            candidate = Path(task.working_dir or "") / declared.path
            artifact["exists"] = candidate.is_file(); artifact["local_path"] = str(candidate)
            if artifact["exists"]:
                artifact["size_bytes"] = candidate.stat().st_size; artifact["checksum"] = _checksum(candidate)
                artifact["media_type"] = artifact.get("media_type") or mimetypes.guess_type(str(candidate))[0]
            self.run["artifacts"].append(artifact)
        if type(task).__name__ == "FaaSTask":
            for name, declared in task.outputs.items():
                relative = "outputs/" + declared["path"]
                candidate = Path(task.working_dir or "") / relative
                artifact = {"name": name, "path": relative, "required": declared.get("required", True),
                    "task": task.name, "declared_output": True, "id": self._artifact_id(task.name, relative),
                    "exists": candidate.is_file(), "local_path": str(candidate)}
                if artifact["exists"]:
                    artifact.update({"size_bytes": candidate.stat().st_size, "checksum": _checksum(candidate),
                        "media_type": declared.get("media_type") or mimetypes.guess_type(str(candidate))[0]})
                self.run["artifacts"].append(artifact)

    def on_workflow_end(self, workflow: Any) -> None:
        if self.output_dir is None: return
        self.run["end_time"] = _utc(); report = validate_run(self.run, self.profile.strict); self.run["validation"] = report
        self._write("run.json", self.run); self._write("prov.json", self._prov()); self._write("ro-crate-metadata.json", self._rocrate())
        self._write("datacite.json", self._datacite()); self._write("codemeta.json", self._codemeta()); self._write("fairness-report.json", report)
        self._write_checksums(); self._write("report.md", self._markdown(report)); self._write("report.html", "<html><body><pre>" + self._markdown(report) + "</pre></body></html>")

    def _record(self, task: Any) -> Dict[str, Any]: return self.run["tasks"].setdefault(task.name, {"id": self._task_id(task), "name": task.name})
    def _task_id(self, task: Any) -> str: return self.run.get("run_id", "urn:dagonstar:run:pending") + ":task:" + _safe(task.name)
    def _artifact_id(self, task: str, path: str) -> str: return self.run["run_id"] + ":artifact:" + _safe(task) + "/" + path.lstrip("/")
    def _artifact(self, artifact: Artifact) -> Dict[str, Any]: return artifact.as_dict() if hasattr(artifact, "as_dict") else dict(artifact)
    def _write(self, name: str, value: Any) -> None:
        target = self.output_dir / name
        if isinstance(value, str): target.write_text(value, encoding="utf-8")
        else: target.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    def _environment(self) -> Dict[str, str]:
        result = {}; denied = tuple(item.upper() for item in self.profile.redact_patterns)
        for key in self.profile.capture_environment:
            if key in os.environ and not any(token in key.upper() for token in denied): result[key] = os.environ[key]
        return result
    def _version(self) -> str:
        try:
            from importlib.metadata import version; return version("dagonstar")
        except Exception: return "unknown"
    def _prov(self) -> Dict[str, Any]:
        activities = list(self.run["tasks"].values()); entities = self.run["artifacts"]
        return {"prefix": {"prov": "http://www.w3.org/ns/prov#"}, "entity": {item["id"]: item for item in entities},
            "activity": {item["id"]: item for item in activities}, "used": [{"activity": self._task_id_name(edge["consumer"]), "entity": self._artifact_id(edge["producer"], edge["path"] or "unknown")} for edge in self.run["dependencies"]],
            "wasInformedBy": self.run["dependencies"]}
    def _task_id_name(self, name: str) -> str: return self.run["run_id"] + ":task:" + _safe(name)
    def _rocrate(self) -> Dict[str, Any]:
        graph: List[Dict[str, Any]] = [{"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}, "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"}},
          {"@id": "./", "@type": "Dataset", "name": self.profile.title, "description": self.profile.description, "license": self.profile.license}]
        graph += [{"@id": item["id"], "@type": "File", "name": item.get("name") or item["path"], "sha256": item.get("checksum"), "contentSize": item.get("size_bytes"), "encodingFormat": item.get("media_type")} for item in self.run["artifacts"]]
        actions = []
        services = []
        for item in self.run["tasks"].values():
            action = {"@id": item["id"], "@type": "CreateAction", "name": item["name"], "startTime": item.get("start_time"), "endTime": item.get("end_time"), "actionStatus": item.get("status")}
            execution = item.get("execution", {})
            if execution.get("model") == "faas":
                identity = "urn:dagonstar:function:%s:%s" % (_safe(str(execution.get("provider"))), _safe(str(execution.get("function"))))
                action["instrument"] = {"@id": identity}
                services.append({"@id": identity, "@type": ["SoftwareApplication", "Service"],
                                 "name": str(execution.get("function")), "runtimePlatform": str(execution.get("provider"))})
            actions.append(action)
        graph += actions + services
        return {"@context": "https://w3id.org/ro/crate/1.2/context", "@graph": graph}
    def _datacite(self) -> Dict[str, Any]: return {"types": {"resourceTypeGeneral": "Workflow"}, "identifiers": [{"identifier": self.run["run_id"], "identifierType": "URN"}], "creators": [{"name": item["name"]} for item in self.run["profile"]["creators"]], "titles": [{"title": self.profile.title}], "publisher": "DAGonStar", "publicationYear": datetime.now().year, "descriptions": [{"description": self.profile.description, "descriptionType": "Abstract"}], "subjects": [{"subject": item} for item in self.profile.keywords], "rightsList": [{"rights": self.profile.license}]}
    def _codemeta(self) -> Dict[str, Any]: return {"@context": "https://doi.org/10.5063/schema/codemeta-2.0", "@type": "SoftwareApplication", "name": "DAGonStar", "description": self.profile.description, "license": self.profile.license, "programmingLanguage": "Python", "runtimePlatform": platform.platform(), "author": self.run["profile"]["creators"]}
    def _write_checksums(self) -> None:
        lines = ["%s  %s" % (a["checksum"].split(":", 1)[1], a["path"]) for a in self.run["artifacts"] if a.get("checksum")]
        self._write("checksums.sha256", "\n".join(lines) + ("\n" if lines else ""))
    def _markdown(self, report: Dict[str, Any]) -> str: return "# FAIRness report\n\nStatus: **%s**\n\n- Run: `%s`\n- Tasks: %d\n- Artifacts: %d\n\nWarnings: %s\n" % (report["status"], self.run["run_id"], len(self.run["tasks"]), len(self.run["artifacts"]), "; ".join(report["warnings"]) or "none")
