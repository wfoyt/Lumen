"""Local LaTeX → MathML → SVG math, without TeX programs or remote assets."""
from functools import lru_cache
import math
import re
import xml.etree.ElementTree as ET


def normalize_latex(source):
    # latex2mathml calls the AMS aligned layout 'split'. Retain alignment
    # markers and row breaks while normalizing compatible environment names.
    aliases = {"aligned": "split", "gather": "matrix", "gather*": "matrix",
               "gathered": "matrix", "equation": "matrix", "equation*": "matrix"}
    return re.sub(r"\\(begin|end)\{([^}]+)\}(?:\[[tbc]\])?",
                  lambda match: "\\" + match[1] + "{" + aliases.get(match[2], match[2]) + "}", source)


@lru_cache(maxsize=128)
def equation_png(source, display=False):
    """Return a transparent equation mask, or None for invalid/incomplete math."""
    if not source.strip() or len(source) > 8192:
        return None
    depth = 0
    for token in re.findall(r"\\.|[{}]", source):
        depth += (token == "{") - (token == "}")
        if depth > 32 or depth < 0:
            return None
    if depth:
        return None
    try:
        from latex2mathml.converter import convert
        from ziamath import Math
        from cairosvg import svg2png
        mathml = ET.fromstring(convert(normalize_latex(source), display="block" if display else "inline"))
        for node in mathml.iter():
            # The converter emits unknown commands literally. Keep their
            # original source rather than drawing a misleading equation.
            if node.text and re.search(r"\\[A-Za-z]+", node.text):
                return None
            for key in ("mathcolor", "mathbackground"):
                node.attrib.pop(key, None)
        mathml.set("mathcolor", "white")
        rendered = Math(mathml, size=21 if display else 17, margin=2)
        width, height = rendered.getsize()
        if not math.isfinite(width + height) or width <= 0 or height <= 0 or width > 8000 or height > 2000 or width * height > 1_000_000:
            return None
        svg = rendered.svgxml()
        for node in svg.iter():
            for key, value in node.attrib.items():
                if key.endswith("href") and not value.startswith("#"):
                    return None
        return svg2png(bytestring=ET.tostring(svg), scale=2)
    except Exception:
        # Malformed model output is data; show it literally, never break a turn.
        return None
