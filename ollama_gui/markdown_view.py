"""Markdown rendered with GTK widgets; no browser or remote asset loading."""
from gi.repository import GLib, Gtk, Pango, GObject
from .markdown import parse_markdown, inline_markup
from .code_view import CodeBlock
from .markdown import math_literal
from .math_view import MathParagraph, equation_widget


class MarkdownView(Gtk.Box):
    __gsignals__ = {"content-updated": (GObject.SignalFlags.RUN_LAST, None, ())}
    def __init__(self, text="", expanded_codes=(), latex_enabled=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.source = text
        self.pending_render = None
        self.expanded_codes = set(expanded_codes)
        self.latex_enabled = latex_enabled
        self.streaming = False
        self.blocks = []
        self.render()

    def get_text(self):
        # Keep the original Markdown available for streaming and saved history.
        return self.source

    def get_copy_text(self):
        return self.source

    def set_text(self, text):
        self.source = text
        self.streaming = False
        if self.pending_render is not None:
            GLib.source_remove(self.pending_render)
            self.pending_render = None
        self.render()

    def append_text(self, text):
        self.source += text
        self.streaming = True
        if self.pending_render is None:
            self.pending_render = GLib.timeout_add(80, self.render)

    def do_unroot(self):
        if self.pending_render is not None:
            GLib.source_remove(self.pending_render)
            self.pending_render = None
        Gtk.Box.do_unroot(self)

    def render(self):
        self.pending_render = None
        self.code_index = 0
        previous = self.blocks
        self.blocks = []
        for index, block in enumerate(parse_markdown(self.source, self.streaming and self.latex_enabled).children):
            signature = self.signature(block)
            old = previous[index] if index < len(previous) else None
            if self.streaming and old and old[0] == signature:
                widget = old[1]
                self.code_index += old[2]
                self.blocks.append((signature, widget, old[2]))
            else:
                code_start = self.code_index
                widget = self.block_widget(block)
                if self.streaming and old and old[1].get_height() > 0:
                    height = old[1].get_height()
                    widget.set_size_request(-1, height)
                    if isinstance(widget, MathParagraph):
                        widget.height_floor = height
                self.blocks.append((signature, widget, self.code_index - code_start))
        retained = {item[1] for item in self.blocks}
        for _, widget, _ in previous:
            if widget not in retained and widget.get_parent() is self:
                self.remove(widget)
        preceding = None
        for _, widget, _ in self.blocks:
            if widget.get_parent() is None:
                self.insert_child_after(widget, preceding)
            preceding = widget
        self.emit("content-updated")
        return GLib.SOURCE_REMOVE

    @staticmethod
    def signature(node):
        content = "" if node.type == "math_pending" else node.content
        return (node.type, node.tag, content, node.info, node.markup, repr(node.attrs),
                tuple(MarkdownView.signature(child) for child in node.children))

    @staticmethod
    def label(markup):
        label = Gtk.Label(wrap=True, selectable=True, xalign=0, hexpand=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
        label.set_markup(markup)
        return label

    def children_box(self, node, spacing=8):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, hexpand=True)
        for child in node.children:
            box.append(self.block_widget(child))
        return box

    def block_widget(self, node):
        kind = node.type
        if kind == "math_pending":
            return self.label("…")
        if kind == "math_display":
            return (equation_widget(node.content, display=True, literal=math_literal(node))
                    if self.latex_enabled else self.label(inline_markup(node)))
        if kind in ("paragraph", "heading", "inline"):
            label = self.paragraph(node)
            if kind == "heading":
                level = int(node.tag[1:])
                label.add_css_class(f"title-{min(level, 3)}")
            return label
        if kind in ("fence", "code_block"):
            return self.code_widget(node.content, node.info.strip() if kind == "fence" else "")
        if kind in ("bullet_list", "ordered_list"):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            start = int(node.attrs.get("start", 1))
            for index, item in enumerate(node.children):
                row = Gtk.Box(spacing=8, margin_start=8)
                row.append(Gtk.Label(label=f"{start + index}." if kind == "ordered_list" else "•", width_chars=2, xalign=1, valign=Gtk.Align.START))
                row.append(self.children_box(item, 6))
                box.append(row)
            return box
        if kind == "blockquote":
            quote = self.children_box(node)
            quote.add_css_class("markdown-quote")
            return quote
        if kind == "hr":
            return Gtk.Separator()
        if kind == "table":
            grid = Gtk.Grid(column_spacing=12, row_spacing=4)
            row_index = 0
            for group in node.children:
                for row in group.children:
                    for column, cell in enumerate(row.children):
                        markup = inline_markup(cell)
                        if cell.type == "th":
                            markup = f"<b>{markup}</b>"
                        label = self.paragraph(cell) if self.contains_math(cell) and self.latex_enabled else self.label(markup)
                        if isinstance(label, Gtk.Label):
                            label.set_wrap(False)
                        label.add_css_class("markdown-table-cell")
                        grid.attach(label, column, row_index, 1, 1)
                    row_index += 1
            scroll = Gtk.ScrolledWindow(propagate_natural_height=True, min_content_height=min(400, max(40, row_index * 40)), max_content_height=400)
            scroll.set_child(grid)
            frame = Gtk.Frame()
            frame.set_child(scroll)
            return frame
        return self.children_box(node) if node.children else self.label(inline_markup(node))

    def contains_math(self, node):
        return node.type in ("math_inline", "math_display") or any(self.contains_math(child) for child in node.children)

    def paragraph(self, node):
        if not self.latex_enabled or not self.contains_math(node):
            return self.label(inline_markup(node))
        # Ordinary inline math flows with its surrounding formatted text.
        # Display delimiters inside a paragraph create separate lines.
        return MathParagraph(inline_markup(node, math=True))

    def code_widget(self, source, language):
        index = self.code_index
        self.code_index += 1
        def remember(expanded):
            if expanded:
                self.expanded_codes.add(index)
            else:
                self.expanded_codes.discard(index)
        return CodeBlock(source, language, expanded=index in self.expanded_codes, on_expanded=remember)
