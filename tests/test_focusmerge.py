#!/usr/bin/env python3
"""Regression tests for tools/focusmerge.py, the side tool that merges several
shots of one unmoved layout into a single frame that is in focus everywhere.

    python3 tests/test_focusmerge.py      # standalone: PASS/FAIL/SKIP, nonzero on fail
    pytest tests/                          # also works; skips register natively

Fixtures are synthetic and generated here, for the same reason test_pipeline.py's
are: the real photos are personal and gitignored. A drawn scene is also the only
way to *know* the ground truth this tool needs -- which half of which frame was
sharp, and by how much -- where a real photo only has opinions about it. The
fixture is rendered once and then photographed twice: two camera poses, two
different halves blurred, and (for the frame that isn't the reference) a touch of
barrel distortion, because a homography cannot absorb that and the local
refinement exists precisely to mop up what it leaves.

The opt-in tier at the bottom asserts on the real pair -- `002232944` and
`002255786` -- when they are present, and skips otherwise. They live in
`chekis/main/raw/` now that their merge has taken their place in the batch; see
`_merged_source`.
"""
import os
import sys
import glob
import tempfile

import numpy as np
import cv2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from checleaner import to_linear, to_srgb
from tools.focusmerge import (align, merge, sharpness, blend_weights,
                              _tile_shifts, _moved_tiles, REFINE_TILES,
                              MIN_INLIERS, MOVE_TOL)


class _Skip(Exception):
    pass


def skip(msg):
    """Skip that works both standalone (caught by the runner below) and under
    pytest (where it should register as a real skip, not a failure)."""
    if "pytest" in sys.modules:
        import pytest
        pytest.skip(msg)
    raise _Skip(msg)


DESK = np.array([47, 66, 95], np.float32)       # BGR: focusmerge works in BGR throughout
BORDER = np.array([231, 232, 232], np.float32)
# Big enough that the tool's 10x10 tile grid gets tiles of a few hundred pixels
# a side, as it does on a phone photo. At half this the phase correlations get
# noisy enough to scatter past MOVE_TOL and the movement check cries wolf --
# which is a property of the fixture, not of the tool.
CARD_W, CARD_H = 290, 458                       # roughly instax proportions
GAP = 26


