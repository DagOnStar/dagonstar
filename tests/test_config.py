import os
import tempfile
import unittest

from dagon.config import read_config


class ConfigTests(unittest.TestCase):
    def test_read_config_returns_nested_dictionary(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as config_file:
            config_file.write("[batch]\nscratch_dir_base=/tmp/dagon\nthreads=2\n")
            path = config_file.name

        try:
            cfg = read_config(path)
        finally:
            os.unlink(path)

        self.assertEqual(cfg["batch"]["scratch_dir_base"], "/tmp/dagon")
        self.assertEqual(cfg["batch"]["threads"], "2")

    def test_read_config_returns_section_or_none(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as config_file:
            config_file.write("[dagon_service]\nuse=False\n")
            path = config_file.name

        try:
            self.assertEqual(read_config(path, "dagon_service"), {"use": "False"})
            self.assertIsNone(read_config(path, "missing"))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
