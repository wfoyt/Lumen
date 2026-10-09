# Lumen

A native GTK 4 / libadwaita chat application for Linux. Python and PyGObject power the interface; Ollama runs your models, and the official MCP Python SDK connects their tools to local or Streamable HTTP MCP servers.

## Install with Flatpak

With [Flatpak installed for your distribution](https://flatpak.org/setup/), install the bundle matching your CPU architecture:

```bash
flatpak install --user ./Lumen-x86_64.flatpak
flatpak run io.github.ollamagnome.Lumen
```

Lumen also appears in your application menu. The bundle includes the Python dependencies, PDF preview support and application assets; Flatpak downloads the matching GNOME runtime when necessary. Ollama and its models are installed separately on your computer or another server. The default `http://localhost:11434` works with host Ollama through the app's network permission.

The Flatpak uses file-picker portals for attachments and does not request access to your home directory. Settings, API keys and conversations are stored separately from a source installation under `~/.var/app/io.github.ollamagnome.Lumen/data/ollama-gnome`. To migrate existing data, close both installations and copy `settings.json` and `chats.json` from `~/.local/share/ollama-gnome/` into that directory, retaining private file permissions.

Built-in Brave Search and Python work inside the package. Python calculations use a fresh Flatpak child sandbox with no network or private application data access and retain the execution limits described below. Custom HTTP MCP servers work normally. Custom stdio MCP servers must be available inside the Flatpak sandbox; host paths, host Python environments and host `npx` installations are not automatically available. Prefer HTTP MCP servers for external integrations.

## Build a distributable Flatpak

The manifest is [packaging/flatpak/io.github.ollamagnome.Lumen.json](packaging/flatpak/io.github.ollamagnome.Lumen.json). It builds the current checkout with checksum-pinned dependencies and no network access during compilation or Python installation.

```bash
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.flatpak.Builder org.gnome.Sdk//50 org.gnome.Platform//50
./scripts/build-flatpak.sh
flatpak install --user ./dist/Lumen-x86_64.flatpak
python3 scripts/check_flatpak.py
```

Distribute `dist/Lumen-x86_64.flatpak` to users on Linux distributions supporting Flatpak. Build on ARM64 Linux to produce `dist/Lumen-aarch64.flatpak`; the dependency manifest includes wheels for both architectures. Each bundle is architecture-specific. `FLATPAK_ARCH` can select an architecture when the matching SDK and cross-build environment are available. Pass extra builder options to the build script, such as `--install` to install the build locally. The app is exported on the `stable` branch. Building does not publish it to Flathub.

The package check opens a temporary window and verifies native imports, PDF rendering, equations, MCP execution, and Python's network/data isolation, timeout and output limit. It uses temporary data and requires a graphical session with the Flatpak portal running.

To update Python dependencies, download the upstream [flatpak-pip-generator](https://github.com/flatpak/flatpak-builder-tools/tree/master/pip), install its `requirements-parser` and `packaging` helpers into your development virtual environment, and run:

```bash
.venv/bin/python scripts/update-flatpak-dependencies.py /path/to/flatpak-pip-generator.py
```

The helper reads `pyproject.toml` and the SDK version from the manifest, includes native wheels for both architectures, and forces dependency installation so SDK-only packages cannot accidentally satisfy runtime requirements. Rebuild and rerun the package check after updating. The GNOME runtime provides PyGObject and Pycairo; they should not be replaced by pip copies. The SDK supplies setuptools and wheel for the application build. A runtime change also requires regenerating the Python dependencies for its Python version.

## Run on Fedora

Requires Python 3.11+, GTK 4.10+, libadwaita 1.5+, GtkSourceView 5 and bubblewrap for the Python tool. Poppler GLib enables native PDF page previews.

```bash
sudo dnf install python3-gobject gtk4 libadwaita gtksourceview5 poppler-glib bubblewrap python3-pip
./scripts/setup.sh
./scripts/run.sh
```

Install and start [Ollama](https://docs.ollama.com/linux) separately. Pull a model, then choose **Refresh Models** from the app menu. Ollama defaults to `http://localhost:11434`; change the URL under **Preferences → Advanced → Ollama** when needed. For MCP, choose a model that supports [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling). Unsupported models will show the server's error.

On the first launch, Lumen welcomes you and walks through **Ollama → Tools → Finish**. Choose **Use Default URL** for Ollama on this computer, or **Use Custom URL · Advanced** to enter a remote or nonstandard HTTP/HTTPS address. Tools and Python start enabled; Brave Search starts disabled. Enabling Brave Search reveals a password field and dashboard instructions for getting an API key. Turning off Tools hides its integration settings. Finish saves your choices and opens your first chat. Closing setup before finishing leaves it available on the next launch; existing installations skip setup.

An optional app-menu launcher refers to this checkout, so keep the directory in place:

```bash
python3 scripts/install-desktop.py
```

## Brave Search

1. Get a key from the [Brave Search API dashboard](https://api-dashboard.search.brave.com/).
2. Open **Preferences → Tools → Brave Search** and turn on **Enable Brave Search** to reveal the key field. Enter the key; it saves automatically. **Set Up Brave Search** also saves it immediately. The padded button turns blue for unsaved changes and returns to gray once saved. The key and other preferences also save automatically after editing. Turning Brave Search off hides its setup fields and prevents its server from connecting or offering tools, while retaining the key and individual tool choices for later. Previously configured Brave servers remain enabled unless you disable them; new installations start with Brave Search off.
3. Optional: **Test Brave Search**, beside the setup button under **Tools**, runs a sample web search using your current key field, even before saving. It checks the search tool and API authentication without connecting to unrelated MCP servers. The sample request uses your Brave API plan.
4. Open the **Tools** dropdown beside **+** inside the message box to see individual tools, enabled by default. Uncheck any tools you do not want the model to use. Ask the model to search the web.

Brave Search has its own subsection under **Tools**, separate from Python. The app includes a Python stdio MCP server for [Brave's Search API](https://api-dashboard.search.brave.com/documentation/guides/authentication). Node/npm are not required for this integration. Once Brave Search is enabled, web and news tools default to checked. Search queries are sent to Brave and may consume your API plan's quota. The model decides when to invoke a tool. Changing preferences upgrades the app's original stock npx Brave configuration to the bundled server; custom launch commands and individual tool choices are preserved.


## Other MCP servers

Under **Preferences → Advanced**, turn on **Edit Custom MCP Configuration** to reveal and unlock the JSON editor and its **Test Servers** button. It accepts a standard `{"mcpServers": {...}}` object; see [data/mcp.example.json](data/mcp.example.json). Hiding the editor keeps saved servers working; Brave Search is available on the Tools page when tools are enabled. Local entries accept `command`, a string array `args`, and an `env` object. HTTP entries accept `url` and optional `headers` (including authorization headers). Add `"enabled": false` to disable an entry. Shell expansion is not performed; use explicit arguments and paths. OAuth login and legacy SSE transport are not implemented.

The **Tools** preferences tab starts with **Enable Tools**, on by default. Switch it off to disable all built-in and custom MCP tools without losing API keys, server configurations or individual choices. Its tool settings are shown only while enabled.

Tools are discovered when the app opens, after changing tool preferences, and with **Refresh Tools** in the Tools menu. They are discovered again at the start of each chat turn, namespaced across servers, and sent to Ollama as JSON schemas. Individual tool choices are saved as `disabled_tools` arrays in the server configuration. Disabled tools are excluded from both the model's tool list and execution routes; a server with all known tools disabled is skipped for chat. Tool calls execute sequentially; their results are returned as `tool` messages until the model answers. The UI shows expandable tool details. A turn is limited to 12 model rounds and 15 minutes, with 60-second MCP request timeouts. Connection failure fails the turn visibly rather than silently answering without its tools.

Only configure servers you trust: local servers run programs under your account. Tools from configured servers default to enabled, and their checkboxes authorize the model to invoke them. Your disabled choices persist across restarts. There is no tool approval dialog during a turn.

## Python calculations

The built-in **execute_python** MCP tool is enabled by default. Switch **Python** on or off under **Preferences → Tools**. Changes are saved automatically. The individual checkbox in **Tools** controls the same saved setting. The model supplies Python source and an optional `.py` filename; the app writes and executes that file in a fresh, disposable bubblewrap sandbox. Ask it to use Python for calculations, statistics or processing text from attachments. Results include stdout, stderr, exit status and timeout/output-limit indicators.

Python's standard library is available, including `math`, `statistics`, `decimal` and `fractions`. Third-party libraries, interactive input, the network, home directories and saved API keys are unavailable in this environment. Execution takes at most 30 seconds, with limits on memory, CPU, file size and captured output. Files created by the script are discarded afterwards. The reserved “Built-in Python” entry is managed by the app and does not belong in the MCP JSON editor. Disabling the tool persists across restarts.

Default assistant instructions tell the model when to use Python, how to supply source and print results, and how to check errors before answering. Each request includes the current local date, time, timezone and UTC offset. To replace the default instructions, enable **Use Custom Assistant Instructions** on the Advanced page; the editor stays hidden and locked until enabled. Turning the switch off restores the default behavior while retaining your custom text. The clock is appended even when using custom instructions. Previously saved custom prompts are retained; the app's old default prompt automatically receives the new guidance.

## Interface and storage

- Adaptive conversation sidebar, standard GNOME header bars, preferences and deletion dialogs; follows system light/dark appearance.
- Streaming answers, stop button, model selection, copy messages, local conversation history and editable system instructions. The conversation header shows the current chat's title, truncates long titles on narrow windows, and updates when a title is generated or renamed.
- Preferences save switches immediately and text fields after a short pause or when closing the dialog. Invalid URLs or custom MCP JSON keep the last valid value while showing a validation message; other settings still save. The Tools button is hidden while tools are disabled.
- Edit a user message with its pencil button or regenerate a response with its refresh button. Both let you choose an installed reply model. Earlier messages, tool calls, replies and later continuations are retained as saved versions; use the arrows and version counter to revisit them. Continuing a chat uses the selected version as model context. A failed revision restores the previous version and preserves the separate unsent composer draft.
- Enter sends; Shift+Enter inserts a newline; Ctrl+N starts a chat; Ctrl+, opens Preferences.
- The sidebar header has Search on the left, the centered Lumen title, then New Chat and the main menu on the right. Search (Ctrl+F) filters titles, message contents and attachment names; Enter opens the first match and Escape clears and closes the search bar. Conversation options appear on hover or keyboard focus, stay visible while their menu is open, and can also be opened by right-clicking the conversation.
- When the sidebar is hidden, New Chat moves to the conversation header immediately to the right of the sidebar toggle. Showing the sidebar moves it back to the sidebar header.
- The selected model generates a short topic title after the first completed reply in a separate background request. Existing conversations without a generated or manual title are named when opened. Turn off **General → Conversations → Automatically Name Conversations** to stop these requests, including any pending title generation; new chats then use a short version of your opening message. Existing titles stay as they are. The title request excludes images, tool results and reasoning, and does not alter chat history. Starting another reply cancels pending title work so it can be retried later. Generation failure leaves the existing title in place. Choose **Rename Conversation…** from a chat's **⋯** menu to set your own title; manual titles persist and are protected from late automatic results. The menu actions have leading icons and left-aligned labels. Titles always stay on one line, with a native gradient fade for overflow and a tooltip showing the full name.
- Choose a model beside the **Tools** button inside the composer. The pill-shaped selector is capped at 240 pixels and shrinks further when needed; long names use an ellipsis. Its separate popup opens upward, provides up to 560 pixels of usable list width with a 260-pixel minimum list height when room allows, and wraps complete model identifiers while staying within small windows.
- Brave calls display **Searching for “query”** and expand into clickable source titles, URLs and brief descriptions. The first three sources appear inline; **Show More** opens all links and complete descriptions in an adaptive libadwaita dialog. Disable **Tools → Tool Display → Format Brave Search Calls** to view raw tool names, arguments and JSON instead. API errors and unfamiliar server output remain visible as literal text. Python calls are labeled **Python** and show the actual executed source with syntax highlighting, followed by execution status and printed results or errors. Disable **Format Python Calls**, directly below the Brave formatting switch, for Python's raw arguments and JSON results. Other tool calls use a four-line literal preview with **Show More** for their full output. Calls retain complete output and arguments locally, while limiting the model's tool context to 60,000 characters; display metadata is excluded from model requests. Older saved chats recover code and queries from their retained assistant tool calls when available. The Tools menu uses readable tool labels such as **Brave Web Search**, **Brave News Search** and **Execute Python**, while retaining original identifiers for dispatch.
- Only one unused blank chat can be created. New Chat and Ctrl+N stay disabled until that chat contains a sent message. Starting a new chat uses a short native crossfade that respects the system animation setting, and closes the sidebar on narrow windows. Chat switching preserves each conversation's unsent draft and attachments in memory. Starting a new chat copies the current composer text, files and images into it, while retaining the original conversation's draft. The attachment lists are independent; removing an attachment from one draft does not remove it from the other.
- Use the **+** menu to add UTF-8 text files (TXT, Markdown, code, CSV; up to 1 MB each), PDFs (up to 20 MB and 200 pages, with up to 1 MB of extracted text) or PNG/JPEG/WebP images (up to 10 MB and 25 megapixels each). PDF text is extracted locally with page labels; unlock encrypted documents before attaching them. Scanned PDFs without selectable text need OCR or page images. Up to eight attachments fit in a message. Remove a draft attachment with its × button. Word documents and other binary files still need conversion to text first.
- Image attachments show compact rounded thumbnails in the composer; hovering does not highlight unused grid space around them. Sent files appear as rounded filename cards alongside image tiles above the user message bubble. Sent images appear as rounded tiles above the user message bubble, aligned to the right and wrapping on narrow windows. Images and files show a pointer cursor and a small native hover animation; clicking them opens an in-app preview. Text/code files use a read-only syntax-highlighted view. New PDF attachments retain their original bytes and render native pages with Previous/Next navigation when Poppler is available; older PDFs and installations without Poppler show the extracted text. Click a sent image to open the uncropped original in a larger native preview. Paste a copied image into the composer with Ctrl+V; ordinary text pasting continues to work. Clipboard images use the same attachment limits and vision-model requirements as uploaded images.
- Attached text is included in the prompt. Image upload and paste require the selected model to report `vision` through Ollama's `/api/show` capability list. Add Images stays disabled while support is unknown, unavailable or absent; text/file uploads remain available. Switching to a text-only model preserves existing image drafts, but sending image drafts or continuing an image-containing history requires a vision model. Edits and regenerated replies enforce the same rule for the chosen reply model. Refresh Models rechecks capabilities. Attachments are retained with the saved conversation. If the Ollama server is remote, attachments are sent there as part of the message.
- The message box grows with wrapped text from 60 to 180 pixels, then scrolls only through the remaining content. Clearing or shortening a draft shrinks it again. The send arrow is inside the padded message box and becomes a stop icon while responding. Delete any conversation through its sidebar **⋯** menu; a confirmation dialog protects against accidental deletion. The main menu contains Preferences and Refresh Models.
- **Thinking…** and a native loading spinner appear while the model is working. Thinking and tool calls are grouped together above a single **Response** heading and the answer, including the final reasoning phase after tools finish. Intermediate assistant text is collected into that turn's response. The spinner stops when a tool call begins or the turn ends. Enable **General → Response Display → Show Model Thinking** to display the model's returned reasoning in collapsible **Model Thinking** sections, both during streaming and in saved conversations. This setting defaults to off and does not enable reasoning on models that do not return it.
- Copying code shows a temporary checkmark and a “Code copied to clipboard” toast, including while an answer is streaming.
- Copying a user message or response likewise shows a temporary checkmark and a “Message copied to clipboard” toast.
- A GNOME desktop notification is sent after a successful reply only while the app is unfocused. Click it to open the conversation. Notifications are cleared when that chat is opened or deleted. Install the user launcher with `python3 scripts/install-desktop.py` to register the app for desktop notifications; GNOME's notification settings and Do Not Disturb apply. Errors and stopped replies do not trigger a completion notification.
- Assistant replies render Markdown with native GTK widgets: headings, bold/italic/strikethrough, nested lists, block quotes, links, tables, inline code and fenced code blocks. Formatting updates during streaming and when saved chats are reopened. GtkSourceView highlights code using its language tag and native Adwaita light/dark color schemes; unknown languages stay readable as plain code. Code blocks wrap long lines and grow with their rendered text up to a 320-pixel preview. Code previews cannot scroll internally: wheel and trackpad gestures scroll the conversation, and **Show More** is the way to reveal the rest inline. **Show Less** restores the preview. Expansion choices survive streaming updates and completion. Code blocks have a separate copy button that copies the complete original code; Copy Message retains the original Markdown. Displayed messages remain selectable without showing a text caret; editable inputs retain their caret. User prompts and unknown tool results remain literal text. Raw HTML is displayed as text, and remote images appear as linked descriptions rather than being fetched automatically.
- **Preferences → General → Response Display** contains the model thinking switch. **Preferences → Tools → Tool Display** contains Brave and Python formatting switches. The Ollama connection URL is on **Advanced**.
- Equation rendering is enabled by default. **Advanced → Equations → LaTeX Equations Support** switches it on or off, including for saved responses and visible thinking. The model receives matching formatting instructions on each request, also when custom assistant instructions are used. Inline `\(x^2\)` or `$x^2$` and display `\[\frac{1}{2}\]` or `$$\frac{1}{2}$$` render locally with [latex2mathml](https://github.com/roniemartinez/latex2mathml) and [Ziamath](https://ziamath.readthedocs.io/en/latest/), without a TeX installation or remote assets. Fractions, roots, Greek letters, sums, integrals, subscripts, superscripts, boxed results, binomials, accents, mathematical fonts, matrices, arrays, aligned equations and piecewise cases are supported. Document preambles, arbitrary package loading, file commands and custom macros are outside the equation renderer and remain readable as source. Long display equations shrink to fit the window. Code fences and inline code remain literal; copying a message retains its original LaTeX. Incomplete equations use a stable placeholder during streaming and render when closed. Completed blocks stay in place as later text arrives, and streaming blocks retain their height during remeasurement. Invalid completed equations show their source. Turning rendering off shows the source and removes the app's equation instructions from model requests. Custom instructions remain under your control.
- Preferences uses padded, rounded multiline editors. **Reset to Default Settings** restores the default connection and assistant instructions and removes saved MCP configurations and keys after confirmation; conversations are retained. This reset is saved immediately.
- **Reset All Data**, below the settings reset, permanently clears conversations, saved attachments, drafts, API keys and preferences after a separate confirmation. The app then starts with one empty conversation. Ollama itself and installed models are unaffected.
- Stop or request failure restores your prompt and discards the incomplete turn, so retries do not carry unfinished tool calls.

For compatibility with existing installations, settings and conversations are stored under `$XDG_DATA_HOME/ollama-gnome` (normally `~/.local/share/ollama-gnome`). Both JSON files are created with mode `0600`. API keys and server headers are stored as plaintext in that private settings file; GNOME Keyring integration is not implemented. You can instead leave credentials out of the JSON and provide them in the launch environment (for example `BRAVE_API_KEY` for the Brave server).

## Development and verification

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/smoke_ui.py
.venv/bin/python scripts/check_setup_ui.py
.venv/bin/python scripts/check_math_ui.py
```

The backend tests run actual stdio MCP fixture servers and simulated streaming Ollama and Brave HTTP responses to verify discovery, tool dispatch, result feedback, cancellation, incomplete streams, round limits, key persistence and private storage. The graphical smoke test briefly opens the window and Preferences using temporary data, checks blank-chat limits and draft isolation, and verifies notifications under simulated focused and unfocused conditions. The setup check uses temporary data and no network calls to verify navigation, defaults, validation, interrupted setup, save failures, restart behavior and adaptive New Chat placement; it also saves previews to `/tmp/lumen-setup-*.png`. Testing against a real model and Brave requires a running Ollama service, a downloaded model and your own API key.
