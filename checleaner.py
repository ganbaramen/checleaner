#!/usr/bin/env python3
"""
checleaner - batch colour-balance and crop photos of instax mini prints.

Point it at a folder of phone photos of cheki (instax mini) fronts lying on a
desk. For every photo it:

  1. measures the print's white border and the photo's black point,
  2. solves a per-channel curve in linear light so both land on fixed targets,
     making whites and blacks consistent across the whole folder,
  3. nudges the desk toward a common tone (secondary, deliberately damped),
  4. if the photo shows exactly one print, deskews and crops it to true instax
     mini proportions (54 x 86 mm) and rotates it upright,
  5. routes anything it isn't confident about into review/ with a reason.

Photos showing several prints are balanced, levelled, and stood upright from
their content (faces), but left uncropped.

Usage:
    python3 checleaner.py PHOTOS/                 # -> PHOTOS/balanced, PHOTOS/review
    python3 checleaner.py PHOTOS/ -o OUT/         # choose the output root
    python3 checleaner.py PHOTOS/ --no-crop       # colour only, never crop
    python3 checleaner.py PHOTOS/ --dry-run       # measure and report, write nothing

The defaults (white 238.8, black 2.2) are calibrated so separate runs on
separate folders come out matching each other.

Requires: numpy, opencv-python, pillow, scipy, piexif
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import textwrap
from dataclasses import dataclass, field

import numpy as np

try:
    import cv2
    from PIL import Image
    from scipy.ndimage import uniform_filter
except ImportError as exc:  # pragma: no cover
    sys.exit(f"missing dependency: {exc}\n"
             "install with: pip install numpy opencv-python pillow scipy piexif")

try:
    import piexif
except ImportError:
    piexif = None

# instax mini card: 54 x 86 mm
ASPECT = 86.0 / 54.0
EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


# ---------------------------------------------------------------- colour space

def to_linear(srgb8):
    """sRGB 0-255 -> linear 0-1. All balancing happens in linear light; doing it
    in gamma space skews the midtones."""
    x = np.asarray(srgb8, dtype=np.float32) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def to_srgb(lin):
    x = np.clip(lin, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055) * 255.0


def soft_shoulder(x, knee=0.90):
    """Roll highlights off above `knee` instead of clipping them flat. Without
    this, brightening a print's border turns its paper texture into a white slab."""
    out = x.copy()
    hot = x > knee
    out[hot] = knee + (1 - knee) * np.tanh((x[hot] - knee) / (1 - knee))
    return out


# ------------------------------------------------------------------ measuring

@dataclass
class Measurement:
    white: np.ndarray          # linear RGB of the print's white border
    black: np.ndarray          # linear RGB of the darkest content
    desk: np.ndarray | None    # linear RGB of the desk, None if barely visible
    white_clipped: float       # fraction of border pixels at/over 250
    desk_px: int


def measure(rgb: np.ndarray, min_desk_px: int = 40_000) -> Measurement:
    """Find the three anchors in a downscaled frame.

    White comes from the *smooth* bright pixels, not simply the brightest: a
    variance filter separates flat paper border from bright busy content like a
    white blouse. Clipped pixels are excluded so a blown highlight can't drag
    the estimate down.
    """
    lum = rgb.mean(axis=2)
    mean = uniform_filter(lum, 9)
    var = np.maximum(uniform_filter(lum * lum, 9) - mean * mean, 0)
    sd = np.sqrt(var)

    bright = lum > np.percentile(lum, 80)
    smooth = sd < np.percentile(sd, 25)
    unclipped = rgb.max(axis=2) < 250

    white_mask = bright & smooth & unclipped
    if white_mask.sum() < 800:                      # tiny border: relax smoothness
        white_mask = bright & unclipped
    clipped = float((~unclipped)[bright].mean()) if bright.any() else 0.0

    # <=, not <: a photo with a large near-black region (a dark print background,
    # say) can pile enough pixels onto the true minimum that it *is* the 0.5th
    # percentile, and a strict less-than then matches nothing -- an empty mask
    # means a NaN black point, silently poisoning the whole correction.
    black_mask = lum <= np.percentile(lum, 0.5)
    if not black_mask.any():
        black_mask = lum <= lum.min()

    # desk: warm, mid-dark, low-texture. Skin and warm clothing inside a print
    # can leak in, which is why the desk correction stays damped.
    desk_mask = ((rgb[:, :, 0] > rgb[:, :, 2] + 12) & (lum > 25) & (lum < 190)
                 & (sd < np.percentile(sd, 45)))

    lin = to_linear(rgb)
    desk = np.median(lin[desk_mask], axis=0) if desk_mask.sum() >= min_desk_px else None
    return Measurement(
        white=np.median(lin[white_mask], axis=0),
        black=lin[black_mask].mean(axis=0),
        desk=desk,
        white_clipped=clipped,
        desk_px=int(desk_mask.sum()),
    )


def solve_levels(rgb: np.ndarray, m: Measurement, white_t, black_t, iters=6):
    """Per-channel gain+offset in linear light mapping white->white_t, black->black_t.

    Applying the transform moves the pixels the anchors were measured from, so a
    couple of re-measure passes are needed to actually land on target.
    """
    W, B = white_t.copy(), black_t.copy()
    gain = off = None
    for _ in range(iters):
        gain = (W - B) / (m.white - m.black)
        off = B - gain * m.black
        corrected = to_srgb(soft_shoulder(np.clip(to_linear(rgb) * gain + off, 0, None)))
        got = measure(corrected)
        err_w, err_b = white_t / got.white, black_t - got.black
        if np.max(np.abs(err_w - 1)) < 0.004 and np.max(np.abs(err_b)) < 0.0004:
            break
        W = W * err_w
        B = B + err_b
    return gain, off


def desk_gamma(desk_lin, target_u, white_t, black_t, strength, clamp=(0.86, 1.16)):
    """Per-channel power curve pulling the desk toward the folder's median tone.

    Uses a gamma rather than a second gain because gamma fixes both endpoints:
    the white and black we just set stay exactly where they are. Damped by
    `strength` and clamped, because the desk matters less than the prints and a
    hard match would drag skin tones with it.
    """
    u = np.clip((desk_lin - black_t) / (white_t - black_t), 1e-4, 0.999)
    return np.clip(1 + (np.log(target_u) / np.log(u) - 1) * strength, *clamp)


