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

    python3 tools/detect.py chekis/main/PXL_20260427_023359428.MP.jpg [...]
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from checleaner import (build_parser, detect_print, detect_all_prints,
                        align_multi, warp, orient, trim_desk, CARD_SOLIDITY_MIN)


def classify(det, d) -> str:
    """run()'s single / near-miss / multi decision for one Detection, kept
    byte-for-byte in step with the branch in run() -- if that changes, change
    this too, or the preview lies."""
    solidity_floor = (min(d.min_solidity, CARD_SOLIDITY_MIN)
                      if det.cornered else d.min_solidity)
    single = (det.quad is not None and det.n_blobs == 1
              and d.aspect_lo <= det.aspect <= d.aspect_hi
              and det.fill >= d.min_fill
              and det.solidity >= solidity_floor)
    if single:
        return "single"
    near_miss = (det.quad is not None and det.n_blobs == 1
                 and 1.40 <= det.rect_aspect <= 1.90)
    return "single?" if near_miss else "multi"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="image files to inspect")
    ap.add_argument("--crop", metavar="DIR",
                    help="warp+orient each single-card hit into DIR (raw colour) to eyeball orientation")
    args = ap.parse_args()

    d = build_parser().parse_args(["."])   # the CLI's own default thresholds
    if args.crop:
        os.makedirs(args.crop, exist_ok=True)

    for path in args.files:
        name = os.path.basename(path)
        det = detect_print(path)
        kind = classify(det, d)
        extra = ""
        if kind == "multi":
            dets = detect_all_prints(path)
            img = cv2.imread(path)
            aligned = align_multi(img, dets) if img is not None else None
            extra = f"  {len(dets)} blobs, {'level' if aligned is not None else 'whole'}"
        print(f"{name:<38} {kind:<8} n_blobs={det.n_blobs} "
              f"aspect={det.aspect:.3f} fill={det.fill:.3f} solidity={det.solidity:.3f}{extra}")
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
