"""Clickable attachment cards, hover feedback and native file previews."""
import base64
from gi.repository import Adw, GLib, Graphene, Gtk
from .code_view import CodeTextView


class PreviewButton(Gtk.Button):
    """Animate the drawing, keeping the layout still while hovering."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.zoom = 1.0
        self.animation = None
        self.set_cursor_from_name("pointer")
        self.set_overflow(Gtk.Overflow.VISIBLE)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", lambda *_: self.animate(1.04))
        motion.connect("leave", lambda *_: self.animate(1.0))
        self.add_controller(motion)

    def animate(self, target):
        if self.animation:
            self.animation.pause()
        self.animation = Adw.TimedAnimation.new(self, self.zoom, target, 140,
                                                Adw.CallbackAnimationTarget.new(self.set_zoom))
        self.animation.play()

    def set_zoom(self, value):
        self.zoom = value
        self.queue_draw()

    def do_snapshot(self, snapshot):
        snapshot.save()
        snapshot.translate(Graphene.Point().init(self.get_width() / 2, self.get_height() / 2))
        snapshot.scale(self.zoom, self.zoom)
        snapshot.translate(Graphene.Point().init(-self.get_width() / 2, -self.get_height() / 2))
        Gtk.Button.do_snapshot(self, snapshot)
        snapshot.restore()

    def do_unroot(self):
        if self.animation:
            self.animation.pause()
            self.animation = None
        Gtk.Button.do_unroot(self)


def stored_file(attachment, message=None):
    """Recover extracted text from messages saved before file previews existed."""
    if "content" in attachment or not message:
        return attachment
    result = dict(attachment)
    marker = f"Attached file: {attachment['name']}\n<attachment>\n"
    payload = message.get("content", "")
    if marker in payload:
        result["content"] = payload.split(marker, 1)[1].split("\n</attachment>", 1)[0]
    return result


class PdfPage(Gtk.Widget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.width, self.height = page.get_size()

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 100, 700, -1, -1
        height = max(1, round((for_size if for_size > 0 else 700) * self.height / self.width))
        return height, height, -1, -1

    def do_snapshot(self, snapshot):
        context = snapshot.append_cairo(Graphene.Rect().init(0, 0, self.get_width(), self.get_height()))
        context.set_source_rgb(1, 1, 1)
        context.paint()
        context.scale(self.get_width() / self.width, self.get_width() / self.width)
        self.page.render(context)


def file_dialog(attachment, parent):
    dialog = Adw.Dialog(title=attachment["name"], content_width=800, content_height=650)
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_margin_top(12)
    scroll.set_margin_bottom(12)
    scroll.set_margin_start(12)
    scroll.set_margin_end(12)
    document = None
    if attachment.get("data") and attachment.get("mime") == "application/pdf":
        try:
            import gi
            gi.require_version("Poppler", "0.18")
            from gi.repository import Poppler
            document = Poppler.Document.new_from_bytes(GLib.Bytes.new(base64.b64decode(attachment["data"])), None)
        except (ValueError, ImportError, GLib.Error):
            document = None
    if document:
        page = [0]
        navigation = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=8, margin_bottom=8)
        previous = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text="Previous Page", css_classes=["flat"])
        count = Gtk.Label()
        following = Gtk.Button(icon_name="go-next-symbolic", tooltip_text="Next Page", css_classes=["flat"])
        def update(delta=0):
            page[0] = max(0, min(document.get_n_pages() - 1, page[0] + delta))
            scroll.set_child(PdfPage(document.get_page(page[0])))
            scroll.get_vadjustment().set_value(0)
            count.set_label(f"{page[0] + 1} / {document.get_n_pages()}")
            previous.set_sensitive(page[0] > 0)
            following.set_sensitive(page[0] + 1 < document.get_n_pages())
        previous.connect("clicked", lambda *_: update(-1))
        following.connect("clicked", lambda *_: update(1))
        for widget in (previous, count, following):
            navigation.append(widget)
        toolbar.add_bottom_bar(navigation)
        update()
    else:
        view = CodeTextView(lambda: None, attachment["name"].rsplit(".", 1)[-1])
        view.get_buffer().set_text(attachment.get("content", "This file's contents were not retained in this older conversation."))
        scroll.set_child(view)
        if attachment["name"].lower().endswith(".pdf"):
            toolbar.add_bottom_bar(Gtk.Label(label="Extracted PDF Text", margin_top=8, margin_bottom=8, css_classes=["dim-label"]))
    toolbar.set_content(scroll)
    dialog.set_child(toolbar)
    dialog.present(parent)
    return dialog


def file_preview(attachment, message=None):
    attachment = stored_file(attachment, message)
    button = PreviewButton(css_classes=["flat", "card"], halign=Gtk.Align.START,
                           tooltip_text=f"Open {attachment['name']}")
    row = Gtk.Box(spacing=8, margin_start=8, margin_end=8, margin_top=8, margin_bottom=8)
    row.append(Gtk.Image(icon_name="application-pdf-symbolic" if attachment["name"].lower().endswith(".pdf") else "text-x-generic-symbolic"))
    row.append(Gtk.Label(label=attachment["name"], xalign=0, ellipsize=3, max_width_chars=22))
    button.set_child(row)
    button.connect("clicked", lambda *_: file_dialog(attachment, button.get_root()))
    return button
