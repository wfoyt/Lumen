"""Capture the real Lumen UI with fictional, everyday conversations.

Run from the checkout with its Python dependencies and a desktop display:
    .venv/bin/python scripts/readme_screenshots.py

No Ollama requests, API calls, or personal settings/history are used. PNGs are
captured at 2× resolution, retaining GTK's own window shadow and rounded corners.
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import cairosvg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ollama_gui.app import Application, Window, Preferences, Adw, Gio, GLib, Gtk
from ollama_gui import history
from ollama_gui.storage import Store, PYTHON_SERVER_NAME
from ollama_gui.attachments import image_attachment, user_message
from gi.repository import Gsk

OUTPUT = Path(__file__).resolve().parents[1] / "docs/screenshots"
WIDTH, HEIGHT, SCALE = 1000, 700, 2
MODEL = "qwen3:8b"


def assistant(content, model=MODEL):
    return {"role": "assistant", "content": content, "model": model}


def user(content):
    return {"role": "user", "content": content}


def chart_attachment():
    # Original vector sample: the values match the notes and the sample reply.
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
    <rect width="640" height="360" rx="20" fill="#f6f8fc"/>
    <g font-family="sans-serif" fill="#233047">
      <text x="40" y="55" font-size="24" font-weight="bold">Community garden sign-ups</text>
      <text x="40" y="84" font-size="15" fill="#5c687c">New members · spring season</text>
      <path d="M60 285 H590" stroke="#d1d8e4"/>
      <rect x="105" y="189" width="100" height="96" rx="8" fill="#9bc7b0"/>
      <rect x="270" y="153" width="100" height="132" rx="8" fill="#64a987"/>
      <rect x="435" y="117" width="100" height="168" rx="8" fill="#35845c"/>
      <g font-size="20" text-anchor="middle" font-weight="bold">
        <text x="155" y="177">120</text><text x="320" y="141">165</text><text x="485" y="105">210</text>
      </g>
      <g font-size="17" text-anchor="middle">
        <text x="155" y="317">March</text><text x="320" y="317">April</text><text x="485" y="317">May</text>
      </g>
    </g></svg>'''
    return image_attachment(cairosvg.svg2png(bytestring=svg.encode()), "spring-signups.png")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Keep the screenshot session independent of live services and user data.
    with tempfile.TemporaryDirectory(prefix="lumen-screenshots-") as root, \
            patch.object(Window, "refresh_models"), \
            patch.object(Window, "refresh_tools"), \
            patch.object(Window, "request_title"):
        app = Application()
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        app.register(None)
        store = Store(root)
        store.settings.update(setup_completed=True, model=MODEL)
        titles = ["Weeknight dinners", "Garden project update", "Cabin weekend costs",
                  "Back up my laptop", "Scale my coffee recipe", "A friendlier email"]
        store.chats = [{"id": str(i), "title": title, "title_source": "manual",
                        "messages": [user(title)]} for i, title in enumerate(titles)]
        window = Window(app, store)
        window.set_default_size(WIDTH, HEIGHT)
        window.model_names = [MODEL, "llama3.2:latest", "gemma3:4b"]
        window.capability_cache = {(store.settings["url"], name):
                                   {"vision"} if name == "gemma3:4b" else {"tools"}
                                   for name in window.model_names}
        window.models.set_model(Gtk.StringList.new(window.model_names))
        window.tool_catalog = [{"name": "execute_python", "server": PYTHON_SERVER_NAME,
                                "description": "Run Python calculations"}]
        window.render_tool_choices()
        paintable = Gtk.WidgetPaintable.new(window)
        style = Adw.StyleManager.get_default()
        original_style = style.get_color_scheme()
        style.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        window.present()
        loop = GLib.MainLoop()
        errors = []
        preferences = None

        def close():
            if preferences:
                preferences.close()
            style.set_color_scheme(original_style)
            window.worker.close()
            window.destroy()
            loop.quit()

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
            GLib.timeout_add(900, run)

        def capture(name):
            assert (window.get_width(), window.get_height()) == (WIDTH, HEIGHT)
            if name != "preferences":
                ok, last = window.messages.get_last_child().compute_bounds(window.scroll)
                assert ok and last.get_y() + last.get_height() <= window.scroll.get_height(), \
                    f"{name}: answer would be cut off; shorten the sample conversation"
            snapshot = Gtk.Snapshot()
            paintable.snapshot(snapshot, WIDTH, HEIGHT)
            node = snapshot.to_node()
            assert node is not None, "No rendered window"
            # WidgetPaintable adds a rectangular allocation clip that cuts off
            # CSD shadows. Retain the native render tree inside that outer clip.
            if isinstance(node, Gsk.ClipNode):
                node = node.get_child()
            bounds = node.get_bounds()
            assert bounds.get_x() < 0, "Native window shadow missing"
            high_resolution = Gtk.Snapshot()
            high_resolution.scale(SCALE, SCALE)
            high_resolution.append_node(node)
            texture = window.get_renderer().render_texture(high_resolution.to_node(), None)
            path = OUTPUT / f"{name}.png"
            assert texture.save_to_png(str(path)), f"Could not save {path}"
            print(f"Saved {path.name} ({texture.get_width()} × {texture.get_height()})", flush=True)

        def conversation(index, messages, model=MODEL):
            window.current = store.chats[index]
            window.current.pop("branches", None)
            window.current.pop("branch_index", None)
            window.current["messages"] = messages
            store.settings["model"] = model
            window.models.set_selected(window.model_names.index(model))
            window.update_image_controls()
            window.render_sidebar()
            window.render_chat()
            window.update_actions()
            # Wait for asynchronous math/layout updates before resetting scroll.
            GLib.timeout_add(600, lambda: window.scroll.get_vadjustment().set_value(0))

        def meal_plan():
            conversation(0, [user("I have chickpeas, rice, spinach and eggs. Plan three quick dinners for two, with as little extra shopping as possible."),
                assistant("## Three dinners, one small shop\n\nEach takes about **20 minutes**. Cook extra rice on the first night.\n\n| Dinner | What to use |\n|---|---|\n| Chickpea curry | Chickpeas, spinach, coconut milk |\n| Egg fried rice | Leftover rice, eggs, spinach |\n| Crispy chickpea bowls | Rice, chickpeas, a fried egg |\n\n**Pick up:** curry paste and a can of coconut milk.")])
            later(light)

        def light():
            capture("chat-light")
            notes = {"kind": "file", "name": "garden-meeting.md", "content":
                     "# Garden team meeting\nSign-ups: March 120, April 165, May 210.\n"
                     "The shorter sign-up form launched in April.\n"
                     "Next: Maya drafts a welcome email by Friday.\n"
                     "Ben confirms volunteer shifts by Thursday.\n"}
            conversation(1, [user_message("Turn this chart and our meeting notes into a short update for the garden volunteers. Include the next steps.", [chart_attachment(), notes]),
                assistant("## A strong start to the season\n\nSign-ups grew **75%**, from **120 in March to 210 in May**. We also launched a shorter sign-up form in April.\n\n**Next steps**\n\n- **Maya:** draft the welcome email by Friday.\n- **Ben:** confirm volunteer shifts by Thursday.", "gemma3:4b")], "gemma3:4b")
            later(attachments)

        def attachments():
            capture("attachments")
            code = 'total = 480 + 132 + 48\nprint(f"Total: ${total:.2f} | Each: ${total / 4:.2f}")'
            # Execute the harmless fixture rather than inventing Python output.
            namespace = {}
            from contextlib import redirect_stdout
            from io import StringIO
            output = StringIO()
            with redirect_stdout(output):
                exec(code, namespace)
            conversation(2, [user("Split our cabin costs ($480 + $132 + $48) four ways. Check with Python."),
                {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "s1_execute_python", "arguments": {"code": code}}}]},
                {"role": "tool", "tool_name": "s1_execute_python", "content": json.dumps({"exit_code": 0, "stdout": output.getvalue(), "stderr": ""})},
                assistant("**$660.00 total → $165.00 per person**, split four ways.")])
            expand_tools()
            later(python)

        def expand_tools():
            child = window.activity_box.get_first_child()
            while child:
                if isinstance(child, Gtk.Expander):
                    child.set_expanded(True)
                child = child.get_next_sibling()

        def python():
            capture("tools")
            # Search results are illustrative fixtures, using real official pages.
            results = {"results": [
                {"title": "How to back up — GNOME Help", "url": "https://help.gnome.org/gnome-help/backup-how.html", "description": "Choose a backup app or copy your personal files to an external drive."},
                {"title": "Déjà Dup Backups — Apps for GNOME", "url": "https://apps.gnome.org/DejaDup/", "description": "Schedule backups and restore files from a local drive, network or cloud storage."}]}
            conversation(3, [user("I'm reinstalling Linux this weekend. Find official guides for backing up my personal files first."),
                {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "s0_brave_web_search", "arguments": {"query": "GNOME back up personal files official guide"}}}]},
                {"role": "tool", "tool_name": "s0_brave_web_search", "content": json.dumps(results)},
                assistant("Start with **GNOME Help** for the basics, or **Déjà Dup** for scheduled backups. Before reinstalling, check that you can restore a few files from your backup.")])
            expand_tools()
            later(search)

        def search():
            capture("web-search")
            conversation(4, [user("My coffee recipe uses 30 g of coffee for 500 g of water. How much coffee for 750 g of water? Show the formula and a reusable Python function."),
                assistant(r'''Use **45 g of coffee** to keep the same ratio.

\[\text{coffee} = \frac{30}{500} \times 750 = 45\,\text{g}\]

```python
def coffee_grams(water_grams):
    return water_grams * 30 / 500

print(coffee_grams(750))  # 45.0
```

Change `750` to the amount of water you want to brew.''')])
            later(math)

        def math():
            capture("equations-code")
            style.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            conversation(5, [
                user("Make this less abrupt: 'Alex, send the slides by Thursday. I need time to rehearse.'"),
                assistant("Hi Alex, could you send me the slides by Thursday? I'd like time to rehearse before our presentation. Thanks!"),
                user("A little warmer, please. Still keep it short."),
                assistant("Hey Alex, could you send over the slides by Thursday? That would give me time to rehearse. Thanks so much!")])
            history.fork(window.current, 2, model=MODEL)
            window.current["messages"].append(assistant("Hey Alex! Could you send the slides by Thursday so I have time to rehearse? Really appreciate it!"))
            window.render_chat()
            GLib.timeout_add(600, lambda: window.scroll.get_vadjustment().set_value(0))
            later(dark)

        def dark():
            capture("chat-dark")
            style.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            nonlocal preferences
            preferences = Preferences(window)
            preferences.present(window)
            preferences.set_visible_page(preferences.tools_page)
            later(settings)

        def settings():
            capture("preferences")
            later(close)

        later(meal_plan)
        loop.run()
        if errors:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
