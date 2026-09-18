#!/usr/bin/env python3
"""
Great Lakes Cartography -- generator for the profile README and its artwork.

    python .readme-source/build.py          # needs fonttools, uharfbuzz, numpy

Rewrites every SVG in assets/ (a light and a dark variant of each), assets/manifest.json and README.md.
The README is generated too, so its image widths always match the assets it shows.

All text is outlined with tools/svgtext.py, so the SVGs carry no font dependency; each glyph is defined
once per file and placed with <use>.

Nothing here is eyeballed. Every layout rule the design leans on is an assertion, so a copy edit that
breaks the page fails the build instead of shipping: boxes stay inside their container and off each other
(Canvas.check), text stays legible at the size it is displayed at and holds 4.5:1 against every background
it can land on (Canvas.write, check_colors), lake names sit in their own lake, the hero's callouts and
scale bar stay dry and clear of the map furniture, the four featured cards are set to one density
(check_repo_density), and every panel's copy fits its column. main() prints the numbers behind the checks.
"""
from __future__ import annotations

import html
import datetime
import json
import math
import pathlib
import sys

import numpy as np
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = HERE / "tools"
sys.path.insert(0, str(TOOLS))
import svgtext  # noqa: E402
from svgtext import measure, text_path  # noqa: E402

# when this script lives in <repo>/.readme-source, it writes the README and assets to the repo root
OUT = HERE.parent if HERE.name == ".readme-source" else HERE
ASSETS = OUT / "assets"
RAW = "https://raw.githubusercontent.com/xinlan-technology/xinlan-technology/main/assets/"
MANIFEST: list[dict] = []
DESKTOP_W, PHONE_W = 846, 340

# Source Serif runs wide and short in the cap, so the serif sizes below are far smaller than the sans
# sizes they sit beside; the two scales are not interchangeable.
SERIF, SERIF_I = "source-serif-4-600", "source-serif-4-400-italic"
SANS, SANS_M, SANS_SB = "inter-400", "inter-500", "inter-600"
MONO, MONO_M = "jetbrains-mono-400", "jetbrains-mono-500"

# ----------------------------------------------------------------------------- palette
# card = colour used behind card content (and for small knock-outs); card_fill = what the card rectangle is
# actually filled with. Dark cards are outline-only so they sit equally well on GitHub dark and dark dimmed.
THEMES = {
    "light": dict(
        paper="#f6f9f9", card="#fbfcfc", card_fill="#fbfcfc", rule="#d5dfe2", grat="#d0dce0", tick="#b9c8cd",
        ink="#0e2a3b", text="#2f4757", muted="#566b79", teal="#1d6873",
        shore="#d0e6eb", deep="#1c6674", deep_op=0.085, contour="#2f7f8a", contour_op=0.55,
        coast="#3f8792", lakelabel="#18495a", amber="#b8731c", amber_t="#8f560b",
        halo="#f6f9f9", chip="#ffffff", chip_fill="#ffffff", tile="#f6f9f9", warm="#e7c79a", cold="#9cc7cf",
        heat=("#e9f0f1", "#c3e0e5", "#8ac9d1", "#409aa4", "#1d6873"), heat_edge="#d5dfe2",
        pages=("#ffffff",),
    ),
    "dark": dict(
        paper="#0f1720", card="#0f161e", card_fill="none", rule="#26343f", grat="#1a2732", tick="#34454f",
        ink="#e8eff1", text="#b9c7cf", muted="#8b9daa", teal="#6cc3c7",
        shore="#112f39", deep="#58b9c2", deep_op=0.075, contour="#86d3d7", contour_op=0.35,
        coast="#5fb3bb", lakelabel="#c3e8ea", amber="#e6a64e", amber_t="#ebb567",
        halo="#0f1720", chip="#0d1117", chip_fill="none", tile="none", warm="#8a6a3c", cold="#2d6570",
        heat=("#152029", "#1b4952", "#2a828c", "#46aeb6", "#7fd9de"), heat_edge="#26343f",
        pages=("#0d1117", "#212830"),   # GitHub dark, GitHub dark dimmed
    ),
}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def num(v: float, prec: int = 1) -> str:
    s = f"{v:.{prec}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ----------------------------------------------------------------------------- text metrics
_BOUNDS: dict = {}


def _glyph_bounds(font, name):
    key = (font, name)
    if key not in _BOUNDS:
        gs = svgtext._load(font)[3]
        bp = BoundsPen(gs)
        gs[name].draw(bp)
        _BOUNDS[key] = bp.bounds
    return _BOUNDS[key]


def ink_box(text, font, size, x, y, anchor="start", tracking=0.0):
    """Exact ink box (x0, y0, x1, y1) of outlined text set at (x, y). Tighter than the advance width,
    which is what the clearance and collision checks want: they measure marks, not slugs."""
    glyphs, width, scale, _ = svgtext._shape(text, font, size, tracking)
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    xs, ys = [], []
    for name, gx, gy in glyphs:
        assert name != ".notdef", f"font {font} has no glyph for a character in {text!r}"
        b = _glyph_bounds(font, name)
        if b is None:       # a blank glyph (space) carries no ink
            continue
        xs += [x + (gx + b[0]) * scale, x + (gx + b[2]) * scale]
        ys += [y - (gy + b[3]) * scale, y - (gy + b[1]) * scale]
    return (min(xs), min(ys), max(xs), max(ys))


def cap_h(font, size):
    """Cap height: the ink above the baseline of a capital H, used to centre text on a given line."""
    return -ink_box("H", font, size, 0, 0)[1]


SEP = " · "
_GLUE, _DOT = "⁠", "⁠·"     # internal markers only; never rendered


def _tokens(text):
    """Break opportunities. In a ' · ' list every item is one unbreakable unit and a line may only end after
    a separator (the separator is then dropped); '~' is a hand-placed non-breaking space."""
    text = text.replace("~", _GLUE)
    if SEP not in text:
        return text.split(" ")
    items = text.split(SEP)
    return [it.replace(" ", _GLUE) + (_DOT if i < len(items) - 1 else "") for i, it in enumerate(items)]


def _fin(line):
    """Rendered form of a line: a separator at the line end is dropped, glue becomes a space."""
    if line.endswith(_DOT):
        line = line[: -len(_DOT)]
    return line.replace(_DOT, " ·").replace(_GLUE, " ")


def _greedy(tokens, font, size, maxw):
    """Fit tokens into lines of at most maxw; None if a single token is already too wide."""
    lines, cur = [], ""
    for w in tokens:
        t = f"{cur} {w}".strip()
        if measure(_fin(t), font, size) <= maxw:
            cur = t
        else:
            if not cur:
                return None
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _wrap_tokens(toks, font, size, maxw, balance=True):
    """Break a token list (see _tokens) into rendered lines, keeping glue and list items intact.
    Balancing re-runs the greedy fit against ever narrower measures, binary-searching the narrowest one
    that still needs no extra line."""
    lines = _greedy(toks, font, size, maxw)
    assert lines is not None, f"a word/item of {_fin(' '.join(toks))!r} is wider than {maxw}px"
    if balance and len(lines) > 1:
        lo, hi = 0.0, float(maxw)
        for _ in range(24):
            mid = (lo + hi) / 2
            trial = _greedy(toks, font, size, mid)
            if trial is not None and len(trial) <= len(lines):
                hi = mid
            else:
                lo = mid
        lines = _greedy(toks, font, size, hi)
    return [_fin(ln) for ln in lines]


def wrap(text, font, size, maxw, max_lines=None, balance=True):
    """Greedy line breaking; with balance=True the lines are set evenly rather than as a full line followed
    by an orphan. '\\n' forces a break. Wrapped copy is never tracked -- tracking is for single lines."""
    out = []
    for part in text.split("\n"):
        out += _wrap_tokens(_tokens(part), font, size, maxw, balance)
    if max_lines:
        assert len(out) <= max_lines, f"{text!r} needs {len(out)} lines (> {max_lines})"
    return out


def plain(text):
    """Text as it reads in alt/desc (hand-placed breaks and glue removed)."""
    return text.replace("\n", " ").replace("~", " ")


def inside(b, c, pad=0.0):
    e = 1e-6      # tolerance: boxes are meant to sit flush with their container, not fail on rounding
    return b[0] >= c[0] + pad - e and b[1] >= c[1] + pad - e and b[2] <= c[2] - pad + e and b[3] <= c[3] - pad + e


def overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def union(*bs):
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def ink_since(c, mark):
    """Ink box of everything added to `c` since `mark = len(c.boxes)` -- one drawn block, measured."""
    return union(*[b["box"] for b in c.boxes[mark:]])


def fb(b):
    return "(" + ", ".join(f"{v:.1f}" for v in b) + ")"


# ----------------------------------------------------------------------------- canvas
class Canvas:
    """One SVG under construction, in its own unit grid, plus the bookkeeping that proves it.

    Every mark that must not be collided with is registered as a box -- text does this itself, shapes call
    reserve -- so check() can verify the layout before write() emits the file. display_frac is the fraction
    of the 846 px desktop column the asset is shown at: what turns unit sizes into real pixels.
    """

    def __init__(self, name, w, h, title, desc, T, display_frac):
        self.name, self.w, self.h, self.title, self.desc, self.T = name, w, h, title, desc, T
        self.display_frac = display_frac
        self.defs: list[str] = []
        self.els: list[str] = []
        self.boxes: list[dict] = []
        self.sizes: list[float] = []
        self.style = ""
        self.gids: dict = {}

    def add(self, s):
        self.els.append(s)

    def glyph(self, font, size, name, gs, scale):
        """Each outlined glyph (font, size) is defined once in <defs> and placed with <use>."""
        k = (font, round(size, 3), name)
        if k not in self.gids:
            pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
            gs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, 0, 0)))
            d = pen.getCommands()
            gid = f"q{len(self.gids)}" if d else None
            if gid:
                self.defs.append(f'<path id="{gid}" d="{d}"/>')
            self.gids[k] = gid
        return self.gids[k]

    def text(self, s, font, size, x, y, fill, anchor="start", tracking=0.0, within=None,
             key=None, collide=True, gap=2.0):
        glyphs, width, scale, gs = svgtext._shape(s, font, size, tracking)
        gx0 = x - (width / 2 if anchor == "middle" else width if anchor == "end" else 0)
        uses = []
        for name, gx, gy in glyphs:
            gid = self.glyph(font, size, name, gs, scale)
            if gid:
                uses.append(f'<use href="#{gid}" x="{num(gx0 + gx * scale, 2)}" y="{num(y - gy * scale, 2)}"/>')
        box = ink_box(s, font, size, x, y, anchor, tracking)
        self.els.append(f'<g fill="{fill}">{"".join(uses)}</g>')
        self.sizes.append(size)
        self.boxes.append(dict(key=key or s, box=box, within=within, collide=collide, gap=gap))
        return box

    def runs(self, pieces, x, y, size, tracking=0.0, anchor="start", within=None, key=None, gap=2.0):
        """Several differently styled pieces on one baseline. pieces = [(text, font, fill), ...]."""
        widths = [measure(t, f, size, tracking) for t, f, _ in pieces]
        total = sum(widths) + tracking * size * (len(pieces) - 1)
        if anchor == "middle":
            x -= total / 2
        elif anchor == "end":
            x -= total
        boxes, cx = [], x
        for (t, f, fill), w in zip(pieces, widths):
            boxes.append(self.text(t, f, size, cx, y, fill, tracking=tracking, within=within, collide=False))
            cx += w + tracking * size
        box = union(*boxes)
        self.reserve(key or "".join(p[0] for p in pieces), box, within=within, gap=gap)
        return box, total

    def reserve(self, key, box, within=None, gap=2.0):
        self.boxes.append(dict(key=key, box=box, within=within, collide=True, gap=gap))

    def check(self):
        """Every box sits inside its container, and no two collidable boxes touch (the pair's smaller gap
        wins, so one lenient box cannot loosen a strict neighbour)."""
        frame = (0, 0, self.w, self.h)
        for b in self.boxes:
            c = b["within"] or frame
            assert inside(b["box"], c), f"{self.name}: {b['key']!r} {fb(b['box'])} escapes {fb(c)}"
        cs = [b for b in self.boxes if b["collide"]]
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                g = min(cs[i]["gap"], cs[j]["gap"])
                assert not overlap(cs[i]["box"], cs[j]["box"], g), \
                    f"{self.name}: {cs[i]['key']!r} {fb(cs[i]['box'])} collides with {cs[j]['key']!r} {fb(cs[j]['box'])}"

    def write(self, theme):
        self.check()
        fname = f"{self.name}-{theme}.svg"
        style = f"<style>{self.style}</style>" if self.style else ""
        defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {num(self.w)} {num(self.h)}" '
               f'width="{num(self.w)}" height="{num(self.h)}" role="img" aria-labelledby="t d">'
               f'<title id="t">{esc(self.title)}</title><desc id="d">{esc(self.desc)}</desc>'
               f'{style}{defs}{"".join(self.els)}</svg>\n')
        ASSETS.mkdir(exist_ok=True)
        (ASSETS / fname).write_text(svg)
        # px per unit once the asset is placed on the page: the SVG scales, so type size is a page property
        k = self.display_frac / self.w * min(self.sizes)
        assert k * DESKTOP_W >= 11, f"{fname}: smallest text {k * DESKTOP_W:.1f}px on desktop"
        assert k * PHONE_W >= 6, f"{fname}: smallest text {k * PHONE_W:.1f}px on phones"
        MANIFEST.append(dict(file=fname, viewbox_w=self.w, min_font=min(self.sizes),
                             display_frac=round(self.display_frac, 4)))
        return fname


# ----------------------------------------------------------------------------- page geometry
# Side-by-side cards are 49% wide with one space between them, so a pair spans ~833.5 of 846 px and its
# outer stroked edges sit ~6.8 px inside the column. Full-width panels inset their card by the same amount
# (6.5 units = 6.74 px) so every card edge on the page lines up.
CARD_W, PANEL_W = 400, 816           # 49%-wide cards and full-width panels -> 1 unit ~ 1.04 px on desktop
PANEL_INSET = 6.0
PANEL_L, PANEL_R = 38, PANEL_W - 38  # content edges inside a full-width panel (31.5 units from its stroke)
CARD_L, CARD_R = 32, CARD_W - 32     # content edges inside a 400-unit card (31.5 units from its stroke)


def card_bg(c, T, inset=0.0):
    c.add(f'<rect x="{num(inset + 0.5, 2)}" y="0.5" width="{num(c.w - 2 * inset - 1, 2)}" height="{num(c.h - 1)}" rx="14" '
          f'fill="{T["card_fill"]}" stroke="{T["rule"]}"/>')


def panel_bg(c, T):
    card_bg(c, T, inset=PANEL_INSET)


def panel_inner(H):
    """Content box inside a full-width panel: every text box in a panel must sit within it."""
    return (PANEL_INSET + 14, 12, PANEL_W - PANEL_INSET - 14, H - 8)


def hline(c, x0, x1, y, color, w=1.0):
    c.add(f'<path d="M{num(x0)} {num(y)}H{num(x1)}" stroke="{color}" stroke-width="{num(w, 2)}" fill="none"/>')


# ----------------------------------------------------------------------------- geography
GEO = json.loads((TOOLS / "data" / "great_lakes.geojson").read_text())
_RAW = {f["properties"]["name"]: f["geometry"]["coordinates"] for f in GEO["features"]}
# In this dataset "Georgian Bay" is already part of the "Lake Huron" polygon (it shares ~95% of its
# vertices), so the duplicate feature is dropped; otherwise its seam would show up as a false shoreline.
_huron = {tuple(p) for p in _RAW["Lake Huron"][0]}
assert sum(tuple(p) in _huron for p in _RAW["Georgian Bay"][0]) > 0.9 * len(_RAW["Georgian Bay"][0])
LAKES = {k.replace("Lake ", ""): v for k, v in _RAW.items() if k != "Georgian Bay"}

