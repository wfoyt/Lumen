import json
import unittest
import httpx
from ollama_gui.backend import Ollama
from ollama_gui.markdown import inline_markup, parse_markdown


class SearchFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_results_are_raw_without_citation_instructions_or_metadata(self):
        alias = "s0_brave_web_search"
        raw = json.dumps({"results": [{"title": "Source", "url": "https://example.com"}]})
        class Hub:
            tools = [{"type": "function", "function": {"name": alias}}]
            routes = {alias: (None, "brave_web_search", "brave-search")}
            def __init__(self, *_): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def call(self, *_): return raw
        requests, events = [], []
        def handle(request):
            payload = json.loads(request.content)
            requests.append(payload)
            old = payload["messages"][0]
            self.assertEqual(old["content"], raw)
            self.assertNotIn("tool_citations", old)
            if len(requests) == 1:
                message = {"tool_calls": [{"function": {"name": alias, "arguments": {"query": "Source"}}}]}
            else:
                self.assertEqual(payload["messages"][-1]["content"], raw)
                message = {"content": "An answer."}
            return httpx.Response(200, content=json.dumps({"message": message, "done": True}))
        history = [{"role": "tool", "content": raw + "\nSource references for this response: cite [1]", "display_content": raw, "tool_citations": [{"number": 1}]}]
        result = await Ollama("http://localhost", httpx.MockTransport(handle)).chat("test", history, {}, lambda *event: events.append(event), hub_factory=Hub)
        self.assertEqual(result[1]["content"], raw)
        self.assertFalse(any("citation_sources" in message or "tool_citations" in message for message in result))
        self.assertNotIn("sources", [kind for kind, _ in events])

    async def test_old_numbered_markers_stay_literal_and_normal_links_still_work(self):
        markup = inline_markup(parse_markdown("A result [1]. [Source](https://example.com).").children[0])
        self.assertIn("[1]", markup)
        self.assertNotIn(">[1]</a>", markup)
        self.assertIn('href="https://example.com"', markup)
