"""Install a launcher for this source checkout in the current user's menu."""
import os
from pathlib import Path

project = Path(__file__).resolve().parents[1]
data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
target = data / "applications/io.github.ollamagnome.Lumen.desktop"
target.parent.mkdir(parents=True, exist_ok=True)
def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"'
target.write_text("\n".join([
    "[Desktop Entry]", "Type=Application", "Name=Lumen", "Comment=Chat with local models and MCP tools",
    "Exec=" + quote(project / "scripts/run.sh"), "Icon=" + str(project / "ollama_gui/icons/hicolor/scalable/apps/ollama-chat-symbolic.svg"), "Terminal=false",
    "Categories=Utility;", "StartupNotify=true", "StartupWMClass=io.github.ollamagnome.Lumen", "X-GNOME-UsesNotifications=true", "",
]))
print(f"Installed {target}")

# Replace only this checkout's old launcher, preserving unrelated installations.
legacy = data / "applications/io.github.ollamagnome.Ollama.desktop"
if legacy.is_file() and "Exec=" + quote(project / "scripts/run.sh") in legacy.read_text():
    legacy.unlink()
