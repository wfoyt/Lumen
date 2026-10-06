"""Native equation layout checks and screenshots, using isolated temporary data."""
import sys
import tempfile
from io import BytesIO
from PIL import Image
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ollama_gui.app import Application, Window, Preferences, Gtk, Adw, Gio, GLib
from ollama_gui.storage import Store
from ollama_gui.markdown_view import MarkdownView
from ollama_gui.math_view import Equation, MathParagraph
from ollama_gui.attachments import image_attachment

SOURCE = r"""## Quadratic formula

For **real roots**, use \(b^2 - 4ac \geq 0\). The [reference](https://example.com/quadratic) explains the formula. [1]

\[
\boxed{x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}}
\]

For \(a=1\), \(b=-3\), and \(c=2\), the solutions are **\(x=1\)** and **\(x=2\)**.

### Sum and integral

$$\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$$

\[\int_0^1 x^2\,dx = \frac{1}{3}\]

\[\begin{aligned}x+y &= 5 \\ x-y &= 1\end{aligned}\]

\[A = \begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}\]

\[f(x)=\begin{cases}x^2 & x>0 \\ 0 & x\le 0\end{cases}\]

- Inline fractions also work: \(\frac{1}{2} + \frac{1}{3} = \frac{5}{6}\).
- A long equation shrinks to fit the available width:

\[y = a_1 x + a_2 x^2 + a_3 x^3 + a_4 x^4 + a_5 x^5 + a_6 x^6 + a_7 x^7\]

`\(code remains literal\)` and prices such as $5 or $10 stay plain text.
"""


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


