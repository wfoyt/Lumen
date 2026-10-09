"""Render an isolated native UI preview to /tmp for layout inspection."""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from io import BytesIO
from PIL import Image
from ollama_gui.app import Application, Window, Preferences, Adw, GLib, Gtk, Gio
from ollama_gui.storage import Store
from ollama_gui.attachments import image_attachment, user_message

with tempfile.TemporaryDirectory() as root:
    app = Application()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    store = Store(root)
    store.chats = [{"id": "preview", "title": "Markdown preview", "messages": [{"role": "user", "content": "Show a formatted reply"}, {"role": "assistant", "content": "## Latest Releases\n\n**Stable releases** include:\n\n- **Mainline:** release information\n- **Long-term:** support information\n\nRead the [source](https://example.com) for details. Use `uname -r` to inspect your system.\n\n```bash\nuname -r\n```\n\n| Release | Status |\n|---|---|\n| Mainline | Stable |\n| Long-term | Supported |\n\n> Check the source for current release details."}]}]
    window = Window(app, store)
    window.cancel_titles()
    window.current["title_source"] = "manual"
    window.preview_paintable = Gtk.WidgetPaintable.new(window)
    window.present()
    loop = GLib.MainLoop()
    failures = []
    responsive = "--responsive" in sys.argv
    layout = "--layout" in sys.argv
    features = "--features" in sys.argv
    tools_layout = "--tools" in sys.argv
    def save_snapshot(path):
        snapshot = Gtk.Snapshot()
        window.preview_paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        if node is None:
            print(f"Waiting for native frame ({window.get_width()} × {window.get_height()}, mapped={window.get_mapped()})")
            return False
        texture = window.get_renderer().render_texture(node, None)
        texture.save_to_png(path)
        print(f"Saved {path} ({window.get_width()} × {window.get_height()}, model selector {window.models.get_width()} px)")
        return True

    def capture():
        try:
            save_snapshot("/tmp/ollama-ui-preview.png")
        except BaseException as exc:
            print(type(exc).__name__, exc)
            failures.append(True)
        finally:
            window.worker.close()
            window.destroy()
            loop.quit()
    def prepare_responsive():
        window.models.set_model(Gtk.StringList.new(["hf.co/Example/Very-Long-Model-Name-That-Must-Shrink-With-The-Window:" + "Long-Quantization-Name-" * 5]))
        window.render_chat()
        preview = window.tool_card("Brave Search", "\n".join(f"Search result {i}: https://example.com/source/{i}" for i in range(100)))
        window.activity_box.get_last_child().set_expanded(True)
        window.preview_tool = preview
        def wide():
            save_snapshot("/tmp/ollama-wide-preview.png")
            window.set_default_size(600, 700)
            window.split.set_show_sidebar(False)
            GLib.timeout_add(1000, checked, narrow)
        def narrow():
            if not save_snapshot("/tmp/ollama-narrow-preview.png"):
                GLib.timeout_add(200, checked, narrow)
                return
            window.preview_dialog = window.preview_tool.open_full()
            GLib.timeout_add(1000, checked, dialog)
        def dialog():
            if not save_snapshot("/tmp/ollama-tool-dialog-preview.png"):
                GLib.timeout_add(200, checked, dialog)
                return
            window.preview_dialog.close()
            window.worker.close()
            window.destroy()
            loop.quit()
        GLib.timeout_add(400, checked, wide)

    def prepare_layout():
        window.models.set_model(Gtk.StringList.new(["hf.co/Example/Qwen-Very-Long-Model-Name-That-Must-Shrink-With-The-Window:Q4_K_M"] ))
        code_source = "\n".join(["# A friendly Python example", "", "def greet(name):", '    return f"Hello, {name}!"', ""] + [f'print(greet("Visitor {i}"))' for i in range(24)] + ["", "# " + "A long comment that wraps within the code block. " * 5])
        window.current["title"] = "A simple Python program"
        window.current["messages"] = [{"role": "assistant", "content": f"## Python example\n\nHere is a program you can run in your terminal.\n\n```python\n{code_source}\n```\n\n**Next step:** save this as `hello.py` and run it with Python."}]
        window.store.chats.append({"id": "other-preview", "title": "Learn the basics of Python", "messages": [{"role": "user", "content": "Tell me about Python"}]})
        window.render_sidebar()
        window.render_chat()
        markdown = window.messages.get_first_child().get_last_child()
        window.preview_code = markdown.get_first_child().get_next_sibling().get_next_sibling()
        if "--hover" in sys.argv:
            window.models.get_first_child().set_state_flags(Gtk.StateFlags.PRELIGHT, False)
            window.plus.get_first_child().set_state_flags(Gtk.StateFlags.PRELIGHT, False)
        def wide():
            window.scroll.get_vadjustment().set_value(0)
            save_snapshot("/tmp/ollama-layout-wide.png")
            window.preview_code.toggle_expanded()
            GLib.timeout_add(300, checked, expanded)
        def expanded():
            window.scroll.get_vadjustment().set_value(window.scroll.get_vadjustment().get_upper())
            GLib.timeout_add(100, checked, expanded_capture)
        def expanded_capture():
            save_snapshot("/tmp/ollama-code-expanded.png")
            window.preview_code.toggle_expanded()
            window.set_default_size(600, 700)
            window.split.set_show_sidebar(False)
            GLib.timeout_add(700, checked, narrow)
        def narrow():
            window.scroll.get_vadjustment().set_value(0)
            GLib.timeout_add(100, checked, narrow_capture)
        def narrow_capture():
            save_snapshot("/tmp/ollama-layout-narrow.png")
            window.preview_preferences = Preferences(window)
            window.preview_preferences.present(window)
            GLib.timeout_add(500, checked, preferences)
        def preferences():
            save_snapshot("/tmp/ollama-preferences-preview.png")
            ancestor = window.preview_preferences.reset_button.get_parent()
            while ancestor and not isinstance(ancestor, Gtk.ScrolledWindow):
                ancestor = ancestor.get_parent()
            if ancestor:
                ancestor.get_vadjustment().set_value(ancestor.get_vadjustment().get_upper())
            GLib.timeout_add(250, checked, preferences_reset)
        def preferences_reset():
            save_snapshot("/tmp/ollama-preferences-reset.png")
            window.preview_preferences.close()
            GLib.timeout_add(400, checked, new_chat)
        def new_chat():
            window.new_chat()
            GLib.timeout_add(70, checked, animation)
        def animation():
            print(f"New chat native transition running: {window.stack.get_transition_running()}")
            save_snapshot("/tmp/ollama-new-chat-transition.png")
            window.worker.close()
            window.destroy()
            loop.quit()
        GLib.timeout_add(400, checked, wide)

    def prepare_features():
        image = BytesIO()
        Image.new("RGB", (800, 450), "#1c71d8").save(image, format="PNG")
        picture = image_attachment(image.getvalue(), "example.png")
        window.models.set_model(Gtk.StringList.new(["hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M", "qwen3:8b"]))
        window.current["messages"] = [user_message("Help me calculate with Python", [picture]), {"role": "assistant", "content": "## Python calculations\n\n```python\n# Calculate a circle's area\nimport math\nradius = 5\narea = math.pi * radius ** 2\nprint(f'Area: {area:.2f}')\n```\n\nThe area is approximately **78.54** square units."}]
        window.attachments = [picture]
        window.current["title"] = "Polynomial Roots and Radical Equations with Python"
        window.store.chats.append({"id": "legacy-title-preview", "title": "Solve for all real \\(x\\):\n\\[\n\\sqrt{x+6}+\\sqrt{10}\n", "title_source": "manual", "messages": [{"role": "user", "content": "A legacy multiline question"}]})
        window.render_sidebar()
        window.render_chat()
        window.render_attachments()
        # Reproduce hovering the old wide grid cell without moving the pointer.
        window.attachment_chips.get_child_at_index(0).set_state_flags(Gtk.StateFlags.PRELIGHT, False)
        def main():
            title = window.chat_list.get_first_child().title_label
            layout_copy = title.get_layout().copy()
            from gi.repository import Pango
            layout_copy.set_ellipsize(Pango.EllipsizeMode.NONE)
            layout_copy.set_width(-1)
            assert title.get_single_line_mode() and "\n" not in title.get_text()
            title_snapshot = Gtk.Snapshot()
            title.do_snapshot(title_snapshot)
            title_node = title_snapshot.to_node()
            assert layout_copy.get_pixel_size()[0] > title.get_width()
            assert "linear-gradient" in title_node.serialize().get_data().decode()
            thumbnails = window.messages.get_first_child().get_first_child()
            button = thumbnails.get_first_child() if isinstance(thumbnails, Adw.WrapBox) else thumbnails.get_child_at_index(0).get_child()
            picture_widget = button.get_child().get_child()
            print("Sent image:", picture_widget.get_paintable().get_intrinsic_width(), picture_widget.get_paintable().get_intrinsic_height(), picture_widget.measure(Gtk.Orientation.HORIZONTAL, -1), picture_widget.get_width(), picture_widget.get_height())
            save_snapshot("/tmp/ollama-features-preview.png")
            window.models.popup()
            window.model_popup_paintable = Gtk.WidgetPaintable.new(window.models.get_popover())
            GLib.timeout_add(350, checked, models)
        def models():
            popup = window.models.get_popover()
            print("Model popup:", popup.get_visible(), popup.get_mapped(), popup.get_width(), popup.get_height())
            snapshot = Gtk.Snapshot()
            window.model_popup_paintable.snapshot(snapshot, popup.get_width(), popup.get_height())
            node = snapshot.to_node()
            if node:
                popup.get_native().get_renderer().render_texture(node, None).save_to_png("/tmp/ollama-model-popup.png")
            assert popup.get_width() >= 560, popup.get_width()
            assert popup.get_height() >= 300, popup.get_height()
            window.models.popdown()
            GLib.timeout_add(250, checked, preferences_open)
        def preferences_open():
            window.preview_preferences = Preferences(window)
            window.preview_preferences.brave_enabled.set_active(True)
            window.preview_preferences.key.set_text("example-key-not-a-real-credential")
            window.preview_preferences.present(window)
            GLib.timeout_add(450, checked, preferences)
        def preferences():
            save_snapshot("/tmp/ollama-brave-setup-preview.png")
            ancestor = window.preview_preferences.erase_button.get_parent()
            while ancestor and not isinstance(ancestor, Gtk.ScrolledWindow):
                ancestor = ancestor.get_parent()
            ancestor.get_vadjustment().set_value(ancestor.get_vadjustment().get_upper())
            GLib.timeout_add(250, checked, reset)
        def reset():
            save_snapshot("/tmp/ollama-all-data-reset-preview.png")
            window.preview_preferences.set_visible_page(window.preview_preferences.advanced_page)
            GLib.timeout_add(350, checked, advanced)
        def advanced():
            save_snapshot("/tmp/ollama-advanced-defaults-preview.png")
            window.preview_preferences.custom_system.set_active(True)
            window.preview_preferences.custom_mcp.set_active(True)
            GLib.timeout_add(350, checked, custom)
        def custom():
            save_snapshot("/tmp/ollama-advanced-custom-preview.png")
            window.preview_preferences.close()
            window.show_thinking()
            GLib.timeout_add(350, checked, thinking)
        def thinking():
            save_snapshot("/tmp/ollama-thinking-preview.png")
            window.plus.popup()
            window.plus_paintable = Gtk.WidgetPaintable.new(window.plus_menu)
            GLib.timeout_add(300, checked, plus)
        def plus():
            snapshot = Gtk.Snapshot()
            window.plus_paintable.snapshot(snapshot, window.plus_menu.get_width(), window.plus_menu.get_height())
            node = snapshot.to_node()
            if node:
                window.plus_menu.get_native().get_renderer().render_texture(node, None).save_to_png("/tmp/ollama-plus-collapsed.png")
            window.plus_menu.popdown()
            window.tools_menu.popup()
            window.tools_paintable = Gtk.WidgetPaintable.new(window.tools_menu)
            GLib.timeout_add(350, checked, tools)
        def tools():
            snapshot = Gtk.Snapshot()
            window.tools_paintable.snapshot(snapshot, window.tools_menu.get_width(), window.tools_menu.get_height())
            node = snapshot.to_node()
            if node:
                window.tools_menu.get_native().get_renderer().render_texture(node, None).save_to_png("/tmp/ollama-plus-tools.png")
            window.tools_menu.popdown()
            GLib.timeout_add(250, checked, close)
        def close():
            window.worker.close()
            window.destroy()
            loop.quit()
        GLib.timeout_add(400, checked, main)
    def checked(callback):
        try:
            callback()
        except BaseException as exc:
            print(type(exc).__name__, exc)
            failures.append(True)
            window.worker.close()
            window.destroy()
            loop.quit()
        return GLib.SOURCE_REMOVE
    def prepare_tools():
        window.set_default_size(1080, 950)
        window.store.settings["show_thinking"] = True
        query = "Fedora Workstation and GNOME development"
        results = json.dumps({"query": query, "results": [
            {"title": "Fedora Workstation", "url": "https://fedoraproject.org/workstation/", "description": "A desktop operating system built on open source software."},
            {"title": "GNOME Developer Documentation", "url": "https://developer.gnome.org/", "description": "Build native applications for GNOME."},
            {"title": "Libadwaita Documentation", "url": "https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/", "description": "Adaptive native application widgets."},
            {"title": "GTK Documentation", "url": "https://docs.gtk.org/gtk4/", "description": "GTK interface widgets and APIs."},
        ]})
        code = "import math\nprint(math.sqrt(81))\nprint(sum(range(1, 101)))"
        window.current["title"] = "GNOME Development and Calculations"
        window.current["messages"] = [
            {"role": "user", "content": "Find GNOME resources and do a quick calculation."},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "s0_brave_web_search", "arguments": {"query": query}}}]},
            {"role": "tool", "tool_name": "s0_brave_web_search", "content": results},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "s1_execute_python", "arguments": {"code": code}}}]},
            {"role": "tool", "tool_name": "s1_execute_python", "content": json.dumps({"exit_code": 0, "stdout": "9.0\n5050\n", "stderr": ""})},
            {"role": "assistant", "content": "GNOME's documentation covers native application development [2], including adaptive libadwaita widgets [3].\n\nThe square root is **9**, and the sum is **5,050**.", "thinking": "I checked the Python results and the linked sources before answering."},
        ]
        window.render_sidebar()
        window.render_chat()
        child = window.activity_box.get_first_child()
        while child:
            if isinstance(child, Gtk.Expander):
                child.set_expanded(True)
                if child.get_label_widget().get_text().startswith("Searching"):
                    window.search_preview = child.get_child()
                elif child.get_label_widget().get_text() == "Python":
                    window.python_preview = child.get_child()
            child = child.get_next_sibling()
        def main():
            window.scroll.get_vadjustment().set_value(0)
            GLib.timeout_add(150, checked, capture_tools)
        def capture_tools():
            code = window.python_preview.code
            assert code.content_height > 40
            assert code.scroll.get_height() == code.content_height
            save_snapshot("/tmp/ollama-clean-tools.png")
            window.search_dialog = window.search_preview.open_full()
            GLib.timeout_add(400, checked, search_dialog)
        def search_dialog():
            save_snapshot("/tmp/ollama-search-links-dialog.png")
            window.search_dialog.close()
            window.preview_preferences = Preferences(window)
            window.preview_preferences.present(window)
            GLib.timeout_add(500, checked, general)
        def general():
            save_snapshot("/tmp/ollama-tools-preferences.png")
            window.preview_preferences.brave_enabled.set_active(True)
            GLib.timeout_add(350, checked, brave_fields)
        def brave_fields():
            save_snapshot("/tmp/ollama-brave-enabled-preferences.png")
            window.preview_preferences.set_visible_page(window.preview_preferences.advanced_page)
            GLib.timeout_add(350, checked, advanced)
        def advanced():
            save_snapshot("/tmp/ollama-response-display-preferences.png")
            window.preview_preferences.close()
            window.scroll.get_vadjustment().set_value(window.scroll.get_vadjustment().get_upper())
            GLib.timeout_add(350, checked, thinking)
        def thinking():
            save_snapshot("/tmp/ollama-visible-thinking.png")
            row = window.chat_list.get_first_child()
            row.motion.emit("enter", 0.0, 0.0)
            row.menu_button.popup()
            window.chat_menu_paintable = Gtk.WidgetPaintable.new(row.menu_button.get_popover())
            GLib.timeout_add(250, checked, chat_menu)
        def chat_menu():
            popup = window.chat_list.get_first_child().menu_button.get_popover()
            snapshot = Gtk.Snapshot()
            window.chat_menu_paintable.snapshot(snapshot, popup.get_width(), popup.get_height())
            node = snapshot.to_node()
            assert node is not None
            popup.get_native().get_renderer().render_texture(node, None).save_to_png("/tmp/ollama-chat-options.png")
            window.chat_list.get_first_child().menu_button.popdown()
            window.set_default_size(360, 700)
            window.split.set_show_sidebar(False)
            GLib.timeout_add(650, checked, narrow)
        def narrow():
            window.scroll.get_vadjustment().set_value(0)
            GLib.timeout_add(150, checked, close)
        def close():
            assert window.messages.get_width() <= window.get_width()
            save_snapshot("/tmp/ollama-clean-tools-narrow.png")
            window.worker.close()
            window.destroy()
            loop.quit()
        GLib.timeout_add(550, checked, main)
    GLib.timeout_add(1200, checked, prepare_tools if tools_layout else prepare_features if features else prepare_layout if layout else prepare_responsive if responsive else capture)
    loop.run()
    if failures:
        raise SystemExit(1)
