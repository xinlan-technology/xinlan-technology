#!/usr/bin/env python3
"""Render a profile README the way GitHub does, as local HTML previews (no screenshots, no browser launch).

Usage:  python3 render.py <variant_dir> [--width 896]

- Sends <variant_dir>/README.md through GitHub's real Markdown API (`gh api markdown`),
  so the HTML goes through GitHub's sanitizer (style/class/script are stripped just like on github.com).
- Wraps it in github-markdown-css inside a box sized like the README card on a GitHub profile page
  (896px card => ~846px content at a 1280px-wide desktop).
- Writes <variant_dir>/_preview_{light,dark}.html for the user to open themselves, plus _preview/sanitized.html.
- <picture><source media="(prefers-color-scheme: dark|light)"> is resolved per theme, as GitHub does.
- Asset URLs https://raw.githubusercontent.com/xinlan-technology/xinlan-technology/main/assets/... are mapped to
  <variant_dir>/assets/... so the preview shows the local files.
"""
import json, os, re, subprocess, sys, tempfile, pathlib, shutil

TOOLS = pathlib.Path(__file__).resolve().parent
RAW_PREFIX = "https://raw.githubusercontent.com/xinlan-technology/xinlan-technology/main/"
CSS = {"light": TOOLS / "github-markdown-light.css", "dark": TOOLS / "github-markdown-dark.css"}
BG = {"light": ("#ffffff", "#d1d9e0"), "dark": ("#0d1117", "#3d444d")}


def ensure_css():
    for theme, p in CSS.items():
        if not p.exists():
            subprocess.run(["curl", "-sfL", "-o", str(p),
                            f"https://cdn.jsdelivr.net/npm/github-markdown-css@5/github-markdown-{theme}.css"], check=True)


def gh_markdown(md: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"text": md, "mode": "gfm"}, f)
        req = f.name
    out = subprocess.run(["gh", "api", "markdown", "--input", req], capture_output=True, text=True)
    os.unlink(req)
    if out.returncode != 0:
        sys.exit(f"gh api markdown failed: {out.stderr}")
    html = out.stdout
    # GitHub proxies external images through camo; point straight at the original so previews don't depend on camo.
    html = re.sub(r'src="https://camo\.githubusercontent\.com/[^"]+"\s+data-canonical-src="([^"]+)"', r'src="\1"', html)
    # GitHub wraps images in <a target=_blank href=...>; harmless. Strip the anchor-link octicons in headings for clarity.
    # README references this repo's assets by absolute raw URL (what github.com will load);
    # map them to the local copies so the preview shows the files being worked on.
    html = html.replace(RAW_PREFIX, "")
    return html


def bust(html: str, vdir: pathlib.Path) -> str:
    """Append ?v=<mtime> to local asset URLs so a reloaded preview never shows cached, stale images."""
    def sub(m):
        attr, url = m.group(1), m.group(2)
        f = vdir / url.lstrip("./")
        return f'{attr}="{url}?v={int(f.stat().st_mtime)}"' if f.exists() else m.group(0)
    return re.sub(r'(src|srcset)="([^"http][^":]*)"', sub, html)


def resolve_theme(html: str, theme: str) -> str:
    other = "light" if theme == "dark" else "dark"
    # drop <source> elements for the other theme; make this theme's sources unconditional
    html = re.sub(r'<source[^>]*prefers-color-scheme:\s*%s[^>]*>' % other, "", html)
    html = re.sub(r'media="\(prefers-color-scheme:\s*%s\)"' % theme, 'media="all"', html)
    return html


def page(body: str, theme: str, width: int) -> str:
    bg, border = BG[theme]
    css = CSS[theme].read_text()
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>{css}
html,body{{margin:0;background:{bg};}}
.wrap{{padding:16px;}}
.markdown-body{{box-sizing:border-box;width:100%;max-width:{width}px;margin:0 auto;padding:24px;border:1px solid {border};border-radius:6px;}}
.markdown-body .anchor{{display:none}}
</style></head><body><div class="wrap"><article class="markdown-body">{body}</article></div></body></html>"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    vdir = pathlib.Path(sys.argv[1]).resolve()
    width = int(sys.argv[sys.argv.index("--width") + 1]) if "--width" in sys.argv else 896
    ensure_css()
    body = gh_markdown((vdir / "README.md").read_text())
    out = vdir / "_preview"
    out.mkdir(exist_ok=True)
    (out / "sanitized.html").write_text(body)
    for theme in ("light", "dark"):
        # page lives in vdir so relative asset paths resolve
        hp = vdir / f"_preview_{theme}.html"
        hp.write_text(page(bust(resolve_theme(body, theme), vdir), theme, width))
        print(f"wrote {hp}")
    print(f"sanitized HTML: {out / 'sanitized.html'}")


if __name__ == "__main__":
    main()
