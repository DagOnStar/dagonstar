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
        self.assertIn("kubernetes", extras)
        self.assertNotIn("docker==7.1.0", install_requires)
        self.assertNotIn("globus_sdk==3.28.0", install_requires)
        self.assertNotIn("apache-libcloud==3.8.0", install_requires)
        self.assertIn("docker==7.1.0", extras["docker"])
        self.assertIn("globus_sdk==3.28.0", extras["globus"])
        self.assertIn("flask==2.2.2", extras["api"])
        self.assertIn('kubernetes==35.0.0; python_version < "3.10"', extras["kubernetes"])
        self.assertIn('kubernetes==36.0.2; python_version >= "3.10"', extras["kubernetes"])

    def test_optional_dependencies_do_not_leak_into_base_install(self):
        parser = configparser.ConfigParser()
        parser.read("setup.cfg")

        base_requirements = {
            line.strip().lower()
            for line in parser["options"]["install_requires"].splitlines()
            if line.strip()
        }
        optional_package_names = {
            "apache-libcloud", "boto3", "docker", "flask", "flask-api",
            "globus_sdk", "werkzeug",
        }

        self.assertTrue(base_requirements.isdisjoint(optional_package_names))

    def test_all_extra_contains_each_integration_extra(self):
        parser = configparser.ConfigParser()
        parser.read("setup.cfg")
        extras = parser["options.extras_require"]
        all_requirements = set(extras["all"].splitlines())

        for extra_name in ("docker", "cloud", "globus", "api", "kubernetes"):
            with self.subTest(extra=extra_name):
                self.assertLessEqual(
                    set(extras[extra_name].splitlines()), all_requirements
                )

    def test_agentic_package_and_runner_are_registered(self):
        parser = configparser.ConfigParser()
        parser.read("setup.cfg")
        self.assertIn("dagon.agentic", parser["options"]["packages"].split())
        self.assertIn("dagon-agent-runner = dagon.agentic.runner:main",
                      parser["options.entry_points"]["console_scripts"])

    def test_agentic_base_import_needs_no_provider_sdk(self):
        import subprocess
        import sys
        code = ("import sys, dagon.agentic, dagon.agentic.task, dagon.agentic.runner; "
                "bad = [m for m in ('openai', 'anthropic', 'langchain', 'boto3', 'docker', 'kubernetes') "
                "if m in sys.modules]; print(','.join(bad))")
        completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(completed.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
