#!/usr/bin/env python3
"""Merge several shots of the *same, unmoved* layout into one, keeping whichever
frame is in focus at each spot.

A phone shooting a deskful of prints picks one focus distance for the whole
frame, and the desk is not perpendicular to the lens, so a single shot is crisp
in a band and mushy outside it. Two shots seconds apart land that band in
different places: on `002232944` / `002255786` (thirteen prints, three rows) the
first is sharp on row A and B1-B4, the second on B5 and row C, and each has a
print the other renders 2.5x softer. Neither photo is good everywhere; between
them every print is good somewhere.

This is a *side tool*, deliberately not part of the pipeline. It runs before
checleaner, by hand, on a set of files you know are the same arrangement, and
writes one photo -- which then goes through a normal run as an ordinary input.
Nothing about the colour maths changes: the merge is geometry and picking, and
what it emits is just a better-focused photograph of the same desk.

    python3 tools/focusmerge.py <shot1>.jpg <shot2>.jpg -o merged.jpg
    python3 tools/focusmerge.py <shot*>.jpg --check                 # report only

The first file is the reference: the output has its framing, its dimensions and
its EXIF, and the others are warped onto it. Per frame it reports how well the
alignment went and how much of the result came from it, and it refuses to merge
a frame it could not line up rather than blending a mess. It also checks whether
anything on the desk *moved* between shots, which is the one way this can
quietly produce a mangled photo -- see `_moved_tiles`.
"""
import os
import sys
import argparse
from dataclasses import dataclass, field

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from checleaner import to_linear, to_srgb, _copy_exif


# ------------------------------------------------------------------ constants

SIFT_FEATURES = 8000
MATCH_RATIO = 0.75          # Lowe's ratio; 2530 of 8000 survive it on the real pair
RANSAC_PX = 3.0
# Below this many inliers the homography is a guess, not a measurement. The real
# pair reaches 1996; a genuinely different layout should not come close.
MIN_INLIERS = 60

# The homography is the right model for prints on a flat desk, and still leaves
# a smooth ~1.4 px residual the projective form cannot absorb (lens distortion,
# mostly: the two shots were framed at slightly different distances). At 1 px the
# blend softens what it touches, which is the exact thing being fixed -- so the
# residual gets measured on a tile grid and warped out.
REFINE_TILES = 10
REFINE_RESP = 0.35          # phase-correlation response below this = no answer
REFINE_MIN_STD = 3.0        # flat desk has nothing to correlate; skip those tiles
SHIFT_MAX = 60.0            # px; past this the correlation peak is not a shift at all

# How far a tile may sit off the smooth field before it is called *moved* rather
# than distorted. On the real pair the field's own scatter -- phase correlation
# on defocused tiles -- tops out at 1.2 px, while a print someone nudged moves by
# tens. The gap is wide, so this sits in the middle. A false alarm here costs a
# look at the photo, not a bad merge; a missed one costs a ghost nobody sees.
MOVE_TOL = 3.0

# Blur applied before the exposure ratio is fitted, in px. Big enough to sit well
# past any plausible defocus, so the fit sees tone and not focus.
GAIN_BLUR = 8.0

# Sharpness and blending.
SHARP_WIN = 41              # px; a print's picture window is ~500, so this is local
BLEND_SIGMA = 25.0          # blur on the decision, not on the image: no seam can
                            # then land on a card edge
BLEND_SHARPNESS = 12.0      # how decisively the better frame wins a tie


@dataclass
class FrameReport:
    """What happened to one input frame. Printed per file, and asserted on."""
    name: str
    reference: bool = False
    matches: int = 0
    inliers: int = 0
    reproj: float = 0.0        # median px, after the homography
    residual: float = 0.0      # max px the local refinement had to move
    gains: tuple = (1.0, 1.0, 1.0)
    share: float = 0.0         # fraction of the output that came from this frame
    moved: list = field(default_factory=list)   # (x, y, w, h, px) of moved content
    failed: str = ""           # non-empty means the frame was left out


# -------------------------------------------------------------------- sharpness