with tempfile.TemporaryDirectory() as directory, patch.object(Window, "refresh_models"), patch.object(Window, "refresh_tools"), patch.object(Window, "request_title"):
    app = Application()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    store = Store(directory)
    store.chats = [{"id": "math", "title": "Quadratic Roots", "title_source": "manual", "messages": [
        {"role": "user", "content": "Explain these equations"},
        {"role": "assistant", "content": SOURCE},
    ]}]
    window = Window(app, store)
    window.set_default_size(1080, 1000)
    window.paintable = Gtk.WidgetPaintable.new(window)
    window.present()
    loop = GLib.MainLoop()
    errors = []
    style = Adw.StyleManager.get_default()
    original_style = style.get_color_scheme()
    style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def screenshot(path):
        snapshot = Gtk.Snapshot()
        window.paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        assert node is not None
        window.get_renderer().render_texture(node, None).save_to_png(path)
        print("Saved", path)

    def checked(callback):
        try:
            callback()
        except BaseException as error:
            errors.append(error)
            import traceback
            traceback.print_exc()
            close()
        return GLib.SOURCE_REMOVE

    def wide():
        view = next(item for item in descendants(window.messages) if isinstance(item, MarkdownView))
        equations = [item for item in descendants(view) if isinstance(item, Equation)]
        assert len(equations) >= 10
        assert all(item.get_height() > 5 and item.get_width() > 5 for item in equations if item.get_mapped())
        paragraphs = [item for item in descendants(view) if isinstance(item, MathParagraph)]
        assert not any(item.get_cursor_visible() or item.get_editable() for item in paragraphs)
        for item in paragraphs:
            y, height = item.get_line_yrange(item.get_buffer().get_end_iter())
            assert item.get_height() >= y + height
        assert any("https://example.com/quadratic" in item.links.values() for item in paragraphs)
        assert SOURCE == view.get_copy_text()
        fallback = MarkdownView(r"\(\unsupported{a}\)")
        assert not any(isinstance(item, Equation) for item in descendants(fallback))
        literal = MarkdownView(SOURCE, latex_enabled=False)
        assert not any(isinstance(item, Equation) for item in descendants(literal))
        assert r"\[" in literal.get_first_child().get_next_sibling().get_next_sibling().get_text()
        stream = MarkdownView()
        stream.set_text(r"\(\frac{1}{")
        stream.append_text(r"2}\)")
        stream.render()
        assert any(isinstance(item, Equation) for item in descendants(stream))
        inline_display = MarkdownView(r"Here is the equation: \[\frac{1}{2}\] then an explanation.")
        anchored = next(item for item in descendants(inline_display) if isinstance(item, Equation))
        assert anchored.display and anchored.measure(Gtk.Orientation.HORIZONTAL, -1).minimum > 0
        screenshot("/tmp/ollama-math-dark.png")
        style.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        GLib.timeout_add(400, checked, light)

    def light():
        screenshot("/tmp/ollama-math-light.png")
        style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        window.split.set_show_sidebar(False)
        window.set_default_size(360, 900)
        GLib.timeout_add(600, checked, narrow)

    def narrow():
        assert window.get_width() <= 360, window.get_width()
        assert window.messages.get_width() <= window.get_width()
        for equation in (item for item in descendants(window.messages) if isinstance(item, Equation)):
            assert equation.get_width() <= window.messages.get_width(), equation.get_width()
        screenshot("/tmp/ollama-math-narrow.png")
        window.set_default_size(1080, 1000)
        window.preferences = Preferences(window)
        window.preferences.present(window)
        window.preferences.set_visible_page(window.preferences.advanced_page)
        GLib.timeout_add(500, checked, advanced)

    def advanced():
        screenshot("/tmp/ollama-math-advanced.png")
        preferences = window.preferences
        assert preferences.url.is_ancestor(preferences.advanced_page)
        assert preferences.latex_enabled.get_active()
        preferences.latex_enabled.set_active(False)
        preferences.save(None)
        assert not Store(directory).settings["latex_enabled"]
        assert not any(isinstance(item, Equation) for item in descendants(window.messages))
        preferences = Preferences(window)
        preferences.present(window)
        assert not preferences.latex_enabled.get_active()
        preferences.latex_enabled.set_active(True)
        preferences.save(None)
        assert any(isinstance(item, Equation) for item in descendants(window.messages))
        window.preferences = Preferences(window)
        window.preferences.present(window)
        assert window.preferences.show_thinking.is_ancestor(window.preferences.general_page)
        GLib.timeout_add(500, checked, general)

    def general():
        screenshot("/tmp/ollama-math-general.png")
        window.preferences.close()
        window.clear_messages()
        window.stream_probe = window.message_card("assistant", "## Stable heading\n\nAn equation \\(x^2\\) in a paragraph.\n\n")
        window.stream_heading = window.stream_probe.get_first_child()
        window.stream_paragraph = window.stream_heading.get_next_sibling()
        window.stream_chunks = iter([r"\[", r"\boxed{", "x = ", r"\frac{", "-b", r"\pm\sqrt{", "b^2-4ac", "}}{2a}", r"}\]", "\n\nExplanation ", r"\(\frac{", "1}{2}", r"\)", " continues."])
        window.stream_heights = []
        window.set_busy(True)
        GLib.timeout_add(200, checked, stream_step)

    def stream_step():
        view = window.stream_probe
        assert view.get_first_child() is window.stream_heading
        assert window.stream_heading.get_next_sibling() is window.stream_paragraph
        height = view.get_height()
        if window.stream_heights:
            assert height >= window.stream_heights[-1], (window.stream_heights, height)
        window.stream_heights.append(height)
        try:
            chunk = next(window.stream_chunks)
        except StopIteration:
            assert sum(isinstance(item, Equation) for item in descendants(view)) == 3
            screenshot("/tmp/ollama-math-streaming.png")
            window.set_busy(False)
            # Sent files share the area above the user bubble with images.
            window.clear_messages()
            label = window.message_card("user", "Please read these.", [{"name": "report.pdf", "kind": "file"}, {"name": "notes.md", "kind": "file"}])
            group = window.messages.get_last_child()
            assert group.get_first_child() is not group.get_last_child()
            assert label.is_ancestor(group.get_last_child())
            assert not label.is_ancestor(group.get_first_child())
            assert sum(isinstance(item, Gtk.Label) and item.get_text() in ("report.pdf", "notes.md") for item in descendants(group.get_first_child())) == 2
            GLib.timeout_add(200, checked, attachments)
            return
        view.append_text(chunk)
        GLib.timeout_add(200, checked, stream_step)

    def attachments():
        screenshot("/tmp/ollama-sent-files.png")
        source = BytesIO()
        Image.new("RGB", (80, 60), "steelblue").save(source, format="PNG")
        image = image_attachment(source.getvalue(), "photo.png")
        window.input.get_buffer().set_text("Draft for the new chat")
        window.attachments = [{"name": "notes.md", "kind": "file", "content": "Some notes"}, image]
        window.render_attachments()
        original = window.current
        window.new_chat()
        new = window.current
        assert new is not original and not new["messages"]
        assert window.input.get_buffer().get_text(*window.input.get_buffer().get_bounds(), False) == "Draft for the new chat"
        assert len(window.attachments) == 2 and window.attachments[1]["content"] == image["content"]
        assert window.attachments is not window.drafts[original["id"]]["attachments"]
        window.attachments.pop()
        window.activate_chat(original)
        assert len(window.attachments) == 2
        window.input.get_buffer().set_text("Another draft")
        window.new_chat()
        assert window.current is new and len(window.attachments) == 1
        assert window.input.get_buffer().get_text(*window.input.get_buffer().get_bounds(), False) == "Draft for the new chat"
        assert not window.lookup_action("new").get_enabled()
        print("PASS: boxed/aligned/matrix/cases equations, stable streaming widgets and heights, copied source, files above messages, draft text/file/image carryover and independence, themes, narrow width and persisted toggle")
        close()

    def close():
        style.set_color_scheme(original_style)
        window.worker.close()
        window.destroy()
        loop.quit()

    GLib.timeout_add(1200, checked, wide)
    loop.run()
    if errors:
        raise SystemExit(1)
