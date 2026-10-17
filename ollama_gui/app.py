import asyncio
import concurrent.futures
import copy
import json
import threading
import uuid
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from .backend import Ollama, ToolHub, test_brave_tool
from . import __version__
from .storage import DEFAULT_SETTINGS, PYTHON_SERVER_NAME, Store, brave_enabled, validate_servers, validate_url, configure_brave, tool_servers
from .attachments import MAX_ATTACHMENTS, MAX_IMAGE_PIXELS, image_attachment, load_attachment, user_message
from .markdown_view import MarkdownView
from .tool_view import tool_view
from .tool_output import saved_tool_details, searchable_chat_text, tool_display_name
from .model_picker import ModelPicker
from .image_view import image_thumbnails, image_preview
from .attachment_view import file_preview
from .instructions import DEFAULT_INSTRUCTIONS, STOCK_INSTRUCTIONS, custom_instructions_enabled, system_instructions
from .memory import automatic_memory_enabled, memory_user_text, memory_status_text
from .personalization_view import PersonalizationPage
from .titles import clean_title, needs_title
from .title_view import FadingTitle
from .composer import ComposerScroll
from .branding import APP_ID, LumenPaintable
from .setup_view import SetupView
from . import history


class Worker:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def submit(self, coroutine, callback):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        def complete(result):
            try:
                value, error = result.result(), None
            except BaseException as exc:
                value, error = None, exc
            GLib.idle_add(callback, value, error)
        future.add_done_callback(complete)
        return future

    def close(self):
        async def stop():
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        asyncio.run_coroutine_threadsafe(stop(), self.loop).add_done_callback(lambda _: self.loop.call_soon_threadsafe(self.loop.stop))


def margins(widget, amount):
    for edge in ("top", "bottom", "start", "end"):
        getattr(widget, f"set_margin_{edge}")(amount)
    return widget


def textview(text="", editable=True):
    widget = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, editable=editable,
                          left_margin=16, right_margin=16, top_margin=16, bottom_margin=16)
    widget.get_buffer().set_text(text)
    return widget


def preferences_editor(widget, minimum, maximum):
    scroll = Gtk.ScrolledWindow(min_content_height=minimum, max_content_height=maximum,
                                propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                css_classes=["card", "preferences-editor"])
    scroll.set_overflow(Gtk.Overflow.HIDDEN)
    scroll.set_child(widget)
    return scroll


def buffer_text(widget):
    buf = widget.get_buffer()
    return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)


def menu_button(title, icon):
    button = Gtk.Button(css_classes=["flat"])
    row = Gtk.Box(spacing=12)
    row.append(Gtk.Image(icon_name=icon))
    row.append(Gtk.Label(label=title, xalign=0, hexpand=True))
    button.set_child(row)
    return button


def error_text(error):
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(error_text(item) for item in error.exceptions)
    return str(error) or type(error).__name__


