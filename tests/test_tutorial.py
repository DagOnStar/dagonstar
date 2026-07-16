"""Structural tests for the redesigned tutorial."""
import importlib.util
import unittest
from pathlib import Path


class TutorialValidationTests(unittest.TestCase):
    def test_canonical_tutorial(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "tools" / "validate_tutorial.py"
        spec = importlib.util.spec_from_file_location("validate_tutorial", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.validate(), [])

    def test_notebook_is_valid_json(self):
        import json
        path = Path(__file__).resolve().parents[1] / "docs/tutorial/DAGonStar_tutorial.ipynb"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["nbformat"], 4)
        markdown = "\n".join(
            "".join(cell.get("source", []))
            for cell in data["cells"]
            if cell.get("cell_type") == "markdown"
        )
        headings = [line for line in markdown.splitlines() if line.startswith("## Lesson ")]
        self.assertEqual(len(headings), 18)
        for number, heading in enumerate(headings):
            self.assertTrue(heading.startswith("## Lesson %02d " % number), heading)
        lesson_cells = [
            index
            for index, cell in enumerate(data["cells"])
            if cell.get("cell_type") == "markdown"
            and "".join(cell.get("source", [])).startswith("## Lesson ")
        ]
        for position, start in enumerate(lesson_cells):
            stop = (
                lesson_cells[position + 1]
                if position + 1 < len(lesson_cells)
                else len(data["cells"])
            )
            self.assertTrue(
                any(
                    cell.get("cell_type") == "code"
                    for cell in data["cells"][start + 1:stop]
                ),
                "Lesson %02d has no executable verification cell" % position,
            )
        code_text = "\n".join(
            "".join(cell.get("source", []))
            for cell in data["cells"]
            if cell.get("cell_type") == "code"
        )
        self.assertNotIn("%run ", code_text)
        self.assertNotIn("!python", code_text)
        self.assertIn("sys.executable", code_text)


if __name__ == "__main__":
    unittest.main()
