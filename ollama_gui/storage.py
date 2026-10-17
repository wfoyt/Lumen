import json
import os
import copy
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from .instructions import DEFAULT_INSTRUCTIONS
from .memory import MAX_MEMORIES, clean_memory, memory_key, validate_memory_update


DEFAULT_SETTINGS = {
    "url": "http://localhost:11434",
    "model": "",
    "system": DEFAULT_INSTRUCTIONS,
    "custom_system_enabled": False,
    "custom_mcp_enabled": False,
    "mcpServers": {},
    "tools_enabled": True,
    "python_enabled": True,
    "auto_titles": True,
    "show_thinking": False,
    "friendly_search": True,
    "friendly_python": True,
    "latex_enabled": True,
    "brave_enabled": False,
    "name_enabled": False,
    "user_name": "",
    "about_enabled": False,
    "user_about": "",
    "memory_enabled": True,
    "auto_memory_enabled": True,
}

PYTHON_SERVER_NAME = "Built-in Python"


def brave_enabled(settings):
    server = settings.get("mcpServers", {}).get("brave-search")
    return settings.get("brave_enabled", bool(server) and server.get("enabled", True))


def tool_servers(settings):
    if not settings.get("tools_enabled", True):
        return {}
    servers = copy.deepcopy(settings["mcpServers"])
    if not brave_enabled(settings):
        servers.pop("brave-search", None)
    servers[PYTHON_SERVER_NAME] = {
        "command": sys.executable, "args": ["-m", "ollama_gui.python_tool"],
        "disabled_tools": [] if settings.get("python_enabled", True) else ["execute_python"],
    }
    return servers


def configure_brave(servers, key, original_key=None):
    """Merge the dedicated key field without replacing custom server settings."""
    servers = copy.deepcopy(servers)
    key = key.strip()
    cfg = servers.get("brave-search", {})
    # Upgrade the original stock setup while retaining custom launchers.
    if cfg.get("command") == "npx" and cfg.get("args") == ["-y", "@brave/brave-search-mcp-server", "--transport", "stdio"]:
        cfg["command"] = sys.executable
        cfg["args"] = ["-m", "ollama_gui.brave"]
    if original_key is not None and key == original_key:
        return servers
    if key:
        cfg = servers.setdefault("brave-search", {
            "command": sys.executable,
            "args": ["-m", "ollama_gui.brave"],
            "env": {},
        })
        cfg.setdefault("env", {})["BRAVE_API_KEY"] = key
    elif "brave-search" in servers:
        servers["brave-search"].get("env", {}).pop("BRAVE_API_KEY", None)
    return servers


def validate_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter an HTTP or HTTPS URL without embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("The server URL cannot contain a query or fragment.")
    return value.rstrip("/")


def validate_servers(servers):
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be a JSON object.")
    for name, cfg in servers.items():
        if name == PYTHON_SERVER_NAME:
            raise ValueError(f"{name} is reserved for the app’s Python tool.")
        if not isinstance(name, str) or not name or not isinstance(cfg, dict):
            raise ValueError("Each server needs a name and a configuration object.")
        if "url" in cfg:
            validate_url(cfg["url"])
        elif not isinstance(cfg.get("command"), str) or not cfg["command"].strip():
            raise ValueError(f"{name}: supply command or url.")
        if not isinstance(cfg.get("args", []), list) or not all(isinstance(x, str) for x in cfg.get("args", [])):
            raise ValueError(f"{name}: args must be an array of strings.")
        if not isinstance(cfg.get("disabled_tools", []), list) or not all(isinstance(x, str) for x in cfg.get("disabled_tools", [])):
            raise ValueError(f"{name}: disabled_tools must be an array of tool names.")
        for field in ("env", "headers"):
            values = cfg.get(field, {})
            if not isinstance(values, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()):
                raise ValueError(f"{name}: {field} must contain string values.")
    return servers


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "ollama-gnome"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.settings = self.read("settings.json", copy.deepcopy(DEFAULT_SETTINGS))
        self.chats = self.read("chats.json", [])
        self.memories = self.read("memories.json", [])

    def set_memories(self, memories):
        if len(memories) > MAX_MEMORIES:
            raise ValueError(f"Memory is full ({MAX_MEMORIES} entries). Delete or combine some memories first.")
        self.write("memories.json", memories)
        self.memories = memories

    def save_memory(self, text, identifier=None, source="manual", chat_id=None):
        text = clean_memory(text)
        memories = copy.deepcopy(self.memories)
        if any(memory_key(item["text"]) == memory_key(text) and item["id"] != identifier for item in memories):
            raise ValueError("That memory is already saved.")
        item = next((item for item in memories if item["id"] == identifier), None)
        if identifier is not None and item is None:
            raise ValueError("That memory no longer exists.")
        if item is None:
            item = {"id": str(uuid.uuid4())}
            memories.append(item)
        item.update(text=text, source=source, chat_id=chat_id,
                    updated_at=datetime.now(timezone.utc).isoformat())
        self.set_memories(memories)

    def delete_memory(self, identifier):
        self.set_memories([item for item in self.memories if item["id"] != identifier])

    def apply_memory_update(self, value, user_text, chat_id):
        validate_memory_update(value, user_text, self.memories)
        memories = copy.deepcopy(self.memories)
        removed = {item["id"] for item in value["forget"]}
        memories = [item for item in memories if item["id"] not in removed]
        saved = 0
        for entry in value["save"]:
            text = clean_memory(entry["text"])
            target = next((item for item in memories if item["id"] == entry["replaces"]), None)
            duplicate = next((item for item in memories if memory_key(item["text"]) == memory_key(text)), None)
            if duplicate is not None and duplicate is not target:
                continue
            if target is None:
                target = {"id": str(uuid.uuid4())}
                memories.append(target)
            if memory_key(target.get("text", "")) == memory_key(text):
                continue
            target.update(text=text, source="automatic", chat_id=chat_id,
                          updated_at=datetime.now(timezone.utc).isoformat())
            saved += 1
        if memories != self.memories:
            self.set_memories(memories)
        return saved, len(removed)

    @property
    def needs_setup(self):
        # Settings or history from earlier versions count as an existing setup.
        # An explicit incomplete marker still takes precedence.
        return not self.settings.get("setup_completed", (self.root / "settings.json").exists() or bool(self.chats))

    def read(self, name, default):
        path = self.root / name
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return default

    def write(self, name, value):
        path = self.root / name
        temporary = path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, indent=2, ensure_ascii=False)
        temporary.replace(path)

    def save(self):
        self.write("settings.json", self.settings)
        self.write("chats.json", self.chats)

    def reset_all(self):
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.write("settings.json", settings)
        self.write("chats.json", [])
        self.set_memories([])
        for name in ("settings.tmp", "chats.tmp", "memories.tmp"):
            (self.root / name).unlink(missing_ok=True)
        self.settings, self.chats = settings, []
