"""Verify vector artwork and actual light/dark rendering in a GTK session."""
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk
import cairo
from ollama_gui.branding import LumenPaintable
from ollama_gui import branding

Adw.init()
style = Adw.StyleManager.get_default()
original = style.get_color_scheme()
paintable = LumenPaintable()
invalidations = []
paintable.connect("invalidate-contents", lambda *_: invalidations.append(True))
try:
    for scheme, value in ((Adw.ColorScheme.FORCE_LIGHT, 0), (Adw.ColorScheme.FORCE_DARK, 255), (Adw.ColorScheme.FORCE_LIGHT, 0)):
        style.set_color_scheme(scheme)
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        for size in (16, 32, 128, 1024):
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
            paintable.draw(cairo.Context(surface), size, size)
            surface.flush()
            data = bytes(surface.get_data())
            pixels = [data[i:i + 4] for i in range(0, len(data), 4)]
            opaque = [p for p in pixels if p[3] == 255]
            assert opaque, "Lumen icon did not render"
            assert all(p[:3] == bytes([value] * 3) for p in opaque), "Incorrect theme color"
            assert any(p[3] == 0 for p in pixels), "Transparency lost"
            assert any(0 < p[3] < 255 for p in pixels), "Antialiased vector edges missing"
            # Bubble opening and filament must stay transparent in both themes.
            if size == 128:
                stride = surface.get_stride()
                for x, y in ((30, 60), (64, 70), (64, 80)):
                    assert data[y * stride + x * 4 + 3] == 0, "Monochrome cutout lost"
        # Exercise the Gdk.Paintable snapshot used by the empty state.
        paintable.snapshot(Gtk.Snapshot(), 128, 128)
    assert len(invalidations) >= 2, "Theme changes did not invalidate the paintable in both directions"
finally:
    paintable.close()
    style.set_color_scheme(original)
assert paintable.style_handler is None
icons = Path(branding.__file__).parent / "icons"
for name in ("io.github.ollamagnome.Lumen.svg", "hicolor/scalable/apps/lumen-symbolic.svg"):
    root = ET.parse(icons / name).getroot()
    assert not any(e.tag.split("}")[-1] == "image" for e in root.iter()), "Embedded raster image"
print("Branding passed: vector icons, black/white/black theme switching, transparent cutouts, smooth edges at 16/32/128/1024px, snapshot and cleanup.")
