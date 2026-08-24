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
import glob
import tempfile

import numpy as np
import cv2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import io
import contextlib
import csv

import checleaner
from checleaner import (measure, solve_levels, to_linear, to_srgb, soft_shoulder,
                        detect_print, detect_all_prints, align_multi, warp, orient,
                        build_parser, content_rotation, count_windows,
                        single_fit, _needs_review, trim_desk,
                        _cached_measurement, run, ASPECT)
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


def add_glare(img, seed=9):
    """Add a patch of specular desk glare below whatever is in the frame.

    An ellipse (fill = pi/4 ~ 0.785, right where real glare measured), big
    enough to clear the 3%-of-frame blob threshold, and far enough below the
    prints that the segmentation close can't bridge the two into one blob. So it
    arrives as a *separate* blob, which is the interesting case: it can't fool
    the single-card shape test, but align_multi crops around the union of every
    blob, so one bright patch in a corner drags the crop out to cover desk
    unless the glare filter drops it.
    """
    img = img.astype(np.float32)
    h, w = img.shape[:2]
    cy, cx = h - int(h * 0.06), w // 2
    ry, rx = int(h * 0.05), int(w * 0.25)
    yy, xx = np.ogrid[:h, :w]
    blob = ((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2 <= 1.0
    img[blob] = np.clip(BORDER + _noise((int(blob.sum()), 3), 2, seed), 0, 255)
    return img.astype(np.uint8)


def make_single_with_glare(frame_w=1200, seed=0):
    """A lone card plus a patch of desk glare that segments as its own blob."""
    return add_glare(make_single(frame_w, seed=seed), seed=seed + 9)


# A pale surface with a cool cast -- the shape of the failure the backs batch
# hit, where the frame read white as (137,161,187) against the paper's neutral
# (145,140,132) and every print came out pushed warm.
PALE_DESK = np.array([206, 214, 228], np.float32)


def make_card_on_pale_desk(frame_w=1200, seed=0):
    """A mostly-dark card on a pale, cool-cast surface: the case where the
    background, not the print, wins the 'brightest smooth pixels' test.

    Returns (frame, paper_mask). The mask comes from the known card rectangle
    rather than the detector, so this pins measure()'s contract and not the
    segmentation's.
    """
    frame_h = int(frame_w * 1.4)
    img = np.clip(PALE_DESK + _noise((frame_h, frame_w, 3), 2, seed), 0, 255)

    card_h = int(frame_h * 0.34)                  # small: little white to find
    card_w = int(card_h / ASPECT)
    y0, x0 = (frame_h - card_h) // 2, (frame_w - card_w) // 2
    paper = np.zeros((frame_h, frame_w), bool)
    paper[y0:y0+card_h, x0:x0+card_w] = True
    img[paper] = np.clip(BORDER + _noise((int(paper.sum()), 3), 2, seed+1), 0, 255)

    # a dark photo window covering most of the card, leaving a thin border
    mx, my = int(card_w * 0.07), int(card_h * 0.06)
    img[y0+my:y0+card_h-my, x0+mx:x0+card_w-mx] = np.clip(
        np.array([28, 30, 34]) + _noise((card_h-2*my, card_w-2*mx, 3), 2, seed+2), 0, 255)
    return img.astype(np.uint8), paper


def make_single_on_foreign_desk(frame_w=1200, seed=0):
    """A lone card on a pale but still *warm* surface -- light wood rather than
    the walnut. Warm and smooth, so it passes the desk test and gets a desk
    reading; far too bright for the damped gamma to reach the batch's target."""
    img = make_single(frame_w, seed=seed).astype(np.float32)
    desk = np.all(np.abs(img - DESK) < 12, axis=2)
    img[desk] = np.clip(np.array([190, 150, 110])
                        + _noise((int(desk.sum()), 3), 2, seed + 7), 0, 255)
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


def _draw_signed_card(img, y0, x0, card_h, card_w, seed):
    """One print with its photo window and a signature scrawled across it.

    Every print in this library is signed, and the ink matters to the geometry:
    a stroke crossing out of the photo area merges with it, so the hole the
    window leaves in the paper mask is no longer a rectangle and the angle
    fitted to it stops being trustworthy. Fixtures that leave the windows clean
    therefore test a photo this library doesn't contain.
    """
    img[y0:y0+card_h, x0:x0+card_w] = np.clip(
        BORDER + _noise((card_h, card_w, 3), 2, seed), 0, 255)
    wy0, wy1 = y0 + int(card_h*.08), y0 + int(card_h*.60)
    wx0 = x0 + int(card_w*.12)
    img[wy0:wy1, wx0:x0+int(card_w*.88)] = WINDOW
    cv2.line(img, (wx0 + int(card_w*.08), wy1 - int(card_h*.04)),
             (x0 + int(card_w*.74), y0 + int(card_h*.84)),
             tuple(float(v) for v in WINDOW), int(card_w * .24))


def make_signed_row(frame_w=1400, cols=2, tilt=1.5, offset=0.0, seed=3):
    """A row of signed prints (see _draw_signed_card), turned by `tilt`.

    `offset` slides the row sideways as a fraction of the frame width, for the
    one-sided-desk case in align_multi.
    """
    frame_h = int(frame_w * 1.2)
    img = np.clip(DESK + _noise((frame_h, frame_w, 3), 2, seed), 0, 255)
    card_w = int(frame_w * 0.68 / cols)          # the row spans most of the frame
    card_h = int(card_w * ASPECT)
    oy = (frame_h - card_h) // 2
    ox = int((frame_w - cols * card_w) // 2 + offset * frame_w)
    for c in range(cols):
        _draw_signed_card(img, oy, ox + c * card_w, card_h, card_w, seed + c)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if tilt:
        M = cv2.getRotationMatrix2D((frame_w/2, frame_h/2), tilt, 1.0)
        img = cv2.warpAffine(img, M, (frame_w, frame_h),
                             flags=cv2.INTER_LINEAR, borderValue=tuple(DESK.tolist()))
    return img


def make_staggered_pile(frame_w=1200, cards=3, seed=5):
    """Level prints dealt corner to corner, so they merge into one blob whose
    minAreaRect follows the *staircase* rather than any card in it.

    Half a card's step each way is enough to turn that rectangle 32 degrees off
    a pile that is perfectly straight -- the same trap a real photo in this
    library sets at 33 degrees. Every straight run of the same outline is still
    a card border lying dead level.
    """
    frame_h = int(frame_w * 1.6)
    img = np.clip(DESK + _noise((frame_h, frame_w, 3), 2, seed), 0, 255)
    card_w = int(frame_w * 0.34)
    card_h = int(card_w * ASPECT)
    step_x, step_y = card_w // 2, card_h // 2
    oy = (frame_h - card_h - (cards-1)*step_y) // 2
    ox = (frame_w - card_w - (cards-1)*step_x) // 2
    for c in range(cards):
        _draw_signed_card(img, oy + c*step_y, ox + c*step_x, card_h, card_w, seed+c)
    return np.clip(img, 0, 255).astype(np.uint8)


def make_single_with_welded_glare(frame_w=1200, seed=0):
    """A lone card with a patch of desk glare close enough that the
    segmentation close welds the two into one blob.

    Distinct from make_single_with_glare, where the patch stands off far enough
    to segment separately: there the blob count catches it, here it becomes part
    of the card's own blob and drags the fitted rectangle out over desk. The
    patch fades at its edges, which is the only thing that tells it from paper
    (`CARD_EDGE_SHARP`), so it is drawn as a soft-edged ellipse rather than a
    hard-edged one.
    """
    img = make_single(frame_w, seed=seed).astype(np.float32)
    h, w = img.shape[:2]
    card_h = int(h * 0.62)
    card_w = int(card_h / ASPECT)
    x1 = (w + card_w) // 2                          # the card's right edge
    gap = int(w * 0.02)                             # too wide for the open, not for the close
    alpha = np.zeros((h, w), np.float32)
    alpha[(h - card_h) // 2:(h + card_h) // 2, x1 + gap:x1 + gap + int(w * 0.045)] = 1.0
    alpha = cv2.GaussianBlur(alpha, (0, 0), w * 0.012)   # soft edges: this is the tell
    img = img * (1 - alpha[:, :, None]) + BORDER * alpha[:, :, None]
    return np.clip(img, 0, 255).astype(np.uint8)


def make_flush_grid(frame_w=1500, n=3, seed=13):
    """An n x n block of cards laid flush, with no gaps at all.

    The one arrangement that beats every shape test outright: n rows of n cards
    is n*card_h by n*card_w, so its *aspect is exactly a card's*, and with the
    borders touching there are no seams for fill or solidity to catch either --
    all three land at a clean card's numbers. Only the photo windows give it
    away, one per print. This is what the window backstop exists for, and
    nothing else in the fixture set reaches it.
    """
    frame_h = int(frame_w * 1.2)
    img = np.clip(DESK + _noise((frame_h, frame_w, 3), 2, seed), 0, 255)
    card_h = int(frame_h * 0.78 / n)
    card_w = int(card_h / ASPECT)
    oy, ox = (frame_h - n * card_h) // 2, (frame_w - n * card_w) // 2
    for r in range(n):
        for c in range(n):
            y0, x0 = oy + r * card_h, ox + c * card_w
            img[y0:y0+card_h, x0:x0+card_w] = np.clip(
                BORDER + _noise((card_h, card_w, 3), 2, seed + r * n + c), 0, 255)
            img[y0+int(card_h*.10):y0+int(card_h*.72),
                x0+int(card_w*.14):x0+int(card_w*.86)] = WINDOW
    return np.clip(img, 0, 255).astype(np.uint8)


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


def _photo(folder, stamp):
    """The source photo in `folder` whose name carries `stamp`, or None if it
    isn't there (the opt-in tier reads that as "skip this one").

    Real photos are named by the *time* part of their filename alone --
    `012024586`, not `PXL_YYYYMMDD_012024586.MP.jpg`. The time is unique across
    the whole library, so the date and extension are only noise to read past,
    and the stamp survives a file being renamed or re-exported.
    """
    hits = [h for h in sorted(glob.glob(os.path.join(folder, f"*{stamp}*")))
            if os.path.isfile(h)]
    assert len(hits) < 2, f"{stamp} matches more than one photo: {hits}"
    return hits[0] if hits else None


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


def test_paper_confinement_leaves_the_normal_desk_alone():
    """The justification for confining the white anchor: on this desk it changes
    nothing. Measured over the real library it was identical on 137 of 140 files
    and moved the gain by 0.000% at the median, which is what lets it ship
    without de-matching every batch already processed against 238.8/2.2."""
    rgb = make_single().astype(np.float32)
    h, w = rgb.shape[:2]
    card_h = int(h * 0.62)
    card_w = int(card_h / ASPECT)
    y0, x0 = (h - card_h) // 2, (w - card_w) // 2
    paper = np.zeros((h, w), bool)
    paper[y0:y0+card_h, x0:x0+card_w] = True

    frame = to_srgb(measure(rgb).white)
    confined = to_srgb(measure(rgb, paper=paper).white)
    assert np.all(np.abs(frame - confined) < 1.0), \
        f"confinement moved white on a normal desk: {np.round(frame,2)} -> {np.round(confined,2)}"


def test_white_anchor_comes_from_the_paper_not_the_background():
    """A dark card on a pale, cool surface: frame-wide, the *table* is the
    brightest smooth thing, so it becomes the white reference and every channel
    gain skews to neutralise the table's cast -- which pushes the print the
    opposite way. Confined to the paper, white is the border again."""
    rgb, paper = make_card_on_pale_desk()
    rgb = rgb.astype(np.float32)

    frame = to_srgb(measure(rgb).white)
    confined = to_srgb(measure(rgb, paper=paper).white)
    assert frame[0] - frame[2] < -10, \
        f"fixture isn't reproducing the cast: frame white {np.round(frame,1)}"
    assert abs(confined[0] - confined[2]) < 3, \
        f"paper-confined white should be neutral, got {np.round(confined,1)}"
    assert np.all(np.abs(confined - BORDER) < 3), \
        f"paper-confined white {np.round(confined,1)} should be the border {BORDER}"

    white_t = np.full(3, float(to_linear(np.array([238.8]))[0]))
    black_t = np.full(3, float(to_linear(np.array([2.2]))[0]))
    g_frame, _ = solve_levels(rgb, measure(rgb), white_t, black_t)
    g_paper, _ = solve_levels(rgb, measure(rgb, paper=paper), white_t, black_t, paper=paper)
    # the frame-wide solve has to stretch red much harder than blue to undo the
    # table; the confined one barely separates the channels at all
    assert g_frame.max() / g_frame.min() > 1.15, \
        f"expected a skewed frame-wide gain, got {np.round(g_frame,3)}"
    assert g_paper.max() / g_paper.min() < 1.05, \
        f"expected a near-neutral confined gain, got {np.round(g_paper,3)}"


def test_foreign_background_is_left_out_of_desk_matching():
    """A photo on a different surface gets no desk gamma at all, rather than the
    largest one the clamp allows. The clamp *is* the test: a background the
    damped curve can't reach isn't this batch's desk, so there is nothing
    sensible to pull it toward."""
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(3):
            cv2.imwrite(os.path.join(tmp, f"desk_{i}.jpg"),
                        cv2.cvtColor(make_single(seed=i * 10), cv2.COLOR_RGB2BGR))
        cv2.imwrite(os.path.join(tmp, "foreign.jpg"),
                    cv2.cvtColor(make_single_on_foreign_desk(seed=3), cv2.COLOR_RGB2BGR))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert run(build_parser().parse_args([tmp])) == 0
        out = buf.getvalue()
        assert "foreign.jpg" in out and "background isn't this batch's desk" in out, out
        assert "desk target" in out and "from 3 images" in out, \
            f"the foreign desk should be out of the target too:\n{out}"

        rows = {r["file"]: r for r in csv.DictReader(open(os.path.join(tmp, "report.csv")))}
        assert rows["foreign.jpg"]["desk_match"] == "foreign", rows["foreign.jpg"]
        assert rows["desk_0.jpg"]["desk_match"] == "matched", rows["desk_0.jpg"]
        # skipping the match is not a defect in the photo: nothing to review
        assert rows["foreign.jpg"]["dest"] == rows["desk_0.jpg"]["dest"] or \
            "desk" not in rows["foreign.jpg"]["flags"], \
            "opting out of desk matching must not route a file to review/"


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


def test_desk_glare_does_not_make_a_single_look_multi():
    """A specular highlight on the desk segments as its own bright, near-neutral
    blob. It used to break the n_blobs == 1 test and push flawless single cards
    down the multi-print path; only card-shaped blobs count toward the total, and
    glare is never rectangular."""
    p = _write(make_single_with_glare())
    try:
        d = detect_print(p)
        seg = checleaner._segment_prints(p, 1100)
        n_bright = len(seg["big"])
    finally:
        os.remove(p)
    assert n_bright >= 2, "fixture no longer produces a separate glare blob; retune it"
    assert d.n_blobs == 1, f"glare counted as a print (n_blobs={d.n_blobs})"
    assert _is_single(d), "a single card beside desk glare must still classify as single"


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


def test_align_crop_picks_best_fit_aspect():
    """align_multi picks the CROP_ASPECTS shape with the most balanced margins:
    a row of two portrait cards (bbox ~1.26) crops at 4:3, and with a quarter
    turn folded in, the same photo crops at 3:4 -- the shape is chosen for the
    FINAL orientation, so a turn can never smuggle in an excluded ratio."""
    p = _write(make_row(cols=2))
    try:
        dets = detect_all_prints(p)
        img = cv2.imread(p)
        out = align_multi(img, dets)
        assert out is not None, "row of 2 should align"
        crop, st = out
        assert st["align_crop"] == "4:3", f"chose {st['align_crop']}, want 4:3"
        got = crop.shape[1] / crop.shape[0]
        assert abs(got - 4 / 3) < 0.01, f"crop ratio {got:.3f}, want ~1.333"

        out = align_multi(img, dets, turn=1)
        assert out is not None
        crop, st = out
        assert st["align_crop"] == "3:4", f"turned: chose {st['align_crop']}, want 3:4"
        got = crop.shape[1] / crop.shape[0]
        assert abs(got - 3 / 4) < 0.01, f"turned crop ratio {got:.3f}, want ~0.75"
    finally:
        os.remove(p)


def test_window_count_tells_one_print_from_several():
    """count_windows counts the enclosed picture-holes in the paper blob: one
    per print. A single card measures 1; a row of two touching prints keeps two
    separate windows even though their borders merge into one blob."""
    p = _write(make_single())
    try:
        assert count_windows(p) == 1, "single card should enclose one window"
    finally:
        os.remove(p)
    p = _write(make_row(cols=2))
    try:
        assert count_windows(p) == 2, "row of two should enclose two windows"
    finally:
        os.remove(p)


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
    "023359428",   # the original sideways complaint (landscape stack)
    "041037832",   # 3x3-ish grid
    "023727013",   # four overlapping prints
    "023126095",   # two landscape prints stacked
    "153435918",   # three unevenly-laid prints: aspect 1.581 is card-like, so
                   # only fill/solidity reject it -- and the sheen-free box the
                   # glare rescue uses reads 0.996/0.994, which would launder it
]


def test_real_multiprint_photos_never_single():
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    checked = 0
    for name in REAL_NOT_SINGLE:
        path = _photo(folder, name)
        if path is None:
            continue
        checked += 1
        assert not _is_single(detect_print(path)), f"{name} misclassified as single"
    if checked == 0:
        skip("none of the named reference photos are present")


def test_real_grid_photo_fails_solidity():
    path = _photo(os.path.join(REPO, "chekis", "main"), "041037832")
    if path is None:
        skip("grid reference photo not present")
    d = detect_print(path)
    assert d.solidity < DEFAULTS.min_solidity, f"real grid solidity {d.solidity:.3f} no longer caught"


def test_real_angled_cards_fit_their_corners():
    """Two real cards shot at an angle. minAreaRect circumscribes a keystoned
    card, so it read 1.485 and 1.506 -- outside the accept band -- and as the
    crop source left warp's perspective transform nothing to correct. The
    four-corner fit recovers the true instax aspect and they classify as single.
    Synthetic keystone doesn't reproduce this (it biases the rect the other way),
    so the assertion lives on the real files."""
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    checked = 0
    for name in ["073304486", "073350228"]:
        path = _photo(folder, name)
        if path is None:
            continue
        checked += 1
        d = detect_print(path)
        assert d.cornered, f"{name}: four-corner fit rejected"
        assert d.rect_aspect < DEFAULTS.aspect_lo, (
            f"{name}: minAreaRect reads {d.rect_aspect:.3f}, no longer the case this guards")
        assert abs(d.aspect - ASPECT) < 0.02, (
            f"{name}: corner aspect {d.aspect:.3f}, want ~{ASPECT:.3f}")
        assert _is_single(d), f"{name}: should classify as single"
    if checked == 0:
        skip("neither angled reference photo is present")


def test_real_window_counts_split_near_misses_from_singles():
    """The --multi-windows threshold (7) sits between the busiest genuine
    single (6 window fragments) and the merged multi-print blobs (7-18). These
    are the anchor files on each side of that line."""
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    thresh = DEFAULTS.multi_windows
    checked = 0
    for name, side in [("023126095", "multi"),   # 6 prints, 10 windows
                       ("023727013", "multi"),   # 4 prints, 10 windows
                       ("023820588", "single"),  # busiest genuine single: 6
                       ("023252712", "single")]:
        path = _photo(folder, name)
        if path is None:
            continue
        checked += 1
        wins = count_windows(path)
        if side == "multi":
            assert wins >= thresh, f"{name}: {wins} windows, expected >= {thresh}"
        else:
            assert wins < thresh, f"{name}: {wins} windows, expected < {thresh}"
    if checked == 0:
        skip("none of the window-count reference photos are present")


def test_row_that_looks_like_a_card_is_caught_by_aspect_not_windows():
    """A tidy row of prints can pass the single-card SHAPE test outright -- one
    real 3-print row landed aspect 1.639, fill 0.994, solidity 0.992, all inside
    the single gate -- and would be warped into one card if shape were the only
    check. The window backstop must still catch it, which is why the count is
    run for single-gate passers too, not only near-misses."""
    path = _photo(os.path.join(REPO, "chekis", "main"), "012024586")
    if path is None:
        skip("row-shaped reference photo not present")
    d = detect_print(path)
    assert d.fill >= DEFAULTS.min_fill and d.solidity >= DEFAULTS.min_solidity, \
        "fixture no longer beats fill/solidity; it no longer tests anything"
    assert d.aspect > DEFAULTS.aspect_hi, \
        f"aspect {d.aspect:.3f} no longer excludes this row (hi {DEFAULTS.aspect_hi})"
    assert count_windows(path) < DEFAULTS.card_windows, \
        "the window count is supposed to be unable to catch this one"


def test_flush_grid_is_caught_only_by_its_windows():
    """Nine cards laid flush beat every shape test at once -- aspect ~1.6, fill
    1.0, solidity 1.0, a clean card's numbers on all three -- because n rows of n
    cards is exactly a card's shape and touching borders leave no seams. The
    window count is the only thing between this and being warped into one print,
    which is what --card-windows exists for. Assert both halves: that the shape
    really does pass, and that the count really does overrule it."""
    path = _write(make_flush_grid())
    try:
        det = detect_print(path)
        shape_ok, _ = single_fit(det, DEFAULTS)
        wins = count_windows(path)
        verdict = classify(det, DEFAULTS, wins)
    finally:
        os.unlink(path)
    assert shape_ok, (f"fixture no longer beats the shape gate (aspect {det.aspect:.3f}, "
                      f"fill {det.fill:.3f}, solidity {det.solidity:.3f})")
    assert wins >= DEFAULTS.card_windows, \
        f"{wins} windows, under --card-windows ({DEFAULTS.card_windows}): backstop can't fire"
    assert verdict != "single", "nine flush cards were warped into one print"


def test_window_backstop_is_stricter_for_a_confident_card_fit():
    """Two thresholds, because the two mistakes cost different things. Demoting
    a near-miss only refiles it; demoting a confident card fit stops a real
    print being cropped, which is what a shared threshold of 7 did to two
    genuine singles whose bright pictures left 7 specks rather than one window."""
    assert DEFAULTS.card_windows > DEFAULTS.multi_windows, \
        "overruling a confident fit must need more evidence than overruling a near-miss"

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "single.jpg")
        cv2.imwrite(path, cv2.cvtColor(make_single(), cv2.COLOR_RGB2BGR))
        det = detect_print(path)
        assert classify(det, DEFAULTS, DEFAULTS.card_windows - 1) == "single", \
            "a real card must survive a window count below the card threshold"
        assert classify(det, DEFAULTS, DEFAULTS.card_windows) == "multi", \
            "enough windows must still overrule even a confident fit"


# Photos whose tilt the ink in their borders used to decide. Each has every
# photo window scrawled across, so their fitted rectangles are ragged and any
# clean hole left is a loop of pen -- small, and square whatever the card under
# it is doing. All four read exactly 0.00 before the tilt was taken off the
# prints' own edges instead; the last is a pair overlapping at a steep angle,
# and is here so a coherence gate that swallowed real rotations would show up.
# Real photos whose single-card fit is only reachable once desk glare welded on
# by the segmentation close is cut off. See single_fit.
REAL_GLARE_RESCUE = ["145119616"]


REAL_TILT = {
    "154241942": -1.46,
    "023437053": 1.41,
    "041311208": 0.88,
    "073507152": -33.16,
}


# Multi-print photos that align_multi levels but leaves mis-turned, with the
# quarter/half turn (in 90-degree CCW units) that stands them upright...
REAL_REORIENT = {
    "023359428": 1,   # row of 2 portrait, a quarter turn off
    "015640226": 1,
    "015731072": 1,
    "023126095": 1,   # mixed landscape+portrait, all a quarter off
    "023727013": 2,   # row of 4 portrait, upside down
}
# ...and multi-print photos already upright, which must be left untouched.
REAL_UPRIGHT = [
    "023252712",
    "014211016",
    "022950306",      # a near-tie the margin rule must protect
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


def test_real_sheen_is_cut_off_the_blob():
    """A desk sheen welded onto a print by the segmentation close used to swell
    the blob -- and every crop drawn from it -- across a band of desk.
    _sheen_free_bbox tells the two apart by how each ends: a card's edge is
    crisp, a sheen's fades. Each of these blobs must lose a real slice, and a
    pile with no sheen must keep its box (that one is the guard against the test
    eating real cards)."""
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    # file -> smallest fraction of the blob's width/height the trim should remove
    sheened = {"130131692": 0.20,
               "142612680": 0.20}
    checked = 0
    for name, want in sheened.items():
        path = _photo(folder, name)
        if path is None:
            continue
        checked += 1
        seg = checleaner._segment_prints(path, 1100)
        idx = max(seg["big"], key=lambda i: seg["stats"][i, cv2.CC_STAT_AREA])
        ys, xs = np.where(seg["labels"] == idx)
        box = checleaner._sheen_free_bbox(seg, idx)
        assert box is not None, f"{name}: no sheen-free box"
        x0, x1, y0, y1 = box
        shrink = max(1 - (x1 - x0) / (xs.max() - xs.min()),
                     1 - (y1 - y0) / (ys.max() - ys.min()))
        assert shrink >= want, f"{name}: only trimmed {shrink:.0%}, want >= {want:.0%}"

    clean = _photo(folder, "041037832")
    if clean is not None:
        checked += 1
        seg = checleaner._segment_prints(clean, 1100)
        idx = max(seg["big"], key=lambda i: seg["stats"][i, cv2.CC_STAT_AREA])
        ys, xs = np.where(seg["labels"] == idx)
        box = checleaner._sheen_free_bbox(seg, idx)
        if box is not None:      # None is fine: the blob stands
            x0, x1, y0, y1 = box
            assert (x1 - x0) >= 0.9 * (xs.max() - xs.min()), "trimmed a clean pile's width"
            assert (y1 - y0) >= 0.9 * (ys.max() - ys.min()), "trimmed a clean pile's height"
    if checked == 0:
        skip("none of the sheen reference photos are present")


def test_real_aligned_crops_have_balanced_margins():
    """align_multi recentres on the true paper extent, so opposite desk margins
    come out roughly equal even when the detection blob overshoots the prints at
    one edge. These files each had a tight edge opposite a 33-69px one before the
    recentre; assert opposite desk margins now match within 20px.

    Both axes, because they fail differently: the vertical ones here were the
    blob overshooting the prints, while `012024586` is a row lying 36 px from
    the left edge of its frame and 330 from the right, where the failure was
    spending the whole of CROP_MARGIN on a side that had no desk to spare."""
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    if checleaner._face_detector() is None:
        skip("face model unavailable (turn affects the crop orientation)")
    import numpy as np
    checked = 0
    for name in ["041037832", "034550829", "012024586"]:
        path = _photo(folder, name)
        if path is None:
            continue
        img = cv2.imread(path)
        out = align_multi(img, detect_all_prints(path), turn=content_rotation(img))
        assert out is not None, f"{name} should align"
        crop = out[0]
        lab = cv2.cvtColor(cv2.GaussianBlur(crop, (7, 7), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
        hi = np.percentile(lab[:, :, 0], 99)
        paper = ((lab[:, :, 0] > 0.62 * hi)
                 & (np.hypot(lab[:, :, 1] - 128, lab[:, :, 2] - 128) < 16)).astype(np.uint8)
        paper = cv2.morphologyEx(paper, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
        H, W = paper.shape[:2]
        rows = np.where(paper.max(axis=1) > 0)[0]
        cols = np.where(paper.max(axis=0) > 0)[0]
        top, bottom = int(rows.min()), int(H - 1 - rows.max())
        left, right = int(cols.min()), int(W - 1 - cols.max())
        checked += 1
        assert abs(top - bottom) <= 20, f"{name}: top {top} vs bottom {bottom} margin"
        assert abs(left - right) <= 20, f"{name}: left {left} vs right {right} margin"
    if checked == 0:
        skip("none of the margin reference photos are present")


def test_glare_welded_to_a_card_is_cut_before_the_fit():
    """Desk glare bridged onto a card by the segmentation close pulls the fitted
    rectangle out over desk -- the shape, not the raggedness, is what breaks.
    The sheen-free reading of the same blob gets to stand in that case."""
    path = _write(make_single_with_welded_glare())
    try:
        det = detect_print(path)
        ok, fit = single_fit(det, DEFAULTS)
    finally:
        os.unlink(path)
    assert not (DEFAULTS.aspect_lo <= det.aspect <= DEFAULTS.aspect_hi), (
        f"fixture's glare no longer distorts the aspect ({det.aspect:.3f})")
    assert ok, f"glare-welded card not rescued (raw aspect {det.aspect:.3f})"
    assert fit is det.sheen_free, "should have been fitted on the trimmed blob"
    assert abs(fit.aspect - ASPECT) < 0.03, f"rescued aspect {fit.aspect:.3f}"


def test_a_ragged_blob_is_not_rescued_by_the_sheen_trim():
    """Only a distorted *shape* may be rescued. A blob whose aspect is already
    card-like and which failed on fill or solidity failed because its outline is
    ragged, and that is what a pile of prints looks like from outside -- letting
    a bounding box launder one would warp a real row into a single card."""
    path = _write(make_grid())
    try:
        det = detect_print(path)
        ok, _ = single_fit(det, DEFAULTS)
    finally:
        os.unlink(path)
    assert DEFAULTS.aspect_lo <= det.aspect <= DEFAULTS.aspect_hi, (
        f"fixture no longer tests the rule: aspect {det.aspect:.3f} is outside the band")
    assert not ok, "a grid of cards must not be rescued into a single card"


def test_writing_near_a_border_is_not_trimmed_as_desk():
    """Black marker is dark and picks up enough of the desk's warmth to pass
    trim_desk's desk test. A date written close to the top border used to drag
    the trim the whole 3.5% cap and cut the writing in half -- real desk is
    contiguous with the edge it came in from, ink in the border is not."""
    img = make_single()
    h, w = img.shape[:2]
    card_h = int(h * 0.62)
    card_w = int(card_h / ASPECT)
    y0, x0 = (h - card_h) // 2, (w - card_w) // 2
    # a stroke of dark, faintly desk-warm ink, one clean border's width in
    ink = np.array([DESK[0] * 0.55, DESK[1] * 0.45, DESK[2] * 0.40], np.float32)
    img = img.astype(np.float32)
    img[y0 + int(card_h * .028):y0 + int(card_h * .046),
        x0 + int(card_w * .15):x0 + int(card_w * .85)] = ink
    path = _write(np.clip(img, 0, 255).astype(np.uint8))
    try:
        det = detect_print(path)
        _, insets = trim_desk(cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8),
                                           cv2.COLOR_RGB2BGR), det.quad)
    finally:
        os.unlink(path)
    assert insets["top"] <= 8, f"trimmed {insets['top']}px into the border for ink"


def test_notes_are_recorded_without_sending_a_photo_to_review():
    """Some checks describe an output without condemning it. They stay in
    report.csv and in the console line; they must not move the file."""
    assert not _needs_review(["desk still on top edge (~57px)"])
    assert not _needs_review(["white reference 70% clipped"])
    assert not _needs_review([])
    assert _needs_review(["orientation uncertain (border ratio 1.20)"])
    assert _needs_review(["white reference 70% clipped",
                          "extreme correction (gain [1.9, 1.8, 1.7])"])


def test_staggered_prints_are_not_levelled_by_their_own_outline():
    """Level prints dealt corner to corner merge into one blob whose fitted
    rectangle follows the staircase, not any card in it. Turning the frame by
    that would tilt prints that were already straight; the outline's straight
    runs are all card borders and still say level."""
    img = make_staggered_pile()
    path = _write(img)
    try:
        dets = detect_all_prints(path)
        assert dets, "the pile should segment"
        tilt = checleaner._dominant_tilt(dets)
        worst = max(abs(checleaner._tilt_deg(d.quad)) for d in dets)
    finally:
        os.unlink(path)
    assert worst > 2.0, (
        f"fixture isn't staggered enough to be a test: blob rect reads {worst:.2f}")
    assert abs(tilt) < 0.5, f"level prints reported at {tilt:.2f} degrees"


def test_signed_row_is_levelled_from_its_edges():
    """The everyday case: a tilted row whose windows are all ragged with ink.
    The tilt still has to come out right."""
    img = make_signed_row(tilt=1.5)
    path = _write(img)
    try:
        tilt = checleaner._dominant_tilt(detect_all_prints(path))
    finally:
        os.unlink(path)
    # align_multi turns the frame *by* this, so correcting a +1.5 degree
    # rotation means reporting -1.5.
    assert abs(tilt + 1.5) < 0.4, f"tilt {tilt:.2f}, wanted about -1.5"


def test_coherence_gate_falls_back_rather_than_trusting_scattered_edges():
    """The edge angle is only used when the outline's straight runs agree on
    one direction. A frame of cards at four different angles has no such
    direction, and must not be levelled to whichever one happened to win."""
    img = make_grid(rot=25.0)
    path = _write(img)
    try:
        dets = detect_all_prints(path)
        dirs = [e for d in dets for e in d.edge_dirs]
        _, agree = checleaner._circular_tilt([a for a, _ in dirs],
                                             [L * L for _, L in dirs])
    finally:
        os.unlink(path)
    assert agree < checleaner.TILT_COHERENCE, (
        f"cards at scattered angles scored {agree:.3f} agreement")


def test_crop_margin_is_rationed_when_the_desk_is_one_sided():
    """CROP_MARGIN is breathing room, and growing the crop widens it on both
    sides at once. Where the desk is one-sided the whole margin only fits by
    sliding the crop, which puts all of it on one side -- so take the largest
    part of it that still sits centred on the prints."""
    img = make_signed_row(tilt=0.0, offset=-0.14)
    path = _write(img)
    try:
        out = align_multi(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), detect_all_prints(path))
    finally:
        os.unlink(path)
    assert out is not None, "a level row on plenty of desk should crop"
    crop = out[0]
    lab = cv2.cvtColor(cv2.GaussianBlur(crop, (7, 7), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    paper = ((lab[:, :, 0] > 0.62 * np.percentile(lab[:, :, 0], 99))
             & (np.hypot(lab[:, :, 1] - 128, lab[:, :, 2] - 128) < 16)).astype(np.uint8)
    paper = cv2.morphologyEx(paper, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    cols = np.where(paper.max(axis=0) > 0)[0]
    left, right = int(cols.min()), int(crop.shape[1] - 1 - cols.max())
    assert abs(left - right) <= 0.01 * crop.shape[1], (
        f"left margin {left} vs right {right} of {crop.shape[1]}")


def test_real_glare_welded_cards_still_crop():
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    checked = 0
    for stamp in REAL_GLARE_RESCUE:
        path = _photo(folder, stamp)
        if path is None:
            continue
        checked += 1
        det = detect_print(path)
        ok, fit = single_fit(det, DEFAULTS)
        assert ok, (f"{stamp}: not rescued (raw aspect {det.aspect:.3f}, "
                    f"fill {det.fill:.3f}, solidity {det.solidity:.3f})")
        assert fit is det.sheen_free, f"{stamp}: rescued but fitted on the raw blob"
        assert count_windows(path) < DEFAULTS.card_windows, (
            f"{stamp}: the window backstop would overrule this anyway")
    if checked == 0:
        skip("none of the glare reference photos are present")


def test_real_tilts_come_from_the_prints_not_the_ink():
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    checked = 0
    for name, want in REAL_TILT.items():
        path = _photo(folder, name)
        if path is None:
            continue
        got = checleaner._dominant_tilt(detect_all_prints(path))
        checked += 1
        assert abs(got - want) < 0.25, f"{name}: tilt {got:.2f}, wanted {want}"
    if checked == 0:
        skip("none of the tilt reference photos are present")


def test_real_multiprint_reorientation():
    folder = os.path.join(REPO, "chekis", "main")
    if not os.path.isdir(folder):
        skip("chekis/main not present (photos are gitignored)")
    if checleaner._face_detector() is None:
        skip("face model unavailable (offline / not cached)")
    checked = 0
    for name, want in REAL_REORIENT.items():
        path = _photo(folder, name)
        if path is None:
            continue
        checked += 1
        got = content_rotation(cv2.imread(path))
        assert got == want, f"{name}: reorient turned {got*90}, want {want*90}"
    for name in REAL_UPRIGHT:
        path = _photo(folder, name)
        if path is None:
            continue
        checked += 1
        got = content_rotation(cv2.imread(path))
        assert got == 0, f"{name}: already upright but reorient turned it {got*90}"
    if checked == 0:
        skip("none of the reorientation reference photos are present")


# ---------------------------------------------------- pass-1 measurement cache

def test_cached_measurement_round_trips_and_rejects_bad_rows():
    """_cached_measurement() is what lets an unchanged file skip pass 1's
    measure+solve, so it must parse a real row back out exactly, treat a
    missing desk *column* (an older report.csv) as unusable rather than
    guessing, and fall back to None -- not raise -- on anything malformed."""
    good = {"white_before": "[229.0, 229.0, 228.0]", "black_before": "[3.1, 2.8, 2.6]",
            "gain": "[1.234, 0.987, 1.056]", "clipped_pct": "0.0",
            "desk": "[0.0622, 0.0263, 0.0139]"}
    out = _cached_measurement(good)
    assert out is not None
    white_before, black_before, gain, clipped_pct, desk = out
    assert white_before == [229.0, 229.0, 228.0]
    assert np.allclose(gain, [1.234, 0.987, 1.056])
    assert clipped_pct == 0.0
    assert np.allclose(desk, [0.0622, 0.0263, 0.0139])

    no_desk = dict(good, desk="")
    _, _, _, _, desk = _cached_measurement(no_desk)
    assert desk is None, "an explicitly empty desk cell means 'no desk detected', not unusable"

    missing_column = {k: v for k, v in good.items() if k != "desk"}
    assert _cached_measurement(missing_column) is None, \
        "a report.csv from before the desk column existed must not be trusted"

    corrupt = dict(good, gain="not a list")
    assert _cached_measurement(corrupt) is None

    assert _cached_measurement(None) is None


def test_rerun_skips_measuring_unchanged_files():
    """The end-to-end behaviour this was built for: replace one input, delete
    its output, rerun -- only that one file should be measured, and the desk
    target computed from the mix of fresh + cached measurements must match a
    run that measured everything fresh."""
    with tempfile.TemporaryDirectory() as tmp:
        names = [f"single_{i}.jpg" for i in range(3)]
        for i, name in enumerate(names):
            cv2.imwrite(os.path.join(tmp, name), cv2.cvtColor(make_single(seed=i * 10), cv2.COLOR_RGB2BGR))

        args = build_parser().parse_args([tmp])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert run(args) == 0
        header = open(os.path.join(tmp, "report.csv")).readline()
        assert "desk" in header.split(","), f"report.csv header missing desk column: {header!r}"

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert run(args) == 0
        out = buf.getvalue()
        assert "measuring 0 of 3 images (3 unchanged, reusing prior measurements)" in out, out

        # wherever run() put it (balanced/ or review/ -- not the point of this test)
        made = [d for d in ("balanced", "review") if os.path.exists(os.path.join(tmp, d, names[0]))]
        assert made, f"{names[0]} landed in neither balanced/ nor review/"
        os.remove(os.path.join(tmp, made[0], names[0]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert run(args) == 0
        out = buf.getvalue()
        assert "measuring 1 of 3 images (2 unchanged, reusing prior measurements)" in out, out
        assert os.path.exists(os.path.join(tmp, made[0], names[0])), \
            "the deleted output should have been regenerated in the same place"

        # --force must ignore the cache regardless of what's on disk
        force_args = build_parser().parse_args([tmp, "--force"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert run(force_args) == 0
        assert "measuring 3 images" in buf.getvalue()


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
