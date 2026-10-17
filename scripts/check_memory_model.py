"""Check automatic memory with a real Ollama model using only fictional test data."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ollama_gui.backend import Ollama
from ollama_gui.storage import Store, validate_url


async def check(url, model):
    backend = Ollama(url)
    with tempfile.TemporaryDirectory(prefix="lumen-memory-check-") as folder:
        store = Store(folder)

        async def apply(text):
            result = await backend.memory_update(model, text, store.memories)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            store.apply_memory_update(result, text, "fictional-chat")
            return result

        print("Checking ordinary conversation, without a request to remember…", flush=True)
        await apply("I'm learning Spanish.")
        assert len(store.memories) == 1, "The model didn't save the ordinary statement as one memory."
        identifier = store.memories[0]["id"]
        assert "spanish" in store.memories[0]["text"].lower(), "The model missed the learning goal."
        print("PASS: the learning goal was saved automatically.", flush=True)

        print("Checking a paraphrase of the same fact…", flush=True)
        before = (store.root / "memories.json").read_text()
        result = await apply("I'm studying Spanish.")
        assert not result["save"] and not result["forget"], "The model didn't recognize the paraphrase as already remembered."
        assert (store.root / "memories.json").read_text() == before, "The duplicate rewrote the saved file."
        print("PASS: the repeated fact was skipped, with no file rewrite.", flush=True)

        print("Checking a correction in normal conversation…", flush=True)
        await apply("I've switched to learning French instead of Spanish.")
        assert len(store.memories) == 1 and store.memories[0]["id"] == identifier, "The correction created a second memory."
        assert "french" in store.memories[0]["text"].lower(), "The correction wasn't saved."
        print("PASS: the existing memory was updated.", flush=True)

        print("Checking a request not to remember a detail…", flush=True)
        before = (store.root / "memories.json").read_text()
        await apply("Don't remember this: my dog is named Luna.")
        assert (store.root / "memories.json").read_text() == before, "A detail was saved despite the request not to remember it."
        print("PASS: the excluded detail wasn't saved. Your app data was untouched.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:11434")
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    asyncio.run(check(validate_url(args.url), args.model))


if __name__ == "__main__":
    main()
