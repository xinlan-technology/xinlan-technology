"""Text -> SVG <path> outlines, so the assets render identically on github.com
(an SVG shown via <img> cannot load web fonts there, and system fonts differ per OS).

    d = text_path("Xin (Shane) Lan", font="source-serif-4-600", size=86, x=40, y=100)
    w = measure("Postdoctoral Fellow", font="inter-500", size=16)   # advance width in px

- font: a stem from FONTS, i.e. a file in tools/fonts/*.woff. Latin subset only, no emoji --
  draw icons as shapes instead.
- y is the BASELINE. anchor: "start" | "middle" | "end". tracking: letter-spacing in em.
- Shaped with HarfBuzz, so kerning and ligatures are real.
- Callers should also put the plain text in the SVG <title> and the <img alt>.
"""
import io
import pathlib
from functools import lru_cache

import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

FONT_DIR = pathlib.Path(__file__).resolve().parent / "fonts"
FONTS = sorted(p.stem for p in FONT_DIR.glob("*.woff"))


def num(v: float, prec: int = 1) -> str:
    """Format an SVG number without dropping integer zeros or keeping negative zero."""
    s = f"{v:.{prec}f}"
    if prec:
        s = s.rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


@lru_cache(maxsize=None)
def _load(font):
    path = FONT_DIR / f"{font}.woff"
    if not path.exists():
        raise ValueError(f"unknown font {font!r}; available: {FONTS}")
    tt = TTFont(str(path))
    # HarfBuzz needs raw sfnt bytes, so re-serialize the decompressed font
    buf = io.BytesIO()
    tt.flavor = None
    tt.save(buf)
    data = buf.getvalue()
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
    pen = SVGPathPen(gs, ntos=lambda v: num(v, precision))
    for name, gx, gy in glyphs:
        # font units are y-up; SVG is y-down
        tp = TransformPen(pen, (scale, 0, 0, -scale, x + gx * scale, y - gy * scale))
        gs[name].draw(tp)
    return pen.getCommands()
