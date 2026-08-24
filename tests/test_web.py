#!/usr/bin/env python3
"""Regression tests for `checleaner.html`, the phone app.

`tests/test_pipeline.py` pins `checleaner.py`; this pins the port. It builds the
same synthetic fixtures, pushes them through the *real page* under Playwright
(`tools/webdetect.py`), and asserts on what comes back -- classification, crop
geometry, the colour targets measured on the app's own output, the glare rescue,
and orientation.

Two things make this worth having as assertions rather than the by-hand sweep
diffing `webdetect.py --compare` already supports:

- The app's thresholds are calibrated separately from Python's (`MULTI_WINDOWS`,
  `CARD_EDGE_SHARP`; see docs/PIPELINE.md § 3), so "the Python tests pass" says
  nothing about it. Its segmentation doesn't even always produce the same blob
  from the same photo -- a 43-px close bridges a sheen on one decoder's pixels
  and not on the other's.
- A sweep diff only reports what *moved*. It cannot tell you the app was already
  wrong, and it has been blind three separate times to changes that moved no
  field it tracked.

Where the two implementations legitimately differ, the test says so and pins the
difference, so that closing the gap fails here and gets the note updated rather
than leaving a stale claim in the docs.

Needs Playwright (`pip install playwright && playwright install chromium`).
Skips cleanly without it, so it is safe in a default `pytest tests/` run --
though it costs a browser launch and one page load per fixture, a few seconds
each, unlike test_pipeline.py which is pure numpy.

    python3 tests/test_web.py          # standalone
    pytest tests/test_web.py           # or under pytest
"""
import os
import sys
import cv2
import tempfile
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image

from checleaner import measure, to_srgb, ASPECT, build_parser
from test_pipeline import (skip, _Skip, make_single, make_single_with_glare,
                           make_single_with_welded_glare, make_card_on_pale_desk,
                           make_row, make_signed_row, make_staggered_pile, make_grid,
                           make_flush_grid, add_glare)

# The app's own output canvas is a fixed size; checleaner.py reaches the same
# one through --width, so take it from the CLI's default rather than restating it.
OUT_W = build_parser().parse_args(["."]).width
OUT_H = round(OUT_W * ASPECT)

try:
    from tools.webdetect import run as drive_page
except ImportError:                                    # dev-only dependency
    drive_page = None


# One frame each, named by what it is testing. `make_row` sizes its cards off
# the frame *height*, so two is as many as fit -- three would run off the edge.
WEB_FIXTURES = {
    "single":            lambda: make_single(),
    "single_upsidedown": lambda: make_single(upside_down=True),
    "single_glare":      lambda: make_single_with_glare(),
    "welded_glare":      lambda: make_single_with_welded_glare(),
    "pale_desk":         lambda: make_card_on_pale_desk()[0],
    "row2":              lambda: make_row(cols=2),
    "row2_glare":        lambda: add_glare(make_row(cols=2)),
    "signed_row":        lambda: make_signed_row(),
    "staggered_pile":    lambda: make_staggered_pile(),
    "grid":              lambda: make_grid(),
    "flush_grid":        lambda: make_flush_grid(),
}

_RESULTS = {}


def results():
    """Every fixture through the page once, cached: {name: (row, output_rgb)}.

    One browser and one page load per fixture is the whole cost of this module,
    so it is paid once here rather than per test. `output_rgb` is the corrected
    frame pulled straight off the canvas, which is what the colour assertions
    measure -- the app's own pixels, not a re-run of the maths.
    """
    if _RESULTS:
        return _RESULTS
    if drive_page is None:
        skip("Playwright not installed (pip install playwright && "
             "playwright install chromium)")
    tmp = tempfile.mkdtemp(prefix="checleaner-web-")
    out = os.path.join(tmp, "out")
    paths = []
    for name, build in WEB_FIXTURES.items():
        path = os.path.join(tmp, name + ".png")
        cv2.imwrite(path, cv2.cvtColor(build(), cv2.COLOR_RGB2BGR))
        paths.append(path)
    try:
        rows, errs = drive_page(paths, save=out, quiet=True)
    except Exception as exc:                           # no browser downloaded, etc.
        skip(f"could not drive checleaner.html: {exc}")
    # Page errors are the finding, not a footnote: the app swallows exceptions
    # and still shows a result, so a thrown error looks like a clean run.
    assert not errs, "page errors: " + "; ".join(dict.fromkeys(errs))
    for row in rows:
        name = os.path.splitext(row["file"])[0]
        saved = os.path.join(out, name + ".jpg")
        rgb = np.asarray(Image.open(saved).convert("RGB")) if os.path.exists(saved) else None
        _RESULTS[name] = (row, rgb)
    return _RESULTS


