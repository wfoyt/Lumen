"""Code blocks that grow with their rendered lines and expand in place."""
import gi
gi.require_version("GtkSource", "5")
from gi.repository import Adw, Gdk, GLib, Gtk, GtkSource


CODE_PREVIEW_HEIGHT = 320


class CodeTextView(GtkSource.View):
    def __init__(self, resized, language):
        buffer = GtkSource.Buffer(highlight_syntax=True)
        alias = language.split()[0].lower() if language else ""
        alias = {"py": "python3", "python": "python3", "python2": "python",
                 "javascript": "js", "node": "js", "ts": "typescript",
                 "bash": "sh", "shell": "sh", "c++": "cpp", "c#": "c-sharp",
                 "csharp": "c-sharp", "yml": "yaml", "rs": "rust"}.get(alias, alias)
        manager = GtkSource.LanguageManager.get_default()
        buffer.set_language(manager.get_language(alias) or manager.guess_language(f"source.{alias}", None))
        super().__init__(editable=False, cursor_visible=False, monospace=True,
                         buffer=buffer,
                         wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=16, right_margin=16,
                         top_margin=8, bottom_margin=16)
        self.resized = resized
        self.previous_width = -1
        self.style_handler = None

    def update_style(self, *_):
        scheme = "Adwaita-dark" if Adw.StyleManager.get_default().get_dark() else "Adwaita"
        manager = GtkSource.StyleSchemeManager.get_default()
        self.get_buffer().set_style_scheme(manager.get_scheme(scheme) or manager.get_scheme("classic"))

    def do_root(self):
        GtkSource.View.do_root(self)
        self.update_style()
        self.style_handler = Adw.StyleManager.get_default().connect("notify::dark", self.update_style)

    def do_unroot(self):
        if self.style_handler is not None:
            Adw.StyleManager.get_default().disconnect(self.style_handler)
            self.style_handler = None
        GtkSource.View.do_unroot(self)

    def do_size_allocate(self, width, height, baseline):
        GtkSource.View.do_size_allocate(self, width, height, baseline)
        if width != self.previous_width:
            self.previous_width = width
            self.resized()