def sharpness(lin_bgr: np.ndarray, win: int = SHARP_WIN) -> np.ndarray:
    """Local fine-detail energy: how much of the picture survives at pixel scale.

    On the *log* of luminance, so it measures contrast relative to the local
    tone rather than absolute. Two shots of one desk differ slightly in exposure,
    and without the log the brighter frame wins everywhere on brightness alone --
    which is not what "in focus" means.
    """
    g = np.log(np.maximum(cv2.cvtColor(lin_bgr, cv2.COLOR_BGR2GRAY), 1e-4))
    lap = cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), 1.0), cv2.CV_32F, ksize=3)
    return cv2.boxFilter(lap * lap, -1, (win, win))


# ------------------------------------------------------------------- alignment

def _homography(ref_gray: np.ndarray, gray: np.ndarray):
    """SIFT + RANSAC. A homography is the exact model here -- the prints all lie
    on one plane -- so this is a fit, not an approximation, and its inlier count
    doubles as the "is this the same layout at all?" test."""
    sift = cv2.SIFT_create(nfeatures=SIFT_FEATURES)
    kr, dr = sift.detectAndCompute(ref_gray, None)
    k, d = sift.detectAndCompute(gray, None)
    if dr is None or d is None or len(k) < 2 or len(kr) < 2:
        return None, 0, 0, 0.0
    pairs = cv2.BFMatcher().knnMatch(d, dr, k=2)
    good = [m for m, n in pairs if m.distance < MATCH_RATIO * n.distance]
    if len(good) < 4:
        return None, len(good), 0, 0.0
    src = np.float32([k[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kr[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_PX)
    if H is None:
        return None, len(good), 0, 0.0
    inl = mask.ravel().astype(bool)
    res = np.linalg.norm(cv2.perspectiveTransform(src, H) - dst, axis=2).ravel()[inl]
    return H, len(good), int(inl.sum()), float(np.median(res)) if inl.any() else 0.0


def _tile_shifts(ref_gray: np.ndarray, gray: np.ndarray, tiles: int,
                 valid: np.ndarray = None):
    """Phase-correlate a grid of tiles: how far this frame's content sits from
    the reference's, tile by tile, after the homography.

    Tiles with nothing to correlate (flat desk), peaks too weak to believe, and
    tiles the other frame does not fully cover are left out entirely -- an answer
    of 0 and no answer at all are different things, and averaging the second into
    the field would drag it toward zero. The coverage test matters more than it
    sounds: a tile hanging off the edge of the other shot correlates its content
    against blank, which is not a small error but an arbitrary one.
    """
    h, w = ref_gray.shape
    th, tw = h // tiles, w // tiles
    d = np.zeros((tiles, tiles, 2), np.float32)
    ok = np.zeros((tiles, tiles), bool)
    win = cv2.createHanningWindow((tw, th), cv2.CV_32F)
    for i in range(tiles):
        for j in range(tiles):
            sl = (slice(i * th, i * th + th), slice(j * tw, j * tw + tw))
            a = ref_gray[sl]
            b = gray[sl]
            if a.std() < REFINE_MIN_STD or (valid is not None and not valid[sl].all()):
                continue
            (dx, dy), resp = cv2.phaseCorrelate(a, b, win)
            if resp < REFINE_RESP or max(abs(dx), abs(dy)) > SHIFT_MAX:
                continue
            d[i, j], ok[i, j] = (dx, dy), True
    return d, ok, (th, tw)


def _smooth_field(d: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """The tile shifts as a slowly-varying field: grow the measured tiles into
    the unmeasured ones, then smooth. What is being modelled is an optical
    property of the lens, which varies slowly across the frame, so per-tile
    scatter is noise and smoothing it away is not a compromise."""
    out = d.copy()
    for c in range(2):
        arr = out[:, :, c]
        for _ in range(4):
            num = cv2.blur(arr * ok, (3, 3))
            den = np.maximum(cv2.blur(ok.astype(np.float32), (3, 3)), 1e-6)
            arr[~ok] = (num / den)[~ok]
        out[:, :, c] = cv2.GaussianBlur(arr, (0, 0), 0.9)
    return out


def _moved_tiles(d: np.ndarray, ok: np.ndarray, tol: float = MOVE_TOL):
    """Tiles whose shift does not belong to the smooth field the others describe.

    This tool's one silent failure is a print that was nudged between shots: the
    alignment is global, so a moved print lands in two places at once and blends
    into a ghost, with a perfectly ordinary-looking report. Disagreement alone
    can't catch it -- the frames are *supposed* to disagree, that being the focus
    difference this exists to exploit. But a moved print disagrees in a way the
    optics cannot: it sits off the smooth residual field that every other tile
    shares, and by tens of pixels rather than the field's own 1.2.

    The model is a *cubic* surface in x and y, refit twice without its outliers
    so one moved print can't bend it toward itself and hide. Cubic because the
    dominant cause is radial distortion, whose displacement goes as k*r^2 times
    the radius -- third order, not second. On the real pair it earns the extra
    terms: fitting the 84 measured tiles leaves 1.89 px at first order, 1.58 at
    second and 1.22 at third, so `MOVE_TOL` clears the honest scatter by 2.5x.
    """
    tiles = d.shape[0]
    off = np.zeros((tiles, tiles), np.float32)
    gy, gx = np.mgrid[0:tiles, 0:tiles].astype(np.float32) / max(tiles - 1, 1) - 0.5
    A = np.stack([(gx ** (p - q)) * (gy ** q)
                  for p in range(4) for q in range(p + 1)], -1)[ok]
    v = d[ok]
    if A.shape[0] < 2 * A.shape[1]:
        return ok.copy(), off      # too few tiles to model: nothing is vouched for
    keep = np.ones(A.shape[0], bool)
    for _ in range(3):
        c, *_ = np.linalg.lstsq(A[keep], v[keep], rcond=None)
        r = np.linalg.norm(v - A @ c, axis=1)
        if (r <= tol).sum() < 2 * A.shape[1]:
            # No cubic describes even a majority of the tiles. Say so by
            # flagging everything rather than reporting a clean frame -- the one
            # thing this check must never do is stay quiet about not knowing.
            off[ok] = r
            return ok.copy(), off
        keep = r <= tol
    off[ok] = r
    return ok & (off > tol), off


def refine_field(ref_gray: np.ndarray, gray: np.ndarray, tiles: int = REFINE_TILES,
                 valid: np.ndarray = None):
    """The sub-pixel residual the homography leaves, as a dense remap field,
    plus the tiles that don't belong to it. Returns (field, max px, moved).

    Skipping the refinement is not an option that merely costs accuracy: the tie
    band between two focus zones is exactly where both frames contribute, and
    blending two frames a pixel apart there gave back 12% of B4's sharpness in
    testing. With it, the worst print keeps 96.9%.

    A moved print is *excluded* from the field rather than corrected by it. The
    correction is a rubber sheet: bending it to follow one print would drag that
    print's neighbours off alignment to chase something that genuinely isn't
    there any more, turning one bad region into several.
    """
    h, w = ref_gray.shape
    d, ok, (th, tw) = _tile_shifts(ref_gray, gray, tiles, valid)
    if not ok.any():
        return None, 0.0, []
    moved, off = _moved_tiles(d, ok)
    field = _smooth_field(d, ok & ~moved)
    fx = cv2.resize(field[:, :, 0], (w, h), interpolation=cv2.INTER_CUBIC)
    fy = cv2.resize(field[:, :, 1], (w, h), interpolation=cv2.INTER_CUBIC)
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32),
                         np.arange(h, dtype=np.float32))
    regions = [(int(j * tw), int(i * th), tw, th, float(off[i, j]))
               for i, j in zip(*np.where(moved))]
    return (gx + fx, gy + fy), float(np.hypot(field[..., 0], field[..., 1]).max()), regions


def align(ref_bgr: np.ndarray, img_bgr: np.ndarray, name: str = "",
          refine: bool = True):
    """Put one frame into the reference's pixel grid, in linear light.

    Returns (linear BGR, valid mask, FrameReport). `linear` is gain-matched to
    the reference per channel so the join can't show as a tone step; the match is
    done in linear light like every other colour operation here, and over the
    overlap only, excluding crushed and clipped pixels which carry no ratio.
    """
    rep = FrameReport(name=name)
    h, w = ref_bgr.shape[:2]
    ref_gray = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    H, matches, inliers, reproj = _homography(ref_gray, cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY))
    rep.matches, rep.inliers, rep.reproj = matches, inliers, reproj
    if H is None or inliers < MIN_INLIERS:
        rep.failed = (f"only {inliers} inliers from {matches} matches "
                      f"(need {MIN_INLIERS}) -- is this the same layout?")
        return None, None, rep

    warped = cv2.warpPerspective(img_bgr, H, (w, h), flags=cv2.INTER_LANCZOS4)
    valid = cv2.warpPerspective(np.ones(img_bgr.shape[:2], np.uint8), H, (w, h)) > 0
    field, rep.residual, rep.moved = refine_field(
        ref_gray.astype(np.float32),
        cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY).astype(np.float32), valid=valid)
    # The movement check is measured either way: --no-refine turns off the
    # correction, not the warning.
    if refine and field is not None:
        warped = cv2.remap(warped, field[0], field[1], cv2.INTER_LANCZOS4)
        valid = cv2.remap(valid.astype(np.uint8), field[0], field[1],
                          cv2.INTER_NEAREST) > 0
    elif not refine:
        rep.residual = 0.0

    lin = to_linear(warped)
    ref_lin = to_linear(ref_bgr)
    # A pixel crushed or clipped in *either* frame carries no ratio: one the
    # brighter frame clipped but the reference didn't reads as "this frame is
    # darker here" when it is only flat. Worth 3 points of gain back when the fit
    # ran on the pixels; with the low-pass below it measures as nothing, on a
    # fixture whose middle 36% is deliberately blown. Kept because it is correct
    # and free, not because it is currently doing work.
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    usable = (valid & (ref_gray > 8) & (ref_gray < 248)
              & (warped_gray > 8) & (warped_gray < 248))
    # Fit the ratio on low-passed copies. Straight least squares on the pixels
    # is biased by exactly the thing this tool exists for: where the reference is
    # sharp and this frame is soft the ratio reads high, where it is the other way
    # round it reads low, and the two don't cancel -- the sharp frame carries all
    # the high-frequency energy the sum is weighted by. On a fixture built with a
    # known 1.06 stop between the frames that came out as 0.904 instead of 0.943.
    # Past the defocus scale both frames carry the same picture, so blurring first
    # leaves only the tone difference the gain is meant to describe.
    a_lp = cv2.GaussianBlur(ref_lin, (0, 0), GAIN_BLUR)
    b_lp = cv2.GaussianBlur(lin, (0, 0), GAIN_BLUR)
    gains = []
    for c in range(3):
        a, b = a_lp[:, :, c][usable], b_lp[:, :, c][usable]
        g = float((a * b).sum() / max((b * b).sum(), 1e-9))
        lin[:, :, c] *= g
        gains.append(g)
    rep.gains = tuple(gains)
    return lin, valid, rep