def row(name):
    return results()[name][0]


def output(name):
    rgb = results()[name][1]
    assert rgb is not None, f"{name}: the page produced no output canvas"
    return rgb


# ------------------------------------------------------------ classification

# What the page's own captions mean, per fixture. `single?` is the near-miss
# band: roughly card-shaped, not confidently one card, so it is levelled rather
# than cropped -- a refusal to warp, not a failure.
WEB_KINDS = {
    "single":            "single",
    "single_upsidedown": "single",
    "single_glare":      "single",          # glare as its own blob, filtered out
    "welded_glare":      "single",          # glare welded on, trimmed off
    "pale_desk":         "single?",         # see test_pale_desk_is_not_croppable
    "row2":              "multi-aligned",
    "row2_glare":        "multi-aligned",
    "signed_row":        "multi-aligned",
    "staggered_pile":    "multi-aligned",
    "grid":              "single?",
    "flush_grid":        "multi-aligned",    # shape says card; only windows disagree
}


def test_web_classifies_every_fixture():
    for name, want in WEB_KINDS.items():
        got = row(name)["kind"]
        assert got == want, f"{name}: page said {got!r}, want {want!r}"


def test_web_never_warps_several_prints_into_one_card():
    """The expensive mistake. A row, a pile or a grid cropped as a single card
    comes out mangled with nothing flagged, so no fixture holding more than one
    print may reach the crop path.

    Asserted on the output's *size*, not on the caption. Every cropped single
    warps to the same canvas, so the size is the fact; the caption is not --
    dropping the solidity gate on purpose warped the grid into a card and the
    page labelled it only "orientation uncertain", which sailed past an earlier
    version of this test that read the verdict.
    """
    for name in ("row2", "row2_glare", "signed_row", "staggered_pile", "grid",
                 "flush_grid"):
        r = row(name)
        assert r["kind"] != "single", f"{name} was cropped as one card"
        assert r["size"] != f"{OUT_W}x{OUT_H}", \
            f"{name} came out card-shaped ({r['size']}) whatever the caption said"


def test_web_flush_grid_is_caught_only_by_its_windows():
    """The arrangement that beats every shape test: nine cards laid flush read
    aspect ~1.6, fill 1.0 and solidity 1.0, exactly a clean card's numbers. The
    photo-window count is the only thing between it and being warped into one
    print, so assert both halves -- that the shape really does pass, and that
    the count really does overrule it."""
    r = row("flush_grid")
    assert r["kind"] != "single", "nine flush cards were warped into one print"
    assert (1.53 <= float(r["aspect"]) <= 1.65 and float(r["fill"]) >= 0.93
            and float(r["solidity"]) >= 0.97), \
        (f"fixture no longer beats the shape gate (aspect {r['aspect']}, fill "
         f"{r['fill']}, solidity {r['solidity']}) -- it tests nothing like this")
    # the page prints the count only on the paths that consult it, so a bare "-"
    # here means the crop path was taken -- which the assertion above has ruled out
    assert r["windows"] != "-" and int(r["windows"]) >= 6, \
        f"window count came back {r['windows']!r}; the backstop cannot fire on that"


def test_web_solidity_is_a_real_ratio():
    """A shape's area over its own convex hull's cannot exceed 1. The old
    approximation could -- it divided a pixel *count* by a polygon area, and
    three photos in the library measured over 1.0 -- which meant the number it
    reported was not the quantity the threshold was set on. Cheap to assert, and
    it fails the moment anyone reaches for a stand-in again."""
    for name in WEB_KINDS:
        sol = float(row(name)["solidity"])
        assert 0 < sol <= 1.0 + 1e-6, f"{name}: solidity {sol}"


def test_web_grid_is_caught_by_solidity():
    """The app's solidity is approximated (closedArea / hullArea, no
    findContours), and the open question is how much it can still do. Here it
    does the job outright: the grid's aspect sits inside the single-card band
    and its bounding box is well filled, so only the notched outer boundary
    betrays it."""
    r = row("grid")
    assert 1.53 <= float(r["aspect"]) <= 1.65, "fixture no longer tests solidity"
    assert float(r["fill"]) >= 0.93, "fixture no longer tests solidity"
    assert float(r["solidity"]) < 0.97, f"grid solidity {r['solidity']} no longer caught"


