"""Regression tests for text, geometry and generated-file safety."""

import contextlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path

import build


class TextTests(unittest.TestCase):
    def test_overlong_items_are_rejected_at_every_position(self):
        wide = "unbreakableword" * 5
        for text in (wide, f"short {wide}", f"short {wide} end", f"short · {wide}"):
            for balance in (False, True):
                with self.subTest(text=text, balance=balance):
                    with self.assertRaisesRegex(AssertionError, "wider than"):
                        build.wrap(text, build.SANS, 16, 100, balance=balance)

    def test_wrapping_preserves_glue_and_list_items(self):
        for text, expected in (("New~York Boston", ["New York", "Boston"]),
                               ("New York · Boston", ["New York", "Boston"]),
                               ("New York\nBoston", ["New York", "Boston"])):
            with self.subTest(text=text):
                self.assertEqual(build.wrap(text, build.SANS, 16, 80), expected)

    def test_svg_numbers_preserve_integer_zeros(self):
        for value, precision, expected in ((100, 0, "100"), (-100, 0, "-100"),
                                           (0, 0, "0"), (-0.001, 2, "0"), (10.50, 2, "10.5")):
            with self.subTest(value=value, precision=precision):
                self.assertEqual(build.num(value, precision), expected)

    def test_integer_precision_text_is_a_valid_svg_path(self):
        for precision in (0, 1, 2):
            with self.subTest(precision=precision):
                pen = BoundsPen(None)
                parse_path(build.text_path("H", build.SANS, 20, precision=precision), pen)
                expected = build.ink_box("H", build.SANS, 20, 0, 0)
                for actual, bound in zip(pen.bounds, expected):
                    self.assertAlmostEqual(actual, bound, delta=10 ** -precision)


class GeometryTests(unittest.TestCase):
    def test_simplification_drops_a_collinear_turnaround(self):
        # dp() measures distance to the infinite line, so a point that doubles back along it is dropped.
        # Harmless on coastline data and kept deliberately: see the comment in dp().
        points = build.np.array([[0., 0.], [2., 0.], [1., 0.]])
        self.assertEqual(len(build.dp(points, 0.1)), 2)

    def test_simplification_handles_straight_and_closed_lines(self):
        line = build.np.array([[0., 0.], [1., 0.], [2., 0.]])
        ring = build.np.array([[0., 0.], [1., 0.], [1., 1.], [0., 1.], [0., 0.]])
        build.np.testing.assert_array_equal(build.dp(line, 0.1), line[[0, -1]])
        build.np.testing.assert_array_equal(build.dp(ring, 0.1), ring)

    def test_unknown_focus_symbol_is_rejected(self):
        canvas = build.Canvas("test", 100, 100, "Test", "Test", 1)
        with self.assertRaisesRegex(ValueError, "unknown focus symbol"):
            build.focus_symbol(canvas, "typo", 0, 0, build.THEMES["light"])


class BuildTests(unittest.TestCase):
    def test_complete_build_is_consistent_repeatable_and_preserves_files_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "obsolete-light.svg").write_text("old generated asset", encoding="utf-8")
            (assets / "custom.svg").write_text("unrelated file", encoding="utf-8")
            (assets / "manifest.json").write_text('[{"file": "obsolete-light.svg"}]', encoding="utf-8")

            def snapshot():
                return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}

            with patch.object(build, "OUT", root), patch.object(build, "ASSETS", assets), \
                    contextlib.redirect_stdout(io.StringIO()):
                build.main()
                first = snapshot()
                self.assertFalse((assets / "obsolete-light.svg").exists())
                self.assertEqual((assets / "custom.svg").read_text(encoding="utf-8"), "unrelated file")
                manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
                names = {entry["file"] for entry in manifest}
                self.assertEqual(len(names), len(manifest))
                self.assertEqual(names, set(build.SVG_OUTPUTS))
                readme = (root / "README.md").read_text(encoding="utf-8")
                linked = set(re.findall(re.escape(build.RAW) + r'([^"<>]+\.svg)', readme))
                self.assertEqual(names, linked)
                for name in names:
                    partner = name.replace("-light.svg", "-dark.svg") if name.endswith("-light.svg") \
                        else name.replace("-dark.svg", "-light.svg")
                    self.assertIn(partner, names)
                    svg = ET.parse(assets / name).getroot()
                    ids = [e.attrib["id"] for e in svg.iter() if "id" in e.attrib]
                    self.assertEqual(len(ids), len(set(ids)), name)
                    self.assertIsNotNone(svg.find("{http://www.w3.org/2000/svg}title"))
                    for element in svg.iter():
                        self.assertNotEqual(element.tag, "{http://www.w3.org/2000/svg}text")
                        for value in element.attrib.values():
                            for ref in re.findall(r"url\(#([^)]*)\)", value):
                                self.assertIn(ref, ids, name)
                        if "href" in element.attrib:
                            self.assertIn(element.attrib["href"].removeprefix("#"), ids, name)
                build.main()
                self.assertEqual(snapshot(), first)
                with patch.object(build, "check_repo_density", side_effect=AssertionError("injected failure")):
                    with self.assertRaisesRegex(AssertionError, "injected failure"):
                        build.main()
                self.assertEqual(snapshot(), first)

    def test_optimized_python_cannot_skip_layout_checks(self):
        # Point the build at a temp directory: the guard is meant to fire first, but the test must not
        # depend on that to keep the real assets/ safe.
        source = str(pathlib.Path(build.__file__).resolve().parent)
        with tempfile.TemporaryDirectory() as directory:
            script = ("import sys, pathlib; sys.path.insert(0, %r); import build\n"
                      "build.OUT = pathlib.Path(%r); build.ASSETS = build.OUT / 'assets'\n"
                      "build.main()" % (source, directory))
            result = subprocess.run([sys.executable, "-O", "-c", script],
                                    capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("layout assertions must remain enabled", result.stderr)


if __name__ == "__main__":
    unittest.main()
