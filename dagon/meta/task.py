"""``TaskType.META``: run a workflow written for another engine as one DAGonStar task.

A meta-task calls an external workflow - a Nextflow pipeline, a Snakefile, a
Parsl program, a StreamFlow/CWL workflow - through an adapter
(:mod:`dagon.meta.adapters`) and exchanges data with the rest of the DAGonStar
graph through ordinary ``workflow://`` references:

* every ``workflow://`` input is discovered as a dependency, staged into
  ``inputs/<name>/`` and handed to the engine as an absolute local path;
* every declared output is collected from the engine's run directory (or from
  the location the engine reports) into ``outputs/<path>``, where downstream
  tasks reference it as ``workflow:///<meta task>/outputs/<path>``.

The external engine is never modified: adapters only build its documented
command line and parameter files.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from dagon.meta import runner as meta_runner
from dagon.meta.adapters.base import adapter_exists, adapter_names, get_adapter
from dagon.meta.models import (INPUT_KINDS, NAME_PATTERN, OUTPUT_KINDS, SCHEMA_VERSION, STAGING_MODES,
                               MetaStagingError, MetaTaskError, MetaValidationError, is_secret_name, json_copy,
                               reject_secrets, safe_relative, sha256_path)
from dagon.streaming import reject_stream_reference
from dagon.task import Task, TaskType

_REFERENCE = "workflow://"
#: Configuration keys honoured in an optional ``[meta.<engine>]`` dagon.ini section.
_CONFIG_KEYS = ("executable", "python")


def parse_reference(reference: str) -> Tuple[str, str, str]:
    """Split ``workflow://<workflow>/<task>/<path>`` (``<workflow>`` may be empty)."""
    try:
        reject_stream_reference(reference, "Meta")
    except ValueError as exc:
        raise MetaValidationError(str(exc)) from exc
    pieces = reference[len(_REFERENCE):].split("/")
    relative = "/".join(pieces[2:]) if len(pieces) >= 3 else ""
    if len(pieces) < 3 or not pieces[1] or not relative or relative in (".", "./"):
        raise MetaValidationError("invalid meta-task workflow reference (expected workflow://<workflow>/<task>/"
                                  "<path>): %s" % reference)
    return pieces[0], pieces[1], safe_relative(relative.rstrip("/"), "input reference")


def _contains_reference(value: Any) -> bool:
    if isinstance(value, str):
        return _REFERENCE in value
    if isinstance(value, dict):
        return any(_contains_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_reference(item) for item in value)
    return False


