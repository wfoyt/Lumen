"""Check real composer allocations with isolated app data and no network calls."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ollama_gui.app import Application, Window, Gio, GLib, Gtk
from ollama_gui.storage import Store

with tempfile.TemporaryDirectory() as directory, patch.object(Window, 'refresh_models'), patch.object(Window, 'refresh_tools'):
    app = Application()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    window = Window(app, Store(directory))
    window.set_default_size(1080, 800)
    window.present()
    loop = GLib.MainLoop()
    errors = []
    scroll = window.input_scroll
    view = window.input
    heights = []

    def content_height():
        y, height = view.get_line_yrange(view.get_buffer().get_end_iter())
        return y + height + view.get_top_margin() + view.get_bottom_margin()

    def check_fits():
        adjustment = scroll.get_vadjustment()
        print('height/content/range/page/value:', scroll.get_height(), content_height(), adjustment.get_upper(), adjustment.get_page_size(), adjustment.get_value())
        assert scroll.get_height() >= content_height()
        assert adjustment.get_upper() <= adjustment.get_page_size() + 1
        assert adjustment.get_value() == 0
        heights.append(scroll.get_height())

    def empty():
        check_fits()
        view.get_buffer().set_text('First line\nSecond line\nThird line\nFourth line')
        later(lines)

    def lines():
        check_fits()
        assert heights[-1] > heights[0]
        view.get_buffer().set_text('A long message with wrapping and comfortable padding. ' * 6)
        later(wrapped)

    def wrapped():
        check_fits()
        view.get_buffer().set_text('\n'.join(f'Line {i}' for i in range(40)))
        later(long)

    def long():
        adjustment = scroll.get_vadjustment()
        print('long height/content/range/page:', scroll.get_height(), content_height(), adjustment.get_upper(), adjustment.get_page_size())
        assert scroll.get_height() == scroll.MAX_HEIGHT
        assert adjustment.get_upper() > adjustment.get_page_size()
        assert abs(adjustment.get_upper() - content_height()) <= 1
        adjustment.set_value(adjustment.get_upper())
        assert adjustment.get_value() == adjustment.get_upper() - adjustment.get_page_size()
        view.get_buffer().set_text('Short again')
        later(short)

    def short():
        check_fits()
        assert scroll.get_height() == scroll.MIN_HEIGHT
        view.get_buffer().set_text('Wrapped content that changes height as the window gets narrower. ' * 5)
        later(before_resize)

    def before_resize():
        check_fits()
        window.split.set_show_sidebar(False)
        window.set_default_size(600, 800)
        later(narrow)

    def narrow():
        print('narrow window/view/height/content:', window.get_width(), view.get_width(), scroll.get_height(), content_height())
        assert scroll.get_height() > heights[-1]
        assert scroll.get_height() <= scroll.MAX_HEIGHT
        assert scroll.get_height() == min(scroll.MAX_HEIGHT, max(scroll.MIN_HEIGHT, content_height()))
        view.get_buffer().set_text('')
        later(cleared)

    def cleared():
        check_fits()
        assert scroll.get_height() == scroll.MIN_HEIGHT
        print('PASS: explicit lines, wrapping, capped scrolling, no excess scroll range, shrink/clear and window resizing')
        close()

    def close():
        window.worker.close()
        window.destroy()
        loop.quit()

    def checked(callback):
        try:
            callback()
        except BaseException as error:
            import traceback
            traceback.print_exc()
            errors.append(error)
            close()
        return GLib.SOURCE_REMOVE

    def later(callback):
        GLib.timeout_add(450, checked, callback)

    GLib.timeout_add(1000, checked, empty)
    loop.run()
    if errors:
        raise SystemExit(1)
