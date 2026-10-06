import asyncio
import json
import os
from pathlib import Path
import sys
import socket
import tempfile
import unittest

import httpx

from ollama_gui.backend import Ollama, ToolHub
from ollama_gui.storage import DEFAULT_SETTINGS, Store, validate_servers, validate_url

SERVERS = {"search": {"command": sys.executable, "args": [str(Path(__file__).with_name("fixture_mcp.py"))]}}


def response(parts):
    return httpx.Response(200, content="\n".join(json.dumps(x) for x in parts))


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_individual_tool_defaults_and_disabled_dispatch(self):
        async with ToolHub(SERVERS) as hub:
            self.assertEqual(hub.catalog[0]["name"], "search")
            self.assertTrue(hub.catalog[0]["enabled"])
            alias = hub.tools[0]["function"]["name"]
        cfg = {"search": {**SERVERS["search"], "disabled_tools": ["search"]}}
        async with ToolHub(cfg) as hub:
            self.assertFalse(hub.catalog[0]["enabled"])
            self.assertEqual(hub.tools, [])
            with self.assertRaises(ValueError):
                await hub.call(alias, {"query": "must not run"})

    async def test_thinking_and_reasoning_events_are_separate_from_answer(self):
        events = []
        backend = Ollama("http://localhost", httpx.MockTransport(lambda _: response([
            {"message": {"thinking": "Internal reasoning"}, "done": False},
            {"message": {"content": "The answer"}, "done": True},
        ])))
        result = await backend.chat("test", [], {}, lambda *event: events.append(event))
        self.assertLess(next(i for i, e in enumerate(events) if e[0] == "thinking"), next(i for i, e in enumerate(events) if e[0] == "token"))
        self.assertEqual([e[1] for e in events if e[0] == "token"], ["The answer"])
        self.assertEqual([e[1] for e in events if e[0] == "reasoning"], ["Internal reasoning"])
        self.assertEqual(result[0]["thinking"], "Internal reasoning")
        self.assertEqual(result[0]["content"], "The answer")

    async def test_streamable_http_discovery_and_call(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name("fixture_mcp.py")), str(port), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        url = f"http://127.0.0.1:{port}/mcp"
        try:
            async with asyncio.timeout(15):
                async with httpx.AsyncClient(trust_env=False) as client:
                    while True:
                        try:
                            await client.get(url)
                            break
                        except httpx.ConnectError:
                            if process.returncode is not None:
                                self.fail("MCP HTTP fixture exited before startup")
                            await asyncio.sleep(0.1)
                async with ToolHub({"http": {"url": url}}) as hub:
                    self.assertEqual(len(hub.tools), 1)
                    result = await hub.call(hub.tools[0]["function"]["name"], {"query": "HTTP"})
                    self.assertIn("Result for HTTP", result)
        finally:
            if process.returncode is None:
                process.terminate()
            await process.wait()

    async def test_real_mcp_discovery_and_call(self):
        async with ToolHub(SERVERS) as hub:
            self.assertEqual(len(hub.tools), 1)
            result = await hub.call(hub.tools[0]["function"]["name"], {"query": "GNOME"})
            self.assertIn("Result for GNOME", result)
            with self.assertRaises(ValueError):
                await hub.call("missing", {})

    async def test_streaming_mcp_roundtrip(self):
        requests, events = [], []
        def handle(request):
            data = json.loads(request.content)
            requests.append(data)
            if len(requests) == 1:
                alias = data["tools"][0]["function"]["name"]
                return response([{"message": {"role": "assistant", "tool_calls": [{"function": {"name": alias, "arguments": {"query": "Fedora"}}}]}, "done": True}])
            self.assertEqual(data["messages"][-1]["role"], "tool")
            self.assertIn("Result for Fedora", data["messages"][-1]["content"])
            for key in ("tool_arguments", "tool_server", "tool_original_name", "display_content"):
                self.assertNotIn(key, data["messages"][-1])
            return response([{"message": {"content": "Hello "}, "done": False}, {"message": {"content": "Fedora"}, "done": True}])
        history = [{"role": "user", "content": "Search Fedora"}]
        result = await Ollama("http://localhost", httpx.MockTransport(handle)).chat("test", history, SERVERS, lambda *event: events.append(event))
        self.assertEqual(len(result), 3)
        self.assertEqual(result[-1]["content"], "Hello Fedora")
        self.assertEqual(result[1]["tool_arguments"], {"query": "Fedora"})
        self.assertEqual(result[1]["tool_original_name"], "search")
        self.assertEqual(result[1]["tool_server"], "search")
        self.assertEqual(len(history), 1)
        self.assertEqual([e[1] for e in events if e[0] == "token"], ["Hello ", "Fedora"])

    async def test_broken_stream_and_error(self):
        for parts in ([{"message": {"content": "partial"}}], [{"error": "model lacks tools"}]):
            backend = Ollama("http://localhost", httpx.MockTransport(lambda _: response(parts)))
            with self.assertRaises(RuntimeError):
                await backend.chat("test", [], {}, lambda *_: None)

    async def test_cancellation_keeps_history(self):
        waiting = asyncio.Event()
        async def handle(_):
            waiting.set()
            await asyncio.Event().wait()
        history = [{"role": "user", "content": "Hi"}]
        task = asyncio.create_task(Ollama("http://localhost", httpx.MockTransport(handle)).chat("test", history, {}, lambda *_: None))
        await waiting.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(history, [{"role": "user", "content": "Hi"}])

    async def test_tool_round_limit(self):
        class Hub:
            tools = [{"type": "function", "function": {"name": "loop"}}]
            def __init__(self, *_): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def call(self, *_): return "again"
        backend = Ollama("http://localhost", httpx.MockTransport(lambda _: response([{"message": {"tool_calls": [{"function": {"name": "loop", "arguments": {}}}]}, "done": True}])))
        with self.assertRaisesRegex(RuntimeError, "12 tool rounds"):
            await backend.chat("test", [], {}, lambda *_: None, hub_factory=Hub)


class StorageTests(unittest.TestCase):
    def test_default_settings_are_independent(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            store = Store(first)
            store.settings["mcpServers"]["test"] = {"command": "unused"}
            self.assertEqual(Store(second).settings, DEFAULT_SETTINGS)
            self.assertEqual(DEFAULT_SETTINGS["mcpServers"], {})

    def test_private_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.chats.append({"title": "Hello", "messages": []})
            store.save()
            self.assertEqual(Store(root).chats[0]["title"], "Hello")
            self.assertEqual(os.stat(Path(root) / "settings.json").st_mode & 0o777, 0o600)

    def test_config_validation(self):
        self.assertEqual(validate_url("http://localhost:11434/"), "http://localhost:11434")
        for value in ("file:///tmp", "http://user:pass@example.com", "garbage"):
            with self.assertRaises(ValueError): validate_url(value)
        for value in ([], {"test": {"args": "oops"}}, {"test": {"command": "python", "env": {"KEY": 4}}}, {"test": {"command": "python", "disabled_tools": "search"}}):
            with self.assertRaises(ValueError): validate_servers(value)

    def test_reset_all_removes_settings_and_history(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings["mcpServers"] = {"server": {"command": "unused", "env": {"KEY": "secret-key"}}}
            store.chats = [{"id": "private", "messages": [{"role": "user", "content": "Private message"}]}]
            store.save()
            store.reset_all()
            reopened = Store(root)
            self.assertEqual(reopened.settings, DEFAULT_SETTINGS)
            self.assertEqual(reopened.chats, [])
            self.assertNotIn("secret-key", (Path(root) / "settings.json").read_text())


if __name__ == "__main__":
    unittest.main()
