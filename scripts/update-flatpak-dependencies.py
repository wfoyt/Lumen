#!/usr/bin/env python3
"""Refresh pinned sources using an upstream flatpak-pip-generator checkout.

Run with a Python environment containing requirements-parser and packaging:
  .venv/bin/python scripts/update-flatpak-dependencies.py /path/to/flatpak-pip-generator.py
"""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib

if len(sys.argv) != 2:
    raise SystemExit("Usage: update-flatpak-dependencies.py /path/to/flatpak-pip-generator.py")
project = Path(__file__).resolve().parents[1]
generator = Path(sys.argv[1]).resolve(strict=True)
metadata = tomllib.loads((project / "pyproject.toml").read_text())
manifest = json.loads((project / "packaging/flatpak/io.github.ollamagnome.Lumen.json").read_text())
requirements = metadata["project"]["dependencies"] + metadata["build-system"]["requires"] + ["wheel"]
names = [re.match(r"[A-Za-z0-9_.-]+", requirement)[0].lower() for requirement in requirements]
with tempfile.TemporaryDirectory(prefix="lumen-flatpak-deps-") as directory:
    path = Path(directory) / "requirements.txt"
    path.write_text("\n".join(requirements) + "\n")
    subprocess.run([
        sys.executable, str(generator), "--runtime", f'{manifest["sdk"]}//{manifest["runtime-version"]}',
        "--requirements-file", str(path),
        # SDK-only packages must not satisfy application runtime dependencies.
        "--ignore-installed", ",".join(names),
        "--prefer-wheels", "pillow,pydantic-core,cffi,cryptography,rpds-py",
        "--output", "packaging/flatpak/python-dependencies",
    ], cwd=project, check=True)
