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

## report.csv gets a dest column, review/ gets a report.txt (2026-08-15)

Reported gap: `review/` is where anything the pipeline isn't confident about
goes, with a flag explaining why — but that only worked if you watched the
per-file console line or knew that "empty `flags` in report.csv" means
`balanced/`, nothing else marks it. Fine at a terminal, not fine when a run is
driven by an agent and the flags/dest logic never gets explained to the
person actually looking at the files afterward.

`report.csv` now has an explicit `dest` column (`balanced` or `review`),
derived from the same `flags`-empty check used to actually route the file, so
it can't drift out of sync with reality. `review/report.txt` lists just the
flagged files and their reasons, written into `review/` itself so it's next
to the photos it's talking about rather than requiring a cross-reference.

---

## checleaner.py skips already-processed files (2026-08-15)

Reported problem: a full run over a growing `chekis/main/` was taking a
while, because every run reprocessed every file, including ones from months
ago that will never change. Profiling pinned the cost on the full-resolution
colour pass (`apply()`, ~3 s/photo) — detection and the thumbnail-based
measurement pass are cheap by comparison (well under 1 s).

Considered per-directory `pending/`/`processed/` splitting for the *source*
photos, but the pipeline is already deterministic, so the simpler fix is to
check the *output*: a file already in `balanced/` or `review/` is skipped,
reusing its prior `report.csv` row for stats/flags, unless `--force`. No
directory reorganizing needed, and it also means a hand-fixed `review/` file
no longer gets silently clobbered by the next run (it did before this).
Pass 1 still measures every file regardless, so the folder-wide desk target
stays accurate even when pass 2 is skipped for most of them.

Bug caught while testing this against the real folder: a handful of files
that had been reclassified `balanced/` → `review/` across earlier runs this
session still had a stale copy sitting in the old directory. The first
version of the skip check looked in `balanced/` before `review/` and trusted
whichever it found first, so it happily "skipped" a stale, wrong-directory
copy and reported it as up to date. Fixed two ways: a file present in *both*
directories is now treated as unresolved and reprocessed (which cleans up
the duplicate as a side effect, via a new stale-copy removal on every fresh
write, not just skip checks); real run on `chekis/main/` confirmed all 18
existing duplicates cleared to 0 and reprocessed correctly.

Measured effect on `chekis/main/`'s 49 files: a no-op rerun (nothing new)
dropped from ~8 minutes to ~65 s -- all of that remaining time is the pass-1
measurement, which is unavoidable since the desk target needs it. Adding one
new file processed only that file, confirmed by timing.

---

## Orientation bugs found while reviewing a fresh batch (2026-08-16)

User caught 6 misoriented files in `chekis/main/` across two categories.

**Real bug, fixed:** `orient()`'s row profile was a *mean* across the row,
which a strong partial-width edge inside the photo can win even though it has
nothing to do with the border -- found on `20260427_022950306`, where the
"bottom" edge it locked onto was the boundary between a subject's pale face
and dark hair, not the paper transition. That transition was real and
full-width, just lower-contrast than the face/hair edge at that particular
photo, so the *mean* profile missed it while a 20th-percentile profile found
it cleanly (confirmed by cropping the row band and looking directly at it).
Confidently wrong too: border ratio 2.07, comfortably above the 1.6 trust
threshold, so this wasn't something the existing uncertainty flag would have
caught. Fixed in `orient()`; see `docs/PIPELINE.md` § 5. Regression-tested
against all 12 known-good singles in `chekis/rancheki/` -- identical flip
decision on every one, so nothing that worked before changed.

**Investigated, not fixed:** 3 more files came out level and centred
(`align_multi()` worked correctly) but still sideways, because the *prints
themselves* are landscape-oriented content on portrait-shaped physical cards
-- confirmed by looking at the raw source photos, where the cards are already
sideways before any processing touches them. No part of the pipeline has ever
attempted to detect this, since it requires reading print content, not card
geometry, and `align_multi()` only rotates the whole frame.