# ---------------------------------------------------------------------- merge

def blend_weights(lins: list, valids: list) -> np.ndarray:
    """How much of each aligned frame every pixel takes: a softmax over sharpness,
    computed on a *blurred* copy of that sharpness.

    Blurring the decision and not the image is what keeps a seam off a card edge.
    It is not free, and the trade is worth stating: on the real pair a hard
    per-pixel pick actually measures slightly *sharper* (worst print 97.7% of the
    best frame against 96.3%), because the tie band gets one frame outright
    instead of a mixture. What it also gets is a patchwork -- 2.4% of pixels
    change by more than 4/255, in blobs following pixel-scale noise in the
    sharpness measure rather than anything about the photograph. Sharpness is not
    the only thing being preserved here: which frame a pixel comes from should be
    a property of the region, not of grain, or two frames' noise and whatever
    sub-pixel misalignment remains get interleaved at pixel scale.
    """
    V = np.stack(valids)
    S = np.stack([sharpness(l) for l in lins])
    S[~V] = 0
    L = np.stack([cv2.GaussianBlur(np.log(s + 1e-6), (0, 0), BLEND_SIGMA) for s in S])
    W = np.exp((L - L.max(0)) * BLEND_SHARPNESS)
    W[~V] = 0
    W /= np.maximum(W.sum(0), 1e-9)
    # Nothing valid anywhere but the reference: fall back to it rather than
    # emitting black, which no caller would notice until they looked.
    W[0][W.sum(0) < 1e-6] = 1.0
    return W


