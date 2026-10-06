"""A compact selector with a separately sized, upward-opening model list."""
from gi.repository import GObject, Gtk, Pango


class ModelPicker(Gtk.MenuButton):
    selected = GObject.Property(type=int, default=0, minimum=0)

    def __init__(self, model):
        super().__init__(direction=Gtk.ArrowType.UP, css_classes=["composer-model"])
        self.model = model
        self.label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=22, hexpand=True)
        child = Gtk.Box(spacing=8)
        child.append(self.label)
        child.append(Gtk.Image(icon_name="pan-down-symbolic"))
        self.set_child(child)
        self.popover = Gtk.Popover(position=Gtk.PositionType.TOP)
        self.rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=["navigation-sidebar"])
        self.rows.connect("row-activated", self.choose)
        self.list_scroll = Gtk.ScrolledWindow(min_content_width=560, min_content_height=260,
                                             max_content_height=420, propagate_natural_height=True,
                                             hscrollbar_policy=Gtk.PolicyType.EXTERNAL)
        self.list_scroll.set_child(self.rows)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=12, margin_bottom=8, margin_start=8, margin_end=8)
        box.append(Gtk.Label(label="Choose a Model", xalign=0, margin_start=8, css_classes=["heading"]))
        box.append(self.list_scroll)
        self.popover.set_child(box)
        self.popover.connect("notify::visible", self.fit_popup)
        self.set_popover(self.popover)
        self.set_model(model)

    def fit_popup(self, *_):
        root = self.get_root()
        if root:
            # Leave room for the list padding and native popover shadows, too.
            self.list_scroll.set_min_content_width(min(560, max(160, root.get_width() - 96)))
            available = min(420, max(100, root.get_height() - 240))
            # Lower the minimum first when space is tight, keeping valid bounds.
            if available > self.list_scroll.get_max_content_height():
                self.list_scroll.set_max_content_height(available)
            self.list_scroll.set_min_content_height(min(260, available))
            self.list_scroll.set_max_content_height(available)

    def set_model(self, model):
        self.model = model
        while child := self.rows.get_first_child():
            self.rows.remove(child)
        for index in range(model.get_n_items()):
            row = Gtk.ListBoxRow()
            row.index = index
            row.set_child(Gtk.Label(label=model.get_string(index), wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                                    xalign=0, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12,
                                    max_width_chars=68))
            self.rows.append(row)
        self.set_selected(min(self.props.selected, max(0, model.get_n_items() - 1)))

    def get_model(self):
        return self.model

    def set_selected(self, index):
        self.props.selected = index
        item = self.get_selected_item()
        name = item.get_string() if item else "No models available"
        self.label.set_text(name)
        self.set_tooltip_text(name)
        self.rows.select_row(self.rows.get_row_at_index(index))

    def get_selected(self):
        return self.props.selected

    def get_selected_item(self):
        return self.model.get_item(self.props.selected)

    def choose(self, _, row):
        self.set_selected(row.index)
        self.popdown()
