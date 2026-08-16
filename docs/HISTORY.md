# Processing history

Every batch run so far, with measured before/after. Useful as regression baselines:
re-running a batch should reproduce the "after" column. All figures are RGB triples
in 0–255, `sd` is the spread across the files in that batch.

Measurement method is in `docs/PIPELINE.md` § Verifying a change.

---

## Targets

White **238.8**, black **2.2**. Fixed across every batch below — that is what makes
photos from different sessions sit together. Desk targets are per-folder medians and
are *not* comparable between folders.

---

## chekis/main/ — main collection (26 files, dark walnut desk)

(Ran at the time as the top-level `chekis/`, before that name was reused for
the photo-storage root that now holds `main/` plus the ad hoc batches below.)

Built up over several runs: 20 files, then 4 more, then 2 re-done.

| | white | black | desk |
|---|---|---|---|
| before | 235.4, 241.1, 239.8 (sd 4.8/2.9/4.7) | 3.2, 1.6, 1.9 (sd 2.0/0.9/1.0) | 61.8, 41.5, 30.3 (sd 5.8/3.6/4.9) |
| **after** | **239.6, 240.0, 240.2 (sd 1.0/1.0/1.2)** | **3.1, 2.8, 2.6 (sd 0.5/0.3/0.3)** | **62.5, 40.8, 29.2 (sd 3.6/1.7/1.9)** |

Corrections were mild, ±12% gain. Notes:

- `20260811_012428` and `20260803_034441` needed the biggest lift (~12% red) and
  now clip 3.8% / 2.3% of pixels in the border.
- `20260804_005451` and `20260811_012446` have visibly greyer desks than the rest;
  pulled halfway only, because correcting them fully started tinting the prints.

### The two pine-desk files (`20260815_*`)

Shot on a **different, lighter desk** under much cooler light. Borders started at
181, 220, 246 — red needed +85%, blue −10%, against the ±12% everything else
wanted. Landed at 238/239/239 and 239/239/238 with black 3.0/2.6/2.8 and
2.3/2.5/2.4, i.e. inside the batch's own spread.

The desk will never match the walnut set and no global curve can fix that. The
large red gain also amplifies red shadow noise slightly — invisible at normal
size, visible if you crop deep into a dark area.

### Later additions

`20260804_005620`, `20260804_005646` (walnut, desk-matched with the batch),
`20260812_002059`, `20260812_002138` (a lighter tan surface and a tight crop with
no desk — whites and blacks only). All four came in cooler and darker than the
walnut batch, needing 20–65% red gain against the batch's ±12%.

### 24 more photos (2026-08-15)

Spans `20260521`–`20260630`, mostly multi-print grids and a handful of singles.
18 of 24 landed in `balanced/` (5 singles cropped cleanly, 13 multi-print left
whole); 6 near-misses went to `review/`, all correctly declined rather than
force-fit — including a genuinely overlapping two-print shot and, more
surprisingly, a 7-print grid photo (`20260611_063147`) whose overall bounding
box happened to land at aspect 1.516, inside the near-miss band, purely by
coincidence. Not a bug: `review/` is exactly where an ambiguous-looking fit
should go, and a glance at the photo makes the right call obvious. Worth
knowing about if near-miss volume ever looks surprising on a future batch.

| | white | black |
|---|---|---|
| before | 207.1, 211.9, 211.8 (sd 10.2/10.8/13.2) | 3.52, 2.44, 3.14 (sd 3.6/2.9/4.0) |
| **after** | **239.5, 239.7, 239.5 (sd 1.5/1.6/2.0)** | **3.09, 2.70, 2.68 (sd 0.7/0.5/0.8)** |

(18 balanced files only — the 6 in `review/` are uncropped and unflagged for
colour, so mixing them in would understate the spread.)

The 5 cleanly-cropped singles landed aspect 1.583–1.631, border ratio 2.16–2.41
— comfortably inside tolerance, no hand fixes needed.

