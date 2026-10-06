import copy
from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from ollama_gui.instructions import DEFAULT_INSTRUCTIONS, LEGACY_INSTRUCTIONS, PREVIOUS_DEFAULT_INSTRUCTIONS, custom_instructions_enabled, system_instructions
from ollama_gui.storage import DEFAULT_SETTINGS, Store


class InstructionsTests(unittest.TestCase):
    def test_defaults_include_python_guidance_and_a_fresh_clock(self):
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        now = datetime(2026, 10, 6, 13, 14, 15, tzinfo=timezone.utc)
        local = now.astimezone()
        prompt = system_instructions(settings, now)
        self.assertIn("execute_python", prompt)
        self.assertIn("code argument", prompt)
        self.assertIn("stdout, stderr", prompt)
        self.assertIn("no network", prompt)
        self.assertNotIn("cite", prompt.lower())
        self.assertNotIn("citation", prompt.lower())
        self.assertIn("LaTeX equation rendering is enabled", prompt)
        self.assertIn(r"\frac", prompt)
        self.assertIn(local.strftime("%Y-%m-%d %H:%M:%S %Z"), prompt)
        self.assertIn(local.strftime("%z"), prompt)
        self.assertNotEqual(prompt, system_instructions(settings, now + timedelta(minutes=1)))
        self.assertEqual(settings, DEFAULT_SETTINGS)

    def test_equation_instructions_follow_the_toggle_including_custom_prompts(self):
        for cfg in ({}, {"system": "Be brief.", "custom_system_enabled": True}):
            self.assertIn(r"\( ... \)", system_instructions(cfg))
            cfg["latex_enabled"] = False
            prompt = system_instructions(cfg)
            self.assertNotIn("LaTeX", prompt)
            self.assertNotIn(r"\frac", prompt)
            self.assertNotIn("citation", prompt.lower())

    def test_legacy_defaults_upgrade_and_existing_custom_instructions_survive(self):
        settings = {"system": LEGACY_INSTRUCTIONS}
        self.assertFalse(custom_instructions_enabled(settings))
        self.assertIn(DEFAULT_INSTRUCTIONS, system_instructions(settings))
        settings["system"] = "Answer in Spanish."
        self.assertTrue(custom_instructions_enabled(settings))
        self.assertTrue(system_instructions(settings).startswith("Answer in Spanish."))
        settings["custom_system_enabled"] = False
        self.assertTrue(system_instructions(settings).startswith(DEFAULT_INSTRUCTIONS))
        self.assertEqual(settings["system"], "Answer in Spanish.")

    def test_old_saved_defaults_do_not_reintroduce_citations_or_disabled_latex(self):
        for old in (LEGACY_INSTRUCTIONS, PREVIOUS_DEFAULT_INSTRUCTIONS):
            for custom in (True, False):
                prompt = system_instructions({"system": old, "custom_system_enabled": custom, "latex_enabled": False})
                self.assertNotIn("cite", prompt.lower())
                self.assertNotIn("latex", prompt.lower())
                self.assertIn("execute_python", prompt)
        prompt = system_instructions({"system": "Use LaTeX equations and cite everything.", "custom_system_enabled": False, "latex_enabled": False})
        self.assertNotIn("cite", prompt.lower())
        self.assertNotIn("latex", prompt.lower())

    def test_custom_preferences_roundtrip_and_reset(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings.update(system="Be brief.", custom_system_enabled=True, custom_mcp_enabled=True)
            store.save()
            reloaded = Store(root)
            self.assertTrue(custom_instructions_enabled(reloaded.settings))
            self.assertTrue(reloaded.settings["custom_mcp_enabled"])
            self.assertTrue(system_instructions(reloaded.settings).startswith("Be brief."))
            reloaded.reset_all()
            self.assertFalse(custom_instructions_enabled(reloaded.settings))
            self.assertFalse(reloaded.settings["custom_mcp_enabled"])
