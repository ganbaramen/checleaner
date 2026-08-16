#!/usr/bin/env python3
"""Regression tests for the checleaner pipeline (CLAUDE.md next-steps item 1).

Both implementations are otherwise checked by hand; this pins the numbers that
must not move. Run it either way -- it needs nothing beyond checleaner's own
deps:

    python3 tests/test_pipeline.py        # standalone: prints PASS/FAIL/SKIP, exits nonzero on fail
    pytest tests/                          # also works; skips register natively

Fixtures are *synthetic*, generated deterministically here rather than committed:
the real photos are personal and gitignored, so a committed fixture folder would
either leak them or bit-rot. A drawn card can't reproduce a real print's texture,
but it exercises the exact invariants we care about -- colour targets, card
aspect, which-way-up, and the single-vs-several decision -- and being drawn, its
ground truth is known, which a real photo's isn't. The opt-in real-photo tier at
the bottom asserts on the actual library when it's present and skips otherwise.

The asserted numbers trace to docs/HISTORY.md and the CLAUDE.md invariants:
white 238.8, black 2.2, instax aspect 1.5926, border ratio ~2.1.
"""
import os
import sys
import tempfile

import numpy as np
import cv2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import checleaner
from checleaner import (measure, solve_levels, to_linear, to_srgb, soft_shoulder,
                        detect_print, warp, orient, build_parser, content_rotation,
                        ASPECT)
from tools.detect import classify   # the single/single?/multi gate, one copy


class _Skip(Exception):
    pass


def skip(msg):
    """Skip that works both standalone (caught by the runner below) and under
    pytest (where it should register as a real skip, not a failure)."""
    if "pytest" in sys.modules:
        import pytest
        pytest.skip(msg)
    raise _Skip(msg)


DEFAULTS = build_parser().parse_args(["."])   # the CLI's own thresholds

DESK = np.array([95, 66, 47], np.float32)      # warm, mid-dark: red > blue, unlike paper
BORDER = np.array([232, 232, 231], np.float32)  # bright, near-neutral: the paper frame
WINDOW = np.array([70, 88, 120], np.float32)    # the photo area: darker, and not near-neutral


def _noise(shape, s, seed):
    return np.random.default_rng(seed).normal(0, s, shape)


def make_single(frame_w=1200, upside_down=False, seed=0):
    """One instax front on desk. Portrait card at true aspect, with an
    off-centre photo window (narrow border one end, wide 'signature' border the
    other) and a near-black block inside so the black point is measurable.
    Generated wide-border-down unless upside_down. Returns an RGB uint8 frame."""
    frame_h = int(frame_w * 1.4)
    img = np.clip(DESK + _noise((frame_h, frame_w, 3), 2, seed), 0, 255)
    card_h = int(frame_h * 0.62)
    card_w = int(card_h / ASPECT)
    y0, x0 = (frame_h - card_h) // 2, (frame_w - card_w) // 2
    img[y0:y0+card_h, x0:x0+card_w] = np.clip(BORDER + _noise((card_h, card_w, 3), 2, seed+1), 0, 255)

    mx = int(card_w * 0.06)
    narrow, wide = int(card_h * 0.05), int(card_h * 0.16)
    wy0 = y0 + (wide if upside_down else narrow)
    wy1 = y0 + card_h - (narrow if upside_down else wide)
    wx0, wx1 = x0 + mx, x0 + card_w - mx
    img[wy0:wy1, wx0:wx1] = np.clip(WINDOW + _noise((wy1-wy0, wx1-wx0, 3), 2, seed+2), 0, 255)
    bh, bw = (wy1-wy0)//4, (wx1-wx0)//3
    img[wy0:wy0+bh, wx0:wx0+bw] = np.clip(np.array([13, 15, 17]) + _noise((bh, bw, 3), 1, seed+3), 0, 255)
    return img.astype(np.uint8)


def make_row(frame_w=1400, cols=2, seed=0):
    """Several prints touching in a row -- they merge into one blob far too wide
    to be a single card. The everyday multi-print shot."""
    frame_h = int(frame_w * 1.2)
    img = np.clip(DESK + _noise((frame_h, frame_w, 3), 2, seed), 0, 255)
    card_h = int(frame_h * 0.62)
    card_w = int(card_h / ASPECT)
    oy, ox = (frame_h - card_h) // 2, (frame_w - cols*card_w) // 2
    for c in range(cols):
        x0 = ox + c*card_w
        img[oy:oy+card_h, x0:x0+card_w] = np.clip(BORDER + _noise((card_h, card_w, 3), 2, seed+c), 0, 255)
        img[oy+int(card_h*.08):oy+int(card_h*.92), x0+int(card_w*.08):x0+int(card_w*.92)] = WINDOW
    return img.astype(np.uint8)


