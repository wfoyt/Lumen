# Lumen

A comfortable home for your AI conversations on Linux. Chat with Ollama models, explore ideas, work with documents and get a little help with everyday tasks—all in an app that feels at home on your desktop.

![Lumen showing a conversation in light mode](docs/screenshots/chat-light.png)

## Get Lumen

Download Lumen from **[GitHub Releases](https://github.com/wfoyt/Lumen/releases/latest)**. Lumen is distributed as a Flatpak for Linux.

1. [Set up Flatpak](https://flatpak.org/setup/) if you haven’t already.
2. Download the `.flatpak` file for your computer: `x86_64` for most Intel/AMD PCs, or `aarch64` for ARM64 when available.
3. Open a terminal in your Downloads folder and install it (use the name of the file you downloaded):

```bash
flatpak install --user ./Lumen-0.1.0-x86_64.flatpak
```

Then open **Lumen** from your application menu. To update, download the latest release and install its bundle the same way.

Everything Lumen needs for its interface, tools and PDF previews is included or installed automatically by Flatpak. You’ll also need **[Ollama](https://docs.ollama.com/linux)** and a downloaded model, either on your computer or on a server you connect to.

## Make yourself at home

The first-launch guide helps you connect to Ollama and choose your tools. For Ollama on this computer, choose **Use Default URL**. Download a model with Ollama, choose **Refresh Models** in Lumen’s menu, and pick a model beside the message box. You’re ready to chat.

- **Keep the conversation flowing.** Watch replies appear as they’re written, stop a reply whenever you like, and switch between your installed models.
- **Pick up where you left off.** Chats save automatically. Search by title, message or attachment name, rename conversations, and keep drafts while moving between chats.
- **Try another direction.** Edit a message or regenerate a reply with a different model. Earlier versions stay available, so you can revisit them and continue from the one you prefer.
- **Read comfortably.** Enjoy formatted answers, tables, links and code you can copy with a click. Show model thinking when supported, and get a desktop notification when a reply finishes while you’re away from the window.

## Bring your files along

Add notes, text files, code, PDFs or pictures with the **+** button. You can also paste an image straight into your message. Click an attachment to preview it inside Lumen.

![An image and a notes file in a Lumen conversation](docs/screenshots/attachments.png)

Ask for a summary, explore a document, or discuss a picture. Images need a model that can understand pictures. Scanned PDFs need readable text or page images.

## Get help searching and calculating

Turn tools on or off in **Preferences → Tools**, and choose individual tools from the menu beside the message box. Use a model that supports tools.

- **Python calculations** help with numbers, statistics and text processing. Python is on by default and runs in a temporary, isolated space without internet or access to your private app data.
- **Brave Search** lets your model search the web and news. Enable it in Preferences and add a key from the [Brave Search dashboard](https://api-dashboard.search.brave.com/). Searches may count toward your Brave plan’s allowance.
- **Your own integrations** can connect through custom MCP servers under **Preferences → Advanced**. For Flatpak, use an HTTP connection when possible; programs installed on your computer aren’t automatically available inside the app. See the [example configuration](data/mcp.example.json).

![Web search sources and a Python calculation shown in Lumen](docs/screenshots/tools.png)

You can expand tool activity to see sources, the code that ran and its results. Only enable tools you trust: your model can use enabled tools without asking each time.

## Make sense of code and equations

Lumen displays highlighted code and readable math right in the conversation. Copy a code block or a full reply, and expand longer code when you want to see more. Equation display can be switched off in Preferences.

![An equation and highlighted Python code in a Lumen reply](docs/screenshots/equations-code.png)

## Make it yours

Lumen follows your desktop’s light or dark appearance and adapts to smaller windows. Preferences let you choose how replies and tools look, show model thinking, change your Ollama connection, and add your own assistant instructions.

**Dark mode and tool preferences**

![Lumen showing a conversation in dark mode](docs/screenshots/chat-dark.png)

![Lumen’s tool preferences](docs/screenshots/preferences.png)

**Handy shortcuts:** Enter sends · Shift+Enter adds a line · Ctrl+N starts a chat · Ctrl+F searches chats · Ctrl+, opens Preferences.

## Your conversations and privacy

Chats, attachments and settings stay on your computer. Your messages and attachments go to the Ollama server you choose; if you use a remote server, they’re sent there. Brave Search sends search queries to Brave. API keys are saved in a private settings file as plain text.

You choose which files to share through the file picker. Lumen doesn’t request access to your entire home folder. **Reset to Default Settings** keeps your chats; **Reset All Data** deletes Lumen’s chats, attachments, keys and settings without removing Ollama or its models.

Lumen saves your data here:

```text
~/.var/app/io.github.ollamagnome.Lumen/data/ollama-gnome/
```

*Screenshots show the real app with sample conversations.*
