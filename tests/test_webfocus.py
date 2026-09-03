#!/usr/bin/env python3
"""Regression tests for `focusmerge.html`, the phone page.

`tests/test_focusmerge.py` pins `tools/focusmerge.py`; this pins the port. It
builds the same synthetic fixtures, pushes them through the *real page* under
Playwright (`tools/webfocus.py`), and asserts on what comes back -- registration,
the exposure match, the merged frame's sharpness measured on the page's own
output, and the moved-print warning.

It has to exist separately from the Python suite, and not only because a browser
is a different machine. The page is a different *algorithm*: ORB where the
desktop tool has SIFT, a hand-written FFT where it has cv2's, a bicubic warp
where it has Lanczos. Every threshold is calibrated against this decoder. "The
Python tests pass" says nothing at all about it -- and three of the bugs found
while writing it existed only here (a FAST pre-test using the N=12 threshold on
an N=9 detector, a parabolic peak formula with the sign inverted, and a missing
pre-blur that let pixel noise decide which frame was sharper).

Where the two implementations legitimately differ, the test pins the difference,
so closing a gap fails here and gets the note updated rather than leaving a stale
claim in the docs.

Needs Playwright (`pip install playwright && playwright install chromium`).
Skips cleanly without it, so it is safe in a default `pytest tests/` run --
though it costs a browser launch and a page load per fixture.

    python3 tests/test_webfocus.py     # standalone
    pytest tests/test_webfocus.py      # or under pytest
"""
import os
import sys
import glob
import tempfile

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from checleaner import to_linear
from tools.focusmerge import sharpness
import tools.webfocus as webfocus
from test_focusmerge import (make_pair as _make_pair, _cards, _soften, _ramp,
                             EXPOSURE, _real_cards)


# How hard the fixture's defocus bites. The Python suite uses 2.2, a ~26x
# sharpness ratio between the halves; this page cannot register that, and the
# limit is not a bug to fix but the difference between the two feature
# detectors -- see test_page_refuses_frames_too_far_apart_in_focus. 1.0 puts the
# fixture at about 3x, which brackets the real pair's 2.5x.
WEB_DEFOCUS = 1.0


def make_pair(**kw):
    kw.setdefault("blur", WEB_DEFOCUS)
    return _make_pair(**kw)


class _Skip(Exception):
    pass


def skip(msg):
    if "pytest" in sys.modules:
        import pytest
        pytest.skip(msg)
    raise _Skip(msg)


def _need_playwright():
    if webfocus.sync_playwright is None:
        skip("Playwright not installed")


def _merge(frames, names=None, keep=None):
    """Write the frames to a temp dir, run the real page on them, return
    (row, reports, merged BGR or None)."""
    _need_playwright()
    names = names or [f"{i}_frame.jpg" for i in range(len(frames))]
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for f, n in zip(frames, names):
            p = os.path.join(tmp, n)
            cv2.imwrite(p, f, [cv2.IMWRITE_JPEG_QUALITY, 96])
            paths.append(p)
        out = os.path.join(tmp, "merged.jpg")
        row, errs = webfocus.run(paths, save=out, quiet=True)
        assert not errs, f"the page raised: {errs}"
        img = cv2.imread(out) if os.path.exists(out) else None
        return row, img


