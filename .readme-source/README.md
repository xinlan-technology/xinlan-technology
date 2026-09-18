# Profile README generator

`build.py` draws the whole profile page: every SVG in `assets/` (a light and a dark
version of each), `assets/manifest.json`, and `README.md` itself.

**`/README.md` and `/assets/` are generated. Do not hand-edit them** — running `build.py`
overwrites both. Edit `build.py` and re-run it, then commit what it wrote.

## Regenerate

```sh
pip install fonttools uharfbuzz numpy
python .readme-source/build.py   # writes README.md + assets/
```

Run it from the repository root. `build.py` detects that it lives in `.readme-source/`
and writes to the repo root; it prints a layout report and fails on any assertion, so a
clean exit means the page is laid out within its own constraints.

## Things a future editor needs to know

- **Text is outlined, not set in a font.** `tools/svgtext.py` converts every string to
  SVG paths, because github.com renders these assets through `<img>`, where an SVG cannot
  load a web font (and system fonts differ per OS). Consequence: only the faces in
  `tools/fonts/*.woff` exist, Latin only, no emoji — draw icons as shapes.
- **Light/dark are two separate files** per image, paired in the README with `<picture>`
  and a `prefers-color-scheme` source. Both must exist for every asset.
- **Map data** lives in `tools/data/*.geojson` (Natural Earth outlines, already simplified).
  Re-simplifying changes the drawn page.
- In copy, `~` glues two words together and `\n` forces a line break; list items separated
  by ` · ` never split across lines.
- The markers pulse with CSS, disabled under `prefers-reduced-motion`.
