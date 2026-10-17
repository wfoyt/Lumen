"""Personalization preferences and the saved-memory manager."""
import copy

from gi.repository import Adw, GLib, Gtk

from .backend import Ollama
from .memory import MAX_MEMORIES, MAX_MEMORY_LENGTH, clean_memory, memory_key


def editor(text, minimum=100):
    view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=16, right_margin=16,
                        top_margin=16, bottom_margin=16)
    view.get_buffer().set_text(text)
    scroll = Gtk.ScrolledWindow(min_content_height=minimum, max_content_height=180,
                                propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER,
                                css_classes=["card", "preferences-editor"])
    scroll.set_child(view)
    return view, scroll


def contents(view):
    buffer = view.get_buffer()
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)


class PersonalizationFields(Gtk.Box):
    """The same profile and memory choices in setup and preferences."""
    def __init__(self, cfg, setup=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        description = ("These details are optional and are saved when you finish setup. You can change them later in Preferences → Personalization."
                       if setup else "Changes save automatically and apply to your next message in every conversation. Turning a field off keeps its text, but stops sharing it with the model.")
        profile = Adw.PreferencesGroup(title="About You", description=description)
        self.append(profile)
        name_group = Adw.PreferencesGroup()
        profile.add(name_group)
        self.name_enabled = Adw.SwitchRow(title="Share Your Name", active=cfg.get("name_enabled", False))
        name_group.add(self.name_enabled)
        self.name = Adw.EntryRow(title="What Should Lumen Call You?", text=cfg.get("user_name", ""))
        self.name_fields = Adw.PreferencesGroup(margin_top=12)
        self.name_fields.add(self.name)
        name_group.add(self.name_fields)
        about_group = Adw.PreferencesGroup(margin_top=20)
        profile.add(about_group)
        self.about_enabled = Adw.SwitchRow(title="Share Details About You", active=cfg.get("about_enabled", False))
        about_group.add(self.about_enabled)
        self.about, about_scroll = editor(cfg.get("user_about", ""))
        self.about_scroll = about_scroll
        self.about_fields = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12)
        self.about_fields.append(about_scroll)
        self.about_fields.append(Gtk.Label(label="What would you like Lumen to know about you? Add your interests, work, goals or response preferences (up to 4,000 characters).", wrap=True, xalign=0, css_classes=["dim-label", "caption"]))
        about_group.add(self.about_fields)
        memory = Adw.PreferencesGroup(title="Memory", description="Saved memories carry useful details between chats. They stay on this computer and are sent to your selected Ollama server when enabled. Turning memory off keeps saved entries.")
        self.memory_group = memory
        self.append(memory)
        self.memory_enabled = Adw.SwitchRow(title="Use Saved Memories", subtitle="Include saved memories in future replies, including new conversations.", active=cfg.get("memory_enabled", True))
        self.automatic = Adw.SwitchRow(title="Automatically Save Memories", subtitle="Remember useful details as you chat, without asking. Already-known details are skipped. Turn this off to stop saving new memories.", active=cfg.get("auto_memory_enabled", True))
        memory.add(self.memory_enabled)
        memory.add(self.automatic)
        for toggle in (self.name_enabled, self.about_enabled, self.memory_enabled):
            toggle.connect("notify::active", self.update_fields)
        self.update_fields()

    def values(self, previous=None):
        # Invalid editor text must never prevent a privacy switch from saving.
        cfg = previous or {}
        name, about = self.name.get_text(), contents(self.about)
        return {"name_enabled": self.name_enabled.get_active(),
                "user_name": name if len(name) <= 200 else cfg.get("user_name", ""),
                "about_enabled": self.about_enabled.get_active(),
                "user_about": about if len(about) <= 4000 else cfg.get("user_about", ""),
                "memory_enabled": self.memory_enabled.get_active(), "auto_memory_enabled": self.automatic.get_active()}

    def validation_errors(self):
        if len(self.name.get_text()) > 200 or len(contents(self.about)) > 4000:
            return ["Name or profile text was not saved. Use at most 200 characters for your name and 4,000 for your profile."]
        return []

    def load(self, cfg):
        self.name_enabled.set_active(cfg.get("name_enabled", False))
        self.name.set_text(cfg.get("user_name", ""))
        self.about_enabled.set_active(cfg.get("about_enabled", False))
        self.about.get_buffer().set_text(cfg.get("user_about", ""))
        self.memory_enabled.set_active(cfg.get("memory_enabled", True))
        self.automatic.set_active(cfg.get("auto_memory_enabled", True))
        self.update_fields()

    def update_fields(self, *_):
        self.name.set_sensitive(self.name_enabled.get_active())
        self.name_fields.set_visible(self.name_enabled.get_active())
        self.about_scroll.set_sensitive(self.about_enabled.get_active())
        self.about_fields.set_visible(self.about_enabled.get_active())
        self.automatic.set_sensitive(self.memory_enabled.get_active())


