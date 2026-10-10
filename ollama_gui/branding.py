"""Render the vector lantern at the requested size and current theme color."""
from pathlib import Path
import gi
gi.require_version("Rsvg", "2.0")
from gi.repository import Adw, Gdk, GObject, Graphene, Rsvg

APP_ID = "io.github.ollamagnome.Lumen"


class LanternPaintable(GObject.Object, Gdk.Paintable):
    def __init__(self):
        super().__init__()
        self.svg = Rsvg.Handle.new_from_file(str(Path(__file__).parent / "icons/hicolor/scalable/apps/lumen-symbolic.svg"))
        self.style = Adw.StyleManager.get_default()
        self.style_handler = self.style.connect("notify::dark", lambda *_: self.invalidate_contents())

    def do_get_intrinsic_width(self):
        return 128

    def do_get_intrinsic_height(self):
        return 128

    def do_get_intrinsic_aspect_ratio(self):
        return 1.0

    def do_snapshot(self, snapshot, width, height):
        context = snapshot.append_cairo(Graphene.Rect().init(0, 0, width, height))
        self.draw(context, width, height)

    def draw(self, context, width, height):
        if width <= 0 or height <= 0:
            return
        viewport = Rsvg.Rectangle()
        viewport.x = viewport.y = 0
        viewport.width, viewport.height = width, height
        # Render paths at the final size, then recolor their alpha coverage.
        context.push_group()
        self.svg.render_document(context, viewport)
        mask = context.pop_group()
        value = 1 if self.style.get_dark() else 0
        context.set_source_rgb(value, value, value)
        context.mask(mask)

    def close(self):
        if self.style_handler is not None:
            self.style.disconnect(self.style_handler)
            self.style_handler = None
