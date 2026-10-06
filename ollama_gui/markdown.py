"""Parse Markdown into native-renderable blocks and escaped label markup."""
from html import escape
import re
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

PARSER = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def closing_delimiter(text, start, closing, maximum):
    position = text.find(closing, start, maximum)
    while position >= 0:
        slashes = 0
        before = position - 1
        while before >= 0 and text[before] == "\\":
            slashes += 1
            before -= 1
        if slashes % 2 == 0:
            return position
        position = text.find(closing, position + len(closing), maximum)
    return -1


def math_inline(state, silent):
    start = state.pos
    opening = next((item for item in (r"\(", r"\[", "$$", "$") if state.src.startswith(item, start)), None)
    if opening is None:
        return False
    if opening == "$" and re.match(r"\d+(?:[.,]\d+)*(?:\s|[;,:!?])", state.src[start + 1:state.posMax]):
        return False
    closing = {r"\(": r"\)", r"\[": r"\]"}.get(opening, opening)
    end = closing_delimiter(state.src, start + len(opening), closing, state.posMax)
    if end < 0:
        remainder = state.src[start + len(opening):state.posMax]
        pending_math = opening != "$" or bool(re.match(r"[A-Za-z\\]", remainder))
        if state.env.get("streaming_math") and pending_math:
            if not silent:
                token = state.push("math_pending", "math", 0)
                token.content = state.src[start + len(opening):state.posMax]
                token.markup = opening
            state.pos = state.posMax
            return True
        return False
    content = state.src[start + len(opening):end]
    if not content.strip():
        return False
    if opening == "$" and (content[0].isspace() or content[-1].isspace()
                           or "\n" in content or (end + 1 < state.posMax and state.src[end + 1].isdigit())):
        return False
    if not silent:
        token = state.push("math_inline" if opening in ("$", r"\(") else "math_display", "math", 0)
        token.content = content
        token.markup = opening
    state.pos = end + len(closing)
    return True


def math_block(state, start_line, end_line, silent):
    if state.is_code_block(start_line):
        return False
    start = state.bMarks[start_line] + state.tShift[start_line]
    opening = next((item for item in (r"\[", "$$") if state.src.startswith(item, start)), None)
    if opening is None:
        return False
    closing = r"\]" if opening == r"\[" else "$$"
    end = closing_delimiter(state.src, start + len(opening), closing, state.eMarks[end_line - 1])
    if end < 0:
        if state.env.get("streaming_math"):
            if not silent:
                token = state.push("math_pending", "math", 0)
                token.content = state.src[start:state.eMarks[end_line - 1]]
                token.markup = opening
                token.map = [start_line, end_line]
                state.line = end_line
            return True
        return False
    last_line = start_line
    while last_line + 1 < end_line and state.bMarks[last_line + 1] <= end:
        last_line += 1
    if state.src[end + len(closing):state.eMarks[last_line]].strip():
        return False
    if silent:
        return True
    token = state.push("math_display", "math", 0)
    token.content = state.getLines(start_line, last_line + 1, state.sCount[start_line], False).strip()[len(opening):-len(closing)]
    token.markup = opening
    token.map = [start_line, last_line + 1]
    state.line = last_line + 1
    return True


PARSER.inline.ruler.before("escape", "math", math_inline)
PARSER.block.ruler.before("fence", "math", math_block, {"alt": ["paragraph", "reference", "blockquote"]})


def math_literal(node):
    closing = {r"\(": r"\)", r"\[": r"\]"}.get(node.markup, node.markup)
    return node.markup + node.content + closing


def parse_markdown(text, streaming_math=False):
    return SyntaxTreeNode(PARSER.parse(text, {"streaming_math": streaming_math}))


def safe_link(value):
    try:
        url = urlsplit(value)
        return url.scheme.lower() in ("http", "https", "mailto") and (bool(url.hostname) if url.scheme.lower() != "mailto" else bool(url.path))
    except ValueError:
        return False


def inline_markup(node, math=False):
    kind = node.type
    if kind == "math_pending":
        return "…"
    if kind in ("math_inline", "math_display"):
        if math:
            return f'<math display="{int(kind == "math_display")}" literal="{escape(math_literal(node), quote=True)}">{escape(node.content)}</math>'
        return escape(math_literal(node))
    if kind in ("text", "html_inline"):
        return escape(node.content)
    if kind in ("softbreak", "hardbreak"):
        return "\n"
    if kind == "code_inline":
        return "<tt>" + escape(node.content) + "</tt>"
    content = "".join(inline_markup(child, math) for child in node.children)
    tag = {"strong": "b", "em": "i", "s": "s"}.get(kind)
    if tag:
        return f"<{tag}>{content}</{tag}>"
    if kind in ("link", "image"):
        href = node.attrs.get("href" if kind == "link" else "src", "")
        if kind == "image":
            content = content or escape(node.content or "Image")
            content += " (image)"
        if safe_link(href):
            return f'<a href="{escape(href, quote=True)}">{content}</a>'
    return content
