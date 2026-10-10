"""Capture README screenshots using sample conversations and disposable data."""
import json
import sys
import tempfile
import cairosvg
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ollama_gui.app import Application, Window, Preferences, Adw, Gio, GLib, Gtk
from ollama_gui.storage import Store
from ollama_gui.attachments import image_attachment, user_message

OUTPUT = Path(__file__).resolve().parents[1] / 'docs/screenshots'
OUTPUT.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory() as root, patch.object(Window, 'refresh_models'), patch.object(Window, 'refresh_tools'), patch.object(Window, 'request_title'):
    app = Application()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    store = Store(root)
    store.settings['setup_completed'] = True
    store.chats = [{'id': 'welcome', 'title': 'A little inspiration', 'title_source': 'manual', 'messages': []}]
    window = Window(app, store)
    window.set_default_size(1080, 800)
    window.models.set_model(Gtk.StringList.new(['llama3.2:latest', 'qwen3:8b']))
    for i, title in enumerate(['Plan a weekend away', 'Understand my notes', 'Help with Python', 'A quick calculation']):
        store.chats.append({'id': str(i), 'title': title, 'title_source': 'manual', 'messages': [{'role': 'user', 'content': title}]})
    window.render_sidebar()
    paintable = Gtk.WidgetPaintable.new(window)
    style = Adw.StyleManager.get_default()
    original_style = style.get_color_scheme()
    style.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
    window.present()
    loop = GLib.MainLoop()
    errors = []

    def capture(name):
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        assert node is not None
        window.get_renderer().render_texture(node, None).save_to_png(str(OUTPUT / f'{name}.png'))
        print('Saved', name, flush=True)

    def conversation(title, messages):
        window.current['title'] = title
        window.current['messages'] = messages
        window.render_sidebar()
        window.render_chat()
        window.update_actions()
        GLib.idle_add(lambda: window.scroll.get_vadjustment().set_value(0))

    def later(callback):
        def run():
            try:
                callback()
            except BaseException:
                import traceback
                traceback.print_exc()
                errors.append(True)
                close()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(650, run)

    def chat():
        conversation('A little inspiration', [
            {'role': 'user', 'content': 'Help me make more time for reading.'},
            {'role': 'assistant', 'content': '## Make room for a good book\n\nStart small: **ten minutes a day** is enough to build a habit.\n\n- Keep a book where you usually relax.\n- Read a few pages with your morning coffee.\n- Choose something you actually look forward to.\n\n> The best reading routine is one you enjoy.\n\n| When | A simple idea |\n|---|---|\n| Morning | A chapter with coffee |\n| Lunch break | A short story |\n| Evening | Put your phone aside and read |\n\nWould you like help choosing your next book?'}])
        later(light)

    def light():
        capture('chat-light')
        style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        later(dark)

    def dark():
        capture('chat-dark')
        icon = Path(__file__).resolve().parents[1] / 'ollama_gui/icons/io.github.ollamagnome.Lumen.svg'
        picture = image_attachment(cairosvg.svg2png(url=str(icon), output_width=512, output_height=512), 'Lumen.png')
        notes = {'kind': 'file', 'name': 'weekend-notes.md', 'content': '# Weekend ideas\nVisit a bookshop, walk in the park, and try a new café.'}
        conversation('Pictures, PDFs and notes', [user_message('Describe this picture and help organize my notes.', [picture, notes]), {'role': 'assistant', 'content': '## A warm little lantern\n\nThe picture shows a glowing lantern. It would make a lovely illustration for your weekend journal.\n\nYour notes suggest a relaxed day:\n\n1. Browse a **local bookshop**.\n2. Take a walk in the park.\n3. Finish with coffee somewhere new.\n\nYou can keep adding pictures or documents as we plan.'}])
        window.attachments = [notes]
        window.render_attachments()
        later(attachments)

    def attachments():
        capture('attachments')
        window.attachments = []
        window.render_attachments()
        conversation('A quick calculation', [{'role': 'user', 'content': 'Explain the quadratic formula with an example.'}, {'role': 'assistant', 'content': r'''## Solve a quadratic

For an equation of the form \(ax^2 + bx + c = 0\), use:

\[x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}\]

For **\(x^2 - 3x + 2 = 0\)**, the solutions are **\(x = 1\)** and **\(x = 2\)**.

You can check them with a short Python snippet:

```python
for x in (1, 2):
    print(x**2 - 3*x + 2)
```

Both results are zero, so both solutions work.'''}])
        later(math)

    def math():
        capture('equations-code')
        window.set_default_size(1080, 950)
        query = 'GNOME getting started'
        results = {'results': [{'title': 'GNOME', 'url': 'https://www.gnome.org/', 'description': 'A desktop designed to help you get things done.'}, {'title': 'GNOME Help', 'url': 'https://help.gnome.org/', 'description': 'Guides for your desktop and applications.'}]}
        code = 'prices = [12.50, 8.00, 4.50]\nprint(f"Total: ${sum(prices):.2f}")'
        conversation('Search and calculate', [
            {'role': 'user', 'content': 'Find GNOME guides and add up $12.50, $8 and $4.50.'},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 's0_brave_web_search', 'arguments': {'query': query}}}]},
            {'role': 'tool', 'tool_name': 's0_brave_web_search', 'content': json.dumps(results)},
            {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 's1_execute_python', 'arguments': {'code': code}}}]},
            {'role': 'tool', 'tool_name': 's1_execute_python', 'content': json.dumps({'exit_code': 0, 'stdout': 'Total: $25.00\n', 'stderr': ''})},
            {'role': 'assistant', 'content': 'Start with **GNOME Help** for desktop guides. Your total is **$25.00**.'}])
        child = window.activity_box.get_first_child()
        while child:
            if isinstance(child, Gtk.Expander):
                child.set_expanded(True)
            child = child.get_next_sibling()
        later(tools)

    def tools():
        capture('tools')
        window.preferences_preview = Preferences(window)
        window.preferences_preview.present(window)
        window.preferences_preview.set_visible_page(window.preferences_preview.tools_page)
        later(preferences)

    def preferences():
        capture('preferences')
        window.preferences_preview.close()
        later(close)

    def close():
        style.set_color_scheme(original_style)
        window.worker.close()
        window.destroy()
        loop.quit()

    later(chat)
    loop.run()
    if errors:
        raise SystemExit(1)
