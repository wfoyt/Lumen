#!/usr/bin/env python3
"""Exercise the installed bundle, including its Python sandbox and native UI.

Run with any host Python 3: python3 scripts/check_flatpak.py [--user | --system]
The checks run in the installed Flatpak using temporary application data.
"""
import asyncio
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


if not Path("/.flatpak-info").exists():
    parser = argparse.ArgumentParser(description=__doc__)
    installation = parser.add_mutually_exclusive_group()
    installation.add_argument("--user", action="store_const", const="--user", dest="installation")
    installation.add_argument("--system", action="store_const", const="--system", dest="installation")
    arguments = parser.parse_args()
    command = ["flatpak", "run"]
    if arguments.installation:
        command.append(arguments.installation)
    raise SystemExit(subprocess.run(
        command + ["--command=python3", "io.github.ollamagnome.Lumen", "-"],
        input=Path(__file__).read_text(), text=True,
    ).returncode)

import gi

for namespace, version in (("Gtk", "4.0"), ("Adw", "1"), ("GtkSource", "5"), ("Poppler", "0.18")):
    gi.require_version(namespace, version)
from gi.repository import Adw, Gio, GLib, Gtk, GtkSource, Poppler
import cairo
import httpx
from ollama_gui.backend import Ollama, ToolHub
from ollama_gui.math_render import equation_png
from ollama_gui.python_tool import execute_python, MAX_OUTPUT_BYTES
from ollama_gui.storage import DEFAULT_SETTINGS, tool_servers


async def check_tools(secret):
    result = await execute_python("import math\nprint(math.sqrt(81))")
    assert result["exit_code"] == 0, result
    assert result["stdout"] == "9.0\n", result
    listener = await asyncio.start_server(lambda *_: None, "127.0.0.1", 0)
    try:
        port = listener.sockets[0].getsockname()[1]
        code = f"""import os, socket
assert not os.path.exists({str(secret)!r}), 'App data exposed'
assert 'LUMEN_TEST_SECRET' not in os.environ, 'Parent environment exposed'
assert not any('site-packages' in path for path in __import__('sys').path)
try:
    socket.create_connection(('127.0.0.1', {port}), timeout=0.2)
except OSError:
    print('isolated')
else:
    raise RuntimeError('Network exposed')
"""
        result = await execute_python(code)
        assert result["exit_code"] == 0 and result["stdout"] == "isolated\n", result
    finally:
        listener.close()
        await listener.wait_closed()
    result = await execute_python("while True: pass", timeout_seconds=1)
    assert result["timed_out"], result
    result = await execute_python("print('x' * 1000000)")
    assert result["output_limited"], result
    assert len(result["stdout"].encode()) + len(result["stderr"].encode()) <= MAX_OUTPUT_BYTES
    async with ToolHub(tool_servers(DEFAULT_SETTINGS)) as hub:
        result = json.loads(await hub.call(hub.tools[0]["function"]["name"], {"code": "print(6 * 7)"}))
        assert result["stdout"] == "42\n", result
    # Exercise the packaged MCP subprocess, answer recovery and title generation
    # together. Model responses are deterministic and need no Ollama/API key.
    requests = []
    def model_response(request):
        data = json.loads(request.content)
        requests.append(data)
        if not data.get("stream"):
            assert "The answer is 42" in data["messages"][-1]["content"]
            return httpx.Response(200, json={"done": True, "message": {"content": "Python Calculation"}})
        if len(requests) == 1:
            alias = data["tools"][0]["function"]["name"]
            message = {"tool_calls": [{"function": {"name": alias, "arguments": {"code": "print(6 * 7)"}}}]}
        elif len(requests) == 2:
            assert json.loads(data["messages"][-1]["content"])["stdout"] == "42\n"
            message = {"thinking": "Reasoning without an answer", "content": ""}
        else:
            assert data["think"] is False and "tools" not in data
            assert data["messages"][-1]["role"] == "tool"
            message = {"content": "The answer is 42"}
        return httpx.Response(200, text=json.dumps({"message": message, "done": True}))
    backend = Ollama("http://test", httpx.MockTransport(model_response))
    history = [{"role": "user", "content": "Calculate 6 * 7 with Python"}]
    result = await backend.chat("test", history, tool_servers(DEFAULT_SETTINGS), lambda *_: None)
    assert result[-1]["content"] == "The answer is 42", result
    assert len(result) == 3 and len(requests) == 3
    assert await backend.title("test", history + result) == "Python Calculation"


data_home = Path(os.environ["XDG_DATA_HOME"])
data_home.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="flatpak-check-", dir=data_home) as directory:
    root = Path(directory)
    secret = root / "private.txt"
    secret.write_text("test-only private data")
    os.environ["LUMEN_TEST_SECRET"] = "test-only environment value"
    os.environ["XDG_DATA_HOME"] = str(root)
    asyncio.run(check_tools(secret))
    assert equation_png(r"\frac{1}{2}", display=True), "Equation rendering failed"
    from pypdf import PdfWriter
    pdf = root / "preview.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as stream:
        writer.write(stream)
    document = Poppler.Document.new_from_file(pdf.as_uri(), None)
    assert document.get_n_pages() == 1
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 100, 100)
    document.get_page(0).render(cairo.Context(surface))
    from ollama_gui.app import Application
    from ollama_gui import __version__
    application = Application()
    application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    ui_ready = []
    about_ready = []
    def open_about():
        window = application.get_active_window()
        menu = window.app_menu.get_menu_model()
        labels = [menu.get_item_attribute_value(i, "label", None).get_string() for i in range(menu.get_n_items())]
        window.activate_action("win.about", None)
        dialog = window.get_visible_dialog()
        about_ready.append(
            "About Lumen" in labels and isinstance(dialog, Adw.AboutDialog)
            and dialog.get_application_name() == "Lumen"
            and dialog.get_version() == __version__
            and dialog.get_developer_name() == "Lumen Team"
            and dialog.get_developers() == ["Lumen Team"]
        )
        return GLib.SOURCE_REMOVE
    def close_window():
        window = application.get_active_window()
        ui_ready.append(window is not None and window.get_visible())
        if window is not None:
            window.close()
        application.quit()
        return GLib.SOURCE_REMOVE
    GLib.timeout_add(500, open_about)
    GLib.timeout_add(1500, close_window)
    assert application.run(["lumen"]) == 0
    assert ui_ready == [True], "Window did not open"
    assert about_ready == [True], "About Lumen menu/dialog failed"
print("Flatpak checks passed: imports, equations, PDF rendering, MCP, answer recovery, titles, Python isolation/limits, UI and About Lumen.")