**Bug found and fixed while processing this batch:** `20260630_140740` has a
large near-pure-black region (multiple dark-background prints), which pushed
its 0.5th-percentile luminance down to exactly the frame's true minimum.
`measure()`'s black mask used a strict `<` against that percentile, so ties at
the minimum matched nothing — an empty mask, a NaN black point, and a
NaN-poisoned gain that would have written a corrupted file to `balanced/`
without ever raising a flag. Changed to `<=` with a `lum.min()` fallback if
still empty. Any future photo with a large enough dark region could have hit
this; there was nothing folder-specific about it.

---

## sova_song_chekis/ — 12 files, 6 fronts + 6 backs

The only batch containing backs. See `docs/PIPELINE.md` § The backs exception.

| | white | black | desk |
|---|---|---|---|
| fronts before | 205.8, 211.8, 208.5 (sd 6.3/6.2/8.2) | 3.0, 2.3, 2.5 | 57.8, 38.5, 28.0 (sd 1.7) |
| **fronts after** | **238.8, 239.0, 238.7 (sd 0.4/0/0.5)** | **3.0, 3.0, 2.8** | **68.3, 44.3, 33.2 (sd ~1.0)** |
| backs before (paper edge) | 177–201, 218–234, 240–247 | 9.7, 6.7, 8.7 (sd 6) | 108, 92, 79 (sd 13) |
| **backs after (paper edge)** | **241.2, 240.5, 242.8 (sd 4.7/2.9/1.2)** | **4.2, 2.7, 2.5** | **135.6, 97.6, 77.2** |

The backs' desk sits ~135 against the fronts' ~68: the phone metered brighter for
the dark film. The two sets are matched **within** themselves, not to each other —
pulling them together would have meant darkening every back substantially.

