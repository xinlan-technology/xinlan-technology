# Great Lakes Cartography: notes

- **Concept.** The profile is laid out like a page from an atlas. The hero is a name plate beside a map of the real Great Lakes (Natural Earth outlines) in a Lambert conformal conic projection. The map sits in a curved frame with a graticule, degree ticks and a true 200 km scale bar; the frame runs 39.5–50° N, 92.5–75.5° W. Lake depth is suggested by shading and by contour lines stepping inward from each shore. These are an offset effect, not survey data. Lake names are set in italic serif and the contours break around them. Amber markers are labelled like places on a map: "CSIS · East Lansing" and "CIGLR · Ann Arbor".
  - **The scale bar sits inside the map sheet**, in its lower-right corner, the way an atlas plate prints
    its scale inside the neatline rather than in the caption below it. It used to be pushed against the
    right end of the bottom strip, a hand's width from the keywords. Bar and labels are unchanged — a
    four-segment bar with its outline as end ticks, "0" and "200 km" in Inter — and it keeps true scale:
    78.6 units is 200 km at the projection's own factor at 44° N (`bar ground length 199.99 km`). The
    labels run at 21.5 rather than 22 (the hero's floor, 6.09 px on a 340 px phone).
    - **Where, and why not under the sheet.** The other candidate was a line under the sheet's bottom
      frame, right-aligned to it. There is no room: the bottom neatline is a conic arc that dips to
      y = 508 at the central meridian, its degree ticks reach y = 511.7 under the right-hand 188 units,
      and the strip rule is at y = 536 — a 24.3-unit band for a 16.1-unit block, i.e. 4.1 units of air
      above and below, and the hero may not grow. Inside the sheet the lower-right is the emptiest
      quarter of the map: no shoreline comes within 48 units.
    - **Position and clearances** (built and asserted, build report `hero ... scale_box / scale_gap`):
      block ink (876.0, 473.2) – (1064.1, 489.2), bar x 898.7–977.3 at y 478.2–484.2, labels on
      baseline 489.0. Shoreline 48.6, map frame (neatline) 9.6, frame tick 11.3, leader line 9.6,
      callout 18.4, marker 79.3. The build asserts the block is on the sheet, dry, and ≥ 20 / 9 / 9 / 9 /
      12 / 20 units from those six in turn.
    - **How it is placed** — nothing is hand-tuned: the "200 km" ink ends flush with the right edge of
      the "CIGLR · Ann Arbor" callout right above it (asserted to 0.01 units), so the two read as one
      right-aligned block of marginalia; and the baseline is centred in the band of open paper between
      that callout's leader shelf (y 463.5) and the highest point of the bottom neatline under the
      block's own measure (y 498.9), which is what balances 9.6 above against 9.6 below.
    - **Knock-out.** The 40° N parallel and three meridians would otherwise run straight through the bar
      (90 and 4 sampled crossings). The block is added to the same `gm` mask the callouts use, so the
      graticule is cut 6 units around it exactly as it is around "CSIS · East Lansing". Its knock-out
      meets the CIGLR callout's, so the lower right has one clean cut rather than a sliver between two;
      the 40° N parallel keeps a 314-unit run to the west and a 56-unit run to the neatline in the east.
  - **The bottom strip is now one centred keyword line.** With the bar gone the strip carries only
    "WATER SYSTEMS · ARTIFICIAL INTELLIGENCE · METACOUPLING" (Inter 21.5, tracking 0.14, 861 units in the
    1072-unit measure — 80.3% fill). There was nothing to make more deliberate at the right end: the rule
    already runs the full measure between the margins (x 64 → 1136) and carries no ticks of its own, and
    the strip holds no other content that could be right-aligned without inventing some. Left-aligned at
    X0 the line would have left 211 units of dead measure (20%, 149 px on desktop) under the map's right
    edge — the visible half of a two-item line that lost its other half. Centred, it sits on the plate's
    own axis (x 600, the axis its rule already spans symmetrically) with 106.0 / 106.7 units of paper at
    the two ends, and reads as the plate's caption. The build asserts the two ends match within 1 unit
    (`strip_ends` in the hero report). Baseline, size, colour and wording are untouched.
- **Page structure.**
  - Each section heading has a numbered title, a rule with scale-bar ticks, and a small contour glyph of one lake (Superior → Simcoe). The glyph sits in a fixed slot flush with the card edge.
  - The appointment cards carry locator maps.
  - **Research focus** is six uniform rows, one per focus area (rows 68 units tall; the panel is 408 units,
    423 px on desktop), with the same vertical rule down the middle and the same hairline rules between rows.
    Every row is built the same way and carries the same amount: a 40-unit icon tile, one heading line
    (Source Serif 22) in a fixed left column and one caption line (Inter 15) starting at one common x on the
    far side of the divider — heading and caption share a baseline, and there is no mixture of one- and
    two-line rows. Uniformity is enforced rather than eyeballed: both lines are wrapped with `max_lines=1`,
    so any wording that would wrap fails the build, and every row then has the same geometry (tiles at
    y = 14.5 + 68 r, headings at x = 96, captions at x = 432, baseline 41.3 into the row). The build prints
    the grid, the tile and baseline, the two column widths and the heading/caption fill of every row.
    - **Why one column.** The settled copy put the captions, not the headings, at the top of the measure:
      "Water resources and human–water interactions" is 334 units at Inter 15, and 15 is the floor (a smaller
      caption drops under 6 px on a phone). A 2 × 3 grid cannot hold that — the content edge to the midline is
      370 units, so even with no gutter at the divider a 36-unit tile and a 10-unit gap leave the text 324 —
      and shrinking the text was not an option, so the layout changed instead of the wording. Side by side in
      one column the caption gets 346 units (96.5% at its widest) and the heading 288 (90.2%, "Water systems
      modeling"; "Large Language Models" is 86.5%), with the lightest row, "Metacoupling", at 50.7%. Stacking
      the caption under the heading instead would have given the same widths for half again the height
      (100-unit rows, 600 units), so the rows carry both lines.
      The panel grew 300 → 408 units (311 → 423 px), which puts it between the education panel (305 px) and
      the tools panel (452 px) rather than above them.
  - The research code section is four full-width featured cards, all built the same way: title block on the left, a 176-unit art column on the right, a rule, then the language dots. Each carries its own schematic, drawn in the same thin cartographic line style and in the theme palette — a lake cross-section (process-guided DL), a plate of six lake outlines (static–dynamic lake model), a tropical cyclone (hurricane R34) and the real California outline (water-system consolidation). Every card is set to one density: the same top/bottom padding (31.5 / 18.4 units), the same rhythm of two head lines over two or three detail lines, and a height that follows that text — 276, 252, 252, 252 units. The build prints the numbers per card (`card <repo>: H … head_fill … text_fill … art_fill … art_h … ink …`) and asserts them, so "this one looks emptier" is a measurement rather than an opinion. The last two were the loose ones: each had a single detail line and a schematic that sat small in its column (text_fill 20.3/20.0%, art_h 53.4/59.2%, ink 21.6/21.9%); with a second detail line and schematics scaled to their column they read at 63.3/63.1% art_h and, after the retitling below, 33.0/32.9% text_fill and 34.4/32.6% ink against 28.5/30.6% and 30.9/34.2% for the first two. `art_fill` stays lower for California (77%) than for the lake plate (100%) only because the state is a narrow shape in a 176-unit column; it fills the column's height like the rest.
    - **Title fill.** Their heads were also too short for the 532-unit text column — two middling lines with an empty wedge running down to the schematic (61.7/48.5% and 49.4/66.0% of the measure). The titles now carry the facts the detail lines used to repeat ("… (R34) from 6-hourly and hourly ERA5 inputs", "… to explore consolidation potential") and run 99.1/91.7% and 98.6/88.1%; the detail lines were rewritten so nothing is said twice. Featured heads are broken to **fill** the measure, not to balance it (`wrap(…, balance=False)`): a balanced break spends the extra room on the second line, which is exactly the gap being fixed. The first two cards place their breaks by hand (`\n`), so they are untouched by this and their fullest line is the second one. `head_fill` is printed per card and asserted: the fullest head line runs ≥ 85% of the column, no line falls under 55%, and the lines average ≥ 80% (80.3/99.3% and 97.8/74.9% for the first two cards).
    - **Cyclone** (schematic, no data): centred in the art box and sized from it — the figure is a circle, so the R34 ring plus its amber tick and the widest stroke just touch the shorter side of the column (r ≈ 78.8 in a 176 × 160 box). Eye r ≈ 7.9 (0.10 R34); three logarithmic spiral bands `r = r₀·e^{0.30θ}` swept 5.05 rad (~289°) at 0/120/240°, reaching 0.88 R34 ≈ 69.4, so the dashed teal 34-kt wind radius sits a 12% annulus outside the outermost band instead of standing off in empty space. A solid radius line at 38° carries an amber tick plus dot where it meets the circle. Nothing is labelled and no value is implied.
    - **California** (real outline, schematic clusters): Natural Earth 50m, one ring, equirectangular true at 37.25° N, Douglas–Peucker at 0.45 units (252 → 92 points), scale 16.69 units/degree. A graticule (121° W, 118° W; 35/38/41° N) is clipped to the state. Four unlabelled clusters — an amber hub with 2–4 teal dots on thin spokes (longest spoke 10.6 units) — sit in the Sacramento Valley, the San Joaquin Valley, the central coast ranges and the inland south. The clusters are placed in degrees, so they grow with the outline; they are checked point-in-polygon, kept ≥ 5.8 units off the coastline and ≥ 8.3 units apart. No real water system is named, located or counted.
    - **The six focus symbols** are all drawn on one 64-unit grid and shown at 40 — unchanged by the relayout,
      only smaller: the tile, its corner radius and the line weight are rescaled together from the 56-unit tile
      the grid used (1.5 → 1.07 units), so half a stroke stays 0.857 grid units and the checks below still hold.
      All six are in the same thin line style:
      a lake column with a wave (process-guided ML), a SHAP bar chart (explainable ML), a stream network running to
      an amber outlet (water systems), a temperature-depth profile (lake thermal dynamics), and the two new ones —
      *metacoupling*: three small clusters of three nodes each, linked by curved flow arrows into a cycle, with the
      focal cluster in amber (a network of coupled systems, deliberately not a globe); *LLM*: a row of five token
      squares, the middle one amber, with a short arrow feeding a stack of three layer bars (no chat bubble).
      `check_focus_symbols()` asserts both stay inside the drawing area the other four use and that their arrows keep
      clear of the nodes and bars they link (build report: `focus symbols ...`).
  - Education is a list of five survey stations (Ph.D. to B.B.A.) with dotted leaders. Tools are grouped with a label above one row of tags. The closing plate gives the coordinates of both posts.
- **Palette.**
  - **Light** (page #ffffff): paper #f6f9f9, card #fbfcfc, rule #d5dfe2, graticule #d0dce0, ink #0e2a3b, text #2f4757, muted #566b79, teal #1d6873, lake #d0e6eb (depth tint #1c6674), contour #2f7f8a at 0.55, coast #3f8792, amber #b8731c (amber text #8f560b).
  - **Dark** (page #0d1117): paper #0f1720, cards outline-only (no fill), rule #26343f, ink #e8eff1, text #b9c7cf, muted #8b9daa, teal #6cc3c7, lake #112f39 (depth tint #58b9c2), contour #86d3d7 at 0.35, coast #5fb3bb, amber #e6a64e (amber text #ebb567). Because dark cards have no fill, they sit equally well on GitHub dark and dark dimmed (#212830).
  - Every text colour is checked to reach at least 4.5:1 on paper, card, chip and page. The weakest pairs are 5.25 (light) and 5.32 (dark dimmed).
- **Fonts** (all converted to outlines, each glyph defined once per SVG). This variant swaps the display serif for a plain text serif and leaves the sans and mono alone:
  - Source Serif 4 Semibold: name (86), section titles (42), card titles (26), featured repo heads (23), focus headings (22), degree labels (21).
  - Source Serif 4 Italic: lake names (21.5), hero tagline (28), contribution taglines (18.5), the education note (18), the closing place names (19).
  - Inter 400/500/600: body text and small-caps labels. JetBrains Mono 400/500: repo names, repo slugs, PR numbers, coordinates.
  - Source Serif sets about 35% wider and 8% shorter in the cap than Instrument Serif, so every serif size, baseline and column above was re-measured rather than simply renamed: the headings keep their measure on the page and give up some cap height. The hero name and the featured repo heads are the two the measure squeezes hardest (71% of the old cap height); everything else lands at 80–91%.
- **Regenerating.** `design/tools/.venv/bin/python design/variants/font-source/build.py` rebuilds all 50 SVGs, `assets/manifest.json` **and README.md**. Edit build.py, not README.md. In build.py, `~` glues two words together and `\n` forces a line break; list items separated by ` · ` never split across lines.
- **Alignment and weight.**
  - Card edges: the 816-wide panels inset their card by 6.5 units and the hero plate by 9.6. With the 49% + space pairs, every card edge lands at about 6.8 px on desktop.
  - Hero strokes are scaled for its 0.705 display size: contours about 0.92 px, coast 1.05 px, frame and leaders 1.0 px.
  - Smallest text is about 15.5 px on desktop and 6.0–6.2 px on phones. The seven link buttons are two fixed rows, four then three (515 and 445 px, at most 600), shown at 1:1.
- **Payload.** The light set is 673 KB; the largest file is the hero at 109 KB.
- **Things to know:**
  - The appointment cards link to the CSIS (csis.msu.edu) and CIGLR (ciglr.seas.umich.edu) sites; the URLs are set in `readme()` (`appt_url`).
  - The cards carry no text links: the whole card is the link to its repository. The JOSS reviewer page is a link button.
  - The markers pulse slowly (CSS); the pulse is off under `prefers-reduced-motion`.
  - Expected linter warnings are bot blocks: LinkedIn (999), ResearchGate (403) and sometimes CIGLR (403). The LinkedIn and ResearchGate URLs are exactly as given in the brief.
