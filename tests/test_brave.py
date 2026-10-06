import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from ollama_gui.brave import search
from ollama_gui.backend import ToolHub, test_brave_tool
from ollama_gui.storage import brave_enabled, configure_brave, tool_servers, Store


class BraveSettingsTests(unittest.TestCase):
    def test_brave_enable_switch_preserves_key_and_excludes_disabled_server(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            self.assertFalse(brave_enabled(store.settings))
            store.settings.update(mcpServers=configure_brave({}, "test-only-key"), brave_enabled=True)
            self.assertIn("brave-search", tool_servers(store.settings))
            store.settings["brave_enabled"] = False
            store.save()
            saved = Store(root).settings
            self.assertNotIn("brave-search", tool_servers(saved))
            self.assertEqual(saved["mcpServers"]["brave-search"]["env"]["BRAVE_API_KEY"], "test-only-key")
            legacy = {"mcpServers": saved["mcpServers"]}
            self.assertTrue(brave_enabled(legacy))
            legacy["mcpServers"]["brave-search"]["enabled"] = False
            self.assertFalse(brave_enabled(legacy))
    def test_save_key_creates_server_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings["mcpServers"] = configure_brave({}, "test-only-key", "")
            store.save()
            cfg = Store(root).settings["mcpServers"]["brave-search"]
            self.assertEqual(cfg["env"]["BRAVE_API_KEY"], "test-only-key")
            self.assertEqual(cfg["args"], ["-m", "ollama_gui.brave"])

    def test_update_and_clear_key_preserve_custom_settings(self):
        servers = {"brave-search": {"command": "custom-server", "args": ["--custom"], "disabled_tools": ["brave_news_search"], "env": {"BRAVE_API_KEY": "old-test-key", "EXTRA": "kept"}}}
        original = copy.deepcopy(servers)
        updated = configure_brave(servers, "replacement-test-key", "old-test-key")
        self.assertEqual(servers, original)
        self.assertEqual(updated["brave-search"]["command"], "custom-server")
        self.assertEqual(updated["brave-search"]["disabled_tools"], ["brave_news_search"])
        self.assertEqual(updated["brave-search"]["env"]["EXTRA"], "kept")
        cleared = configure_brave(updated, "", "replacement-test-key")
        self.assertNotIn("BRAVE_API_KEY", cleared["brave-search"]["env"])

    def test_unchanged_key_respects_json_editor_and_upgrades_stock_setup(self):
        servers = {"brave-search": {"command": "custom-server", "env": {"BRAVE_API_KEY": "edited-in-json"}}}
        self.assertEqual(configure_brave(servers, "original-row-value", "original-row-value"), servers)
        stock = {"brave-search": {"command": "npx", "args": ["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"], "env": {"BRAVE_API_KEY": "test-only-key"}}}
        self.assertEqual(configure_brave(stock, "test-only-key", "test-only-key")["brave-search"]["command"], sys.executable)


class BraveTests(unittest.IsolatedAsyncioTestCase):
    async def test_brave_test_calls_only_brave_even_with_disabled_tools(self):
        servers = {"unrelated": {"command": "must-not-launch"}, "brave-search": {"command": sys.executable, "args": [str(Path(__file__).with_name("fixture_brave.py"))], "env": {"BRAVE_API_KEY": "test-only-key"}, "enabled": False, "disabled_tools": ["brave_web_search"]}}
        original = copy.deepcopy(servers)
        result = await test_brave_tool(servers)
        self.assertIn("working", result)
        self.assertEqual(servers, original)

    async def test_brave_test_reports_missing_key_and_tool_errors(self):
        with self.assertRaisesRegex(ValueError, "API key"):
            await test_brave_tool({})
        class Hub:
            routes = {"alias": (None, "brave_web_search", "brave-search")}
            def __init__(self, *_): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def call(self, *_): return "Tool error: Invalid API key"
        with self.assertRaisesRegex(RuntimeError, "Invalid API key"):
            await test_brave_tool({"brave-search": {"command": "unused"}}, Hub)

    async def test_auth_query_and_results(self):
        def handle(request):
            self.assertEqual(request.headers["X-Subscription-Token"], "test-only-key")
            self.assertEqual(request.url.params["freshness"], "pw")
            self.assertEqual(request.url.params["q"], "GNOME")
            return httpx.Response(200, json={"web": {"results": [{"title": "GNOME", "url": "https://example.com", "description": "Result"}]}})
        with patch.dict(os.environ, {"BRAVE_API_KEY": "test-only-key"}, clear=True):
            result = await search("web", "GNOME", 5, "pw", httpx.MockTransport(handle))
            self.assertEqual(result["results"][0]["url"], "https://example.com")

    async def test_api_failure_is_actionable_without_leaking_key(self):
        with patch.dict(os.environ, {"BRAVE_API_KEY": "test-only-key"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "API key") as error:
                await search("web", "GNOME", transport=httpx.MockTransport(lambda _: httpx.Response(401)))
            self.assertNotIn("test-only-key", str(error.exception))

    async def test_bundled_mcp_web_and_news_roundtrip(self):
        servers = {"brave": {"command": sys.executable, "args": [str(Path(__file__).with_name("fixture_brave.py"))], "env": {"BRAVE_API_KEY": "test-only-key"}}}
        async with ToolHub(servers) as hub:
            self.assertEqual({tool["name"] for tool in hub.catalog}, {"brave_web_search", "brave_news_search"})
            for tool in hub.tools:
                result = await hub.call(tool["function"]["name"], {"query": "GNOME"})
                self.assertIn("https://example.com/brave", result)