Tried a geometric proxy anyway: a merged blob's aspect ratio, combined with
whether its long edge ended up vertical or horizontal, can in principle tell
"K landscape cards stacked" apart from "K portrait cards in a row" (they
share the identical aspect otherwise). Matched all 3 known-sideways files.
Then swept every multi/aligned file in the folder and it also fired on two
correctly-oriented grids of 10 and 13 cards -- their overall aspect happened
to land near the same `k=2` ratio for reasons that have nothing to do with
any individual card's orientation. ~30% precision (3 of 10 flagged files were
real). Not shipped, not even as a review flag: a flag that's wrong 7 times
out of 10 gets ignored, which is worse than no flag. Full writeup in
`docs/PIPELINE.md` § 6, so this isn't re-attempted the same way without
knowing why it doesn't work. The 2 remaining near-miss files the user flagged
were never processed for orientation at all -- `single?` output is always
just the balanced whole frame, by design, so their sideways/upside-down
appearance is simply how the phone captured them.

Actually fixing the landscape-print case needs per-print detection (splitting
merged blobs into individual cards, next steps item 3 in `CLAUDE.md`) so each
print's own content -- not the merged group's incidental shape -- can be
reasoned about.

---

## Two more real bugs found in the same review pass (2026-08-16)

Same session, different symptom: user flagged 3 files in `review/` as
overcropped. Two distinct bugs, both real, both fixed.

