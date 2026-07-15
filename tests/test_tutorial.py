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


if __name__ == "__main__":
    unittest.main()