def merge(frames: list, names: list = None, refine: bool = True):
    """Focus-stack aligned frames onto the first. Returns (uint8 BGR, reports).

    A frame that could not be lined up is reported and left out rather than
    blended in; see `blend_weights` for how the rest are weighed against each
    other.
    """
    names = names or [f"frame {i}" for i in range(len(frames))]
    ref = frames[0]
    lins = [to_linear(ref)]
    valids = [np.ones(ref.shape[:2], bool)]
    reports = [FrameReport(name=names[0], reference=True)]
    for img, name in zip(frames[1:], names[1:]):
        lin, valid, rep = align(ref, img, name, refine=refine)
        reports.append(rep)
        if rep.failed:
            continue
        lins.append(lin)
        valids.append(valid)

    used = [r for r in reports if not r.failed]
    W = blend_weights(lins, valids)
    for r, wt in zip(used, W):
        r.share = float(wt.mean())
    out = sum(W[i][:, :, None] * lins[i] for i in range(len(lins)))
    return to_srgb(out).round().astype(np.uint8), reports


# ------------------------------------------------------------------------ CLI

def describe(rep: FrameReport) -> str:
    if rep.reference:
        return f"{rep.name:<34} reference"
    if rep.failed:
        return f"{rep.name:<34} SKIPPED: {rep.failed}"
    moved = ""
    if rep.moved:
        worst = max(r[4] for r in rep.moved)
        moved = f"  MOVED: {len(rep.moved)} regions, up to {worst:.1f} px"
    return (f"{rep.name:<34} {rep.inliers}/{rep.matches} inliers  "
            f"reproj={rep.reproj:.2f}px  refined={rep.residual:.2f}px  "
            f"gain=({rep.gains[0]:.3f},{rep.gains[1]:.3f},{rep.gains[2]:.3f})  "
            f"share={rep.share:.0%}{moved}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="shots of the same layout; the first is the reference")
    ap.add_argument("-o", "--out", help="output file (required unless --check)")
    ap.add_argument("--check", action="store_true",
                    help="align and report, write nothing")
    ap.add_argument("--quality", type=int, default=96, help="JPEG quality")
    ap.add_argument("--no-refine", action="store_true",
                    help="skip the local residual correction (diagnostic: on the "
                         "reference pair it takes the worst print from 88%% of the "
                         "best single frame to 97%%)")
    args = ap.parse_args()

    if len(args.files) < 2:
        print("need at least two shots to merge", file=sys.stderr)
        return 2
    if not args.out and not args.check:
        print("give -o OUT, or --check to report without writing", file=sys.stderr)
        return 2

    frames, names = [], []
    for path in args.files:
        img = cv2.imread(path)
        if img is None:
            print(f"can't read {path}", file=sys.stderr)
            return 1
        frames.append(img)
        names.append(os.path.basename(path))

    out, reports = merge(frames, names, refine=not args.no_refine)
    for rep in reports:
        print(describe(rep))

    sys.stdout.flush()
    if any(r.moved for r in reports):
        print("\nSomething on the desk moved between shots. The merge blends both "
              "positions there, so those regions will ghost -- reshoot, or drop "
              "the offending frame.", file=sys.stderr)
    skipped = [r for r in reports if r.failed]
    if len(skipped) == len(reports) - 1:
        print("\nNothing lined up with the reference; there is nothing to merge.",
              file=sys.stderr)
        return 1

    if args.check:
        print(f"\n--check: {out.shape[1]}x{out.shape[0]} merge not written")
        return 0

    cv2.imwrite(args.out, out, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
    _copy_exif(args.files[0], args.out, out.shape[1], out.shape[0])
    print(f"\n-> {args.out}  ({out.shape[1]}x{out.shape[0]}, "
          f"EXIF from {names[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
