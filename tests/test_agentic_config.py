"""dagon.ini profile resolution for agentic tasks (no provider calls, no credentials)."""
import configparser
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dagon.agentic import AgenticConfigurationError
from dagon.agentic.config import DEFAULT_BUDGETS, resolve_profile
from dagon.agentic.providers import build_adapter
from dagon.agentic.registry import default_registry
from dagon.config import read_config
from tests.agentic_fixtures import FIXTURE_INI, agent_sections, agent_task, agent_workflow, add_producer

ROOT = Path(__file__).resolve().parents[1]


class AgenticConfigurationTests(unittest.TestCase):
    def config(self, **changes):
        sections = agent_sections(endpoint="http://127.0.0.1:9")
        for section, values in changes.items():
            name = section.replace("__", ".")
            if values is None:
                sections.pop(name, None)
            else:
                sections.setdefault(name, {}).update(values)
        return sections

    def test_profile_resolves_with_budgets_tools_and_stable_digest(self):
        profile = resolve_profile(self.config(), "quality-local")
        self.assertEqual(profile.implementation, "mock")
        self.assertEqual(profile.tools, ("inspect_records", "repair_records"))
        self.assertEqual(profile.guardrails, ("preserve_record_ids",))
        self.assertEqual(profile.budgets["max_steps"], 8)
        self.assertEqual(profile.budgets["max_attempts"], 8)
        self.assertEqual(profile.digest, resolve_profile(self.config(), "quality-local").digest)
        self.assertNotIn("endpoint", str(profile.public()))

    def test_documented_defaults_apply_to_omitted_budgets(self):
        profile = resolve_profile(self.config(), "reason-only")
        for key, value in DEFAULT_BUDGETS.items():
            self.assertEqual(profile.budgets[key], value)
        self.assertEqual(profile.tools, ())

    def test_configparser_and_read_config_forms_are_equivalent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "dagon.ini")
            path.write_text(FIXTURE_INI, encoding="utf-8")
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(str(path))
            self.assertEqual(resolve_profile(parser, "quality-local").digest,
                             resolve_profile(read_config(str(path)), "quality-local").digest)

    def test_missing_and_unknown_configuration_is_reported(self):
        cases = {
            "missing profile": (self.config(**{"agent__quality-local": None}), "is not configured"),
            "missing provider": (self.config(agent_provider__fixture=None), "agent provider"),
            "unknown profile key": (self.config(**{"agent__quality-local": {"endpoint": "x"}}), "unknown key"),
            "unknown provider key": (self.config(agent_provider__fixture={"module": "os"}), "unknown key"),
            "unregistered implementation": (self.config(agent_provider__fixture={"implementation": "os.system"}),
                                            "not a registered adapter"),
            "missing max_steps": (self.config(**{"agent__quality-local": {"max_steps": ""}}), "max_steps"),
            "infinite timeout": (self.config(**{"agent__quality-local": {"timeout_seconds": "inf"}}), "finite"),
            "nan budget": (self.config(**{"agent__quality-local": {"max_tokens": "nan"}}), "finite"),
            "fractional steps": (self.config(**{"agent__quality-local": {"max_steps": "2.5"}}), "integer"),
            "unknown tool": (self.config(**{"agent__quality-local": {"tools": "shell"}}), "unknown tool"),
            "unknown guardrail": (self.config(**{"agent__quality-local": {"guardrails": "nope"}}), "unknown guardrail"),
            "bad strategy": (self.config(**{"agent__quality-local": {"strategy": "unbounded"}}), "strategy"),
            "scenario on builtin": (self.config(agent_provider__builtin={"scenario": "malformed"}), "scenario"),
        }
        for label, (config, message) in cases.items():
            with self.subTest(label):
                name = "quality-live" if label == "scenario on builtin" else "quality-local"
                with self.assertRaisesRegex(AgenticConfigurationError, message):
                    resolve_profile(config, name)

    def test_builtin_adapter_requires_a_configured_llm_provider(self):
        with self.assertRaisesRegex(AgenticConfigurationError, "requires llm_provider"):
            resolve_profile(self.config(**{"agent__quality-live": {"llm_provider": ""}}), "quality-live")
        with self.assertRaisesRegex(AgenticConfigurationError, r"\[llm.loopback\]"):
            resolve_profile(self.config(llm__loopback=None), "quality-live")
        with self.assertRaisesRegex(AgenticConfigurationError, "endpoint"):
            resolve_profile(self.config(llm__loopback={"endpoint": "ftp://x"}), "quality-live")
        with self.assertRaisesRegex(AgenticConfigurationError, "api_key_env"):
            resolve_profile(self.config(llm__loopback={"api_key_env": ""}), "quality-live")

    def test_profile_is_the_maximum_authority(self):
        config = self.config()
        self.assertEqual(resolve_profile(config, "quality-local", ["inspect_records"]).tools, ("inspect_records",))
        self.assertEqual(resolve_profile(config, "quality-local", []).tools, ())
        with self.assertRaisesRegex(AgenticConfigurationError, "not permitted"):
            resolve_profile(config, "reason-only", ["inspect_records"])
        narrowed = resolve_profile(config, "quality-local", task_budgets={"max_steps": 3})
        self.assertEqual(narrowed.budgets["max_steps"], 3)
        with self.assertRaisesRegex(AgenticConfigurationError, "exceeds"):
            resolve_profile(config, "quality-local", task_budgets={"max_steps": 9})
        profile = resolve_profile(config, "quality-local", task_guardrails=["non_empty_result"])
        self.assertEqual(profile.guardrails, ("non_empty_result", "preserve_record_ids"))

    def test_secrets_are_resolved_only_at_invocation(self):
        config = self.config()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DAGON_TEST_AGENT_KEY", None)
            profile = resolve_profile(config, "quality-live")
            self.assertNotIn("DAGON_TEST_AGENT_KEY_VALUE", str(profile.normalized()))
            with self.assertRaisesRegex(AgenticConfigurationError, "no credential"):
                build_adapter(profile, config, default_registry())
            adapter, _, emulation = build_adapter(profile, config, default_registry(), portable_emulation=True)
            self.addCleanup(adapter.close)
            self.assertEqual(adapter.id, "mock")
            self.assertEqual(emulation["configured_implementation"], "builtin")
        with mock.patch.dict(os.environ, {"DAGON_TEST_AGENT_KEY": "key-value-1234"}):
            adapter, secrets, _ = build_adapter(profile, config, default_registry())
            self.addCleanup(adapter.close)
            self.assertEqual(adapter.id, "builtin")
            self.assertEqual(secrets, ["key-value-1234"])

    def test_inline_api_keys_are_refused_without_echoing_them(self):
        from dagon.agentic.config import resolve_api_key
        inline = "INLINE-SENTINEL-0123456789"
        for values in ({"api_key": inline}, {"api_key": inline, "api_key_env": "DAGON_TEST_AGENT_KEY"}):
            with self.subTest(sorted(values)):
                config = self.config(llm__loopback=values)
                with self.assertRaisesRegex(AgenticConfigurationError, "inline api_key") as caught:
                    resolve_profile(config, "quality-live")
                self.assertNotIn(inline, str(caught.exception))
                with self.assertRaisesRegex(AgenticConfigurationError, "inline api_key") as caught:
                    resolve_api_key(config, "loopback")
                self.assertNotIn(inline, str(caught.exception))
        # An [llm.*] section that no agent profile selects stays available to LLM tasks.
        config = self.config(**{"llm__legacy": {"endpoint": "http://127.0.0.1:9", "api_key": inline}})
        self.assertEqual(resolve_profile(config, "quality-local").name, "quality-local")

    def test_a_present_credential_is_never_sent_to_the_adapter_worker(self):
        config = self.config()
        profile = resolve_profile(config, "quality-live")
        with mock.patch.dict(os.environ, {"DAGON_TEST_AGENT_KEY": "key-value-5678"}), \
                mock.patch("dagon.agentic.sandbox.ProcessAdapter") as process_adapter:
            build_adapter(profile, config, default_registry())
        _, options = process_adapter.call_args[0][:2]
        self.assertEqual(options["api_key_env"], "DAGON_TEST_AGENT_KEY")
        self.assertNotIn("key-value-5678", repr(process_adapter.call_args))

    def test_preflight_runs_before_scratch_or_tool_calls(self):
        with tempfile.TemporaryDirectory() as scratch:
            workflow = agent_workflow("preflight", scratch)
            add_producer(workflow, scratch)
            task = agent_task(agent="not-configured")
            workflow.add_task(task)
            workflow.make_dependencies()
            with mock.patch("dagon.agentic.engine.call_in_process") as tool:
                with self.assertRaisesRegex(AgenticConfigurationError, r"\[agent.not-configured\]"):
                    task.execute()
            tool.assert_not_called()
            self.assertIsNone(task.working_dir)
            self.assertNotIn("preflight.quality_control", workflow.checkpoints)

    def test_sample_configuration_defines_working_agent_profiles(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(str(ROOT / "dagon.ini.sample"))
        self.assertEqual(resolve_profile(parser, "quality-local").implementation, "mock")
        self.assertEqual(resolve_profile(parser, "quality-live").implementation, "builtin")
        import re
        self.assertIsNone(re.search(r"^api_key\s*=", (ROOT / "dagon.ini.sample").read_text(encoding="utf-8"), re.M))


if __name__ == "__main__":
    unittest.main()
