#!/usr/bin/env python3
"""Fast detection preview -- the geometry half of the pipeline, on named files.

The slow part of a full run is the colour pass, and it is unavoidable there:
pass 1 measures *every* file in the batch to solve a shared desk target (~3 s
each), then pass 2 re-reads and corrects each at full resolution (~10 s each).
None of that touches detection -- which blob is a card, its aspect/fill/solidity,
which way up it goes, whether it is one print or several. So when you are
iterating on the *geometry* (detect_print, orient, align_multi, or the
single/near-miss thresholds), running the whole dataset just to see the decision
change is pure waste. This runs only that decision, on only the files you name,
in well under a second each.

    python3 tools/detect.py chekis/main/<file>.jpg [...]
    python3 tools/detect.py --crop /tmp/out chekis/main/*.jpg

Per file it prints the same single / single? / multi verdict run() would reach,
reusing the CLI's own default thresholds via build_parser() so the preview and a
real run cannot drift apart. With --crop it also warps and orients each
single-card hit and writes the result so you can eyeball orientation -- it warps
the raw photo, since colour never moves a pixel, so the crop's geometry is
identical to what a full run produces. Files run() would leave whole (multi) are
reported, with whether align_multi would level them, but not cropped -- matching
the pipeline, which does not carve a card out of a multi-print shot.
"""
import os
import sys
import argparse

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import checleaner
from checleaner import (build_parser, detect_print, detect_all_prints,
                        align_multi, warp, orient, trim_desk, count_windows,
                        CARD_SOLIDITY_MIN)


def classify(det, d, windows=None) -> str:
    """run()'s single / near-miss / multi decision for one Detection, kept
    byte-for-byte in step with the branch in run() -- if that changes, change
    this too, or the preview lies.

    It did lie: the photo-window backstop was added to run() and never mirrored
    here, so this reported "single" for two files a real run demoted to multi.
    Hence `windows` is not optional in spirit -- pass the count, or the answer
    is only the pre-backstop half of the decision.
    """
    solidity_floor = (min(d.min_solidity, CARD_SOLIDITY_MIN)
                      if det.cornered else d.min_solidity)
    single = (det.quad is not None and det.n_blobs == 1
              and d.aspect_lo <= det.aspect <= d.aspect_hi
              and det.fill >= d.min_fill
              and det.solidity >= solidity_floor)
    near_miss = (det.quad is not None and det.n_blobs == 1
                 and 1.40 <= det.rect_aspect <= 1.90)
    if (single or near_miss) and windows is not None:
        if windows >= (d.card_windows if single else d.multi_windows):
            single = near_miss = False
    if single:
        return "single"
    return "single?" if near_miss else "multi"


def sheen_report(path: str) -> str:
    """Every paper piece in the biggest blob with its own boundary sharpness.

    `CARD_EDGE_SHARP` is the one threshold that can't be sanity-checked from a
    crop: it decides which pieces of a blob are card and which are desk sheen,
    and both answers produce a plausible-looking rectangle. This prints the
    numbers the decision is actually made on -- area and mean Scharr magnitude
    per piece, then the box that comes out -- so the gap between the two classes
    can be seen rather than assumed. It is also the ground truth the JS port is
    calibrated against: checleaner.html scores the same pieces about 0.23x these
    values, which is where its own 105 comes from (docs/PIPELINE.md § 3).
    """
    seg = checleaner._segment_prints(path)
    if seg is None:
        return "no segmentation"
    idx = seg["big"][0] if seg["big"] else 1
    blob = seg["labels"] == idx
    raw = seg["raw"] & blob
    k = np.ones((2 * checleaner.SHEEN_ERODE + 1,) * 2, np.uint8)
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(
        cv2.erode(raw.astype(np.uint8), k), 8)
    pieces = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < checleaner.SHEEN_MIN_AREA * blob.size:
            continue
        grown = ((cv2.dilate((lbl == i).astype(np.uint8), k) > 0) & raw).astype(np.uint8)
        rim = (cv2.dilate(grown, np.ones((3, 3), np.uint8)) - grown) > 0
        if not rim.any():
            continue
        score = float(seg["edge"][rim].mean())
        pieces.append(f"{area}px@{score:.0f}"
                      + ("" if score >= checleaner.CARD_EDGE_SHARP else "*"))
    box = checleaner._sheen_free_bbox(seg, idx)
    return (f"box={box if box else 'none (blob stands)'} "
            f"pieces=[{', '.join(pieces)}]  (* = read as sheen)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="image files to inspect")
    ap.add_argument("--crop", metavar="DIR",
                    help="warp+orient each single-card hit into DIR (raw colour) to eyeball orientation")
    ap.add_argument("--sheen", action="store_true",
                    help="also show each paper piece's boundary sharpness and the trimmed box")
    args = ap.parse_args()

    d = build_parser().parse_args(["."])   # the CLI's own default thresholds
    if args.crop:
        os.makedirs(args.crop, exist_ok=True)

    for path in args.files:
        name = os.path.basename(path)
        det = detect_print(path)
        wins = count_windows(path)
        kind = classify(det, d, wins)
        extra = f" windows={wins}" if wins is not None else ""
        if kind == "multi":
            dets = detect_all_prints(path)
            img = cv2.imread(path)
            aligned = align_multi(img, dets) if img is not None else None
            extra += f"  {len(dets)} blobs, {'level' if aligned is not None else 'whole'}"
        print(f"{name:<38} {kind:<8} n_blobs={det.n_blobs} "
              f"aspect={det.aspect:.3f} fill={det.fill:.3f} solidity={det.solidity:.3f}{extra}")
        if args.sheen:
            print(f"{'':<38} {sheen_report(path)}")
        if kind == "single" and args.crop:
            img = cv2.imread(path)
            quad, _ = trim_desk(img, det.quad)
            crop, ratio = orient(warp(img, quad, d.width))
            out = os.path.join(args.crop, name)
            cv2.imwrite(out, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            print(f"{'':<38} -> {out}  border_ratio={ratio:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
