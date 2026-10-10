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
from ollama_gui.branding import LanternPaintable
from ollama_gui import branding

Adw.init()
style = Adw.StyleManager.get_default()
original = style.get_color_scheme()
paintable = LanternPaintable()
invalidations = []
paintable.connect("invalidate-contents", lambda *_: invalidations.append(True))
try:
    for scheme, value in ((Adw.ColorScheme.FORCE_LIGHT, 0), (Adw.ColorScheme.FORCE_DARK, 255)):
        style.set_color_scheme(scheme)
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        for size in (128, 1024):
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
            paintable.draw(cairo.Context(surface), size, size)
            surface.flush()
            data = bytes(surface.get_data())
            pixels = [data[i:i + 4] for i in range(0, len(data), 4)]
            opaque = [p for p in pixels if p[3] == 255]
            assert opaque, "Lantern did not render"
            assert all(p[:3] == bytes([value] * 3) for p in opaque), "Incorrect theme color"
            assert any(p[3] == 0 for p in pixels), "Transparency lost"
            assert any(0 < p[3] < 255 for p in pixels), "Antialiased vector edges missing"
        # Exercise the Gdk.Paintable snapshot used by the empty state.
        paintable.snapshot(Gtk.Snapshot(), 128, 128)
    assert invalidations, "Changing themes did not invalidate the paintable"
finally:
    paintable.close()
    style.set_color_scheme(original)
assert paintable.style_handler is None
icons = Path(branding.__file__).parent / "icons"
for name in ("io.github.ollamagnome.Lumen.svg", "hicolor/scalable/apps/lumen-symbolic.svg"):
    root = ET.parse(icons / name).getroot()
    assert not any(e.tag.split("}")[-1] == "image" for e in root.iter()), "Embedded raster image"
print("Branding passed: vector icons, black in light mode, white in dark mode, live theme changes, smooth edges at 128/1024px, snapshot and cleanup.")
