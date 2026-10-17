"""Exercise real GTK preferences and cross-chat memory with a simulated model."""
import asyncio
import copy
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ollama_gui.app import Application, Window, Preferences, Ollama, Gio, Gtk, GLib
from ollama_gui.storage import Store


requests, memory_requests = [], []


async def reply(self, model, messages, servers, emit):
    requests.append(copy.deepcopy(messages))
    await asyncio.sleep(.02)
    emit("token", "A test reply.")
    return [{"role": "assistant", "content": "A test reply."}]


async def extract(self, model, text, memories):
    memory_requests.append(text)
    if "waiting" in text:
        try:
            await asyncio.sleep(.7)
        except asyncio.CancelledError:
            pass  # Deliberately return late: cancelled checks must never write.
        fact, evidence = "The user likes waiting.", "I like waiting"
    elif "short replies" in text:
        fact, evidence = "The user prefers short replies.", "I prefer short replies"
    else:
        return {"save": [], "forget": []}
    return {"save": [{"text": fact, "evidence": evidence, "replaces": ""}], "forget": []}


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


with tempfile.TemporaryDirectory() as folder, patch.object(Window, "refresh_models"), patch.object(Window, "refresh_tools"), patch.object(Window, "request_title"), patch.object(Application, "notify_completion"), patch.object(Ollama, "chat", reply), patch.object(Ollama, "memory_update", extract):
    store = Store(folder)
    store.settings.update(setup_completed=True, tools_enabled=False, auto_titles=False, model="test-model")
    store.save()
    app = Application()
    app.set_application_id("io.github.ollamagnome.Lumen.PersonalizationCheck")
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.register(None)
    window = Window(app, store)
    window.model_names = ["test-model"]
    window.models.set_model(Gtk.StringList.new(window.model_names))
    window.present()
    loop = GLib.MainLoop()
    errors, dialogs = [], []
    paintable = Gtk.WidgetPaintable.new(window)

    def snapshot(path):
        canvas = Gtk.Snapshot()
        paintable.snapshot(canvas, window.get_width(), window.get_height())
        node = canvas.to_node()
        assert node is not None
        window.get_renderer().render_texture(node, None).save_to_png(path)

    def preferences():
        prefs = Preferences(window)
        dialogs.append(prefs)
        page = prefs.personalization
        prefs.set_visible_page(page)
        prefs.present(window)
        assert "tools or memory" in prefs.custom_warning.get_label()
        page.name_enabled.set_active(True)
        page.name.set_text("Ada Testname")
        page.about_enabled.set_active(True)
        page.about.get_buffer().set_text("I build test robots.")
        assert page.name_fields.get_visible() and page.about_fields.get_visible()
        prefs.flush_autosave()
        saved = Store(folder).settings
        assert saved["name_enabled"] and saved["user_name"] == "Ada Testname"
        assert saved["about_enabled"] and saved["user_about"] == "I build test robots."
        dialog = page.edit_memory()
        dialog.editor.get_buffer().set_text("The user likes jazz.")
        dialog.emit("response", "save")
        dialog.close()
        assert Store(folder).memories[0]["text"] == "The user likes jazz."
        page.test_memory()
        wait_until(first_capture, lambda: prefs.test_future is None)

    def first_capture():
        prefs = dialogs[-1]
        assert "working" in prefs.personalization.test_result.get_label(), prefs.personalization.test_result.get_label()
        assert len(store.memories) == 1  # Test button has no persistent side effects.
        snapshot("/tmp/lumen-personalization-wide.png")
        prefs.close()
        dialogs.pop()
        window.input.get_buffer().set_text("I prefer short replies.")
        window.send_or_stop(None)
        after_reply(first_reply)

    def first_reply():
        assert not window.busy
        prompt = requests[-1][0]["content"]
        assert all(text in prompt for text in ("Ada Testname", "I build test robots.", "The user likes jazz."))
        assert store.settings["auto_memory_enabled"]
        assert len(memory_requests) == 3  # Two no-write test requests, then ordinary conversation.
        assert len(store.memories) == 2
        assert "Memory updated" in window.memory_status
        window.saved_memory_snapshot = copy.deepcopy(store.memories)
        prefs = window.show_personalization()
        dialogs.append(prefs)
        page = prefs.personalization
        prefs.set_visible_page(page)
        prefs.present(window)
        page.name_enabled.set_active(False)
        page.about_enabled.set_active(False)
        assert not page.name_fields.get_visible() and not page.about_fields.get_visible()
        assert page.name.get_text() == "Ada Testname"
        page.name.set_text("x" * 201)
        page.about.get_buffer().set_text("x" * 4001)
        page.memory_enabled.set_active(False)
        assert not Store(folder).settings["memory_enabled"]
        assert Store(folder).settings["user_name"] == "Ada Testname"
        assert Store(folder).settings["user_about"] == "I build test robots."
        assert "not saved" in prefs.result.get_label()
        page.name.set_text("Ada Testname")
        page.about.get_buffer().set_text("I build test robots.")
        assert not page.automatic.get_sensitive()
        assert not page.name.get_sensitive() and not page.about_scroll.get_sensitive()
        prefs.close()
        dialogs.pop()
        window.new_chat()
        window.input.get_buffer().set_text("What do you know about me?")
        window.send_or_stop(None)
        after_reply(disabled_reply)

    def disabled_reply():
        prompt = requests[-1][0]["content"]
        assert all(text not in prompt for text in ("Ada Testname", "I build test robots.", "The user likes jazz."))
        assert store.settings["user_name"] == "Ada Testname" and len(store.memories) == 2
        prefs = Preferences(window)
        dialogs.append(prefs)
        page = prefs.personalization
        prefs.present(window)
        page.memory_enabled.set_active(True)
        page.automatic.set_active(True)
        assert Store(folder).settings["auto_memory_enabled"]
        prefs.close()
        dialogs.pop()
        window.new_chat()
        window.input.get_buffer().set_text("I prefer short replies.")
        window.send_or_stop(None)
        after_reply(automatic_saved)

    def automatic_saved():
        assert not window.busy and window.memory_future is None
        assert len(Store(folder).memories) == 2
        assert store.memories == window.saved_memory_snapshot
        assert "up to date" in window.memory_status
        window.new_chat()
        window.input.get_buffer().set_text("What is my reply preference?")
        window.send_or_stop(None)
        after_reply(cross_chat)

    def cross_chat():
        assert "The user prefers short replies." in requests[-1][0]["content"]
        prefs = Preferences(window)
        dialogs.append(prefs)
        page = prefs.personalization
        prefs.set_visible_page(page)
        prefs.present(window)
        item = store.memories[0]
        dialog = page.edit_memory(item)
        dialog.editor.get_buffer().set_text("The user likes classical music.")
        dialog.emit("response", "save")
        dialog.close()
        assert store.memories[0]["text"] == "The user likes classical music."
        window.request_memory({"id": window.current["id"], "messages": [{"role": "user", "content": "I like waiting"}]})
        later(cancel_inflight, 80)

    def cancel_inflight():
        prefs = dialogs[-1]
        prefs.personalization.automatic.set_active(False)
        assert window.memory_future is None
        assert len(store.memories) == 2
        later(cancelled_result, 950)

    def cancelled_result():
        assert len(store.memories) == 2
        assert all("waiting" not in item["text"] for item in Store(folder).memories)
        prefs = dialogs[-1]
        page = prefs.personalization
        page.name_enabled.set_active(True)
        page.about_enabled.set_active(True)
        window.set_default_size(420, 760)
        later(narrow)

    def narrow():
        snapshot("/tmp/lumen-personalization-narrow.png")
        prefs = dialogs[-1]
        page = prefs.personalization
        ancestor = page.clear_button.get_parent()
        while ancestor and not isinstance(ancestor, Gtk.ScrolledWindow):
            ancestor = ancestor.get_parent()
        assert ancestor
        ancestor.get_vadjustment().set_value(ancestor.get_vadjustment().get_upper())
        later(manager)

    def manager():
        snapshot("/tmp/lumen-personalization-manager.png")
        prefs = dialogs[-1]
        page = prefs.personalization
        page.delete_memory(store.memories[-1]["id"])
        assert len(Store(folder).memories) == 1
        dialog = prefs.reset_defaults()
        dialog.emit("response", "reset")
        dialog.close()
        assert store.settings["user_name"] == "" and len(store.memories) == 1
        assert not page.name_enabled.get_active() and page.automatic.get_active()
        dialog = page.clear_memories()
        dialog.emit("response", "delete")
        dialog.close()
        assert Store(folder).memories == []
        store.save_memory("Temporary memory")
        window.reset_all_data()
        prefs.load_saved_fields()
        assert Store(folder).memories == []
        assert Store(folder).settings["auto_memory_enabled"]
        print("PASS: automatic saving from ordinary conversation by default with Tools off, duplicate checks without file rewrites, cross-chat recall, no-write test, Manage action, personalization visibility/autosave, manual edits/deletes, cancellation protection, resets and wide/narrow layout")
        close()

    def close():
        for dialog in dialogs:
            dialog.close()
        window.close()
        loop.quit()

    def checked(callback):
        try:
            callback()
        except BaseException as exc:
            import traceback
            traceback.print_exc()
            errors.append(exc)
            close()
        return GLib.SOURCE_REMOVE

    def later(callback, delay=450):
        GLib.timeout_add(delay, checked, callback)

    def wait_until(callback, condition):
        deadline = time.monotonic() + 15
        def poll():
            if condition():
                later(callback, 100)
                return GLib.SOURCE_REMOVE
            if time.monotonic() >= deadline:
                def fail():
                    raise AssertionError(f"Timed out waiting for {callback.__name__}")
                checked(fail)
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        GLib.timeout_add(50, poll)

    def after_reply(callback):
        wait_until(callback, lambda: not window.busy and window.memory_future is None and not window.memory_queue)

    later(preferences, 850)
    loop.run()
    if errors:
        raise SystemExit(1)
