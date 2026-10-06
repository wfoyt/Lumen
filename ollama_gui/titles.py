"""Short display titles without changing the conversation's model context."""
import re


def clean_title(text):
    text = " ".join(text.split())
    text = re.sub(r"^(?:chat\s+title|title)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip(' \"\'“”‘’`#*')
    return text[:80].rstrip()


def title_context(messages):
    context = []
    for role in ("user", "assistant"):
        message = next((m for m in messages if m["role"] == role and m.get("content")), None)
        if message:
            context.append({"role": role, "content": message.get("display_content", message["content"])[:2000]})
    return context


def needs_title(chat):
    return chat.get("title_source") not in ("manual", "generated") and len(title_context(chat["messages"])) == 2