**`trim_desk()`'s desk-hue reference can be near-white.** It samples a ring
around the *original photo's* outer edge and assumes that's desk. On
`20260803_034511524` and `20260803_034606768`, the card fills nearly the
whole frame, so that ring instead sampled the card's own border -- reference
colour came back at L≈240 with chroma magnitude (`nv`) 2.0 and 2.24. A hue
*direction* derived from an almost-neutral reference is essentially noise,
and the projection test downstream (`proj > 0.55*nv`) turns hypersensitive
when `nv` itself is tiny, flagging the border's ordinary chroma jitter as
desk. Confirmed by reproducing the exact pipeline (color-corrected image,
same as `run()` uses, not the raw file -- the first repro attempt used the
raw image and didn't show the bug) and measuring actual pixel brightness
across the output's left/right edges to prove the border really was cut to
~3% instead of the expected ~5.5%. Swept `nv` across all of `chekis/rancheki/`
plus the rest of `chekis/main/`: every working file measured >= 3.6, both
broken files measured ~2.0-2.24 -- clean separation. Fixed by skipping the
trim entirely below `nv = 4` rather than trust a hue direction that thin.
Zero regressions on the rancheki regression set (all residual-desk checks
still pass at 0px).

**A tight grid of cards can pass the single-card test.**
`20260811_012314592` is an 11-card grid, not a single print, but the merged
blob's overall aspect (1.626) and fill (0.944) both happened to land inside
the single-card acceptance window, so it got warped and cropped as if it
were one card -- the "crop" ended up keeping nearly the entire original
frame (quad spanned 82% of the width, 99.9% of the height). Tried "does the
blob touch the frame edge" as a discriminator first; rejected it after
finding a *known-good* single (`20260812_002138234`, a legitimate close-up
shot) with the same near-zero margin on every side -- edge-touching alone
isn't safe. The signal that actually works: solidity, raw contour area over
convex hull area. A real card's border has no internal seams, so its raw
contour already equals its hull (solidity 1.0000, confirmed on
`20260812_002138234`); the 11-card grid's seams between cells leave notches
that only the hull smooths over (solidity 0.9424). Swept solidity across
every currently-accepted single in both `chekis/rancheki/` and `chekis/main/`
-- next-lowest was 0.9895, a comfortable margin above the break case. Added
`--min-solidity` (default 0.97) as a fourth acceptance gate alongside
aspect/fill; the grid file now correctly falls through to the near-miss path
and lands in `review/` with a clear reason instead of a distorted crop.

---

## Splitting multi-print photos into per-print crops: tried, backed out (2026-08-16)

Attempted Next-steps item 3 -- carve a merged multi-print blob into one crop
per print (`split_prints()` and friends: window-hole detection, union-find
fragment clustering, dual portrait/landscape hypothesis). It ran end to end and
handled real overlap, but was reverted, for two reasons:

- **Wrong problem.** The actual ask behind "some images end up sideways" was only
  to *detect* that a photo holds several prints so the pipeline stops cropping and
  rotating it as if it were one card. That detection already exists: a multi-print
  blob fails the tight single-card gate (aspect/fill/**solidity**, the last added
  in the 2026-08-16 grid-as-single fix) and is left whole (`multi`/`aligned`) or
  flagged `single?`. On the seven cited overlap photos, `tools/detect.py` confirms
  none classify as `single`, so none can come out sideways. Splitting was never
  needed to fix the reported symptom.
- **The crops were unreliable anyway.** Reconstructed split quads don't actually
  carry a real card's 1.593 aspect, and `warp()` force-fits every crop to
  1800×2867 -- so mis-estimated quads came out visibly squished. Splitting stays a
  future item, but the reconstruction needs to be evidence-tight enough to hit the
  true card rectangle before it's worth shipping.

Kept from the exercise: `tools/detect.py`, a detection-only preview that gives
run()'s single/single?/multi verdict on named files sub-second each, so detection
geometry can be iterated without grinding the whole batch's colour pass.

## Multi-print frames stood upright from content (2026-08-16)

Five `chekis/main/` frames came out of `align_multi()` level but sideways or
upside down -- the long-standing "landscape prints" limitation, previously
filed as unfixable because card geometry can't tell portrait from landscape.
The fix reads the *content* instead: `content_rotation()` scores each 90° turn
by face confidence (YuNet) and takes the one that stands the most faces upright.
See `docs/PIPELINE.md` § 6 for why geometry couldn't and faces can.

Files corrected (turn = 90° CCW units):

| file | layout | turn |
|---|---|---|
| PXL_20260427_023359428 | 1 row of 2 portrait | 90° |
| PXL_20260501_015640226 | 1 row of 3 portrait | 90° |
| PXL_20260501_015731072 | 1 row of 3 portrait | 90° |
| PXL_20260427_023126095 | 1 row of 2 landscape + 1 row of 4 portrait | 90° |
| PXL_20260427_023727013 | 1 row of 4 portrait | 180° |

No regressions: swept all 49 multi/aligned/`single?` frames, exactly these five
turned, the other 44 (including a 0°-vs-180° near-tie at 1.61 vs 1.82 that the
1.5× margin protects) were left byte-identical. The turn is recorded in the new
`reorient` column of `report.csv`. Model is YuNet (~230 KB), cached under
`~/.cache/checleaner/`; without it the step no-ops and the old leave-it-level
behaviour returns.

## Multi-print alignment ported to the phone app (2026-08-16)

`checleaner.html` used to balance a multi-print photo and leave it whole. It now
levels and centres it too: `alignMulti()` is a faithful port of `align_multi()`
(same fold-to-[-45,45) tilt, area-weighted circular mean, footprint check).
Verified with Playwright against the five multi-print files — output dimensions
match the desktop tool's to within a pixel or two (e.g. 015731072: web
2479×3291 vs Python 2482×3297).

Content reorientation (faces) was *not* ported — an offline single-file page
can't ship an ONNX model. Instead the app gained ⟲ 90° / 180° / ⟳ 90° buttons,
so a levelled-but-sideways result is one tap from upright. Single-card output is
unchanged (still 1800×2867, still flags residual desk).

## Multi-print crops get a best-fit aspect ratio (2026-08-16)

`align_multi()` used to crop at the source photo's own aspect ratio. Now it
picks the best fit from `CROP_ASPECTS` (4:3, 3:4, 1:1, 16:9 -- a module-level
list, extend it there): tightest crop per candidate, scored by how balanced the
horizontal-vs-vertical margins come out; a candidate that would poke outside
the photo is disqualified, and if all are, the old own-ratio behaviour is the
fallback -- so a print can never be cut off. Recorded in `report.csv`'s new
`align_crop` column.

Because a quarter turn flips a crop's aspect (a 16:9 turned upright becomes the
9:16 the list deliberately excludes), the face-derived content turn is now
decided *first*, on the balanced frame, and folded into the alignment warp --
one rotation instead of rotate-then-rot90. Verified on the three previously
turned aligned files: same 90° turn detected, output now 4:3, and re-running
face detection on the result confirms upright.

Sweep of all 15 aligned files in `chekis/main/`: 8 chose 4:3, 5 chose 1:1
(grids), 2 fell back to original (tall diagonal layouts where every candidate
poked outside -- one at frame ratio 0.753, a hair off 3:4's 0.750, which is the
fallback working at the margin, not a bug). None declined that aligned before.

## Overlapping prints cleared from review by counting photo windows (2026-08-16)

Two files the user called "easily croppable" were stuck in review as `single?`
near-misses: overlapped prints merge into one blob whose shape stats can beat a
genuine card's (023727013, a 4-print row: fill 0.988, solidity 0.991 -- white
border on white border leaves no seam to catch; 023126095's two-row layout even
lands aspect 1.545, inside the single-card window). Shape alone cannot tell
these from a badly-fit single card, which is exactly what the near-miss gate
exists to catch.

The pictures can: each print's photo area stays a separate enclosed hole in the
paper mask. `count_windows()` (salvaged from the abandoned split_prints work)
counts them. Sweep of all 66 files: genuine singles measure 1-6 (the high ones
are windows fragmented by bright content bridging to the border), merged
multi-print blobs 7-18, with the two complaint files at 10 each. Threshold
`--multi-windows 7` -- one above the worst genuine single. Boundary files at
5-8 windows were eyeballed: all genuinely multi, so the ones under threshold
merely stay in review (safe direction; a missed flip costs one review, a wrong
flip would skip review for a card that needed hand-cropping).

Result of the --force rerun: of the 14 former `single?` files, the 10 with >= 7
windows went down the align path (levelled, best-fit-cropped, reoriented) and
the 4 with fewer stayed `single?`. Seven of the ten moved out of review into
balanced; the other three reclassified but kept a *different* flag (blown white
reference, mostly) so stayed in review on their own merit. Net: balanced
40 -> 47, review 26 -> 19.

## Window backstop extended to catch single-gate passers (2026-08-16)

Reshooting the clipped-border files (see above) surfaced a bad crop: a reshot
3-print row (012024586) landed aspect 1.639, fill 0.994, solidity 0.992 -- all
inside the single-card gate -- so it was warped into one card and rotated
sideways, the only tell a border ratio of 12. The window count that already
caught overlapping *near-misses* was only being run on blobs that *failed* the
single test; a row tidy enough to pass sailed past it. Fixed by running
`count_windows()` for single-gate passers too and demoting any with >=
`--multi-windows` windows. 012024586 (7 windows) now balances as a whole
multi-print frame instead of a mangled single. Full --force rerun: every kept
single measures 1-6 windows (no genuine card wrongly demoted), 55/11 split
unchanged.

## Aligned crops recentred on real paper for even margins (2026-08-16)

A grid photo (041037832) came out with its top prints jammed against the edge
and a desk strip along the bottom. Cause: the segmentation close bridged the
bottom prints to a patch of bright desk near the frame edge, so the blob's
bounding box overshot ~70 px past the real prints, sliding the (centred) crop
down. A margin sweep of all aligned files found this on 4 of them: one edge
tight, the opposite 33-69 px loose.

Fixed with `_paper_center()`: recentre the crop on the actual paper extent
(bright + near-neutral, opened but *not* closed -- the close is what reaches
into the glare), trusted only when that span tracks the blob's size and the
implied shift is small. After a --force rerun the worst top/bottom gap fell from
69 px to 6, mean ~2 px, no file over 15; already-even crops were untouched
(023359428 stayed 0/0). New opt-in test asserts balanced margins on the three
worst former offenders.

## Known unfixable, so nobody re-litigates them

- **Blown white references.** Where the paper is already clipped in the original
  (the backs, 3–11% of band pixels), the true value is not recoverable. That is a
  shooting fix — one stop down — not a processing one.
- **Different desks.** Pine and walnut will not match. Neither will a back's desk
  and a front's when the phone metered them two stops apart.
- **Cards running out of frame.** Cannot be cropped; needs a re-shoot.
- **Backs' long edges.** Almost no paper margin, so film meets desk directly. What
  looks like a bad crop there is usually the card itself.
  (Multi-print frames coming out sideways used to live here too; now fixed by
  content-based reorientation -- see the 2026-08-16 entry above.)