class PersonalizationPage(Adw.PreferencesPage):
    def __init__(self, preferences):
        super().__init__(title="Personalization", icon_name="avatar-default-symbolic")
        self.preferences = preferences
        self.window = preferences.window
        self.fields = PersonalizationFields(self.window.store.settings)
        fields_group = Adw.PreferencesGroup()
        fields_group.add(self.fields)
        self.add(fields_group)
        for name in ("name_enabled", "name", "name_fields", "about_enabled", "about", "about_fields",
                     "about_scroll", "memory_enabled", "automatic"):
            setattr(self, name, getattr(self.fields, name))
        memory = self.fields.memory_group
        self.status = Gtk.Label(wrap=True, xalign=0, css_classes=["dim-label", "caption"])
        memory.add(self.status)
        test_row = Adw.ActionRow(title="Test Automatic Memory", subtitle="Check that normal conversation creates a memory and repeating it is skipped. Uses fictional details; nothing is saved.")
        self.test = Gtk.Button(label="Test", valign=Gtk.Align.CENTER)
        self.test.connect("clicked", self.test_memory)
        test_row.add_suffix(self.test)
        test_row.set_activatable_widget(self.test)
        memory.add(test_row)
        self.test_result = Gtk.Label(wrap=True, xalign=0)
        memory.add(self.test_result)
        self.saved_group = Adw.PreferencesGroup(title="Saved Memories", description=f"Review what Lumen remembers. Up to {MAX_MEMORIES} entries, {MAX_MEMORY_LENGTH} characters each. Deleting a conversation keeps its memories; delete them here to forget them.")
        self.add(self.saved_group)
        self.memory_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.saved_group.add(self.memory_rows)
        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=12)
        self.add_button = Gtk.Button(label="Add Memory…")
        self.add_button.connect("clicked", lambda *_: self.edit_memory())
        actions.append(self.add_button)
        self.clear_button = Gtk.Button(label="Delete All…", css_classes=["destructive-action"])
        self.clear_button.connect("clicked", self.clear_memories)
        actions.append(self.clear_button)
        self.saved_group.add(actions)
        result = Gtk.Label(wrap=True, xalign=0)
        preferences.result.bind_property("label", result, "label", 2)
        feedback = Adw.PreferencesGroup()
        feedback.add(result)
        self.add(feedback)
        self.snapshot = None
        self.refresh_memories()
        self.poll = GLib.timeout_add(400, self.refresh_memories)

    def connect_changes(self):
        for toggle in (self.name_enabled, self.about_enabled, self.memory_enabled, self.automatic):
            toggle.connect("notify::active", self.preferences.autosave_switch)
        self.name.connect("changed", self.preferences.queue_autosave)
        self.about.get_buffer().connect("changed", self.preferences.queue_autosave)

    def values(self):
        return self.fields.values(self.window.store.settings)

    def validation_errors(self):
        return self.fields.validation_errors()

    def load(self, cfg):
        self.fields.load(cfg)
        self.refresh_memories()

    def refresh_memories(self):
        self.status.set_label(self.window.memory_status)
        memories = self.window.store.memories
        if self.snapshot != memories:
            self.snapshot = copy.deepcopy(memories)
            child = self.memory_rows.get_first_child()
            while child:
                self.memory_rows.remove(child)
                child = self.memory_rows.get_first_child()
            self.saved_group.set_title(f"Saved Memories ({len(memories)}/{MAX_MEMORIES})")
            if not memories:
                self.memory_rows.append(Gtk.Label(label="No saved memories yet. Add one yourself or enable automatic memories.", wrap=True, xalign=0, css_classes=["dim-label"]))
            for item in memories:
                row = Adw.ActionRow(title=item["text"], use_markup=False,
                                    subtitle="Saved automatically" if item.get("source") == "automatic" else "Added by you")
                edit = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text="Edit Memory", valign=Gtk.Align.CENTER, css_classes=["flat"])
                edit.connect("clicked", lambda _, entry=item: self.edit_memory(entry))
                row.add_suffix(edit)
                delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Delete Memory", valign=Gtk.Align.CENTER, css_classes=["flat"])
                delete.connect("clicked", lambda _, identifier=item["id"]: self.delete_memory(identifier))
                row.add_suffix(delete)
                row.add_css_class("card")
                self.memory_rows.append(row)
            self.clear_button.set_sensitive(bool(memories))
            self.add_button.set_sensitive(len(memories) < MAX_MEMORIES)
        return GLib.SOURCE_CONTINUE

    def edit_memory(self, item=None):
        dialog = Adw.AlertDialog(heading="Edit Memory" if item else "Add Memory",
                                 body=f"Save a useful fact or preference about you (up to {MAX_MEMORY_LENGTH} characters).")
        view, scroll = editor(item["text"] if item else "")
        dialog.editor = view
        dialog.set_extra_child(scroll)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        def valid(*_):
            text = contents(view)
            duplicate = any(memory_key(entry["text"]) == memory_key(text) and
                            (not item or entry["id"] != item["id"]) for entry in self.window.store.memories)
            dialog.set_response_enabled("save", bool(text.strip()) and len(" ".join(text.split())) <= MAX_MEMORY_LENGTH and not duplicate)
        view.get_buffer().connect("changed", valid)
        valid()
        def response(_, action):
            if action == "save":
                try:
                    text = clean_memory(contents(view))
                    self.window.cancel_memories()
                    self.window.store.save_memory(text, item["id"] if item else None)
                    self.window.memory_status = "Memory saved. It will be available on your next message when saved memories are enabled."
                    self.refresh_memories()
                except (ValueError, OSError) as exc:
                    self.preferences.result.set_label(str(exc))
        dialog.connect("response", response)
        dialog.present(self.preferences)
        return dialog

    def delete_memory(self, identifier):
        try:
            self.window.cancel_memories()
            self.window.store.delete_memory(identifier)
            self.window.memory_status = "Memory deleted. Past chat messages are unchanged."
            self.refresh_memories()
        except OSError as exc:
            self.preferences.result.set_label(str(exc))

    def clear_memories(self, *_):
        dialog = Adw.AlertDialog(heading="Delete All Saved Memories?", body="Lumen will forget every saved memory. Your profile and conversations will be kept. This cannot be undone.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete All")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        def response(_, action):
            if action == "delete":
                try:
                    self.window.cancel_memories()
                    self.window.store.set_memories([])
                    self.window.memory_status = "All saved memories deleted."
                    self.refresh_memories()
                except OSError as exc:
                    self.preferences.result.set_label(str(exc))
        dialog.connect("response", response)
        dialog.present(self.preferences)
        return dialog

    def test_memory(self, *_):
        self.preferences.flush_autosave()
        cfg = self.window.store.settings
        model = cfg.get("model", "")
        if not model or model not in self.window.model_names:
            self.test_result.set_label("Choose an installed model in the chat window first.")
            return
        async def test():
            backend = Ollama(cfg["url"])
            result = await backend.memory_update(model, "I prefer short replies.", [])
            if not result["save"]:
                raise ValueError("Your model didn't pick up the sample preference automatically. Try another model.")
            sample = [{"id": f"sample-{index}", "text": entry["text"], "source": "automatic"}
                      for index, entry in enumerate(result["save"])]
            repeated = await backend.memory_update(model, "Concise answers suit me best.", sample)
            if repeated["save"] or repeated["forget"]:
                raise ValueError("Your model picked up the preference but didn't skip its paraphrase. Try another model for more reliable memory.")
            return "Automatic memory is working: a normal message was remembered and a repeated preference was skipped. No memories were saved."
        self.preferences.run_test(self.test, test(), self.test_result, "Checking your model's memory extraction…")

    def close(self):
        GLib.source_remove(self.poll)