Files needing hand-work: `035516` (corners measured by hand — dark back on an
unusually light patch of desk, the fit kept snapping to the film's inner boundary),
`035600` and `035651` (overcropped left and right; corners measured by hand, plus
a hand-tuned inset on one edge each).

---

## rancheki/ — 21 files, 11 single prints + 10 multi-print

| | white | black | desk (multi shots only) |
|---|---|---|---|
| before | 201.4, 212.2, 215.8 (sd 8.8/7.0/9.0) | 2.7, 2.0, 2.4 (sd 2.1/1.8/2.3) | 54.7, 35.0, 25.2 (sd 4.4/2.8/2.5) |
| **after** | **239.9, 240.0, 240.5 (sd 1.9/1.0/2.3)** | **2.8, 2.6, 2.6 (sd 0.7/0.7/1.0)** | **65.2, 42.3, 31.0 (sd 5.7/2.4/1.9)** |

Folder desk target came out at 68.7, 44.3, 31.6 from 17 images.

All 11 singles cropped cleanly (measured aspects 1.54–1.62 against instax's 1.593).
Five were lying rotated 90° on the desk; ten needed a 180° flip, only `031909` was
already upright. `031909` and `033346` had a wedge of desk surviving on two edges
each and were trimmed by hand.

`20260630_062001471` was added later: a two-print close-up with the cards running
past the frame edge, so it cannot be cropped even in principle. Only needed ~8% on
red — the closest to neutral of anything in the folder.

---

## Automation results

`checleaner.py` run over `rancheki/` unattended: **19 of 20 to `balanced/`,
1 to `review/`**. All 11 singles cropped, deskewed and turned upright; all 8
multi-print shots balanced and left whole. Colour output indistinguishable from
the hand pass — white 239.9, 239.9, 240.7 against 239.8, 240.0, 240.4.

The one flagged file, `20260601_053951`, is the three-print shot: a clean rectangle
at aspect 1.884, genuinely ambiguous between "three prints in a row" and "one print
fitted badly". Correct behaviour — it should ask.

`checleaner.html` on the same 11 singles: **11 of 11, no warnings.** Aspects 1.579–1.611,
border ratios 2.02–2.18. Gains match the Python to ~1% (`033253`: 1.596, 1.324,
1.244 in the browser against 1.579, 1.309, 1.242 on desktop). ~2 s per photo on a
desktop CPU, expect 5–10 s on a Pixel 7.

---

## Paper-frame detector ported to checleaner.py (2026-08-15)

`checleaner.py`'s `detect_print` now uses the paper-frame method described in
`docs/PIPELINE.md` § 3, replacing "everything that isn't desk". Re-run against
`rancheki/` (22 files now — one single was added after the count above was
written):

All 12 singles fit, aspects **1.568–1.611**, closely matching the JS's own
1.579–1.611 on the same folder — a big tightening from the old method's
1.54–1.62. The one file below 1.579 is `033346`, already on record above as
needing hand-trimming in both implementations, so it being the outlier in both
is expected rather than a regression. All 10 historical multi/near-miss cases
still classify the same way, including `053951339` (the three-print shot)
still landing at aspect 1.884 and correctly flagged as a near-miss rather than
silently accepted or silently dropped.

### EXIF on the phone app

`checleaner.html` now splices the source photo's raw EXIF APP1 segment into
the saved JPEG (method in the file's own comment above `findExifSegment`).
Verified two ways:

- A synthetic file (orientation 6, a thumbnail, a crafted date) round-tripped
  through the extracted `findExifSegment`/`patchExifSegment` functions: date
  preserved, orientation reset to 1, thumbnail IFD link severed, dimensions
  updated.
- Playwright end-to-end through the real page on two `rancheki/` photos, one
  cropped-single and one uncropped-multi: both saved files carried the
  source's capture date and GPS unchanged, orientation normal, and pixel
  dimensions matching the actual output.

Caught in the process: the initial `"Exif\0\0"` signature check had two byte
bugs (a transposed `i`/`f`, and one byte too many in the comparison) that made
it never match, so EXIF would have silently never been copied. Both were only
visible by actually running bytes through it — worth remembering if this code
is touched again without a test alongside it.

---

## Multi-print alignment added to checleaner.py (2026-08-15)

Multi-print photos were balanced and left whole; `align_multi()` (method in
`docs/PIPELINE.md` § 6) now also rotates the frame level and crops it centred
on the prints when it safely can, at the original photo's aspect ratio.
Python only for now — porting to `checleaner.html` is next steps item 2.

Test file: `chekis/main/PXL_20260427_023437053.MP.jpg` (two touching prints,
tilted ~1.5°) — verified both by inspecting the geometry directly (target and
achieved crop ratio agreed to 4 decimal places; top/bottom margins agreed to
0.001px, left/right to five nines) and by eye on the actual rendered output.

Ran over all of `chekis/main/`'s 49 files: 11 ordinary multi-print photos got
aligned (tilts found: -0.36° to 1.47°, all single-blob since touching prints
in this folder merge into one paper-frame blob — the code doesn't require
that, it's just what this folder happens to contain). Alignment and colour
flags are independent, as intended: a few aligned files still routed to
`review/` for pre-existing white-reference clipping, unrelated to the crop.

Confirmed the "leave it whole" fallback also fires correctly:
`20260521_073507` has two prints laid out on the diagonal, filling the frame
corner to corner with almost no desk margin. A centred, level crop of that
would need padding that isn't in the photo, so `align_multi()` correctly
declined and it was left as an ordinary whole-frame multi.

---

## Known unfixable, so nobody re-litigates them

- **Blown white references.** Where the paper is already clipped in the original
  (the backs, 3–11% of band pixels), the true value is not recoverable. That is a
  shooting fix — one stop down — not a processing one.
- **Different desks.** Pine and walnut will not match. Neither will a back's desk
  and a front's when the phone metered them two stops apart.
- **Cards running out of frame.** Cannot be cropped; needs a re-shoot.
- **Backs' long edges.** Almost no paper margin, so film meets desk directly. What
  looks like a bad crop there is usually the card itself.
