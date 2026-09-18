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

The script resolves paths from its own location, so it can run from any working directory.
It prints a layout report and validates both themes before replacing generated files.
Only obsolete SVGs listed in the previous manifest are removed; unrelated files are preserved.
Do not use `python -O` or `PYTHONOPTIMIZE`: the generator requires its layout assertions.

## Verify

```sh
python -m unittest discover -s .readme-source -v
```

Tests cover line wrapping, SVG number formatting, map simplification, light/dark asset
references, repeatable builds, and preservation of existing files when validation fails.

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
