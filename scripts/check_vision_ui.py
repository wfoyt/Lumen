"""Verify image admission and model-switch races with isolated native data."""
import asyncio
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from ollama_gui.app import Application, Window, Gio, Gdk, GLib, Gtk, Ollama
from ollama_gui.storage import Store
from ollama_gui.attachments import image_attachment, user_message
from ollama_gui.image_view import texture

queries = []
async def capabilities(self, model):
    queries.append((self.url, model))
    await asyncio.sleep(.25 if model == 'slow' else .03)
    if model == 'unavailable': raise RuntimeError('Simulated discovery failure')
    return {'completion', 'vision'} if model in ('eyes', 'slow') else {'completion'}

class ImageClipboard:
    reads = 0
    delayed = False
    def get_formats(self): return Gdk.ContentFormats.new(['image/png'])
    def read_texture_async(self, _, callback):
        self.reads += 1
        if self.delayed: self.callback = callback
        else: GLib.idle_add(callback, self, None)
    def read_texture_finish(self, result): return self.paintable

class TextClipboard:
    def get_formats(self): return Gdk.ContentFormats.new(['text/plain'])

class Chooser:
    instances = []
    def __init__(self, **kwargs): self.instances.append(self)
    def set_filters(self, filters): pass
    def open_multiple(self, window, cancellable, callback): self.callback = callback
    def open_multiple_finish(self, result):
        files = Gio.ListStore.new(Gio.File); files.append(Gio.File.new_for_path(self.path)); return files
    def finish(self): self.callback(self, None)

with tempfile.TemporaryDirectory() as folder, patch.object(Window, 'refresh_models'), patch.object(Window, 'refresh_tools'), patch.object(Window, 'request_title'), patch.object(Ollama, 'model_capabilities', capabilities), patch('ollama_gui.app.Gtk.FileDialog', Chooser):
    app = Application(); app.set_flags(Gio.ApplicationFlags.NON_UNIQUE); app.register(None)
    store = Store(folder); store.settings['setup_completed'] = True
    window = Window(app, store); window.present(); loop = GLib.MainLoop(); errors = []
    window.model_names = ['plain', 'eyes', 'slow', 'unavailable']
    window.store.settings['model'] = 'plain'; window.models.set_model(Gtk.StringList.new(window.model_names))
    messages = []; window.notify = messages.append
    png = BytesIO(); Image.new('RGB', (100, 80), 'green').save(png, 'PNG')
    attachment = image_attachment(png.getvalue()); clipboard = ImageClipboard(); clipboard.paintable = texture(attachment['content'])
    path = Path(folder) / 'image.png'; path.write_bytes(png.getvalue())
    text_path = Path(folder) / 'notes.txt'; text_path.write_text('Plain text attachment')

    def initial():
        assert not window.images_button.get_sensitive()
        assert window.paste_image(clipboard) and clipboard.reads == 0
        assert not window.paste_image(TextClipboard())
        window.choose_attachments('image'); assert not Chooser.instances
        later(plain)

    def plain():
        assert not window.supports_images() and not window.images_button.get_sensitive()
        assert 'does not support' in window.images_button.get_tooltip_text()
        window.paste_image(clipboard); assert clipboard.reads == 0
        window.models.set_selected(1); assert not window.images_button.get_sensitive()
        later(vision)

    def vision():
        assert window.supports_images() and window.images_button.get_sensitive()
        window.paste_image(clipboard); assert clipboard.reads == 1
        later(pasted)

    def pasted():
        assert len(window.attachments) == 1 and window.attachments[0]['kind'] == 'image'
        window.models.set_selected(0)
        window.input.get_buffer().set_text('Analyze this')
        before = list(window.current['messages']); window.send_or_stop(None)
        assert window.current['messages'] == before and window.future is None
        assert len(window.attachments) == 1
        window.attachments = []; window.render_attachments()
        window.models.set_selected(1); window.choose_attachments('image')
        chooser = Chooser.instances[-1]; chooser.path = str(path)
        window.models.set_selected(0); chooser.finish()
        assert not window.draft_loading and not window.attachments
        window.choose_attachments('file'); chooser = Chooser.instances[-1]; chooser.path = str(text_path); chooser.finish()
        later(file_loaded)

    def file_loaded():
        assert len(window.attachments) == 1 and window.attachments[0]['kind'] == 'file'
        window.attachments = []; window.render_attachments()
        window.models.set_selected(1); window.choose_attachments('image'); chooser = Chooser.instances[-1]; chooser.path = str(path); chooser.finish()
        later(uploaded)

    def uploaded():
        assert len(window.attachments) == 1 and window.attachments[0]['kind'] == 'image'
        window.attachments = []; window.render_attachments()
        clipboard.delayed = True; window.paste_image(clipboard)
        window.models.set_selected(0); clipboard.callback(clipboard, None)
        later(paste_race)

    def paste_race():
        assert not window.attachments and not window.draft_loading
        window.current['messages'] = [user_message('An image question', [attachment]), {'role': 'assistant', 'content': 'Previous reply', 'model': 'eyes'}]
        window.render_chat(); before = list(window.current['messages']); window.send_or_stop(None)
        assert window.current['messages'] == before and window.future is None
        dialog = window.revision_dialog(0); dialog.model_picker.set_selected(0)
        assert not dialog.get_response_enabled('send')
        dialog.emit('response', 'send'); assert 'branches' not in window.current
        dialog.model_picker.set_selected(1); assert dialog.get_response_enabled('send'); dialog.close()
        window.models.set_selected(2); window.models.set_selected(0)
        later(stale)

    def stale():
        assert not window.images_button.get_sensitive() and window.supports_images('slow')
        window.models.set_selected(3)
        later(failed)

    def failed():
        assert not window.images_button.get_sensitive()
        assert 'Could not verify' in window.images_button.get_tooltip_text()
        window.paste_image(clipboard); assert clipboard.reads == 2
        assert queries.count(('http://localhost:11434', 'eyes')) == 1
        window.store.settings['url'] = 'http://other-server:11434'; window.update_image_controls()
        window.store.settings['model'] = 'eyes'; assert not window.supports_images()
        window.clear_capabilities(); assert not window.capability_cache
        print('PASS: capability-based gating, pending/error states, normal text paste and files, image upload/paste, chooser and clipboard model-switch races, send/history/regeneration protection, cache isolation and stale results')
        close()

    def close(): window.close(); loop.quit()
    def checked(callback):
        try: callback()
        except BaseException as error:
            import traceback; traceback.print_exc(); errors.append(error); close()
        return GLib.SOURCE_REMOVE
    def later(callback):
        deadline = time.monotonic() + 15
        def ready():
            if not window.draft_loading and not window.capability_jobs:
                return checked(callback)
            if time.monotonic() >= deadline:
                def fail():
                    raise AssertionError(f"Timed out waiting for {callback.__name__}")
                return checked(fail)
            return GLib.SOURCE_CONTINUE
        GLib.timeout_add(100, ready)
    GLib.timeout_add(10, checked, initial); loop.run()
    if errors: raise SystemExit(1)
