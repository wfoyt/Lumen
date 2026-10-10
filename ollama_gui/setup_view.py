"""First-run setup, with changes committed only when the user finishes."""
import copy

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from .storage import DEFAULT_SETTINGS, brave_enabled, configure_brave, validate_url


class SetupView(Gtk.Box):
    def __init__(self, settings, paintable, on_finish):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.navigation = Adw.NavigationView(vexpand=True)
        self.append(self.navigation)
        self.settings = copy.deepcopy(settings)
        self.on_finish = on_finish
        self.custom_url = False

        welcome = Adw.StatusPage(
            paintable=paintable, title="Welcome to Lumen",
            description="A little light for your ideas. Chat with your Ollama models and make room for discovery.")
        self.start_button = self.next_button("Start Setup", lambda *_: self.navigation.push_by_tag("ollama"))
        welcome.set_child(self.start_button)
        self.add_page("welcome", "Welcome", welcome)

        connection = self.page_body("Connect to Ollama", "Choose where Lumen can find your Ollama models.", "network-server-symbolic")
        local = Adw.PreferencesGroup(
            description="For Ollama running on this computer. Make sure Ollama is installed and running.")
        connection.append(local)
        self.default_button = Gtk.Button(label="Use Default URL", css_classes=["suggested-action", "pill"])
        self.default_button.connect("clicked", self.use_default)
        local.add(self.default_button)
        local.add(Gtk.Label(label=DEFAULT_SETTINGS["url"], selectable=True, margin_top=8, css_classes=["dim-label", "caption"]))

        self.custom_button = Gtk.Button(css_classes=["pill"])
        custom_label = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
        custom_label.append(Gtk.Label(label="Use Custom URL"))
        custom_label.append(Gtk.Label(label="Advanced", css_classes=["dim-label", "caption"]))
        self.custom_button.set_child(custom_label)
        self.custom_button.set_tooltip_text("For a remote Ollama server or a nonstandard address")
        self.custom_button.connect("clicked", self.use_custom)
        connection.append(self.custom_button)
        self.custom_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN, visible=False)
        custom_fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.custom_revealer.set_child(custom_fields)
        group = Adw.PreferencesGroup(title="Custom Connection", description="Advanced: enter the full HTTP or HTTPS address of your Ollama server.")
        self.url = Adw.EntryRow(title="Ollama URL", text=settings["url"], input_purpose=Gtk.InputPurpose.URL)
        self.url.connect("changed", self.clear_url_error)
        group.add(self.url)
        custom_fields.append(group)
        self.url_error = self.error_label()
        custom_fields.append(self.url_error)
        self.url_next = self.next_button("Next", self.connection_next)
        self.url_next.set_visible(False)
        connection.append(self.custom_revealer)
        self.add_page("ollama", "Ollama", self.scrolled(connection), self.url_next)

        tools = self.page_body("Set Up Tools", "Give your models a few extra ways to help. You can change these choices in Preferences.", "applications-science-symbolic")
        control = Adw.PreferencesGroup()
        self.tools_enabled = Adw.SwitchRow(title="Enable Tools", subtitle="Allow models to use the tools you enable below.", active=settings.get("tools_enabled", True))
        control.add(self.tools_enabled)
        tools.append(control)
        self.tools_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        integrations = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.tools_revealer.set_child(integrations)
        group = Adw.PreferencesGroup()
        self.python_enabled = Adw.SwitchRow(title="Python Integration", subtitle="Run Python for calculations, statistics and data processing.", active=settings.get("python_enabled", True))
        group.add(self.python_enabled)
        self.brave_enabled = Adw.SwitchRow(title="Brave Search Integration", subtitle="Search the web and news using your Brave API key.", active=brave_enabled(settings))
        group.add(self.brave_enabled)
        integrations.append(group)
        self.brave_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        brave_fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.brave_revealer.set_child(brave_fields)
        brave = Adw.PreferencesGroup(title="Brave Search API Key")
        self.key = Adw.PasswordEntryRow(title="API Key")
        self.key.set_text(settings.get("mcpServers", {}).get("brave-search", {}).get("env", {}).get("BRAVE_API_KEY", ""))
        self.key.connect("changed", self.clear_key_error)
        brave.add(self.key)
        brave_fields.append(brave)
        self.key_error = self.error_label()
        brave_fields.append(self.key_error)
        brave_fields.append(Gtk.Label(label="How to get an API key", xalign=0, css_classes=["heading"]))
        brave_fields.append(Gtk.Label(
            label="1. Sign in or create an account in the Brave Search API dashboard.\n2. Choose and activate an API plan.\n3. Open API Keys, create a key, and paste it above.",
            wrap=True, xalign=0))
        brave_fields.append(Gtk.LinkButton(uri="https://api-dashboard.search.brave.com/", label="Open Brave Search Dashboard", halign=Gtk.Align.START))
        brave_fields.append(Gtk.Label(label="Searches use your Brave Search API plan.", wrap=True, xalign=0, css_classes=["dim-label", "caption"]))
        integrations.append(self.brave_revealer)
        tools.append(self.tools_revealer)
        self.tools_next = self.next_button("Next", self.tools_continue)
        self.tools_enabled.connect("notify::active", self.update_tool_fields)
        self.brave_enabled.connect("notify::active", self.update_tool_fields)
        self.update_tool_fields()
        self.add_page("tools", "Tools", self.scrolled(tools), self.tools_next)

        ready = Adw.StatusPage(paintable=paintable, title="Welcome to Lumen",
                              description="You’re ready to begin. Finish setup to open your first chat, then choose a model and ask a question.")
        finish_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.finish_error = self.error_label()
        finish_box.append(self.finish_error)
        self.finish_button = self.next_button("Finish", self.finish)
        finish_box.append(self.finish_button)
        ready.set_child(finish_box)
        self.add_page("ready", "Ready", ready)

    def add_page(self, tag, title, content, next_button=None):
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(content)
        if next_button is not None:
            footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=12, margin_bottom=12)
            footer.append(next_button)
            next_button.bind_property("visible", footer, "visible", 2)
            toolbar.add_bottom_bar(footer)
            toolbar.set_bottom_bar_style(Adw.ToolbarStyle.RAISED)
        self.navigation.add(Adw.NavigationPage(child=toolbar, title=title, tag=tag))

    @staticmethod
    def next_button(label, callback):
        button = Gtk.Button(label=label, halign=Gtk.Align.CENTER, css_classes=["suggested-action", "pill"])
        button.connect("clicked", callback)
        return button

    @staticmethod
    def error_label():
        return Gtk.Label(wrap=True, xalign=0, visible=False, css_classes=["error"])

    @staticmethod
    def page_body(title, description, icon):
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24, valign=Gtk.Align.CENTER,
                       margin_top=32, margin_bottom=32, margin_start=24, margin_end=24)
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        heading.append(Gtk.Image(icon_name=icon, pixel_size=64, css_classes=["dim-label"]))
        heading.append(Gtk.Label(label=title, wrap=True, justify=Gtk.Justification.CENTER, css_classes=["title-1"]))
        heading.append(Gtk.Label(label=description, wrap=True, justify=Gtk.Justification.CENTER, css_classes=["dim-label"]))
        body.append(heading)
        return body

    @staticmethod
    def scrolled(body):
        clamp = Adw.Clamp(maximum_size=560, tightening_threshold=400)
        clamp.set_child(body)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(clamp)
        return scroll

    def use_default(self, *_):
        self.custom_url = False
        self.custom_revealer.set_reveal_child(False)
        self.custom_revealer.set_visible(False)
        self.url_next.set_visible(False)
        self.clear_url_error()
        self.navigation.push_by_tag("tools")

    def use_custom(self, *_):
        self.custom_url = True
        self.custom_revealer.set_visible(True)
        self.custom_revealer.set_reveal_child(True)
        self.url_next.set_visible(True)
        self.url.grab_focus()

    def clear_url_error(self, *_):
        self.url.remove_css_class("error")
        self.url_error.set_visible(False)

    def clear_key_error(self, *_):
        self.key.remove_css_class("error")
        self.key_error.set_visible(False)

    def connection_url(self):
        return validate_url(self.url.get_text().strip()) if self.custom_url else DEFAULT_SETTINGS["url"]

    def connection_next(self, *_):
        try:
            self.connection_url()
        except ValueError as exc:
            self.url.add_css_class("error")
            self.url_error.set_text(str(exc))
            self.url_error.set_visible(True)
            self.url.grab_focus()
            return
        self.navigation.push_by_tag("tools")

    def update_tool_fields(self, *_):
        enabled = self.tools_enabled.get_active()
        self.tools_revealer.set_reveal_child(enabled)
        self.tools_revealer.set_visible(enabled)
        brave = enabled and self.brave_enabled.get_active()
        self.brave_revealer.set_reveal_child(brave)
        self.brave_revealer.set_visible(brave)
        self.clear_key_error()

    def tools_continue(self, *_):
        if self.tools_enabled.get_active() and self.brave_enabled.get_active() and not self.key.get_text().strip():
            self.key.add_css_class("error")
            self.key_error.set_text("Enter an API key, or turn off Brave Search to continue.")
            self.key_error.set_visible(True)
            self.key.grab_focus()
            return
        self.navigation.push_by_tag("ready")

    def finish(self, *_):
        cfg = {**self.settings, "url": self.connection_url(), "tools_enabled": self.tools_enabled.get_active(),
               "python_enabled": self.python_enabled.get_active(), "brave_enabled": self.brave_enabled.get_active(),
               "mcpServers": configure_brave(self.settings["mcpServers"], self.key.get_text()), "setup_completed": True}
        if "brave-search" in cfg["mcpServers"]:
            cfg["mcpServers"]["brave-search"]["enabled"] = cfg["brave_enabled"]
        try:
            self.on_finish(cfg)
        except OSError as exc:
            self.finish_error.set_text(f"Could not save setup: {exc}")
            self.finish_error.set_visible(True)