class CodeBlock(Gtk.Box):
    def __init__(self, source, language="", expanded=False, on_expanded=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                         css_classes=["card", "markdown-code"])
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.source = source
        self.expanded = expanded
        self.on_expanded = on_expanded
        self.measure_pending = None
        self.copy_pending = None
        self.content_height = 40
        header = Gtk.Box(spacing=8, margin_start=16, margin_end=8, margin_top=8)
        header.append(Gtk.Label(label=language or "Code", xalign=0, hexpand=True, css_classes=["dim-label"]))
        self.copy_button = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy Code", css_classes=["flat"])
        self.copy_button.connect("clicked", self.copy_code)
        header.append(self.copy_button)
        self.append(header)
        self.view = CodeTextView(self.queue_measure, language)
        self.view.get_buffer().set_text(source.rstrip("\n"))
        self.scroll = Gtk.ScrolledWindow(min_content_height=40, max_content_height=40,
                                         propagate_natural_height=True,
                                         hscrollbar_policy=Gtk.PolicyType.NEVER,
                                         vscrollbar_policy=Gtk.PolicyType.EXTERNAL)
        self.scroll.set_child(self.view)
        self.scroll.set_kinetic_scrolling(False)
        # The viewport clips the preview but never moves within it, including
        # keyboard navigation or selection dragging. Only Show More reveals it.
        self.scroll.get_vadjustment().connect("value-changed", self.lock_preview)
        self.scroll_controller = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.BOTH_AXES)
        self.scroll_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.scroll_controller.connect("scroll", self.scroll_conversation)
        self.add_controller(self.scroll_controller)
        self.append(self.scroll)
        self.reveal_button = Gtk.Button(label="Show More", halign=Gtk.Align.START,
                                        margin_start=12, margin_end=12, margin_bottom=12,
                                        visible=False, css_classes=["flat"])
        self.reveal_button.connect("clicked", self.toggle_expanded)
        self.append(self.reveal_button)
        # Collapsed tool expanders can allocate their children before they are
        # rooted. Measure again when shown, even if their width is unchanged.
        self.connect("map", lambda *_: self.queue_measure())

    def copy_code(self, *_):
        self.get_clipboard().set(self.source)
        root = self.get_root()
        if isinstance(root, Adw.ApplicationWindow) and isinstance(root.get_content(), Adw.ToastOverlay):
            # The toast survives streaming Markdown rebuilds, which can replace
            # this button before its temporary checkmark has finished showing.
            root.get_content().add_toast(Adw.Toast(title="Code copied to clipboard", timeout=2))
        if self.copy_pending is not None:
            GLib.source_remove(self.copy_pending)
        self.copy_button.set_icon_name("emblem-ok-symbolic")
        self.copy_button.set_tooltip_text("Copied to Clipboard")
        self.copy_pending = GLib.timeout_add(2000, self.reset_copy_feedback)

    def reset_copy_feedback(self):
        self.copy_pending = None
        self.copy_button.set_icon_name("edit-copy-symbolic")
        self.copy_button.set_tooltip_text("Copy Code")
        return GLib.SOURCE_REMOVE

    @staticmethod
    def lock_preview(adjustment):
        if adjustment.get_value() != 0:
            adjustment.set_value(0)

    def scroll_conversation(self, controller, dx, dy):
        # Wheel/trackpad gestures over code scroll the enclosing transcript,
        # rather than silently exposing lines hidden behind the preview.
        ancestor = self.get_parent()
        while ancestor and not isinstance(ancestor, Gtk.ScrolledWindow):
            ancestor = ancestor.get_parent()
        if ancestor and dy:
            adjustment = ancestor.get_vadjustment()
            step = 1 if controller.get_unit() == Gdk.ScrollUnit.SURFACE else max(1, adjustment.get_page_size()) ** (2 / 3)
            adjustment.set_value(adjustment.get_value() + dy * step)
        return True

    def queue_measure(self):
        if self.measure_pending is None:
            self.measure_pending = GLib.idle_add(self.update_height)

    def update_height(self):
        self.measure_pending = None
        if not self.view.get_root() or self.view.get_width() <= 0:
            return GLib.SOURCE_REMOVE
        # Ask TextView about the last rendered line, including wrapping at the
        # actual allocation. Character counts cannot predict its pixel height.
        end = self.view.get_buffer().get_end_iter()
        y, height = self.view.get_line_yrange(end)
        self.content_height = max(40, y + height + self.view.get_top_margin() + self.view.get_bottom_margin())
        self.apply_height()
        return GLib.SOURCE_REMOVE

    def apply_height(self):
        target = self.content_height if self.expanded else min(CODE_PREVIEW_HEIGHT, self.content_height)
        # Update both bounds together without briefly leaving min above max.
        if target > self.scroll.get_max_content_height():
            self.scroll.set_max_content_height(target)
        self.scroll.set_min_content_height(target)
        self.scroll.set_max_content_height(target)
        self.reveal_button.set_visible(self.content_height > CODE_PREVIEW_HEIGHT)
        self.reveal_button.set_label("Show Less" if self.expanded else "Show More")

    def toggle_expanded(self, *_):
        self.expanded = not self.expanded
        self.apply_height()
        if self.on_expanded:
            self.on_expanded(self.expanded)

    def do_unroot(self):
        if self.copy_pending is not None:
            GLib.source_remove(self.copy_pending)
            self.copy_pending = None
        self.reset_copy_feedback()
        if self.measure_pending is not None:
            GLib.source_remove(self.measure_pending)
            self.measure_pending = None
        Gtk.Box.do_unroot(self)