# California state outline (Natural Earth 50m, lon/lat): one 252-point ring, used by the
# water_system_consolidation card.
_CA = json.loads((TOOLS / "data" / "california.geojson").read_text())
CALIFORNIA = np.asarray(_CA["geometry"]["coordinates"][0], float)
assert _CA["properties"]["name"] == "California" and len(_CA["geometry"]["coordinates"]) == 1

EAST_LANSING = (-84.48, 42.73)   # Michigan State University (CSIS)
ANN_ARBOR = (-83.74, 42.28)      # University of Michigan (CIGLR)

# Lambert conformal conic (sphere), standard parallels 42.5 N / 47.5 N, central meridian 84 W
_P1, _P2, _P0, _L0 = map(math.radians, (42.5, 47.5, 45.0, -84.0))
_N = math.log(math.cos(_P1) / math.cos(_P2)) / math.log(
    math.tan(math.pi / 4 + _P2 / 2) / math.tan(math.pi / 4 + _P1 / 2))
_F = math.cos(_P1) * math.tan(math.pi / 4 + _P1 / 2) ** _N / _N
_RHO0 = _F / math.tan(math.pi / 4 + _P0 / 2) ** _N


def lcc(lon, lat):
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    rho = _F / np.tan(np.pi / 4 + np.radians(lat) / 2) ** _N
    th = _N * (np.radians(lon) - _L0)
    return rho * np.sin(th), -(_RHO0 - rho * np.cos(th))   # y grows downward (SVG)


def lcc_k(lat):
    """Map scale factor of the projection at a latitude."""
    phi = math.radians(lat)
    rho = _F / math.tan(math.pi / 4 + phi / 2) ** _N
    return _N * rho / math.cos(phi)


def flat(lat0):
    """Equirectangular projection true at lat0 -- used where the Great Lakes conic does not apply
    (California sits 36 deg off its central meridian, which would visibly rotate the state)."""
    k = math.cos(math.radians(lat0))

    def proj(lon, lat):
        return k * np.asarray(lon, float), -np.asarray(lat, float)
    return proj


class View:
    def __init__(self, s, ox, oy, proj=lcc):
        self.s, self.ox, self.oy, self.proj = s, ox, oy, proj

    def __call__(self, lon, lat):
        x, y = self.proj(lon, lat)
        return self.ox + self.s * x, self.oy + self.s * y

    def pt(self, lonlat):
        x, y = self(*lonlat)
        return float(x), float(y)

    @classmethod
    def fit(cls, lonlat: np.ndarray, box, proj=lcc):
        """Scale and centre a lon/lat ring inside `box`."""
        x, y = proj(lonlat[:, 0], lonlat[:, 1])
        bw, bh = box[2] - box[0], box[3] - box[1]
        s = min(bw / (x.max() - x.min()), bh / (y.max() - y.min()))
        ox = box[0] + (bw - s * (x.max() - x.min())) / 2 - s * x.min()
        oy = box[1] + (bh - s * (y.max() - y.min())) / 2 - s * y.min()
        return cls(s, ox, oy, proj)


def dp(pts, eps):
    """Douglas-Peucker simplification (iterative)."""
    n = len(pts)
    if n < 3:
        return pts
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        seg = pts[b] - pts[a]
        L = math.hypot(*seg)
        rel = pts[a + 1:b] - pts[a]
        d = np.hypot(rel[:, 0], rel[:, 1]) if L < 1e-9 else np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / L
        i = int(np.argmax(d))
        if d[i] > eps:
            m = a + 1 + i
            keep[m] = True
            stack += [(a, m), (m, b)]
    return pts[keep]


def ring_area_deg(r):
    a = np.asarray(r)
    return 0.5 * abs(np.dot(a[:-1, 0], a[1:, 1]) - np.dot(a[1:, 0], a[:-1, 1]))


def lake_rings(view, eps, hole_min=0.015, names=None):
    """{lake: [ring px arrays]} (first ring = shore, rest = islands above hole_min deg^2)."""
    out = {}
    for name, poly in LAKES.items():
        if names and name not in names:
            continue
        rings = []
        for i, r in enumerate(poly):
            if i > 0 and (hole_min is None or ring_area_deg(r) < hole_min):
                continue
            a = np.asarray(r, float)
            X, Y = view(a[:, 0], a[:, 1])
            p = dp(np.column_stack([X, Y]), eps)
            if len(p) >= 5:
                rings.append(p)
        out[name] = rings
    return out


def rings_d(lakes, prec=1):
    parts = []
    for rings in lakes.values():
        for r in rings:
            pts = r[:-1] if np.allclose(r[0], r[-1]) else r
            parts.append("M" + " ".join(f"{num(x, prec)} {num(y, prec)}" for x, y in pts) + "Z")
    return "".join(parts)


def lakes_bbox(lakes):
    allp = np.vstack([r for rings in lakes.values() for r in rings])
    return (*allp.min(0), *allp.max(0))


def _pip(pts, ring):
    x, y = pts[:, 0:1], pts[:, 1:2]
    x1, y1 = ring[None, :, 0], ring[None, :, 1]
    x2, y2 = np.roll(ring[:, 0], -1)[None], np.roll(ring[:, 1], -1)[None]
    dy = np.where(y2 == y1, 1e-12, y2 - y1)
    cond = ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / dy + x1)
    return cond.sum(1) % 2 == 1


def in_water(pts, lakes):
    pts = np.asarray(pts, float)
    res = np.zeros(len(pts), bool)
    for rings in lakes.values():
        acc = np.zeros(len(pts), bool)
        for r in rings:
            acc ^= _pip(pts, r)
        res |= acc
    return res


def shore_dist(pts, lakes):
    pts = np.asarray(pts, float)
    best = np.full(len(pts), np.inf)
    for rings in lakes.values():
        for a in rings:
            b = np.roll(a, -1, axis=0)
            ab = b - a
            L2 = (ab ** 2).sum(1)
            L2[L2 == 0] = 1e-12
            ap = pts[:, None, :] - a[None]
            t = np.clip((ap * ab[None]).sum(2) / L2[None], 0, 1)
            proj = a[None] + t[..., None] * ab[None]
            d = np.hypot(pts[:, None, 0] - proj[..., 0], pts[:, None, 1] - proj[..., 1])
            best = np.minimum(best, d.min(1))
    return best


def sample_box(box, step=1.5):
    xs = np.arange(box[0], box[2] + 1e-9, step)
    ys = np.arange(box[1], box[3] + 1e-9, step)
    gx, gy = np.meshgrid(np.append(xs, box[2]), np.append(ys, box[3]))
    return np.column_stack([gx.ravel(), gy.ravel()])


def sample_poly(poly, step=1.0, close=True):
    out = []
    ends = np.roll(poly, -1, axis=0)
    pairs = list(zip(poly, ends)) if close else list(zip(poly[:-1], poly[1:]))
    for a, b in pairs:
        n = max(1, int(math.hypot(*(b - a)) / step))
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        out.append(a + t * (b - a))
    return np.vstack(out)


def draw_lakes(c, lakes, T, idp, levels=(), coast_w=1.0, knockouts=(), line_w=0.8, prec=1):
    """Lake fill + stepped 'bathymetry' tints and contour lines as inward offsets of the shoreline.
    An offset at distance d is the edge of (lake minus a 2d-wide stroke of its shoreline), built with masks."""
    d = rings_d(lakes, prec)
    bx = lakes_bbox(lakes)
    mx = f'x="{num(bx[0] - 4)}" y="{num(bx[1] - 4)}" width="{num(bx[2] - bx[0] + 8)}" height="{num(bx[3] - bx[1] + 8)}"'
    c.defs.append(f'<path id="{idp}" d="{d}" fill-rule="evenodd" clip-rule="evenodd"/>')
    c.add(f'<use href="#{idp}" fill="{T["shore"]}"/>')
    if levels:
        c.defs.append(f'<clipPath id="{idp}c"><use href="#{idp}"/></clipPath>')
        for i, lv in enumerate(levels):
            c.defs.append(
                f'<mask id="{idp}m{i}" maskUnits="userSpaceOnUse" {mx}><use href="#{idp}" fill="#fff"/>'
                f'<use href="#{idp}" fill="none" stroke="#000" stroke-width="{num(2 * lv, 2)}" stroke-linejoin="round"/></mask>')
            c.add(f'<rect {mx} fill="{T["deep"]}" opacity="{T["deep_op"]}" mask="url(#{idp}m{i})"/>')
        rings = []
        for lv in sorted(levels, reverse=True):
            rings.append(f'<use href="#{idp}" fill="none" stroke="#fff" stroke-width="{num(2 * lv + line_w, 2)}" stroke-linejoin="round"/>'
                         f'<use href="#{idp}" fill="none" stroke="#000" stroke-width="{num(2 * lv - line_w, 2)}" stroke-linejoin="round"/>')
        rings += knockouts
        c.defs.append(f'<mask id="{idp}l" maskUnits="userSpaceOnUse" {mx}>{"".join(rings)}</mask>')
        c.add(f'<g clip-path="url(#{idp}c)"><rect {mx} fill="{T["contour"]}" opacity="{T["contour_op"]}" mask="url(#{idp}l)"/></g>')
    c.add(f'<use href="#{idp}" fill="none" stroke="{T["coast"]}" stroke-width="{num(coast_w, 2)}" stroke-linejoin="round"/>')


def mini_map(c, T, box, idp, highlight=None, both=True):
    """Small locator map of the lakes (no islands); `both` also rings the appointment that is not
    highlighted. Returns the view, so the caller can place its own marks."""
    pts = np.vstack([np.asarray(p[0]) for p in LAKES.values()])
    view = View.fit(pts, box)
    draw_lakes(c, lake_rings(view, 0.3, hole_min=None), T, idp, coast_w=0.6)
    if both:
        for loc in (EAST_LANSING, ANN_ARBOR):
            if loc == highlight:
                continue
            x, y = view.pt(loc)
            c.add(f'<circle cx="{num(x)}" cy="{num(y)}" r="1.9" fill="none" stroke="{T["amber"]}" stroke-width="1"/>')
    if highlight:
        x, y = view.pt(highlight)
        c.add(f'<circle cx="{num(x)}" cy="{num(y)}" r="5.5" fill="none" stroke="{T["amber"]}" stroke-width="0.9" opacity="0.55"/>'
              f'<circle cx="{num(x)}" cy="{num(y)}" r="2.6" fill="{T["amber"]}"/>')
    c.reserve(f"{idp} map", box, gap=4)
    return view


# ----------------------------------------------------------------------------- hero
# map sheet: lon0, lon1, lat0, lat1 (a conic "fan"). The sheet runs to 39.5 N so the callouts under Lake Erie
# keep >= 20 units of paper between them and the frame ticks.
FAN = (-92.5, -75.5, 39.5, 50.0)
MAP_X0 = 544

RIPPLE_CSS = ("@keyframes rp{0%{transform:scale(.6);opacity:.65}100%{transform:scale(2.1);opacity:0}}"
              ".rp{transform-box:fill-box;transform-origin:center;animation:rp 4.2s ease-out infinite}"
              ".rp2{animation-delay:2.1s}"
              "@media (prefers-reduced-motion: reduce){.rp{animation:none;opacity:.3}}")


def fan_outline(view, step=0.25):
    lo0, lo1, la0, la1 = FAN
    pts = []
    for lo in np.arange(lo0, lo1 + 1e-9, step):
        pts.append(view(lo, la0))
    for la in np.arange(la0, la1 + 1e-9, step):
        pts.append(view(lo1, la))
    for lo in np.arange(lo1, lo0 - 1e-9, -step):
        pts.append(view(lo, la1))
    for la in np.arange(la1, la0 - 1e-9, -step):
        pts.append(view(lo0, la))
    return np.array(pts, float)


def poly_d(pts, close=True):
    return "M" + " ".join(f"{num(x)} {num(y)}" for x, y in pts) + ("Z" if close else "")


HERO_W = 1200
HERO_K = DESKTOP_W / HERO_W            # the hero is shown at 0.705 px per unit on desktop


def hw(px):
    """Hero stroke width (units) that renders at `px` pixels on desktop."""
    return round(px / HERO_K, 2)


def ring_gap(b, ring):
    """Smallest distance between a box and a sampled outline."""
    dx = np.maximum(np.maximum(b[0] - ring[:, 0], ring[:, 0] - b[2]), 0)
    dy = np.maximum(np.maximum(b[1] - ring[:, 1], ring[:, 1] - b[3]), 0)
    return float(np.hypot(dx, dy).min())


def box_gap(a, b):
    """Smallest distance between two boxes (0 if they touch or overlap)."""
    return math.hypot(max(a[0] - b[2], b[0] - a[2], 0.0), max(a[1] - b[3], b[1] - a[3], 0.0))


HERO_STATS: dict = {}


