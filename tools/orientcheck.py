#!/usr/bin/env python3
"""Score an orientation estimator against the library's own answers.

`content_rotation()` picks the quarter turn that stands a multi-print frame
upright, using a face model. Anything proposed to replace it -- because the
phone app can't ship that model (see CLAUDE.md's next steps) -- has to be judged
against the same photos, and the bar is unusual: it is far more important never
to turn a frame that was already right than to catch every frame that is wrong.
So "mostly agrees" is not a pass, and the number that matters is *wrong*, not
*right*.

Ground truth is the `reorient` column of each batch's `report.csv`, i.e. what
the face detector decided, which has been looked at. Frames it left alone are
recorded as 0.

    python3 tools/orientcheck.py                 # score the built-in estimator
    CAP=0.6 RATIO=4 python3 tools/orientcheck.py # ... with different thresholds

The estimator here is **border asymmetry, and it does not work** -- kept because
the scoring half is the reusable part, and because if per-print splitting ever
lands (next steps) this becomes worth re-running in five minutes. See the
2026-08-24 entry in docs/HISTORY.md for the numbers and why.
"""
import os
import sys
import csv
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import checleaner as C

# A window smaller than this fraction of the paper's bbox is ink or a speck,
# not a print's picture area. Same order as count_windows' own floor.
MIN_WIN_FRAC = 0.004
# How far out from a window the walk may go, as a fraction of the window's own
# short side. A print's border cannot be longer than that, and without a cap the
# walk crosses whole neighbouring cards -- runs of 261, 284 and 587 px where a
# real 20 mm border is about 58.
CAP_FRAC = float(os.environ.get("CAP", 0.75))
# How lopsided an axis must be before it decides. Real instax is 20 mm against
# 4 mm, so a clean measurement lands near 5.
MIN_RATIO = float(os.environ.get("RATIO", 2.5))

DIRS = ((1, 0), (0, -1), (-1, 0), (0, 1))          # down, left, up, right
NAMES = ("down", "left", "up", "right")


def windows(path, size=1100):
    """(paper mask, window labels, stats, centroids) for one photo, or None.

    Windows are the enclosed holes in the paper -- one per print's picture area,
    found the same way count_windows() finds them.
    """
    seg = C._segment_prints(path, size)
    if seg is None or not seg["big"]:
        return None
    paper = np.isin(seg["labels"], seg["big"])
    ys, xs = np.where(paper)
    sub = paper[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.uint8)
    notpaper = np.pad(1 - sub, 1, constant_values=1)
    ffmask = np.zeros((notpaper.shape[0] + 2, notpaper.shape[1] + 2), np.uint8)
    filled = notpaper.copy()
    cv2.floodFill(filled, ffmask, (0, 0), 2)
    holes = (((notpaper == 1) & (filled != 2))[1:-1, 1:-1]).astype(np.uint8)
    n, lbl, stats, cent = cv2.connectedComponentsWithStats(holes, 8)
    return sub, lbl, stats, cent, n


def border_vote(path):
    """Which quarter turn the prints' borders think is needed, or None.

    An instax has a 4 mm border above its picture and a 20 mm signature border
    below, so walking out of a window until the paper ends should say which way
    is down. Two corrections over the naive version, and neither is enough --
    see the module docstring:

    - the walk is capped, because in a merged blob the paper runs on into the
      next card and "distance until the paper ends" is a property of the pile;
    - opposite pairs are compared rather than all four directions, because a
      card in a row has free top and bottom but neighbours left and right, and
      the capped neighbour distances would otherwise win outright.
    """
    got = windows(path)
    if got is None:
        return None, []
    sub, lbl, stats, cent, n = got
    h, w = sub.shape
    area_min = MIN_WIN_FRAC * h * w
    votes, per = np.zeros(4), []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] <= area_min:
            continue
        short = min(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
        cap = max(4, int(CAP_FRAC * short))
        cy, cx = int(round(cent[i][1])), int(round(cent[i][0]))
        run = []
        for dy, dx in DIRS:
            y, x, dist, outside = cy, cx, 0, False
            while dist < cap:
                y += dy
                x += dx
                if not (0 <= y < h and 0 <= x < w):
                    break
                if not outside:                     # still crossing our own window
                    if lbl[y, x] == i:
                        continue
                    outside = True
                if not sub[y, x]:                   # off the paper, or into another window
                    break
                dist += 1
            run.append(dist)
        down, left, up, right = run
        vert = max(down, up) / max(min(down, up), 1)
        horz = max(left, right) / max(min(left, right), 1)
        area = float(stats[i, cv2.CC_STAT_AREA])
        if max(vert, horz) >= MIN_RATIO:
            idx = (0 if down > up else 2) if vert >= horz else (1 if left > right else 3)
            votes[idx] += area
            per.append((area, run, NAMES[idx]))
        else:
            per.append((area, run, "-"))
    return (int(np.argmax(votes)) if votes.any() else None), per


def truth():
    """{path: quarter turns} from every batch's report.csv, multi-print only."""
    out = {}
    for folder in sorted(os.listdir("chekis")) if os.path.isdir("chekis") else []:
        report = os.path.join("chekis", folder, "report.csv")
        if not os.path.exists(report):
            continue
        with open(report, newline="") as fh:
            for row in csv.DictReader(fh):
                # single cards are stood up by orient(), not by content rotation
                if row["kind"] not in ("aligned", "multi", "single?"):
                    continue
                path = os.path.join("chekis", folder, row["file"])
                if os.path.exists(path):
                    out[path] = int(round(float(row["reorient"] or 0) / 90)) % 4
    return out


def main():
    answers = truth()
    if not answers:
        sys.exit("no report.csv with a reorient column found under chekis/")
    rows = []
    for path, want in sorted(answers.items()):
        guess, per = border_vote(path)
        rows.append((path, want, guess, len(per)))

    voted = [(w, g) for _, w, g, _ in rows if g is not None]
    right = sum(1 for w, g in voted if w == g)
    wrong = [(p, w, g) for p, w, g, _ in rows if g is not None and g != w]
    print("CAP=%.2f RATIO=%.1f over %d frames: %d abstain, %d right, %d WRONG"
          % (CAP_FRAC, MIN_RATIO, len(rows), len(rows) - len(voted), right, len(wrong)))

    need = [(w, g) for _, w, g, _ in rows if w != 0]
    print("  of the %d needing a turn: %d right, %d wrong, %d abstain"
          % (len(need), sum(1 for w, g in need if g == w),
             sum(1 for w, g in need if g is not None and g != w),
             sum(1 for w, g in need if g is None)))
    upright = [(w, g) for _, w, g, _ in rows if w == 0]
    print("  of the %d already upright: %d left alone, %d TURNED WRONGLY"
          % (len(upright), sum(1 for w, g in upright if g in (None, 0)),
             sum(1 for w, g in upright if g not in (None, 0))))

    # Where the signal survives: with one or two prints a card's borders are
    # mostly free, in a pile every border abuts another card's paper.
    buckets = {}
    for _, want, guess, nwin in rows:
        if guess is None:
            continue
        key = "1-2" if nwin <= 2 else ("3-5" if nwin <= 5 else "6+")
        b = buckets.setdefault(key, [0, 0])
        b[0 if guess == want else 1] += 1
    print("  by prints in frame:")
    for key in ("1-2", "3-5", "6+"):
        if key in buckets:
            print("     %-4s %2d right, %2d wrong" % (key, *buckets[key]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
