import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "cwl", "export_workflow.py")
COMMITTED_CWL = os.path.join(ROOT, "examples", "cwl", "interoperable-workflow.cwl")


class CWLExampleTests(unittest.TestCase):
    def test_example_regenerates_committed_interoperable_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            generated = os.path.join(directory, "interoperable-workflow.cwl")
            subprocess.run(
                [sys.executable, EXAMPLE, "--output", generated],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            with open(generated, encoding="utf-8") as stream:
                generated_text = stream.read()
            with open(COMMITTED_CWL, encoding="utf-8") as stream:
                committed_text = stream.read()

        self.assertEqual(generated_text, committed_text)
        document = json.loads(committed_text)
        simulation_inputs = document["steps"]["run_simulation"]["in"]
        self.assertEqual(
            set(simulation_inputs.values()),
            {
                "collect_observations/completed",
                "prepare_parameters/completed",
            },
        )
        self.assertEqual(
            document["outputs"]["run_simulation_completed"]["outputSource"],
            "run_simulation/completed",
        )

    @unittest.skipUnless(shutil.which("cwltool"), "cwltool is not installed")
    def test_committed_workflow_validates_with_cwltool(self):
        subprocess.run(
            ["cwltool", "--validate", COMMITTED_CWL],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