def _halves(img):
    s = sharpness(to_linear(img))
    h, w = s.shape
    return (float(s[h//4:3*h//4, int(.08*w):int(.28*w)].mean()),
            float(s[h//4:3*h//4, int(.72*w):int(.92*w)].mean()))


# ------------------------------------------------------------------ the merge

def test_page_takes_the_sharp_side_of_each_frame():
    """The whole point, on the page rather than in numpy: neither input is good
    everywhere and the output is. Measured on the page's own merged canvas, not
    on anything Python produced."""
    f1, f2 = make_pair()
    row, out = _merge([f1, f2], ["a.jpg", "b.jpg"])
    assert out is not None, row["status"]
    assert row["frames"] == "2/2", row
    l1, r1 = _halves(f1)
    l2, r2 = _halves(f2)
    lo, ro = _halves(out)
    assert l1 > 2 * l2 and r2 > 2 * r1, "fixture is wrong: each half should favour one frame"
    assert lo > 0.85 * l1, f"merged left {lo:.4f} lost the sharp frame ({l1:.4f})"
    assert ro > 0.85 * r2, f"merged right {ro:.4f} lost the sharp frame ({r2:.4f})"


def test_page_keeps_the_first_shot_as_the_reference():
    """The output takes the first file's framing and dimensions -- everything
    downstream, EXIF included, assumes it."""
    f1, f2 = make_pair()
    row, out = _merge([f1, f2], ["a.jpg", "b.jpg"])
    assert out.shape == f1.shape, (out.shape, f1.shape)
    assert row["size"] == f"{f1.shape[1]}x{f1.shape[0]}", row["size"]


def test_page_matches_exposure_onto_the_first_shot():
    """The fixture's second frame is a known EXPOSURE brighter in linear light,
    so the gain the page reports has a right answer to check against. Colour is
    checleaner's job; a merge that drifted would de-match the whole library."""
    f1, f2 = make_pair()
    row, _ = _merge([f1, f2], ["a.jpg", "b.jpg"])
    gains = [float(v) for v in row["gains"].split(",")]
    for name, g in zip("RGB", gains):
        assert abs(g - 1 / EXPOSURE) < 0.02, \
            f"{name} gain {g:.3f}, expected {1 / EXPOSURE:.3f}"


def test_page_refuses_a_frame_it_cannot_line_up():
    """Two unrelated photographs must be reported, not blended: a plausible file
    that is nonsense is worse than an error."""
    f1, _ = make_pair()
    other = _cards(np.random.default_rng(77))
    row, out = _merge([f1, other], ["a.jpg", "b.jpg"])
    assert row["frames"] == "1/2", row
    assert row["skipped"] != "-", "an unrelated frame was merged in silently"
    assert "nothing lined up" in row["status"], row["status"]


# --------------------------------------------------- the maths, inside the page

MATHS = """() => {
  const out = {};
  // FAST on a drawn square. Nine consecutive of sixteen circle points always
  // contain at least *two* of the four compass points, so the pre-test must ask
  // for two; asking for three is the FAST-12 rule and rejects a square's corners
  // outright, which is exactly what it did.
  const w = 200, h = 200, g = new Uint8Array(w*h).fill(40);
  for (let y = 60; y < 140; y++) for (let x = 60; x < 140; x++) g[y*w+x] = 220;
  const kp = fastCorners(g, w, h);
  const near = (cx, cy) => kp.some(k => Math.abs(k.x-cx) < 4 && Math.abs(k.y-cy) < 4);
  out.squareCorners = [near(60,60), near(139,60), near(60,139), near(139,139)];

  // Phase correlation against known fractional shifts of a broadband field. A
  // sparse signal is the wrong fixture: whitening amplifies its empty bins into
  // noise that swamps the peak.
  const n = TILE;
  let seed = 99; const rnd = () => { seed = (seed*1103515245+12345)&0x7fffffff; return seed/0x7fffffff; };
  const N = n+64, raw = new Float64Array(N*N);
  for (let i = 0; i < N*N; i++) raw[i] = rnd();
  const sm = new Float64Array(N*N);
  for (let y = 2; y < N-2; y++) for (let x = 2; x < N-2; x++) { let s = 0;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) s += raw[(y+dy)*N+x+dx];
    sm[y*N+x] = s/25; }
  const samp = (x, y) => { const x0 = Math.floor(x), y0 = Math.floor(y), ax = x-x0, ay = y-y0;
    const gg = (xx, yy) => sm[Math.min(N-1,Math.max(0,yy))*N + Math.min(N-1,Math.max(0,xx))];
    return (gg(x0,y0)*(1-ax)+gg(x0+1,y0)*ax)*(1-ay) + (gg(x0,y0+1)*(1-ax)+gg(x0+1,y0+1)*ax)*ay; };
  let worst = 0;
  for (const [sx, sy] of [[0,0],[1,0],[2.5,0],[2.5,1.5],[5,-7],[0.5,-0.5],[-3.25,4.75],[0.2,0.1]]) {
    const A = new Float32Array(n*n), B = new Float32Array(n*n);
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      A[y*n+x] = samp(x+32, y+32)*255; B[y*n+x] = samp(x+32-sx, y+32-sy)*255; }
    const r = phaseCorr(A, B);
    worst = Math.max(worst, Math.hypot(r.dx-sx, r.dy-sy));
  }
  out.shiftError = worst;

  // and the homography solver, against a transform it should reproduce exactly
  const H = [[1.04,-0.003,-21.9],[0.001,1.041,-70.4],[-1.4e-6,-3.5e-7,1]];
  const pts = [];
  for (const [x,y] of [[100,120],[2800,140],[3000,2700],[150,2600],[1500,1400],[800,2000]]) {
    const [u,v] = applyH(H,x,y); pts.push([x,y,u,v]); }
  const H2 = homographyFrom(pts);
  let herr = 0;
  for (const p of pts) { const [u,v] = applyH(H2,p[0],p[1]); herr = Math.max(herr, Math.hypot(u-p[2],v-p[3])); }
  out.homographyError = herr;
  return out;
}"""


def test_the_pages_maths_hold_up():
    """The internals, exercised inside the browser that runs them.

    These are cheap -- one page load, no image files -- and they cover the parts
    a whole-merge test reaches only indirectly. Two of them exist because the
    end-to-end tests did *not* catch a deliberate break: the FAST pre-test
    threshold and the sub-pixel peak both survived being wrecked while every
    merge still came out fine, which means those merges were passing for reasons
    other than the code being right.
    """
    _need_playwright()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"file://{webfocus.PAGE}")
        res = pg.evaluate(MATHS)
        b.close()
    assert not errs, errs
    assert all(res["squareCorners"]), \
        f"FAST missed corners of a drawn square: {res['squareCorners']}"
    assert res["shiftError"] < 0.25, \
        f"phase correlation is off by {res['shiftError']:.2f}px on known shifts"
    assert res["homographyError"] < 0.05, \
        f"the homography solver misses its own transform by {res['homographyError']:.3f}px"


# ------------------------------------------------------------ moved prints

def _nudge(img, box, by):
    """Lift one card and put it back somewhere else -- the failure the page's
    movement check exists for."""
    x, y, w, h = box
    dx, dy = by
    out = img.copy()
    card = img[y:y+h, x:x+w].copy()
    out[y:y+h, x:x+w] = cv2.GaussianBlur(img[y:y+h, x:x+w], (0, 0), 9)
    out[y+dy:y+dy+h, x+dx:x+dx+w] = card
    return out


def test_page_reports_a_print_that_moved():
    """A nudged print aligns nowhere and blends into a ghost, while every other
    number in the report still looks fine. It has to be said out loud."""
    import test_focusmerge as T
    f1, f2 = make_pair()
    box = (T.GAP + 2*(T.CARD_W + T.GAP), T.GAP + T.CARD_H + T.GAP, T.CARD_W, T.CARD_H)
    row, out = _merge([f1, _nudge(f2, box, (34, 22))], ["a.jpg", "b.jpg"])
    assert row["moved"] != "-" and not row["moved"].startswith("0@"), \
        f"a print moved 40px and the page reported {row['moved']}"
    worst = float(row["moved"].split("@")[1])
    assert worst > 20, f"reported only {worst:.1f}px of movement"


def test_page_stays_quiet_on_a_still_desk():
    """The other half, and the one that decides whether the warning is worth
    anything. The frames differ everywhere -- focus, exposure, lens distortion --
    and none of that may read as movement.

    This is where the page needed a rule the desktop tool does not: thirteen
    near-identical cards give a tile several plausible correlation peaks, and six
    of them came back 8-49 px out on a still desk. Response cannot separate those
    from good tiles; having company that agrees can. See `movedTiles`.
    """
    f1, f2 = make_pair()
    row, _ = _merge([f1, f2], ["a.jpg", "b.jpg"])
    assert row["moved"] == "-" or row["moved"].startswith("0@"), \
        f"clean pair reported movement: {row['moved']}"


def test_page_refuses_frames_too_far_apart_in_focus():
    """The page's real limit, pinned rather than left to be discovered.

    ORB matches a binary pattern of pixel comparisons, and a razor-sharp patch
    and a heavily defocused one do not produce the same pattern. Measured on the
    fixture, the page registers up to about a 5x sharpness ratio between the
    frames and refuses past it; SIFT, on the desktop, still merges at 26x. The
    reference pair sits at 2.5x, so this is head-room rather than a wall -- but
    it is a real difference between the two implementations, and the thing that
    matters is what happens beyond it: the page must *refuse*, not merge two
    frames it has failed to line up.
    """
    f1, f2 = make_pair(blur=2.2)
    row, out = _merge([f1, f2], ["a.jpg", "b.jpg"])
    assert row["frames"] == "1/2", \
        f"the page claims to have merged frames it cannot match: {row}"
    assert "nothing lined up" in row["status"], row["status"]


# ----------------------------------------------------- opt-in: the real photos

def _photo(stamp):
    folder = os.path.join(REPO, "chekis", "main", "raw")
    hits = [h for h in sorted(glob.glob(os.path.join(folder, f"*{stamp}*")))
            if os.path.isfile(h)]
    assert len(hits) < 2, f"{stamp} matches more than one photo: {hits}"
    return hits[0] if hits else None


def test_real_pair_merges_on_the_page_as_well_as_in_python():
    """The measurement both implementations exist for, on the photographs they
    were written for -- and the one that says the port is a port.

    The desktop tool keeps 96.9% of the best frame on the worst of the thirteen
    prints. The page reaches 95.7%, on a different feature detector, a different
    FFT and a different resampler. The bar is set below the desktop's on purpose:
    they are not the same algorithm and never will be, and pinning the page to
    Python's exact number would fail for reasons that are not defects.
    """
    _need_playwright()
    pa, pb = _photo("002232944"), _photo("002255786")
    if not pa or not pb:
        skip("the reference pair is not present (photos are gitignored)")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "merged.jpg")
        row, errs = webfocus.run([pa, pb], save=out, quiet=True)
        assert not errs, f"the page raised: {errs}"
        merged = cv2.imread(out)
    a, b = cv2.imread(pa), cv2.imread(pb)
    assert row["moved"] == "-" or row["moved"].startswith("0@"), \
        f"nothing moved between these two shots, but the page said {row['moved']}"

    from tools.focusmerge import align
    lin_b, _, _ = align(a, b, "b")
    sa, sb, so = sharpness(to_linear(a)), sharpness(lin_b), sharpness(to_linear(merged))
    worst, worst_card = 1e9, ""
    for name, box in _real_cards():
        va, vb, vo = sa[box].mean(), sb[box].mean(), so[box].mean()
        if vo / max(va, vb) < worst:
            worst, worst_card = vo / max(va, vb), name
        if name == "A1":
            assert va > 2 * vb, "A1 should be much sharper in the first shot"
        if name == "C5":
            assert vb > 2 * va, "C5 should be much sharper in the second"
    assert worst > 0.92, f"{worst_card} kept only {worst:.0%} of the best frame"


def test_real_pair_registers_as_well_as_sift_does():
    """ORB is not a compromise here, which is the finding the whole page rests
    on: it reaches sub-pixel reprojection on real print content, where SIFT --
    the reason a browser port looked impossible -- measures 0.73."""
    _need_playwright()
    pa, pb = _photo("002232944"), _photo("002255786")
    if not pa or not pb:
        skip("the reference pair is not present (photos are gitignored)")
    row, errs = webfocus.run([pa, pb], quiet=True)
    assert not errs, f"the page raised: {errs}"
    inl, tot = (int(v) for v in row["inliers"].split("/"))
    assert inl > 300, f"only {inl} inliers of {tot} matches"
    assert float(row["reproj"]) < 1.5, f"reprojection {row['reproj']}px"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except _Skip as e:
            print(f"SKIP  {name}: {e}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
