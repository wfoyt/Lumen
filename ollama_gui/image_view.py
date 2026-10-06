"""Native image thumbnails for drafts and saved vision messages."""
import base64
from io import BytesIO
from PIL import Image
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk


def image_thumbnails():
    # WrapBox keeps images together at the end of each line and adapts to the
    # transcript width. Retain compatibility with older libadwaita releases.
    if hasattr(Adw, "WrapBox"):
        return Adw.WrapBox(child_spacing=8, line_spacing=8, align=1,
                           natural_line_length=440)
    return Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, min_children_per_line=1,
                        max_children_per_line=4, column_spacing=8, row_spacing=8,
                        homogeneous=True, halign=Gtk.Align.END)


def texture(encoded, bounds=None):
    data = GLib.Bytes.new(base64.b64decode(encoded))
    if bounds:
        stream = Gio.MemoryInputStream.new_from_bytes(data)
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(stream, *bounds, True, None)
        return Gdk.Texture.new_for_pixbuf(pixbuf)
    try:
        return Gdk.Texture.new_from_bytes(data)
    except GLib.Error:
        # Native image loaders vary by distro; Pillow can normalize a validated
        # WebP/JPEG attachment to PNG for the full-size preview when needed.
        with Image.open(BytesIO(data.get_data())) as source:
            normalized = BytesIO()
            source.convert("RGBA").save(normalized, format="PNG")
        return Gdk.Texture.new_from_bytes(GLib.Bytes.new(normalized.getvalue()))


def image_preview(attachment, encoded=None, draft=False):
    data = attachment.get("thumbnail") or encoded or attachment.get("content")
    try:
        paintable = texture(data, (96, 72) if draft else (104, 104))
    except (GLib.Error, ValueError, TypeError, OSError):
        return Gtk.Label(label="Image preview unavailable", wrap=True)
    picture = Gtk.Picture(paintable=paintable, can_shrink=True, content_fit=Gtk.ContentFit.COVER)
    picture.set_tooltip_text(attachment["name"])
    picture.update_property([Gtk.AccessibleProperty.LABEL], [attachment["name"]])
    picture.set_halign(Gtk.Align.START)
    frame = Gtk.AspectFrame(ratio=4 / 3 if draft else 1, obey_child=False,
                            width_request=96 if draft else 104, height_request=72 if draft else 104,
                            css_classes=["image-thumbnail"], halign=Gtk.Align.START)
    frame.set_overflow(Gtk.Overflow.HIDDEN)
    frame.set_child(picture)
    if draft:
        return frame
    button = Gtk.Button(css_classes=["flat", "sent-image"], halign=Gtk.Align.START)
    button.set_child(frame)
    def show(_):
        dialog = Adw.Dialog(title=attachment["name"], content_width=800, content_height=600)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        try:
            original = texture(encoded or attachment.get("content") or data)
        except (GLib.Error, ValueError, TypeError, OSError):
            original = paintable
        full = Gtk.Picture(paintable=original,
                           can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN,
                           margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        toolbar.set_content(full)
        dialog.set_child(toolbar)
        dialog.present(button.get_root())
    button.connect("clicked", show)
    return button
