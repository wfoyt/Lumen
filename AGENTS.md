# Project workflow

Rebuild the Flatpak only when the user explicitly requests it. When requested,
use `scripts/build-flatpak.sh` from the current checkout and refresh the bundle
and checksum in `dist/`.

Update the installed Lumen Flatpak on this system only when changes to the app
are made (application code, runtime dependencies, app assets, or packaging).
Documentation-only changes, including README text, screenshots, and AGENTS.md,
do not require a rebuild or installation update.

For app changes, check both user and system installations and update each
installed copy using a bundle that includes those changes. If this requires a
new build that the user has not requested, ask for the rebuild before proceeding;
do not rebuild automatically or install an outdated bundle.

Run `python3 scripts/check_flatpak.py` after installation. Report any required
build, installation, or verification that remains blocked or pending explicitly.
