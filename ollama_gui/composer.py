"""A composer that grows with wrapped text before enabling scrolling."""
from gi.repository import GLib, Gtk


class ComposerTextView(Gtk.TextView):
    def __init__(self, resized):
        super().__init__(wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=16,
                         right_margin=16, top_margin=16, bottom_margin=12)
        self.resized = resized
        self.previous_width = -1

    def do_size_allocate(self, width, height, baseline):
        Gtk.TextView.do_size_allocate(self, width, height, baseline)
        if width != self.previous_width:
            self.previous_width = width
            self.resized()


class ComposerScroll(Gtk.ScrolledWindow):
    MIN_HEIGHT = 60
    MAX_HEIGHT = 180

    def __init__(self):
        super().__init__(min_content_height=self.MIN_HEIGHT,
                         max_content_height=self.MIN_HEIGHT,
                         propagate_natural_height=True,
                         hscrollbar_policy=Gtk.PolicyType.NEVER,
                         vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        self.measure_pending = None
        self.view = ComposerTextView(self.queue_measure)
        self.set_child(self.view)
        self.view.get_buffer().connect("changed", lambda *_: self.queue_measure())
        self.connect("map", lambda *_: self.queue_measure())

    def queue_measure(self):
        if self.measure_pending is None:
            self.measure_pending = GLib.idle_add(self.update_height)

    def update_height(self):
        self.measure_pending = None
        if not self.view.get_root() or self.view.get_width() <= 0:
            return GLib.SOURCE_REMOVE
        # Measure rendered lines so wrapping, pasted text and window resizing
        # all use the actual font metrics rather than a newline count.
        y, height = self.view.get_line_yrange(self.view.get_buffer().get_end_iter())
        content_height = y + height + self.view.get_top_margin() + self.view.get_bottom_margin()
        target = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, content_height))
        if target > self.get_max_content_height():
            self.set_max_content_height(target)
        self.set_min_content_height(target)
        self.set_max_content_height(target)
        if content_height <= self.MAX_HEIGHT:
            self.get_vadjustment().set_value(0)
        return GLib.SOURCE_REMOVE

    def do_unroot(self):
        if self.measure_pending is not None:
            GLib.source_remove(self.measure_pending)
            self.measure_pending = None
        Gtk.ScrolledWindow.do_unroot(self)
