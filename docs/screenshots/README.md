# Lumen screenshots

Full-resolution PNG captures of the real Linux app, with fictional everyday conversations. Use these files for the project README and a future Flathub listing. There are no promotional overlays, desktop backgrounds, personal chat histories, or real API keys in the captures.

## Gallery and captions

The first six images make a feature-focused store gallery. The preferences screenshot is an optional seventh image. Use `chat-light.png` as the default screenshot.

| Order | File | Suggested caption |
|---|---|---|
| 1 | [chat-light.png](chat-light.png) | Plan everyday tasks with clear answers and organized conversations |
| 2 | [attachments.png](attachments.png) | Turn images and meeting notes into useful next steps |
| 3 | [tools.png](tools.png) | Check calculations with built-in Python and inspect the results |
| 4 | [web-search.png](web-search.png) | Search the web with Brave Search and open the original sources |
| 5 | [equations-code.png](equations-code.png) | Read rendered equations and copy highlighted code |
| 6 | [chat-dark.png](chat-dark.png) | Refine a reply and revisit earlier versions in dark mode |
| Optional | [preferences.png](preferences.png) | Choose your tools and how their activity appears |

## Capture details

- Native GTK/libadwaita window at **1000 × 700 logical pixels**, captured at **2× resolution** for crisp text.
- PNGs retain GTK's native rounded corners, decorations, and transparent window shadows. Image dimensions include the shadow.
- Light appearance for the main gallery; one dark screenshot demonstrates theme support.
- The same window size and platform typography throughout, with no image rescaling or added graphics.
- Fictional sample messages and attachment data; Python fixture output is calculated when capturing. Search activity uses illustrative results pointing to real official pages, without making a live Brave request.

These choices follow [Flathub's screenshot quality guidance](https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines/quality-guidelines): readable app windows, useful content, native decoration, and short captions.

## Recreate the images

From the repository root, with the project's dependencies and a working Linux desktop display:

```bash
.venv/bin/python scripts/readme_screenshots.py
```

The script replaces only the gallery PNGs in this directory. It uses disposable data and does not read or change your existing Lumen conversations or preferences. Ollama and Brave Search are not needed for the capture.

## Prepare a Flathub listing

Flathub reads screenshots and captions from the app's MetaInfo XML. When these images have been committed and made publicly accessible, add `<screenshots>` entries to `packaging/flatpak/io.github.ollamagnome.Lumen.metainfo.xml` using the captions above. Set `type="default"` on the first screenshot and `xml:lang="en"` on the images.

Use direct image URLs pinned to the published commit or release tag, rather than a moving branch. The set is ready to host; screenshots have not been added to the live MetaInfo because their immutable public URLs do not exist yet. See [Flathub's MetaInfo instructions](https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines#screenshots).
