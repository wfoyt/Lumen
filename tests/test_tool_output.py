import json
import unittest
import httpx

from ollama_gui.tool_output import brave_results, python_result, saved_tool_details, tool_preview, searchable_chat_text
from ollama_gui.backend import Ollama


class PreviewTests(unittest.TestCase):
    def test_search_links_strip_html_and_reject_unsafe_urls(self):
        source = json.dumps({"results": [
            {"title": "<b>Fedora</b> &amp; GNOME", "url": "https://example.com/?a=1&b=2", "description": "A <strong>source</strong>"},
            {"title": "Unsafe", "url": "javascript:alert(1)"},
            {"url": "file:///etc/passwd"},
            {"url": "https://user:secret@example.com"},
        ]})
        self.assertEqual(brave_results(source), [{"title": "Fedora & GNOME", "url": "https://example.com/?a=1&b=2", "description": "A source"}])
        self.assertEqual(brave_results('{"results": []}'), [])
        for text in ('Tool error: API key expired', '{}', '[1]', '{"results": [{"url": "javascript:bad"}]}'):
            self.assertIsNone(brave_results(text))

    def test_older_saved_calls_recover_arguments_in_order(self):
        messages = [{"role": "assistant", "tool_calls": [
            {"function": {"name": "s0_brave_web_search", "arguments": {"query": "Fedora"}}},
            {"function": {"name": "s0_brave_web_search", "arguments": '{"query": "GNOME"}'}},
            {"function": {"name": "s1_execute_python", "arguments": {"code": "print(42)"}}},
        ]}, {"role": "tool", "tool_name": "s0_brave_web_search"},
           {"role": "tool", "tool_name": "s0_brave_web_search"},
           {"role": "tool", "tool_name": "s1_execute_python"},
           {"role": "tool", "tool_name": "s4_execute_python", "tool_arguments": {"code": "print(5)"}, "tool_original_name": "execute_python", "tool_server": "Built-in Python"}]
        details = saved_tool_details(messages)
        self.assertEqual(details[1]["arguments"], {"query": "Fedora"})
        self.assertEqual(details[2]["arguments"], {"query": "GNOME"})
        self.assertEqual(details[3]["arguments"], {"code": "print(42)"})
        self.assertEqual(details[4]["name"], "Built-in Python / execute_python")
        self.assertEqual(details[4]["arguments"], {"code": "print(5)"})
        self.assertEqual(len(messages[0]["tool_calls"]), 3)

    def test_python_output_preserves_results_errors_and_limits(self):
        self.assertEqual(python_result('{"exit_code":0,"stdout":"42\\n","stderr":""}'), ("Completed", "42\n"))
        status, output = python_result(json.dumps({"exit_code": -1, "stdout": "Partial", "stderr": "Traceback", "timed_out": True, "output_limited": True}))
        self.assertIn("timed out", status)
        self.assertIn("truncated", status)
        self.assertEqual(output, "Partial\nErrors:\nTraceback")
        self.assertIsNone(python_result("Tool error: Python unavailable"))

    def test_long_output_is_bounded_and_short_output_unchanged(self):
        source = "\n".join(f"Result {i}" for i in range(20))
        preview, more = tool_preview(source)
        self.assertEqual(preview, "Result 0\nResult 1\nResult 2\nResult 3")
        self.assertTrue(more)
        self.assertEqual(tool_preview("Done"), ("Done", False))
        preview, more = tool_preview("x" * 10000)
        self.assertLessEqual(len(preview), 240)
        self.assertTrue(more)

    def test_search_matches_titles_messages_and_attachment_names(self):
        chat = {"title": "Projects", "messages": [{"role": "user", "content": "Image request", "images": ["hidden-base64-data"], "attachments": [{"name": "Report.csv"}]}, {"role": "assistant", "content": "Fedora and GNOME"}]}
        haystack = searchable_chat_text(chat)
        for term in ("projects", "fedora", "gnome", "report.csv"):
            self.assertIn(term, haystack)
        self.assertNotIn("hidden-base64-data", haystack)


class FullOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_output_retained_but_model_context_is_bounded(self):
        source = "Result\n" * 12000
        class Hub:
            tools = [{"type": "function", "function": {"name": "search"}}]
            def __init__(self, *_): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def call(self, *_): return source
        requests = []
        def handle(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if len(requests) == 1:
                message = {"tool_calls": [{"function": {"name": "search", "arguments": {}}}]}
            else:
                tool = payload["messages"][-1]
                self.assertEqual(len(tool["content"]), 60000)
                self.assertNotIn("display_content", tool)
                self.assertNotIn("tool_arguments", tool)
                message = {"content": "Done"}
            return httpx.Response(200, content=json.dumps({"message": message, "done": True}))
        result = await Ollama("http://localhost", httpx.MockTransport(handle)).chat("test", [], {}, lambda *_: None, hub_factory=Hub)
        self.assertEqual(result[1]["display_content"], source)
        self.assertEqual(result[1]["tool_arguments"], {})
