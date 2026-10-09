#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_dir"
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("GtkSource", "5"); from gi.repository import Gtk, Adw, GtkSource' || {
    printf '%s\n' 'Install Fedora dependencies first: sudo dnf install python3-gobject gtk4 libadwaita gtksourceview5 poppler-glib bubblewrap python3-pip' >&2
    exit 1
}
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e .
printf '%s\n' 'Ready. Start with ./scripts/run.sh'
