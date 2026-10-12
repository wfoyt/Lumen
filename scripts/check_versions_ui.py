"""Native version, autosave and attachment checks with no model/network calls."""
import asyncio
import copy
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from ollama_gui.app import Application, Window, Preferences, Gio, Gtk, GLib, buffer_text, Ollama
from ollama_gui.storage import Store
from ollama_gui.attachments import image_attachment, load_attachment, user_message
from ollama_gui.attachment_view import PreviewButton, PdfPage, file_dialog, stored_file
from ollama_gui import history

requests = []
async def reply(self, model, messages, servers, emit):
    requests.append((model, copy.deepcopy(messages), copy.deepcopy(servers)))
    await asyncio.sleep(.03)
    if model == 'fail':
        raise RuntimeError('Simulated model failure')
    emit('token', f'Reply from {model}')
    return [{'role': 'assistant', 'content': f'Reply from {model}'}]


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


with tempfile.TemporaryDirectory() as folder, patch.object(Window, 'refresh_models'), patch.object(Window, 'refresh_tools'), patch.object(Window, 'request_title'), patch.object(Application, 'notify_completion'), patch.object(Ollama, 'chat', reply):
    app = Application(); app.set_flags(Gio.ApplicationFlags.NON_UNIQUE); app.register(None)
    store = Store(folder)
    file = {'name': 'notes.py', 'kind': 'file', 'content': 'print(42)\n'}
    store.chats = [{'id': 'versions', 'title': 'Saved Versions', 'messages': [
        user_message('Original question', [file]), {'role': 'assistant', 'content': 'Original reply', 'model': 'one'},
        {'role': 'user', 'content': 'Follow-up'}, {'role': 'assistant', 'content': 'Follow-up reply', 'model': 'one'},
    ]}]
    original = copy.deepcopy(store.chats[0]['messages'])
    window = Window(app, store); window.model_names = ['one', 'two', 'fail']; store.settings['model'] = 'one'
    window.present(); loop = GLib.MainLoop(); errors = []; dialogs = []
    window.paintable = Gtk.WidgetPaintable.new(window)

    def snap(path):
        snapshot = Gtk.Snapshot(); window.paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node(); assert node
        window.get_renderer().render_texture(node, None).save_to_png(path)

    def preferences():
        prefs = Preferences(window); prefs.present(window); dialogs.append(prefs)
        assert not any(isinstance(widget, Gtk.Button) and widget.get_label() == 'Save Preferences' for widget in descendants(prefs))
        prefs.tools_enabled.set_active(False)
        assert not Store(folder).settings['tools_enabled'] and not window.tools_button.get_visible()
        assert window.servers_for_chat() == {}
        prefs.python_enabled.set_active(False)
        prefs.tools_enabled.set_active(True)
        assert Store(folder).settings['tools_enabled'] and window.tools_button.get_visible()
        assert not Store(folder).settings['python_enabled']
        prefs.url.set_text('not a URL')
        prefs.show_thinking.set_active(True)
        assert Store(folder).settings['show_thinking']
        assert Store(folder).settings['url'] == 'http://localhost:11434'
        assert prefs.result.get_label()
        prefs.url.set_text('http://localhost:11434')
        prefs.custom_system.set_active(True)
        prefs.system.get_buffer().set_text('Custom instructions saved automatically.')
        later(auto_text)

    def auto_text():
        assert Store(folder).settings['system'] == 'Custom instructions saved automatically.'
        prefs = dialogs.pop(); prefs.key.set_text('test-only-key'); prefs.brave_enabled.set_active(True)
        assert Store(folder).settings['mcpServers']['brave-search']['env']['BRAVE_API_KEY'] == 'test-only-key'
        prefs.close()
        window.input.get_buffer().set_text('Unsent composer draft')
        dialog = window.revision_dialog(0)
        assert dialog.model_picker.get_selected_item().get_string() == 'one'
        dialog.model_picker.set_selected(1); dialog.emit('response', 'send'); dialog.close()
        later(regenerated)

    def regenerated():
        assert not window.busy and requests[-1][0] == 'two'
        assert len(requests[-1][1]) == 2 and requests[-1][1][-1]['content'] == original[0]['content']
        assert window.current['messages'][-1]['content'] == 'Reply from two'
        assert window.current['messages'][-1]['model'] == 'two'
        assert window.current['branches'][0]['messages'] == original
        assert buffer_text(window.input) == 'Unsent composer draft'
        assert history.choices(window.current, 0) == [0, 1]
        assert any(isinstance(widget, Gtk.Label) and widget.get_text() == '2/2' for widget in descendants(window.messages))
        window.select_version(0); assert window.current['messages'] == original
        dialog = window.revision_dialog(0, edit=True)
        dialog.editor.get_buffer().set_text('Edited question'); dialog.emit('response', 'send'); dialog.close()
        later(edited)

    def edited():
        assert requests[-1][0] == 'one'
        assert 'print(42)' in requests[-1][1][-1]['content']
        assert window.current['messages'][0]['display_content'] == 'Edited question'
        assert window.current['branches'][0]['messages'] == original
        assert history.choices(window.current, 0) == [0, 1, 2]
        saved = Store(folder).chats[0]
        assert len(saved['branches']) == 3 and saved['branch_index'] == 2
        snap('/tmp/lumen-edited-version.png')
        dialog = window.revision_dialog(0); dialog.model_picker.set_selected(2); dialog.emit('response', 'send'); dialog.close()
        later(failed)

    def failed():
        assert not window.busy and window.current['branch_index'] == 2
        assert history.choices(window.current, 0) == [0, 1, 2]
        assert window.current['messages'][0]['display_content'] == 'Edited question'
        assert buffer_text(window.input) == 'Unsent composer draft'
        # A saved old file can still be viewed using the retained model payload.
        legacy = {'name': 'notes.py', 'kind': 'file'}
        recovered = stored_file(legacy, original[0]); assert recovered['content'] == 'print(42)\n'
        image = BytesIO(); Image.new('RGB', (400, 300), 'royalblue').save(image, 'PNG')
        window.attachments = [image_attachment(image.getvalue()), file]
        window.render_attachments()
        buttons = [widget for widget in descendants(window.attachment_chips) if isinstance(widget, PreviewButton)]
        assert len(buttons) == 2
        assert all(button.get_cursor().get_name() == 'pointer' for button in buttons)
        buttons[0].animate(1.04)
        window.hover_button = buttons[0]
        dialog = file_dialog(file, window); dialogs.append(dialog)
        assert any(hasattr(widget, 'get_buffer') and widget.get_buffer().get_char_count() >= 10 for widget in descendants(dialog))
        later(file_preview)

    def file_preview():
        assert window.hover_button.zoom > 1.03
        snap('/tmp/lumen-file-preview.png'); dialogs.pop().close()
        writer = PdfWriter()
        for i in range(2):
            page = writer.add_blank_page(width=300, height=300)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject(); stream.set_data(f'BT /F1 12 Tf 20 200 Td (Page {i+1} preview) Tj ET'.encode())
            page[NameObject('/Contents')] = writer._add_object(stream)
        path = Path(folder) / 'test.pdf'; writer.write(path)
        attachment = load_attachment(path, 'file')
        sent = user_message('Read this PDF', [attachment])
        dialog = file_dialog(sent['attachments'][0], window); dialogs.append(dialog)
        assert any(isinstance(widget, PdfPage) for widget in descendants(dialog))
        later(pdf)

    def pdf():
        snap('/tmp/lumen-pdf-preview.png')
        next_page = next(widget for widget in descendants(dialogs[-1]) if isinstance(widget, Gtk.Button) and widget.get_tooltip_text() == 'Next Page')
        next_page.emit('clicked')
        assert any(isinstance(widget, Gtk.Label) and widget.get_text() == '2 / 2' for widget in descendants(dialogs[-1]))
        dialogs.pop().close()
        window.select_version(0)
        assert window.current['messages'] == original
        window.set_default_size(360, 760); window.split.set_show_sidebar(False)
        later(narrow)

    def narrow():
        assert window.get_width() >= 360
        snap('/tmp/lumen-versions-narrow.png')
        print('PASS: automatic saves, invalid text preserves valid fields, hidden Tools button, editing/regeneration with model selection, saved history cycling, failure recovery and separate drafts, clickable hover previews, old files and native PDF pages')
        close()

    def close():
        for dialog in dialogs:
            dialog.close()
        window.close(); loop.quit()

    def checked(callback):
        try:
            callback()
        except BaseException as error:
            import traceback; traceback.print_exc(); errors.append(error); close()
        return GLib.SOURCE_REMOVE
    def later(callback): GLib.timeout_add(650, checked, callback)
    GLib.timeout_add(1000, checked, preferences); loop.run()
    if errors: raise SystemExit(1)