class Preferences(Adw.PreferencesDialog):
    def __init__(self, window):
        super().__init__(title="Preferences")
        self.window = window
        self.set_content_width(660)
        self.set_content_height(720)
        self.loading_fields = True
        self.autosave_pending = None
        self.result = Gtk.Label(wrap=True, xalign=0)
        cfg = window.store.settings
        page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        self.general_page = page
        self.add(page)
        connection = Adw.PreferencesGroup(title="Ollama", description="Connect to your running Ollama service.")
        self.url = Adw.EntryRow(title="Server URL", text=cfg["url"])
        connection.add(self.url)
        tools_group = Adw.PreferencesGroup(title="Tools")
        tools_page = Adw.PreferencesPage(title="Tools", icon_name="applications-science-symbolic")
        self.tools_page = tools_page
        self.add(tools_page)
        tools_control = Adw.PreferencesGroup()
        tools_page.add(tools_control)
        self.tools_enabled = Adw.SwitchRow(title="Enable Tools", subtitle="Allow models to use Python, Brave Search and configured MCP tools.", active=cfg.get("tools_enabled", True))
        tools_control.add(self.tools_enabled)
        self.tools_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        tool_settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.tools_revealer.set_child(tool_settings)
        tools_control.add(self.tools_revealer)
        tool_settings.append(tools_group)
        self.tools_group = tools_group
        local_tools = Adw.PreferencesGroup()
        tools_group.add(local_tools)
        self.python_enabled = Adw.SwitchRow(title="Python", subtitle="Run Python for math, statistics and data processing.", active=cfg.get("python_enabled", True))
        local_tools.add(self.python_enabled)
        brave = Adw.PreferencesGroup(title="Brave Search", margin_top=20)
        tools_group.add(brave)
        self.brave_group = brave
        self.brave_enabled = Adw.SwitchRow(title="Enable Brave Search", subtitle="Search the web and news with your API key.", active=brave_enabled(cfg))
        brave.add(self.brave_enabled)
        self.brave_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        brave_fields = Adw.PreferencesGroup(description="Enter your API key. Changes are saved automatically.", margin_top=12)
        self.brave_revealer.set_child(brave_fields)
        brave.add(self.brave_revealer)
        self.key = Adw.PasswordEntryRow(title="API Key")
        self.key.set_text(cfg["mcpServers"].get("brave-search", {}).get("env", {}).get("BRAVE_API_KEY", ""))
        self.initial_brave_key = self.key.get_text()
        brave_fields.add(self.key)
        if hasattr(Adw, "WrapBox"):
            brave_buttons = Adw.WrapBox(child_spacing=8, line_spacing=8, align=1, natural_line_length=360,
                                        margin_top=12, margin_bottom=12)
        else:
            brave_buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=12, margin_bottom=12)
        self.brave_test = Gtk.Button(label="Test Brave Search", tooltip_text="Run a sample web search to check your API key and search tool.")
        self.brave_test.connect("clicked", self.test_brave)
        brave_buttons.append(self.brave_test)
        self.brave_setup = Gtk.Button(label="Set Up Brave Search", css_classes=["brave-setup"])
        self.brave_setup.connect("clicked", self.add_brave)
        brave_buttons.append(self.brave_setup)
        brave_fields.add(brave_buttons)
        self.brave_result = Gtk.Label(wrap=True, xalign=0)
        brave_fields.add(self.brave_result)
        brave_help = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12)
        brave_help.append(Gtk.Label(label="How to get an API key", xalign=0, css_classes=["heading"]))
        brave_help.append(Gtk.Label(
            label="1. Sign in or create an account in the Brave Search API dashboard.\n2. Choose and activate an API plan.\n3. Open API Keys, create a key, and paste it above.\n4. Select Test Brave Search to check your connection.",
            wrap=True, xalign=0))
        brave_help.append(Gtk.LinkButton(uri="https://api-dashboard.search.brave.com/", label="Open Brave Search Dashboard", halign=Gtk.Align.START))
        brave_help.append(Gtk.Label(label="Searches use your Brave Search API plan.", wrap=True, xalign=0, css_classes=["dim-label", "caption"]))
        brave_fields.add(brave_help)
        self.key.connect("changed", self.update_brave_button)
        self.brave_enabled.connect("notify::active", self.update_brave_fields)
        conversations = Adw.PreferencesGroup(title="Conversations")
        page.add(conversations)
        self.auto_titles = Adw.SwitchRow(title="Automatically Name Conversations", subtitle="Ask the model for a short title after the first reply.", active=cfg.get("auto_titles", True))
        conversations.add(self.auto_titles)
        self.personalization = PersonalizationPage(self)
        self.add(self.personalization)
        advanced = Adw.PreferencesPage(title="Advanced", icon_name="preferences-other-symbolic")
        self.advanced_page = advanced
        self.add(advanced)
        display = Adw.PreferencesGroup(title="Response Display")
        page.add(display)
        self.show_thinking = Adw.SwitchRow(title="Show Model Thinking", subtitle="Display reasoning returned by models that support it.", active=cfg.get("show_thinking", False))
        self.friendly_search = Adw.SwitchRow(title="Format Brave Search Calls", subtitle="Show search queries and links instead of tool names and JSON.", active=cfg.get("friendly_search", True))
        self.friendly_python = Adw.SwitchRow(title="Format Python Calls", subtitle="Show executed code and results instead of raw JSON.", active=cfg.get("friendly_python", True))
        display.add(self.show_thinking)
        tool_display = Adw.PreferencesGroup(title="Tool Display")
        tool_settings.append(tool_display)
        tool_display.add(self.friendly_search)
        tool_display.add(self.friendly_python)
        advanced.add(connection)
        math = Adw.PreferencesGroup(title="Equations")
        advanced.add(math)
        self.latex_enabled = Adw.SwitchRow(title="LaTeX Equations Support", subtitle="Render inline and display equations in replies and model thinking.", active=cfg.get("latex_enabled", True))
        math.add(self.latex_enabled)
        prompt = Adw.PreferencesGroup(title="Assistant Instructions", description="The defaults cover tools, personalization and memory. Your enabled profile, saved memories, equation guidance and current local time are also added to custom instructions.")
        advanced.add(prompt)
        self.custom_system = Adw.SwitchRow(title="Use Custom Assistant Instructions", active=custom_instructions_enabled(cfg))
        prompt.add(self.custom_system)
        self.custom_warning = Gtk.Label(label="Custom instructions replace Lumen's default guidance. Conflicting instructions may cause tools or memory to work incorrectly.", wrap=True, xalign=0, css_classes=["warning", "caption"], margin_top=8, margin_bottom=8)
        prompt.add(self.custom_warning)
        self.system = textview(DEFAULT_INSTRUCTIONS if cfg["system"] in STOCK_INSTRUCTIONS else cfg["system"])
        self.system_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.system_revealer.set_child(preferences_editor(self.system, 180, 280))
        prompt.add(self.system_revealer)
        self.custom_system.connect("notify::active", self.update_advanced_editors)
        tools = Adw.PreferencesGroup(title="MCP Servers", description="Brave Search is configured on the Tools page. For other servers, enable custom configuration and supply mcpServers JSON with command / args / env, or url / headers for Streamable HTTP. Add servers you trust.")
        advanced.add(tools)
        self.custom_mcp = Adw.SwitchRow(title="Edit Custom MCP Configuration", subtitle="Saved servers keep working when this editor is hidden.", active=cfg.get("custom_mcp_enabled", False))
        tools.add(self.custom_mcp)
        self.servers = textview(json.dumps({"mcpServers": cfg["mcpServers"]}, indent=2))
        self.servers.set_monospace(True)
        self.servers.get_buffer().connect("changed", self.update_brave_button)
        self.servers_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.servers_revealer.set_child(preferences_editor(self.servers, 180, 320))
        tools.add(self.servers_revealer)
        self.custom_mcp.connect("notify::active", self.update_advanced_editors)
        apply = Adw.PreferencesGroup()
        page.add(apply)
        apply.add(self.result)
        tools_apply = Adw.PreferencesGroup()
        tools_page.add(tools_apply)
        tools_result = Gtk.Label(wrap=True, xalign=0)
        self.result.bind_property("label", tools_result, "label", 2)
        tools_apply.add(tools_result)
        advanced_apply = Adw.PreferencesGroup()
        advanced.add(advanced_apply)
        advanced_apply.add(self.preference_buttons(advanced=True))
        advanced_result = Gtk.Label(wrap=True, xalign=0)
        self.result.bind_property("label", advanced_result, "label", 2)
        advanced_apply.add(advanced_result)
        reset_group = Adw.PreferencesGroup(title="Settings")
        page.add(reset_group)
        reset_row = Adw.ActionRow(title="Reset to Default Settings", subtitle="Restore preferences, clear your profile, and remove MCP configurations and API keys. Conversations and saved memories are kept.")
        self.reset_button = Gtk.Button(label="Reset…", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        self.reset_button.connect("clicked", self.reset_defaults)
        reset_row.add_suffix(self.reset_button)
        reset_row.set_activatable_widget(self.reset_button)
        reset_group.add(reset_row)
        erase_row = Adw.ActionRow(title="Reset All Data", subtitle="Delete all conversations, memories, profile details, drafts, attachments and preferences from this app.")
        self.erase_button = Gtk.Button(label="Reset All Data…", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        self.erase_button.connect("clicked", self.reset_all_data)
        erase_row.add_suffix(self.erase_button)
        erase_row.set_activatable_widget(self.erase_button)
        reset_group.add(erase_row)
        self.test_future = None
        self.test_button = None
        self.test_generation = 0
        self.connect("closed", lambda *_: self.cancel_test())
        self.update_advanced_editors()
        self.update_brave_button()
        self.update_brave_fields()
        self.tools_enabled.connect("notify::active", self.update_tools_fields)
        self.update_tools_fields()
        self.loading_fields = False
        for toggle in (self.tools_enabled, self.python_enabled, self.brave_enabled, self.auto_titles, self.show_thinking, self.friendly_search, self.friendly_python, self.latex_enabled, self.custom_system, self.custom_mcp):
            toggle.connect("notify::active", self.autosave_switch)
        for field in (self.url, self.key):
            field.connect("changed", self.queue_autosave)
        for editor in (self.system, self.servers):
            editor.get_buffer().connect("changed", self.queue_autosave)
        self.personalization.connect_changes()
        self.connect("closed", self.preferences_closed)

    def preferences_closed(self, *_):
        self.personalization.close()
        if self.autosave_pending is not None:
            self.flush_autosave()

    def autosave_switch(self, *_):
        if not self.loading_fields:
            self.flush_autosave()

    def queue_autosave(self, *_):
        if self.loading_fields:
            return
        if self.autosave_pending is not None:
            GLib.source_remove(self.autosave_pending)
        self.autosave_pending = GLib.timeout_add(450, self.flush_autosave)

    def flush_autosave(self, *_):
        if self.autosave_pending is not None:
            GLib.source_remove(self.autosave_pending)
            self.autosave_pending = None
        if not self.loading_fields:
            self.save()
        return GLib.SOURCE_REMOVE

    def update_tools_fields(self, *_):
        enabled = self.tools_enabled.get_active()
        self.tools_revealer.set_visible(enabled)
        self.tools_revealer.set_reveal_child(enabled)
        if not enabled:
            self.cancel_test()

    def update_brave_fields(self, *_):
        enabled = self.brave_enabled.get_active()
        self.brave_revealer.set_visible(enabled)
        self.brave_revealer.set_reveal_child(enabled)
        if not enabled and self.test_button is self.brave_test:
            self.cancel_test()
        self.update_brave_button()

    def preference_buttons(self, advanced=False):
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        if advanced:
            self.advanced_test = Gtk.Button(label="Test Servers", visible=self.custom_mcp.get_active())
            self.advanced_test.connect("clicked", self.test_servers)
            buttons.append(self.advanced_test)
        return buttons

    def update_advanced_editors(self, *_):
        for toggle, editor, revealer in ((self.custom_system, self.system, self.system_revealer),
                                          (self.custom_mcp, self.servers, self.servers_revealer)):
            enabled = toggle.get_active()
            editor.set_editable(enabled)
            editor.set_sensitive(enabled)
            # Hiding also removes the editor and any secret values from focus
            # navigation and accessibility until customization is enabled.
            revealer.set_reveal_child(enabled)
            revealer.set_visible(enabled)
        self.update_brave_button()
        if hasattr(self, "advanced_test"):
            self.advanced_test.set_visible(self.custom_mcp.get_active())
            if not self.custom_mcp.get_active() and self.test_button is self.advanced_test:
                self.cancel_test()

    def update_brave_button(self, *_):
        saved = self.window.store.settings["mcpServers"].get("brave-search", {})
        dirty = self.key.get_text().strip() != saved.get("env", {}).get("BRAVE_API_KEY", "")
        dirty = dirty or self.brave_enabled.get_active() != brave_enabled(self.window.store.settings)
        if hasattr(self, "servers") and self.custom_mcp.get_active():
            try:
                current = json.loads(buffer_text(self.servers)).get("mcpServers", {}).get("brave-search", {})
                dirty = dirty or current != saved
            except (ValueError, AttributeError):
                pass
        if dirty:
            self.brave_setup.add_css_class("suggested-action")
        else:
            self.brave_setup.remove_css_class("suggested-action")

    def load_saved_fields(self):
        self.loading_fields = True
        cfg = self.window.store.settings
        self.url.set_text(cfg["url"])
        self.system.get_buffer().set_text(DEFAULT_INSTRUCTIONS if cfg["system"] in STOCK_INSTRUCTIONS else cfg["system"])
        self.personalization.load(cfg)
        self.custom_system.set_active(custom_instructions_enabled(cfg))
        self.custom_mcp.set_active(cfg.get("custom_mcp_enabled", False))
        self.tools_enabled.set_active(cfg.get("tools_enabled", True))
        self.update_tools_fields()
        self.python_enabled.set_active(cfg.get("python_enabled", True))
        self.auto_titles.set_active(cfg.get("auto_titles", True))
        self.show_thinking.set_active(cfg.get("show_thinking", False))
        self.friendly_search.set_active(cfg.get("friendly_search", True))
        self.friendly_python.set_active(cfg.get("friendly_python", True))
        self.latex_enabled.set_active(cfg.get("latex_enabled", True))
        self.brave_enabled.set_active(brave_enabled(cfg))
        key = cfg["mcpServers"].get("brave-search", {}).get("env", {}).get("BRAVE_API_KEY", "")
        self.key.set_text(key)
        self.initial_brave_key = key
        self.servers.get_buffer().set_text(json.dumps({"mcpServers": cfg["mcpServers"]}, indent=2))
        self.update_advanced_editors()
        self.update_brave_button()
        self.update_brave_fields()
        self.loading_fields = False

    def reset_all_data(self, *_):
        dialog = Adw.AlertDialog(heading="Reset All App Data?", body="Permanently delete every conversation, saved memory, profile detail, attachment, draft, API key and preference in this app. This cannot be undone.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("erase", "Reset All Data")
        dialog.set_response_appearance("erase", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        def response(_, value):
            if value != "erase" or self.window.busy or self.window.draft_loading:
                return
            try:
                self.cancel_test()
                self.window.reset_all_data()
                self.load_saved_fields()
                self.result.set_text("All app data reset.")
            except Exception as exc:
                self.result.set_text(str(exc))
        dialog.connect("response", response)
        dialog.present(self)
        return dialog

    def cancel_test(self):
        self.test_generation += 1
        if self.test_future:
            self.test_future.cancel()
            self.test_future = None
        if self.test_button is not None:
            self.test_button.set_sensitive(True)
            self.test_button = None

    def reset_defaults(self, *_):
        dialog = Adw.AlertDialog(heading="Reset Preferences?", body="Restore the default connection and instructions, clear your name and profile, and remove saved MCP servers and API keys. Your conversations and saved memories will be kept.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        def response(_, value):
            if value != "reset":
                return
            try:
                cfg = copy.deepcopy(DEFAULT_SETTINGS)
                self.window.store.write("settings.json", cfg)
                self.window.store.settings = cfg
                self.window.cancel_memories()
                self.window.memory_status = memory_status_text(cfg)
                self.cancel_test()
                self.load_saved_fields()
                self.result.set_text("Default settings restored.")
                self.window.refresh_models()
                self.window.refresh_tools()
                self.window.render_chat()
            except Exception as exc:
                self.result.set_text(str(exc))
        dialog.connect("response", response)
        dialog.present(self)
        return dialog

    def parsed(self):
        if not self.custom_mcp.get_active():
            # A hidden/stale JSON editor must not undo Brave setup or tool
            # selections saved elsewhere in the app.
            return configure_brave(self.window.store.settings["mcpServers"], self.key.get_text(), self.initial_brave_key)
        value = json.loads(buffer_text(self.servers))
        if not isinstance(value, dict) or "mcpServers" not in value:
            raise ValueError('Supply an object containing "mcpServers".')
        servers = validate_servers(value["mcpServers"])
        return configure_brave(servers, self.key.get_text(), self.initial_brave_key)

    def add_brave(self, _):
        try:
            if not self.key.get_text().strip():
                raise ValueError("Enter your Brave Search API key first.")
            servers = self.parsed()
            servers = configure_brave(servers, self.key.get_text())
            saved = copy.deepcopy(self.window.store.settings["mcpServers"])
            saved["brave-search"] = servers["brave-search"]
            saved["brave-search"]["enabled"] = True
            cfg = {**self.window.store.settings, "mcpServers": saved, "brave_enabled": True, "tools_enabled": self.tools_enabled.get_active()}
            self.window.store.write("settings.json", cfg)
            self.window.store.settings = cfg
            self.brave_enabled.set_active(True)
            self.initial_brave_key = self.key.get_text().strip()
            self.servers.get_buffer().set_text(json.dumps({"mcpServers": servers}, indent=2))
            self.update_brave_button()
            self.window.refresh_tools()
            self.brave_result.set_text("Brave Search saved. Search tools will appear in the Tools menu.")
        except Exception as exc:
            self.brave_result.set_text(str(exc))

    def test_brave(self, button):
        if not self.brave_enabled.get_active():
            return
        servers = configure_brave(self.window.store.settings["mcpServers"], self.key.get_text())
        self.run_test(button, test_brave_tool(servers), self.brave_result, "Testing Brave Search…")

    def run_test(self, button, coroutine, result, progress):
        self.cancel_test()
        generation = self.test_generation
        button.set_sensitive(False)
        self.test_button = button
        result.set_text(progress)
        def done(value, error):
            if generation != self.test_generation:
                return
            self.test_future = None
            self.test_button = None
            button.set_sensitive(True)
            result.set_text(error_text(error) if error else value)
        self.test_future = self.window.worker.submit(coroutine, done)

    def test_servers(self, button):
        if not self.custom_mcp.get_active():
            return
        try:
            servers = self.parsed()
            if not self.brave_enabled.get_active():
                servers.pop("brave-search", None)
        except Exception as exc:
            self.result.set_text(str(exc))
            return
        async def test():
            async with asyncio.timeout(90):
                async with ToolHub(servers) as hub:
                    return f"Connected. {len(hub.tools)} tools available."
        self.run_test(button, test(), self.result, "Connecting to MCP servers…")

    def save(self, _=None):
        if self.loading_fields:
            return
        try:
            previous = self.window.store.settings
            key_changed = self.key.get_text().strip() != self.initial_brave_key.strip()
            errors = self.personalization.validation_errors()
            try:
                url = validate_url(self.url.get_text().strip())
            except ValueError as exc:
                url = previous["url"]
                errors.append(str(exc))
            try:
                servers = self.parsed()
            except (ValueError, TypeError) as exc:
                servers = copy.deepcopy(previous["mcpServers"])
                errors.append(str(exc))
            cfg = {**self.window.store.settings, "url": url,
                   **self.personalization.values(),
                   "system": buffer_text(self.system), "custom_system_enabled": self.custom_system.get_active(),
                   "custom_mcp_enabled": self.custom_mcp.get_active(), "mcpServers": servers,
                   "tools_enabled": self.tools_enabled.get_active(),
                   "python_enabled": self.python_enabled.get_active(), "auto_titles": self.auto_titles.get_active(),
                   "show_thinking": self.show_thinking.get_active(), "friendly_search": self.friendly_search.get_active(),
                   "friendly_python": self.friendly_python.get_active(), "brave_enabled": self.brave_enabled.get_active(),
                   "latex_enabled": self.latex_enabled.get_active()}
            if "brave-search" in cfg["mcpServers"]:
                cfg["mcpServers"]["brave-search"]["enabled"] = cfg["brave_enabled"]
            if cfg != previous:
                self.window.store.write("settings.json", cfg)
                self.window.store.settings = cfg
                if any(cfg.get(key) != previous.get(key) for key in ("memory_enabled", "auto_memory_enabled", "url")):
                    self.window.cancel_memories()
                    self.window.memory_status = memory_status_text(cfg)
                if not cfg["auto_titles"]:
                    self.window.cancel_titles()
                display_keys = ("show_thinking", "friendly_search", "friendly_python", "latex_enabled")
                if not self.window.busy and any(cfg.get(key) != previous.get(key) for key in display_keys):
                    self.window.render_chat()
                if cfg["url"] != previous["url"]:
                    self.window.refresh_models()
                tool_keys = ("mcpServers", "tools_enabled", "python_enabled", "brave_enabled")
                if any(cfg.get(key) != previous.get(key) for key in tool_keys):
                    self.window.render_tool_choices()
                    self.window.refresh_tools()
                if cfg["auto_titles"] and not previous.get("auto_titles", True):
                    self.window.request_title(self.window.current)
            if not errors:
                self.initial_brave_key = self.key.get_text().strip()
                if key_changed or not self.custom_mcp.get_active():
                    self.loading_fields = True
                    self.servers.get_buffer().set_text(json.dumps({"mcpServers": cfg["mcpServers"]}, indent=2))
                    self.loading_fields = False
            self.update_brave_button()
            self.result.set_text("; ".join(errors))
        except Exception as exc:
            self.result.set_text(str(exc))


class Window(Adw.ApplicationWindow):
    def __init__(self, app, store=None):
        super().__init__(application=app, title="Lumen", default_width=1080, default_height=760)
        self.store = store or Store()
        self.setup = None
        self.worker = Worker()
        self.current = None
        self.future = None
        self.active_label = None
        self.active_tool = None
        self.active_reasoning = None
        self.activity_box = None
        self.round_boundary = False
        self.follow_response = True
        self.scroll_pending = None
        self.scrolling_transcript = False
        self.model_names = []
        self.capability_cache = {}
        self.capability_errors = {}
        self.capability_jobs = {}
        self.attachments = []
        self.pending_attachments = []
        self.revision_parent = None
        self.reply_model = ""
        self.thinking_label = None
        self.thinking_card = None
        self.thinking_spinner = None
        self.tool_catalog = []
        self.tool_errors = []
        self.tools_loading = False
        self.tools_future = None
        self.busy = False
        self.draft_loading = False
        self.drafts = {}
        self.turn_generation = 0
        self.closed = False
        self.title_jobs = {}
        self.memory_future = None
        self.memory_queue = []
        self.memory_generation = 0
        self.memory_status = memory_status_text(self.store.settings)
        icons = Gtk.IconTheme.get_for_display(self.get_display())
        icons.add_search_path(str(Path(__file__).parent / "icons"))
        self.set_icon_name(APP_ID)
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .message-composer textview, .message-composer textview text,
            .markdown-code textview, .markdown-code textview text,
            .preferences-editor textview, .preferences-editor textview text { background: transparent; }
            .math-paragraph, .math-paragraph text { background: transparent; }
            .message-composer { padding: 8px; }
            .brave-setup { padding: 10px 20px; }
            .composer-model > button { border-radius: 9999px; }
            .composer-model > button:not(:hover):not(:checked) { background: transparent; box-shadow: none; }
            .chat-transcript label, .chat-transcript textview,
            .read-only-output label { caret-color: transparent; -gtk-secondary-caret-color: transparent; }
            .attachment-chip { padding: 2px 8px; border-radius: 12px; background: alpha(currentColor, 0.07); }
            .attachment-list > flowboxchild,
            .attachment-list > flowboxchild:hover,
            .attachment-list > flowboxchild:active,
            .attachment-list > flowboxchild:selected { background: transparent; box-shadow: none; padding: 0; border: none; }
            .image-thumbnail { border-radius: 12px; }
            .sent-image { padding: 0; border-radius: 12px; }
            .markdown-quote { border-left: 3px solid alpha(currentColor, 0.25); padding-left: 12px; }
            .markdown-table-cell { padding: 8px; border-bottom: 1px solid alpha(currentColor, 0.12); }
            .conversation-menu { opacity: 0; }
            .conversation-menu.options-visible { opacity: 1; }
        """)
        Gtk.StyleContext.add_provider_for_display(self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.toast = Adw.ToastOverlay()
        self.set_content(self.toast)
        self.split = Adw.OverlaySplitView(sidebar_width_fraction=0.30, min_sidebar_width=280, max_sidebar_width=340)
        self.toast.set_child(self.split)
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 760sp"))
        breakpoint.add_setter(self.split, "collapsed", True)
        self.add_breakpoint(breakpoint)
        self.build_sidebar()
        self.build_chat()
        self.actions()
        self.connect("close-request", self.on_close)
        if self.store.needs_setup:
            self.setup = SetupView(self.store.settings, self.lumen_paintable, self.finish_setup)
            self.toast.set_child(self.setup)
            self.update_actions()
        else:
            self.start_chat()

    def finish_setup(self, settings):
        self.store.write("settings.json", settings)
        self.store.settings = settings
        self.memory_status = memory_status_text(settings)
        self.setup = None
        self.toast.set_child(self.split)
        self.start_chat()

    def start_chat(self):
        if self.store.chats:
            self.current = self.store.chats[0]
        else:
            self.new_chat()
        self.render_sidebar()
        self.render_chat()
        self.refresh_models()
        self.refresh_tools()
        self.update_actions()

    def actions(self):
        for name, callback in (("new", lambda *_: self.new_chat()), ("preferences", lambda *_: Preferences(self).present(self)), ("personalization", self.show_personalization), ("refresh", lambda *_: self.refresh_models()), ("delete", self.delete_chat), ("search", lambda *_: self.open_search()), ("about", self.show_about)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        self.get_application().set_accels_for_action("win.new", ["<Control>n"])
        self.get_application().set_accels_for_action("win.preferences", ["<Control>comma"])
        self.get_application().set_accels_for_action("win.search", ["<Control>f"])

    def show_personalization(self, *_):
        dialog = Preferences(self)
        dialog.set_visible_page(dialog.personalization)
        dialog.present(self)
        return dialog

    def show_about(self, *_):
        dialog = Adw.AboutDialog(
            application_name="Lumen",
            application_icon=APP_ID,
            version=__version__,
            developer_name="Lumen Team",
            developers=["Lumen Team"],
            comments="A native GNOME chat app for Ollama with MCP tools.",
            website="https://github.com/wfoyt/Lumen",
            issue_url="https://github.com/wfoyt/Lumen/issues",
        )
        dialog.present(self)
        return dialog

    def build_sidebar(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        header.set_title_widget(Gtk.Label(label="Lumen", ellipsize=Pango.EllipsizeMode.END, css_classes=["heading"]))
        self.search_button = Gtk.ToggleButton(icon_name="edit-find-symbolic", tooltip_text="Search Conversations (Ctrl+F)")
        header.pack_start(self.search_button)
        self.new_chat_button = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="New Conversation (Ctrl+N)", action_name="win.new")
        menu = Gio.Menu()
        menu.append("Preferences", "win.preferences")
        menu.append("Refresh Models", "win.refresh")
        menu.append("About Lumen", "win.about")
        self.app_menu = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Main Menu", menu_model=menu)
        self.sidebar_controls = Gtk.Box(spacing=6)
        self.sidebar_controls.append(self.new_chat_button)
        self.sidebar_controls.append(self.app_menu)
        header.pack_end(self.sidebar_controls)
        toolbar.add_top_bar(header)
        self.chat_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
        self.chat_list.connect("row-activated", self.select_chat)
        self.search_query = ""
        self.chat_list.set_filter_func(lambda row: self.search_query in row.search_text)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.chat_list)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search_entry = Gtk.SearchEntry(placeholder_text="Search conversations")
        self.search_entry.connect("changed", lambda *_: self.update_search())
        self.search_entry.connect("activate", self.open_first_search_result)
        self.search_bar = Gtk.SearchBar()
        self.search_bar.set_child(self.search_entry)
        self.search_bar.connect_entry(self.search_entry)
        self.search_bar.set_key_capture_widget(toolbar)
        self.search_bar.bind_property("search-mode-enabled", self.search_button, "active", 3)
        self.search_bar.connect("notify::search-mode-enabled", self.search_mode_changed)
        box.append(self.search_bar)
        self.sidebar_results = Gtk.Stack(vexpand=True)
        self.sidebar_results.add_named(scroll, "results")
        self.sidebar_results.add_named(margins(Gtk.Label(label="No matching conversations", wrap=True, valign=Gtk.Align.START, css_classes=["dim-label"]), 18), "empty")
        box.append(self.sidebar_results)
        toolbar.set_content(box)
        self.split.set_sidebar(toolbar)

    def build_chat(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.sidebar_toggle = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Show Conversations")
        self.split.bind_property("show-sidebar", self.sidebar_toggle, "active", 3)
        self.chat_header_controls = Gtk.Box(spacing=6)
        self.chat_header_controls.append(self.sidebar_toggle)
        header.pack_start(self.chat_header_controls)
        self.split.connect("notify::show-sidebar", self.move_new_chat_button)
        self.move_new_chat_button()
        self.chat_title = Gtk.Label(label="New Conversation", ellipsize=Pango.EllipsizeMode.END,
                                    single_line_mode=True, max_width_chars=40, css_classes=["heading"])
        header.set_title_widget(self.chat_title)
        toolbar.add_top_bar(header)
        self.models = ModelPicker(model=Gtk.StringList.new(["No models available"]))
        self.models.set_hexpand(True)
        self.models.set_tooltip_text("Choose an installed Ollama model")
        self.models.connect("notify::selected", self.model_selected)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, css_classes=["chat-transcript"])
        margins(self.messages, 24)
        self.lumen_paintable = LumenPaintable()
        self.empty = Adw.StatusPage(paintable=self.lumen_paintable, title="A conversation starts here", description="Choose a model and ask a question. Use + to attach files or images, and the Tools menu to choose tools.")
        self.stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=200)
        self.stack.add_named(self.empty, "empty")
        clamp = Adw.Clamp(maximum_size=800, tightening_threshold=600)
        clamp.set_child(self.messages)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll.set_child(clamp)
        self.scroll.get_vadjustment().connect("changed", self.transcript_resized)
        self.scroll.get_vadjustment().connect("value-changed", self.transcript_scrolled)
        self.stack.add_named(self.scroll, "messages")
        content.append(self.stack)
        composer = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), 24)
        self.composer_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["card", "message-composer"])
        composer.append(self.composer_card)
        self.attachment_chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1,
                                            max_children_per_line=4, css_classes=["attachment-list"])
        margins(self.attachment_chips, 8)
        self.attachment_chips.set_visible(False)
        self.composer_card.append(self.attachment_chips)
        self.input_scroll = ComposerScroll()
        self.input = self.input_scroll.view
        self.input.set_accepts_tab(False)
        self.input.set_tooltip_text("Message Lumen · Enter to send · Shift+Enter for a new line")
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.input_key)
        self.input.add_controller(keys)
        self.input.connect("paste-clipboard", self.paste_clipboard)
        overlay = Gtk.Overlay()
        overlay.set_child(self.input_scroll)
        placeholder = Gtk.Label(label="Message Lumen…", xalign=0, valign=Gtk.Align.START, halign=Gtk.Align.START, margin_top=16, margin_start=16, css_classes=["dim-label"])
        placeholder.set_can_target(False)
        overlay.add_overlay(placeholder)
        self.input.get_buffer().connect("changed", lambda buf: placeholder.set_visible(buf.get_char_count() == 0))
        self.composer_card.append(overlay)
        controls = margins(Gtk.Box(spacing=6), 8)
        self.plus = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text="Add Files or Images", css_classes=["flat", "circular"])
        self.plus_menu = Gtk.Popover()
        menu_box = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), 6)
        for title, icon, kind in (("Add Files…", "document-new-symbolic", "file"), ("Add Images…", "insert-image-symbolic", "image")):
            button = Gtk.Button(css_classes=["flat"])
            row = Gtk.Box(spacing=12)
            row.append(Gtk.Image(icon_name=icon))
            row.append(Gtk.Label(label=title, xalign=0, hexpand=True))
            button.set_child(row)
            button.connect("clicked", lambda _, value=kind: self.choose_attachments(value))
            if kind == "image":
                self.images_button = button
                button.set_sensitive(False)
                button.set_tooltip_text("Choose a vision model to attach images")
            menu_box.append(button)
        self.plus_menu.set_child(menu_box)
        self.plus.set_popover(self.plus_menu)
        controls.append(self.plus)
        self.tools_button = Gtk.MenuButton(icon_name="applications-science-symbolic", tooltip_text="Tools", css_classes=["flat", "circular"], visible=self.store.settings.get("tools_enabled", True))
        self.tools_menu = Gtk.Popover()
        tools_box = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), 6)
        self.tool_choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        tool_scroll = Gtk.ScrolledWindow(max_content_height=280, min_content_width=260, propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        tool_scroll.set_child(self.tool_choices)
        tools_box.append(tool_scroll)
        self.refresh_tools_button = Gtk.Button(label="Refresh Tools", css_classes=["flat"])
        self.refresh_tools_button.connect("clicked", lambda *_: self.refresh_tools())
        tools_box.append(self.refresh_tools_button)
        self.tools_menu.set_child(tools_box)
        self.tools_button.set_popover(self.tools_menu)
        controls.append(self.tools_button)
        self.model_clamp = Adw.Clamp(maximum_size=240, tightening_threshold=240, hexpand=False)
        self.model_clamp.set_child(self.models)
        controls.append(self.model_clamp)
        controls.append(Gtk.Box(hexpand=True))
        self.tool_indicator = Gtk.Label(css_classes=["dim-label"], visible=False)
        controls.append(self.tool_indicator)
        self.send = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Send Message", css_classes=["suggested-action", "circular"])
        self.send.connect("clicked", self.send_or_stop)
        controls.append(self.send)
        self.composer_card.append(controls)
        clamp_bottom = Adw.Clamp(maximum_size=800)
        clamp_bottom.set_child(composer)
        content.append(clamp_bottom)
        toolbar.set_content(content)
        self.split.set_content(toolbar)

    def notify(self, message):
        self.toast.add_toast(Adw.Toast(title=message))

    def move_new_chat_button(self, *_):
        target = self.sidebar_controls if self.split.get_show_sidebar() else self.chat_header_controls
        parent = self.new_chat_button.get_parent()
        if parent is not target:
            parent.remove(self.new_chat_button)
            if target is self.sidebar_controls:
                target.prepend(self.new_chat_button)
            else:
                target.append(self.new_chat_button)

    def open_search(self):
        self.split.set_show_sidebar(True)
        self.search_bar.set_search_mode(True)
        self.search_entry.grab_focus()

    def search_mode_changed(self, *_):
        if self.search_bar.get_search_mode():
            self.search_entry.grab_focus()
        else:
            self.search_entry.set_text("")

    def update_search(self):
        self.search_query = self.search_entry.get_text().strip().casefold()
        row = self.chat_list.get_first_child()
        while row:
            row.search_text = searchable_chat_text(row.chat)
            row = row.get_next_sibling()
        self.chat_list.invalidate_filter()
        matches = any(self.search_query in searchable_chat_text(chat) for chat in self.store.chats)
        self.sidebar_results.set_visible_child_name("results" if matches else "empty")

    def open_first_search_result(self, *_):
        if self.busy or self.draft_loading:
            return
        row = self.chat_list.get_first_child()
        while row:
            if self.search_query in row.search_text:
                self.select_chat(self.chat_list, row)
                break
            row = row.get_next_sibling()

    def refresh_tools(self):
        if self.future:
            return
        # Stale discovery callbacks cannot overwrite a newer configuration.
        generation = getattr(self, "tools_generation", 0) + 1
        self.tools_generation = generation
        if self.tools_future:
            self.tools_future.cancel()
        servers = tool_servers(self.store.settings)
        self.tools_loading = True
        self.render_tool_choices()
        async def discover():
            catalog, errors = [], []
            for name, cfg in servers.items():
                if not cfg.get("enabled", True):
                    continue
                try:
                    async with asyncio.timeout(90):
                        async with ToolHub({name: cfg}) as hub:
                            catalog.extend(hub.catalog)
                except Exception as exc:
                    errors.append(f"{name}: {error_text(exc)}")
            return catalog, errors
        def done(value, error):
            if self.closed or generation != self.tools_generation:
                return
            self.tools_loading = False
            self.tools_future = None
            if error:
                self.tool_catalog, self.tool_errors = [], [error_text(error)]
            else:
                self.tool_catalog, self.tool_errors = value
            self.render_tool_choices()
        self.tools_future = self.worker.submit(discover(), done)

    def render_tool_choices(self):
        self.tools_button.set_visible(self.store.settings.get("tools_enabled", True))
        while child := self.tool_choices.get_first_child():
            self.tool_choices.remove(child)
        self.refresh_tools_button.set_sensitive(self.store.settings.get("tools_enabled", True) and not self.tools_loading and not self.future)
        if not self.store.settings.get("tools_enabled", True):
            self.tool_choices.append(margins(Gtk.Label(label="Tools are disabled. Enable them in Preferences → Tools.", wrap=True, max_width_chars=32, xalign=0, css_classes=["dim-label"]), 8))
        elif self.tools_loading:
            self.tool_choices.append(margins(Gtk.Label(label="Discovering tools…", xalign=0, css_classes=["dim-label"]), 8))
        else:
            last_server = None
            for tool in self.tool_catalog:
                cfg = self.tool_configuration(tool["server"])
                if cfg is None or not cfg.get("enabled", True):
                    continue
                if last_server != tool["server"]:
                    server_title = {"brave-search": "Brave Search", PYTHON_SERVER_NAME: "Python"}.get(tool["server"], tool["server"])
                    self.tool_choices.append(Gtk.Label(label=server_title, xalign=0, margin_start=8, margin_top=6, css_classes=["dim-label"]))
                    last_server = tool["server"]
                toggle = Gtk.CheckButton(label=tool_display_name(tool["name"]), active=tool["name"] not in cfg.get("disabled_tools", []), margin_start=8, margin_end=8, tooltip_text=tool["description"])
                toggle.set_sensitive(not self.future)
                toggle.connect("toggled", lambda button, item=tool: self.toggle_tool(item, button.get_active()))
                self.tool_choices.append(toggle)
            if not self.tool_catalog and not self.tool_errors:
                self.tool_choices.append(margins(Gtk.Label(label="No tools found. Add an MCP server in Preferences.", wrap=True, max_width_chars=32, xalign=0, css_classes=["dim-label"]), 8))
            for error in self.tool_errors:
                self.tool_choices.append(margins(Gtk.Label(label=error, wrap=True, max_width_chars=32, xalign=0, css_classes=["error"]), 8))
        self.update_tool_indicator()

    def toggle_tool(self, tool, enabled):
        cfg = self.tool_configuration(tool["server"])
        if cfg is None or self.future:
            return
        disabled = set(cfg.get("disabled_tools", []))
        if enabled:
            disabled.discard(tool["name"])
        else:
            disabled.add(tool["name"])
        if tool["server"] == PYTHON_SERVER_NAME:
            self.store.settings["python_enabled"] = enabled
        else:
            cfg["disabled_tools"] = sorted(disabled)
        self.save_store()
        self.update_tool_indicator()

    def update_tool_indicator(self):
        count = sum(1 for tool in self.tool_catalog if (cfg := self.tool_configuration(tool["server"])) is not None and cfg.get("enabled", True) and tool["name"] not in cfg.get("disabled_tools", []))
        self.tool_indicator.set_label(f"{count} tool{'s' if count != 1 else ''}")
        self.tool_indicator.set_visible(count > 0)

    def servers_for_chat(self):
        servers = tool_servers(self.store.settings)
        if not self.store.settings.get("python_enabled", True):
            servers.pop(PYTHON_SERVER_NAME, None)
        for name in list(servers):
            known = [tool["name"] for tool in self.tool_catalog if tool["server"] == name]
            if known and all(tool in servers[name].get("disabled_tools", []) for tool in known):
                del servers[name]
        return servers

    def tool_configuration(self, name):
        if not self.store.settings.get("tools_enabled", True):
            return None
        if name == PYTHON_SERVER_NAME:
            return {"disabled_tools": [] if self.store.settings.get("python_enabled", True) else ["execute_python"]}
        if name == "brave-search" and not brave_enabled(self.store.settings):
            return None
        return self.store.settings["mcpServers"].get(name)

    def activity(self):
        if self.stack.get_visible_child_name() == "empty":
            self.clear_messages()
            self.stack.set_visible_child_name("messages")
        if self.activity_box is None:
            self.activity_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            response = self.active_label.get_parent() if self.active_label is not None else None
            if response is not None and response.get_parent() is self.messages:
                self.messages.insert_child_after(self.activity_box, response.get_prev_sibling())
            else:
                self.messages.append(self.activity_box)
        return self.activity_box

    def show_thinking(self):
        if self.thinking_label is None:
            self.thinking_card = Gtk.Box(spacing=8)
            self.thinking_spinner = Gtk.Spinner(spinning=True, width_request=16, height_request=16)
            self.thinking_label = Gtk.Label(label="Thinking…", xalign=0, css_classes=["dim-label"])
            self.thinking_card.append(self.thinking_spinner)
            self.thinking_card.append(self.thinking_label)
            self.activity().append(self.thinking_card)
        self.scroll_bottom()

    def finish_thinking(self):
        if self.thinking_spinner is not None:
            self.thinking_spinner.stop()
        if self.thinking_card is not None and self.thinking_card.get_parent() is not None:
            self.thinking_card.get_parent().remove(self.thinking_card)
            self.thinking_card.remove(self.thinking_spinner)
        self.thinking_spinner = None
        self.thinking_label = None
        self.thinking_card = None
        if self.activity_box is not None and self.activity_box.get_first_child() is None:
            self.messages.remove(self.activity_box)
            self.activity_box = None

    def clear_thinking(self):
        self.finish_thinking()
        self.active_reasoning = None

    def choose_attachments(self, kind):
        self.plus_menu.popdown()
        if kind == "image" and not self.require_vision():
            return
        dialog = Gtk.FileDialog(title="Add Images" if kind == "image" else "Add Files (Text or PDF)", accept_label="Add")
        if kind == "image":
            image_filter = Gtk.FileFilter(name="Images (PNG, JPEG, WebP)")
            for mime in ("image/png", "image/jpeg", "image/webp"):
                image_filter.add_mime_type(mime)
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(image_filter)
            dialog.set_filters(filters)
        chat_id = self.current["id"]
        def selected(dialog, result):
            try:
                files = dialog.open_multiple_finish(result)
            except GLib.Error as exc:
                if exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED) or exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.CANCELLED):
                    return
                self.notify(f"Could not open attachments: {exc.message}")
                return
            if self.future or self.current["id"] != chat_id:
                return
            if kind == "image" and not self.require_vision():
                return
            if len(self.attachments) + files.get_n_items() > MAX_ATTACHMENTS:
                self.notify(f"Attach up to {MAX_ATTACHMENTS} files or images per message.")
                return
            paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
            if any(path is None for path in paths):
                self.notify("Choose files available on this device.")
                return
            # Read files away from GTK; hold the composer while the draft loads.
            self.draft_loading = True
            self.set_busy(False)
            async def load():
                return await asyncio.to_thread(lambda: [load_attachment(path, kind) for path in paths])
            def loaded(items, error):
                if self.closed:
                    return
                self.draft_loading = False
                self.set_busy(self.busy)
                if error:
                    self.notify(error_text(error))
                elif self.current["id"] == chat_id and (kind != "image" or self.require_vision()):
                    self.attachments.extend(items)
                    self.render_attachments()
                self.input.grab_focus()
            self.worker.submit(load(), loaded)
        dialog.open_multiple(self, None, selected)

    def render_attachments(self):
        while child := self.attachment_chips.get_first_child():
            self.attachment_chips.remove(child)
        for attachment in self.attachments:
            chip = Gtk.Box(spacing=6, halign=Gtk.Align.START, css_classes=["attachment-chip"])
            if attachment["kind"] == "image":
                chip.append(image_preview(attachment, draft=True))
            else:
                chip.append(file_preview(attachment))
            remove = Gtk.Button(icon_name="window-close-symbolic", tooltip_text=f"Remove {attachment['name']}", css_classes=["flat", "circular"])
            def remove_attachment(_, item=attachment):
                self.attachments.remove(item)
                self.render_attachments()
            remove.connect("clicked", remove_attachment)
            chip.append(remove)
            self.attachment_chips.append(chip)
            chip.get_parent().set_focusable(False)
        self.attachment_chips.set_visible(bool(self.attachments))
        self.update_image_controls()

    def save_store(self):
        for chat in self.store.chats:
            history.checkpoint(chat)
        try:
            self.store.save()
        except OSError as exc:
            self.notify(f"Could not save: {exc}")

    def reset_all_data(self):
        old_ids = [chat["id"] for chat in self.store.chats]
        self.cancel_titles()
        self.cancel_memories()
        self.store.reset_all()
        self.memory_status = "All saved memories and profile details were deleted."
        for identifier in old_ids:
            self.get_application().withdraw_notification(f"reply-{identifier}")
        self.turn_generation += 1
        self.current = None
        self.drafts.clear()
        self.attachments = []
        self.pending_attachments = []
        self.input.get_buffer().set_text("")
        self.clear_messages()
        self.new_chat()
        self.refresh_models()
        self.refresh_tools()

    def new_chat(self):
        if self.setup is not None or self.busy or self.draft_loading:
            return
        self.search_bar.set_search_mode(False)
        # Every entry point, including Ctrl+N and direct calls, reuses a blank.
        blank = next((chat for chat in self.store.chats if not chat["messages"]), None)
        if blank is None:
            blank = {"id": str(uuid.uuid4()), "title": "New Conversation", "title_source": "pending", "messages": []}
            self.store.chats.insert(0, blank)
        if self.current is not None and self.current is not blank:
            # Carry the composer into a new chat. Sidebar switching continues
            # to restore each conversation's own draft.
            text, files = buffer_text(self.input), copy.deepcopy(self.attachments)
            if text or files:
                existing = self.drafts.get(blank["id"], {})
                if not (existing.get("text") or existing.get("attachments")):
                    self.drafts[blank["id"]] = {"text": text, "attachments": files}
        self.activate_chat(blank)
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)
        self.save_store()

    def update_actions(self):
        available = self.setup is None and not self.busy and not self.draft_loading
        self.lookup_action("new").set_enabled(available and not any(not chat["messages"] for chat in self.store.chats))
        for name in ("delete", "preferences", "personalization", "refresh", "search"):
            self.lookup_action(name).set_enabled(available)

    def activate_chat(self, chat):
        if self.search_query and self.search_query not in searchable_chat_text(chat):
            self.search_entry.set_text("")
        if self.current is not None and self.current is not chat:
            self.drafts[self.current["id"]] = {"text": buffer_text(self.input), "attachments": self.attachments}
        if self.current is not chat:
            self.current = chat
            draft = self.drafts.get(chat["id"], {})
            self.input.get_buffer().set_text(draft.get("text", ""))
            self.attachments = draft.get("attachments", [])
        self.render_attachments()
        self.render_sidebar()
        self.render_chat()
        self.update_actions()
        self.input.grab_focus()
        self.get_application().withdraw_notification(f"reply-{chat['id']}")
        self.request_title(chat)

    def render_sidebar(self):
        while child := self.chat_list.get_first_child():
            self.chat_list.remove(child)
        for chat in self.store.chats:
            row = Gtk.ListBoxRow()
            row.chat = chat
            row.search_text = searchable_chat_text(chat)
            box = margins(Gtk.Box(spacing=6), 6)
            label = FadingTitle(chat["title"])
            row.title_label = label
            box.append(label)
            more = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text=f"Options for {chat['title']}", css_classes=["flat", "circular"])
            popover = Gtk.Popover()
            options = margins(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), 6)
            rename = menu_button("Rename Conversation…", "document-edit-symbolic")
            def rename_from_menu(_, target=chat, popup=popover):
                popup.popdown()
                self.rename_chat(target)
            rename.connect("clicked", rename_from_menu)
            options.append(rename)
            delete = menu_button("Delete Conversation…", "user-trash-symbolic")
            def delete_from_menu(_, target=chat, popup=popover):
                popup.popdown()
                self.delete_chat(chat=target)
            delete.connect("clicked", delete_from_menu)
            options.append(delete)
            popover.set_child(options)
            more.set_popover(popover)
            more.add_css_class("conversation-menu")
            more.set_can_target(False)
            row.menu_button = more
            row.hovered = False
            row.motion = Gtk.EventControllerMotion()
            def hover(_, *args, target=row, entered=True):
                target.hovered = entered
                self.update_row_menu(target)
            row.motion.connect("enter", hover)
            row.motion.connect("leave", lambda controller, target=row: hover(controller, target=target, entered=False))
            row.add_controller(row.motion)
            row.focus = Gtk.EventControllerFocus()
            row.focus.connect("enter", lambda _, target=row: self.update_row_menu(target))
            row.focus.connect("leave", lambda _, target=row: self.update_row_menu(target))
            row.add_controller(row.focus)
            popover.connect("notify::visible", lambda *_, target=row: self.update_row_menu(target))
            context_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            context_click.connect("pressed", lambda *_, button=more: button.popup())
            row.add_controller(context_click)
            box.append(more)
            row.set_child(box)
            self.chat_list.append(row)
            if chat is self.current:
                self.chat_list.select_row(row)
        self.update_search()
        self.update_header_title()

    def update_header_title(self):
        if self.current is not None:
            title = " ".join(self.current["title"].split())
            self.chat_title.set_text(title)
            self.chat_title.set_tooltip_text(title)
            self.set_title(title)

    @staticmethod
    def update_row_menu(row):
        show = row.hovered or row.focus.contains_focus() or row.menu_button.get_popover().get_visible()
        row.menu_button.set_can_target(show)
        if show:
            row.menu_button.add_css_class("options-visible")
        else:
            row.menu_button.remove_css_class("options-visible")

    def update_chat_title(self, chat):
        row = self.chat_list.get_first_child()
        while row:
            if row.chat is chat:
                row.title_label.set_text(chat["title"])
                row.menu_button.set_tooltip_text(f"Options for {row.title_label.get_text()}")
                row.search_text = searchable_chat_text(chat)
                break
            row = row.get_next_sibling()
        self.update_search()
        if chat is self.current:
            self.update_header_title()

    def cancel_titles(self, identifier=None):
        for key, job in list(self.title_jobs.items()):
            if identifier is None or key == identifier:
                del self.title_jobs[key]
                if job["future"] is not None:
                    job["future"].cancel()

    def request_title(self, chat):
        model = self.store.settings.get("model")
        if self.closed or self.busy or not self.store.settings.get("auto_titles", True) or self.title_jobs or model not in self.model_names or not needs_title(chat):
            return
        identifier = chat["id"]
        job = {"future": None}
        self.title_jobs[identifier] = job
        def done(title, error):
            if self.title_jobs.get(identifier) is not job:
                return
            del self.title_jobs[identifier]
            if self.closed or not self.store.settings.get("auto_titles", True):
                return
            if not error and any(item is chat for item in self.store.chats) and chat.get("title_source") != "manual":
                chat["title"] = title
                chat["title_source"] = "generated"
                self.update_chat_title(chat)
                self.save_store()
            # Title generation never holds the composer or raises chat errors.
            # If the user opened another chat, name that one when we're idle.
            if self.current is not chat:
                self.request_title(self.current)
        job["future"] = self.worker.submit(Ollama(self.store.settings["url"]).title(model, copy.deepcopy(chat["messages"])), done)

    def rename_chat(self, chat):
        if self.busy or self.draft_loading or not any(item is chat for item in self.store.chats):
            return
        dialog = Adw.AlertDialog(heading="Rename Conversation")
        entry = Adw.EntryRow(title="Conversation Title", text=" ".join(chat["title"].split()))
        entry.get_delegate().set_max_length(80)
        entry.set_activates_default(True)
        group = Adw.PreferencesGroup()
        group.add(entry)
        dialog.set_extra_child(group)
        dialog.entry = entry
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")
        entry.connect("changed", lambda *_: dialog.set_response_enabled("rename", bool(entry.get_text().strip())))
        def response(_, value):
            title = " ".join(entry.get_text().split())[:80]
            if value == "rename" and title and any(item is chat for item in self.store.chats) and not self.busy:
                self.cancel_titles(chat["id"])
                chat.update(title=title, title_source="manual")
                self.update_chat_title(chat)
                self.save_store()
        dialog.connect("response", response)
        dialog.present(self)
        entry.grab_focus()
        return dialog

    def select_chat(self, _, row):
        if self.busy or self.draft_loading:
            return
        self.activate_chat(row.chat)
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)

    def render_chat(self, final_code_expansion=(), reset_scroll=True):
        self.update_search()
        if reset_scroll:
            self.follow_response = True
        self.finish_thinking()
        self.thinking_label = None
        self.active_label = None
        self.active_reasoning = None
        self.active_tool = None
        self.activity_box = None
        self.round_boundary = False
        if not self.current["messages"]:
            # Keep the outgoing view intact until the native crossfade finishes.
            # The first message or next populated chat replaces it while hidden.
            self.stack.set_visible_child_name("empty")
            return
        self.clear_messages()
        details = saved_tool_details(self.current["messages"])
        response_parts = []
        turn_index = None
        response_model = ""
        def response(final=False):
            if response_parts:
                self.message_card("assistant", "\n\n".join(response_parts),
                                  expanded_codes=final_code_expansion if final else (),
                                  message_index=turn_index, model=response_model)
                response_parts.clear()
        for index, message in enumerate(self.current["messages"]):
            if message["role"] == "user":
                response()
                turn_index = index
                response_model = ""
                self.message_card("user", message.get("display_content", message.get("content", "")),
                                  message.get("attachments", []), images=message.get("images", []), message_index=index,
                                  file_message=message)
            elif message["role"] == "tool":
                self.tool_card(text=message.get("display_content", message["content"]), **details[index])
            elif message["role"] == "assistant":
                response_model = message.get("model", response_model)
                if message.get("thinking") and self.store.settings.get("show_thinking", False):
                    expander, _ = self.reasoning_view(message["thinking"])
                    self.activity().append(expander)
                if message.get("content"):
                    response_parts.append(message.get("display_content", message["content"]))
        response(final=True)
        self.stack.set_visible_child_name("messages")
        self.scroll_bottom()

    def clear_messages(self):
        while child := self.messages.get_first_child():
            self.messages.remove(child)
        self.activity_box = None

    def reasoning_view(self, text):
        expander = Gtk.Expander(label="Model Thinking", expanded=True)
        view = MarkdownView(text, latex_enabled=self.store.settings.get("latex_enabled", True))
        view.connect("content-updated", lambda *_: self.scroll_bottom())
        view.set_margin_top(8)
        view.set_margin_bottom(8)
        view.set_margin_start(12)
        view.add_css_class("dim-label")
        expander.set_child(view)
        return expander, view

    def copy_message(self, button, label):
        self.get_clipboard().set(label.get_copy_text() if isinstance(label, MarkdownView) else label.get_text())
        self.toast.add_toast(Adw.Toast(title="Message copied to clipboard", timeout=2))
        if getattr(button, "copy_pending", None) is not None:
            GLib.source_remove(button.copy_pending)
        button.set_icon_name("emblem-ok-symbolic")
        button.set_tooltip_text("Copied to Clipboard")
        def reset():
            button.copy_pending = None
            button.set_icon_name("edit-copy-symbolic")
            button.set_tooltip_text("Copy Message")
            return GLib.SOURCE_REMOVE
        button.copy_pending = GLib.timeout_add(2000, reset)

    def message_card(self, role, text, attachments=(), expanded_codes=(), images=(), message_index=None, model="", file_message=None):
        if self.stack.get_visible_child_name() == "empty":
            self.clear_messages()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        top = Gtk.Box(spacing=8)
        top.append(Gtk.Label(label="You" if role == "user" else "Response", xalign=0, hexpand=True, css_classes=["heading"]))
        copy_button = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy Message", css_classes=["flat"])
        if role == "assistant":
            label = MarkdownView(text, expanded_codes=expanded_codes,
                                 latex_enabled=self.store.settings.get("latex_enabled", True))
            label.connect("content-updated", lambda *_: self.scroll_bottom())
        else:
            self.activity_box = None
            label = Gtk.Label(label=text, wrap=True, selectable=True, xalign=0, use_markup=False)
            label.set_wrap_mode(2)
        copy_button.connect("clicked", lambda button: self.copy_message(button, label))
        if model and role == "assistant":
            top.append(Gtk.Label(label=model, ellipsize=Pango.EllipsizeMode.END, max_width_chars=18,
                                 tooltip_text=model, css_classes=["dim-label"]))
        if message_index is not None:
            self.add_version_controls(top, message_index)
            action = Gtk.Button(icon_name="document-edit-symbolic" if role == "user" else "view-refresh-symbolic",
                                tooltip_text="Edit Message" if role == "user" else "Regenerate Response",
                                css_classes=["flat"], sensitive=not self.busy)
            action.connect("clicked", lambda *_: self.revision_dialog(message_index, edit=role == "user"))
            top.append(action)
        top.append(copy_button)
        box.append(top)
        box.append(label)
        thumbnails = image_thumbnails()
        image_index = 0
        for attachment in attachments:
            if attachment["kind"] == "image":
                data = images[image_index] if image_index < len(images) else None
                image_index += 1
                thumbnails.append(image_preview(attachment, encoded=data))
                continue
            thumbnails.append(file_preview(attachment, file_message))
        if role == "user":
            outer = Gtk.Box(css_classes=["card"])
            box.set_hexpand(True)
            outer.append(margins(box, 16))
            if attachments:
                group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                group.append(thumbnails)
                group.append(outer)
                self.messages.append(group)
            else:
                self.messages.append(outer)
        else:
            if attachments:
                box.append(thumbnails)
            self.messages.append(box)
        self.stack.set_visible_child_name("messages")
        return label

    def tool_card(self, name, text="", arguments=None, tool_name=None):
        if self.stack.get_visible_child_name() == "empty":
            self.clear_messages()
            self.stack.set_visible_child_name("messages")
        title, preview = tool_view(name, arguments, text, self, tool_name=tool_name,
                                   friendly_search=self.store.settings.get("friendly_search", True),
                                   friendly_python=self.store.settings.get("friendly_python", True))
        expander = Gtk.Expander()
        expander.set_label_widget(Gtk.Label(label=title, xalign=0, hexpand=True,
                                             ellipsize=Pango.EllipsizeMode.END, tooltip_text=title))
        expander.set_child(preview)
        self.activity().append(expander)
        return preview

    def scroll_bottom(self):
        if not self.follow_response or self.scroll_pending is not None:
            return
        def move():
            self.scroll_pending = None
            # A user can scroll away after this idle callback was queued.
            if self.follow_response:
                adj = self.scroll.get_vadjustment()
                self.scrolling_transcript = True
                try:
                    adj.set_value(max(0, adj.get_upper() - adj.get_page_size()))
                finally:
                    self.scrolling_transcript = False
            return GLib.SOURCE_REMOVE
        self.scroll_pending = GLib.idle_add(move)

    def transcript_scrolled(self, adjustment):
        if not self.scrolling_transcript:
            bottom = max(0, adjustment.get_upper() - adjustment.get_page_size())
            self.follow_response = adjustment.get_value() >= bottom - 2

    def transcript_resized(self, adjustment):
        if self.follow_response:
            self.scroll_bottom()

    def supports_images(self, model=None):
        model = model or self.store.settings.get("model", "")
        return "vision" in self.capability_cache.get((self.store.settings["url"], model), set())

    def ensure_capabilities(self, model, callback=None):
        if not model or model not in self.model_names:
            return
        key = (self.store.settings["url"], model)
        if key in self.capability_cache:
            return
        if key in self.capability_jobs:
            if callback and callback not in self.capability_jobs[key]["callbacks"]:
                self.capability_jobs[key]["callbacks"].append(callback)
            return
        job = {"callbacks": [callback] if callback else [], "future": None}
        self.capability_jobs[key] = job
        def done(capabilities, error):
            if self.closed or self.capability_jobs.get(key) is not job:
                return
            self.capability_jobs.pop(key)
            self.capability_cache[key] = capabilities if not error else set()
            if error:
                self.capability_errors[key] = error_text(error)
            self.update_image_controls()
            for updated in job["callbacks"]:
                updated()
        job["future"] = self.worker.submit(Ollama(key[0]).model_capabilities(model), done)
        self.update_image_controls()

    def image_support_message(self, model=None):
        model = model or self.store.settings.get("model", "")
        key = (self.store.settings["url"], model)
        if not model or model not in self.model_names:
            return "Choose a vision model to attach images."
        if key in self.capability_errors:
            return "Could not verify image support. Refresh Models and try again."
        if key not in self.capability_cache:
            return "Checking image support. Try again shortly."
        return "This model does not support images. Choose a vision model."

    def require_vision(self, model=None):
        model = model or self.store.settings.get("model", "")
        if self.supports_images(model):
            return True
        self.ensure_capabilities(model)
        self.notify(self.image_support_message(model))
        return False

    def update_image_controls(self):
        if hasattr(self, "images_button"):
            enabled = self.supports_images()
            self.images_button.set_sensitive(enabled and not self.busy and not self.draft_loading)
            self.images_button.set_tooltip_text("Add Images" if enabled else self.image_support_message())

    def clear_capabilities(self):
        for job in self.capability_jobs.values():
            if job["future"]:
                job["future"].cancel()
        self.capability_jobs.clear()
        self.capability_cache.clear()
        self.capability_errors.clear()
        self.update_image_controls()

    def refresh_models(self):
        self.clear_capabilities()
        url = self.store.settings["url"]
        generation = getattr(self, "model_generation", 0) + 1
        self.model_generation = generation
        def done(names, error):
            if self.closed or generation != self.model_generation:
                return
            self.model_names = names or []
            wanted = self.store.settings.get("model", "")
            self.updating_models = True
            self.models.set_model(Gtk.StringList.new(names or ["No models available"]))
            self.models.set_selected(names.index(wanted) if names and wanted in names else 0)
            self.updating_models = False
            if names:
                self.store.settings["model"] = names[self.models.get_selected()]
            self.save_store()
            self.models.set_sensitive(bool(names) and not self.busy and not self.draft_loading)
            self.ensure_capabilities(self.store.settings.get("model", ""))
            self.update_image_controls()
            self.request_title(self.current)
            if error:
                self.notify("Cannot connect to Ollama. Start ‘ollama serve’ and check Preferences.")
            elif not names:
                self.notify("No models installed. Pull a model, then Refresh Models.")
        self.worker.submit(Ollama(url).models(), done)

    def model_selected(self, *_):
        if getattr(self, "updating_models", False):
            return
        selected = self.models.get_selected_item()
        if selected and selected.get_string() in self.model_names:
            self.store.settings["model"] = selected.get_string()
            self.update_image_controls()
            self.ensure_capabilities(selected.get_string())
            self.save_store()

    def input_key(self, _, key, __, state):
        if key in (Gdk.KEY_v, Gdk.KEY_V) and state & Gdk.ModifierType.CONTROL_MASK:
            if self.paste_image():
                return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not state & Gdk.ModifierType.SHIFT_MASK:
            if not self.future:
                self.send_or_stop(None)
            return True
        return False

    def paste_clipboard(self, widget):
        if self.paste_image():
            widget.stop_emission_by_name("paste-clipboard")

    def paste_image(self, clipboard=None):
        clipboard = clipboard or self.get_clipboard()
        formats = clipboard.get_formats()
        if not (formats.contain_gtype(Gdk.Texture) or any(mime.startswith("image/") for mime in formats.get_mime_types())):
            return False
        if self.busy or self.draft_loading:
            return True
        if not self.require_vision():
            return True
        if len(self.attachments) >= MAX_ATTACHMENTS:
            self.notify(f"Attach up to {MAX_ATTACHMENTS} files or images per message.")
            return True
        chat_id = self.current["id"]
        self.draft_loading = True
        self.set_busy(False)
        def ready(source, result):
            if self.closed:
                return
            try:
                texture = source.read_texture_finish(result)
                if texture.get_width() * texture.get_height() > MAX_IMAGE_PIXELS:
                    raise ValueError("Maximum pasted image resolution is 25 megapixels.")
                data = texture.save_to_png_bytes().get_data()
            except Exception as exc:
                self.draft_loading = False
                self.set_busy(False)
                self.notify(f"Could not paste image: {error_text(exc)}")
                return
            async def load():
                return await asyncio.to_thread(image_attachment, data, "Pasted image.png")
            def loaded(item, error):
                if self.closed:
                    return
                self.draft_loading = False
                self.set_busy(False)
                if error:
                    self.notify(error_text(error))
                elif self.current["id"] == chat_id and self.require_vision():
                    self.attachments.append(item)
                    self.render_attachments()
                self.input.grab_focus()
            self.worker.submit(load(), loaded)
        clipboard.read_texture_async(None, ready)
        return True

    def set_busy(self, busy):
        self.busy = busy
        available = not busy and not self.draft_loading
        self.send.set_icon_name("media-playback-stop-symbolic" if busy else "go-up-symbolic")
        self.send.set_tooltip_text("Stop Response" if busy else "Send Message")
        self.send.set_sensitive(not self.draft_loading)
        for widget in (self.input, self.chat_list, self.tool_choices, self.plus, self.tools_button, self.attachment_chips):
            widget.set_sensitive(available)
        self.refresh_tools_button.set_sensitive(available and self.store.settings.get("tools_enabled", True) and not self.tools_loading)
        self.models.set_sensitive(available and bool(self.model_names))
        self.update_image_controls()
        self.update_actions()

    def send_or_stop(self, _):
        if self.draft_loading:
            return
        if self.future:
            self.future.cancel()
            return
        text = buffer_text(self.input).strip()
        model = self.store.settings.get("model")
        if not text and not self.attachments:
            return
        if not model or model not in self.model_names:
            self.notify("Choose an installed model first.")
            return
        if (any(item["kind"] == "image" for item in self.attachments) or any(item.get("images") for item in self.current["messages"])) and not self.require_vision(model):
            return
        self.cancel_titles()
        cfg = copy.deepcopy(self.store.settings)
        user = user_message(text, self.attachments)
        self.pending_attachments = copy.deepcopy(self.attachments)
        self.current["messages"].append(user)
        if not cfg.get("auto_titles", True) and self.current.get("title_source") not in ("manual", "generated"):
            self.current.update(title=clean_title(text or " · ".join(item["name"] for item in self.attachments)), title_source="fallback")
        self.save_store()
        self.input.get_buffer().set_text("")
        self.render_sidebar()
        self.message_card("user", user.get("display_content", user["content"]), user.get("attachments", []), images=user.get("images", []), file_message=user)
        self.attachments = []
        self.drafts.pop(self.current["id"], None)
        self.render_attachments()
        self.begin_reply(model)

    def begin_reply(self, model, revision_parent=None):
        self.reply_model = model
        self.revision_parent = revision_parent
        cfg = copy.deepcopy(self.store.settings)
        servers = self.servers_for_chat()
        self.turn_generation += 1
        generation = self.turn_generation
        self.active_label = None
        self.active_tool = None
        self.active_reasoning = None
        self.round_boundary = False
        self.follow_response = True
        self.set_busy(True)
        self.show_thinking()
        history_messages = [{"role": "system", "content": system_instructions(cfg, memories=self.store.memories)}] + self.current["messages"]
        def emit(kind, value):
            GLib.idle_add(self.dispatch_event, generation, kind, value)
        self.future = self.worker.submit(Ollama(cfg["url"]).chat(model, history_messages, servers, emit), lambda messages, error: self.finished(messages, error, generation))

    def add_version_controls(self, row, index):
        versions = history.choices(self.current, index)
        if len(versions) < 2:
            return
        current = self.current.get("branch_index", 0)
        if current not in versions:
            return
        position = versions.index(current)
        previous = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous Version", css_classes=["flat"], sensitive=not self.busy and position > 0)
        following = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next Version", css_classes=["flat"], sensitive=not self.busy and position + 1 < len(versions))
        previous.connect("clicked", lambda *_: self.select_version(versions[position - 1]))
        following.connect("clicked", lambda *_: self.select_version(versions[position + 1]))
        row.append(previous)
        row.append(Gtk.Label(label=f"{position + 1}/{len(versions)}", tooltip_text="Message Version", css_classes=["dim-label"]))
        row.append(following)

    def select_version(self, index):
        if self.busy or self.draft_loading:
            return
        history.select(self.current, index)
        self.save_store()
        self.render_chat()

    def revision_dialog(self, index, edit=False):
        if self.busy or self.draft_loading:
            return
        chat = self.current
        message = chat["messages"][index]
        dialog = Adw.AlertDialog(heading="Edit Message" if edit else "Regenerate Response",
                                body="Your earlier messages and replies will remain available using the version arrows.")
        extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        editor = None
        if edit:
            editor = textview(message.get("display_content", message["content"]))
            extra.append(preferences_editor(editor, 120, 260))
            dialog.editor = editor
        extra.append(Gtk.Label(label="Reply Model", xalign=0, css_classes=["heading"]))
        picker = ModelPicker(Gtk.StringList.new(self.model_names))
        original_model = next((item.get("model") for item in chat["messages"][index + 1:] if item["role"] == "assistant" and item.get("model")), self.store.settings.get("model", ""))
        if original_model in self.model_names:
            picker.set_selected(self.model_names.index(original_model))
        extra.append(picker)
        dialog.model_picker = picker
        dialog.set_extra_child(extra)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("send", "Send Edit" if edit else "Regenerate")
        dialog.set_response_appearance("send", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("send")
        dialog.set_close_response("cancel")
        has_images = any(item.get("images") for item in chat["messages"][:index + 1])
        dialog.capabilities_closed = False
        dialog.connect("closed", lambda *_: setattr(dialog, "capabilities_closed", True))
        image_notice = Gtk.Label(wrap=True, xalign=0, css_classes=["dim-label"])
        extra.append(image_notice)
        def enabled(*_):
            if dialog.capabilities_closed:
                return
            item = picker.get_selected_item()
            model = item.get_string() if item else ""
            allowed = not has_images or self.supports_images(model)
            dialog.set_response_enabled("send", bool(self.model_names) and allowed and (not edit or bool(buffer_text(editor).strip())))
            image_notice.set_visible(has_images and not allowed)
            if has_images and not allowed:
                image_notice.set_label(self.image_support_message(model))
                self.ensure_capabilities(model, enabled)
        picker.connect("notify::selected", enabled)
        if editor:
            editor.get_buffer().connect("changed", enabled)
        enabled()
        def response(_, value):
            if value != "send" or self.busy or self.draft_loading or self.current is not chat:
                return
            item = picker.get_selected_item()
            if item is None or item.get_string() not in self.model_names:
                return
            model = item.get_string()
            if has_images and not self.require_vision(model):
                return
            replacement = history.edited_message(message, buffer_text(editor).strip()) if edit else None
            parent = history.fork(chat, index, replacement, model)
            self.cancel_titles(chat["id"])
            self.cancel_memories()
            self.pending_attachments = []
            self.save_store()
            self.render_chat()
            self.begin_reply(model, revision_parent=parent)
        dialog.connect("response", response)
        dialog.present(self)
        return dialog

    def dispatch_event(self, generation, kind, value):
        if not self.closed and generation == self.turn_generation and self.busy:
            self.event(kind, value)

    def event(self, kind, value):
        if kind == "status":
            return
        elif kind == "thinking":
            self.show_thinking()
        elif kind == "reasoning":
            if self.store.settings.get("show_thinking", False):
                self.show_thinking()
                if self.active_reasoning is None and self.thinking_card is not None:
                    expander, self.active_reasoning = self.reasoning_view("")
                    self.activity().insert_child_after(expander, self.thinking_card.get_prev_sibling())
                if self.active_reasoning is not None:
                    self.active_reasoning.append_text(value)
        elif kind == "token":
            self.finish_thinking()
            if self.active_label is None:
                self.active_label = self.message_card("assistant", "")
            elif self.round_boundary and self.active_label.get_text():
                self.active_label.append_text("\n\n")
            self.round_boundary = False
            self.active_label.append_text(value)
        elif kind == "tool-start":
            self.clear_thinking()
            self.active_tool = self.tool_card(value["name"], arguments=value["arguments"], tool_name=value.get("tool_name"))
        elif kind == "tool-result" and self.active_tool:
            self.active_tool.set_result(value)
        elif kind == "round":
            self.round_boundary = True
            self.active_reasoning = None
            self.show_thinking()
        self.scroll_bottom()

    def finished(self, messages, error, generation=None):
        if self.closed or (generation is not None and generation != self.turn_generation):
            return
        self.turn_generation += 1
        self.future = None
        self.set_busy(False)
        if error:
            cancelled = isinstance(error, (asyncio.CancelledError, concurrent.futures.CancelledError))
            if self.revision_parent is not None:
                self.current["branches"][self.current["branch_index"]]["status"] = "failed"
                history.select(self.current, self.revision_parent)
                self.revision_parent = None
                self.render_chat()
                self.notify("Regeneration stopped. Previous version restored." if cancelled else f"Request failed: {error_text(error)}")
                self.save_store()
                self.update_actions()
                self.pending_attachments = []
                return
            # Remove the pending user turn, allowing a clean retry.
            message = self.current["messages"].pop()
            text = message.get("display_content", message["content"])
            self.input.get_buffer().set_text(text)
            self.attachments = self.pending_attachments
            self.render_attachments()
            self.render_chat()
            self.notify("Stopped. Your message is ready to send again." if cancelled else f"Request failed: {error_text(error)}")
            if not self.current["messages"] and self.current.get("title_source") != "manual":
                self.current["title"] = "New Conversation"
                self.render_sidebar()
        else:
            expansion = set(self.active_label.expanded_codes) if self.active_label else ()
            for message in messages:
                if message["role"] == "assistant":
                    message["model"] = self.reply_model
            self.current["messages"].extend(messages)
            self.render_chat(final_code_expansion=expansion, reset_scroll=False)
            self.get_application().notify_completion(self.current)
            self.request_title(self.current)
            self.request_memory(self.current)
        self.pending_attachments = []
        self.revision_parent = None
        self.save_store()
        self.update_actions()
        self.input.grab_focus()

    def cancel_memories(self):
        pending = self.memory_future is not None or bool(self.memory_queue)
        self.memory_generation += 1
        self.memory_queue.clear()
        if self.memory_future is not None:
            self.memory_future.cancel()
            self.memory_future = None
        if pending:
            self.memory_status = "Pending automatic memory checks cancelled."

    def request_memory(self, chat):
        cfg = self.store.settings
        if self.closed or not automatic_memory_enabled(cfg):
            return
        message = next((item for item in reversed(chat["messages"]) if item["role"] == "user"), {})
        text = memory_user_text(message)
        if not text.strip():
            return
        self.memory_queue.append({"text": text, "chat_id": chat["id"], "model": self.reply_model, "url": cfg["url"]})
        self.next_memory()

    def next_memory(self):
        if self.closed or self.memory_future is not None or not self.memory_queue or not automatic_memory_enabled(self.store.settings):
            return
        job = self.memory_queue.pop(0)
        generation = self.memory_generation
        snapshot = copy.deepcopy(self.store.memories)
        self.memory_status = "Checking your message for useful memories…"
        def done(value, error):
            if self.closed or generation != self.memory_generation:
                return
            self.memory_future = None
            valid = (automatic_memory_enabled(self.store.settings) and self.store.settings["url"] == job["url"]
                     and any(chat["id"] == job["chat_id"] for chat in self.store.chats) and self.store.memories == snapshot)
            if valid:
                try:
                    if error:
                        raise error
                    saved, forgotten = self.store.apply_memory_update(value, job["text"], job["chat_id"])
                    if saved or forgotten:
                        self.memory_status = "Memory updated. Your saved details are ready for future conversations."
                        toast = Adw.Toast.new("Memory updated")
                        toast.set_button_label("Manage")
                        toast.set_action_name("win.personalization")
                        self.toast.add_toast(toast)
                    else:
                        self.memory_status = "Memory is up to date. No new details to save."
                except Exception as exc:
                    self.memory_status = "Automatic memory was not updated: " + error_text(exc) + " You can add memories manually in Personalization."
                    self.notify("Automatic memory was not updated. See Preferences → Personalization for details.")
            else:
                self.memory_status = "A stale memory check was discarded."
            self.next_memory()
        self.memory_future = self.worker.submit(Ollama(job["url"]).memory_update(job["model"], job["text"], snapshot), done)

    def delete_chat(self, *_, chat=None):
        if self.busy or self.draft_loading:
            return
        target = chat if chat is not None else self.current
        dialog = Adw.AlertDialog(heading="Delete Conversation?", body=f'“{target["title"]}” will be removed from this device.')
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        def response(_, value):
            if value == "delete" and target in self.store.chats and not self.busy and not self.draft_loading:
                self.cancel_titles(target["id"])
                self.cancel_memories()
                self.store.chats.remove(target)
                self.drafts.pop(target["id"], None)
                self.get_application().withdraw_notification(f"reply-{target['id']}")
                if target is self.current and self.store.chats:
                    self.current = None
                    self.activate_chat(self.store.chats[0])
                elif not self.store.chats:
                    self.current = None
                    self.new_chat()
                else:
                    self.render_sidebar()
                self.save_store()
                self.update_actions()
        dialog.connect("response", response)
        dialog.present(self)
        return dialog

    def on_close(self, *_):
        self.closed = True
        self.lumen_paintable.close()
        self.clear_capabilities()
        if self.scroll_pending is not None:
            GLib.source_remove(self.scroll_pending)
            self.scroll_pending = None
        self.cancel_titles()
        self.cancel_memories()
        self.worker.close()
        if self.setup is None:
            self.save_store()
        return False


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        open_chat = Gio.SimpleAction.new("open-chat", GLib.VariantType.new("s"))
        open_chat.connect("activate", self.open_chat)
        self.add_action(open_chat)

    def open_chat(self, _, target):
        self.activate()
        window = self.get_active_window()
        if window and not window.busy and not window.draft_loading:
            for chat in window.store.chats:
                if chat["id"] == target.get_string():
                    window.activate_chat(chat)
                    break

    def notify_completion(self, chat):
        if self.is_focused():
            return
        notification = Gio.Notification.new("Lumen reply is ready")
        notification.set_body(f'Your reply in “{chat["title"]}” is complete.')
        notification.set_icon(Gio.ThemedIcon.new("dialog-information-symbolic"))
        notification.set_default_action_and_target("app.open-chat", GLib.Variant("s", chat["id"]))
        self.send_notification(f"reply-{chat['id']}", notification)

    def is_focused(self):
        return any(window.is_active() for window in self.get_windows())

    def do_activate(self):
        window = self.get_active_window() or Window(self)
        window.present()


def main():
    GLib.set_application_name("Lumen")
    Application().run(None)