# -------------------------------------------------------------- crop geometry

def test_web_single_crops_are_instax_shaped():
    """Every cropped single warps to the same canvas, at the real card's aspect
    -- 54 x 86 mm. Both implementations must agree on this or the two halves of
    the library stop matching."""
    for name in ("single", "single_upsidedown", "single_glare", "welded_glare"):
        r = row(name)
        assert r["size"] == f"{OUT_W}x{OUT_H}", f"{name}: output {r['size']}"
        assert abs(float(r["aspect"]) - ASPECT) < 0.02, \
            f"{name}: fitted aspect {r['aspect']}, want {ASPECT:.4f}"


def border_bands(rgb):
    """(top, bottom) paper band above and below the print's picture area, as a
    fraction of the crop's height.

    An instax mini has a narrow border at the top and a wide signature border at
    the bottom -- 4 mm against 20 mm -- which is the only thing in the frame that
    says which way up it is. Measured on the largest *run* of window rows rather
    than the first and last: one stray dark row at a crop's edge is a resampling
    artefact, and taking it literally reported a correctly turned card as
    upside down.
    """
    h, w = rgb.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), (9, 9), 0),
                       cv2.COLOR_BGR2LAB).astype(np.float32)
    paper = ((lab[:, :, 0] > 0.62 * np.percentile(lab[:, :, 0], 99))
             & (np.hypot(lab[:, :, 1] - 128, lab[:, :, 2] - 128) < 16))
    window = paper[:, int(0.2 * w):int(0.8 * w)].mean(axis=1) < 0.5
    best = run = start = best_start = 0
    for i, inside in enumerate(window):
        if not inside:
            run = 0
            continue
        start = i if run == 0 else start
        run += 1
        if run > best:
            best, best_start = run, start
    assert best, "no picture area found in the crop"
    return best_start / h, (h - 1 - (best_start + best - 1)) / h


def test_web_orientation_puts_the_wide_border_at_the_bottom():
    """The fixture is generated wide-border-down, and again upside down; both
    must come back the same way up. Measured on the crop itself rather than on a
    caption, because getting this wrong moves the pixels and nothing else --
    size, aspect and verdict are identical either way."""
    for name in ("single", "single_upsidedown", "single_glare", "welded_glare"):
        top, bottom = border_bands(output(name))
        assert bottom > 2 * top, (f"{name}: border {top:.3f} above the picture and "
                                  f"{bottom:.3f} below -- upside down")
        # the fixture's own geometry: 5% narrow end, 16% wide end
        assert abs(top - 0.05) < 0.02 and abs(bottom - 0.16) < 0.02, \
            f"{name}: bands {top:.3f}/{bottom:.3f}, want about 0.05/0.16"


def test_web_a_glare_blob_leaves_the_crop_untouched():
    """A patch of desk glare that segments as its own blob must be filtered out
    before it can reach the crop, so the result is the *same picture* as the
    clean card -- not merely one that still passes the shape gate. Compared on
    the page's 8x8 thumbprint of the output, since a crop dragged a few pixels
    by the glare would keep its size, aspect and verdict."""
    clean = row("single")["sig"].split(".")
    glared = row("single_glare")["sig"].split(".")
    assert clean != ["-"], "no thumbprint recorded"
    worst = max(abs(int(a) - int(b)) for a, b in zip(clean, glared))
    assert worst <= 2, f"glare moved the crop: thumbprints differ by up to {worst}/64"


# --------------------------------------------------------------------- colour

def test_web_output_hits_the_colour_targets():
    """White 238.8, black 2.2 -- the library-wide anchors, measured on the
    frames the app itself produced. These are what make a photo corrected on the
    phone sit next to one corrected on the desktop, so they are the single most
    important thing to pin about the port.

    White only on the multi-print frames: their crops are mostly desk and print
    content, so the darkest 0.5% is not a black *point* in any meaningful sense
    (it ranges 0.0-8.4 across them). On a cropped single the frame is one card
    and the reading is real.
    """
    for name in WEB_KINDS:
        m = measure(output(name))
        white = to_srgb(m.white)
        assert np.all(np.abs(white - 238.8) < 1.6), \
            f"{name}: white landed {np.round(white, 1).tolist()}, want 238.8"
    for name in ("single", "single_upsidedown", "single_glare", "welded_glare"):
        black = to_srgb(measure(output(name)).black)
        assert np.all(np.abs(black - 2.2) < 1.0), \
            f"{name}: black landed {np.round(black, 2).tolist()}, want 2.2"