def make_grid(frame_w=1400, gap=16, rot=4.0, seed=7):
    """A 2x2 grid of hand-placed (so slightly rotated) cards. Two stacked cards
    are as tall as they are wide-per-two, so the grid's *aspect* lands right in
    the single-card window and its bounding box is *filled* -- only the notched,
    misaligned outer boundary (low solidity) betrays that it isn't one card.
    This is the exact trap the solidity check exists to catch."""
    rng = np.random.default_rng(seed)
    frame_h = int(frame_w * 1.2)
    img = np.clip(DESK + rng.normal(0, 2, (frame_h, frame_w, 3)), 0, 255)
    card_h = int(frame_h * 0.6 / 2)
    card_w = int(card_h / ASPECT)
    tw, th = 2*card_w + gap, 2*card_h + gap
    oy, ox = (frame_h - th) // 2, (frame_w - tw) // 2
    for r in range(2):
        for c in range(2):
            y0, x0 = oy + r*(card_h+gap), ox + c*(card_w+gap)
            card = np.full((card_h, card_w, 3), BORDER, np.float32)
            card[int(card_h*.08):int(card_h*.92), int(card_w*.08):int(card_w*.92)] = WINDOW
            M = cv2.getRotationMatrix2D((card_w/2, card_h/2), rng.uniform(-rot, rot), 1.0)
            card = cv2.warpAffine(card, M, (card_w, card_h), borderValue=tuple(DESK.tolist()))
            img[y0:y0+card_h, x0:x0+card_w] = np.clip(card + rng.normal(0, 2, card.shape), 0, 255)
    return img.astype(np.uint8)


def _write(rgb):
    """Drop an RGB frame to a temp PNG the detector can read; caller cleans up."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cv2.imwrite(path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return path


def _is_single(det):
    return classify(det, DEFAULTS) == "single"


# --------------------------------------------------------------- invariant tests

def test_colour_targets_hit_238_and_2():
    """White border -> 238.8, black point -> 2.2, the fixed library-wide anchors.
    solve_levels iterates to land these exactly regardless of the input's own
    exposure, so this is a true invariant, not just a golden number."""
    rgb = make_single().astype(np.float32)
    white_t = np.full(3, float(to_linear(np.array([238.8]))[0]))
    black_t = np.full(3, float(to_linear(np.array([2.2]))[0]))
    gain, off = solve_levels(rgb, measure(rgb), white_t, black_t)
    corrected = to_srgb(soft_shoulder(np.clip(to_linear(rgb) * gain + off, 0, None)))
    after = measure(corrected)
    white, black = to_srgb(after.white), to_srgb(after.black)
    assert np.all(np.abs(white - 238.8) < 0.8), f"white landed {np.round(white,2)}, want 238.8"
    assert np.all(np.abs(black - 2.2) < 0.8), f"black landed {np.round(black,3)}, want 2.2"


def test_single_card_detects_at_true_aspect():
    """A lone card is found as one blob at instax aspect and clears the single gate."""
    p = _write(make_single())
    try:
        d = detect_print(p)
    finally:
        os.remove(p)
    assert d.n_blobs == 1, f"n_blobs={d.n_blobs}"
    assert abs(d.aspect - ASPECT) < 0.03, f"aspect={d.aspect:.3f}, want ~{ASPECT:.3f}"
    assert d.fill >= DEFAULTS.min_fill and d.solidity >= DEFAULTS.min_solidity
    assert _is_single(d), "a clean single card must classify as single"


def _window_gaps(crop_bgr):
    """(gap above the photo window, gap below it) in the oriented crop."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    mid = gray[:, gray.shape[1]//3: 2*gray.shape[1]//3].mean(axis=1)
    dark = np.where(mid < 150)[0]
    return int(dark.min()), int(crop_bgr.shape[0] - 1 - dark.max())


def test_orientation_puts_wide_border_at_bottom():
    """orient() must normalise both an already-upright card and an upside-down
    one to wide-signature-border-down -- i.e. the photo window ends up nearer
    the top -- with a border ratio well clear of the 'looked alike' floor."""
    for upside_down in (False, True):
        p = _write(make_single(upside_down=upside_down))
        try:
            d = detect_print(p)
            crop, ratio = orient(warp(cv2.imread(p), d.quad, 900))
        finally:
            os.remove(p)
        top_gap, bottom_gap = _window_gaps(crop)
        assert top_gap < bottom_gap, (
            f"upside_down={upside_down}: window not left near the top "
            f"(top_gap={top_gap}, bottom_gap={bottom_gap})")
        assert ratio > DEFAULTS.min_border_ratio, f"border ratio {ratio:.2f} too low"


