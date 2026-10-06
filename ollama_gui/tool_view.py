from gi.repository import Adw, GLib, Gtk, Pango
import json
import weakref
from .tool_output import BRAVE_TOOLS, brave_results, original_tool_name, python_result, tool_preview
from .code_view import CodeBlock


class ToolOutputDialog(Adw.Dialog):
    def __init__(self, name, text):
        super().__init__(title="Tool Output", content_width=760, content_height=560)
        self.full_text = text
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Tool Output", subtitle=name))
        copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy Full Output")
        copy.connect("clicked", lambda _: self.get_clipboard().set(self.full_text))
        header.pack_start(copy)
        toolbar.add_top_bar(header)
        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=20, right_margin=20, top_margin=16, bottom_margin=20)
        self.view.get_buffer().set_text(text)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(self.view)
        toolbar.set_content(scroll)
        self.set_child(toolbar)


class ToolPreview(Gtk.Box):
    def __init__(self, name, text, owner, arguments=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10, margin_start=12, margin_end=12, css_classes=["read-only-output"])
        self.name = name
        self.arguments = arguments
        self.owner = weakref.ref(owner)
        self.source = ""
        self.preview = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, lines=4, ellipsize=Pango.EllipsizeMode.END, selectable=True, xalign=0)
        self.append(self.preview)
        self.more = Gtk.Label(label="More output available…", xalign=0, css_classes=["dim-label"])
        self.append(self.more)
        self.show_more = Gtk.Button(label="Show More", halign=Gtk.Align.START)
        self.show_more.connect("clicked", lambda *_: self.open_full())
        self.append(self.show_more)
        self.set_result(text)

    def get_text(self):
        return self.source

    def set_text(self, text):
        self.source = text
        preview, truncated = tool_preview(text)
        self.preview.set_text(preview)
        self.more.set_visible(truncated)
        self.show_more.set_visible(bool(text))

    def set_result(self, text):
        prefix = json.dumps(self.arguments, indent=2, ensure_ascii=False) if self.arguments is not None else ""
        self.set_text(prefix + ("\n\n" if prefix and text else "") + text)

    def open_full(self):
        dialog = ToolOutputDialog(self.name, self.source)
        dialog.present(self.owner())
        return dialog


def search_links(results):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    for result in results:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        link = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=0,
                         lines=2, ellipsize=Pango.EllipsizeMode.END)
        link.set_markup(f'<a href="{GLib.markup_escape_text(result["url"])}">{GLib.markup_escape_text(result["title"])}</a>')
        link.set_tooltip_text(result["url"])
        row.append(link)
        url = Gtk.Label(label=result["url"], xalign=0, ellipsize=Pango.EllipsizeMode.END,
                        css_classes=["dim-label", "caption"], tooltip_text=result["url"])
        row.append(url)
        if result["description"]:
            row.append(Gtk.Label(label=result["description"], wrap=True,
                                 wrap_mode=Pango.WrapMode.WORD_CHAR, lines=2,
                                 ellipsize=Pango.EllipsizeMode.END, xalign=0))
        box.append(row)
    return box


class SearchOutputDialog(ToolOutputDialog):
    def __init__(self, name, text, results):
        super().__init__(name, text)
        content = search_links(results)
        for edge in ("top", "bottom", "start", "end"):
            getattr(content, f"set_margin_{edge}")(20)
        # All results are available in the dialog, including full descriptions.
        row = content.get_first_child()
        while row:
            child = row.get_first_child()
            while child:
                if isinstance(child, Gtk.Label) and child.get_wrap():
                    child.set_lines(-1)
                    child.set_ellipsize(Pango.EllipsizeMode.NONE)
                child = child.get_next_sibling()
            row = row.get_next_sibling()
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(content)
        self.get_child().set_content(scroll)


class SearchPreview(Gtk.Box):
    def __init__(self, name, text, owner):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                         margin_top=12, margin_bottom=12, margin_start=12,
                         margin_end=12, css_classes=["read-only-output"])
        self.name, self.owner = name, weakref.ref(owner)
        self.source, self.results = "", None
        self.set_result(text)

    def get_text(self):
        return self.source

    def set_result(self, text):
        self.source, self.results = text, brave_results(text)
        while child := self.get_first_child():
            self.remove(child)
        if not text:
            self.append(Gtk.Label(label="Waiting for search results…", xalign=0, css_classes=["dim-label"]))
        elif self.results is None:
            # API errors and unfamiliar custom server responses stay readable.
            self.append(ToolPreview(self.name, text, self.owner()))
        elif not self.results:
            self.append(Gtk.Label(label="No search results.", xalign=0))
        else:
            self.append(search_links(self.results[:3]))
            if len(self.results) > 3:
                self.append(Gtk.Label(label=f"{len(self.results) - 3} more results…", xalign=0, css_classes=["dim-label"]))
            self.show_more = Gtk.Button(label="Show More", halign=Gtk.Align.START)
            self.show_more.connect("clicked", lambda *_: self.open_full())
            self.append(self.show_more)

    def open_full(self):
        dialog = (SearchOutputDialog(self.name, self.source, self.results)
                  if self.results else ToolOutputDialog(self.name, self.source))
        dialog.present(self.owner())
        return dialog


class PythonPreview(Gtk.Box):
    def __init__(self, arguments, text, owner):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        code = arguments.get("code")
        if isinstance(code, str):
            self.code = CodeBlock(code, "python")
            self.append(self.code)
        else:
            self.append(Gtk.Label(label="Code was not retained in this older conversation.", wrap=True, xalign=0, css_classes=["dim-label"]))
        self.status = Gtk.Label(xalign=0, css_classes=["dim-label"])
        self.append(self.status)
        self.output = ToolPreview("Python Output", "", owner)
        self.append(self.output)
        self.source = ""
        self.set_result(text)

    def get_text(self):
        return self.source

    def set_result(self, text):
        self.source = text
        result = python_result(text)
        status, output = result if result else ("Running Python…" if not text else "Python Output", text)
        self.status.set_text(status)
        self.output.set_text(output)
        self.output.set_visible(bool(output))
        self.output.show_more.set_visible(bool(output) and self.output.more.get_visible())


def tool_view(name, arguments, text, owner, tool_name=None, friendly_search=True, friendly_python=True):
    tool_name = tool_name or original_tool_name(name)
    if tool_name in BRAVE_TOOLS and friendly_search:
        query = arguments.get("query", "") if arguments else ""
        query = " ".join(str(query).split())
        title = f"Searching for “{query}”" if query else "Brave Search"
        return title, SearchPreview(title, text, owner)
    if tool_name == "execute_python" and friendly_python:
        return "Python", PythonPreview(arguments or {}, text, owner)
    return name, ToolPreview(name, text, owner, arguments)
