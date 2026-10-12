"""Exercise live search and transcript scrolling with temporary chats."""
import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ollama_gui.app import Application, Window, Ollama, Gio, GLib
from ollama_gui.storage import Store
from ollama_gui import history


async def reply(self, model, messages, servers, emit):
    await asyncio.sleep(.03)
    emit("token", "unique-reply-needle")
    return [{"role": "assistant", "content": "unique-reply-needle"}]


with tempfile.TemporaryDirectory() as folder, patch.object(Window, "refresh_models"), patch.object(Window, "refresh_tools"), patch.object(Window, "request_title"), patch.object(Application, "notify_completion"), patch.object(Ollama, "chat", reply):
    app = Application()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    store = Store(folder)
    store.settings.update(setup_completed=True, auto_titles=False, model="test")
    window = Window(app, store)
    window.model_names = ["test"]
    window.present()
    loop = GLib.MainLoop()
    errors = []
    long_reply = "\n\n".join(f"Paragraph {i}: " + "example " * 40 for i in range(40))

    def search(query, expected):
        window.search_entry.set_text(query)
        row = window.chat_list.get_first_child()
        assert row.get_child_visible() == expected, query
        assert window.sidebar_results.get_visible_child_name() == ("results" if expected else "empty"), query

    def start():
        window.input.get_buffer().set_text("Question")
        window.send_or_stop(None)
        later(completed_search)

    def completed_search():
        assert not window.busy
        search("unique-reply-needle", True)
        window.search_entry.set_text("")
        parent = history.fork(window.current, 0)
        window.current["messages"].append({"role": "assistant", "content": "alternate-version-needle"})
        window.render_chat()
        search("alternate-version-needle", True)
        window.select_version(parent)
        search("alternate-version-needle", False)
        search("unique-reply-needle", True)
        window.search_entry.set_text("")
        window.current["messages"].append({"role": "user", "content": "cancelled-question-needle"})
        window.render_sidebar()
        search("cancelled-question-needle", True)
        window.finished(None, asyncio.CancelledError())
        search("cancelled-question-needle", False)
        window.search_entry.set_text("")
        window.current["messages"] = [
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": long_reply},
            {"role": "user", "content": "Follow-up"},
        ]
        window.render_chat()
        window.set_busy(True)
        window.event("token", "Streaming answer")
        later(pause_scroll)

    def bottom():
        adjustment = window.scroll.get_vadjustment()
        return adjustment.get_upper() - adjustment.get_page_size()

    def pause_scroll():
        adjustment = window.scroll.get_vadjustment()
        assert bottom() > 100
        assert abs(adjustment.get_value() - bottom()) < 2
        # Scroll away while an automatic move is already queued.
        window.scroll_bottom()
        adjustment.set_value(100)
        assert not window.follow_response
        window.event("token", "\n\n" + "More output. " * 100)
        later(paused)

    def paused():
        assert abs(window.scroll.get_vadjustment().get_value() - 100) < 2
        assert not window.follow_response
        window.set_default_size(900, 760)
        later(resized)

    def resized():
        assert abs(window.scroll.get_vadjustment().get_value() - 100) < 2
        assert not window.follow_response
        # Final rendering must preserve the reader's position as well.
        window.finished([{"role": "assistant", "content": "Streaming answer\n\n" + "More output. " * 100}], None)
        later(completed_scroll)

    def completed_scroll():
        assert abs(window.scroll.get_vadjustment().get_value() - 100) < 2
        assert not window.follow_response
        window.scroll.get_vadjustment().set_value(bottom())
        assert window.follow_response
        window.set_busy(True)
        window.event("token", "\n\n" + "Following again. " * 100)
        later(resumed)

    def resumed():
        assert window.follow_response
        assert abs(window.scroll.get_vadjustment().get_value() - bottom()) < 2
        window.set_busy(False)
        print("PASS: completed replies, version changes and cancelled turns update search; scrolling pauses queued/live updates, survives resize/completion and resumes at the bottom")
        close()

    def close():
        window.close()
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

    GLib.timeout_add(500, checked, start)
    loop.run()
    if errors:
        raise SystemExit(1)
