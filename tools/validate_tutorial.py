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
