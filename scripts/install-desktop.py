"""Install a launcher for this source checkout in the current user's menu."""
import os
import shutil
import subprocess
from pathlib import Path

project = Path(__file__).resolve().parents[1]
data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
target = data / "applications/io.github.ollamagnome.Lumen.desktop"
target.parent.mkdir(parents=True, exist_ok=True)
# Register the icon under the application ID so GNOME can also resolve it
# for running windows, notifications and the overview.
icon_dir = data / "icons/hicolor/256x256/apps"
icon_dir.mkdir(parents=True, exist_ok=True)
shutil.copyfile(project / "ollama_gui/icons/lumen.png", icon_dir / "io.github.ollamagnome.Lumen.png")
def quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$') + '"'
target.write_text("\n".join([
    "[Desktop Entry]", "Type=Application", "Name=Lumen", "Comment=Chat with local models and MCP tools",
    "Exec=" + quote(project / "scripts/run.sh"), "Icon=io.github.ollamagnome.Lumen", "Terminal=false",
    "Categories=Utility;", "StartupNotify=true", "StartupWMClass=io.github.ollamagnome.Lumen", "X-GNOME-UsesNotifications=true", "",
]))
print(f"Installed {target}")

# Replace only this checkout's old launcher, preserving unrelated installations.
legacy = data / "applications/io.github.ollamagnome.Ollama.desktop"
if legacy.is_file() and "Exec=" + quote(project / "scripts/run.sh") in legacy.read_text():
    legacy.unlink()

for command in (("gtk-update-icon-cache", "--force", "--ignore-theme-index", str(data / "icons/hicolor")), ("update-desktop-database", str(target.parent))):
    if shutil.which(command[0]):
        subprocess.run(command, check=False)