def test_web_a_pale_background_does_not_drag_the_white_anchor():
    """A card on a surface *brighter than its own border* still lands on target.

    What this does not do is isolate the paper-confined anchor
    (docs/PIPELINE.md § 1): disabling that confinement in the app on purpose
    leaves this fixture inside tolerance, because the card fills enough of the
    frame that the brightest band is mostly paper either way. It is the plain
    `single` fixture that moves (to 241.0). So read this as "a bright backdrop
    doesn't break the correction", and reach for the Python tests, which compare
    the two gains directly, for the confinement itself.
    """
    white = to_srgb(measure(output("pale_desk")).white)
    assert np.all(np.abs(white - 238.8) < 1.6), \
        f"pale desk pulled white to {np.round(white, 1).tolist()}"


# ----------------------------------------------------------------- glare trim

def test_web_glare_rescue_fires_only_where_it_should():
    """Glare welded onto a card by the segmentation close distorts the fitted
    rectangle, and the sheen-free reading of the blob stands in for it. It must
    not fire on a clean card, and must not launder anything holding several
    prints into a single (see single_fit in checleaner.py)."""
    assert row("welded_glare")["glare"] == "trimmed", "glare rescue did not fire"
    for name in ("single", "single_glare", "row2", "signed_row", "grid",
                 "staggered_pile"):
        assert row(name)["glare"] != "trimmed", f"{name}: glare rescue fired"


def test_web_a_stray_glare_blob_does_not_drag_an_aligned_crop():
    """align() crops around the union of every blob it was given, so one bright
    patch of desk off in a corner would pull the crop out to cover it. The
    fill-and-area filter on secondary blobs is what stops that, and the proof is
    that the same row with and without the patch crops identically."""
    plain, glared = row("row2"), row("row2_glare")
    assert plain["size"] == glared["size"], \
        f"glare changed the crop: {plain['size']} -> {glared['size']}"
    a, b = plain["sig"].split("."), glared["sig"].split(".")
    worst = max(abs(int(x) - int(y)) for x, y in zip(a, b))
    assert worst <= 3, f"glare moved the aligned crop: thumbprints differ by {worst}/64"


# --------------------------------------------------- known port divergences

def test_web_levels_a_staggered_pile_by_its_cards():
    """Three level prints dealt corner to corner. The blob's fitted rectangle
    follows the staircase -- aspect 2.23 -- so a tilt taken from it turns the
    frame by an angle no card in the photo has, which opens blank corners no
    crop fits inside; the app used to decline outright and leave the frame whole.
    Reading the tilt off the outline's straight runs instead, which are all card
    borders, it now crops to the same 1008 x 1344 `checleaner.py` produces.

    This was a pinned divergence until the contour tracer landed. Keep it
    asserting on the *shape*, not just on "it cropped": the failure it guards
    against is a plausible-looking crop at the staircase's angle.
    """
    r = row("staggered_pile")
    assert r["kind"] == "multi-aligned", f"pile came back {r['kind']!r}"
    assert float(r["aspect"]) > 2.0, \
        "fixture no longer staggers enough for the blob rectangle to mislead"
    assert abs(float(r["tilt"])) < 0.5, \
        f"levelled by {r['tilt']}deg -- that is the staircase's angle, not a card's"
    assert r["size"] == "1008x1344", f"crop came out {r['size']}, want 1008x1344"


def test_pale_desk_is_not_croppable_by_either_implementation():
    """A card on a desk brighter than its own border: the desk segments as paper
    and merges with the card, so the blob is the whole frame and no card shape
    fits it. Both implementations decline to crop it, and the fixture exists for
    the colour anchor rather than the geometry -- pinned here so a change that
    silently starts cropping it gets noticed."""
    assert row("pale_desk")["kind"] == "single?"


# ------------------------------------------------------------------ runner

def main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed = failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
        except _Skip as exc:
            print(f"SKIP  {name}: {exc}")
            skipped += 1
        except AssertionError as exc:
            print(f"FAIL  {name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
            failed += 1
        else:
            print(f"PASS  {name}")
            passed += 1
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
