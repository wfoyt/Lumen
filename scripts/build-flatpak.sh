#!/usr/bin/env bash
# Build from this checkout, then export a single-file distribution bundle.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$project_dir"
app_id=io.github.ollamagnome.Lumen
version="$(python3 -c 'from ollama_gui import __version__; print(__version__)')"
arch="${FLATPAK_ARCH:-$(flatpak --default-arch)}"
bundle="Lumen-$version-$arch.flatpak"
if command -v flatpak-builder >/dev/null 2>&1; then
    builder=(flatpak-builder)
elif flatpak info org.flatpak.Builder >/dev/null 2>&1; then
    builder=(flatpak run org.flatpak.Builder)
else
    printf '%s\n' 'Install flatpak-builder or run: flatpak install --user flathub org.flatpak.Builder' >&2
    exit 1
fi
mkdir -p dist
"${builder[@]}" --force-clean --user --install-deps-from=flathub \
    --arch="$arch" --repo=build/flatpak-repo \
    build/flatpak packaging/flatpak/"$app_id".json "$@"
flatpak build-bundle --arch="$arch" \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    build/flatpak-repo "dist/$bundle" "$app_id" stable
(cd dist && sha256sum "$bundle" > "$bundle.sha256")
printf 'Bundle ready: %s/dist/%s\n' "$project_dir" "$bundle"
