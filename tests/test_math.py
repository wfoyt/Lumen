from io import BytesIO
import unittest
import xml.etree.ElementTree as ET
from PIL import Image
from ollama_gui.markdown import parse_markdown, inline_markup
from ollama_gui.math_render import equation_png, normalize_latex


def math_nodes(root):
    for child in root.children:
        if child.type in ("math_inline", "math_display"):
            yield child
        yield from math_nodes(child)


class MathTests(unittest.TestCase):
    def test_delimiters_and_markdown_are_preserved(self):
        source = r"**Inline** \(x^2\), $\alpha$, [source](https://example.com) [1]." + "\n\n" + r"\[\frac{1}{2}\]" + "\n\n$$\ns = \\sum_{i=1}^{n} i\n$$\n"
        root = parse_markdown(source)
        self.assertEqual([item.type for item in math_nodes(root)], ["math_inline", "math_inline", "math_display", "math_display"])
        markup = inline_markup(root.children[0], math=True)
        self.assertIn("<b>Inline</b>", markup)
        self.assertIn('<math display="0"', markup)
        self.assertIn("[1]", markup)
        self.assertNotIn(">[1]</a>", markup)
        ET.fromstring("<markup>" + markup + "</markup>")
        self.assertIn(r"\(x^2\)", inline_markup(root.children[0]))

    def test_math_does_not_interpret_currency_code_or_escaped_delimiters(self):
        root = parse_markdown(r"Pay $5 or $10; escaped \\(x\\); code `\(x\)` and `$x$`." + "\n\n```latex\n\\[x^2\\]\n```\n")
        self.assertEqual(list(math_nodes(root)), [])
        self.assertEqual(len(list(math_nodes(parse_markdown("Use $x+1$ and $y$.")))), 2)

    def test_streaming_and_untrusted_math_never_break_markup(self):
        source = r"## Result \(x^2\)" + "\n\n" + r"\[x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}\]" + "\n\n" + r"*\(a < b\)* and \(\text{<script>}\)."
        for length in range(len(source) + 1):
            for streaming in (False, True):
                for node in parse_markdown(source[:length], streaming_math=streaming).children:
                    ET.fromstring("<markup>" + inline_markup(node, math=True) + "</markup>")

    def test_unfinished_streamed_math_is_a_stable_placeholder(self):
        for source in (r"\[\boxed{x =", r"Inline \(\frac{1}{", r"Inline $x^"):
            root = parse_markdown(source, streaming_math=True)
            self.assertIn("…", inline_markup(root.children[-1], math=True))
            self.assertNotIn("…", inline_markup(parse_markdown(source).children[-1], math=True))

    def test_renders_equations_as_transparent_images_without_a_tex_installation(self):
        for source in (r"\boxed{x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}}", r"\int_0^1 x^2\,dx = \frac{1}{3}", r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}", r"\alpha + \beta = \pi", r"\text{Area} = \pi r^2",
                       r"\begin{aligned}a&=b+c\\d&=e\end{aligned}", r"\begin{bmatrix}1&2\\3&4\end{bmatrix}", r"f(x)=\begin{cases}x^2&x>0\\0&x\le 0\end{cases}", r"\overbrace{x+y}^{n}", r"\mathbb{R} \subseteq \mathbb{C}"):
            with self.subTest(source=source):
                png = equation_png(source, True)
                self.assertIsNotNone(png)
                image = Image.open(BytesIO(png))
                self.assertGreater(image.width, 10)
                self.assertGreater(image.height, 10)
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
                self.assertEqual(png, equation_png(source, True))

    def test_unsupported_or_excessive_math_has_a_literal_fallback(self):
        for source in (r"\frac{1}{", r"\input{/etc/passwd}", "x" * 9000, "{" * 33 + "x" + "}" * 33, ""):
            with self.subTest(source=source[:60]):
                self.assertIsNone(equation_png(source))

    def test_aligned_equations_keep_rows_and_alignment(self):
        from latex2mathml.converter import convert
        xml = ET.fromstring(convert(normalize_latex(r"\begin{aligned}x+y&=5\\x-y&=1\end{aligned}")))
        namespace = {"m": "http://www.w3.org/1998/Math/MathML"}
        table = xml.find(".//m:mtable", namespace)
        self.assertIsNotNone(table)
        self.assertEqual(len(table.findall("m:mtr", namespace)), 2)
        self.assertEqual([len(row.findall("m:mtd", namespace)) for row in table], [2, 2])