def build_hero(T, theme):
    W, H = HERO_W, 640
    M = 64            # one outer margin: name, map sheet (+ ticks), strip rule and scale bar
    PL = 9.6          # plate stroke centre -> 6.77 px on desktop, the same x as every card edge below
    c = Canvas("hero", W, H,
               "Xin (Shane) Lan, Ph.D. - water systems, artificial intelligence, metacoupling",
               "Name plate beside a Lambert conformal conic map of the Great Lakes with bathymetry-style "
               "contours, marking CSIS at Michigan State University (East Lansing) and CIGLR at the "
               "University of Michigan (Ann Arbor).", T, 1.0)
    c.style = RIPPLE_CSS
    sw = hw(1.04)                                   # the cards' 1-unit stroke renders at 1.04 px
    c.add(f'<rect x="{PL}" y="{num(sw / 2, 2)}" width="{num(W - 2 * PL, 2)}" height="{num(H - sw, 2)}" rx="21" '
          f'fill="{T["paper"]}" stroke="{T["rule"]}" stroke-width="{sw}"/>')
    STRIP = 536

    # --- map sheet (conic fan) -------------------------------------------------
    unit = View(1, 0, 0)
    fo = fan_outline(unit)
    x, y = fo[:, 0], fo[:, 1]
    TICK = 7
    box = (MAP_X0, 36, W - M - TICK - 1, STRIP - 28)
    s = min((box[2] - box[0]) / (x.max() - x.min()), (box[3] - box[1]) / (y.max() - y.min()))
    ox = box[2] - s * x.max()                                   # right-aligned in its box
    oy = box[1] + ((box[3] - box[1]) - s * (y.max() - y.min())) / 2 - s * y.min()
    view = View(s, ox, oy)
    fan = fan_outline(view)
    fan_box = (fan[:, 0].min(), fan[:, 1].min(), fan[:, 0].max(), fan[:, 1].max())
    assert inside(fan_box, box), f"hero: map sheet {fb(fan_box)} outside {fb(box)}"

    c.add(f'<path d="{poly_d(fan)}" fill="{T["paper"]}" stroke="none"/>')
    # graticule every 2 degrees
    lo0, lo1, la0, la1 = FAN
    g = []
    for lo in range(-92, -75, 2):
        (xa, ya), (xb, yb) = view.pt((lo, la0)), view.pt((lo, la1))
        g.append(f"M{num(xa)} {num(ya)}L{num(xb)} {num(yb)}")
    # parallels curve under the conic, so each is drawn as a polyline sampled every half degree
    parallels = [[view.pt((lo, la)) for lo in np.arange(lo0, lo1 + 1e-9, 0.5)]
                 for la in range(math.ceil(la0 / 2) * 2, int(la1), 2) if la0 < la < la1]
    g += [poly_d(p, close=False) for p in parallels]
    # meridians are knocked out behind the callouts (mask filled in once the callouts are placed)
    c.add(f'<path d="{"".join(g)}" fill="none" stroke="{T["grat"]}" stroke-width="{hw(0.85)}" mask="url(#gm)"/>')
    # the parallels are sampled again below: no callout may sit on one
    par_pts = np.vstack([sample_poly(np.array(p), 2.0, close=False) for p in parallels])

    # neatline + degree ticks pointing outward (kept as segments too: the scale bar is measured off them)
    ticks, tick_seg = [], []

    def add_tick(at, outward, major):
        """One tick at `at`, pointing away from the sheet along the direction of `outward`."""
        p, q = np.array(view.pt(at)), np.array(view.pt(outward))
        u = (q - p) / np.hypot(*(q - p))
        tl = TICK if major else 4       # every 5 degrees the tick is long enough to count off
        ticks.append(f"M{num(p[0])} {num(p[1])}l{num(u[0] * tl)} {num(u[1] * tl)}")
        tick_seg.append(np.array([p, p + u * tl]))

    for lo in range(math.ceil(lo0), math.floor(lo1) + 1):
        for la, sgn in ((la0, -1), (la1, 1)):
            add_tick((lo, la), (lo, la + sgn * 0.2), lo % 5 == 0)
    for la in range(math.ceil(la0), math.floor(la1) + 1):
        for lo, sgn in ((lo0, -1), (lo1, 1)):
            add_tick((lo, la), (lo + sgn * 0.2, la), la % 5 == 0)
    c.add(f'<path d="{"".join(ticks)}" fill="none" stroke="{T["tick"]}" stroke-width="{hw(0.9)}"/>')
    tick_pts = np.vstack([sample_poly(s_, 1.0, close=False) for s_ in tick_seg]
                         + [np.array([s_[1] for s_ in tick_seg])])
    c.add(f'<path d="{poly_d(fan)}" fill="none" stroke="{T["tick"]}" stroke-width="{hw(1.0)}"/>')
    ring = sample_poly(fan, 1.0)

    # --- lakes -------------------------------------------------------------------
    lakes = lake_rings(view, eps=0.45)
    lb = lakes_bbox(lakes)
    assert inside(lb, fan_box, pad=6)
    # Hydrographic names in italic serif (cartographic convention), auto-placed for maximum shore clearance.
    # (name, lon, lat, preferred angle, allowed deviation, placement): angles follow each lake's long axis.
    # Lake Ontario is too narrow at this scale to hold the name, so it is set on the shore just north of it.
    labels = [("Superior", -86.6, 47.6, 25, 10, "water"), ("Michigan", -87.05, 43.6, -84, 8, "water"),
              ("Huron", -82.3, 44.8, 65, 15, "water"), ("Erie", -81.3, 42.15, -24, 8, "water"),
              ("Ontario", -77.7, 44.3, -4, 4, "land")]
    # 21.5 is the floor that still gives >= 6 px on a 340 px phone; pad is the halo the name keeps clear
    # of the shore, and also the stroke that knocks the contours out behind it.
    lab_size, pad = 21.5, 3.5
    knock, lab_els = [], []
    for name, lon, lat, ang, span, mode in labels:
        lake = {name: lakes[name]} if mode == "water" else lakes
        cx, cy, ang, bb = place_label(name, SERIF_I, lab_size, view.pt((lon, lat)), ang, lake, mode, ang_span=span)
        d = text_path(name, SERIF_I, lab_size, 0, bb[4], "middle", 0, 1)
        tr = f"translate({num(cx, 2)} {num(cy, 2)}) rotate({num(ang)})"
        world = rot_box_pts(bb[:4], ang, cx, cy, 1.0)
        wet = in_water(world, lakes)
        assert (wet.all() if mode == "water" else not wet.any()), f"hero: label {name} misplaced"
        md = shore_dist(world, lakes).min()
        assert md >= pad, f"hero: label {name} only {md:.1f}px from a shoreline"
        if mode == "land":
            assert _pip(world, fan).all(), f"hero: label {name} leaves the map sheet"
        c.reserve(f"lake label {name}", (world[:, 0].min(), world[:, 1].min(), world[:, 0].max(), world[:, 1].max()), gap=4)
        if mode == "water":
            knock.append(f'<path d="{d}" transform="{tr}" fill="#000" stroke="#000" stroke-width="{2 * pad}" stroke-linejoin="round"/>')
        lab_els.append(f'<path d="{d}" transform="{tr}" fill="{T["lakelabel"]}"/>')
        c.sizes.append(lab_size)

    levels = [4.5, 9.5, 15.5, 22.5, 30.5]
    draw_lakes(c, lakes, T, "lk", levels=levels, coast_w=hw(1.05), knockouts=knock, line_w=hw(0.92))
    c.els += lab_els

    # --- markers + callouts --------------------------------------------------------
    # place names, as a map labels them: organisation (ink) · town (text)
    el, aa = view.pt(EAST_LANSING), view.pt(ANN_ARBOR)
    size = 22
    capv = cap_h(SANS_M, size)
    pieces_el = [("CSIS", SANS_SB, T["ink"]), ("  ·  ", SANS_M, T["amber_t"]), ("East Lansing", SANS_M, T["text"])]
    pieces_aa = [("CIGLR", SANS_SB, T["ink"]), ("  ·  ", SANS_M, T["amber_t"]), ("Ann Arbor", SANS_M, T["text"])]
    w_el = sum(measure(t, f, size) for t, f, _ in pieces_el)
    w_aa = sum(measure(t, f, size) for t, f, _ in pieces_aa)
    x_el1, x_aa0 = el[0] - 12, aa[0] + 12
    span = (x_el1 - w_el - 24, x_aa0 + w_aa + 24)
    allp = np.vstack([r for rings in lakes.values() for r in rings])
    sel = allp[(allp[:, 0] >= span[0]) & (allp[:, 0] <= span[1])]
    water_bottom = sel[:, 1].max()
    base = water_bottom + 14 + capv
    shelf = base + 9
    b_el, _ = c.runs(pieces_el, x_el1, base, size, anchor="end", key="CSIS callout", gap=6)
    b_aa, _ = c.runs(pieces_aa, x_aa0, base, size, key="CIGLR callout", gap=6)
    # the Ann Arbor leader leaves its marker on a short diagonal away from Lake Erie's western shore
    jog = 6
    leaders = [[(el[0], el[1] + 8), (el[0], shelf), (b_el[0] - 2, shelf)],
               [(aa[0] - 2, aa[1] + 7.6), (aa[0] - jog, aa[1] + 7.6 + 2 * jog), (aa[0] - jog, shelf), (b_aa[2] + 2, shelf)]]
    # callouts + shelves: dry, on the sheet and well clear of its frame (outline + 7 px ticks)
    frame_gap, knock_boxes = [], []
    for bx_, pl in zip((b_el, b_aa), leaders):
        ext = union(bx_, (min(p[0] for p in pl[1:]), shelf, max(p[0] for p in pl[1:]), shelf))
        pts = sample_box((ext[0] - 4, ext[1] - 4, ext[2] + 4, ext[3] + 4), 2)
        assert not in_water(pts, lakes).any(), "hero: callout touches water"
        assert _pip(pts, fan).all(), f"hero: callout {fb(bx_)} leaves the map sheet"
        frame_gap.append(ring_gap(ext, ring) - TICK)
        gx = par_pts
        assert not ((gx[:, 0] > ext[0] - 6) & (gx[:, 0] < ext[2] + 6) & (gx[:, 1] > ext[1] - 6) & (gx[:, 1] < ext[3] + 6)).any(), \
            "hero: a parallel runs through a callout"
        knock_boxes.append(ext)
    assert min(frame_gap) >= 20, f"hero: callouts only {min(frame_gap):.1f} units inside the frame ticks"
    leader_gap, lead_pts = [], []
    for pl in leaders:
        pts = sample_poly(np.array(pl, float), 1.0, close=False)
        assert not in_water(pts, lakes).any(), "hero: leader line crosses water"
        leader_gap.append(float(shore_dist(pts, lakes).min()))
        lead_pts.append(np.vstack([pts, np.array(pl, float)]))
    assert min(leader_gap) >= 12, f"hero: a leader line runs {min(leader_gap):.1f} units from a shoreline"
    lead_pts = np.vstack(lead_pts)
    HERO_STATS.update(frame_gap=[round(v, 1) for v in frame_gap], leader_gap=[round(v, 1) for v in leader_gap])

    # --- scale bar: the plate carries its own scale ---------------------------------
    # An atlas plate prints its scale inside the neatline, so the bar goes in the sheet's lower-right
    # corner -- the emptiest quarter of the map -- flush right with the callout above it and centred in
    # the open paper between that callout's leader shelf and the bottom neatline. Like the callouts it
    # knocks the graticule out behind it (mask "gm"), so no meridian or parallel crosses it.
    ppk = view.s * lcc_k(44.0) / 6371.0
    SL = 200 * ppk                                   # 200 km at the map's own projection
    assert 60 < SL < 200, SL
    sc = 21.5                                        # the hero's floor: 6.09 px on a 340 px phone
    ib200 = ink_box("200 km", SANS_M, sc, 0, 0, "end")      # ink relative to an end-anchored baseline
    ib0 = ink_box("0", SANS_M, sc, 0, 0, "end")
    xr = b_aa[2] - ib200[2]                          # "200 km" ends on the callout's own right edge
    bx1 = xr + ib200[0] - 12
    bx0 = bx1 - SL
    sc_l, sc_r = bx0 - 10 + ib0[0], b_aa[2]
    sc_t, sc_b = min(ib0[1], ib200[1]), max(ib0[3], ib200[3])
    # the bottom neatline curves, so the floor is its highest point under the block's own measure
    below = ring[(ring[:, 0] >= sc_l) & (ring[:, 0] <= sc_r) & (ring[:, 1] > shelf)]
    floor = float(below[:, 1].min())
    base = shelf + (floor - shelf - (sc_b - sc_t)) / 2 - sc_t
    sc_box = (sc_l, base + sc_t, sc_r, base + sc_b)
    pts = sample_box(sc_box, 1.5)
    assert _pip(pts, fan).all(), f"hero: scale bar {fb(sc_box)} leaves the map sheet"
    assert not in_water(pts, lakes).any(), "hero: scale bar touches water"
    sg = dict(shore=float(shore_dist(pts, lakes).min()), frame=ring_gap(sc_box, ring),
              tick=ring_gap(sc_box, tick_pts), leader=ring_gap(sc_box, lead_pts),
              callout=min(box_gap(sc_box, b) for b in (b_el, b_aa)),
              marker=min(box_gap(sc_box, (p[0] - 9.6, p[1] - 9.6, p[0] + 9.6, p[1] + 9.6)) for p in (el, aa)))
    assert sg["shore"] >= 20, f"hero: scale bar only {sg['shore']:.1f} units from a shoreline"
    assert sg["frame"] >= 9, f"hero: scale bar only {sg['frame']:.1f} units inside the map frame"
    assert sg["tick"] >= 9, f"hero: scale bar only {sg['tick']:.1f} units from a frame tick"
    assert sg["leader"] >= 9, f"hero: scale bar only {sg['leader']:.1f} units from a leader line"
    assert sg["callout"] >= 12, f"hero: scale bar only {sg['callout']:.1f} units from a callout"
    assert sg["marker"] >= 20, f"hero: scale bar only {sg['marker']:.1f} units from a marker"
    knock_boxes.append(sc_box)
    by = base - cap_h(SANS_M, sc) / 2 - 3
    segs = []
    for i in range(4):
        xa = bx0 + i * SL / 4
        segs.append(f'<rect x="{num(xa, 2)}" y="{num(by, 2)}" width="{num(SL / 4, 2)}" height="6" '
                    f'fill="{T["ink"] if i % 2 == 0 else T["paper"]}"/>')
    c.add("".join(segs) + f'<rect x="{num(bx0, 2)}" y="{num(by, 2)}" width="{num(SL, 2)}" height="6" fill="none" '
          f'stroke="{T["ink"]}" stroke-width="{hw(0.9)}"/>')
    c.reserve("scale bar", (bx0, by, bx1, by + 6), gap=10)
    lab200 = c.text("200 km", SANS_M, sc, xr, base, T["muted"], anchor="end", gap=10)
    c.text("0", SANS_M, sc, bx0 - 10, base, T["muted"], anchor="end", gap=10)
    assert abs(lab200[2] - b_aa[2]) < 0.01, f"hero: scale label is not flush with the callout {fb(lab200)}"
    HERO_STATS.update(km200=round(float(SL), 1), scale_box=[round(float(v), 1) for v in sc_box],
                      scale_gap={k: round(float(v), 1) for k, v in sg.items()})

    c.defs.append(f'<mask id="gm" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">'
                  f'<rect width="{W}" height="{H}" fill="#fff"/>'
                  + "".join(f'<rect x="{num(b[0] - 6)}" y="{num(b[1] - 6)}" width="{num(b[2] - b[0] + 12)}" '
                            f'height="{num(b[3] - b[1] + 12)}" rx="5" fill="#000"/>' for b in knock_boxes) + '</mask>')
    ld = "".join("M" + "L".join(f"{num(px)} {num(py)}" for px, py in pl) for pl in leaders)
    c.add(f'<path d="{ld}" fill="none" stroke="{T["amber"]}" stroke-width="{hw(1.0)}" stroke-linejoin="round"/>')
    for n_, (mx, my) in enumerate((el, aa)):
        c.add(f'<circle class="rp{" rp2" if n_ else ""}" cx="{num(mx)}" cy="{num(my)}" r="9" fill="none" stroke="{T["amber"]}" stroke-width="{hw(1.05)}" opacity="0.3"/>')
        c.add(f'<circle cx="{num(mx)}" cy="{num(my)}" r="5.2" fill="{T["amber"]}" stroke="{T["paper"]}" stroke-width="2"/>')
    assert math.hypot(el[0] - aa[0], el[1] - aa[1]) > 14, "hero: markers overlap"
    for (mx, my) in (el, aa):
        c.reserve("marker", (mx - 6, my - 6, mx + 6, my + 6), gap=4)

    # --- name plate (left column) ------------------------------------------------
    X0 = M
    # The column runs right up to the map's box, not to the fan: the fan is height-bound and its outline
    # only starts around x 586 beside the name, so the 28px clearance asserted below is the real guard.
    col = (M - 16, 40, box[0] - 4, STRIP - 16)
    # X0 - 1.5 sets the "X" on the optical left margin; baselines 174/276 are 1.19 em apart.
    n1 = c.text("Xin (Shane)", SERIF, 86, X0 - 1.5, 174, T["ink"], tracking=-0.005, within=col, gap=8)
    n2 = c.text("Lan, Ph.D.", SERIF, 86, X0 - 1.5, 276, T["ink"], tracking=-0.005, within=col, gap=8)
    c.add(f'<rect x="{X0}" y="326" width="56" height="2.2" fill="{T["amber"]}"/>')
    c.reserve("rule", (X0, 326, X0 + 56, 328.2), within=col)
    tag = []
    for i, line in enumerate(["Hydrological modeling and AI for", "understanding water systems and",
                              "human\u2013nature interactions."]):
        tag.append(c.text(line, SERIF_I, 28, X0, 382 + 38 * i, T["text"], within=col))
    # typography must stay >= 28px from the map sheet (its outline incl. the 7px ticks)
    for b in (n1, n2, *tag):
        gapv = ring_gap(b, ring)
        assert gapv >= 28 + TICK, f"hero: text {fb(b)} only {gapv:.1f}px from the map sheet"
        assert not _pip(np.array([[b[0], b[1]], [b[2], b[3]]]), fan).any()

    # --- bottom strip: the plate's keyword line --------------------------------------
    # The keywords are the strip's only content, so they are centred on the plate's axis (x 600) -- the
    # same axis the rule above them spans symmetrically -- and read as the plate's caption. Left-aligned
    # they would leave a fifth of the measure as dead line under the map's right edge.
    hline(c, M, W - M, STRIP, T["rule"], w=sw)
    # 21.5 is the hero's floor (6.09 px on a 340 px phone); the strip is centred on the 22-unit cap the
    # callouts share, not on this size, so the line sits on one baseline with them.
    SUBTITLE = 21.5
    base = (STRIP + H) / 2 + cap_h(SANS_M, 22) / 2
    dot = ("  ·  ", SANS_M, T["amber_t"])
    sb, tot = c.runs([("WATER SYSTEMS", SANS_M, T["ink"]), dot, ("ARTIFICIAL INTELLIGENCE", SANS_M, T["ink"]),
                      dot, ("METACOUPLING", SANS_M, T["ink"])], (M + W - M) / 2, base, SUBTITLE,
                     tracking=0.14, anchor="middle",
                     within=(M - 8, STRIP + 8, W - M + 8, H - 8), key="subtitle", gap=24)
    ends = (round(sb[0] - M, 1), round(W - M - sb[2], 1))
    assert abs(ends[0] - ends[1]) <= 1, f"hero: keyword line off centre in the strip {ends}"
    HERO_STATS.update(map_right=round(float(fan_box[2]) + TICK, 1), name_left=round(n1[0], 1),
                      strip_fill=round(100 * tot / (W - 2 * M), 1), strip_ends=list(ends))
    return c.write(theme)


