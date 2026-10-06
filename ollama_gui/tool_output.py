"""Presentation helpers; original tool results remain in the model context."""
import html
import json
import re
from urllib.parse import urlparse


BRAVE_TOOLS = ("brave_web_search", "brave_news_search")


def tool_display_name(name):
    return {"brave_web_search": "Brave Web Search", "brave_news_search": "Brave News Search",
            "execute_python": "Execute Python"}.get(name, re.sub(r"[_-]+", " ", name).title())


def original_tool_name(name):
    return re.sub(r"^s\d+_", "", name.rsplit(" / ", 1)[-1])


def parsed_arguments(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def saved_tool_details(messages):
    """Recover older saved call arguments, consuming repeated calls in order."""
    details, calls = {}, []
    for index, message in enumerate(messages):
        if message.get("role") == "assistant":
            calls = [call.get("function", {}) for call in message.get("tool_calls", [])]
        elif message.get("role") == "tool":
            alias = message.get("tool_name", "Tool")
            call = next((item for item in calls if item.get("name") == alias), {})
            if call:
                calls.remove(call)
            tool = message.get("tool_original_name", original_tool_name(alias))
            server = message.get("tool_server")
            details[index] = {"name": f"{server} / {tool}" if server else alias,
                              "tool_name": tool,
                              "arguments": parsed_arguments(message.get("tool_arguments", call.get("arguments", {})))}
    return details


def json_result(text):
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def brave_results(text):
    """Extract only safe, literal link data from Brave's result object."""
    value = json_result(text)
    if value is None:
        return None
    entries = value.get("results")
    if entries is None and isinstance(value.get("web"), dict):
        entries = value["web"].get("results")
    if not isinstance(entries, list):
        return None
    results = []
    def plain(value):
        return " ".join(html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).split())
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            continue
        url = item["url"]
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        results.append({"url": url, "title": plain(item.get("title")) or url,
                        "description": plain(item.get("description"))})
    # Unexpected nonempty output should remain visible in a literal fallback.
    return results if results or not entries else None


def python_result(text):
    value = json_result(text)
    if value is None or "exit_code" not in value:
        return None
    status = "Completed" if value["exit_code"] == 0 else f"Exited with code {value['exit_code']}"
    if value.get("timed_out"):
        status = "Execution timed out"
    if value.get("output_limited"):
        status += " · Output truncated"
    output = str(value.get("stdout") or "")
    stderr = str(value.get("stderr") or "")
    if stderr:
        output += ("\n" if output else "") + "Errors:\n" + stderr
    return status, output


def tool_preview(text, max_lines=4, max_chars=240):
    lines = text.splitlines()
    preview = "\n".join(lines[:max_lines])
    truncated = len(lines) > max_lines or len(preview) > max_chars
    return preview[:max_chars], truncated


def searchable_chat_text(chat):
    parts = [chat["title"]]
    for message in chat["messages"]:
        parts.append(message.get("display_content", message.get("content", "")))
        parts.extend(item["name"] for item in message.get("attachments", []))
    return "\n".join(parts).casefold()