def test_row_of_prints_is_not_a_single_card():
    """Two prints side by side merge into one wide blob; it must not be cropped
    and rotated as though it were a single card (the sideways-output bug)."""
    p = _write(make_row(cols=2))
    try:
        d = detect_print(p)
    finally:
        os.remove(p)
    assert not _is_single(d), f"row misread as single (aspect {d.aspect:.3f})"


def test_grid_is_rejected_by_solidity_not_aspect():
    """A 2x2 grid lands inside the single-card aspect+fill window yet is only one
    blob -- solidity is the sole discriminator, so verify it is what rejects it."""
    p = _write(make_grid())
    try:
        d = detect_print(p)
    finally:
        os.remove(p)
    assert d.n_blobs == 1, f"grid split into {d.n_blobs} blobs; retune the fixture"
    assert DEFAULTS.aspect_lo <= d.aspect <= DEFAULTS.aspect_hi, f"aspect {d.aspect:.3f} out of window"
    assert d.fill >= DEFAULTS.min_fill, f"fill {d.fill:.3f} already fails; solidity not exercised"
    assert d.solidity < DEFAULTS.min_solidity, f"solidity {d.solidity:.3f} did not catch the grid"
    assert not _is_single(d)


# --------------------------------------------------- opt-in: the real library

# Files discussed as multi-print/overlap shots that must never be treated as a
# single card. Skipped per-file when absent, so a fresh clone (no photos) still
# passes; present, it pins the behaviour on the real images.
REAL_NOT_SINGLE = [
    "PXL_20260427_023359428.MP.jpg",   # the original sideways complaint (landscape stack)
    "PXL_20260803_041037832.MP.jpg",   # 3x3-ish grid
    "PXL_20260427_023727013.MP.jpg",   # four overlapping prints
    "PXL_20260427_023126095.MP.jpg",   # two landscape prints stacked
]


def test_real_multiprint_photos_never_single():
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    checked = 0
    for name in REAL_NOT_SINGLE:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            continue
        checked += 1
        assert not _is_single(detect_print(path)), f"{name} misclassified as single"
    if checked == 0:
        skip("none of the named reference photos are present")


def test_real_grid_photo_fails_solidity():
    path = os.path.join(REPO, "chekis", "main", "PXL_20260803_041037832.MP.jpg")
    if not os.path.exists(path):
        skip("grid reference photo not present")
    d = detect_print(path)
    assert d.solidity < DEFAULTS.min_solidity, f"real grid solidity {d.solidity:.3f} no longer caught"


# Multi-print photos that align_multi levels but leaves mis-turned, with the
# quarter/half turn (in 90-degree CCW units) that stands them upright...
REAL_REORIENT = {
    "PXL_20260427_023359428.MP.jpg": 1,   # row of 2 portrait, a quarter turn off
    "PXL_20260501_015640226.MP.jpg": 1,
    "PXL_20260501_015731072.MP.jpg": 1,
    "PXL_20260427_023126095.MP.jpg": 1,   # mixed landscape+portrait, all a quarter off
    "PXL_20260427_023727013.MP.jpg": 2,   # row of 4 portrait, upside down
}
# ...and multi-print photos already upright, which must be left untouched.
REAL_UPRIGHT = [
    "PXL_20260427_023252712.MP.jpg",
    "PXL_20260810_014211016.MP.jpg",
    "PXL_20260427_022950306.MP.jpg",      # a near-tie the margin rule must protect
]


def test_content_rotation_no_ops_without_a_detector():
    """The reorientation is optional: with no face model it returns 'no turn'
    rather than erroring, so a machine that can't load it just gets the older
    leave-it-level behaviour."""
    saved = checleaner._FACE_DET
    checleaner._FACE_DET = None            # force 'load already failed'
    try:
        import numpy as _np
        assert content_rotation(_np.zeros((400, 300, 3), _np.uint8)) == 0
    finally:
        checleaner._FACE_DET = saved


def test_real_multiprint_reorientation():
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    if checleaner._face_detector() is None:
        skip("face model unavailable (offline / not cached)")
    checked = 0
    for name, want in REAL_REORIENT.items():
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            continue
        checked += 1
        got = content_rotation(cv2.imread(path))
        assert got == want, f"{name}: reorient turned {got*90}, want {want*90}"
    for name in REAL_UPRIGHT:
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            continue
        checked += 1
        got = content_rotation(cv2.imread(path))
        assert got == 0, f"{name}: already upright but reorient turned it {got*90}"
    if checked == 0:
        skip("none of the reorientation reference photos are present")


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
