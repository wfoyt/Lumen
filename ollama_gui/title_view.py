"""Single-line sidebar labels with a native transparent fade at the edge."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk, Pango


class FadingTitle(Gtk.Label):
    def __init__(self, text):
        super().__init__(xalign=0, hexpand=True, single_line_mode=True,
                         ellipsize=Pango.EllipsizeMode.END, margin_start=6)
        self.set_text(text)

    def set_text(self, text):
        text = " ".join(text.split())
        Gtk.Label.set_text(self, text)
        self.set_tooltip_text(text)

    def do_snapshot(self, snapshot):
        layout = self.get_layout().copy()
        layout.set_ellipsize(Pango.EllipsizeMode.NONE)
        layout.set_width(-1)
        width, height = self.get_width(), self.get_height()
        if layout.get_pixel_size()[0] <= width or width <= 0:
            Gtk.Label.do_snapshot(self, snapshot)
            return
        bounds = Graphene.Rect().init(0, 0, width, height)
        start = Graphene.Point().init(0, 0)
        end = Graphene.Point().init(width, 0)
        opaque = Gdk.RGBA()
        opaque.parse("white")
        transparent = Gdk.RGBA()
        transparent.parse("white")
        transparent.alpha = 0
        stops = []
        for offset, color in ((0, opaque), (max(0, 1 - 28 / width), opaque), (1, transparent)):
            stop = Gsk.ColorStop()
            stop.offset, stop.color = offset, color
            stops.append(stop)
        snapshot.push_clip(bounds)
        # GTK's mask records the gradient first, then the label as its source.
        snapshot.push_mask(Gsk.MaskMode.ALPHA)
        snapshot.append_linear_gradient(bounds, start, end, stops)
        snapshot.pop()
        _, y = self.get_layout_offsets()
        snapshot.save()
        snapshot.translate(Graphene.Point().init(0, y))
        snapshot.append_layout(layout, self.get_color())
        snapshot.restore()
        snapshot.pop()
        snapshot.pop()
