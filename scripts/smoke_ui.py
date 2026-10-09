"""Run on a graphical session; uses temporary application data."""
import sys
import json
import copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
from io import BytesIO
from PIL import Image
from unittest.mock import patch
from ollama_gui.app import Application, Window, Preferences, Adw, Gdk, GLib, Gtk, Gio
from ollama_gui.storage import DEFAULT_SETTINGS, PYTHON_SERVER_NAME, Store
from ollama_gui.attachments import image_attachment, user_message
from ollama_gui.image_view import texture
from ollama_gui.markdown_view import MarkdownView
from ollama_gui.code_view import CodeBlock, CODE_PREVIEW_HEIGHT
from ollama_gui.title_view import FadingTitle
from ollama_gui.tool_view import SearchPreview, PythonPreview, ToolPreview, SearchOutputDialog


async def fake_title(*_):
    return "Test Conversation"

with tempfile.TemporaryDirectory() as root, patch("ollama_gui.app.Ollama.title", new=fake_title):
    app = Application()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    notifications = []
    app.send_notification = lambda identifier, notification: notifications.append((identifier, notification))
    app.withdraw_notification = lambda *_: None
    store = Store(root)
    store.settings["setup_completed"] = True
    window = Window(app, store)
    window.present()
    prefs = Preferences(window)
    prefs.present(window)
    loop = GLib.MainLoop()
    def finish():
        prefs.close()
        assert Gtk.IconTheme.get_for_display(window.get_display()).has_icon("lumen-symbolic")
        assert window.empty.get_paintable() is window.lantern_paintable
        assert window.get_icon_name() == "io.github.ollamagnome.Lumen"
        assert Gtk.IconTheme.get_for_display(window.get_display()).has_icon("io.github.ollamagnome.Lumen")
        assert window.send.get_icon_name() == "go-up-symbolic"
        assert window.plus.get_popover() is window.plus_menu
        assert window.plus.get_next_sibling() is window.tools_button
        assert window.model_clamp.get_child() is window.models
        assert window.model_clamp.get_maximum_size() == 240
        assert window.app_menu.get_parent() is window.sidebar_controls
        assert window.app_menu.get_prev_sibling().get_action_name() == "win.new"
        assert window.stack.get_transition_type() == Gtk.StackTransitionType.CROSSFADE
        assert window.stack.get_transition_duration() == 200
        assert prefs.system.get_left_margin() == 16
        assert prefs.system.get_parent().has_css_class("preferences-editor")
        assert prefs.servers.get_parent().has_css_class("card")
        assert prefs.python_enabled.get_active()
        assert prefs.auto_titles.get_active()
        assert not prefs.show_thinking.get_active()
        assert prefs.friendly_search.get_active()
        assert prefs.friendly_python.get_active()
        assert prefs.friendly_search.get_next_sibling() is prefs.friendly_python
        assert prefs.url.is_ancestor(prefs.advanced_page)
        assert not prefs.url.is_ancestor(prefs.general_page)
        assert prefs.show_thinking.is_ancestor(prefs.general_page)
        assert prefs.friendly_search.is_ancestor(prefs.tools_page)
        assert prefs.friendly_python.is_ancestor(prefs.tools_page)
        assert prefs.latex_enabled.is_ancestor(prefs.advanced_page)
        assert prefs.latex_enabled.get_active()
        assert not prefs.brave_enabled.get_active()
        assert not prefs.brave_revealer.get_visible()
        prefs.brave_enabled.set_active(True)
        assert prefs.brave_revealer.get_visible()
        prefs.brave_enabled.set_active(False)
        assert prefs.tools_enabled.get_active()
        assert prefs.tools_enabled.is_ancestor(prefs.tools_page)
        assert prefs.python_enabled.is_ancestor(prefs.tools_page)
        assert prefs.brave_group.is_ancestor(prefs.tools_page)
        prefs.tools_enabled.set_active(False)
        assert not prefs.tools_revealer.get_visible()
        prefs.tools_enabled.set_active(True)
        assert prefs.tools_revealer.get_visible()
        assert prefs.brave_group.is_ancestor(prefs.tools_group)
        assert prefs.python_enabled.get_parent() is not prefs.key.get_parent()
        assert not prefs.advanced_test.get_visible()
        assert prefs.brave_test.get_next_sibling() is prefs.brave_setup
        menu = window.app_menu.get_menu_model()
        assert all(menu.get_item_attribute_value(index, "label", None).get_string() != "Delete Conversation" for index in range(menu.get_n_items()))
        assert not prefs.custom_system.get_active()
        assert not prefs.custom_mcp.get_active()
        assert not prefs.system.get_editable() and not prefs.servers.get_editable()
        assert not prefs.system_revealer.get_visible() and not prefs.servers_revealer.get_visible()
        assert window.tools_button.get_tooltip_text() == "Tools"
        assert window.tools_button.get_popover() is window.tools_menu
        assert window.plus.get_next_sibling() is window.tools_button
        assert window.tools_button.get_next_sibling() is window.model_clamp
        assert window.tool_choices.get_parent().get_parent() is window.tools_menu.get_child().get_first_child()
        window.open_search()
        assert window.search_button.get_active()
        window.search_entry.set_text("no such chat")
        assert window.sidebar_results.get_visible_child_name() == "empty"
        window.search_bar.set_search_mode(False)
        assert window.search_entry.get_text() == ""
        assert not hasattr(window, "status")
        assert window.chat_title.get_text() == window.current["title"]
        blank = window.current
        for _ in range(10):
            window.new_chat()
        assert len(window.store.chats) == 1
        assert window.current is blank
        assert not window.lookup_action("new").get_enabled()
        window.input.get_buffer().set_text("Unsent draft")
        window.new_chat()
        assert window.input.get_buffer().get_char_count() > 0
        window.store.settings["mcpServers"] = {"test-server": {"command": "unused"}}
        window.tool_catalog = [{"server": "test-server", "name": "search", "description": "Find information"}]
        window.tools_loading = False
        window.render_tool_choices()
        toggle = window.tool_choices.get_last_child()
        assert toggle.get_active()
        assert window.tool_indicator.get_visible()
        toggle.set_active(False)
        assert not window.tool_indicator.get_visible()
        assert "test-server" not in window.servers_for_chat()
        assert Store(root).settings["mcpServers"]["test-server"]["disabled_tools"] == ["search"]
        toggle.set_active(True)
        assert "test-server" in window.servers_for_chat()
        python = {"server": PYTHON_SERVER_NAME, "name": "execute_python", "description": "Python execution"}
        window.toggle_tool(python, False)
        assert PYTHON_SERVER_NAME not in window.servers_for_chat()
        assert not Store(root).settings["python_enabled"]
        window.toggle_tool(python, True)
        assert PYTHON_SERVER_NAME in window.servers_for_chat()
        window.store.settings["mcpServers"]["brave-search"] = {"command": "unused-for-label-test"}
        window.store.settings["brave_enabled"] = True
        window.tool_catalog = [
            {"server": "brave-search", "name": "brave_web_search", "description": "Web search"},
            {"server": "brave-search", "name": "brave_news_search", "description": "News search"}, python,
        ]
        window.render_tool_choices()
        labels = []
        child = window.tool_choices.get_first_child()
        while child:
            if isinstance(child, Gtk.CheckButton):
                labels.append(child.get_label())
            child = child.get_next_sibling()
        assert labels == ["Brave Web Search", "Brave News Search", "Execute Python"]
        del window.store.settings["mcpServers"]["brave-search"]
        window.store.settings["brave_enabled"] = False
        window.attachments = [{"name": "notes.md", "kind": "file", "content": "Notes"}]
        window.render_attachments()
        assert window.attachment_chips.get_visible()
        window.set_busy(True)
        assert window.send.get_icon_name() == "media-playback-stop-symbolic"
        assert not window.plus.get_sensitive()
        window.set_busy(False)
        target = window.current
        target["messages"] = [{"role": "user", "content": "Test"}]
        window.update_actions()
        assert window.lookup_action("new").get_enabled()
        window.new_chat()
        current = window.current
        assert window.input.get_buffer().get_char_count() > 0
        assert len(window.attachments) == 1
        assert window.attachments[0]["name"] == "notes.md"
        assert window.attachments is not window.drafts[target["id"]]["attachments"]
        assert not window.lookup_action("new").get_enabled()
        window.activate_chat(target)
        assert window.input.get_buffer().get_char_count() > 0
        window.activate_chat(current)
        assert window.input.get_buffer().get_char_count() > 0
        window.search_entry.set_text("Test")
        assert window.sidebar_results.get_visible_child_name() == "results"
        assert window.chat_list.get_first_child().chat is current
        window.open_first_search_result()
        assert window.current is target
        window.search_entry.set_text("")
        window.activate_chat(current)
        deletion = window.delete_chat(chat=target)
        deletion.emit("response", "delete")
        deletion.close()
        assert target not in window.store.chats
        assert window.current is current
        assert len(Store(root).chats) == 1
        assert isinstance(window.chat_list.get_first_child().get_child().get_last_child(), Gtk.MenuButton)
        row = window.chat_list.get_first_child()
        assert isinstance(row.title_label, FadingTitle)
        assert row.title_label.get_single_line_mode()
        option = row.menu_button.get_popover().get_child().get_first_child()
        assert option.get_child().get_first_child().get_icon_name() == "document-edit-symbolic"
        assert option.get_child().get_last_child().get_text() == "Rename Conversation…"
        assert option.get_child().get_last_child().get_xalign() == 0
        assert option.get_next_sibling().get_child().get_first_child().get_icon_name() == "user-trash-symbolic"
        for icon in ("document-edit-symbolic", "user-trash-symbolic"):
            assert Gtk.IconTheme.get_for_display(window.get_display()).has_icon(icon)
        row.motion.emit("enter", 0.0, 0.0)
        assert row.menu_button.has_css_class("options-visible")
        assert row.menu_button.get_can_target()
        row.motion.emit("leave")
        assert not row.menu_button.has_css_class("options-visible")
        assert not row.menu_button.get_can_target()
        row.motion.emit("enter", 0.0, 0.0)
        row.menu_button.popup()
        row.motion.emit("leave")
        assert row.menu_button.has_css_class("options-visible")
        row.menu_button.popdown()
        user_label = window.message_card("user", "Test message")
        assert user_label.get_parent().get_margin_start() == 16
        assert user_label.get_parent().get_parent().has_css_class("card")
        class MessageClipboard:
            copied = None
            def set(self, text): self.copied = text
        message_clipboard = MessageClipboard()
        window.get_clipboard = lambda: message_clipboard
        window.message_copy = user_label.get_parent().get_first_child().get_last_child()
        window.message_copy.emit("clicked")
        assert message_clipboard.copied == "Test message"
        assert window.message_copy.get_icon_name() == "emblem-ok-symbolic"
        assert window.message_copy.get_tooltip_text() == "Copied to Clipboard"
        window.event("thinking", None)
        assert window.thinking_label.get_text() == "Thinking…"
        spinner = window.thinking_spinner
        assert spinner.get_spinning()
        window.event("reasoning", "Hidden model reasoning")
        assert window.active_reasoning is None
        window.event("token", "Hello")
        assert window.thinking_label is None
        assert window.thinking_spinner is None
        assert not spinner.get_spinning() and spinner.get_parent() is None
        assert window.active_label.get_text() == "Hello"
        window.store.settings["show_thinking"] = True
        window.event("round", None)
        window.event("reasoning", "Check the calculation. ")
        window.event("reasoning", "Then answer.")
        reasoning = window.active_reasoning
        assert reasoning.get_text() == "Check the calculation. Then answer."
        assert isinstance(reasoning.get_ancestor(Gtk.Expander), Gtk.Expander)
        window.event("token", "42")
        assert window.active_label.get_text() == "Hello\n\n42"
        assert reasoning.get_parent() is not None and window.thinking_spinner is None
        assert reasoning.is_ancestor(window.activity_box)
        assert window.activity_box.get_next_sibling() is window.active_label.get_parent()
        assert window.active_label.get_parent().get_first_child().get_first_child().get_text() == "Response"
        window.event("round", None)
        window.event("reasoning", "Search first.")
        reasoning = window.active_reasoning
        window.event("tool-start", {"name": "s0_brave_web_search", "arguments": {"query": "Fedora & GNOME"}})
        assert reasoning.get_root() is window
        assert window.thinking_spinner is None
        assert isinstance(window.active_tool, SearchPreview)
        assert window.activity_box.get_last_child().get_label_widget().get_text() == "Searching for “Fedora & GNOME”"
        window.activity_box.get_last_child().set_expanded(True)
        search_output = json.dumps({"results": [{"title": f"Source {i}", "url": f"https://example.com/{i}?a=1&b=2", "description": "A source <b>description</b>"} for i in range(6)]})
        window.event("tool-result", search_output)
        assert len(window.active_tool.results) == 6
        assert window.active_tool.get_first_child().get_first_child().get_first_child().get_text() == "Source 0"
        popup = window.active_tool.open_full()
        assert isinstance(popup, SearchOutputDialog) and popup.full_text == search_output
        popup.close()
        window.event("tool-start", {"name": "s1_execute_python", "arguments": {"code": "print(6 * 7)"}})
        assert isinstance(window.active_tool, PythonPreview)
        assert window.activity_box.get_last_child().get_label_widget().get_text() == "Python"
        assert window.active_tool.code.source == "print(6 * 7)"
        window.event("tool-result", '{"exit_code":0,"stdout":"42\\n","stderr":""}')
        assert window.active_tool.status.get_text() == "Completed"
        assert window.active_tool.output.get_text() == "42\n"
        window.store.settings["friendly_python"] = False
        raw_python = window.tool_card("s1_execute_python", '{"exit_code":0,"stdout":"42"}', {"code": "print(42)"})
        assert isinstance(raw_python, ToolPreview)
        assert '"exit_code":0' in raw_python.get_text()
        window.store.settings["friendly_python"] = True
        window.store.settings["friendly_search"] = False
        raw = window.tool_card("s0_brave_web_search", search_output, {"query": "Fedora"})
        assert isinstance(raw, ToolPreview) and search_output in raw.get_text()
        window.store.settings["friendly_search"] = True
        window.store.settings["show_thinking"] = False
        window.event("round", None)
        assert window.thinking_label.get_text() == "Thinking…"
        assert window.thinking_spinner.get_spinning()
        window.event("tool-start", {"name": "Test Search", "arguments": {}})
        assert window.thinking_label is None
        assert window.thinking_spinner is None
        window.current["messages"].append({"role": "user", "content": "Test"})
        # Deterministic focus scenarios; no real desktop notifications are sent.
        app.is_focused = lambda: True
        window.finished([{"role": "assistant", "content": "Done"}], None)
        assert len(notifications) == 0
        assert window.lookup_action("new").get_enabled()
        app.is_focused = lambda: False
        window.current["messages"].append({"role": "user", "content": "Background reply"})
        window.finished([{"role": "assistant", "content": "Done in background"}], None)
        assert len(notifications) == 1
        window.current["messages"].append({"role": "user", "content": "Will fail"})
        window.finished(None, RuntimeError("test failure"))
        assert len(notifications) == 1
        previous_generation = window.turn_generation - 1
        children_before = window.messages.get_last_child()
        window.dispatch_event(previous_generation, "token", "Stale reply")
        assert window.messages.get_last_child() is children_before
        window.refresh_models = lambda: None
        window.refresh_tools = lambda: None
        # Deliver title results after manual rename/delete/reset to exercise
        # protection against stale background callbacks without a live model.
        real_worker = window.worker
        class Future:
            cancelled = False
            def cancel(self): self.cancelled = True
        class TitleWorker:
            jobs = []
            def close(self): pass
            def submit(self, coroutine, callback):
                coroutine.close()
                future = Future()
                self.jobs.append((callback, future))
                return future
        fake_worker = TitleWorker()
        window.cancel_titles()
        window.worker = fake_worker
        window.model_names = ["test"]
        window.store.settings["model"] = "test"
        window.current["title_source"] = "pending"
        window.request_title(window.current)
        callback, _ = fake_worker.jobs[-1]
        callback("Python Calculation", None)
        assert window.current["title"] == "Python Calculation"
        assert window.chat_title.get_text() == "Python Calculation"
        assert Store(root).chats[0]["title_source"] == "generated"
        window.current["title_source"] = "pending"
        window.request_title(window.current)
        callback, future = fake_worker.jobs[-1]
        display_preferences = Preferences(window)
        display_preferences.present(window)
        saved_servers = copy.deepcopy(window.store.settings["mcpServers"])
        display_preferences.tools_enabled.set_active(False)
        display_preferences.auto_titles.set_active(False)
        display_preferences.show_thinking.set_active(True)
        display_preferences.friendly_search.set_active(False)
        display_preferences.friendly_python.set_active(False)
        display_preferences.latex_enabled.set_active(False)
        display_preferences.save(None)
        display_preferences.close()
        assert future.cancelled and not window.title_jobs
        callback("Disabled Automatic Title", None)
        assert window.current["title"] == "Python Calculation"
        count = len(fake_worker.jobs)
        window.request_title(window.current)
        assert len(fake_worker.jobs) == count
        display_preferences = Preferences(window)
        display_preferences.present(window)
        assert not display_preferences.auto_titles.get_active()
        assert display_preferences.show_thinking.get_active()
        assert not display_preferences.friendly_search.get_active()
        assert not display_preferences.friendly_python.get_active()
        assert not display_preferences.latex_enabled.get_active()
        assert not Store(root).settings["latex_enabled"]
        assert not Store(root).settings["auto_titles"]
        assert not display_preferences.tools_enabled.get_active()
        assert not display_preferences.tools_revealer.get_visible()
        assert not Store(root).settings["tools_enabled"]
        assert window.servers_for_chat() == {}
        assert window.store.settings["mcpServers"] == saved_servers
        display_preferences.tools_enabled.set_active(True)
        display_preferences.auto_titles.set_active(True)
        display_preferences.show_thinking.set_active(False)
        display_preferences.friendly_search.set_active(True)
        display_preferences.friendly_python.set_active(True)
        display_preferences.latex_enabled.set_active(True)
        display_preferences.save(None)
        display_preferences.close()
        window.cancel_titles()
        window.current["title_source"] = "pending"
        window.request_title(window.current)
        callback, future = fake_worker.jobs[-1]
        rename = window.rename_chat(window.current)
        rename.entry.set_text("   ")
        assert not rename.get_response_enabled("rename")
        rename.entry.set_text("My Math Notes")
        rename.emit("response", "rename")
        rename.close()
        assert future.cancelled
        callback("Late Automatic Name", None)
        assert window.current["title"] == "My Math Notes"
        assert window.chat_title.get_text() == "My Math Notes"
        assert window.current["title_source"] == "manual"
        window.request_title(window.current)
        assert not window.title_jobs
        target = {"id": "delete-title-test", "title": "Pending", "messages": [{"role": "user", "content": "Question"}, {"role": "assistant", "content": "Answer"}]}
        window.store.chats.append(target)
        window.request_title(target)
        callback, future = fake_worker.jobs[-1]
        deletion = window.delete_chat(chat=target)
        deletion.emit("response", "delete")
        deletion.close()
        callback("Deleted Chat", None)
        assert future.cancelled and target not in window.store.chats
        window.worker = real_worker
        custom_preferences = Preferences(window)
        custom_preferences.present(window)
        custom_preferences.custom_system.set_active(True)
        custom_preferences.custom_mcp.set_active(True)
        assert custom_preferences.advanced_test.get_visible()
        assert custom_preferences.system.get_editable() and custom_preferences.servers.get_editable()
        assert custom_preferences.system_revealer.get_visible() and custom_preferences.servers_revealer.get_visible()
        custom_preferences.system.get_buffer().set_text("Answer in Spanish.")
        custom_preferences.save(None)
        custom_preferences.close()
        custom_preferences = Preferences(window)
        custom_preferences.present(window)
        assert custom_preferences.custom_system.get_active() and custom_preferences.custom_mcp.get_active()
        assert custom_preferences.system.get_buffer().get_char_count() == len("Answer in Spanish.")
        custom_preferences.custom_system.set_active(False)
        custom_preferences.custom_mcp.set_active(False)
        assert not custom_preferences.advanced_test.get_visible()
        custom_preferences.servers.get_buffer().set_text("invalid hidden JSON")
        custom_preferences.save(None)
        custom_preferences.close()
        assert not Store(root).settings["custom_system_enabled"]
        assert not Store(root).settings["custom_mcp_enabled"]
        assert "test-server" in Store(root).settings["mcpServers"]
        key_preferences = Preferences(window)
        key_preferences.present(window)
        assert not key_preferences.brave_setup.has_css_class("suggested-action")
        key_preferences.key.set_text("test-only-key")
        key_preferences.brave_enabled.set_active(True)
        key_preferences.python_enabled.set_active(False)
        assert not key_preferences.brave_setup.has_css_class("suggested-action")
        key_preferences.add_brave(None)
        assert Store(root).settings["mcpServers"]["brave-search"]["env"]["BRAVE_API_KEY"] == "test-only-key"
        assert not key_preferences.brave_setup.has_css_class("suggested-action")
        assert Store(root).settings["brave_enabled"]
        key_preferences.save(None)
        key_preferences.close()
        assert not Store(root).settings["python_enabled"]
        assert PYTHON_SERVER_NAME not in window.servers_for_chat()
        saved = Store(root).settings["mcpServers"]["brave-search"]
        assert saved["env"]["BRAVE_API_KEY"] == "test-only-key"
        assert saved["args"] == ["-m", "ollama_gui.brave"]
        reopened = Preferences(window)
        reopened.present(window)
        assert reopened.key.get_text() == "test-only-key"
        assert reopened.brave_enabled.get_active()
        reopened.brave_enabled.set_active(False)
        assert not reopened.brave_revealer.get_visible()
        reopened.save(None)
        reopened.close()
        assert not Store(root).settings["brave_enabled"]
        assert "brave-search" not in window.servers_for_chat()
        reopened = Preferences(window)
        reopened.present(window)
        assert reopened.key.get_text() == "test-only-key"
        reopened.brave_enabled.set_active(True)
        assert not reopened.python_enabled.get_active()
        reopened.python_enabled.set_active(True)
        reopened.key.set_text("replacement-test-key")
        reopened.save(None)
        reopened.close()
        assert Store(root).settings["mcpServers"]["brave-search"]["env"]["BRAVE_API_KEY"] == "replacement-test-key"
        assert Store(root).settings["python_enabled"]
        reset_preferences = Preferences(window)
        reset_preferences.present(window)
        reset_dialog = reset_preferences.reset_defaults()
        reset_dialog.emit("response", "cancel")
        reset_dialog.close()
        assert Store(root).settings["mcpServers"]
        chats_before = list(window.store.chats)
        reset_dialog = reset_preferences.reset_defaults()
        reset_dialog.emit("response", "reset")
        reset_dialog.close()
        assert Store(root).settings == DEFAULT_SETTINGS
        assert window.store.chats == chats_before
        assert reset_preferences.key.get_text() == ""
        assert reset_preferences.url.get_text() == DEFAULT_SETTINGS["url"]
        assert reset_preferences.system.get_buffer().get_char_count() == len(DEFAULT_SETTINGS["system"])
        reset_dialog = reset_preferences.reset_all_data()
        reset_dialog.emit("response", "cancel")
        reset_dialog.close()
        assert window.store.chats == chats_before
        window.drafts["private"] = {"text": "Private draft", "attachments": []}
        window.cancel_titles()
        window.worker = fake_worker
        old_chat = window.current
        old_chat["title_source"] = "pending"
        window.request_title(old_chat)
        callback, future = fake_worker.jobs[-1]
        window.worker = real_worker
        reset_dialog = reset_preferences.reset_all_data()
        reset_dialog.emit("response", "erase")
        reset_dialog.close()
        callback("Old Data Title", None)
        assert future.cancelled and old_chat not in window.store.chats
        assert len(window.store.chats) == 1 and not window.current["messages"]
        assert len(Store(root).chats) == 1 and not Store(root).chats[0]["messages"]
        assert not window.drafts
        assert not window.attachments
        reset_preferences.close()
        window.message_card("user", "Test message with padding")
        window.message_card("assistant", "Streaming text & <untrusted markup>")
        formatted = window.message_card("assistant", "## Title\n\n**Bold** and [source](https://example.com).\n\n- First\n- Second\n\n```python\nprint('<literal>')\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |")
        assert isinstance(formatted, MarkdownView)
        heading = formatted.get_first_child()
        assert heading.get_text() == "Title" and heading.has_css_class("title-2")
        assert "**Bold**" in formatted.get_text()
        assert "<b>Bold</b>" in heading.get_next_sibling().get_label()
        stream = MarkdownView()
        window.messages.append(stream)
        stream.append_text("**Hel")
        stream.append_text("lo**")
        stream.set_text(stream.get_text())
        assert stream.get_text() == "**Hello**"
        assert stream.get_first_child().get_text() == "Hello"
        full_output = "\n".join(f"Line {i}" for i in range(100))
        preview = window.tool_card("Test Search", full_output)
        window.activity_box.get_last_child().set_expanded(True)
        assert preview.preview.get_lines() == 4
        assert preview.more.get_visible()
        assert preview.get_text() == full_output
        popup = preview.open_full()
        assert popup.full_text == full_output
        assert popup.view.get_buffer().get_char_count() == len(full_output)
        popup.close()
        preview.set_text(full_output + "\nNewest result")
        assert preview.get_text().endswith("Newest result")
        # Older saved conversations reconstruct their query/code from tool
        # calls. Display preferences also apply after reloading local history.
        stored_search = json.dumps({"results": [{"title": "Saved source", "url": "https://example.com/saved", "description": "A saved search result"}]})
        window.current["messages"] = [
            {"role": "user", "content": "Search Fedora"},
            {"role": "assistant", "content": "", "thinking": "Use a source.", "tool_calls": [{"function": {"name": "s0_brave_web_search", "arguments": {"query": "Fedora"}}}]},
            {"role": "tool", "tool_name": "s0_brave_web_search", "content": stored_search},
            {"role": "assistant", "content": "Done [1].", "thinking": "Check the source."},
        ]
        window.save_store()
        window.current["messages"] = Store(root).chats[0]["messages"]
        window.render_chat()
        saved_tool = window.messages.get_first_child().get_next_sibling().get_first_child()
        assert isinstance(saved_tool, Gtk.Expander)
        assert saved_tool.get_label_widget().get_text() == "Searching for “Fedora”"
        assert isinstance(saved_tool.get_child(), SearchPreview)
        window.store.settings["show_thinking"] = True
        window.render_chat()
        activity = window.messages.get_first_child().get_next_sibling()
        assert activity.get_first_child().get_child().get_text() == "Use a source."
        assert activity.get_last_child().get_child().get_text() == "Check the source."
        answer = window.messages.get_last_child()
        assert activity.get_next_sibling() is answer
        assert answer.get_first_child().get_first_child().get_text() == "Response"
        assert answer.get_last_child().get_text() == "Done [1]."
        assert 'href="https://example.com/saved"' not in answer.get_last_child().get_first_child().get_label()
        answer.get_first_child().get_last_child().emit("clicked")
        assert message_clipboard.copied == "Done [1]."
        window.store.settings["show_thinking"] = False
        window.store.settings["friendly_search"] = False
        window.render_chat()
        saved_tool = window.messages.get_first_child().get_next_sibling().get_first_child()
        assert isinstance(saved_tool.get_child(), ToolPreview)
        assert '"query": "Fedora"' in saved_tool.get_child().get_text()
        assert stored_search in saved_tool.get_child().get_text()
        window.store.settings["friendly_search"] = True
        second_search = json.dumps({"results": [{"title": "Second source", "url": "https://example.com/second"}]})
        window.current["messages"].extend([
            {"role": "user", "content": "Search again"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "s0_brave_web_search", "arguments": {"query": "Second"}}}]},
            {"role": "tool", "tool_name": "s0_brave_web_search", "content": second_search},
            {"role": "assistant", "content": "Another claim [1]."},
        ])
        window.render_chat()
        first_answer = window.messages.get_first_child().get_next_sibling().get_next_sibling().get_last_child()
        second_answer = window.messages.get_last_child().get_last_child()
        assert first_answer.get_copy_text() == "Done [1]."
        assert second_answer.get_copy_text() == "Another claim [1]."
        assert window.messages.get_last_child().get_first_child().get_first_child().get_text() == "Response"
        window.models.set_model(Gtk.StringList.new(["long-model-name-" * 30]))
        assert window.models.rows.get_first_child().get_child().get_text() == "long-model-name-" * 30
        window.models.popup()
        assert window.models.get_popover().get_position() == Gtk.PositionType.TOP
        assert window.models.list_scroll.get_min_content_width() > window.models.get_width()
        assert window.models.list_scroll.get_min_content_height() == 260
        window.models.popdown()
        code_source = "\n".join(f"print('Line {i}')" for i in range(45)) + "\n" + "x" * 350
        window.current["messages"] = [{"role": "assistant", "content": f"```python\nprint('Short')\n```\n\n```python\n{code_source}\n```\n\nAfter the code."}]
        window.render_chat()
        markdown = window.messages.get_last_child().get_last_child()
        window.short_code = markdown.get_first_child()
        window.long_code = window.short_code.get_next_sibling()
        assert isinstance(window.long_code, CodeBlock)
        assert window.long_code.view.get_buffer().get_char_count() == len(code_source)
        window.set_default_size(600, 700)
        GLib.timeout_add(400, checked, check_code_layout)
        return GLib.SOURCE_REMOVE

    def check_code_layout():
        short = window.short_code
        code = window.long_code
        assert 40 <= short.content_height < CODE_PREVIEW_HEIGHT, short.content_height
        assert not short.reveal_button.get_visible()
        assert code.content_height > CODE_PREVIEW_HEIGHT, code.content_height
        assert code.scroll.get_min_content_height() == CODE_PREVIEW_HEIGHT
        assert code.scroll.get_height() == CODE_PREVIEW_HEIGHT, code.scroll.get_height()
        assert code.reveal_button.get_visible()
        assert code.get_width() <= window.messages.get_width()
        assert window.models.get_width() <= 240, window.models.get_width()
        assert window.messages.has_css_class("chat-transcript")
        assert not code.view.get_cursor_visible()
        assert code.view.get_buffer().get_highlight_syntax()
        assert code.view.get_buffer().get_language().get_id() == "python3"
        javascript = CodeBlock("const answer = 42;", "javascript")
        assert javascript.view.get_buffer().get_language().get_id() == "js"
        assert code.view.get_buffer().get_style_scheme() is not None
        class Clipboard:
            copied = None
            def set(self, text):
                self.copied = text
        clipboard = Clipboard()
        code.get_clipboard = lambda: clipboard
        code.copy_button.emit("clicked")
        assert clipboard.copied == code.source
        assert code.copy_button.get_icon_name() == "emblem-ok-symbolic"
        assert code.copy_button.get_tooltip_text() == "Copied to Clipboard"
        code.scroll.get_vadjustment().set_value(100)
        assert code.scroll.get_vadjustment().get_value() == 0
        window.scroll.get_vadjustment().set_value(0)
        assert code.scroll_controller.emit("scroll", 0.0, 1.0)
        assert window.scroll.get_vadjustment().get_value() > 0
        assert code.scroll.get_vadjustment().get_value() == 0
        code.toggle_expanded()
        assert code.scroll.get_min_content_height() == code.content_height
        GLib.timeout_add(200, checked, check_code_expanded)

    def check_code_expanded():
        code = window.long_code
        assert code.scroll.get_height() >= code.content_height
        assert code.reveal_button.get_label() == "Show Less"
        code.toggle_expanded()
        assert code.scroll.get_min_content_height() == CODE_PREVIEW_HEIGHT
        # A streaming rebuild keeps code expansion choices.
        code.toggle_expanded()
        markdown = code.get_parent()
        markdown.append_text(" More text.")
        markdown.set_text(markdown.get_text())
        assert markdown.get_first_child().get_next_sibling().expanded
        window.active_label = markdown
        window.finished([{"role": "assistant", "content": markdown.get_text()}], None)
        completed = window.messages.get_last_child().get_last_child()
        assert completed.get_first_child().get_next_sibling().expanded
        window.set_default_size(360, 700)
        GLib.timeout_add(400, checked, check_compact_selector)

    def check_compact_selector():
        assert 0 < window.models.get_width() < 240, window.models.get_width()
        assert window.models.get_selected_item().get_string() == "long-model-name-" * 30
        window.models.fit_popup()
        assert window.models.list_scroll.get_min_content_width() <= window.get_width() - 64
        window.models.popup()
        GLib.timeout_add(250, checked, check_narrow_popup)

    def check_narrow_popup():
        popup = window.models.get_popover()
        assert popup.get_mapped()
        assert 240 < popup.get_width() <= window.get_width(), (popup.get_width(), window.get_width())
        assert window.models.rows.get_selected_row().index == 0
        window.models.popdown()
        image = BytesIO()
        Image.new("RGB", (400, 300), "royalblue").save(image, format="PNG")
        window.capability_cache[(window.store.settings["url"], window.store.settings.get("model", ""))] = {"vision"}
        window.update_image_controls()
        window.test_image = image_attachment(image.getvalue())
        window.attachments = [window.test_image]
        window.render_attachments()
        chip = window.attachment_chips.get_child_at_index(0).get_child()
        assert isinstance(chip.get_first_child(), Gtk.Button)
        assert isinstance(chip.get_first_child().get_child(), Gtk.AspectFrame)
        message = user_message("An image", window.attachments)
        label = window.message_card("user", "An image", message["attachments"], images=message["images"])
        bubble = label.get_parent().get_parent()
        group = bubble.get_parent()
        assert group.get_last_child() is bubble and bubble.has_css_class("card")
        thumbnails = group.get_first_child()
        if hasattr(Adw, "WrapBox"):
            assert isinstance(thumbnails, Adw.WrapBox) and thumbnails.get_align() == 1
            button = thumbnails.get_first_child()
        else:
            button = thumbnails.get_child_at_index(0).get_child()
        assert isinstance(button, Gtk.Button) and button.has_css_class("sent-image")
        assert button.get_child().has_css_class("image-thumbnail")
        window.sent_image = button.get_child()
        window.draft_chip = chip
        window.attachments = []
        window.render_attachments()
        # Exercise asynchronous image pasting without replacing the user's clipboard.
        class Clipboard:
            def get_formats(self):
                return Gdk.ContentFormats.new(["image/png"])
            def read_texture_async(self, _, callback):
                GLib.idle_add(callback, self, None)
            def read_texture_finish(self, _):
                return texture(window.test_image["content"])
        assert window.paste_image(Clipboard())
        assert window.draft_loading
        GLib.timeout_add(250, checked, check_pasted_image)

    def check_pasted_image():
        if window.draft_loading:
            window.paste_waits = getattr(window, "paste_waits", 0) + 1
            assert window.paste_waits < 30, "Image worker did not finish within three seconds"
            GLib.timeout_add(100, checked, check_pasted_image)
            return
        assert not window.draft_loading
        assert len(window.attachments) == 1
        assert window.attachments[0]["kind"] == "image"
        assert window.attachments[0]["name"] == "Pasted image.png"
        assert window.attachments[0]["content"]
        assert window.sent_image.get_height() >= 72
        assert window.sent_image.get_width() <= 112
        # A rooted code block exercises the actual feedback timeout, rather
        # than only cleanup when a streamed Markdown block is rebuilt.
        window.copy_probe = CodeBlock("print(42)", "python")
        class Clipboard:
            def set(self, text):
                assert text == "print(42)"
        window.copy_probe.get_clipboard = lambda: Clipboard()
        window.messages.append(window.copy_probe)
        window.copy_probe.copy_button.emit("clicked")
        assert window.copy_probe.copy_button.get_icon_name() == "emblem-ok-symbolic"
        # Restore a wide allocation to ensure FlowBox doesn't stretch the tile.
        window.set_default_size(1080, 760)
        GLib.timeout_add(2200, checked, check_copy_reset)

    def check_copy_reset():
        assert window.long_code.copy_button.get_icon_name() == "edit-copy-symbolic"
        assert window.copy_probe.copy_button.get_icon_name() == "edit-copy-symbolic"
        assert window.copy_probe.copy_button.get_tooltip_text() == "Copy Code"
        assert window.message_copy.get_icon_name() == "edit-copy-symbolic"
        assert window.message_copy.get_tooltip_text() == "Copy Message"
        window.render_attachments()
        chip = window.attachment_chips.get_child_at_index(0).get_child()
        assert chip.get_halign() == Gtk.Align.START
        GLib.timeout_add(250, checked, final_layout)

    def final_layout():
        chip = window.attachment_chips.get_child_at_index(0).get_child()
        assert chip.get_width() < 170, chip.get_width()
        message = user_message("Eight pictures", [window.test_image] * 8)
        label = window.message_card("user", "Eight pictures", message["attachments"], images=message["images"])
        window.multi_images = label.get_parent().get_parent().get_parent().get_first_child()
        window.set_default_size(360, 700)
        GLib.timeout_add(350, checked, final_images)

    def final_images():
        assert window.multi_images.get_width() <= window.messages.get_width()
        assert window.multi_images.get_height() > 210
        window.store.settings["mcpServers"] = {"brave-search": {"command": sys.executable, "args": [str(Path(__file__).resolve().parents[1] / "tests/fixture_brave.py")], "env": {"BRAVE_API_KEY": "test-only-key"}}, "unrelated": {"command": "must-not-launch"}}
        window.brave_preferences = Preferences(window)
        window.brave_preferences.present(window)
        window.brave_preferences.brave_enabled.set_active(True)
        window.brave_preferences.test_brave(window.brave_preferences.brave_test)
        assert not window.brave_preferences.brave_test.get_sensitive()
        window.brave_poll = 0
        GLib.timeout_add(150, checked, check_brave_test)

    def check_brave_test():
        preferences = window.brave_preferences
        if preferences.test_future is not None:
            window.brave_poll += 1
            assert window.brave_poll < 60, "Brave test did not complete"
            GLib.timeout_add(150, checked, check_brave_test)
            return
        assert preferences.brave_test.get_sensitive()
        assert "working" in preferences.brave_result.get_text(), preferences.brave_result.get_text()
        assert preferences.brave_test.get_width() <= window.get_width() - 40
        assert preferences.brave_setup.get_width() <= window.get_width() - 40
        preferences.close()
        print("PASS: citation removal, draft carryover, grouped activity/response layout, conversation title header, copy feedback, Brave gating, Python formatting, readable tool names, preference persistence and existing UI behavior")
        window.worker.close()
        window.destroy()
        loop.quit()

    def checked(callback):
        try:
            callback()
        except BaseException:
            window.worker.close()
            window.destroy()
            loop.quit()
            import traceback
            traceback.print_exc()
            failures.append(True)
        return GLib.SOURCE_REMOVE
    failures = []
    GLib.timeout_add(1200, checked, finish)
    loop.run()
    if failures:
        raise SystemExit(1)
