import copy
import tempfile
import unittest
from ollama_gui import history
from ollama_gui.storage import Store
from ollama_gui.attachments import user_message


class HistoryTests(unittest.TestCase):
    def chat(self):
        return {"id": "chat", "title": "Test", "messages": [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First reply", "model": "one"},
            {"role": "user", "content": "Follow-up"},
            {"role": "assistant", "content": "Second reply"},
        ]}

    def test_edit_keeps_old_continuation_and_survives_reopening(self):
        chat = self.chat()
        original = copy.deepcopy(chat["messages"])
        replacement = history.edited_message(chat["messages"][0], "Edited question")
        self.assertEqual(history.fork(chat, 0, replacement, "two"), 0)
        self.assertEqual(chat["messages"], [replacement])
        chat["messages"].append({"role": "assistant", "content": "Edited reply", "model": "two"})
        history.checkpoint(chat)
        self.assertEqual(history.choices(chat, 0), [0, 1])
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.chats = [chat]
            store.save()
            chat = Store(folder).chats[0]
            history.select(chat, 0)
            self.assertEqual(chat["messages"], original)
            history.select(chat, 1)
            self.assertEqual(chat["messages"][1]["content"], "Edited reply")

    def test_regeneration_and_nested_turns_keep_complete_tool_context(self):
        chat = self.chat()
        chat["messages"][1:2] = [
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "tool"}}]},
            {"role": "tool", "content": "Tool output", "tool_name": "tool"},
            {"role": "assistant", "content": "First reply", "model": "one"},
        ]
        original = copy.deepcopy(chat["messages"])
        history.fork(chat, 4, model="two")
        self.assertEqual(chat["messages"], original[:5])
        chat["messages"].append({"role": "assistant", "content": "New follow-up", "model": "two"})
        self.assertEqual(history.choices(chat, 0), [1])
        self.assertEqual(history.choices(chat, 4), [0, 1])
        history.select(chat, 0)
        self.assertEqual(chat["messages"], original)
        history.fork(chat, 0, model="one")
        self.assertEqual(chat["messages"], original[:1])
        self.assertEqual(chat["branches"][1]["messages"][-1]["content"], "New follow-up")

    def test_edit_retains_files_and_images_and_does_not_mutate_original(self):
        file = {"name": "notes.txt", "kind": "file", "content": "Private file text"}
        image = {"name": "image.png", "kind": "image", "content": "encoded"}
        original = user_message("Old message", [file, image])
        before = copy.deepcopy(original)
        edited = history.edited_message(original, "New message")
        self.assertEqual(edited["display_content"], "New message")
        self.assertIn("Private file text", edited["content"])
        self.assertEqual(edited["images"], ["encoded"])
        edited["attachments"][0]["content"] = "changed"
        self.assertEqual(original, before)
