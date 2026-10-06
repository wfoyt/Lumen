import unittest
import xml.etree.ElementTree as ET

from ollama_gui.markdown import parse_markdown, inline_markup, safe_link


class MarkdownTests(unittest.TestCase):
    def test_headings_emphasis_lists_and_code(self):
        root = parse_markdown("## Releases\n\n**Stable** and *supported* with `code`.\n\n3. First\n4. Second\n\n```python\nprint('<tag>')\n```\n")
        self.assertEqual([node.type for node in root.children], ["heading", "paragraph", "ordered_list", "fence"])
        self.assertEqual(root.children[0].tag, "h2")
        markup = inline_markup(root.children[1])
        self.assertIn("<b>Stable</b>", markup)
        self.assertIn("<i>supported</i>", markup)
        self.assertIn("<tt>code</tt>", markup)
        self.assertEqual(root.children[2].attrs["start"], 3)
        self.assertEqual(root.children[3].content, "print('<tag>')\n")

    def test_nested_lists_quotes_table_and_strikethrough(self):
        root = parse_markdown("- Outer\n  - Inner\n\n> A quote\n\n| Name | Value |\n|---|---|\n| Test | ~~old~~ |\n")
        self.assertEqual(root.children[0].children[0].children[1].type, "bullet_list")
        self.assertEqual(root.children[1].type, "blockquote")
        table = root.children[2]
        self.assertEqual(table.type, "table")
        self.assertIn("<s>old</s>", inline_markup(table.children[1].children[0].children[1]))

    def test_links_and_untrusted_markup(self):
        root = parse_markdown('A <b>literal tag</b> & [source](https://example.com/?a=1&b=2) and [bad](file:///etc/passwd).')
        markup = inline_markup(root.children[0])
        self.assertIn("&lt;b&gt;literal tag&lt;/b&gt;", markup)
        self.assertIn('href="https://example.com/?a=1&amp;b=2"', markup)
        self.assertNotIn('href="file:', markup)
        ET.fromstring("<markup>" + markup + "</markup>")
        for link in ("file:///tmp/file", "javascript:alert(1)", "data:text/html,test", "//example.com", "https://[invalid"):
            self.assertFalse(safe_link(link))

    def test_every_stream_prefix_is_parseable(self):
        source = '## Title\n\n**bold & <literal>** [link](https://example.com)\n\n```python\nprint("hi")\n```\n'
        for length in range(len(source) + 1):
            root = parse_markdown(source[:length])
            for block in root.children:
                if block.type in ("heading", "paragraph"):
                    ET.fromstring("<markup>" + inline_markup(block) + "</markup>")
