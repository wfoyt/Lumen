"""Saved conversation branches for edits and regenerated replies."""
import copy


def checkpoint(chat):
    if "branches" in chat:
        chat["branches"][chat.get("branch_index", 0)]["messages"] = copy.deepcopy(chat["messages"])


def fork(chat, user_index, replacement=None, model=""):
    """Keep the complete old continuation before starting an alternate turn."""
    if "branches" not in chat:
        chat["branches"] = [{"messages": copy.deepcopy(chat["messages"]), "parent": None, "fork": None}]
        chat["branch_index"] = 0
    checkpoint(chat)
    parent = chat["branch_index"]
    messages = copy.deepcopy(chat["messages"][:user_index + 1])
    if replacement is not None:
        messages[user_index] = copy.deepcopy(replacement)
    branch = {"messages": copy.deepcopy(messages), "parent": parent, "fork": user_index, "model": model}
    chat["branches"].append(branch)
    chat["branch_index"] = len(chat["branches"]) - 1
    chat["messages"] = messages
    return parent


def select(chat, index):
    checkpoint(chat)
    chat["messages"] = copy.deepcopy(chat["branches"][index]["messages"])
    chat["branch_index"] = index


def choices(chat, user_index):
    """Only offer versions with the same preceding conversation context."""
    checkpoint(chat)
    prefix = chat["messages"][:user_index]
    choices = []
    for index, branch in enumerate(chat.get("branches", [])):
        if branch.get("status") == "failed":
            continue
        messages = branch["messages"]
        if len(messages) <= user_index or messages[user_index]["role"] != "user" or messages[:user_index] != prefix:
            continue
        # Shared earlier turns are one version until they have a distinct
        # user message or response, even when later turns have branches.
        end = next((i for i in range(user_index + 1, len(messages)) if messages[i]["role"] == "user"), len(messages))
        turn = messages[user_index:end]
        duplicate = next((i for i, (_, candidate) in enumerate(choices) if candidate == turn), None)
        if duplicate is None:
            choices.append((index, turn))
        elif index == chat.get("branch_index", 0):
            choices[duplicate] = (index, turn)
    return [index for index, _ in choices]


def edited_message(message, text):
    replacement = copy.deepcopy(message)
    previous = message.get("display_content", message["content"])
    suffix = message["content"][len(previous):] if message["content"].startswith(previous) else ""
    replacement["content"] = text + suffix
    if "display_content" in message:
        replacement["display_content"] = text
    return replacement
