#!/usr/bin/env python3
"""Validate the canonical tutorial structure and local Markdown links."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "docs" / "tutorial"
INDEX = TUTORIAL / "README.md"
REQUIRED = [
    "Learning outcomes", "Prerequisites", "Scientific scenario", "Conceptual model",
    "Build the workflow", "Run the example", "Expected result", "Verify",
    "What DAGonStar did", "Controlled experiment", "Common problems and diagnosis",
    "Scientific practice", "Summary", "Next lesson",
]
CANONICAL = re.findall(r"\[[0-9]{2}\]\((lesson_[^)]+\.md)\)", INDEX.read_text(encoding="utf-8"))
RETIRED = re.compile(
    r"lesson_(?:01_local_workflow|02_explicit_dependencies|03_data_dependencies|"
    r"04_scratch_and_launchers|05_cycle_detection|06_checkpointing|07_data_staging|"
    r"08_docker_tasks|09_remote_and_slurm|10_meta_workflows|11_asynchronous_launch|"
    r"12_llm_tasks|13_web_tasks|14_native_tasks|15_fair_by_design|16_using_dynostore|"
    r"17_cwl_interoperability|(?:1[89]|2[0-2])_faas|22_all_task_types)\.md"
)
GENERIC = (
    "explain the underlying mechanism",
    "DAGonStar constructed or inspected the graph",
    "Read the authoritative example or structural check before running it",
)


def validate():
    errors = []
    if len(CANONICAL) != 18:
        errors.append("tutorial index must list exactly Lessons 00-17")
    for number, relative in enumerate(CANONICAL):
        path = TUTORIAL / relative
        if not path.is_file():
            errors.append("missing canonical lesson: " + relative); continue
        text = path.read_text(encoding="utf-8")
        expected = "# Lesson %02d:" % number
        if not text.startswith(expected): errors.append(relative + " title does not start with " + expected)
        for heading in REQUIRED:
            if "\n## " + heading + "\n" not in text: errors.append(relative + " missing heading: " + heading)
        for label in ("**Track:**", "**Runtime:**", "**Colab:**", "**Estimated effort:**"):
            if label not in text: errors.append(relative + " missing metadata: " + label)
        for phrase in GENERIC:
            if phrase in text: errors.append(relative + " contains generic boilerplate: " + phrase)
        if text.count("lesson_00_set_up_dagonstar") > (1 if number else 0):
            errors.append(relative + " repeats the setup prerequisite")
    for path in TUTORIAL.glob("lesson_*.md"):
        if RETIRED.fullmatch(path.name): errors.append("retired parallel lesson remains: " + path.name)
    teaching_files = [ROOT / "README.md"]
    teaching_files += list((ROOT / "docs").rglob("*.md"))
    teaching_files += list((ROOT / "examples").rglob("README.md"))
    for path in teaching_files:
        for match in RETIRED.finditer(path.read_text(encoding="utf-8")):
            errors.append(
                "%s references retired lesson: %s"
                % (path.relative_to(ROOT), match.group(0))
            )
    checked = [INDEX] + [TUTORIAL / item for item in CANONICAL]
    checked += list((TUTORIAL / "resources").glob("*.md")) + list((TUTORIAL / "integrations").glob("*.md"))
    for path in checked:
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            if target.startswith(("http:", "https:", "#", "mailto:")): continue
            clean = target.split("#", 1)[0]
            if clean and not (path.parent / clean).resolve().exists():
                errors.append("%s has broken link: %s" % (path.relative_to(ROOT), target))
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        print("\n".join(failures), file=sys.stderr); raise SystemExit(1)
    print("Validated 18 canonical lessons and internal tutorial links.")
