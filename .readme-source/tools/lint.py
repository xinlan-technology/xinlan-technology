#!/usr/bin/env python3
"""Code-only checks for a profile README variant (no browser, no screenshots).

Usage:
  design/tools/.venv/bin/python design/tools/lint.py <variant_dir>
  design/tools/.venv/bin/python design/tools/lint.py --contrast "#0b1f33" "#ffffff"

Checks:
  * README goes through GitHub's real sanitizer (gh api markdown); reports attributes GitHub strips (style/class/...)
  * every image referenced exists locally (repo raw URLs map to <variant_dir>/assets/...) or loads over HTTP as an image
  * every <picture> has a dark <source> and an <img> fallback; every <img> has alt text
  * every SVG: well-formed, has viewBox, no <text> (must be outlined paths), no script/foreignObject/external refs,
    light/dark pairs exist (*-light.svg <-> *-dark.svg), size budget
  * assets/manifest.json (written by build.py) -> effective smallest text size on desktop and on phones
  * outbound links respond (warnings only; some sites block bots)
Writes the HTML previews too (render.py). Exit code 1 if any ERROR.

manifest.json format (list):
  [{"file": "hero-light.svg", "viewbox_w": 1200, "min_font": 14, "display_frac": 1.0}, ...]
  display_frac = fraction of the README content width the image occupies (1.0 for width="100%", 0.49 for side-by-side).
"""
import json, pathlib, re, sys, urllib.request, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import render  # noqa: E402

DESKTOP_W, MOBILE_W = 846, 340   # README content width on a 1280px desktop / a 390px phone
errors, warns = [], []
E = lambda m: errors.append(m)
W = lambda m: warns.append(m)


