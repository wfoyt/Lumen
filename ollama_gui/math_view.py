"""Native inline math anchors and adaptive display equations."""
from io import BytesIO
import math
import xml.etree.ElementTree as ET
import cairo
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gtk, Pango, Graphene, GLib
from .math_render import equation_png


class Equation(Gtk.Widget):
    def __init__(self, source, png, display=False, anchored=False):
        super().__init__(hexpand=display)
        self.source = source
        self.display = display
        self.anchored = anchored
        self.surface = cairo.ImageSurface.create_from_png(BytesIO(png))
        self.natural_width = self.surface.get_width() / 2
        self.natural_height = self.surface.get_height() / 2
        self.set_tooltip_text(source)
        self.update_property([Gtk.AccessibleProperty.LABEL], ["Equation: " + source])

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            width = max(1, math.ceil(min(self.natural_width, 640 if self.display and not self.anchored else 224)))
            # TextView anchors allocate their minimum width, rather than their
            # natural width. Cap inline math so it can wrap on narrow screens.
            return 0 if self.display and not self.anchored else width, width, -1, -1
        scale = min(1, max(1, for_size) / self.natural_width) if for_size >= 0 else 1
        height = max(1, math.ceil(self.natural_height * scale))
        return height, height, -1, -1

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        if width <= 0 or height <= 0:
            return
        scale = min(1, width / self.natural_width, height / self.natural_height)
        context = snapshot.append_cairo(Graphene.Rect().init(0, 0, width, height))
        context.translate((width - self.natural_width * scale) / 2 if self.display else 0,
                          (height - self.natural_height * scale) / 2)
        context.scale(scale / 2, scale / 2)
        color = self.get_color()
        context.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        context.mask_surface(self.surface, 0, 0)


def equation_widget(source, display=False, literal=None):
    png = equation_png(source, display)
    if png is not None:
        return Equation(source, png, display)
    label = Gtk.Label(label=literal or source, wrap=True, selectable=True, xalign=0,
                      hexpand=True, wrap_mode=Pango.WrapMode.WORD_CHAR)
    label.set_tooltip_text("This equation uses unsupported or incomplete LaTeX; its source is shown.")
    return label


class MathParagraph(Gtk.TextView):
    """Use real text flow with selectable formatting and ordinary Markdown links."""
    def __init__(self, markup):
        super().__init__(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                         hexpand=True, pixels_above_lines=2, pixels_below_lines=2)
        self.add_css_class("math-paragraph")
        self.links = {}
        self.equations = []
        self.measure_pending = None
        self.previous_width = -1
        self.height_floor = 0
        root = ET.fromstring("<markup>" + markup + "</markup>")
        self.add_element(root, [])
        click = Gtk.GestureClick(button=1)
        click.connect("released", self.follow_link)
        self.add_controller(click)
        self.connect("map", lambda *_: self.queue_measure())

    def do_size_allocate(self, width, height, baseline):
        Gtk.TextView.do_size_allocate(self, width, height, baseline)
        if width != self.previous_width:
            self.previous_width = width
            self.queue_measure()

    def queue_measure(self):
        if self.measure_pending is None:
            self.measure_pending = GLib.idle_add(self.update_height)

    def update_height(self):
        self.measure_pending = None
        if self.get_root() and self.get_width() > 0:
            # TextView's initial request can omit the descent of embedded
            # anchors. Measure the fully laid-out final line after allocation.
            y, height = self.get_line_yrange(self.get_buffer().get_end_iter())
            self.set_size_request(-1, max(self.height_floor, y + height + self.get_top_margin() + self.get_bottom_margin() + 4))
        return GLib.SOURCE_REMOVE

    def do_unroot(self):
        if self.measure_pending is not None:
            GLib.source_remove(self.measure_pending)
            self.measure_pending = None
        Gtk.TextView.do_unroot(self)

    def insert_text(self, text, tags):
        if text:
            self.get_buffer().insert_with_tags(self.get_buffer().get_end_iter(), text, *tags)

    def add_element(self, element, tags):
        buffer = self.get_buffer()
        if element.tag == "math":
            source = element.text or ""
            display = element.attrib.get("display") == "1"
            png = equation_png(source, display)
            if png is None:
                self.insert_text(element.attrib["literal"], tags)
            else:
                if display:
                    self.insert_text("\n", [])
                start = buffer.get_char_count()
                equation = Equation(source, png, display, anchored=True)
                self.equations.append(equation)
                self.add_child_at_anchor(equation, buffer.create_child_anchor(buffer.get_end_iter()))
                if display:
                    self.insert_text("\n", [])
                    center = buffer.create_tag(None, justification=Gtk.Justification.CENTER)
                    buffer.apply_tag(center, buffer.get_iter_at_offset(start), buffer.get_end_iter())
            return
        props = {"b": {"weight": Pango.Weight.BOLD}, "i": {"style": Pango.Style.ITALIC},
                 "s": {"strikethrough": True}, "tt": {"family": "monospace"}}.get(element.tag)
        if element.tag == "a":
            props = {"underline": Pango.Underline.SINGLE, "foreground": "#3584e4"}
        if props:
            tag = buffer.create_tag(None, **props)
            tags = tags + [tag]
            if element.tag == "a":
                self.links[tag] = element.attrib["href"]
        self.insert_text(element.text, tags)
        for child in element:
            self.add_element(child, tags)
            self.insert_text(child.tail, tags)

    def follow_link(self, gesture, presses, x, y):
        if self.get_buffer().get_has_selection():
            return
        x, y = self.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        found, iterator = self.get_iter_at_location(x, y)
        if found:
            for tag in iterator.get_tags():
                if tag in self.links:
                    Gtk.UriLauncher.new(self.links[tag]).launch(self.get_root(), None, None)
                    return
