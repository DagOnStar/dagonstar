import unittest

from dagon.stager.base import Stager, StagerMover, DataMover

from tests.helpers import minimal_config


class StagingTests(unittest.TestCase):
    def test_generate_command_quotes_paths_and_configuration_values(self):
        cfg = minimal_config()
        cfg["batch"]["threads"] = "2 workers"
        cfg["slurm"]["partition"] = "debug partition"
        stager = Stager(DataMover.COPY, StagerMover.NORMAL, cfg)

        script = stager.generate_command(
            "/tmp/source dir/output file.txt",
            "/tmp/destination dir",
            'cp -r "$file" "$dst"',
            StagerMover.NORMAL.value,
        )

        self.assertIn("src='/tmp/source dir/output file.txt'", script)
        self.assertIn("dst='/tmp/destination dir'", script)
        self.assertIn("jobs='2 workers'", script)
        self.assertIn("partition='debug partition'", script)
        self.assertIn('cmd="cp -r \\"$file\\" \\"$dst\\""', script)

    def test_generate_command_supports_all_staging_modes(self):
        stager = Stager(DataMover.COPY, StagerMover.NORMAL, minimal_config())

        for mode in StagerMover:
            with self.subTest(mode=mode):
                script = stager.generate_command("/tmp/source", "/tmp/destination", "cp", mode.value)
                self.assertIn("src=/tmp/source", script)
                self.assertIn("job_ids=()", script)


if __name__ == "__main__":
    unittest.main()
