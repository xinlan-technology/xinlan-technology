"""Text -> SVG <path> outlines, so SVG assets render identically on github.com
(an SVG shown via <img> cannot load web fonts reliably there, and system fonts differ per OS).

Run scripts that import this with:  design/tools/.venv/bin/python your_script.py

    import sys; sys.path.insert(0, "<abs path to design/tools>")
    from svgtext import text_path, measure, FONTS

    d = text_path("Xin (Shane) Lan", font="inter-700", size=48, x=40, y=100, anchor="start", tracking=-0.01)
    svg += f'<path d="{d}" fill="#0b1f33"/>'
    w = measure("Postdoctoral Fellow", font="inter-500", size=16)   # width in px

- font: a stem from FONTS (files in tools/fonts/*.woff): e.g. inter-400..800, fraunces-400/600/700,
  fraunces-400-italic, instrument-serif-400, instrument-serif-400-italic, dm-serif-display-400,
  jetbrains-mono-400/500/700, space-grotesk-400/500/700, ibm-plex-sans-400/600.
  Latin subset only (no CJK). Emoji are not available -- draw icons as shapes instead.
- y is the text BASELINE. anchor: "start" | "middle" | "end". tracking: letter-spacing in em (e.g. 0.12 for small caps labels).
- Shaped with HarfBuzz (real kerning + ligatures).
- Always also put the plain text in the SVG's <title>/aria-label and the <img alt> for accessibility.
"""
import pathlib
from functools import lru_cache

import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

FONT_DIR = pathlib.Path(__file__).resolve().parent / "fonts"
FONTS = sorted(p.stem for p in FONT_DIR.glob("*.woff"))


@lru_cache(maxsize=None)
def _load(font):
    path = FONT_DIR / f"{font}.woff"
    if not path.exists():
        raise ValueError(f"unknown font {font!r}; available: {FONTS}")
    tt = TTFont(str(path))
    # HarfBuzz needs raw sfnt bytes, so re-serialize the decompressed font
    import io
    buf = io.BytesIO()
    tt.flavor = None
    tt.save(buf)
    data = buf.getvalue()
    tt = TTFont(io.BytesIO(data))
    face = hb.Face(data)
    hbfont = hb.Font(face)
    upem = face.upem
    return tt, hbfont, upem, tt.getGlyphSet()


def _shape(text, font, size, tracking):
    tt, hbfont, upem, gs = _load(font)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": True})
    order = tt.getGlyphOrder()
    scale = size / upem
    glyphs, pen_x = [], 0.0
    track = tracking * upem
    n = len(buf.glyph_infos)
    for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
        glyphs.append((order[info.codepoint], pen_x + pos.x_offset, pos.y_offset))
        pen_x += pos.x_advance + (track if i < n - 1 else 0)
    return glyphs, pen_x * scale, scale, gs


def measure(text, font="inter-400", size=16, tracking=0.0):
    """Advance width of `text` in px."""
    return _shape(text, font, size, tracking)[1]


def text_path(text, font="inter-400", size=16, x=0.0, y=0.0, anchor="start", tracking=0.0, precision=2):
    """Return the SVG path `d` string for `text` with its baseline at (x, y)."""
    glyphs, width, scale, gs = _shape(text, font, size, tracking)
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    pen = SVGPathPen(gs, ntos=lambda v: (f"{v:.{precision}f}").rstrip("0").rstrip("."))
    for name, gx, gy in glyphs:
        # font units are y-up; SVG is y-down
        tp = TransformPen(pen, (scale, 0, 0, -scale, x + gx * scale, y - gy * scale))
        gs[name].draw(tp)
    return pen.getCommands()