def rel_lum(hexc):
    hexc = hexc.lstrip("#")
    r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((rel_lum(a), rel_lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def fetch_ok(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (readme-lint)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers.get("Content-Type", "")
    except Exception as e:  # noqa: BLE001
        return getattr(e, "code", None) or str(e)[:60], ""


def check_svg(p: pathlib.Path):
    size = p.stat().st_size
    if size > 1_000_000:
        E(f"{p.name}: {size/1e3:.0f} KB (>1 MB)")
    elif size > 400_000:
        W(f"{p.name}: {size/1e3:.0f} KB (large; simplify paths / lower precision)")
    try:
        root = ET.parse(p).getroot()
    except ET.ParseError as e:
        E(f"{p.name}: invalid XML: {e}")
        return
    if not root.get("viewBox"):
        E(f"{p.name}: root <svg> has no viewBox")
    tags = {el.tag.split('}')[-1] for el in root.iter()}
    for bad in ("text", "tspan", "textPath"):
        if bad in tags:
            E(f"{p.name}: contains <{bad}> - outline text with svgtext.text_path (fonts are not reliable on github.com)")
    for bad in ("script", "foreignObject", "iframe"):
        if bad in tags:
            E(f"{p.name}: contains <{bad}> (blocked / unsafe on github.com)")
    raw = p.read_text()
    if re.search(r'(?:href|src)\s*=\s*"https?://', raw) or re.search(r'url\(\s*["\']?https?://', raw) or "@import" in raw:
        E(f"{p.name}: references an external resource (SVG-as-image cannot load it)")
    if "<title" not in raw:
        W(f"{p.name}: no <title> (accessibility)")


def main():
    if sys.argv[1:2] == ["--contrast"]:
        a, b = sys.argv[2], sys.argv[3]
        c = contrast(a, b)
        print(f"{a} on {b}: {c:.2f}:1  (AA body >= 4.5, AA large/UI >= 3)")
        return
    vdir = pathlib.Path(sys.argv[1]).resolve()
    md = (vdir / "README.md").read_text()
    render.ensure_css()
    body = render.gh_markdown(md)   # raw URLs of this repo already mapped to relative paths

    # --- sanitizer losses
    for attr in ("style", "class"):
        n = len(re.findall(rf'\s{attr}\s*=', md))
        if n:
            W(f"README uses {attr}= {n}x - GitHub strips it, so it has no effect")
    for tag in ("script", "style", "iframe", "svg", "button", "input", "font"):
        if re.search(rf"<{tag}[\s>]", md, re.I) and not re.search(rf"<{tag}[\s>]", body, re.I):
            W(f"README uses <{tag}> - GitHub removes it")

    # --- images
    srcs = re.findall(r'<img[^>]*\ssrc="([^"]+)"', body) + re.findall(r'<source[^>]*\ssrcset="([^"]+)"', body)
    local, remote = set(), set()
    for s in srcs:
        (remote if s.startswith("http") else local).add(s)
    for s in sorted(local):
        f = (vdir / s.lstrip("./")).resolve()
        if not f.exists():
            E(f"image not found locally: {s}")
    with ThreadPoolExecutor(8) as ex:
        for s, (st, ct) in zip(sorted(remote), ex.map(fetch_ok, sorted(remote))):
            if st != 200 or not ct.startswith("image"):
                E(f"remote image broken ({st} {ct}): {s[:100]}")
    for m in re.finditer(r'<img\b[^>]*>', body):
        if 'alt="' not in m.group(0) or 'alt=""' in m.group(0):
            W(f"img without alt: {m.group(0)[:90]}")
    for m in re.finditer(r'<picture>(.*?)</picture>', body, re.S):
        inner = m.group(1)
        if "prefers-color-scheme: dark" not in inner:
            W(f"<picture> without a dark source: {inner.strip()[:80]}")
        if "<img" not in inner:
            E("<picture> without <img> fallback")
    if "raw.githubusercontent.com/xinlan-technology/xinlan-technology/main/assets" not in md and local:
        W("README uses relative asset paths; prefer https://raw.githubusercontent.com/xinlan-technology/xinlan-technology/main/assets/<file> (proven on this profile)")

    # --- svgs
    assets = vdir / "assets"
    svgs = sorted(assets.glob("*.svg")) if assets.exists() else []
    referenced = {pathlib.Path(s).name for s in local}
    for p in svgs:
        check_svg(p)
        if p.name not in referenced:
            W(f"asset not referenced by README: {p.name}")
        for a, b in (("-light.svg", "-dark.svg"), ("-dark.svg", "-light.svg")):
            if p.name.endswith(a) and not (assets / p.name.replace(a, b)).exists():
                E(f"{p.name}: missing {b[1:-4]} counterpart")

    # --- legibility from manifest
    man = assets / "manifest.json"
    if man.exists():
        for it in json.loads(man.read_text()):
            k = it["display_frac"] / it["viewbox_w"] * it["min_font"]
            d, mo = k * DESKTOP_W, k * MOBILE_W
            line = f"{it['file']}: smallest text ~{d:.1f}px desktop, ~{mo:.1f}px phone"
            if d < 11 or mo < 6:
                W(line + "  <- too small")
            else:
                print("OK   ", line)
    elif svgs:
        W("no assets/manifest.json - cannot check text legibility")

    # --- links
    hrefs = sorted({h for h in re.findall(r'href="(https?://[^"]+)"', body) if "raw.githubusercontent" not in h})
    with ThreadPoolExecutor(8) as ex:
        for h, (st, _) in zip(hrefs, ex.map(fetch_ok, hrefs)):
            if st != 200:
                W(f"link returned {st}: {h[:100]}")

    # --- previews
    for theme in ("light", "dark"):
        (vdir / f"_preview_{theme}.html").write_text(
            render.page(render.bust(render.resolve_theme(body, theme), vdir), theme, 896))

    for m in warns:
        print("WARN ", m)
    for m in errors:
        print("ERROR", m)
    print(f"\n{len(errors)} error(s), {len(warns)} warning(s). Previews: {vdir}/_preview_light.html, _preview_dark.html")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
