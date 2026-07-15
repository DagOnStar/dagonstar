import importlib.util
import sys
import unittest
from pathlib import Path


EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "dynostore"
sys.path.insert(0, str(EXAMPLE_DIR))

from dynostore_commands import download_catalog, upload_catalog
from dynostore_workflow import build_workflow


class DynoStoreExampleTests(unittest.TestCase):
    def test_commands_use_runtime_server_and_quote_arguments(self):
        upload = upload_catalog("input file; false", "catalog; false")
        download = download_catalog("catalog; false", "output dir")

        self.assertIn('"$DYNOSTORE_SERVER"', upload)
        self.assertNotIn("https://", upload)
        self.assertIn("'input file; false'", upload)
        self.assertIn("'--catalog=catalog; false'", upload)
        self.assertIn("'catalog; false'", download)
        self.assertIn("'output dir'", download)

    def test_workflow_has_explicit_producer_consumer_edge(self):
        workflow = build_workflow("/tmp/dagon-dynostore-test", "test-catalog")
        producer, consumer = workflow.tasks

        self.assertEqual([producer], consumer.prevs)
        self.assertEqual([consumer], producer.nexts)
        self.assertNotIn("workflow://", consumer.command)


if __name__ == "__main__":
    unittest.main()
