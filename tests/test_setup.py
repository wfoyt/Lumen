import json
from pathlib import Path
import tempfile
import unittest

from ollama_gui.storage import DEFAULT_SETTINGS, Store


class FirstRunTests(unittest.TestCase):
    def test_new_installation_requires_setup_without_changing_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            self.assertTrue(store.needs_setup)
            self.assertEqual(store.settings, DEFAULT_SETTINGS)
            self.assertFalse((Path(root) / "settings.json").exists())

    def test_completed_setup_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings["setup_completed"] = True
            store.save()
            self.assertFalse(Store(root).needs_setup)

    def test_legacy_settings_and_history_skip_setup(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.save()
            self.assertFalse(Store(root).needs_setup)
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "chats.json").write_text(json.dumps([{"id": "legacy", "messages": []}]))
            self.assertFalse(Store(root).needs_setup)

    def test_incomplete_marker_does_not_become_completed_on_save(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings["setup_completed"] = False
            store.save()
            self.assertTrue(Store(root).needs_setup)

    def test_reset_keeps_existing_installation_out_of_setup(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings["setup_completed"] = True
            store.save()
            store.reset_all()
            self.assertFalse(Store(root).needs_setup)


if __name__ == "__main__":
    unittest.main()