def _picture(rng, h, w):
    """A card's photo window: shapes at every scale, then fine grain on top.

    Both halves are needed and for different reasons. The shapes give SIFT
    something repeatable to match -- an early version filled the window with
    plain noise and the registration collapsed to 6 inliers, because noise has
    no keypoint that survives being blurred. The grain is what defocus actually
    takes away, so it is what the sharpness measurement reads.
    """
    img = np.full((h, w, 3), 150.0, np.float32)
    for _ in range(26):
        col = rng.integers(15, 232, 3).tolist()
        x, y = rng.integers(0, w), rng.integers(0, h)
        s = int(rng.integers(6, max(7, min(h, w) // 2)))
        if rng.random() < 0.5:
            cv2.rectangle(img, (x, y), (x + s, y + int(s * rng.uniform(.4, 1.8))), col, -1)
        else:
            cv2.circle(img, (x, y), s, col, -1)
    for _ in range(8):
        p = tuple(rng.integers(0, [w, h], 2).tolist())
        q = tuple(rng.integers(0, [w, h], 2).tolist())
        cv2.line(img, p, q, rng.integers(0, 232, 3).tolist(), int(rng.integers(1, 4)))
    return np.clip(img + rng.normal(0, 22, (h, w, 3)), 4, 236)


def _cards(rng, moved=None):
    """A 5x3 deskful of cards, drawn BGR. `moved` shifts one card by (dx, dy) --
    the fixture for a print someone nudged between shots."""
    h = 3 * CARD_H + 4 * GAP
    w = 5 * CARD_W + 6 * GAP
    img = np.tile(DESK, (h, w, 1)) + rng.normal(0, 2, (h, w, 3))
    for r in range(3):
        for c in range(5):
            y = GAP + r * (CARD_H + GAP)
            x = GAP + c * (CARD_W + GAP)
            if moved and (r, c) == moved[0]:
                y, x = y + moved[1][1], x + moved[1][0]
            img[y:y+CARD_H, x:x+CARD_W] = BORDER + rng.normal(0, 2, (CARD_H, CARD_W, 3))
            wy, wx = y + 14, x + 14
            wh, ww = int(CARD_H * 0.72), CARD_W - 28
            img[wy:wy+wh, wx:wx+ww] = _picture(rng, wh, ww)
            cv2.line(img, (x + 20, y + CARD_H - 30), (x + CARD_W - 20, y + CARD_H - 45),
                     (20, 20, 20), 3)
    return np.clip(img, 0, 255).astype(np.uint8)


DEFOCUS = 2.2      # sigma of the fixture's out-of-focus half, in linear light


def _soften(img, mask, sigma=DEFOCUS):
    """Defocus `img` where mask is 1, sharp where it is 0, smoothly between --
    a focal plane crossing the desk, which is what makes one shot insufficient.

    In linear light, because that is where a lens does it. Blurring in sRGB
    instead darkens whatever it touches -- the curve is convex, so smoothing
    away contrast lowers the linear mean -- and the fixture then had a 9%
    brightness step between its sharp and soft halves that no gain could match
    and that read as the merge shifting tone.
    """
    lin = to_linear(img)
    blurred = cv2.GaussianBlur(lin, (0, 0), sigma)
    m = mask[:, :, None]
    return to_srgb(np.clip(lin * (1 - m) + blurred * m, 0, 1)).round().astype(np.uint8)


def _ramp(shape):
    """0 on the left of the frame, 1 on the right, with a soft middle. Used as a
    defocus mask, so `_soften(img, _ramp(...))` leaves the *left* side sharp."""
    h, w = shape
    x = np.linspace(-1, 1, w, dtype=np.float32)
    return np.tile(np.clip(x * 2.2 + 0.5, 0, 1), (h, 1))


def _barrel(img, px=5.0):
    """A little radial distortion: a homography cannot represent it, so it is
    exactly the residual refine_field() was written for.

    Sized by the displacement it produces at the corners, not by its coefficient.
    Radial distortion moves a point by k*r^2*r, so a fixed k means an amount that
    grows with the *cube* of the frame -- enlarging the fixture once quietly took
    it from 2.5 px to 35 and made the alignment look broken."""
    h, w = img.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    cx, cy = w / 2, h / 2
    r2 = (gx - cx) ** 2 + (gy - cy) ** 2
    k = px / np.hypot(cx, cy) ** 3
    f = (1 + k * r2).astype(np.float32)
    return cv2.remap(img, cx + (gx - cx) * f, cy + (gy - cy) * f, cv2.INTER_LANCZOS4)


def _pose(img, dx=17.0, dy=-11.0, scale=1.012, rot=0.4):
    """The camera moved a little between shots, as it does hand-held."""
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, scale)
    M[0, 2] += dx
    M[1, 2] += dy
    H = np.vstack([M, [0, 0, 1]])
    return cv2.warpPerspective(img, H, (w, h), flags=cv2.INTER_LANCZOS4,
                               borderMode=cv2.BORDER_REPLICATE)


EXPOSURE = 1.06     # frame 2 is a touch brighter, as two hand-held shots are


def make_pair(moved=None, seed=4, distort=True, exposure=EXPOSURE, dx=17.0,
              blur=DEFOCUS):
    """Two shots of one desk: frame 1 sharp on the left, frame 2 sharp on the
    right, taken from slightly different positions. Returns (frame1, frame2).

    `dx` is how far the camera moved sideways; a big one pushes whole tiles off
    the edge of the second shot, which is what the coverage test is for. `blur`
    is how hard the defocus bites -- tests/test_webfocus.py turns it down,
    because ORB tolerates far less of a difference than SIFT does.
    """
    rng = np.random.default_rng(seed)
    scene = _cards(rng)
    other = _cards(np.random.default_rng(seed), moved=moved) if moved else scene
    ramp = _ramp(scene.shape[:2])
    f1 = _soften(scene, ramp, blur)              # right half soft
    f2 = _soften(other, 1 - ramp, blur)          # left half soft
    f2 = _pose(f2, dx=dx)
    if distort:
        f2 = _barrel(f2)
    # in linear light, because that is what an exposure difference *is* -- an
    # sRGB multiply is a tone curve change and no linear gain could undo it
    f2 = to_srgb(np.clip(to_linear(f2) * exposure, 0, 1)).round().astype(np.uint8)
    return f1, f2


def _halves(img):
    """(left, right) sharpness, sampled well inside each edge so the fixture's
    soft middle and the frame border stay out of both numbers."""
    s = sharpness(to_linear(img))
    h, w = s.shape
    return (float(s[h//4:3*h//4, int(.08*w):int(.28*w)].mean()),
            float(s[h//4:3*h//4, int(.72*w):int(.92*w)].mean()))


# --------------------------------------------------------------- the merge itself

def test_merge_takes_the_sharp_side_of_each_frame():
    """The whole point: neither input is good everywhere, the output is.

    Both halves of the merge must reach the *better* input's sharpness, not the
    average of the two -- averaging is what a naive blend does, and it would
    still pass a test that only asked the output to beat the worse frame.
    """
    f1, f2 = make_pair()
    out, reports = merge([f1, f2], ["f1", "f2"])
    assert not any(r.failed for r in reports), [r.failed for r in reports]

    l1, r1 = _halves(f1)
    l2, r2 = _halves(f2)
    lo, ro = _halves(out)
    assert l1 > 2 * l2, f"fixture is wrong: frame 1's left should be the sharp one ({l1:.4f} vs {l2:.4f})"
    assert r2 > 2 * r1, f"fixture is wrong: frame 2's right should be the sharp one ({r2:.4f} vs {r1:.4f})"
    assert lo > 0.9 * l1, f"merged left {lo:.4f} lost the sharp frame 1 ({l1:.4f})"
    assert ro > 0.9 * r2, f"merged right {ro:.4f} lost the sharp frame 2 ({r2:.4f})"


def test_output_keeps_the_reference_frame():
    """The first file is the reference: same size, same framing, same pixels
    where it already won. A merge that quietly reframes would break every
    downstream assumption checleaner makes about the photo."""
    f1, f2 = make_pair()
    out, _ = merge([f1, f2], ["f1", "f2"])
    assert out.shape == f1.shape, (out.shape, f1.shape)
    h, w = f1.shape[:2]
    # deep in frame 1's sharp half, the merge is frame 1
    a = f1[h//4:3*h//4, int(.08*w):int(.22*w)].astype(np.float32)
    b = out[h//4:3*h//4, int(.08*w):int(.22*w)].astype(np.float32)
    assert np.abs(a - b).mean() < 2.0, \
        f"merge altered the reference where it won by {np.abs(a - b).mean():.2f}/255"


def test_merge_is_anchored_to_the_reference_tone():
    """focusmerge is geometry and picking, nothing else. The frames differ in
    exposure -- hand-held shots do -- and the merge has to pull the others onto
    the reference rather than land somewhere between: colour is checleaner's job,
    its targets are library-wide, and a merge that drifted would de-match the
    batch it was written to feed.

    The fixture's frame 2 is a known EXPOSURE brighter in linear light, so the
    gain the tool reports has a right answer to be checked against.
    """
    # A pair that differs *only* in blur and exposure: same camera position, no
    # distortion. The bias being tested is the blur's, so nothing else may
    # contribute, and with the frames already aligned the answer is exact.
    scene = _cards(np.random.default_rng(4))
    ramp = _ramp(scene.shape[:2])
    still_a = _soften(scene, ramp)
    still_b = to_srgb(np.clip(to_linear(_soften(scene, 1 - ramp)) * EXPOSURE, 0, 1)
                      ).round().astype(np.uint8)
    _, _, still = align(still_a, still_b, "still")
    for c, name in enumerate("BGR"):
        err = still.gains[c] * EXPOSURE - 1
        assert abs(err) < 0.005, \
            f"{name} gain {still.gains[c]:.4f} is {err:+.2%} off {1 / EXPOSURE:.4f}"

    f1, f2 = make_pair()
    lin, valid, rep = align(f1, f2, "f2")
    for c, name in enumerate("BGR"):
        assert abs(rep.gains[c] - 1 / EXPOSURE) < 0.01, \
            f"{name} gain {rep.gains[c]:.3f}, expected {1 / EXPOSURE:.3f}"
    out, _ = merge([f1, f2], ["f1", "f2"])
    h, w = out.shape[:2]
    box = (slice(h//4, 3*h//4), slice(int(.15*w), int(.85*w)))
    for c, name in enumerate("BGR"):
        before = float(to_linear(f1)[box][:, :, c].mean())
        after = float(to_linear(out)[box][:, :, c].mean())
        assert abs(after / before - 1) < 0.01, \
            f"{name} moved {before:.4f} -> {after:.4f} (linear) across the merge"


# ------------------------------------------------------------------- alignment

def test_alignment_lands_the_frames_on_each_other():
    f1, f2 = make_pair()
    lin, valid, rep = align(f1, f2, "f2")
    assert not rep.failed, rep.failed
    assert rep.inliers > MIN_INLIERS, rep.inliers
    assert rep.reproj < 2.0, f"homography reprojection {rep.reproj:.2f}px"
    a = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY).astype(np.float32)
    b = cv2.cvtColor((np.clip(lin, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8),
                     cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = a.shape
    win = cv2.createHanningWindow((w // 2, h // 2), cv2.CV_32F)
    (dx, dy), _ = cv2.phaseCorrelate(a[h//4:3*h//4, w//4:3*w//4].copy(),
                                     b[h//4:3*h//4, w//4:3*w//4].copy(), win)
    assert np.hypot(dx, dy) < 0.4, f"aligned frames still {dx:+.2f},{dy:+.2f} px apart"


def _misalignment(ref, lin):
    """Median tile shift between the reference and an aligned frame, in px.

    Measured on the tool's own tile grid, and taken as a *median* rather than a
    max: what matters is how far the frames typically sit apart, and one tile of
    defocused desk can post a couple of pixels of noise on its own.
    """
    b = (np.clip(lin, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    d, ok, _ = _tile_shifts(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.float32),
                            cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32),
                            REFINE_TILES)
    return float(np.median(np.hypot(d[..., 0], d[..., 1])[ok]))


def test_local_refinement_beats_the_homography_alone():
    """The fixture's frame 2 is barrel-distorted, which no homography can undo,
    so a residual survives the fit -- and a pixel of misalignment softens whatever
    the blend touches, which is the thing the merge exists to avoid.

    The comparison has to be against the *homography's* output, not the raw
    frame: against the raw frame the camera move alone is 27 px, so any
    refinement at all looks like a triumph. Written that way first, this test
    passed with the refinement disabled.
    """
    f1, f2 = make_pair()
    lin_h, _, _ = align(f1, f2, "f2", refine=False)
    lin_r, _, _ = align(f1, f2, "f2", refine=True)
    before, after = _misalignment(f1, lin_h), _misalignment(f1, lin_r)
    assert before > 0.5, \
        f"fixture no longer needs refining ({before:.2f}px); the test proves nothing"
    assert after < 0.5 * before, \
        f"refinement left {after:.2f}px of the homography's {before:.2f}px"


def test_the_switch_between_frames_is_gradual():
    """No seam may land on a card edge, so the *decision* is blurred before it is
    applied and the changeover spreads over hundreds of pixels.

    Measured as the steepest per-pixel step in the weight map, away from the frame
    border where a hard edge is correct -- past there one frame simply isn't
    covered. A hard per-pixel pick steps by a whole 1.0; the blurred decision tops
    out around 0.25, and its 99.9th percentile is a twentieth of that.
    """
    f1, f2 = make_pair()
    lin, valid, _ = align(f1, f2, "f2")
    W = blend_weights([to_linear(f1), lin],
                      [np.ones(f1.shape[:2], bool), valid])[0]
    core = cv2.erode(valid.astype(np.uint8), np.ones((81, 81), np.uint8))[:-1, :-1] > 0
    step = np.maximum(np.abs(np.diff(W, axis=1))[:-1, :],
                      np.abs(np.diff(W, axis=0))[:, :-1])[core]
    assert step.max() < 0.5, f"weight map steps by {step.max():.2f} in one pixel"
    assert np.percentile(step, 99.9) < 0.10, \
        f"weight map's 99.9th percentile step is {np.percentile(step, 99.9):.3f}"


def test_a_different_scene_is_refused_not_blended():
    """Point it at two unrelated photos and it must say so. Blending them would
    produce a plausible-looking file that is nonsense, which is worse than an
    error."""
    f1, _ = make_pair()
    # a different deskful of prints, not noise: noise yields so few matches that
    # the inlier gate is never what refuses it, and the test then passes with
    # MIN_INLIERS set to 1
    other = _cards(np.random.default_rng(77))
    out, reports = merge([f1, other], ["f1", "other"])
    assert reports[1].failed, "an unrelated frame was merged in silently"
    assert reports[1].inliers < MIN_INLIERS, reports[1].inliers
    assert np.array_equal(out, f1), "the reference should come back untouched"


# ------------------------------------------------------------- the movement check

def test_a_lens_is_not_mistaken_for_a_moved_print():
    """The movement check's model is a *cubic* surface, because that is the shape
    a lens leaves: radial distortion displaces a point by k*r^2 times its radius.

    Fitting the tile shifts straight rather than through the images, so the model
    order is the only thing under test. A radial field peaking at 8 px, plus a
    little measurement noise, is what a wide framing change looks like and must
    read as clean -- a quadratic surface leaves 4 px of it unexplained and would
    report the corners as prints that moved. One block of tiles displaced on its
    own is the thing that should be reported, and only it.
    """
    tiles = 10
    gy, gx = np.mgrid[0:tiles, 0:tiles].astype(np.float32) / (tiles - 1) - 0.5
    k = 8.0 / (0.5 * np.sqrt(2)) ** 3
    lens = np.stack([k * (gx * gx + gy * gy) * gx,
                     k * (gx * gx + gy * gy) * gy], -1).astype(np.float32)
    lens += np.random.default_rng(0).normal(0, 0.3, lens.shape).astype(np.float32)
    ok = np.ones((tiles, tiles), bool)
    moved, _ = _moved_tiles(lens, ok)
    assert not moved.any(), \
        f"{moved.sum()} tiles of a plain lens residual read as movement"

    nudged = lens.copy()
    nudged[4:6, 3:5] += np.array([20.0, -12.0], np.float32)
    moved, off = _moved_tiles(nudged, ok)
    assert set(zip(*np.where(moved))) == {(4, 3), (4, 4), (5, 3), (5, 4)}, \
        f"flagged {sorted(zip(*np.where(moved)))}, expected the 2x2 block at (4,3)"
    assert off[moved].max() > 20, off[moved].max()


def test_a_print_that_moved_is_reported():
    """The one silent failure this tool has. A nudged print aligns nowhere, so
    the merge blends two positions into a ghost -- and every other number in the
    report still looks fine, because the other twelve prints did line up."""
    f1, f2 = make_pair(moved=((1, 2), (26, 14)))
    _, _, rep = align(f1, f2, "f2")
    assert rep.moved, "a print moved 30px and nothing was reported"
    worst = max(r[4] for r in rep.moved)
    assert worst > MOVE_TOL, worst
    # and it points at the card that actually moved, not somewhere else
    cx = GAP + 2 * (CARD_W + GAP) + CARD_W / 2
    cy = GAP + 1 * (CARD_H + GAP) + CARD_H / 2
    hits = [r for r in rep.moved
            if r[0] - r[2] <= cx <= r[0] + 2 * r[2] and r[1] - r[3] <= cy <= r[1] + 2 * r[3]]
    assert hits, f"movement reported at {[(r[0], r[1]) for r in rep.moved]}, not near ({cx:.0f},{cy:.0f})"


def test_an_unmoved_layout_reports_no_movement():
    """The other half of the check, and the one that decides whether the warning
    is worth anything: a real pair differs everywhere -- different focus, different
    exposure, lens distortion -- and none of that may read as movement."""
    f1, f2 = make_pair()
    _, _, rep = align(f1, f2, "f2")
    assert not rep.moved, f"clean pair reported {len(rep.moved)} moved regions: {rep.moved}"


def test_tiles_the_other_shot_does_not_cover_do_not_vote():
    """With the camera moved far enough sideways, whole tiles along one edge have
    no counterpart in the second shot. Correlating those against blank does not
    give a small error, it gives an arbitrary one -- 58 px in this fixture -- and
    the movement check then reports a print that never moved.
    """
    f1, f2 = make_pair(dx=90.0)
    _, valid, rep = align(f1, f2, "f2")
    assert valid.mean() < 0.95, \
        f"fixture covers {valid.mean():.1%} of the frame; nothing falls off the edge"
    assert not rep.moved, f"uncovered tiles reported as movement: {rep.moved}"


# ------------------------------------------------------- opt-in: the real photos

def _photo(folder, stamp):
    """The source photo in `folder` whose name carries `stamp`, or None. Real
    photos are named by the time part alone -- see tests/test_pipeline.py."""
    hits = [h for h in sorted(glob.glob(os.path.join(folder, f"*{stamp}*")))
            if os.path.isfile(h)]
    assert len(hits) < 2, f"{stamp} matches more than one photo: {hits}"
    return hits[0] if hits else None


def _merged_source(stamp):
    """A shot that went into a merge, wherever it now lives.

    Once a merge is adopted its inputs move to `<batch>/raw/`, so that the batch
    holds the merged frame instead of the two soft originals -- checleaner reads
    only the loose files, so a subfolder takes them out of the run. These tests
    still want the originals, and looking only in the batch folder would find the
    *merge* under the reference's own timestamp and then skip on the second file:
    a green run that had stopped checking anything.
    """
    batch = os.path.join(REPO, "chekis", "main")
    return _photo(os.path.join(batch, "raw"), stamp) or _photo(batch, stamp)


# The 5x3 grid of prints in 002232944, measured off the paper blob's bounding
# box; row A holds three, centred. Only used to score the real pair per print.
REAL_GRID = (243, 3152, 111, 2879)


def _real_cards():
    x0, x1, y0, y1 = REAL_GRID
    cw, ch = (x1 - x0) / 5, (y1 - y0) / 3
    for r, (lab, cols) in enumerate([("A", 3), ("B", 5), ("C", 5)]):
        left = x0 + (5 - cols) / 2 * cw
        for j in range(cols):
            bx, by = left + j * cw, y0 + r * ch
            yield (f"{lab}{j+1}",
                   (slice(int(by + .10 * ch), int(by + .65 * ch)),
                    slice(int(bx + .14 * cw), int(bx + .86 * cw))))


def test_real_pair_merges_to_the_best_of_both():
    """The measurement the tool exists for, on the photos it was written for.

    002232944 is sharp on rows A and B1-B4, 002255786 on B5 and row C. A1 is
    2.5x sharper in the first, C5 2.5x sharper in the second, so keeping either
    photo alone throws away a print. Every print in the merge must reach the
    better frame's sharpness; the measured worst is 97%.
    """
    pa, pb = _merged_source("002232944"), _merged_source("002255786")
    if not pa or not pb:
        skip("the reference pair is not present (photos are gitignored)")
    a, b = cv2.imread(pa), cv2.imread(pb)
    out, reports = merge([a, b], ["a", "b"])
    assert not any(r.failed for r in reports), [r.failed for r in reports]
    assert not any(r.moved for r in reports), "nothing moved between these two shots"

    lin_b, _, _ = align(a, b, "b")
    sa, sb, so = sharpness(to_linear(a)), sharpness(lin_b), sharpness(to_linear(out))
    worst, worst_card = 1e9, ""
    for name, box in _real_cards():
        va, vb, vo = sa[box].mean(), sb[box].mean(), so[box].mean()
        if vo / max(va, vb) < worst:
            worst, worst_card = vo / max(va, vb), name
        if name == "A1":
            assert va > 2 * vb, f"A1 should be much sharper in 002232944 ({va:.4f} vs {vb:.4f})"
        if name == "C5":
            assert vb > 2 * va, f"C5 should be much sharper in 002255786 ({vb:.4f} vs {va:.4f})"
    assert worst > 0.93, f"{worst_card} kept only {worst:.0%} of the best frame"


def test_real_pair_is_not_reported_as_having_moved():
    """Nothing was touched between these two shots, and the warning has to stay
    quiet on them or it will be ignored on the pair where it matters."""
    pa, pb = _merged_source("002232944"), _merged_source("002255786")
    if not pa or not pb:
        skip("the reference pair is not present (photos are gitignored)")
    _, _, rep = align(cv2.imread(pa), cv2.imread(pb), "b")
    assert not rep.moved, f"reported {len(rep.moved)} moved regions on a still desk"
    assert rep.inliers > 500, rep.inliers


# -------------------------------------------------------------------------- CLI

def test_cli_writes_a_file_and_check_does_not():
    from tools.focusmerge import main
    f1, f2 = make_pair()
    with tempfile.TemporaryDirectory() as tmp:
        p1 = os.path.join(tmp, "one.jpg")
        p2 = os.path.join(tmp, "two.jpg")
        out = os.path.join(tmp, "merged.jpg")
        cv2.imwrite(p1, f1)
        cv2.imwrite(p2, f2)
        argv = sys.argv
        try:
            sys.argv = ["focusmerge", p1, p2, "--check"]
            assert main() == 0
            assert not os.path.exists(out), "--check wrote a file"
            sys.argv = ["focusmerge", p1, p2, "-o", out]
            assert main() == 0
            assert os.path.exists(out)
            assert cv2.imread(out).shape == f1.shape
        finally:
            sys.argv = argv


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
        except Exception as e:            # a crash is a failure, not a pass
            failed += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
