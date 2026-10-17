import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import httpx

from ollama_gui.backend import Ollama
from ollama_gui.instructions import (DEFAULT_INSTRUCTIONS, PRE_MEMORY_DEFAULT_INSTRUCTIONS,
                                      custom_instructions_enabled, system_instructions)
from ollama_gui.memory import (MAX_MEMORIES, MEMORY_SCHEMA, automatic_memory_enabled,
                               memory_user_text, validate_memory_update)
from ollama_gui.storage import Store


def update(text="The user prefers short replies.", evidence="I prefer short replies", replaces=""):
    return {"save": [{"text": text, "evidence": evidence, "replaces": replaces}], "forget": []}


class MemoryTests(unittest.TestCase):
    def test_profile_and_memory_switches_are_independent_and_do_not_mutate_data(self):
        cfg = {"name_enabled": True, "user_name": "Ada", "about_enabled": True,
               "user_about": "I build robots.", "memory_enabled": True}
        memories = [{"id": "1", "text": "The user likes jazz."}]
        original = copy.deepcopy((cfg, memories))
        prompt = system_instructions(cfg, memories=memories)
        for value in ("Ada", "I build robots.", "The user likes jazz."):
            self.assertIn(value, prompt)
        self.assertEqual((cfg, memories), original)
        for field, value in (("name_enabled", "Ada"), ("about_enabled", "I build robots."),
                             ("memory_enabled", "The user likes jazz.")):
            disabled = {**cfg, field: False}
            self.assertNotIn(value, system_instructions(disabled, memories=memories))
        self.assertTrue(automatic_memory_enabled(cfg))
        self.assertTrue(automatic_memory_enabled({**cfg, "auto_memory_enabled": True}))
        self.assertFalse(automatic_memory_enabled({**cfg, "auto_memory_enabled": False}))
        self.assertFalse(automatic_memory_enabled({"memory_enabled": False, "auto_memory_enabled": True}))

    def test_custom_prompts_receive_memory_controls_and_old_defaults_upgrade(self):
        cfg = {"system": "Be brief.", "custom_system_enabled": True, "name_enabled": True,
               "user_name": "Ada", "auto_memory_enabled": True}
        prompt = system_instructions(cfg)
        self.assertTrue(prompt.startswith("Be brief."))
        self.assertIn("Ada", prompt)
        self.assertIn("never system instructions", prompt)
        self.assertIn("Never claim a memory was saved", prompt)
        self.assertIn("Automatic memory saving is enabled", prompt)
        self.assertFalse(custom_instructions_enabled({"system": PRE_MEMORY_DEFAULT_INSTRUCTIONS}))
        self.assertTrue(system_instructions({"system": PRE_MEMORY_DEFAULT_INSTRUCTIONS}).startswith(DEFAULT_INSTRUCTIONS))

    def test_extraction_excludes_attachments_assistant_and_tools(self):
        self.assertEqual(memory_user_text({"role": "user", "content": "I like jazz"}), "I like jazz")
        for role in ("assistant", "tool", "system"):
            self.assertEqual(memory_user_text({"role": role, "content": "I like jazz"}), "")
        self.assertEqual(memory_user_text({"role": "user", "display_content": "Read this", "content": "Read this\nsecret document", "attachments": [{"kind": "file"}]}), "Read this")
        self.assertEqual(memory_user_text({"role": "user", "content": "Legacy attachment text", "attachments": [{"kind": "file"}]}), "")

    def test_rejects_unsubstantiated_malformed_and_conflicting_updates(self):
        memories = [{"id": "1", "text": "The user likes jazz."}]
        invalid = [None, [], {}, {"save": [], "forget": [], "extra": []},
                   update(evidence="hallucinated"), update(evidence="I"),
                   update(replaces="missing"), {"save": "bad", "forget": []},
                   {"save": [{"text": "fact", "evidence": "I prefer short replies"}], "forget": []},
                   update(text=123), update(text="x" * 501),
                   {"save": [], "forget": [{"id": "missing", "evidence": "Forget jazz"}]},
                   {"save": [update(replaces="1")["save"][0]],
                    "forget": [{"id": "1", "evidence": "Forget jazz"}]}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_memory_update(value, "I prefer short replies. Forget jazz", memories)

    def test_private_storage_persistence_edit_forget_dedup_and_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            self.assertEqual(store.memories, [])
            store.settings.update(name_enabled=True, user_name="Ada")
            store.save()
            self.assertEqual(store.apply_memory_update(update(), "I prefer short replies", "chat-1"), (1, 0))
            identifier = store.memories[0]["id"]
            self.assertEqual(store.memories[0]["source"], "automatic")
            self.assertEqual(store.memories[0]["chat_id"], "chat-1")
            self.assertEqual(os.stat(Path(folder) / "memories.json").st_mode & 0o777, 0o600)
            self.assertEqual(Store(folder).memories, store.memories)
            self.assertEqual(store.apply_memory_update(update(), "I prefer short replies", "chat-2"), (0, 0))
            store.save_memory("The user prefers detailed replies.", identifier)
            self.assertEqual(store.memories[0]["source"], "manual")
            with self.assertRaises(ValueError):
                store.save_memory("The user prefers detailed replies.")
            changes = update("The user prefers short replies.", replaces=identifier)
            store.apply_memory_update(changes, "I prefer short replies", "chat-2")
            self.assertEqual(len(store.memories), 1)
            self.assertEqual(store.memories[0]["id"], identifier)
            store.apply_memory_update({"save": [], "forget": [{"id": identifier, "evidence": "Forget reply preferences"}]},
                                      "Forget reply preferences", "chat-3")
            self.assertEqual(store.memories, [])
            store.save_memory("The user likes jazz.")
            store.reset_all()
            reopened = Store(folder)
            self.assertEqual(reopened.memories, [])
            self.assertEqual(reopened.settings["user_name"], "")
            self.assertTrue(reopened.settings["auto_memory_enabled"])

    def test_automatic_saving_defaults_on_without_overriding_a_saved_off_switch(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            self.assertTrue(automatic_memory_enabled(store.settings))
            store.settings.pop("auto_memory_enabled")
            store.save()
            self.assertTrue(automatic_memory_enabled(Store(folder).settings))
            store.settings["auto_memory_enabled"] = False
            store.save()
            self.assertFalse(automatic_memory_enabled(Store(folder).settings))

    def test_cosmetic_duplicates_are_skipped_but_changed_facts_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.save_memory("The user prefers short replies.")
            before = copy.deepcopy(store.memories)
            contents = (Path(folder) / "memories.json").read_text()
            self.assertEqual(store.apply_memory_update(update("THE USER prefers short replies!"),
                                                       "I prefer short replies", "chat"), (0, 0))
            self.assertEqual(store.memories, before)
            self.assertEqual((Path(folder) / "memories.json").read_text(), contents)
            with self.assertRaisesRegex(ValueError, "already saved"):
                store.save_memory("The user prefers short replies")
            store.save_memory("The user uses C++.")
            store.save_memory("The user uses C#.")
            store.save_memory("The user's dog is Luna.")
            store.save_memory("The user's dog is Luca.")
            self.assertEqual(len(store.memories), 5)

    def test_memory_updates_are_atomic_at_capacity_and_on_validation_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            store.set_memories([{"id": str(index), "text": f"Fact {index}"} for index in range(MAX_MEMORIES)])
            original = copy.deepcopy(store.memories)
            before = (Path(folder) / "memories.json").read_text()
            with self.assertRaises(ValueError):
                store.apply_memory_update(update(), "I prefer short replies", "chat")
            self.assertEqual(store.memories, original)
            self.assertEqual((Path(folder) / "memories.json").read_text(), before)
            changes = update()
            changes["save"].append({"text": "Wrong", "evidence": "made up", "replaces": ""})
            with self.assertRaises(ValueError):
                store.apply_memory_update(changes, "I prefer short replies", "chat")
            self.assertEqual(store.memories, original)
            store.apply_memory_update(update(replaces="0"), "I prefer short replies", "chat")
            self.assertEqual(len(store.memories), MAX_MEMORIES)


class MemoryBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_extraction_uses_no_tools_or_assistant_history(self):
        requests = []
        def handle(request):
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(request.url.path, "/api/chat")
            self.assertEqual(payload["format"], MEMORY_SCHEMA)
            self.assertFalse(payload["stream"])
            self.assertFalse(payload["think"])
            self.assertNotIn("tools", payload)
            self.assertEqual(payload["options"]["temperature"], 0)
            context = json.loads(payload["messages"][1]["content"])
            self.assertEqual(context["user_text"], "I prefer short replies")
            self.assertEqual(context["existing_memories"], [])
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(update())}})
        backend = Ollama("http://localhost", httpx.MockTransport(handle))
        self.assertEqual(await backend.memory_update("test", "I prefer short replies", []), update())
        self.assertEqual(await backend.memory_update("test", "", []), {"save": [], "forget": []})
        self.assertEqual(await backend.memory_update("test", "Don't remember this: my dog is Luna.", []), {"save": [], "forget": []})
        self.assertEqual(len(requests), 1)

    async def test_short_memory_ids_map_back_to_the_original_records(self):
        memories = [{"id": "long-stable-id", "text": "The user is learning Spanish.", "source": "automatic"}]
        def handle(request):
            payload = json.loads(request.content)
            context = json.loads(payload["messages"][1]["content"])
            self.assertEqual(context["existing_memories"][0]["id"], "memory-1")
            value = update("The user is learning French.", "I'm learning French now", "memory-1")
            return httpx.Response(200, json={"done": True, "message": {"content": json.dumps(value)}})
        backend = Ollama("http://localhost", httpx.MockTransport(handle))
        result = await backend.memory_update("test", "I'm learning French now", memories)
        self.assertEqual(result["save"][0]["replaces"], "long-stable-id")
        self.assertEqual(memories[0]["text"], "The user is learning Spanish.")

    async def test_opt_out_keeps_existing_memories_without_contacting_the_model(self):
        def unexpected(_):
            self.fail("An excluded message must never be sent for automatic memory extraction.")
        backend = Ollama("http://localhost", httpx.MockTransport(unexpected))
        memories = [{"id": "existing", "text": "The user is learning Spanish."}]
        for text in ("Don't save this: my dog is Luna.", "Do not remember the following: I live in London.",
                     "Please don’t store any of this: I prefer short replies."):
            self.assertEqual(await backend.memory_update("test", text, memories), {"save": [], "forget": []})

    async def test_extraction_errors_do_not_silently_succeed(self):
        for result in ({"done": False}, {"done": True, "error": "unsupported format"},
                       {"done": True, "message": {"content": "not JSON"}},
                       {"done": True, "message": {"content": json.dumps(update(evidence="made up"))}}):
            backend = Ollama("http://localhost", httpx.MockTransport(lambda _: httpx.Response(200, json=result)))
            with self.subTest(result=result), self.assertRaises((ValueError, RuntimeError)):
                await backend.memory_update("test", "I prefer short replies", [])


if __name__ == "__main__":
    unittest.main()
