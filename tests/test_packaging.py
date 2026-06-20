import configparser
import unittest


class PackagingTests(unittest.TestCase):
    def test_optional_integrations_are_declared_as_extras(self):
        parser = configparser.ConfigParser()
        parser.read("setup.cfg")

        install_requires = "\n".join(
            value for _, value in parser.items("options")
        )
        extras = parser["options.extras_require"]

        self.assertIn("docker", extras)
        self.assertIn("cloud", extras)
        self.assertIn("globus", extras)
        self.assertIn("api", extras)
        self.assertNotIn("docker==7.1.0", install_requires)
        self.assertNotIn("globus_sdk==3.28.0", install_requires)
        self.assertNotIn("apache-libcloud==3.8.0", install_requires)
        self.assertIn("docker==7.1.0", extras["docker"])
        self.assertIn("globus_sdk==3.28.0", extras["globus"])
        self.assertIn("flask==2.2.2", extras["api"])


if __name__ == "__main__":
    unittest.main()