def apply(rgb8: np.ndarray, gain, off, gamma, white_t, black_t) -> np.ndarray:
    lin = to_linear(rgb8)
    u = np.clip((lin * gain + off - black_t) / (white_t - black_t), 0, None)
    if gamma is not None and not np.allclose(gamma, 1):
        u = np.power(u, gamma)
    return to_srgb(soft_shoulder(np.clip(black_t + u * (white_t - black_t), 0, None))
                   ).round().astype(np.uint8)


# ------------------------------------------------------------------- geometry

@dataclass
class Detection:
    quad: np.ndarray | None = None   # 4x2 in full-res coords, long edge first
    aspect: float = 0.0
    fill: float = 0.0                # how rectangular the detected blob is
    solidity: float = 1.0            # raw contour area / hull area -- see _blob_detection
    area: float = 0.0                # full-res px^2, for weighting multi-blob results
    n_blobs: int = 0
    ok: bool = False
    reason: str = ""


def _segment_prints(path: str, size: int = 1100):
    """Paper-frame segmentation shared by detect_print and detect_all_prints:
    bright *and* near-neutral, which desk never is. See docs/PIPELINE.md § 3
    for why this beats segmenting "everything that isn't desk". Returns None
    if the file can't be read.
    """
    img = cv2.imread(path)
    if img is None:
        return None
    h, w = img.shape[:2]
    sc = size / max(h, w)
    small = cv2.resize(img, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(cv2.GaussianBlur(small, (7, 7), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    H, W = L.shape

    hi = np.percentile(L, 99)
    chroma = np.hypot(A - 128, B - 128)
    mask = ((L > 0.62 * hi) & (chroma < 16)).astype(np.uint8) * 255
    # close wide enough to bridge the photo window, then open to shed highlights
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((43, 43), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((17, 17), np.uint8))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    big = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 0.03 * H * W]
    return dict(labels=labels, stats=stats, big=big, sc=sc)


def _blob_detection(labels: np.ndarray, idx: int, sc: float) -> Detection | None:
    """minAreaRect + fill for one connected component, scaled to full-res coords."""
    comp = (labels == idx).astype(np.uint8)
    contour = max(cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0],
                  key=cv2.contourArea)
    hull = cv2.convexHull(contour)
    rect = cv2.minAreaRect(hull)
    (rw, rh) = rect[1]
    if min(rw, rh) < 1:
        return None

    box = cv2.boxPoints(rect)
    edges = [np.linalg.norm(box[(i + 1) % 4] - box[i]) for i in range(4)]
    if (edges[0] + edges[2]) < (edges[1] + edges[3]):
        box = np.roll(box, -1, axis=0)               # long edge first
    edges = [np.linalg.norm(box[(i + 1) % 4] - box[i]) for i in range(4)]

    return Detection(
        quad=box / sc,
        aspect=(edges[0] + edges[2]) / (edges[1] + edges[3]),
        # fill measured on the hull, so a frame with an unfilled middle still scores ~1
        fill=cv2.contourArea(hull) / (rw * rh),
        # raw contour vs. hull: a tight grid of several cards can fill a rect
        # almost as well as one real card (high `fill`), but the seams between
        # cards leave notches in the raw mask that only the hull smooths over.
        # A real card's border has no seams, so its raw contour already *is*
        # its hull -- solidity lands at 1.0, not just close to it.
        solidity=cv2.contourArea(contour) / cv2.contourArea(hull),
        area=(rw * rh) / (sc * sc),
    )


def detect_print(path: str, size: int = 1100) -> Detection:
    """Find a single print by its white paper frame: bright *and* near-neutral.

    Ported from checleaner.html, which finds this more reliably than the
    "everything that isn't desk" approach tried first: a print's dark photo
    area is often as dark and as warm as walnut, so that mask comes out as a
    hollow frame and any bright patch of desk merges into it. Bright-and-
    neutral is the more distinctive feature -- desk is never both. On the
    same 11 photos this landed aspects at 1.568-1.611 against the old
    method's 1.54-1.62; see docs/PIPELINE.md.
    """
    seg = _segment_prints(path, size)
    if seg is None:
        return Detection(reason="unreadable")
    big = seg["big"]
    if not big:
        return Detection(n_blobs=0, reason="no print found")

    idx = max(big, key=lambda i: seg["stats"][i, cv2.CC_STAT_AREA])
    d = _blob_detection(seg["labels"], idx, seg["sc"])
    if d is None:
        return Detection(n_blobs=len(big), reason="degenerate fit")
    d.n_blobs = len(big)
    return d


def detect_all_prints(path: str, size: int = 1100) -> list[Detection]:
    """Every print-sized blob in the photo, not just the largest.

    Used to align a multi-print photo (see align_multi), where every print
    that segmented cleanly should count, not just the biggest one.
    """
    seg = _segment_prints(path, size)
    if seg is None:
        return []
    dets = (_blob_detection(seg["labels"], idx, seg["sc"]) for idx in seg["big"])
    return [d for d in dets if d is not None]


def count_windows(path: str, size: int = 1400) -> int | None:
    """How many photo windows the largest paper blob encloses.

    Disambiguates a near-miss: prints that overlap merge into one blob whose
    shape statistics can beat a genuine card's (white border on white border
    leaves no seam for fill or solidity to catch), but each print's *picture*
    stays dark and separate -- a hole in the paper mask. One card has one
    window, fragmented at most into a few pieces where bright content (a white
    blouse, a pale wall) bridges it to the border; across the whole library the
    worst genuine single measured 6 fragments, while merged multi-print blobs
    run 7-18. So a high count is proof of several prints, while a low count
    proves nothing -- which is why the caller treats only the high side as
    evidence.

    The flood fill seeds from a padded border, not the bbox corner: the corner
    of a tilted blob's bbox can be *inside* the blob, and seeding there marks
    the wrong region as exterior (cost a real debugging session in the
    abandoned split_prints work this is salvaged from).
    """
    seg = _segment_prints(path, size)
    if seg is None or not seg["big"]:
        return None
    idx = max(seg["big"], key=lambda i: seg["stats"][i, cv2.CC_STAT_AREA])
    comp = (seg["labels"] == idx).astype(np.uint8)
    ys, xs = np.where(comp)
    sub = comp[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    notpaper = np.pad((1 - sub).astype(np.uint8), 1, constant_values=1)
    ffmask = np.zeros((notpaper.shape[0] + 2, notpaper.shape[1] + 2), np.uint8)
    filled = notpaper.copy()
    cv2.floodFill(filled, ffmask, (0, 0), 2)
    holes = (((notpaper == 1) & (filled != 2))[1:-1, 1:-1]).astype(np.uint8) * 255
    n, _, stats, _ = cv2.connectedComponentsWithStats(holes, 8)
    return sum(1 for i in range(1, n)
               if stats[i, 4] > 0.005 * sub.shape[0] * sub.shape[1])


def _tilt_deg(quad: np.ndarray) -> float:
    """A blob's tilt from axis-aligned, folded into [-45, 45).

    A rectangle looks the same every 90 degrees, so its long edge's raw angle
    isn't the right thing to average across blobs -- two prints tilted +44 and
    -44 degrees are actually within 2 degrees of each other, not 88.
    """
    v = quad[1] - quad[0]
    deg = float(np.degrees(np.arctan2(v[1], v[0]))) % 90
    return deg - 90 if deg >= 45 else deg


def _dominant_tilt(dets: list[Detection]) -> float:
    """Area-weighted circular mean of blob tilts, mod 90.

    Area weighting means a couple of small false-positive blobs can't outvote
    the actual prints. Circular averaging (via the angle-quadrupling trick,
    since tilt has period 90 not 360) matters for the same wraparound reason
    as _tilt_deg: a plain mean of +44 and -44 would land on 0, not on the true
    answer of (roughly) +45 or -45.
    """
    tilts = np.radians([_tilt_deg(d.quad) for d in dets])
    weights = np.array([d.area for d in dets])
    theta4 = tilts * 4
    mean4 = np.arctan2(np.average(np.sin(theta4), weights=weights),
                        np.average(np.cos(theta4), weights=weights))
    deg = np.degrees(mean4) / 4 % 90
    return float(deg - 90 if deg >= 45 else deg)


# Preferred crop shapes for multi-print photos, tried in addition to the
# frame's own ratio. Order doesn't matter (best fit wins); add new shapes here.
# Deliberately no 9:16 -- an ultra-tall crop of prints on a desk reads as an
# accident, not a composition.
CROP_ASPECTS = [
    ("4:3", 4 / 3),
    ("3:4", 3 / 4),
    ("1:1", 1.0),
    ("16:9", 16 / 9),
]


def _paper_center(bgr: np.ndarray, blob_bbox, scale=0.25):
    """Centre of the bright, near-neutral paper inside `blob_bbox`, or None.

    Used only to recentre a multi-print crop, so it must be *tighter* than the
    detection blob, never looser: it opens (to shed stray bright specks) but does
    not close (the close is what bridged the blob into desk glare in the first
    place). The result is trusted only when it lands inside the blob's own bbox
    and covers a real amount of it -- otherwise the blob centre stands.
    """
    x0, y0, x1, y1 = blob_bbox
    small = cv2.resize(bgr, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    pm = ((L > 0.62 * np.percentile(L, 99)) & (np.hypot(A - 128, B - 128) < 16)).astype(np.uint8)
    pm = cv2.morphologyEx(pm, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    ys, xs = np.where(pm)
    if len(ys) < 200:
        return None
    px0, py0, px1, py1 = xs.min() / scale, ys.min() / scale, xs.max() / scale, ys.max() / scale
    pw, ph, bw, bh = px1 - px0, py1 - py0, x1 - x0, y1 - y0
    # The paper span should track the blob's: much smaller means the test missed
    # prints, much larger means it grabbed something past them (a bright wall,
    # blown desk). Either way, don't trust it. A few px of overshoot is normal --
    # paper detection catches the true border edge the blob's rect can undercut.
    if not (0.5 * bw <= pw <= 1.3 * bw and 0.5 * bh <= ph <= 1.3 * bh):
        return None
    pcx, pcy = (px0 + px1) / 2, (py0 + py1) / 2
    # only a gentle recentre; a big shift means the paper read is unreliable
    if abs(pcx - (x0 + x1) / 2) > 0.15 * bw or abs(pcy - (y0 + y1) / 2) > 0.15 * bh:
        return None
    return pcx, pcy


def align_multi(img: np.ndarray, dets: list[Detection], turn: int = 0):
    """Rotate and crop a multi-print photo so the prints sit level and centred.

    Rotates the whole frame by the dominant tilt of the detected prints plus
    `turn` quarter-turns (CCW, from content_rotation -- folded into the same
    warp so the crop shape is chosen for the *final* orientation; cropping
    first and turning after would silently convert a chosen 16:9 into the 9:16
    that CROP_ASPECTS deliberately excludes), then crops around the prints'
    union bounding box with equal margins top/bottom and left/right.

    The crop shape is the best fit from CROP_ASPECTS: for each candidate, the
    tightest crop at that ratio still containing every print pins one axis
    (zero margin) and leaves the excess on the other, so the candidate with the
    most balanced horizontal-vs-vertical margins is simply the one closest to
    the prints' own bounding-box shape. The crop is never grown beyond tightest
    to force the margins equal -- that would buy symmetry with desk. If no
    candidate fits inside the photo, the frame's own ratio is the fallback.

    Returns None -- leave the photo whole, today's existing behaviour --
    rather than force a crop that reaches into the blank corners the rotation
    opens up. These photos usually have generous desk margin, so that should
    be rare, but a photo where the prints already fill the frame edge to edge
    can't be centred without padding that isn't there.
    """
    if not dets:
        return None
    h, w = img.shape[:2]
    tilt = _dominant_tilt(dets)
    angle = tilt + 90.0 * (turn % 4)

    center = (w / 2, h / 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    M[0, 2] += new_w / 2 - center[0]
    M[1, 2] += new_h / 2 - center[1]
    rotated = cv2.warpAffine(img, M, (new_w, new_h), flags=cv2.INTER_LANCZOS4)

    pts = np.concatenate([d.quad for d in dets]).reshape(-1, 1, 2).astype(np.float32)
    pts = cv2.transform(pts, M).reshape(-1, 2)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw2, bh2 = (x1 - x0) / 2, (y1 - y0) / 2

    # Recentre on the *actual* paper. The detected blob can overshoot the prints
    # at one edge -- the segmentation close that bridges each print's photo
    # window also bridges a print to bright desk glare or a shadow just past it
    # -- which slides the crop off centre, so one margin vanishes while the
    # opposite grows (a real complaint on ~1 photo in 5). Paper here is
    # bright-and-neutral *opened but not closed*: the close is exactly what
    # reaches into the glare, so leaving it out gives the true paper edge.
    pcenter = _paper_center(rotated, (x0, y0, x1, y1))
    if pcenter is not None:
        cx, cy = pcenter

    # does a crop stay inside the photo's real (unrotated) footprint, or would
    # it reach past an edge into the blank fill the rotation opened up?
    invM = cv2.invertAffineTransform(M)

    def fits(hw, hh):
        corners = np.array([[cx - hw, cy - hh], [cx + hw, cy - hh],
                            [cx + hw, cy + hh], [cx - hw, cy + hh]], np.float32)
        back = cv2.transform(corners.reshape(-1, 1, 2), invM).reshape(-1, 2)
        pad = 0.5
        return ((back[:, 0] >= -pad).all() and (back[:, 0] <= w + pad).all()
                and (back[:, 1] >= -pad).all() and (back[:, 1] <= h + pad).all())

    best = None
    for label, r in CROP_ASPECTS:
        hh = max(bh2, bw2 / r)
        hw = hh * r
        score = abs((hw - bw2) - (hh - bh2))       # excess margin: 0 on the pinned axis
        if fits(hw, hh) and (best is None or score < best[0]):
            best = (score, label, hw, hh)
    if best is not None:
        _, crop_label, hw, hh = best
    else:
        # the frame's own shape (as turned) -- exactly the pre-CROP_ASPECTS
        # behaviour, and by construction of new_w/new_h it can only fail the
        # footprint test through the tilt, same as before
        ratio = (w / h) if turn % 2 == 0 else (h / w)
        hh = max(bh2, bw2 / ratio)
        hw = hh * ratio
        if not fits(hw, hh):
            return None
        crop_label = "original"

    x0i, y0i = max(0, int(round(cx - hw))), max(0, int(round(cy - hh)))
    x1i, y1i = min(new_w, int(round(cx + hw))), min(new_h, int(round(cy + hh)))
    crop = rotated[y0i:y1i, x0i:x1i]
    return crop, dict(align_tilt=round(tilt, 2), align_n=len(dets), align_crop=crop_label)


def warp(img: np.ndarray, quad: np.ndarray, out_w: int) -> np.ndarray:
    """Perspective-correct the quad onto a portrait canvas of exact instax shape."""
    out_h = int(round(out_w * ASPECT))
    q = np.asarray(quad, np.float32)
    e = [np.linalg.norm(q[(i + 1) % 4] - q[i]) for i in range(4)]
    if (e[0] + e[2]) < (e[1] + e[3]):
        q = np.roll(q, -1, axis=0)
    q = q[::-1].copy()                               # keep handedness: no mirroring
    dst = np.array([[0, 0], [0, out_h - 1], [out_w - 1, out_h - 1], [out_w - 1, 0]], np.float32)
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(q, dst), (out_w, out_h),
                               flags=cv2.INTER_LANCZOS4)


def trim_desk(img: np.ndarray, quad: np.ndarray, cap=0.035, analysis_w=900):
    """Pull each edge inward past any desk that crept into the crop.

    Works on a provisional rectified crop, where 'is this line desk?' is a 1-D
    question. Returns the tightened quad and the per-edge insets in output pixels.
    """
    lab_full = cv2.cvtColor(cv2.GaussianBlur(cv2.resize(img, (0, 0), fx=0.25, fy=0.25),
                                             (7, 7), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    H, W = lab_full.shape[:2]
    k = int(0.03 * max(H, W))
    ring = np.zeros((H, W), bool)
    ring[:k, :] = ring[-k:, :] = True
    ring[:, :k] = ring[:, -k:] = True
    mu = np.median(lab_full[ring], axis=0)
    va, vb = mu[1] - 128, mu[2] - 128
    nv = float(np.hypot(va, vb)) + 1e-6
    if nv < 4:
        # The ring is barely coloured at all -- happens when the card fills
        # almost the whole frame, or the backdrop isn't a classic desk, so
        # there's little real desk in that outer 3% to sample. A hue
        # *direction* derived from a near-neutral reference is essentially
        # noise, and the projection test below turns hypersensitive: it can
        # cross threshold on the card's own white border's ordinary chroma
        # jitter. Better to skip the trim than cut into the border on a
        # signal this unreliable. Every known-good file measures >= ~3.6;
        # the break cases measured ~2.0-2.24.
        return np.asarray(quad, np.float32), dict(top=0, bottom=0, left=0, right=0)
    ua, ub = va / nv, vb / nv

    aw = analysis_w
    ah = int(aw * ASPECT)
    crop = warp(img, quad, aw)
    lab = cv2.cvtColor(cv2.GaussianBlur(crop, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    # project chroma onto the desk's hue direction: shadow keeps the hue, so this
    # survives the shadow the print casts on the side away from the light
    proj = (lab[:, :, 1] - 128) * ua + (lab[:, :, 2] - 128) * ub
    desk = (proj > 0.55 * nv) & (lab[:, :, 0] < 1.25 * mu[0])

    def scan(axis, which):
        last, limit = -1, int(cap * (ah if axis == "y" else aw))
        for i in range(limit):
            idx = i if which < 0 else ((ah - 1 - i) if axis == "y" else (aw - 1 - i))
            line = desk[idx, :] if axis == "y" else desk[:, idx]
            core = line[int(0.12 * len(line)):int(0.88 * len(line))]
            if core.mean() > 0.08:
                last = i
        return last + 4 if last >= 0 else 0

    t, b = scan("y", -1), scan("y", 1)
    l, r = scan("x", -1), scan("x", 1)

    q = np.asarray(quad, np.float32)
    e = [np.linalg.norm(q[(i + 1) % 4] - q[i]) for i in range(4)]
    if (e[0] + e[2]) < (e[1] + e[3]):
        q = np.roll(q, -1, axis=0)
    q = q[::-1].copy()
    dst = np.array([[0, 0], [0, ah - 1], [aw - 1, ah - 1], [aw - 1, 0]], np.float32)
    M = cv2.getPerspectiveTransform(q, dst)
    inner = np.array([[l, t], [l, ah - 1 - b], [aw - 1 - r, ah - 1 - b], [aw - 1 - r, t]],
                     np.float32).reshape(-1, 1, 2)
    src = cv2.perspectiveTransform(inner, np.linalg.inv(M)).reshape(-1, 2)
    return src[::-1], dict(top=t, bottom=b, left=l, right=r)


def residual_desk(crop_bgr: np.ndarray, skip=4, probe=0.02) -> dict:
    """How deep desk still reaches into each edge of a finished crop, in pixels.

    Deliberately a plain warm-and-dark test rather than the hue model used for
    trimming: the point is to second-guess that model, so it should not share its
    blind spots. A print's border is neither warm nor dark, so this is unambiguous.
    """
    rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    warm = (rgb[:, :, 0] > rgb[:, :, 2] + 12) & (rgb.mean(axis=2) < 170)
    H, W = warm.shape
    out = {}
    for name, get, n in (("top", lambda i: warm[i], int(probe * H)),
                         ("bottom", lambda i: warm[H - 1 - i], int(probe * H)),
                         ("left", lambda i: warm[:, i], int(probe * W)),
                         ("right", lambda i: warm[:, W - 1 - i], int(probe * W))):
        depth = 0
        for i in range(skip, n):
            if get(i).mean() > 0.15:
                depth = i + 1
        out[name] = depth
    return out


def orient(crop_bgr: np.ndarray):
    """Rotate a rectified front so the wide signature border is at the bottom.

    An instax mini's photo window sits off-centre along the long axis, leaving a
    ~5mm border at one end and ~17mm at the other, so locating the window says
    which way is up without looking at the picture.

    The window is located by its edges, not its brightness: brightness fails on
    prints whose own content is pale (a white wall reads as paper) and on the
    signature, which is dark ink sitting in the border. The window boundary, by
    contrast, is always a hard full-width horizontal edge.

    That full-width property is why the row profile is a low percentile across
    the row, not the mean: a mean can be won by a strong but partial-width edge
    inside the photo (a pale face against dark hair, say), which has nothing to
    do with the border and can out-score the true transition if the photo's own
    content is higher-contrast than the paper edge at that spot. A percentile
    close to the row's minimum only scores high where the gradient is strong
    almost everywhere across the row, which a same-width content edge can't
    fake but the genuine full-width border transition always satisfies.

    Returns (image, ratio). Ratio is wide gap / narrow gap; on a real instax mini
    it lands near 2.1. Close to 1 means the two ends looked alike and the call is
    untrustworthy.
    """
    gray = cv2.cvtColor(cv2.GaussianBlur(crop_bgr, (5, 5), 0), cv2.COLOR_BGR2GRAY).astype(np.float32)
    H, W = gray.shape
    band = np.abs(cv2.Scharr(gray, cv2.CV_32F, 0, 1))[:, int(0.2 * W):int(0.8 * W)]
    prof = np.percentile(band, 20, axis=1)
    m = int(0.03 * H)
    prof[:m] = 0
    prof[-m:] = 0                                     # ignore the crop's own soft rim

    top = int(np.argmax(prof[:int(0.45 * H)]))
    bottom = int(0.55 * H) + int(np.argmax(prof[int(0.55 * H):]))
    top_gap, bottom_gap = top, H - 1 - bottom
    lo, hi = sorted((top_gap, bottom_gap))
    ratio = hi / max(lo, 1)
    if bottom_gap < top_gap:                          # wide border is up top
        crop_bgr = cv2.rotate(crop_bgr, cv2.ROTATE_180)
    return crop_bgr, ratio


# ------------------------------------------ multi-print content orientation

# align_multi() gets a multi-print photo level but not upright: mod-90 tilt has
# no notion of up-vs-down or a quarter turn, and the frame carries no single
# signature border to read the way orient() reads one card's. The content does
# carry it, though -- these are photos of people, and the turn that stands the
# most faces upright is the way up. A small face detector supplies that; it is
# optional and cached, and if it can't be loaded the frame is just left as
# align_multi left it (the pre-face behaviour), never an error.

_FACE_MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
                   "face_detection_yunet/face_detection_yunet_2023mar.onnx")
_FACE_MODEL_NAME = "face_detection_yunet_2023mar.onnx"
_FACE_DET = "unset"   # cached detector, or None once a load attempt has failed


def _face_model_path() -> str | None:
    """The YuNet model file, fetched to a user cache on first use. $CHEKI_FACE_MODEL
    overrides the location; a failed download disables the feature, not the run."""
    env = os.environ.get("CHEKI_FACE_MODEL")
    if env:
        return env if os.path.exists(env) else None
    cache = os.path.join(os.path.expanduser("~"), ".cache", "checleaner")
    path = os.path.join(cache, _FACE_MODEL_NAME)
    if os.path.exists(path):
        return path
    try:
        import urllib.request
        os.makedirs(cache, exist_ok=True)
        print(f"fetching face-orientation model (~230 KB) -> {path}", flush=True)
        urllib.request.urlretrieve(_FACE_MODEL_URL, path)
        return path
    except Exception as exc:                          # offline, blocked, etc.
        print(f"  multi-print reorientation off (no model: {exc})", flush=True)
        return None


def _face_detector():
    """Lazily build the detector once; return None (and stay None) if it can't be."""
    global _FACE_DET
    if _FACE_DET != "unset":
        return _FACE_DET
    _FACE_DET = None
    if not hasattr(cv2, "FaceDetectorYN"):
        return None
    path = _face_model_path()
    if not path:
        return None
    try:
        _FACE_DET = cv2.FaceDetectorYN.create(path, "", (320, 320), 0.6, 0.3, 5000)
    except Exception as exc:                          # pragma: no cover
        print(f"  multi-print reorientation off (model load failed: {exc})", flush=True)
        _FACE_DET = None
    return _FACE_DET


def content_rotation(img: np.ndarray, downscale: int = 1400,
                     min_score: float = 1.2, margin: float = 1.5) -> int:
    """Number of 90-degree CCW turns that stand a multi-print frame upright (0-3).

    Each turn is scored by summed face confidence, but a turn only wins over
    leaving the frame alone when the frame as-is holds little face evidence *and*
    the turn is decisively better (min_score / margin). That asymmetry is
    deliberate: a frame already upright, or holding no faces at all, must be left
    exactly as it is -- the cost of missing a rotation is one review, the cost of
    inventing one is corrupting a photo that was already right.
    """
    det = _face_detector()
    if det is None:
        return 0
    h, w = img.shape[:2]
    sc = downscale / max(h, w)
    small = cv2.resize(img, (int(w * sc), int(h * sc))) if sc < 1 else img

    def score(im):
        det.setInputSize((im.shape[1], im.shape[0]))
        _, faces = det.detect(im)
        return 0.0 if faces is None else float(faces[:, -1].sum())

    s = [score(np.ascontiguousarray(np.rot90(small, k))) for k in range(4)]
    best = int(np.argmax(s))
    if best != 0 and s[best] >= min_score and s[best] > margin * s[0]:
        return best
    return 0


# ------------------------------------------------------------------ the driver

@dataclass
class Result:
    name: str
    kind: str = "single"
    flags: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def run(args) -> int:
    src = args.folder
    files = sorted(f for f in os.listdir(src)
                   if os.path.splitext(f)[1].lower() in EXTS
                   and not f.startswith("."))
    if not files:
        sys.exit(f"no images in {src}")

    white_t = np.full(3, float(to_linear(np.array([args.white]))[0]))
    black_t = np.full(3, float(to_linear(np.array([args.black]))[0]))

    # -- pass 1: measure and solve every image ------------------------------
    print(f"measuring {len(files)} images", flush=True)
    solved, results = {}, {}
    for name in files:
        path = os.path.join(src, name)
        thumb = Image.open(path)
        thumb.thumbnail((1400, 1400))
        rgb = np.asarray(thumb.convert("RGB")).astype(np.float32)
        m = measure(rgb)
        gain, off = solve_levels(rgb, m, white_t, black_t)

        corrected = to_srgb(soft_shoulder(np.clip(to_linear(rgb) * gain + off, 0, None)))
        after = measure(corrected)
        solved[name] = (gain, off, after.desk)

        r = Result(name)
        r.stats = dict(
            white_before=np.round(to_srgb(m.white), 1).tolist(),
            black_before=np.round(to_srgb(m.black), 2).tolist(),
            gain=np.round(gain, 3).tolist(),
            clipped_pct=round(m.white_clipped * 100, 1),
        )
        if m.white_clipped > 0.15:
            r.flags.append(f"white reference {m.white_clipped*100:.0f}% clipped")
        if gain.max() > args.max_gain or gain.min() < 1 / args.max_gain:
            r.flags.append(f"extreme correction (gain {np.round(gain,2).tolist()})")
        results[name] = r

    # -- folder-wide desk target -------------------------------------------
    desks = [d for (_, _, d) in solved.values() if d is not None]
    target_u = None
    if desks and args.desk_strength > 0:
        target_u = np.median([np.clip((d - black_t) / (white_t - black_t), 1e-4, 0.999)
                              for d in desks], axis=0)
        print(f"desk target {np.round(to_srgb(black_t + target_u*(white_t-black_t)),1).tolist()}"
              f" from {len(desks)} images", flush=True)

    if args.dry_run:
        for name in files:
            r = results[name]
            print(f"  {name}  gain={r.stats['gain']}  {'; '.join(r.flags) or 'ok'}")
        return 0

    out_root = args.out or src
    good_dir = os.path.join(out_root, "balanced")
    review_dir = os.path.join(out_root, "review")
    os.makedirs(good_dir, exist_ok=True)
    os.makedirs(review_dir, exist_ok=True)

    # A file already sitting in balanced/ or review/ produces the identical
    # output if reprocessed -- the pipeline is deterministic -- so redoing it
    # is pure waste. Skip by default and reuse the prior report.csv row for
    # its pass-2 stats/flags; --force to reprocess everything regardless
    # (e.g. after an algorithm change that should benefit every file).
    prior = {} if args.force else _read_prior_report(os.path.join(out_root, "report.csv"))
    already_done = {}
    for name in files:
        in_good = os.path.exists(os.path.join(good_dir, name))
        in_review = os.path.exists(os.path.join(review_dir, name))
        if in_good and not in_review:
            already_done[name] = "balanced"
        elif in_review and not in_good:
            already_done[name] = "review"
        # else: present in neither (normal) or both (stale duplicate from
        # before a file got reclassified) -- either way, not cleanly
        # resolved, so fall through and reprocess it. A duplicate gets
        # cleaned up as a side effect of the stale-copy removal below.
    n_skipped = 0

    # -- pass 2: apply, crop, orient ---------------------------------------
    for name in files:
        r = results[name]

        if not args.force and name in already_done:
            n_skipped += 1
            old = prior.get(name)
            if old:
                r.kind = old.get("kind") or r.kind
                for flag in (f.strip() for f in old.get("flags", "").split(";")):
                    if flag and flag not in r.flags:
                        r.flags.append(flag)
                for k in ("aspect", "fill", "border_ratio", "align_tilt", "align_n",
                          "align_crop", "reorient", "windows"):
                    v = old.get(k)
                    if v not in (None, ""):
                        r.stats[k] = v
            else:
                r.kind = "skipped"
            print(f"  {name:<34} {r.kind:<7} -> {already_done[name]:<8} "
                  "(unchanged, already processed)", flush=True)
            continue

        path = os.path.join(src, name)
        gain, off, desk = solved[name]
        gamma = (desk_gamma(desk, target_u, white_t, black_t, args.desk_strength)
                 if (desk is not None and target_u is not None) else None)

        rgb8 = np.asarray(Image.open(path).convert("RGB"))
        img = cv2.cvtColor(apply(rgb8, gain, off, gamma, white_t, black_t), cv2.COLOR_RGB2BGR)

        if not args.no_crop:
            det = detect_print(path)
            single = (det.quad is not None and det.n_blobs == 1
                      and args.aspect_lo <= det.aspect <= args.aspect_hi
                      and det.fill >= args.min_fill
                      and det.solidity >= args.min_solidity)
            near_miss = (det.quad is not None and det.n_blobs == 1
                         and 1.40 <= det.aspect <= 1.90)
            # Photo-window backstop for a single card-shaped blob: several prints
            # in a tidy row merge into one clean rectangle that can pass the tight
            # single test outright (aspect in range, no seams for fill/solidity to
            # catch -- this is exactly how a real 3-print row got cropped as one
            # card) or land just outside it as a near-miss. Either way, a blob
            # enclosing many photo windows can't be one card, so overrule it. Only
            # the high side is evidence: a low count proves nothing (count_windows).
            if single or near_miss:
                wins = count_windows(path)
                if wins is not None:
                    r.stats["windows"] = wins
                    if wins >= args.multi_windows:
                        single = near_miss = False
            if single:
                r.stats.update(aspect=round(det.aspect, 3), fill=round(det.fill, 3))
                quad, insets = trim_desk(img, det.quad)
                crop = warp(img, quad, args.width)
                crop, ratio = orient(crop)
                r.stats.update(trim=insets, border_ratio=round(ratio, 2))

                # did the trim actually clear the desk?
                left = residual_desk(crop)
                worst = max(left.values())
                if worst > args.max_residual:
                    r.flags.append(f"desk still on {max(left, key=left.get)} edge (~{worst}px)")
                if ratio < args.min_border_ratio:
                    r.flags.append(f"orientation uncertain (border ratio {ratio:.2f})")
                img = crop
            else:
                # Several prints, or one blob whose shape is nowhere near a single
                # card (two prints side by side merge into one wide blob): an
                # ordinary multi-print shot. Only a near-miss — roughly card-shaped
                # but failing the tight test, and not overruled by the window
                # backstop above — is worth a human look, because that is what a
                # genuinely bad single-card fit looks like.
                r.kind = "multi"
                # align_multi only levels; the content turn (a quarter or half
                # turn so the frame isn't left sideways) is decided *first* and
                # folded into the alignment warp, because the crop shape is
                # picked from CROP_ASPECTS for the final orientation -- turning
                # after cropping would flip a chosen 16:9 into 9:16
                turn = 0 if args.no_reorient else content_rotation(img)
                if near_miss:
                    r.kind = "single?"
                    r.flags.append(f"fit rejected (aspect {det.aspect:.3f}, fill {det.fill:.3f}, "
                                   f"solidity {det.solidity:.3f})")
                else:
                    aligned = align_multi(img, detect_all_prints(path), turn=turn)
                    if aligned is not None:
                        img, align_stats = aligned
                        r.kind = "aligned"
                        r.stats.update(align_stats)
                        if turn:
                            r.stats["reorient"] = turn * 90
                        turn = 0            # already folded into the warp
                if turn:                    # single? / align declined: turn whole
                    img = np.ascontiguousarray(np.rot90(img, turn))
                    r.stats["reorient"] = turn * 90
        else:
            r.kind = "nocrop"

        dest_dir = review_dir if r.flags else good_dir
        # a reprocess (--force, or a code change) can reclassify a file --
        # drop any stale copy left in the other directory so it isn't
        # duplicated across both
        stale = os.path.join(good_dir if dest_dir is review_dir else review_dir, name)
        if os.path.exists(stale):
            os.remove(stale)
        dest = os.path.join(dest_dir, name)
        cv2.imwrite(dest, img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
        _copy_exif(path, dest, img.shape[1], img.shape[0])

        note = "; ".join(r.flags) if r.flags else "ok"
        print(f"  {name:<34} {r.kind:<7} -> {os.path.basename(dest_dir):<8} {note}", flush=True)

    _write_report(os.path.join(out_root, "report.csv"), files, results)
    _write_review_notes(review_dir, files, results)
    n_review = sum(1 for r in results.values() if r.flags)
    skip_note = f" ({n_skipped} unchanged, skipped)" if n_skipped else ""
    print(f"\n{len(files) - n_review} in balanced/, {n_review} in review/{skip_note}")
    print(f"report: {os.path.join(out_root, 'report.csv')}")
    if n_review:
        print(f"review notes: {os.path.join(review_dir, 'report.txt')}")
    return 0


def _copy_exif(src, dest, w, h):
    if piexif is None:
        return
    try:
        ex = piexif.load(src)
        ex.pop("thumbnail", None)
        ex["1st"] = {}
        ex["0th"].pop(piexif.ImageIFD.Orientation, None)
        if piexif.ExifIFD.PixelXDimension in ex["Exif"]:
            ex["Exif"][piexif.ExifIFD.PixelXDimension] = w
        if piexif.ExifIFD.PixelYDimension in ex["Exif"]:
            ex["Exif"][piexif.ExifIFD.PixelYDimension] = h
        piexif.insert(piexif.dump(ex), dest)
    except Exception:
        pass                                          # EXIF is nice to have, not essential


def _write_report(path, files, results):
    with open(path, "w", newline="") as fh:
        wr = csv.writer(fh)
        # dest is derived (review iff flags), not tracked separately, so it can
        # never drift out of sync with where the file actually landed
        wr.writerow(["file", "dest", "kind", "white_before", "black_before", "gain",
                     "clipped_pct", "aspect", "fill", "border_ratio",
                     "align_tilt", "align_n", "align_crop", "reorient",
                     "windows", "flags"])
        for name in files:
            r = results[name]
            s = r.stats
            dest = "review" if r.flags else "balanced"
            wr.writerow([name, dest, r.kind, s.get("white_before"), s.get("black_before"),
                         s.get("gain"), s.get("clipped_pct"), s.get("aspect"),
                         s.get("fill"), s.get("border_ratio"),
                         s.get("align_tilt"), s.get("align_n"), s.get("align_crop"),
                         s.get("reorient"), s.get("windows"),
                         "; ".join(r.flags)])


# plain-English gloss per flag prefix, for review/report.txt -- the flag
# string itself (also used in report.csv) stays terse and technical, so this
# is matched by prefix rather than replacing it
_FLAG_EXPLANATIONS = [
    ("white reference",
     "The print's white border was overexposed in the original photo, so the "
     "colour correction it's based on is a bit of a guess. Check the colours "
     "don't look washed out or tinted -- if the photo was shot in bright "
     "light, that's the fix for next time, not something to redo here."),
    ("extreme correction",
     "This photo needed an unusually large colour correction. Check for "
     "over-saturated colour or noisy shadows, especially in reds."),
    ("fit rejected",
     "Found one blob that's roughly card-shaped but not confident enough to "
     "crop automatically. Look at the photo: if it's genuinely a single "
     "print (shot at an odd angle, say), crop and straighten it yourself; if "
     "it's actually multiple prints -- the usual reason this fires -- it's "
     "already colour-balanced correctly and needs nothing further."),
    ("desk still on",
     "A sliver of desk is still visible on one edge of the crop. Trim it "
     "further by hand if it bothers you."),
    ("orientation uncertain",
     "The two ends of the print's border looked too similar in width to "
     "confidently tell which one is the wide signature border. Check "
     "whether the photo is upside down and rotate 180 degrees if so."),
]


def _explain_flag(flag: str) -> str:
    return next((e for prefix, e in _FLAG_EXPLANATIONS if flag.startswith(prefix)), "")


def _read_prior_report(path):
    """Load a previous run's report.csv, if there is one, so a file that's
    already in balanced/ or review/ can carry forward the pass-2 stats and
    flags that produced it instead of redoing that (expensive) work. Returns
    {} if there's nothing to read yet -- normal on a folder's first run.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, newline="") as fh:
            return {row["file"]: row for row in csv.DictReader(fh)}
    except (OSError, csv.Error, KeyError):
        return {}


def _write_review_notes(review_dir, files, results):
    """Plain-text summary dropped in review/ itself, next to the photos it
    describes, so what needs a look is readable without cross-referencing
    report.csv or console output -- which matters when a run is driven by an
    agent and nobody's watching stdout live."""
    flagged = [(name, results[name]) for name in files if results[name].flags]
    with open(os.path.join(review_dir, "report.txt"), "w") as fh:
        if not flagged:
            fh.write("Nothing needs review.\n")
            return
        fh.write(f"{len(flagged)} file(s) need a look. Full detail in report.csv.\n\n")
        for name, r in flagged:
            fh.write(f"{name}\n")
            for flag in r.flags:
                fh.write(f"  - {flag}\n")
                explanation = _explain_flag(flag)
                if explanation:
                    fh.write(textwrap.fill(explanation, width=76,
                                            initial_indent="      ",
                                            subsequent_indent="      ") + "\n")
            fh.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Factored out of main() so tools/detect.py can borrow the exact same
    default thresholds -- a detection preview that used different numbers than
    a real run would be worse than useless."""
    p = argparse.ArgumentParser(
        description="Colour-balance and crop photos of instax mini prints.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("folder", help="folder of photos")
    p.add_argument("-o", "--out", help="output root (default: alongside the input)")
    p.add_argument("--white", type=float, default=238.8,
                   help="target for the print's white border, 0-255")
    p.add_argument("--black", type=float, default=2.2, help="target black point, 0-255")
    p.add_argument("--desk-strength", type=float, default=0.5,
                   help="how hard to match the desk, 0 disables")
    p.add_argument("--width", type=int, default=1800, help="output width for crops")
    p.add_argument("--quality", type=int, default=96, help="JPEG quality")
    p.add_argument("--no-crop", action="store_true", help="colour-balance only")
    p.add_argument("--no-reorient", action="store_true",
                   help="skip standing multi-print photos upright from their "
                        "content (needs the cached YuNet face model)")
    p.add_argument("--dry-run", action="store_true", help="measure and report, write nothing")
    p.add_argument("--force", action="store_true",
                   help="reprocess every file, even ones already in balanced/ or review/ "
                        "(default: skip them and reuse their last result -- the expensive "
                        "part is the full-resolution colour pass, not detection)")
    p.add_argument("--aspect-lo", type=float, default=1.53, help="reject fits below this")
    p.add_argument("--aspect-hi", type=float, default=1.65, help="reject fits above this")
    p.add_argument("--min-fill", type=float, default=0.93,
                   help="reject blobs less rectangular than this")
    p.add_argument("--min-solidity", type=float, default=0.97,
                   help="reject blobs whose raw mask has notches the hull "
                        "smooths over -- catches a tight card grid that "
                        "coincidentally fits the single-card aspect/fill window")
    p.add_argument("--multi-windows", type=int, default=7,
                   help="a near-miss blob enclosing at least this many photo "
                        "windows is treated as several merged prints, not a "
                        "suspect single card (worst genuine single measured 6)")
    p.add_argument("--min-border-ratio", type=float, default=1.6,
                   help="flag orientation when the two end borders look this alike "
                        "(a real instax mini measures ~2.1)")
    p.add_argument("--max-residual", type=int, default=15,
                   help="flag a crop with more than this many output px of desk on an edge")
    p.add_argument("--max-gain", type=float, default=2.2,
                   help="flag corrections stronger than this")
    return p


def main():
    args = build_parser().parse_args()
    if not os.path.isdir(args.folder):
        sys.exit(f"not a folder: {args.folder}")
    sys.exit(run(args))


if __name__ == "__main__":
    main()
