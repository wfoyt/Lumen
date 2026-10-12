"""Check first-run navigation, persistence and adaptive New Chat placement."""
import copy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ollama_gui.app import Application, Window, Gio, Gtk, GLib
from ollama_gui.storage import DEFAULT_SETTINGS, Store, tool_servers


with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as custom_root, patch.object(Window, "refresh_models") as models, patch.object(Window, "refresh_tools") as tools, patch.object(Window, "request_title"):
    app = Application()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    windows = []
    store = Store(root)
    window = Window(app, store)
    windows.append(window)
    setup = window.setup
    window.paintable = Gtk.WidgetPaintable.new(window)
    window.present()
    loop = GLib.MainLoop()
    errors = []

    def snapshot(name):
        image = Gtk.Snapshot()
        window.paintable.snapshot(image, window.get_width(), window.get_height())
        node = image.to_node()
        assert node is not None
        window.get_renderer().render_texture(node, None).save_to_png(f"/tmp/lumen-setup-{name}.png")

    def welcome():
        assert setup.navigation.get_visible_page_tag() == "welcome"
        assert window.current is None and not store.chats
        assert not models.called and not tools.called
        for name in ("new", "preferences", "refresh", "search", "delete"):
            assert not window.lookup_action(name).get_enabled()
        window.new_chat()
        assert not store.chats
        snapshot("welcome")
        setup.start_button.emit("clicked")
        later(connection)

    def connection():
        assert setup.navigation.get_visible_page_tag() == "ollama"
        assert not setup.custom_revealer.get_visible()
        snapshot("ollama")
        setup.default_button.emit("clicked")
        later(integrations)

    def integrations():
        assert setup.navigation.get_visible_page_tag() == "tools"
        assert setup.tools_enabled.get_active() and setup.python_enabled.get_active()
        assert not setup.brave_enabled.get_active() and not setup.brave_revealer.get_visible()
        setup.python_enabled.set_active(False)
        setup.brave_enabled.set_active(True)
        assert setup.brave_revealer.get_visible()
        setup.tools_next.emit("clicked")
        assert setup.navigation.get_visible_page_tag() == "tools" and setup.key_error.get_visible()
        setup.key.set_text("test-only-key")
        assert not setup.key_error.get_visible()
        setup.tools_enabled.set_active(False)
        assert not setup.tools_revealer.get_visible() and not setup.brave_revealer.get_visible()
        setup.tools_enabled.set_active(True)
        assert setup.tools_revealer.get_visible() and setup.brave_revealer.get_visible()
        later(brave)

    def brave():
        snapshot("tools")
        assert not (Path(root) / "settings.json").exists()
        assert store.settings == DEFAULT_SETTINGS
        setup.tools_next.emit("clicked")
        later(ready)

    def ready():
        assert setup.navigation.get_visible_page_tag() == "ready"
        snapshot("ready")
        setup.navigation.pop()
        assert setup.key.get_text() == "test-only-key" and not setup.python_enabled.get_active()
        setup.tools_next.emit("clicked")
        previous = copy.deepcopy(store.settings)
        with patch.object(store, "write", side_effect=OSError("Simulated save failure")):
            setup.finish_button.emit("clicked")
        assert window.setup is setup and setup.finish_error.get_visible()
        assert store.settings == previous and not store.chats
        setup.finish_button.emit("clicked")
        assert window.setup is None
        assert store.settings["url"] == DEFAULT_SETTINGS["url"]
        assert store.settings["setup_completed"]
        assert not store.settings["python_enabled"] and store.settings["brave_enabled"]
        assert store.settings["mcpServers"]["brave-search"]["env"]["BRAVE_API_KEY"] == "test-only-key"
        assert len(store.chats) == 1 and not window.current["messages"]
        assert not Store(root).needs_setup
        assert models.call_count == tools.call_count == 1
        window.split.set_show_sidebar(False)
        later(chat)

    def chat():
        assert window.new_chat_button.get_parent() is window.chat_header_controls
        assert window.sidebar_toggle.get_next_sibling() is window.new_chat_button
        assert not window.lookup_action("new").get_enabled()
        snapshot("chat")
        for _ in range(3):
            window.split.set_show_sidebar(True)
            assert window.new_chat_button.get_parent() is window.sidebar_controls
            assert window.new_chat_button.get_next_sibling() is window.app_menu
            window.split.set_show_sidebar(False)
            assert window.sidebar_toggle.get_next_sibling() is window.new_chat_button
        window.current["messages"] = [{"role": "user", "content": "First chat"}]
        window.update_actions()
        assert window.new_chat_button.get_sensitive()
        window.new_chat_button.emit("clicked")
        assert len(store.chats) == 2 and not window.current["messages"]
        # Reopening a completed installation skips setup.
        reopened = Window(app, Store(root))
        windows.append(reopened)
        assert reopened.setup is None and reopened.current is not None
        reopened.close()
        begin_custom()

    def begin_custom():
        global window, setup
        window.close()
        # Closing midway must not turn the next launch into an existing setup.
        interrupted = Window(app, Store(custom_root))
        windows.append(interrupted)
        interrupted.setup.start_button.emit("clicked")
        interrupted.close()
        assert Store(custom_root).needs_setup
        window = Window(app, Store(custom_root))
        windows.append(window)
        setup = window.setup
        window.paintable = Gtk.WidgetPaintable.new(window)
        window.set_default_size(360, 760)
        window.present()
        setup.start_button.emit("clicked")
        setup.custom_button.emit("clicked")
        setup.url.set_text("not-a-url")
        setup.url_next.emit("clicked")
        assert setup.navigation.get_visible_page_tag() == "ollama" and setup.url_error.get_visible()
        setup.url.set_text("https://ollama.example.test:11434/")
        assert not setup.url_error.get_visible()
        later(custom)

    def custom():
        assert window.get_width() == 360
        snapshot("custom-narrow")
        setup.url_next.emit("clicked")
        assert setup.navigation.get_visible_page_tag() == "tools"
        assert setup.python_enabled.get_active() and not setup.brave_enabled.get_active()
        # All-tools-off may continue without a Brave key, retaining choices.
        setup.brave_enabled.set_active(True)
        setup.tools_enabled.set_active(False)
        setup.tools_next.emit("clicked")
        assert setup.navigation.get_visible_page_tag() == "ready"
        setup.navigation.pop()
        setup.brave_enabled.set_active(False)
        setup.tools_enabled.set_active(True)
        later(narrow_tools)

    def narrow_tools():
        snapshot("tools-narrow")
        setup.tools_next.emit("clicked")
        setup.finish_button.emit("clicked")
        saved = Store(custom_root)
        assert saved.settings["url"] == "https://ollama.example.test:11434"
        assert saved.settings["python_enabled"] and not saved.settings["brave_enabled"]
        assert set(tool_servers(saved.settings)) == {"Built-in Python"}
        assert not saved.needs_setup and len(saved.chats) == 1
        window.split.set_show_sidebar(False)
        later(narrow_chat)

    def narrow_chat():
        assert window.new_chat_button.get_parent() is window.chat_header_controls
        snapshot("chat-narrow")
        print("PASS: first-run setup, default/custom URLs, validation, tool defaults and visibility, Back navigation, delayed save, save failure, interrupted setup, persistence, and adaptive New Chat placement")
        close()

    def close():
        for item in windows:
            if not item.closed:
                item.close()
        loop.quit()

    def checked(callback):
        try:
            callback()
        except BaseException as error:
            import traceback
            traceback.print_exc()
            errors.append(error)
            close()
        return GLib.SOURCE_REMOVE

    def later(callback):
        GLib.timeout_add(500, checked, callback)

    GLib.timeout_add(600, checked, welcome)
    loop.run()
    if errors:
        raise SystemExit(1)
