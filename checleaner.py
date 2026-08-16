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

Photos showing several prints are balanced but left uncropped.

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
    n_blobs: int = 0
    ok: bool = False
    reason: str = ""


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
    img = cv2.imread(path)
    if img is None:
        return Detection(reason="unreadable")
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
    if not big:
        return Detection(n_blobs=0, reason="no print found")

    idx = max(big, key=lambda i: stats[i, cv2.CC_STAT_AREA])
    comp = (labels == idx).astype(np.uint8)
    contour = max(cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0],
                  key=cv2.contourArea)
    hull = cv2.convexHull(contour)
    rect = cv2.minAreaRect(hull)
    (rw, rh) = rect[1]
    if min(rw, rh) < 1:
        return Detection(n_blobs=len(big), reason="degenerate fit")

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
        n_blobs=len(big),
    )


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

    Returns (image, ratio). Ratio is wide gap / narrow gap; on a real instax mini
    it lands near 2.1. Close to 1 means the two ends looked alike and the call is
    untrustworthy.
    """
    gray = cv2.cvtColor(cv2.GaussianBlur(crop_bgr, (5, 5), 0), cv2.COLOR_BGR2GRAY).astype(np.float32)
    H, W = gray.shape
    prof = np.abs(cv2.Scharr(gray, cv2.CV_32F, 0, 1))[:, int(0.2 * W):int(0.8 * W)].mean(axis=1)
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

    # -- pass 2: apply, crop, orient ---------------------------------------
    for name in files:
        path = os.path.join(src, name)
        r = results[name]
        gain, off, desk = solved[name]
        gamma = (desk_gamma(desk, target_u, white_t, black_t, args.desk_strength)
                 if (desk is not None and target_u is not None) else None)

        rgb8 = np.asarray(Image.open(path).convert("RGB"))
        img = cv2.cvtColor(apply(rgb8, gain, off, gamma, white_t, black_t), cv2.COLOR_RGB2BGR)

        if not args.no_crop:
            det = detect_print(path)
            single = (det.quad is not None and det.n_blobs == 1
                      and args.aspect_lo <= det.aspect <= args.aspect_hi
                      and det.fill >= args.min_fill)
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
                # card (two prints side by side merge into one wide blob): that's an
                # ordinary multi-print shot, so balance it and leave it whole.
                # Only a near-miss — roughly card-shaped but failing the tight test —
                # is worth a human look, because that's what a bad fit looks like.
                r.kind = "multi"
                near_miss = (det.quad is not None and det.n_blobs == 1
                             and 1.40 <= det.aspect <= 1.90)
                if near_miss:
                    r.kind = "single?"
                    r.flags.append(f"fit rejected (aspect {det.aspect:.3f}, fill {det.fill:.3f})")
        else:
            r.kind = "nocrop"

        dest_dir = review_dir if r.flags else good_dir
        dest = os.path.join(dest_dir, name)
        cv2.imwrite(dest, img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
        _copy_exif(path, dest, img.shape[1], img.shape[0])

        note = "; ".join(r.flags) if r.flags else "ok"
        print(f"  {name:<34} {r.kind:<7} -> {os.path.basename(dest_dir):<8} {note}", flush=True)

    _write_report(os.path.join(out_root, "report.csv"), files, results)
    n_review = sum(1 for r in results.values() if r.flags)
    print(f"\n{len(files) - n_review} in balanced/, {n_review} in review/")
    print(f"report: {os.path.join(out_root, 'report.csv')}")
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
        wr.writerow(["file", "kind", "white_before", "black_before", "gain",
                     "clipped_pct", "aspect", "fill", "border_ratio", "flags"])
        for name in files:
            r = results[name]
            s = r.stats
            wr.writerow([name, r.kind, s.get("white_before"), s.get("black_before"),
                         s.get("gain"), s.get("clipped_pct"), s.get("aspect"),
                         s.get("fill"), s.get("border_ratio"), "; ".join(r.flags)])


def main():
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
    p.add_argument("--dry-run", action="store_true", help="measure and report, write nothing")
    p.add_argument("--aspect-lo", type=float, default=1.53, help="reject fits below this")
    p.add_argument("--aspect-hi", type=float, default=1.65, help="reject fits above this")
    p.add_argument("--min-fill", type=float, default=0.93,
                   help="reject blobs less rectangular than this")
    p.add_argument("--min-border-ratio", type=float, default=1.6,
                   help="flag orientation when the two end borders look this alike "
                        "(a real instax mini measures ~2.1)")
    p.add_argument("--max-residual", type=int, default=15,
                   help="flag a crop with more than this many output px of desk on an edge")
    p.add_argument("--max-gain", type=float, default=2.2,
                   help="flag corrections stronger than this")
    args = p.parse_args()
    if not os.path.isdir(args.folder):
        sys.exit(f"not a folder: {args.folder}")
    sys.exit(run(args))


if __name__ == "__main__":
    main()
