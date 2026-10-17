"""Run the current checkout with isolated, persistent test data and a separate app ID."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ollama_gui.app import Application, Window, Preferences, Gio, GLib
from ollama_gui.branding import APP_ID
from ollama_gui.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, help="Use a specific isolated test folder.")
    parser.add_argument("--setup", action="store_true", help="Start the complete first-run setup in a fresh test folder.")
    args = parser.parse_args()
    root = args.data_dir
    if root is None:
        root = (Path(tempfile.mkdtemp(prefix="lumen-setup-test-")) if args.setup else
                Path(tempfile.gettempdir()) / f"lumen-personalization-test-{os.getuid()}")
    if args.setup and root.exists() and any(root.iterdir()):
        parser.error("Setup testing requires an empty --data-dir. Omit --data-dir to get a fresh folder automatically.")
    store = Store(root)
    if not args.setup and not (store.root / "settings.json").exists():
        # Copy only the connection and selected model, never chats, keys or profile.
        sources = [Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ollama-gnome/settings.json",
                   Path.home() / f".var/app/{APP_ID}/data/ollama-gnome/settings.json"]
        for source in sources:
            try:
                saved = json.loads(source.read_text())
            except (OSError, ValueError):
                continue
            for key in ("url", "model"):
                if isinstance(saved.get(key), str):
                    store.settings[key] = saved[key]
            break
        store.settings.update(setup_completed=True, tools_enabled=False, auto_titles=False)
        store.save()
    label = "Setup" if args.setup else "Personalization"
    print(f"{label} test data: {store.root.resolve()}", flush=True)
    print("This separate test app runs the checkout. Installed Flatpaks and their data are unchanged.", flush=True)
    def activate(application):
        window = application.get_active_window()
        if window is None:
            window = Window(application, store)
            window.set_title(f"Lumen — {label} Test")
            window.present()
            if not args.setup:
                preferences = Preferences(window)
                preferences.set_visible_page(preferences.personalization)
                window.test_preferences = preferences
                preferences.present(window)
        else:
            window.present()
    # Use an Application subclass so the normal activate handler does not open
    # another window against the real Store.
    class TestApplication(Application):
        def do_activate(self):
            activate(self)
    app = TestApplication()
    app.set_application_id(APP_ID + f".{label}Test")
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    GLib.set_application_name(f"Lumen {label} Test")
    app.run([])


if __name__ == "__main__":
    main()