class MetaTask(Task):
    """Run an external workflow (another engine) with ``workflow://`` data exchange.

    :param name: task name (unique in the workflow)
    :param engine: registered adapter name (``nextflow``, ``snakemake``, ``parsl``,
        ``streamflow``, ``cwl``, ``command``, ``mock``, or a registered plug-in)
    :param workflow: the external workflow definition: a local file or directory,
        or - for engines that resolve them, such as Nextflow - a remote name
    :param inputs: name -> value.  A ``workflow://`` string is a staged file or
        directory; ``{"type": "file"|"directory", "path": ...}`` names a local
        or referenced path explicitly; anything else is a JSON value
    :param outputs: name -> relative path, or ``{"path": ..., "source": ...,
        "engine_output": ..., "type": "file"|"directory", "required": bool}``.
        ``source`` is relative to the engine run directory (default: ``path``);
        ``engine_output`` names an output the engine reports (CWL runners)
    :param engine_options: adapter-specific options (JSON, credential-free)
    :param environment: extra environment variables for the engine (no secrets;
        credentials are inherited from the parent process environment)
    :param timeout: seconds before the engine is terminated
    :param staging: ``"copy"`` (default) or ``"symlink"`` for staged inputs
    """

    # No command launcher: streams (dagon.streaming) need a command task.
    stream_capable = False
    task_type = TaskType.META

    def __init__(self, name: str, engine: str = "", workflow: str = "", inputs: Optional[Mapping[str, Any]] = None,
                 outputs: Optional[Mapping[str, Any]] = None, engine_options: Optional[Mapping[str, Any]] = None,
                 environment: Optional[Mapping[str, str]] = None, timeout: Optional[float] = None,
                 staging: str = "copy", working_dir: Optional[str] = None,
                 transversal_workflow: Optional[str] = None, globusendpoint: Optional[str] = None,
                 **unknown: Any) -> None:
        if unknown:
            raise MetaValidationError("unknown meta-task option(s): %s" % ", ".join(sorted(unknown)))
        self.engine = str(engine or "").lower()
        if not self.engine or not adapter_exists(self.engine):
            raise MetaValidationError("unknown meta-task engine %r; choose from %s"
                                      % (engine, ", ".join(adapter_names())))
        adapter = get_adapter(self.engine)
        if not isinstance(workflow, str) or not workflow:
            raise MetaValidationError("meta-task workflow (the external workflow definition) is required")
        self.workflow_location = self._workflow_location(workflow, adapter.capabilities().remote_workflows)
        self.inputs = self._normalize_inputs(inputs or {}, adapter.capabilities().directory_inputs)
        self.outputs = self._normalize_outputs(outputs or {}, adapter.capabilities().named_outputs)
        options = json_copy(dict(engine_options or {}), "engine_options")
        reject_secrets(options, "engine_options")
        adapter.validate(self.workflow_location, options)
        self.engine_options = options
        self.environment = self._normalize_environment(environment or {})
        if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0):
            raise MetaValidationError("meta-task timeout must be a positive number of seconds")
        self.timeout = timeout
        if staging not in STAGING_MODES:
            raise MetaValidationError("meta-task staging must be one of: %s" % ", ".join(STAGING_MODES))
        self.staging = staging
        self.meta_result: Optional[Dict[str, Any]] = None
        command = "dagon-meta-runner run --spec .dagon/meta_spec.json --workdir ."
        Task.__init__(self, name, command, working_dir=working_dir, transversal_workflow=transversal_workflow,
                      globusendpoint=globusendpoint)

    # -- specification -----------------------------------------------------

    @staticmethod
    def _workflow_location(workflow: str, remote_allowed: bool) -> str:
        if workflow.startswith(_REFERENCE):
            raise MetaValidationError("the meta-task workflow definition is a local path or engine-resolved "
                                      "name, not a workflow:// reference")
        candidate = Path(workflow).expanduser()
        if not remote_allowed or candidate.exists() or candidate.is_absolute() or \
                workflow.startswith((".", "~")) or candidate.suffix:
            return str(candidate.resolve())
        # An engine-resolved name such as ``nextflow-io/hello``.
        return workflow

    @staticmethod
    def _normalize_inputs(inputs: Mapping[str, Any], directories: bool) -> Dict[str, Dict[str, Any]]:
        if not isinstance(inputs, Mapping):
            raise MetaValidationError("meta-task inputs must be a mapping")
        result = {}
        for name, value in inputs.items():
            if not isinstance(name, str) or not NAME_PATTERN.match(name):
                raise MetaValidationError("meta-task input names must be identifiers: %r" % (name,))
            if isinstance(value, str) and value.startswith(_REFERENCE):
                parse_reference(value)
                descriptor: Dict[str, Any] = {"type": "auto", "path": value}
            elif isinstance(value, Mapping) and value.get("type") in INPUT_KINDS + ("auto",) and \
                    set(value) <= {"type", "path", "value"}:
                kind = value["type"]
                if kind == "value":
                    descriptor = {"type": "value", "value": json_copy(value.get("value"), "input " + name)}
                else:
                    location = value.get("path")
                    if not isinstance(location, str) or not location:
                        raise MetaValidationError("meta-task %s input %s needs a path" % (kind, name))
                    if location.startswith(_REFERENCE):
                        parse_reference(location)
                    else:
                        location = str(Path(location).expanduser().resolve())
                    descriptor = {"type": kind, "path": location}
            else:
                copied = json_copy(value, "input " + name)
                if _contains_reference(copied):
                    raise MetaValidationError("meta-task input %s embeds workflow:// references in a structured "
                                              "value; bind each file or directory as its own input" % name)
                descriptor = {"type": "value", "value": copied}
            if descriptor["type"] == "directory" and not directories:
                raise MetaValidationError("this engine adapter does not accept directory inputs: %s" % name)
            result[name] = descriptor
        return result

    @staticmethod
    def _normalize_outputs(outputs: Mapping[str, Any], named: bool) -> Dict[str, Dict[str, Any]]:
        if not isinstance(outputs, Mapping):
            raise MetaValidationError("meta-task outputs must be a mapping")
        result = {}
        destinations = set()
        for name, value in outputs.items():
            if not isinstance(name, str) or not NAME_PATTERN.match(name):
                raise MetaValidationError("meta-task output names must be identifiers: %r" % (name,))
            descriptor: Optional[Dict[str, Any]] = None
            if isinstance(value, str):
                descriptor = {"path": value}
            elif isinstance(value, Mapping):
                descriptor = dict(value)
            if descriptor is None or not set(descriptor) <= {"path", "source", "engine_output", "type", "required"}:
                raise MetaValidationError("invalid meta-task output descriptor for %s" % name)
            if "path" not in descriptor:
                raise MetaValidationError("meta-task output %s needs a path below outputs/" % name)
            normalized = {"path": safe_relative(descriptor["path"], "output path"),
                          "type": descriptor.get("type", "file"), "required": bool(descriptor.get("required", True))}
            if normalized["type"] not in OUTPUT_KINDS:
                raise MetaValidationError("meta-task output %s type must be 'file' or 'directory'" % name)
            if descriptor.get("engine_output"):
                if not named:
                    raise MetaValidationError("this engine does not report named outputs; give output %s a "
                                              "'source' path instead of 'engine_output'" % name)
                if "source" in descriptor:
                    raise MetaValidationError("meta-task output %s sets both 'source' and 'engine_output'" % name)
                normalized["engine_output"] = str(descriptor["engine_output"])
            else:
                normalized["source"] = safe_relative(descriptor.get("source", descriptor["path"]), "output source")
            if normalized["path"] in destinations:
                raise MetaValidationError("two meta-task outputs share the path %s" % normalized["path"])
            destinations.add(normalized["path"])
            result[name] = normalized
        return result

    @staticmethod
    def _normalize_environment(environment: Mapping[str, Any]) -> Dict[str, str]:
        if not isinstance(environment, Mapping):
            raise MetaValidationError("meta-task environment must be a mapping")
        result = {}
        for key, value in environment.items():
            if not isinstance(key, str) or not key or "=" in key:
                raise MetaValidationError("invalid meta-task environment variable name: %r" % (key,))
            if is_secret_name(key):
                raise MetaValidationError("meta-task environment variable %s looks like a credential; export it in "
                                          "the parent process environment instead" % key)
            result[key] = str(value)
        return result

    def portable_spec(self) -> Dict[str, Any]:
        """The credential-free, JSON-serializable specification (also the CWL-embedded spec)."""
        spec: Dict[str, Any] = {"schema_version": SCHEMA_VERSION, "engine": self.engine,
                                "workflow": self.workflow_location, "inputs": self.inputs, "outputs": self.outputs,
                                "engine_options": self.engine_options, "environment": self.environment,
                                "staging": self.staging}
        if self.timeout is not None:
            spec["timeout"] = self.timeout
        return json_copy(spec, "specification")

    def _effective_spec(self) -> Dict[str, Any]:
        """The specification with site defaults from an optional ``[meta.<engine>]`` section."""
        spec = self.portable_spec()
        section = {}
        if self.workflow is not None and isinstance(getattr(self.workflow, "cfg", None), Mapping):
            section = dict(self.workflow.cfg.get("meta." + self.engine, {}) or {})
        for key in _CONFIG_KEYS:
            if key in section and key not in spec["engine_options"]:
                if key == "python" and self.engine != "parsl":
                    continue
                spec["engine_options"][key] = str(section[key])
        return spec

    @staticmethod
    def spec_digest(spec: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def as_json(self) -> Dict[str, Any]:
        task = super().as_json()
        task.update({"type": "meta", "command": None, "meta": self.portable_spec()})
        task.pop("working_dir", None)
        return task

    # -- dependencies ------------------------------------------------------

    def _references(self) -> Iterable[Tuple[str, str]]:
        for name, descriptor in sorted(self.inputs.items()):
            location = descriptor.get("path")
            if isinstance(location, str) and location.startswith(_REFERENCE):
                yield name, location

    def _find_producer(self, workflow_name: str, task_name: str) -> Any:
        return self.workflow.find_task_by_name(workflow_name, task_name) if self.workflow is not None else None

    def _producers(self) -> List[Tuple[str, str, str, Any]]:
        """(reference, workflow, relative path, producer task) for every referenced input."""
        found = []
        for _, reference in self._references():
            workflow_name, task_name, relative = parse_reference(reference)
            workflow_name = workflow_name or self.workflow.name
            found.append((reference, workflow_name, relative, self._find_producer(workflow_name, task_name)))
        return found

    def pre_run(self) -> None:
        seen = set()
        for reference, workflow_name, _, producer in self._producers():
            if producer is None:
                raise MetaValidationError("meta-task input producer was not found: %s" % reference)
            if producer is self:
                raise MetaValidationError("a meta-task cannot consume its own outputs: %s" % reference)
            if id(producer) in seen:
                continue
            seen.add(id(producer))
            if workflow_name == self.workflow.name:
                if producer not in self.prevs:
                    self.add_dependency_to(producer)
            elif producer not in self.prevs:
                self.add_transversal_point(producer)
            producer.increment_reference_count()

    def _release_references(self) -> None:
        released = set()
        for _, _, _, producer in self._producers():
            if producer is not None and id(producer) not in released:
                released.add(id(producer))
                producer.decrement_reference_count()

    def input_kind(self, reference: str) -> str:
        """CWL type (``File`` or ``Directory``) of the input bound to *reference*."""
        for descriptor in self.inputs.values():
            if descriptor.get("path") == reference:
                return "Directory" if descriptor["type"] == "directory" else "File"
        return "File"

    def output_kind(self, relative: str) -> Optional[str]:
        """CWL type of a declared output given its path relative to the scratch directory."""
        for descriptor in self.outputs.values():
            if "outputs/" + descriptor["path"] == relative:
                return "Directory" if descriptor["type"] == "directory" else "File"
        return None

    # -- staging -----------------------------------------------------------

    def _source(self, location: str) -> Path:
        if not location.startswith(_REFERENCE):
            return Path(location)
        workflow_name, task_name, relative = parse_reference(location)
        producer = self._find_producer(workflow_name or self.workflow.name, task_name)
        if producer is None or producer.working_dir is None:
            raise MetaStagingError("meta-task input producer is unavailable: %s" % location)
        return Path(producer.working_dir, relative)

    def _stage_inputs(self) -> Dict[str, str]:
        """Stage file and directory inputs below ``inputs/<name>/``; return location -> staged path."""
        bindings: Dict[str, str] = {}
        for name, descriptor in sorted(self.inputs.items()):
            if descriptor["type"] == "value":
                continue
            source = self._source(descriptor["path"])
            kind = descriptor["type"]
            if kind == "auto":
                kind = "directory" if source.is_dir() else "file"
            if not (source.is_dir() if kind == "directory" else source.is_file()):
                raise MetaStagingError("meta-task %s input %s does not exist: %s" % (kind, name, source))
            destination = Path(self.working_dir, "inputs", name, source.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink() or destination.is_file():
                destination.unlink()
            elif destination.is_dir():
                shutil.rmtree(str(destination))
            if self.staging == "symlink":
                os.symlink(str(source.resolve()), str(destination), target_is_directory=source.is_dir())
            elif source.is_dir():
                shutil.copytree(str(source), str(destination))
            else:
                shutil.copy2(str(source), str(destination))
            bindings[descriptor["path"]] = destination.relative_to(self.working_dir).as_posix()
        return bindings

    # -- checkpoint --------------------------------------------------------

    def reuse_checkpoint(self) -> bool:
        """Reuse only a verified success: same spec, workflow definition, inputs, and outputs."""
        checkpoint = self.workflow.checkpoints.get(self.checkpoint_key(), {})
        if checkpoint.get("task_type") != "meta" or checkpoint.get("schema_version") != SCHEMA_VERSION or \
                checkpoint.get("code") != 0:
            return False
        if bool(checkpoint.get("emulated")) != bool(self.workflow.is_portable_emulation()):
            return False
        working_dir = checkpoint.get("working_dir")
        if not isinstance(working_dir, str) or not Path(working_dir).is_dir():
            return False
        if checkpoint.get("spec_sha256") != self.spec_digest(self._effective_spec()):
            return False
        identity = meta_runner.workflow_identity(self.workflow_location)
        if identity["sha256"] is None or identity["sha256"] != checkpoint.get("workflow_sha256"):
            # A remote workflow cannot be re-verified locally, so it always runs again.
            return False
        recorded_inputs = {item.get("location"): item.get("sha256") for item in checkpoint.get("inputs", [])}
        try:
            for name, descriptor in self.inputs.items():
                if descriptor["type"] == "value":
                    continue
                source = self._source(descriptor["path"])
                if not source.exists() or recorded_inputs.get(descriptor["path"]) != sha256_path(source):
                    return False
        except MetaTaskError:
            return False
        for output in checkpoint.get("outputs", []):
            target = Path(working_dir, output["path"])
            if not target.exists() or sha256_path(target) != output.get("sha256"):
                return False
        self.working_dir, self.fair_checkpoint_reused = working_dir, True
        return True

    # -- execution ---------------------------------------------------------

    def execute(self) -> None:
        if self.reuse_checkpoint():
            self._release_references()
            return
        emulate = bool(self.workflow.is_portable_emulation())
        spec = self._effective_spec()
        self.create_working_dir()
        checkpoint = self.initialize_checkpoint()
        checkpoint.update({"schema_version": SCHEMA_VERSION, "task_type": "meta", "engine": self.engine,
                           "spec_sha256": self.spec_digest(spec), "emulated": emulate})
        metadata_dir = Path(self.working_dir, ".dagon")
        metadata_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.joinpath("meta_spec.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n",
                                                           encoding="utf-8")
        self.workflow._fire_event("on_task_staging_in_start", self)
        try:
            bindings = self._stage_inputs()
        except MetaTaskError as exc:
            self.failure_phase = exc.phase
            raise
        except OSError as exc:
            self.failure_phase = "staging"
            raise MetaStagingError("meta-task inputs could not be staged: %s" % exc) from exc
        finally:
            self.workflow._fire_event("on_task_staging_in_end", self)
        metadata_dir.joinpath("meta_bindings.json").write_text(json.dumps(bindings, indent=2, sort_keys=True) + "\n",
                                                               encoding="utf-8")
        self.workflow._fire_event("on_task_execute_start", self)
        if not self.workflow.dry:
            try:
                self.meta_result = meta_runner.run(spec, self.working_dir, bindings, emulate=emulate)
            except MetaTaskError as exc:
                self.failure_phase = exc.phase
                checkpoint["code"] = getattr(exc, "returncode", None) or 1
                raise
            checkpoint.update({"code": 0, "workflow_sha256": self.meta_result["workflow"]["sha256"],
                               "inputs": self.meta_result["inputs"], "outputs": self.meta_result["outputs"]})
        self.workflow._fire_event("on_task_staging_out_start", self)
        try:
            self._release_references()
        finally:
            self.workflow._fire_event("on_task_staging_out_end", self)

    def get_execution_metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {"model": "meta", "engine": self.engine, "workflow": self.workflow_location}
        if self.meta_result:
            result = self.meta_result
            metadata.update({"adapter": result["adapter"], "engine_version": result.get("engine_version"),
                             "emulated": result.get("emulated", False), "workflow_sha256": result["workflow"]["sha256"],
                             "duration_seconds": result.get("duration_seconds"), "outputs": result["outputs"],
                             "engine_metadata": result.get("engine_metadata", {})})
        return metadata