class Field:
    """Signed distance to the nearest shoreline on a regular grid (+ in water, - on land)."""

    def __init__(self, lakes, box, step=1.0):
        self.x0, self.y0, self.step = box[0], box[1], step
        xs = np.arange(box[0], box[2] + step, step)
        ys = np.arange(box[1], box[3] + step, step)
        gx, gy = np.meshgrid(xs, ys)
        pts = np.column_stack([gx.ravel(), gy.ravel()])
        d = np.empty(len(pts))
        w = np.empty(len(pts), bool)
        for i in range(0, len(pts), 3000):
            d[i:i + 3000] = shore_dist(pts[i:i + 3000], lakes)
            w[i:i + 3000] = in_water(pts[i:i + 3000], lakes)
        self.f = np.where(w, d, -d).reshape(gx.shape)

    def __call__(self, pts, outside):
        ix = np.rint((pts[:, 0] - self.x0) / self.step).astype(int)
        iy = np.rint((pts[:, 1] - self.y0) / self.step).astype(int)
        ok = (ix >= 0) & (iy >= 0) & (ix < self.f.shape[1]) & (iy < self.f.shape[0])
        out = np.full(len(pts), outside, float)
        out[ok] = self.f[iy[ok], ix[ok]]
        return out


def label_box(text, font, size):
    """Ink box of `text` centred on the origin; returns (x0, y0, x1, y1, baseline_y)."""
    b0 = ink_box(text, font, size, 0, 0, "middle")
    dy = -(b0[1] + b0[3]) / 2
    return (b0[0], b0[1] + dy, b0[2], b0[3] + dy, dy)


def rot_box_pts(bb, ang, cx, cy, step):
    """Sample a box, rotate it by `ang` and drop it at (cx, cy) -- the ink a rotated label covers."""
    pts = sample_box(bb, step)
    a = math.radians(ang)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return pts @ R.T + [cx, cy]


SEARCH, SEARCH_STEP = 36, 2.0       # label search: units either side of the preferred point, and its grid step
# Score weights per mode: clearance is worth having up to `cap`, past which drifting or turning away from the
# preferred placement costs more than it gains. A land label is pulled back harder, so a shore name stays
# beside its lake instead of wandering off into open land where clearance is unbounded.
PLACE_W = dict(water=(7.0, 0.04, 0.12), land=(8.0, 0.08, 0.15))


def place_label(text, font, size, pref, pref_ang, lakes, mode="water", ang_span=12):
    """Slide and turn a lake name around its preferred point/angle; keep the placement with the most
    shoreline clearance, penalised for straying from that preference. Returns (cx, cy, angle, ink box)."""
    bb = label_box(text, font, size)
    half = max(abs(bb[0]), abs(bb[2])) + 8
    fbox = (pref[0] - SEARCH - half, pref[1] - SEARCH - half, pref[0] + SEARCH + half, pref[1] + SEARCH + half)
    field = Field(lakes, fbox)
    sign = 1.0 if mode == "water" else -1.0     # measure clearance inside the water, or outside it
    cap, w_drift, w_ang = PLACE_W[mode]
    local = sample_box(bb[:4], 2.0)
    g = np.arange(-SEARCH, SEARCH + 1e-9, SEARCH_STEP)
    C = np.array([(pref[0] + u, pref[1] + v) for u in g for v in g])
    best = None
    for ang in np.arange(pref_ang - ang_span, pref_ang + ang_span + 1e-9, 1.0):
        a = math.radians(ang)
        R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        rl = local @ R.T
        world = (C[:, None, :] + rl[None]).reshape(-1, 2)
        vals = sign * field(world, -1e3 * sign)      # samples off the grid score as hopelessly wrong
        clr = vals.reshape(len(C), len(rl)).min(1) - 0.75
        score = (np.minimum(clr, cap) - w_drift * np.hypot(C[:, 0] - pref[0], C[:, 1] - pref[1])
                 - w_ang * abs(ang - pref_ang))
        i = int(np.argmax(score))
        if best is None or score[i] > best[0]:
            best = (score[i], C[i][0], C[i][1], float(ang))
    _, cx, cy, ang = best
    return float(cx), float(cy), ang, bb


# ----------------------------------------------------------------------------- icons (16-unit line icons)
ICONS = {
    "globe": '<circle cx="8" cy="8" r="6.5"/><ellipse cx="8" cy="8" rx="2.8" ry="6.5"/>'
             '<path d="M1.5 8h13M2.6 4.7h10.8M2.6 11.3h10.8"/>',
    "scholar": '<path d="M8 2.6 15 6 8 9.4 1 6Z"/><path d="M4 7.6v3.3c0 1.2 1.8 2.2 4 2.2s4-1 4-2.2V7.6"/><path d="M15 6v4.2"/>',
    "orcid": '<circle cx="8" cy="8" r="6.5"/><path d="M5.5 7.1v4.3"/><circle cx="5.5" cy="5" r=".7" fill="{c}" stroke="none"/>'
             '<path d="M7.8 6.8v4.6h1.3c1.5 0 2.5-1 2.5-2.3S10.6 6.8 9.1 6.8Z"/>',
    "researchgate": '<rect x="1.5" y="1.5" width="13" height="13" rx="3"/>'
                    '<path d="M3.9 11V5h1.7a1.5 1.5 0 0 1 0 3H3.9m1.8 0L7.1 11"/>'
                    '<path d="M12.2 6.3A2.1 2.1 0 1 0 12.4 9.4V8.3H10.9"/>',
    "linkedin": '<rect x="1.5" y="1.5" width="13" height="13" rx="3"/><path d="M5 7.2v4.3"/>'
                '<circle cx="5" cy="5.1" r=".7" fill="{c}" stroke="none"/><path d="M7.6 11.5V7.2M7.6 9.3c0-1.4.8-2.1 1.8-2.1s1.7.7 1.7 2.1v2.2"/>',
    "x": '<path d="M2.4 2.6h3.1l8.1 10.8h-3.1Z"/><path d="M13.3 2.6 9 7.4M7 9.7 2.7 13.4"/>',
    "repo": '<path d="M3 2.5h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3Z"/><path d="M5.6 2.5v11"/>',
    "arrow": '<path d="M4.5 11.5 11.5 4.5M6 4.5h5.5V10"/>',
    "review": '<circle cx="8" cy="8" r="6.5"/><path d="M5.2 8.3l1.9 1.9 3.8-4"/>',
}
ICON_SW = 1.3       # stroke width at the icon's drawn size, divided out by the scale factor below


def icon(c, kind, x, y, size, color, within=None):
    k = size / 16
    body = ICONS[kind].replace("{c}", color)
    c.add(f'<g transform="translate({num(x, 2)} {num(y, 2)}) scale({num(k, 4)})" fill="none" stroke="{color}" '
          f'stroke-width="{num(ICON_SW / k, 3)}" stroke-linecap="round" stroke-linejoin="round">{body}</g>')
    c.reserve(f"icon {kind}", (x, y, x + size, y + size), within=within)


# ----------------------------------------------------------------------------- appointment cards
TITLE = 26          # appointment card titles
HEAD = 23           # featured repo heads: their 532-unit measure caps a two-line title at 23

APPOINTMENTS = [
    dict(name="appt-csis", role="Postdoctoral Scholar", where="EAST LANSING, MI", place="East Lansing, MI", loc=EAST_LANSING,
         org=["Center for Systems Integration", "and Sustainability (CSIS)"], inst="Michigan State University",
         coord="42.73° N · 84.48° W",
         line="Postdoctoral Scholar | Center for Systems Integration and Sustainability (CSIS), Michigan State University — East Lansing, MI"),
    dict(name="appt-ciglr", role="Postdoctoral Fellow", where="ANN ARBOR, MI", place="Ann Arbor, MI", loc=ANN_ARBOR,
         org=["Cooperative Institute for", "Great Lakes Research (CIGLR)"], inst="University of Michigan",
         coord="42.28° N · 83.74° W",
         line="Postdoctoral Fellow | Cooperative Institute for Great Lakes Research (CIGLR), University of Michigan — Ann Arbor, MI"),
]


def build_appointment(a, T, theme):
    W, H = CARD_W, 236
    c = Canvas(a["name"], W, H, a["line"],
               f"Current appointment card with a locator map marking {a['place']} ({a['coord'].replace('°', '').replace(SEP, ', ')}).", T, 0.49)
    card_bg(c, T)
    inner = (24, 18, W - 24, H - 12)
    mini_map(c, T, (CARD_R - 92, 26, CARD_R, 88), "mm", highlight=a["loc"])
    c.add(f'<circle cx="{CARD_L + 4}" cy="{num(53 - cap_h(SANS_SB, 15) / 2, 2)}" r="4" fill="{T["amber"]}"/>')
    c.reserve("dot", (CARD_L, 44, CARD_L + 8, 52), within=inner)
    c.text(a["where"], SANS_SB, 15, CARD_L + 16, 53, T["teal"], tracking=0.12, within=inner)
    c.text(a["role"], SERIF, TITLE, CARD_L - 1, 122, T["ink"], within=inner, gap=6)
    for i, line in enumerate(a["org"]):
        c.text(line, SANS_M, 17.5, CARD_L, 156 + 25 * i, T["text"], within=inner)
    c.text(a["inst"], SANS, 16, CARD_L, 208, T["muted"], within=inner)
    return c.write(theme)


# ----------------------------------------------------------------------------- section titles
SECTIONS = [
    ("sec-appointments", "01", "Current appointments", "Superior"),
    ("sec-research", "02", "Research focus", "Michigan"),
    ("sec-code", "03", "Selected research code", "Huron"),
    ("sec-education", "04", "Education", "Erie"),
    ("sec-tools", "05", "Methods & Tools", "Ontario"),
    ("sec-activity", "06", "Code activity", None),
]
SEC_SIZE, SEC_NUM = 42, 17
GLYPH_SLOT = 48


def build_section(sec, T, theme):
    name, idx, title, lake = sec
    W, H = PANEL_W, 70
    desc = (f"Section {idx} heading with a small contour glyph of Lake {lake}." if lake
            else f"Section {idx} heading.")
    c = Canvas(name, W, H, title, desc, T, 1.0)
    base = 57
    x0, x1 = PANEL_INSET + 0.5, W - PANEL_INSET - 0.5       # the card edges below
    off = ink_box(idx, MONO_M, SEC_NUM, 0, base)[0]
    nb = c.text(idx, MONO_M, SEC_NUM, x0 - off, base, T["amber_t"], gap=8)
    tb = c.text(title, SERIF, SEC_SIZE, nb[2] + 14, base, T["ink"], gap=16)
    y_line = base - 10
    if lake:
        # every glyph is centred in the same 48-unit slot, flush with the card edge
        slot = (x1 - GLYPH_SLOT, y_line - 20, x1, y_line + 20)
        pts = np.asarray(LAKES[lake][0], float)
        view = View.fit(pts, slot)
        lk = lake_rings(view, 0.2, hole_min=None, names=[lake])
        lb = lakes_bbox(lk)
        assert inside(lb, slot, pad=-0.01), f"{name}: glyph outside its slot"
        draw_lakes(c, lk, T, "g", levels=(2.4, 5.0), coast_w=0.8, line_w=0.6, prec=2)
        c.reserve("glyph", slot, gap=10)
    rx0, rx1 = tb[2] + 18, (x1 - GLYPH_SLOT - 16 if lake else x1)
    assert rx1 - rx0 > 60, f"{name}: no room for the rule"
    hline(c, rx0, rx1, y_line, T["rule"])
    # scale-bar ticks at the start of the rule (a quiet cartographic cue)
    c.add(f'<path d="M{num(rx0)} {y_line - 3}v6M{num(rx0 + 24)} {y_line - 2}v4M{num(rx0 + 48)} {y_line - 2}v4" '
          f'stroke="{T["tick"]}" stroke-width="1"/>')
    return c.write(theme)


# ----------------------------------------------------------------------------- link buttons (1:1 px)
BTN_H, BTN_FONT, BTN_ICON = 32, 15, 15
BTN_ROW_MAX = 600       # px; a row this wide still sits centred on the 846 px desktop column
LINKS = [
    ("btn-website", "globe", "Website", "https://xinlan-science.github.io/"),
    ("btn-scholar", "scholar", "Google Scholar", "https://scholar.google.com/citations?hl=en&user=hDHQtHAAAAAJ"),
    ("btn-orcid", "orcid", "ORCID", "https://orcid.org/0000-0002-0607-2270"),
    ("btn-researchgate", "researchgate", "ResearchGate", "https://www.researchgate.net/profile/Xin-Lan-20"),
    ("btn-joss", "review", "JOSS Reviewer", "https://joss.theoj.org/papers/reviewed_by/@xinlan-technology"),
    ("btn-linkedin", "linkedin", "LinkedIn", "https://www.linkedin.com/in/xin-lan-585912184/"),
    ("btn-x", "x", "@ShaneResearch", "https://twitter.com/ShaneResearch"),
]
BTN_ROWS = (LINKS[:4], LINKS[4:])      # two deliberate rows (four, then three): never a lone orphan button
LINK_ALT = {"btn-website": "Personal website", "btn-scholar": "Google Scholar profile", "btn-orcid": "ORCID iD 0000-0002-0607-2270",
            "btn-researchgate": "ResearchGate profile", "btn-joss": "Reviewer for the Journal of Open Source Software (JOSS)",
            "btn-linkedin": "LinkedIn profile", "btn-x": "X (Twitter) @ShaneResearch"}
BTN_W: dict = {}


