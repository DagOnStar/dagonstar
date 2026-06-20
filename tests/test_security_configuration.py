import unittest
from unittest import mock

from dagon.communication.data_transfer import SKYCDS


class SecurityConfigurationTests(unittest.TestCase):
    def test_skycds_rejects_missing_runtime_configuration(self):
        skycds = SKYCDS()

        with mock.patch.object(skycds, "CLIENT_TOKEN", ""), \
                mock.patch.object(skycds, "CATALOG_TOKEN", ""), \
                mock.patch.object(skycds, "API_TOKEN", ""), \
                mock.patch.object(skycds, "IP_SKYCDS", ""):
            with self.assertRaisesRegex(ValueError, "DAGON_SKYCDS_CLIENT_TOKEN"):
                skycds._validate_configuration()

    def test_skycds_accepts_complete_runtime_configuration(self):
        skycds = SKYCDS()

        with mock.patch.object(skycds, "CLIENT_TOKEN", "client"), \
                mock.patch.object(skycds, "CATALOG_TOKEN", "catalog"), \
                mock.patch.object(skycds, "API_TOKEN", "api"), \
                mock.patch.object(skycds, "IP_SKYCDS", "127.0.0.1"):
            skycds._validate_configuration()


if __name__ == "__main__":
    unittest.main()
