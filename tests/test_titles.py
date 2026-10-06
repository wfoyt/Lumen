import copy
import json
import unittest
import httpx

from ollama_gui.backend import Ollama
from ollama_gui.titles import clean_title, needs_title


class TitleTests(unittest.IsolatedAsyncioTestCase):
    async def test_title_uses_a_separate_small_request_without_private_metadata(self):
        messages = [{"role": "user", "content": "Raw attachment secret", "display_content": "Explain this photo", "images": ["private-image"], "attachments": [{"name": "private.png"}]},
                    {"role": "tool", "content": "private tool output"},
                    {"role": "assistant", "content": "A mountain landscape", "thinking": "private reasoning"}]
        original = copy.deepcopy(messages)
        def handle(request):
            body = json.loads(request.content)
            self.assertFalse(body["stream"])
            self.assertFalse(body["think"])
            self.assertNotIn("tools", body)
            self.assertLessEqual(body["options"]["num_predict"], 64)
            self.assertIn("Explain this photo", body["messages"][-1]["content"])
            self.assertNotIn("private", request.content.decode())
            self.assertNotIn("secret", request.content.decode())
            return httpx.Response(200, json={"done": True, "message": {"content": 'Title: **Mountain\nLandscape**'}})
        title = await Ollama("http://localhost", httpx.MockTransport(handle)).title("test", messages)
        self.assertEqual(title, "Mountain Landscape")
        self.assertEqual(messages, original)

    async def test_title_failure_does_not_change_messages(self):
        messages = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}]
        for data in ({"done": False}, {"done": True, "message": {"content": ""}}, {"error": "model missing"}):
            backend = Ollama("http://localhost", httpx.MockTransport(lambda _: httpx.Response(200, json=data)))
            with self.assertRaises(RuntimeError):
                await backend.title("test", messages)
        self.assertEqual(len(messages), 2)

    def test_titles_are_bounded_and_manual_names_are_never_regenerated(self):
        self.assertEqual(clean_title('  "A\nshort title"  '), "A short title")
        self.assertEqual(len(clean_title("x" * 200)), 80)
        chat = {"messages": [{"role": "user", "content": "Question"}]}
        self.assertFalse(needs_title(chat))
        chat["messages"].append({"role": "assistant", "content": "Answer"})
        self.assertTrue(needs_title(chat))
        for source in ("manual", "generated"):
            chat["title_source"] = source
            self.assertFalse(needs_title(chat))