def build_button(b, T, theme):
    name, ic, label, _ = b
    tw = measure(label, SANS_M, BTN_FONT)
    PL, GAP, PR = 11, 7, 13
    W = math.ceil(PL + BTN_ICON + GAP + tw + PR)
    BTN_W[name] = W
    c = Canvas(name, W, BTN_H, label, f"Link button: {label}", T, W / DESKTOP_W)
    c.add(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{BTN_H - 1}" rx="{(BTN_H - 1) / 2}" fill="{T["card_fill"]}" stroke="{T["rule"]}"/>')
    within = (6, 3, W - 6, BTN_H - 3)
    icon(c, ic, PL, (BTN_H - BTN_ICON) / 2, BTN_ICON, T["teal"], within=within)
    c.text(label, SANS_M, BTN_FONT, PL + BTN_ICON + GAP, BTN_H / 2 + cap_h(SANS_M, BTN_FONT) / 2, T["ink"], within=within)
    return c.write(theme)


# ----------------------------------------------------------------------------- research focus legend
FOCUS = [  # (symbol, heading, caption) -- settled copy: ONE line each, verbatim, in one row per focus area
    ("pgml", "Process-guided ML", "Integrating physical knowledge with ML"),
    ("xai", "Explainable ML", "Interpretable and transparent AI models"),
    ("water", "Water systems modeling", "Water resources and human–water interactions"),
    ("thermal", "Lake thermal dynamics", "Lake temperature and thermal structure"),
    ("meta", "Metacoupling", "Human–nature interactions across space"),
    ("llm", "Large Language Models", "LLM agents for scientific workflows"),
]


def focus_pairs():
    """The panel's copy as it reads in alt text and <desc>: one 'heading: caption' per focus area."""
    return [f"{label}: {sub}" for _, label, sub in FOCUS]

# --- metacoupling symbol: three coupled systems (a triangle of nodes each) and the flows between them
META_CLUSTERS = [(16, 19), (48, 19), (32, 45)]      # cluster centres on the 64-unit symbol grid
META_R = 5.2                                        # radius of a cluster's node triangle
META_FLOWS = [((24, 16.2), (32, 10.6), (40, 16.2)),         # system 1 -> system 2
              ((47.5, 26), (48.5, 36.5), (38.8, 42.8)),     # system 2 -> system 3
              ((25.2, 42.8), (15.5, 36.5), (16.5, 26))]     # system 3 -> system 1 (mirror of the second)
META_NODE = 2.2
FLOW_HEAD, FLOW_SPREAD = 4.0, math.radians(27)      # chevron arrowhead: barb length and half-angle


def _triad(cx, cy, r=META_R):
    """The three nodes of one cluster, on a small equilateral triangle."""
    return [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (-math.pi / 2, math.pi / 6, 5 * math.pi / 6)]


def _head_pts(ctrl, p1):
    """Chevron at p1: the tip, then the two barbs. The tangent comes from the control point, so this
    works for a flow arrow's curve and for the LLM symbol's straight feed arrow alike."""
    a = math.atan2(p1[1] - ctrl[1], p1[0] - ctrl[0]) + math.pi
    return [p1] + [(p1[0] + FLOW_HEAD * math.cos(a + s), p1[1] + FLOW_HEAD * math.sin(a + s))
                   for s in (-FLOW_SPREAD, FLOW_SPREAD)]


def _flow_d(p0, ctrl, p1):
    """Quadratic flow arrow p0 -> p1, chevron-headed."""
    def P(p):
        return f"{num(p[0], 2)} {num(p[1], 2)}"

    _, b0, b1 = _head_pts(ctrl, p1)
    return f"M{P(p0)}Q{P(ctrl)} {P(p1)}M{P(b0)}L{P(p1)}L{P(b1)}"


# --- LLM symbol: a sequence of tokens feeding a stack of layers
LLM_BARS = (9, 18, 27)                              # top of each layer bar (LLM_BAR_H tall, x 13..51)
LLM_BAR_H = 6
LLM_TOKENS = (10, 19.5, 29, 38.5, 48)               # token squares; the middle one (centred on 32) is amber
LLM_TOK, LLM_TOK_Y = 6, 47
LLM_TIP, LLM_TAIL = 37.5, 44.5                      # the feed arrow, from the token row up into the stack

# Tile size, corner radius and line weight scale together off a 56-unit reference tile, so that half a
# stroke stays 0.857 units on the symbols' own 64-unit grid whatever size the tile is drawn at -- which is
# what makes the clearances asserted in check_focus_symbols independent of FOCUS_TILE.
FOCUS_TILE = 40
SYM_SW = 1.5 * FOCUS_TILE / 56
SYM_RX = 11 * FOCUS_TILE / 56


def focus_symbol(c, kind, x, y, T, S=FOCUS_TILE):
    k = S / 64
    c.add(f'<rect x="{num(x + .5)}" y="{num(y + .5)}" width="{S - 1}" height="{S - 1}" rx="{num(SYM_RX, 2)}" fill="{T["tile"]}" stroke="{T["rule"]}"/>')
    g = (f'<g transform="translate({num(x)} {num(y)}) scale({num(k, 4)})" fill="none" stroke-linecap="round" '
         f'stroke-linejoin="round" stroke-width="{num(SYM_SW / k, 3)}">')
    tl, am, tk = T["teal"], T["amber"], T["tick"]
    if kind == "pgml":
        body = (f'<path d="M18.4 23H27.6M36.4 23H45.6" stroke="{tk}"/>'
                f'<path d="M14 27v9M32 27v9M50 27v9" stroke="{tk}" stroke-dasharray="1.5 3"/>'
                f'<path d="M8 43q6-9 12 0t12 0 12 0 12 0" stroke="{tl}"/>'
                f'<circle cx="14" cy="23" r="3.6" fill="none" stroke="{tl}"/>'
                f'<circle cx="32" cy="23" r="3.6" fill="{am}" stroke="{am}"/>'
                f'<circle cx="50" cy="23" r="3.6" fill="none" stroke="{tl}"/>')
    elif kind == "xai":
        body = (f'<path d="M32 11v42" stroke="{tk}"/>'
                f'<path d="M32 18h17M32 28h-11M32 38h9M32 48h-5" stroke-width="5" stroke="{tl}"/>'
                f'<path d="M32 28h-11M32 48h-5" stroke-width="5" stroke="{am}"/>')
    elif kind == "water":
        body = (f'<path d="M32 52V37L19 25l-6-11M19 25l7-12M32 37l13-15 5-10M45 22l7 1" stroke="{tl}"/>'
                f'<circle cx="19" cy="25" r="2.2" fill="{tl}" stroke="none"/><circle cx="45" cy="22" r="2.2" fill="{tl}" stroke="none"/>'
                f'<circle cx="32" cy="37" r="2.2" fill="{tl}" stroke="none"/><circle cx="32" cy="52" r="3.8" fill="{am}" stroke="none"/>')
    elif kind == "meta":   # three coupled systems, flows running between them
        parts = []
        for i, (cx, cy) in enumerate(META_CLUSTERS):
            v = _triad(cx, cy)
            col = am if i == 2 else tl          # the focal system is the amber one
            parts.append('<path d="M' + "L".join(f"{num(p[0], 2)} {num(p[1], 2)}" for p in v)
                         + f'Z" stroke="{tk}"/>')
            parts += [f'<circle cx="{num(p[0], 2)}" cy="{num(p[1], 2)}" r="{META_NODE}" fill="{col}" stroke="none"/>'
                      for p in v]
        parts += [f'<path d="{_flow_d(*f)}" stroke="{tl}"/>' for f in META_FLOWS]
        body = "".join(parts)
    elif kind == "llm":    # a token sequence feeding a stack of layers
        body = ("".join(f'<rect x="13" y="{num(t)}" width="38" height="{LLM_BAR_H}" rx="2.5" stroke="{tl}"/>'
                        for t in LLM_BARS)
                + "".join(f'<rect x="{num(t)}" y="{LLM_TOK_Y}" width="{LLM_TOK}" height="{LLM_TOK}" rx="1.6" '
                          f'fill="{am if i == 2 else "none"}" stroke="{am if i == 2 else tl}"/>'
                          for i, t in enumerate(LLM_TOKENS))
                + f'<path d="M32 {num(LLM_TAIL)}V{num(LLM_TIP)}M30 {num(LLM_TIP + 3.3)}L32 {num(LLM_TIP)}'
                  f'L34 {num(LLM_TIP + 3.3)}" stroke="{tl}"/>')
    else:  # thermal profile: temperature (x) vs depth (y)
        body = (f'<path d="M13 11v43M13 11h40" stroke="{tk}"/>'
                f'<path d="M13 29h40" stroke="{am}" stroke-dasharray="2 3"/>'
                f'<path d="M47 14c0 6 0 10-2 13-3 4-18 3-21 8-2 3-3 9-3 16" stroke="{tl}" stroke-width="1.8"/>')
    c.add(g + body + "</g>")
    c.reserve(f"symbol {kind}", (x, y, x + S, y + S), gap=12)


FOCUS_STATS: dict = {}
SYM_STATS: dict = {}
SYM_AREA = (7.0, 8.0, 57.0, 56.0)   # the drawing area the other four symbols use, on the 64-unit grid


def _q_bounds(p0, ctrl, p1):
    """Bounding box of a quadratic Bezier (endpoints plus the extremum on each axis)."""
    out = []
    for i in (0, 1):
        vals = [p0[i], p1[i]]
        den = p0[i] - 2 * ctrl[i] + p1[i]
        if abs(den) > 1e-9:
            t = (p0[i] - ctrl[i]) / den
            if 0 < t < 1:
                vals.append((1 - t) ** 2 * p0[i] + 2 * t * (1 - t) * ctrl[i] + t * t * p1[i])
        out.append((min(vals), max(vals)))
    return (out[0][0], out[1][0], out[0][1], out[1][1])


def check_focus_symbols():
    """The metacoupling and LLM symbols are drawn on the same 64-unit grid as the other four. Keep them
    inside that grid's drawing area, and keep the flow arrows and the feed arrow off the node clusters
    and bars they link, so nothing in a tile touches anything else."""
    sw = SYM_SW * 32 / FOCUS_TILE    # half a stroke, in grid units: what a drawn edge adds to a box
    nodes = [p for cx, cy in META_CLUSTERS for p in _triad(cx, cy)]
    boxes = [(p[0] - META_NODE, p[1] - META_NODE, p[0] + META_NODE, p[1] + META_NODE) for p in nodes]
    clear = []
    for p0, ctrl, p1 in META_FLOWS:
        pts = [p0] + _head_pts(ctrl, p1)
        boxes += [_q_bounds(p0, ctrl, p1), (min(p[0] for p in pts), min(p[1] for p in pts),
                                            max(p[0] for p in pts), max(p[1] for p in pts))]
        clear += [min(math.hypot(p[0] - n[0], p[1] - n[1]) - META_NODE - sw for n in nodes) for p in pts]
    mb = union(*boxes)
    mb = (mb[0] - sw, mb[1] - sw, mb[2] + sw, mb[3] + sw)
    assert inside(mb, SYM_AREA), f"metacoupling symbol {fb(mb)} escapes the tile's drawing area {fb(SYM_AREA)}"
    assert min(clear) >= 1.0, f"a metacoupling flow arrow comes within {min(clear):.2f} of a node"

    bars = [(13, t, 51, t + LLM_BAR_H) for t in LLM_BARS]
    toks = [(t, LLM_TOK_Y, t + LLM_TOK, LLM_TOK_Y + LLM_TOK) for t in LLM_TOKENS]
    lb = union(*(bars + toks + [(30, LLM_TIP, 34, LLM_TAIL)]))
    lb = (lb[0] - sw, lb[1] - sw, lb[2] + sw, lb[3] + sw)
    assert inside(lb, SYM_AREA), f"LLM symbol {fb(lb)} escapes the tile's drawing area {fb(SYM_AREA)}"
    assert LLM_TOKENS[2] + LLM_TOK / 2 == 32, "the amber token is not the one the feed arrow rises from"
    gaps = [LLM_BARS[i + 1] - (LLM_BARS[i] + LLM_BAR_H) for i in range(len(LLM_BARS) - 1)]
    gaps += [LLM_TOKENS[i + 1] - (LLM_TOKENS[i] + LLM_TOK) for i in range(len(LLM_TOKENS) - 1)]
    # arrow tip -> bottom bar, arrow tail -> token row
    gaps += [LLM_TIP - (LLM_BARS[-1] + LLM_BAR_H), LLM_TOK_Y - LLM_TAIL]
    assert min(gaps) - 2 * sw >= 0.4, f"LLM symbol parts come within {min(gaps) - 2 * sw:.2f} of each other"
    SYM_STATS["metacoupling box"] = [round(v, 1) for v in mb]
    SYM_STATS["node clearance"] = round(min(clear), 2)
    SYM_STATS["LLM box"] = [round(v, 1) for v in lb]
    SYM_STATS["LLM gaps"] = [round(g, 2) for g in gaps]


def build_focus(T, theme):
    """One row per focus area: an icon tile, the heading in a fixed left column and the caption starting at
    one common x across the midline divider, all three on one baseline.

    One focus area per row, rather than two, because the captions are the longest lines in the panel: the
    longest measures 334 units at Inter 15 (the size the phone floor fixes), and half the panel minus a tile
    and its gap leaves only ~324."""
    W, MID, CH = PANEL_W, PANEL_W / 2, 68
    ROWS = len(FOCUS)
    FH, FS, GUT = 22, 15, 24                  # heading size, caption size, gutter either side of the divider
    tx = PANEL_L + FOCUS_TILE + 18            # heading column: tile, gap, then the heading
    headw, cx = (MID - GUT) - tx, MID + GUT   # caption column starts at the same x in every row
    capw = PANEL_R - cx
    capL = cap_h(SERIF, FH)
    pad = (CH - FOCUS_TILE) / 2               # tile -> rule above/below, and -> the panel's top/bottom edge
    assert pad >= 14, f"focus icon tiles sit only {pad:.1f} units from the rules"
    assert FS >= 15, f"focus captions at {FS} units fall under the panel's phone-legibility floor"
    rows, fills = [], []
    for kind, label, sub in FOCUS:
        # max_lines=1 is the uniformity rule: no heading and no caption may wrap, so no row is taller
        head = wrap(label, SERIF, FH, headw, max_lines=1)[0]
        capline = wrap(sub, SANS, FS, capw, max_lines=1)[0]
        fills.append([round(measure(label, SERIF, FH) / headw * 100, 1),
                      round(measure(sub, SANS, FS) / capw * 100, 1)])
        rows.append((kind, head, capline))
    H = ROWS * CH
    n = {4: "four", 6: "six", 8: "eight"}.get(ROWS, str(ROWS))
    c = Canvas("focus", W, H, "Research focus",
               f"Map-legend style panel of {n} research focus areas, one per row: an icon tile, the heading in "
               "a left column and one caption line beside it, across a hairline divider -- "
               + "; ".join(focus_pairs()) + ".", T, 1.0)
    panel_bg(c, T)
    for r in range(1, ROWS):
        hline(c, PANEL_L, PANEL_R, r * CH, T["rule"])
    c.add(f'<path d="M{num(MID)} 20V{num(H - 20)}" stroke="{T["rule"]}"/>')
    base = (CH + capL) / 2                    # one baseline per row, shared by the heading and the caption
    for r, (kind, head, capline) in enumerate(rows):
        y0 = r * CH
        cell = (PANEL_L - 4, y0 + 6, PANEL_R + 1, y0 + CH - 6)
        focus_symbol(c, kind, PANEL_L, y0 + pad, T)
        c.text(head, SERIF, FH, tx, y0 + base, T["ink"], within=cell)
        c.text(capline, SANS, FS, cx, y0 + base, T["muted"], within=cell)
    FOCUS_STATS["grid"] = f"{ROWS} rows of {CH} (H {H})"
    FOCUS_STATS["tile/baseline"] = [FOCUS_TILE, round(base, 1)]
    FOCUS_STATS["columns"] = [round(headw), round(capw)]
    FOCUS_STATS["heading/caption fill %"] = fills
    return c.write(theme)


# ----------------------------------------------------------------------------- repository cards
GH = "https://github.com/xinlan-technology/"
REPOS = [
    dict(repo="process_guided_deep_learning",
         head="Process-guided deep learning for daily\nlake water temperature profiles (Lake Mendota)",
         detail=["LSTM · Transformer · CNN-LSTM · Attention-LSTM",
                 "GLM-simulation pretraining · depth-wise ensemble · energy-conservation loss"],
         langs=["Python", "PyTorch"], art="section"),
    dict(repo="static-dynamic-lake-model",
         head="Lake-aware deep learning for lake temperature\nprofiles across lakes in 11~U.S.~states",
         detail=["HydroLAKES static features · satellite embeddings · NLDAS forcing · FiLM modulation by latent lake type · SHAP attribution"],
         langs=["Python", "PyTorch"], art="types"),
    dict(repo="hurricane_wind_radius_analysis",
         head="LSTM prediction of hurricane 34-kt wind radius (R34) from 6-hourly and hourly ERA5 inputs",
         detail=["Two models compared · evaluated only at 6-hour best-track points",
                 "50 features in three physics groups · grouped SHAP attribution"],
         langs=["Python"], art="cyclone"),
    dict(repo="water_system_consolidation",
         head="Geospatial clustering of California public water systems to explore consolidation potential",
         detail=["Service-area centroids · OpenStreetMap shortest-path distances",
                 "Violations · HR2W risk systems · county-level socioeconomic data"],
         langs=["Python", "GeoPandas"], art="clusters"),
]


def repo_slug(r):
    return "repo-" + r["repo"].replace("_", "-")


def sentence(*parts):
    """Join fragments into sentences without doubled punctuation or empty pieces."""
    out = []
    for p in parts:
        p = plain(p).replace(SEP, ", ").strip()
        if p:
            out.append(p if p[-1] in ".?!" else p + ".")
    return " ".join(out)


LANG_COLOR = {"Python": "teal", "PyTorch": "amber", "GeoPandas": "muted"}


def lang_row(c, T, langs, x, base, within):
    for lg in langs:
        c.add(f'<circle cx="{num(x + 5)}" cy="{num(base - cap_h(SANS, 15) / 2, 2)}" r="5" fill="{T[LANG_COLOR[lg]]}"/>')
        c.reserve(f"dot {lg}", (x, base - 11, x + 10, base), within=within)
        b = c.text(lg, SANS_M, 15, x + 16, base, T["text"], within=within)
        x = b[2] + 20
    return x


def lake_section_art(c, T, box):
    """Schematic (not data): a lake basin cross-section with warm surface water over cold deep water."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    top = y0 + 18
    basin = (f"M{num(x0)} {num(top)}H{num(x1)}"
             f"C{num(x1 - w * .06)} {num(top + h * .45)} {num(x1 - w * .22)} {num(y1)} {num(x0 + w * .55)} {num(y1)}"
             f"C{num(x0 + w * .25)} {num(y1)} {num(x0 + w * .1)} {num(top + h * .35)} {num(x0)} {num(top)}Z")
    c.defs.append(f'<linearGradient id="th" x1="0" y1="{num(top)}" x2="0" y2="{num(y1)}" gradientUnits="userSpaceOnUse">'
                  f'<stop offset="0" stop-color="{T["warm"]}"/><stop offset="0.34" stop-color="{T["warm"]}" stop-opacity="0.75"/>'
                  f'<stop offset="0.46" stop-color="{T["cold"]}" stop-opacity="0.8"/><stop offset="1" stop-color="{T["cold"]}"/></linearGradient>'
                  f'<clipPath id="bs"><path d="{basin}"/></clipPath>')
    c.add(f'<path d="{basin}" fill="url(#th)" opacity="0.55"/>')
    yt = top + (y1 - top) * 0.40
    c.add(f'<g clip-path="url(#bs)"><path d="M{num(x0)} {num(yt)}H{num(x1)}" stroke="{T["amber"]}" stroke-dasharray="3 4" stroke-width="1.2"/>'
          + "".join(f'<path d="M{num(x0)} {num(top + k * 14)}H{num(x1)}" stroke="{T["paper"]}" stroke-width="0.8" opacity="0.6"/>' for k in range(1, 9))
          + "</g>")
    c.add(f'<path d="{basin}" fill="none" stroke="{T["coast"]}" stroke-width="1.2"/>')
    wave = "".join(f"q{num(w / 16)} -4 {num(w / 8)} 0" for _ in range(8))
    c.add(f'<path d="M{num(x0)} {num(top - 6)}{wave}" fill="none" stroke="{T["teal"]}" stroke-width="1.2"/>')
    # temperature profile (schematic)
    px = x0 + w * 0.34
    c.add(f'<path d="M{num(px + 44)} {num(top + 4)}c0 12 -2 22 -8 {num(yt - top - 16)}s-30 8 -34 22 -2 30 -2 40" '
          f'fill="none" stroke="{T["ink"]}" stroke-width="1.6" stroke-linecap="round"/>')
    c.reserve("lake art", (x0, top - 12, x1, y1), gap=16)
    return (x0, top - 12, x1, y1)


TYPE_LAKES = ["Superior", "Michigan", "Huron", "Erie", "Ontario", "Simcoe"]


def lake_types_art(c, T, box):
    """Schematic (not data): a specimen plate of six lake outlines, each drawn with the page's contour style,
    for a model that learns per-lake behaviour. The outlines are simply the Great Lakes shapes."""
    x0, y0, x1, y1 = box
    cols, rows = 3, 2
    cw, rh = (x1 - x0) / cols, (y1 - y0) / rows
    grid = []
    for i in range(1, cols):
        grid.append(f"M{num(x0 + i * cw)} {num(y0 + 6)}V{num(y1 - 6)}")
    grid.append(f"M{num(x0 + 6)} {num(y0 + rh)}H{num(x1 - 6)}")
    c.add(f'<path d="{"".join(grid)}" stroke="{T["rule"]}" stroke-dasharray="2 4" fill="none"/>')
    for n, lake in enumerate(TYPE_LAKES):
        cx0, cy0 = x0 + (n % cols) * cw, y0 + (n // cols) * rh
        cell = (cx0 + 10, cy0 + 12, cx0 + cw - 10, cy0 + rh - 12)
        view = View.fit(np.asarray(LAKES[lake][0], float), cell)
        lk = lake_rings(view, 0.25, hole_min=None, names=[lake])
        draw_lakes(c, lk, T, f"t{n}", levels=(2.2, 4.8), coast_w=0.9, line_w=0.7, prec=1)
        assert inside(lakes_bbox(lk), cell, pad=-0.01)
    c.reserve("lake types", box, gap=16)
    return box


# --- hurricane schematic --------------------------------------------------------------------------
# Schematic (not data): the bands are a plain logarithmic spiral and the dashed circle only stands for
# "the radius the model predicts". The figure is a circle, so it is sized from its art column rather than
# fixed -- the R34 ring plus its tick and stroke just touches the column's shorter side, the way the lake
# plate and the California outline fill theirs -- and everything else is a fraction of that radius.
CY_EYE_F = 0.10              # eye radius, as a fraction of the R34 circle
CY_RING = 0.88               # outermost spiral band, as a fraction of the R34 circle: the dashed ring
                             # sits just outside the bands instead of standing off in an empty annulus
CY_B = 0.30                  # spiral band: r = r0 * exp(CY_B * theta)
CY_SPAN = 5.05               # radians swept by each band (~289 deg)
CY_ANG = math.radians(38)    # bearing of the radius line, up and to the right
CY_TICK_F = 0.083            # half-length of the amber tick across the radius, as a fraction of R34
CY_STATS: dict = {}


def _spiral(cx, cy, phase, r0, n=72):
    th = np.linspace(0.0, CY_SPAN, n)
    r = r0 * np.exp(CY_B * th)
    a = th + phase
    return np.column_stack([cx + r * np.cos(a), cy - r * np.sin(a)])   # counter-clockwise on screen


def cyclone_art(c, T, box):
    """Schematic (not data): a tropical cyclone -- an eye, three logarithmic spiral bands, and a dashed
    circle for the predicted 34-kt wind radius carrying a radius line and an amber tick."""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = min(x1 - x0, y1 - y0) / 2
    r34 = (half - 0.9) / math.hypot(1.0, CY_TICK_F)     # the tick tips reach r34 * hypot(1, CY_TICK_F)
    eye, tk = CY_EYE_F * r34, CY_TICK_F * r34
    r0 = CY_RING * r34 / math.exp(CY_B * CY_SPAN)
    r_band = r0 * math.exp(CY_B * CY_SPAN)
    ann = (r34 - r_band) / r34
    assert 0.06 <= ann <= 0.16, f"the R34 ring stands {100 * ann:.1f}% of its radius off the outer band"
    assert r_band > 2 * eye, f"spiral bands reach {r_band:.1f}, too close to the {eye:.1f} eye"
    ux, uy = math.cos(CY_ANG), -math.sin(CY_ANG)
    px, py = cx + r34 * ux, cy + r34 * uy
    tick = [(px - tk * uy, py + tk * ux), (px + tk * uy, py - tk * ux)]
    art = union((cx - r34, cy - r34, cx + r34, cy + r34),
                (min(p[0] for p in tick), min(p[1] for p in tick),
                 max(p[0] for p in tick), max(p[1] for p in tick)))
    art = (art[0] - 0.9, art[1] - 0.9, art[2] + 0.9, art[3] + 0.9)      # widest stroke
    assert inside(art, box), f"cyclone art {fb(art)} escapes {fb(box)}"
    assert art[3] - art[1] >= 0.97 * (y1 - y0), \
        f"cyclone art spans {art[3] - art[1]:.1f} of its {y1 - y0:.1f} column: it would read as empty"
    CY_STATS.update(r34=round(r34, 1), band=round(r_band, 1), eye=round(eye, 1),
                    annulus=round(100 * ann, 1), span=round(art[3] - art[1], 1))
    c.defs.append(
        f'<radialGradient id="cyg" cx="0.5" cy="0.5" r="0.5">'
        f'<stop offset="0" stop-color="{T["deep"]}" stop-opacity="{num(T["deep_op"] * 2.6, 3)}"/>'
        f'<stop offset="0.55" stop-color="{T["deep"]}" stop-opacity="{num(T["deep_op"] * 1.1, 3)}"/>'
        f'<stop offset="1" stop-color="{T["deep"]}" stop-opacity="0"/></radialGradient>')
    c.add(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r34, 2)}" fill="url(#cyg)"/>'
          f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r34, 2)}" fill="none" stroke="{T["teal"]}" '
          f'stroke-width="1" stroke-dasharray="3 4"/>')
    for k in range(3):
        c.add(f'<path d="{poly_d(_spiral(cx, cy, 2 * math.pi * k / 3, r0), close=False)}" fill="none" '
              f'stroke="{T["coast"]}" stroke-width="1.1" stroke-linecap="round"/>')
    # the radius is drawn like a hero leader: solid and quiet, so only the R34 circle reads as dashed
    c.add(f'<path d="M{num(cx + eye * ux, 2)} {num(cy + eye * uy, 2)}L{num(px, 2)} {num(py, 2)}" '
          f'fill="none" stroke="{T["coast"]}" stroke-width="0.9" opacity="0.8"/>'
          f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(eye, 2)}" fill="{T["shore"]}" '
          f'stroke="{T["coast"]}" stroke-width="1.1"/>'
          f'<path d="M{num(tick[0][0], 2)} {num(tick[0][1], 2)}L{num(tick[1][0], 2)} {num(tick[1][1], 2)}" '
          f'fill="none" stroke="{T["amber"]}" stroke-width="1.6" stroke-linecap="round"/>'
          f'<circle cx="{num(px, 2)}" cy="{num(py, 2)}" r="2.4" fill="{T["amber"]}"/>')
    c.reserve("cyclone art", box, gap=16)
    return art


# --- California water-system clustering schematic ---------------------------------------------------
CA_LAT0 = 37.25       # the state's mid-latitude: the equirectangular projection is true here
# Schematic (not data): hub (lon, lat) + satellite offsets in degrees. The places are plausible
# California settings -- Sacramento Valley, San Joaquin Valley, central coast ranges, inland south --
# but they stand for no real water system and are deliberately unlabelled.
CA_CLUSTERS = [
    ((-121.70, 38.95), [(-0.60, 0.42), (0.52, 0.28), (0.25, -0.55)]),
    ((-120.10, 36.85), [(-0.60, 0.40), (0.62, 0.22), (0.20, -0.55), (-0.45, -0.48)]),
    ((-120.10, 35.55), [(-0.55, 0.25), (0.50, -0.40)]),
    ((-117.55, 34.15), [(0.60, 0.25), (-0.50, 0.45), (0.30, -0.50)]),
]
CA_HUB_R, CA_DOT_R = 3.1, 1.9
CA_MERIDIANS, CA_PARALLELS = (-121.0, -118.0), (35.0, 38.0, 41.0)
CA_STATS: dict = {}


def california_art(c, T, box):
    """Schematic (not data): the real California outline (Natural Earth 50m) drawn as a coastline,
    with a graticule clipped to the state and four unlabelled clusters of water systems joined to a hub."""
    fit = (box[0] + 1, box[1] + 1, box[2] - 1, box[3] - 1)      # 1 unit for the coastline stroke
    view = View.fit(CALIFORNIA, fit, proj=flat(CA_LAT0))
    ring = dp(np.column_stack(view(CALIFORNIA[:, 0], CALIFORNIA[:, 1])), 0.45)
    bb = (ring[:, 0].min(), ring[:, 1].min(), ring[:, 0].max(), ring[:, 1].max())
    assert inside((bb[0] - 0.5, bb[1] - 0.5, bb[2] + 0.5, bb[3] + 0.5), box), \
        f"California outline {fb(bb)} escapes {fb(box)}"
    d = poly_d(ring, close=True)
    grat = ["".join(f"M{num(float(view(lo, 0)[0]))} {num(box[1])}V{num(box[3])}" for lo in CA_MERIDIANS),
            "".join(f"M{num(box[0])} {num(float(view(0, la)[1]))}H{num(box[2])}" for la in CA_PARALLELS)]
    c.defs.append(f'<clipPath id="cac"><path d="{d}"/></clipPath>')
    c.add(f'<path d="{d}" fill="{T["deep"]}" fill-opacity="{T["deep_op"]}"/>'
          f'<g clip-path="url(#cac)"><path d="{"".join(grat)}" fill="none" stroke="{T["rule"]}" '
          f'stroke-width="0.7" stroke-dasharray="2 4"/></g>'
          f'<path d="{d}" fill="none" stroke="{T["coast"]}" stroke-width="1" stroke-linejoin="round"/>')
    dots, clear = [], []
    for hub, offs in CA_CLUSTERS:
        hx, hy = view.pt(hub)
        sats = [view.pt((hub[0] + dx, hub[1] + dy)) for dx, dy in offs]
        dots += [(hx, hy)] + sats
        clear.append(max(math.dist((hx, hy), s) for s in sats))
        c.add("".join(f'<path d="M{num(hx, 2)} {num(hy, 2)}L{num(sx, 2)} {num(sy, 2)}" fill="none" '
                      f'stroke="{T["coast"]}" stroke-width="0.7" opacity="0.7"/>' for sx, sy in sats)
              + "".join(f'<circle cx="{num(sx, 2)}" cy="{num(sy, 2)}" r="{num(CA_DOT_R, 2)}" fill="{T["teal"]}"/>'
                        for sx, sy in sats)
              + f'<circle cx="{num(hx, 2)}" cy="{num(hy, 2)}" r="{num(CA_HUB_R, 2)}" fill="{T["amber"]}"/>')
    pts = np.asarray(dots, float)
    assert _pip(pts, ring).all(), "a water-system dot falls outside California"
    dist = shore_dist(pts, {"ca": [ring]})
    assert dist.min() >= CA_HUB_R + 0.9, f"a dot sits {dist.min():.1f} units from the coastline"
    gap = min(math.dist(a, b) for i, a in enumerate(dots) for b in dots[i + 1:])
    assert gap >= CA_HUB_R + CA_DOT_R + 1.5, f"two water-system dots are {gap:.1f} units apart"
    CA_STATS.update(points=len(ring), scale=round(float(view.s), 2), spoke=round(max(clear), 1),
                    edge=round(float(dist.min()), 1), gap=round(gap, 1))
    c.reserve("california art", box, gap=16)
    return (bb[0] - 0.5, bb[1] - 0.5, bb[2] + 0.5, bb[3] + 0.5)      # the outline plus its stroke


HEAD_PITCH = 29       # baseline step between head lines: 1.26 em at HEAD
DET_PITCH = 24        # baseline step between detail lines
# Every featured card reserves the same 176-unit art column; only the top/bottom inset differs, because
# the cross-section hangs from a waterline while the other three are centred figures.
REPO_ART = dict(section=(lake_section_art, lambda H: (40, min(H - 76, 212), 4)),
                types=(lake_types_art, lambda H: (28, H - 64, 0)),
                cyclone=(cyclone_art, lambda H: (28, H - 64, 0)),
                clusters=(california_art, lambda H: (28, H - 64, 0)))
ART_KEYS = {"lake art", "lake types", "cyclone art", "california art"}   # the keys the four arts reserve
REPO_STATS: dict = {}     # repo -> density numbers, printed in the build report


def build_repo_featured(r, T, theme):
    W = PANEL_W
    ART = 176
    ax1 = PANEL_R
    ax0 = ax1 - ART
    textw = ax0 - 32 - PANEL_L
    # Heads fill the measure rather than balance it: a balanced break splits the head into two middling
    # lines, and beside a 176-unit art column that reads as a gap (see check_repo_density). Heads with a
    # hand-placed '\n' are unaffected - each of their parts already fits on one line.
    lines = wrap(r["head"], SERIF, HEAD, textw, max_lines=2, balance=False)
    det = [ln for d in r["detail"] for ln in wrap(d, SANS, 16, textw)]
    for ln, font, size in [(t, SERIF, HEAD) for t in lines] + [(t, SANS, 16) for t in det]:
        w = measure(ln, font, size)
        assert w <= textw, f"{r['repo']}: {ln!r} sets {w:.0f} units wide, past the {textw}-unit text column"
    # the card grows downwards from a fixed head: only the detail lines and the final height vary
    y_head = 88
    y_det = y_head + HEAD_PITCH * (len(lines) - 1) + 36
    last = y_det + DET_PITCH * (len(det) - 1)
    H = int(math.ceil((last + 24 + 48) / 4) * 4)
    langs = ", ".join(r["langs"])
    c = Canvas(repo_slug(r), W, H, f"{r['repo']}: {plain(r['head'])}",
               sentence("Featured repository card", *r["detail"], f"Built with: {langs}"), T, 1.0)
    panel_bg(c, T)
    inner = (PANEL_INSET + 18, 18, W - PANEL_INSET - 18, H - 12)
    art_fn, art_box = REPO_ART[r["art"]]
    top, bot, right_inset = art_box(H)
    art_col = (ax0, top, ax1 - right_inset, bot)
    art_bb = art_fn(c, T, art_col)

    # each block's ink box is measured as it is drawn, and repo_density compares the gaps between them
    mark = len(c.boxes)
    icon(c, "repo", PANEL_L, 32, 16, T["teal"], within=inner)
    c.text(r["repo"], MONO_M, 17, PANEL_L + 24, 46, T["ink"], within=inner)
    slug_b = ink_since(c, mark)

    mark = len(c.boxes)
    for i, ln in enumerate(lines):
        c.text(ln, SERIF, HEAD, PANEL_L - 1, y_head + HEAD_PITCH * i, T["ink"], within=inner, gap=4)
    head_b = ink_since(c, mark)

    mark = len(c.boxes)
    for i, ln in enumerate(det):
        c.text(ln, SANS, 16, PANEL_L, y_det + DET_PITCH * i, T["muted"], within=inner)
    det_b = ink_since(c, mark)

    rule_y = H - 48
    hline(c, PANEL_L, PANEL_R, rule_y, T["rule"])
    base = H - 22
    mark = len(c.boxes)
    lang_row(c, T, r["langs"], PANEL_L, base, inner)
    lang_b = ink_since(c, mark)
    icon(c, "arrow", PANEL_R - 16, base - cap_h(SANS_M, 15) / 2 - 8, 16, T["teal"], within=inner)
    repo_density(r, c, H, art_col, art_bb, slug_b, head_b, det_b, lang_b, rule_y, textw,
                 (len(lines), len(det)), lines)
    return c.write(theme)


def repo_density(r, c, H, art_col, art_bb, slug_b, head_b, det_b, lang_b, rule_y, textw, rows, head_lines):
    """Measure how densely a featured card is set, so the four can be compared rather than eyeballed.

    text_h  ink height of the text block; gaps  slug -> head -> details -> rule -> languages, ink to ink;
    pad  card edge -> slug ink, and language ink -> card edge; rows  (head lines, detail lines);
    head_fill  each head line's width as a per cent of the text column; text_fill / art_fill / art_h / ink
    are per cent of the text column, the art column, the card height and the whole card respectively.
    """
    def pct(v):
        return round(100 * v, 1)

    card = (PANEL_INSET + 0.5, 0.5, c.w - PANEL_INSET - 0.5, H - 0.5)
    assert sum(1 for b in c.boxes if b["key"] in ART_KEYS) == 1, \
        f"{r['repo']}: its schematic did not reserve the art column under a known key"
    ink = sum((b["box"][2] - b["box"][0]) * (b["box"][3] - b["box"][1])
              for b in c.boxes if b["key"] not in ART_KEYS)     # everything but the schematic: text + icons
    art_a = (art_bb[2] - art_bb[0]) * (art_bb[3] - art_bb[1])
    col_a = (art_col[2] - art_col[0]) * (art_col[3] - art_col[1])
    card_a = (card[2] - card[0]) * (card[3] - card[1])
    REPO_STATS[r["repo"]] = dict(
        H=H, text_h=round(det_b[3] - slug_b[1], 1),
        gaps=[round(head_b[1] - slug_b[3], 1), round(det_b[1] - head_b[3], 1),
              round(rule_y - det_b[3], 1), round(lang_b[1] - rule_y, 1)],
        pad=[round(slug_b[1] - card[1], 1), round(card[3] - lang_b[3], 1)],
        text_fill=pct(ink / (textw * (card[3] - card[1]))),
        art_fill=pct(art_a / col_a), art_h=pct((art_bb[3] - art_bb[1]) / H),
        ink=pct((ink + art_a) / card_a), art=r["art"], rows=rows,
        head_fill=[pct(measure(ln, SERIF, HEAD) / textw) for ln in head_lines])


HEAD_FULL, HEAD_MIN, HEAD_MEAN = 85.0, 55.0, 80.0


def check_repo_density():
    """The four featured cards are read as one block, so they are set to one density: same paddings,
    same detail rhythm, and schematics that span the same fraction of their card."""
    s = [REPO_STATS[r["repo"]] for r in REPOS]
    for r, k in zip(REPOS, s):
        assert k["rows"][0] == 2 and k["rows"][1] >= 2, \
            f"{r['repo']}: text block is {k['rows'][0]} head + {k['rows'][1]} detail lines, not the card rhythm"
        # A head that does not use its measure leaves an empty wedge between the title and the art column,
        # so the thresholds are set just under what the two best-set cards (99/80 and 98/75) achieve.
        f = k["head_fill"]
        assert max(f) >= HEAD_FULL and min(f) >= HEAD_MIN, \
            (f"{r['repo']}: head lines fill {f}% of the text column; a head needs one line >= {HEAD_FULL}% "
             f"and none under {HEAD_MIN}%, or it leaves a gap beside the schematic")
        assert sum(f) / len(f) >= HEAD_MEAN, \
            f"{r['repo']}: head lines fill {f}% of the text column, averaging under {HEAD_MEAN}%"
    pads = {tuple(k["pad"]) for k in s}
    assert len(pads) == 1, f"featured cards do not share their top/bottom padding: {sorted(pads)}"
    centred = [k["art_h"] for k in s if k["art"] != "section"]
    assert max(centred) - min(centred) <= 1.5, \
        f"the centred schematics span different fractions of their cards: {centred}"
    assert min(k["art_h"] for k in s) >= 55, \
        f"a featured schematic spans only {min(k['art_h'] for k in s)}% of its card"
    assert max(k["text_fill"] for k in s) - min(k["text_fill"] for k in s) <= 9, \
        f"featured card text blocks are set at very different densities: {[k['text_fill'] for k in s]}"
    assert min(k["ink"] for k in s) >= 25, \
        f"a featured card carries only {min(k['ink'] for k in s)}% ink and will read as empty"


# ----------------------------------------------------------------------------- education panel
EDUCATION = [
    ("Ph.D.", "Geography, Environment, and Spatial Sciences", "Dual major in Environmental Science and Policy",
     "Michigan State University"),
    ("M.S.", "Computer and Information Technology", None, "University of Pennsylvania"),
    ("M.S.", "Earth and Environmental Engineering", None, "Columbia University"),
    ("B.S.", "Marine Sciences", None, "China University of Geosciences (Beijing)"),
    ("B.B.A.", "Business Administration", None, "China University of Geosciences (Beijing)"),
]
EDU_LABEL_GAP = 16       # minimum ink gap between a degree label and its field
EDU_STATS: dict = {}     # degree label -> ink gap to its field (units), printed in the build report


def edu_alt():
    return "; ".join(f"{d} {f}{' (' + e[0].lower() + e[1:] + ')' if e else ''}, {i}" for d, f, e, i in EDUCATION)


def build_education(T, theme):
    """Survey-station list: degree + field on the left, institution flush right, dotted leaders between."""
    W = PANEL_W
    PITCH, EXTRA = 48, 26
    bases, y = [], 46
    for _, _, extra, _ in EDUCATION:      # a row with an extra line is that much taller
        bases.append(y)
        y += (EXTRA if extra else 0) + PITCH
    H = int(bases[-1] + 28 + 2)
    c = Canvas("education", W, H, "Education", edu_alt(), T, 1.0)
    panel_bg(c, T)
    inner = panel_inner(H)
    # station rail, degree label, field: FX clears the widest degree label by EDU_LABEL_GAP (asserted below)
    SX, DX, FX = PANEL_L + 6, PANEL_L + 26, PANEL_L + 105
    mids = []
    for (deg, field, extra, inst), base in zip(EDUCATION, bases):
        db = c.text(deg, SERIF, 21, DX, base, T["ink"], within=inner, gap=10)
        fb_ = c.text(field, SANS_M, 17, FX, base, T["ink"], within=inner)
        gap = fb_[0] - db[2]
        assert gap >= EDU_LABEL_GAP, f"education: {deg!r} is only {gap:.1f} units from its field"
        EDU_STATS[deg] = min(EDU_STATS.get(deg, 99.0), round(gap, 1))
        ib = c.text(inst, SANS, 16, PANEL_R, base, T["text"], anchor="end", within=inner)
        x0, x1 = fb_[2] + 10, ib[0] - 10
        assert x1 - x0 >= 24, f"education: no room for a leader before {inst}"
        c.add(f'<path d="M{num(x0)} {num(base - 1)}H{num(x1)}" stroke="{T["tick"]}" stroke-width="1.6" '
              f'stroke-dasharray="0 5" stroke-linecap="round"/>')
        if extra:
            c.text(extra, SERIF_I, 18, FX, base + EXTRA, T["teal"], within=inner)
        mids.append(base - cap_h(SANS_M, 17) / 2)
    R = 5.5
    seg = "".join(f"M{SX} {num(a + R + 3)}V{num(b - R - 3)}" for a, b in zip(mids, mids[1:]))
    c.add(f'<path d="{seg}" stroke="{T["tick"]}" stroke-width="1.2"/>')
    for m in mids:
        # every station is a completed degree, so all markers are hollow; a filled amber marker is
        # reserved for "where he is now" (the two appointments on the hero map)
        c.add(f'<circle cx="{SX}" cy="{num(m)}" r="{R}" fill="none" stroke="{T["amber"]}" stroke-width="1.5"/>')
        c.reserve("station", (SX - 6, m - 6, SX + 6, m + 6), within=inner, gap=8)
    return c.write(theme)


# ----------------------------------------------------------------------------- tools panel
TOOLS_LIST = [
    ("Programming", ["Python", "R", "Java", "C/C++", "JavaScript", "Bash/Linux"]),
    ("Machine learning", ["Deep Learning", "Reinforcement Learning", "Ensemble Learning"]),
    ("Geospatial", ["GIS", "Google Earth Engine", "Remote Sensing"]),
    ("Earth system modeling", ["General Lake Model (GLM)", "Variable Infiltration Capacity (VIC)",
                               "Community Land Model (CLM)"]),
    ("Computing & development", ["Docker", "Azure", "Git"]),
]


def tools_alt():
    return "; ".join(f"{l}: {', '.join(i)}" for l, i in TOOLS_LIST)


def build_tools(T, theme):
    """Each group: a small-caps label above its tags; a group that does not fit wraps onto a second line."""
    W = PANEL_W
    CH, PADX, GAPX, GAPY, FS = 32, 12, 7, 8, 15
    top_base, label_gap, group_gap = 40, 10, 30

    def rows_for(items):
        """Greedy line breaking of the chips of one group."""
        rows, row, x = [], [], PANEL_L
        for it in items:
            w = measure(it, SANS_M, FS) + 2 * PADX
            if row and x + w > PANEL_R:
                rows.append(row)
                row, x = [], PANEL_L
            row.append((it, w))
            x += w + GAPX
        rows.append(row)
        return rows

    groups = [(label, rows_for(items)) for label, items in TOOLS_LIST]
    H = top_base
    for i, (_, rows) in enumerate(groups):
        H += label_gap + len(rows) * (CH + GAPY) - GAPY
        H += group_gap if i < len(groups) - 1 else 26
    H = int(H)
    c = Canvas("tools", W, H, "Methods and tools", tools_alt(), T, 1.0)
    panel_bg(c, T)
    inner = panel_inner(H)
    base = top_base
    for label, rows in groups:
        c.text(label.upper(), SANS_SB, 15, PANEL_L, base, T["teal"], tracking=0.1, within=inner)
        cy = base + label_gap
        for row in rows:
            cx = PANEL_L
            for it, w in row:
                assert cx + w <= PANEL_R + 1e-6, f"tools: {it!r} does not fit"
                c.add(f'<rect x="{num(cx + .5)}" y="{num(cy + .5)}" width="{num(w - 1)}" height="{CH - 1}" '
                      f'rx="{(CH - 1) / 2}" fill="{T["chip_fill"]}" stroke="{T["rule"]}"/>')
                c.text(it, SANS_M, FS, cx + PADX, cy + CH / 2 + cap_h(SANS_M, FS) / 2, T["ink"],
                       within=(cx + 4, cy + 2, cx + w - 4, cy + CH - 2), collide=False)
                c.reserve(f"chip {it}", (cx, cy, cx + w, cy + CH), within=(PANEL_L - 1, 12, PANEL_R + 1, H - 8),
                          gap=GAPX - 1)
                cx += w + GAPX
            cy += CH + GAPY
        base = cy - GAPY + group_gap
    return c.write(theme)


# ----------------------------------------------------------------------------- code activity (contribution heatmap)
# Snapshot of the GitHub contribution calendar, stored in activity.json; refresh it with
# refresh_activity.py, which scrapes https://github.com/users/<login>/contributions -- the same calendar
# the profile page draws (the GraphQL viewer query returns a different, lower total). Static until rebuilt.
ACTIVITY = json.loads((HERE / "activity.json").read_text())
HEAT_STEPS = (2, 4, 8)          # 0 | 1-2 | 3-4 | 5-8 | 9+


def heat_level(v):
    if v <= 0:
        return 0
    return 1 + sum(1 for t in HEAT_STEPS if v > t)


def fmt_day(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')} {d.year}"


def activity_stats():
    """(total contributions, days with any activity, busiest day)."""
    flat = [v for week in ACTIVITY["weeks"] for v in week]
    return ACTIVITY["total"], sum(1 for v in flat if v > 0), max(flat)


def activity_alt():
    total, active, top = activity_stats()
    return (f"GitHub contribution heatmap (snapshot): {total} contributions between {fmt_day(ACTIVITY['start'])} and "
            f"{fmt_day(ACTIVITY['end'])}, active on {active} days, busiest day {top} contributions.")


def build_activity(T, theme):
    """A 53x7 contribution heatmap in the cartographic palette, laid out like the other panels."""
    W = PANEL_W
    weeks = ACTIVITY["weeks"]
    total, active, top = activity_stats()
    GAP, LAB = 2.6, 46                       # cell gap; width reserved for the weekday labels
    gx0 = PANEL_L + LAB
    pitch = (PANEL_R - gx0 + GAP) / len(weeks)
    cell = pitch - GAP
    gy0 = 96
    H = int(gy0 + 7 * pitch - GAP + 44)
    c = Canvas("activity", W, H, "Code activity", activity_alt(), T, 1.0)
    panel_bg(c, T)
    inner = panel_inner(H)
    c.runs([(f"{total}", MONO_M, T["ink"]), (" contributions", SANS_M, T["text"])],
           PANEL_L, 42, 17, within=inner, key="total")
    # legend, right-aligned on the same baseline
    lw = 5 * (cell + 4)
    lx = PANEL_R - lw - measure("More", SANS, 15) - 8
    c.text("Less", SANS, 15, lx - 8, 42, T["muted"], anchor="end", within=inner, key="less")
    for i in range(5):
        x = lx + i * (cell + 4)
        c.add(f'<rect x="{num(x)}" y="{num(42 - cell + 1)}" width="{num(cell)}" height="{num(cell)}" rx="2.4" '
              f'fill="{T["heat"][i]}" stroke="{T["heat_edge"]}" stroke-width="0.8"/>')
    c.reserve("legend", (lx, 42 - cell + 1, lx + lw, 43), within=inner, gap=6)
    c.text("More", SANS, 15, PANEL_R, 42, T["muted"], anchor="end", within=inner, key="more")
    # month labels: the first week of each month, provided there is room since the last label
    start = datetime.date.fromisoformat(ACTIVITY["start"])
    last_x, seen = -1e9, set()
    for wi in range(len(weeks)):
        d = start + datetime.timedelta(days=7 * wi)
        key = (d.year, d.month)
        x = gx0 + wi * pitch
        if key not in seen and d.day <= 7 and x - last_x > 52:
            seen.add(key)
            lx = min(x, PANEL_R - measure(d.strftime("%b"), SANS, 15))   # clamp the last label inside
            c.text(d.strftime("%b"), SANS, 15, lx, gy0 - 12, T["muted"], within=inner, key=f"m{wi}", gap=6)
            last_x = x
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = gy0 + row * pitch + cell / 2 + cap_h(SANS, 15) / 2
        c.text(label, SANS, 15, gx0 - 12, y, T["muted"], anchor="end", within=inner, key=label, gap=4)
    # the grid itself (decorative marks, reserved as one block)
    by_level = {}
    for wi, week in enumerate(weeks):
        for di, v in enumerate(week):
            x, y = gx0 + wi * pitch, gy0 + di * pitch
            by_level.setdefault(heat_level(v), []).append(
                f'<rect x="{num(x)}" y="{num(y)}" width="{num(cell)}" height="{num(cell)}" rx="2.4"/>')
    for lvl in sorted(by_level):
        c.add(f'<g fill="{T["heat"][lvl]}" stroke="{T["heat_edge"]}" stroke-width="0.8">{"".join(by_level[lvl])}</g>')
    grid = (gx0, gy0, PANEL_R, gy0 + 7 * pitch - GAP)
    c.reserve("grid", grid, within=inner, gap=6)
    c.text(f"Snapshot \u00b7 {fmt_day(ACTIVITY['start'])} \u2013 {fmt_day(ACTIVITY['end'])} \u00b7 active on "
           f"{active} days \u00b7 busiest day {top}", SANS, 15, PANEL_L, H - 16, T["muted"], within=inner, key="caption")
    return c.write(theme)


def build_footer(T, theme):
    W, H = PANEL_W, 80
    c = Canvas("footer", W, H, "East Lansing, MI (42.73 N, 84.48 W) and Ann Arbor, MI (42.28 N, 83.74 W)",
               "Closing plate with a small Great Lakes locator map and the coordinates of both appointments.", T, 1.0)
    cx = W / 2
    view = mini_map(c, T, (cx - 52, 6, cx + 52, 74), "fm", highlight=None, both=False)
    for loc in (EAST_LANSING, ANN_ARBOR):
        x, y = view.pt(loc)
        c.add(f'<circle cx="{num(x)}" cy="{num(y)}" r="2.6" fill="{T["amber"]}"/>')
    l1 = c.text("East Lansing, MI", SERIF_I, 19, cx - 76, 36, T["ink"], anchor="end")
    l2 = c.text("42.73° N · 84.48° W", MONO, 15, cx - 76, 60, T["muted"], anchor="end")
    r1 = c.text("Ann Arbor, MI", SERIF_I, 19, cx + 76, 36, T["ink"])
    r2 = c.text("42.28° N · 83.74° W", MONO, 15, cx + 76, 60, T["muted"])
    xl = min(l1[0], l2[0]) - 20
    xr = max(r1[2], r2[2]) + 20
    e0, e1 = PANEL_INSET + 0.5, W - PANEL_INSET - 0.5
    hline(c, e0, xl, 40, T["rule"])
    hline(c, xr, e1, 40, T["rule"])
    c.add(f'<path d="M{num(e0)} 36v8M{num(e1)} 36v8" stroke="{T["tick"]}"/>')
    return c.write(theme)


# ----------------------------------------------------------------------------- colour checks
def _lum(h):
    """Relative luminance of a #rrggbb colour, per WCAG 2.1."""
    def lin(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(int(h.lstrip("#")[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def blend(a, b, t):
    pa = [int(a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    pb = [int(b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def check_colors():
    report = []
    for theme, T in THEMES.items():
        # text can sit on the hero paper, a card, a chip or (outline-only cards) straight on the GitHub page
        bgs = {"paper": T["paper"], "card": T["card"], "chip": T["chip"], **{f"page {p}": p for p in T["pages"]}}
        worst = (99, "")
        for fg in ("ink", "text", "muted", "teal", "amber_t"):
            for bn, bg in bgs.items():
                r = contrast(T[fg], bg)
                assert r >= 4.5, f"{theme}: {fg} on {bn} = {r:.2f}"
                worst = min(worst, (r, f"{fg}/{bn}"))
        deepest = blend(T["shore"], T["deep"], 1 - (1 - T["deep_op"]) ** 5)
        for bg in (T["shore"], deepest):
            r = contrast(T["lakelabel"], bg)
            assert r >= 4.5, f"{theme}: lake label on {bg} = {r:.2f}"
        contour = blend(T["shore"], T["contour"], T["contour_op"])
        report.append(f"{theme}: weakest text {worst[1]} {worst[0]:.2f}; lake label/shore {contrast(T['lakelabel'], T['shore']):.2f}; "
                      f"contour/shore {contrast(contour, T['shore']):.2f}; coast/shore {contrast(T['coast'], T['shore']):.2f}; "
                      f"lake/paper {contrast(T['shore'], T['paper']):.2f}; graticule/paper {contrast(T['grat'], T['paper']):.2f}")
    return report


# ----------------------------------------------------------------------------- README
def pic(name, alt, width, height=None, href=None):
    dark, light = f"{RAW}{name}-dark.svg", f"{RAW}{name}-light.svg"
    h = f' height="{height}"' if height else ""
    s = (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{dark}">'
         f'<source media="(prefers-color-scheme: light)" srcset="{light}">'
         f'<img alt="{esc(alt)}" src="{light}" width="{width}"{h}></picture>')
    return f'<a href="{esc(href)}">{s}</a>' if href else s


def repo_alt(r):
    return f"{r['repo']} - " + sentence(r["head"], *r["detail"], "Languages: " + ", ".join(r["langs"]))


def readme():
    sec = {s[0]: s for s in SECTIONS}

    def S(name):                    # a full-width section heading strip
        return pic(name, sec[name][2], "100%")

    # cards that belong together share one <p>; <br> separates rows, so the vertical gutter (~6 px of line
    # descent) matches the horizontal one (one space, ~4.4 px) instead of a 16 px paragraph margin
    rows = ["\n".join(pic(n, LINK_ALT[n], BTN_W[n], BTN_H, href=url) for n, _, _, url in row) for row in BTN_ROWS]
    buttons = "<br>\n".join(rows)
    appt_url = {"appt-csis": "https://csis.msu.edu/", "appt-ciglr": "https://ciglr.seas.umich.edu/"}
    appts = "\n".join(pic(a["name"], a["line"], "49%", href=appt_url[a["name"]]) for a in APPOINTMENTS)
    code = "<br>\n".join(pic(repo_slug(r), repo_alt(r), "100%", href=GH + r["repo"]) for r in REPOS)
    focus_alt = "Research focus: " + "; ".join(focus_pairs())
    return f"""<!-- Generated by build.py (variant: Great Lakes Cartography). Edit build.py and re-run it instead of editing this file. -->

{pic("hero", "Xin (Shane) Lan, Ph.D. - water systems, artificial intelligence, metacoupling. Map of the Great Lakes marking CSIS at Michigan State University (East Lansing) and CIGLR at the University of Michigan (Ann Arbor).", "100%", href="https://xinlan-science.github.io/")}

<p align="center">
{buttons}
</p>

Hydrologist and interdisciplinary researcher working at the intersection of **water systems**, **artificial intelligence**, and **metacoupling**. I combine process-based modeling and data-driven methods to study water dynamics and human&ndash;nature interactions across space.

{S("sec-appointments")}

<p align="center">
{appts}
</p>

{S("sec-research")}

{pic("focus", focus_alt, "100%")}

{S("sec-code")}

<p align="center">
{code}
</p>

{S("sec-education")}

{pic("education", "Education: " + edu_alt(), "100%")}

{S("sec-tools")}

{pic("tools", "Methods and tools - " + tools_alt(), "100%")}

{S("sec-activity")}

{pic("activity", activity_alt(), "100%")}

{pic("footer", "East Lansing, MI (42.73 N, 84.48 W) and Ann Arbor, MI (42.28 N, 83.74 W)", "100%")}

"""


# ----------------------------------------------------------------------------- page-level checks
SPACE_PX = 4.4


def page_report():
    """Rendered size of the page on desktop, from the generated assets (px)."""
    def h(name):
        """Displayed height of a full-width asset."""
        svg = (ASSETS / f"{name}-light.svg").read_text()
        vb = [float(v) for v in svg.split('viewBox="', 1)[1].split('"', 1)[0].split()]
        return vb[3] * DESKTOP_W / vb[2]

    pair = 2 * 0.49 * DESKTOP_W + SPACE_PX
    off = (DESKTOP_W - pair) / 2
    card_edge = off + 0.5 * 0.49 * DESKTOP_W / CARD_W
    panel_edge = (PANEL_INSET + 0.5) * DESKTOP_W / PANEL_W
    hero_edge = 9.6 * DESKTOP_W / HERO_W
    return dict(card_edge=round(card_edge, 2), panel_edge=round(panel_edge, 2), hero_edge=round(hero_edge, 2),
                hero_h=round(h("hero")), focus_h=round(h("focus")), education_h=round(h("education")),
                tools_h=round(h("tools")), activity_h=round(h("activity")))


# ----------------------------------------------------------------------------- main
def main():
    ASSETS.mkdir(exist_ok=True)
    for f in ASSETS.glob("*.svg"):
        f.unlink()
    MANIFEST.clear()
    check_focus_symbols()
    colors = check_colors()
    for theme, T in THEMES.items():
        build_hero(T, theme)
        for a in APPOINTMENTS:
            build_appointment(a, T, theme)
        for s in SECTIONS:
            build_section(s, T, theme)
        for b in LINKS:
            build_button(b, T, theme)
        build_focus(T, theme)
        for r in REPOS:
            build_repo_featured(r, T, theme)
        build_education(T, theme)
        build_tools(T, theme)
        build_activity(T, theme)
        build_footer(T, theme)
    row_w = [sum(BTN_W[n] for n, *_ in row) + SPACE_PX * (len(row) - 1) for row in BTN_ROWS]
    assert max(row_w) <= BTN_ROW_MAX, f"a link-button row needs {max(row_w):.0f}px (> {BTN_ROW_MAX})"
    check_repo_density()
    (ASSETS / "manifest.json").write_text(json.dumps(MANIFEST, indent=1) + "\n")
    (OUT / "README.md").write_text(readme())
    sizes = sorted(((f.stat().st_size, f.name) for f in ASSETS.glob("*.svg")), reverse=True)
    light_kb = sum(sz for sz, n in sizes if n.endswith("-light.svg")) / 1e3
    print(f"wrote {len(sizes)} SVGs (largest {sizes[0][1]} {sizes[0][0] / 1e3:.0f} KB; light set {light_kb:.0f} KB), manifest, README.md")
    print(f"link rows {[round(w) for w in row_w]}px; california art {CA_STATS}; cyclone art {CY_STATS}")
    for r in REPOS:
        s = REPO_STATS[r["repo"]]
        print(f"card {r['repo']}: H {s['H']} text_h {s['text_h']} gaps {s['gaps']} pad {s['pad']} "
              f"head_fill {s['head_fill']}% text_fill {s['text_fill']}% art_fill {s['art_fill']}% "
              f"art_h {s['art_h']}% ink {s['ink']}%")
    print(f"education label->field gaps {EDU_STATS}")
    print(f"hero {HERO_STATS}; focus {FOCUS_STATS}")
    print(f"focus symbols {SYM_STATS}")
    print(f"page {page_report()}")
    for line in colors:
        print("contrast", line)


if __name__ == "__main__":
    main()
